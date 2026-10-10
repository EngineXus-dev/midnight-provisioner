"""Kali recovery-copy binding: synthetic files only; no libvirt or guest start."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from nightglass.cli import main
from nightglass.kali_recovery_link import KaliRecoveryLink, save_kali_recovery_link
from nightglass.kali_setup import build_setup_plan, save_setup_plan
from nightglass.recovery import _recovery_xml
from nightglass.runner import ToolError

OLD = "nightglass-kali-recon"
NEW = "nightglass-kali-recon-restore-test"
UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def domain(path, *, uuid=UUID, extra="", nvram=None):
    firmware = f"<os><nvram>{nvram}</nvram></os>" if nvram else ""
    return (
        f'<domain type="kvm"><name>{OLD}</name><uuid>{uuid}</uuid>'
        f'{firmware}<memory unit="MiB">2048</memory><vcpu>1</vcpu>'
        '<devices><graphics type="vnc" listen="127.0.0.1"/>'
        f'<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>'
        f'<source file="{path}"/><target dev="vda" bus="virtio"/></disk>'
        f'{extra}</devices></domain>'
    )


# Native Windows cannot perform POSIX fchmod. Isolate this capability only
# while running synthetic module tests; production Linux enforcement is intact.
_fixture_mode_patch = None


def setUpModule():
    global _fixture_mode_patch
    if os.name == "nt":
        _fixture_mode_patch = patch("nightglass.kali_setup.os.fchmod", create=True)
        _fixture_mode_patch.start()


def tearDownModule():
    global _fixture_mode_patch
    if _fixture_mode_patch is not None:
        _fixture_mode_patch.stop()
        _fixture_mode_patch = None


class KaliRecoveryLinkTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.plan = self.root / "kali-plan.json"
        save_setup_plan(build_setup_plan("recon"), self.plan)
        self.backup = self.root / "original-cold-backup"
        self.staged = self.root / "new-recovery-staging"
        (self.backup / "disks").mkdir(parents=True)
        (self.staged / "disks").mkdir(parents=True)
        self.original_vm_disk = self.root / "manually-installed-disk.qcow2"
        self.original_vm_disk.write_bytes(b"original-disk-untouched")
        self.archive_disk = self.backup / "disks/disk-01.qcow2"
        self.archive_disk.write_bytes(b"identical-backed-up-bits")
        self.staged_disk = self.staged / "disks/disk-01.qcow2"
        self.staged_disk.write_bytes(self.archive_disk.read_bytes())
        self.archive_xml = self.backup / "domain.xml"
        self.archive_xml.write_text(domain(str(self.original_vm_disk)), encoding="utf-8")
        self.staged_xml = self.staged / "domain.xml"
        self.write_backup()
        self.write_stage()
        self.expected_source_bytes = self.archive_disk.read_bytes()

    @staticmethod
    def record(path, kind, name, *, source=None):
        data = path.read_bytes()
        row = {
            "kind": kind, "path": name,
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        }
        if source is not None:
            row["source"] = source
        return row

    def write_backup(self, *, domain_name=OLD, policy="lab"):
        rows = [
            self.record(
                self.archive_disk, "disk", "disks/disk-01.qcow2",
                source=str(self.original_vm_disk),
            ),
            self.record(self.archive_xml, "xml", "domain.xml"),
        ]
        nvram = self.backup / "firmware/nvram.bin"
        if nvram.exists():
            rows.append(self.record(nvram, "nvram", "firmware/nvram.bin",
                                    source=str(self.original_nvram)))
        (self.backup / "manifest.json").write_text(json.dumps({
            "format": "nightglass-cold-backup", "version": 1,
            "domain": domain_name, "policy": policy, "files": rows,
        }))
        return rows

    def write_stage(self, *, original=OLD, original_policy="lab",
                    guest=NEW, xml_content=None):
        rows = json.loads((self.backup / "manifest.json").read_text())["files"]
        xml_content = xml_content if xml_content is not None else _recovery_xml(
            self.backup, tuple(rows), OLD, guest, "lab", self.staged,
        )
        self.staged_xml.write_text(xml_content, encoding="utf-8")
        items = [
            self.record(self.staged_disk, "disk", "disks/disk-01.qcow2"),
            self.record(self.staged_xml, "xml", "domain.xml"),
        ]
        nvram = self.staged / "firmware/nvram.bin"
        if nvram.exists():
            items.append(self.record(nvram, "nvram", "firmware/nvram.bin"))
        (self.staged / "recovery-manifest.json").write_text(json.dumps({
            "format": "nightglass-recovery-staging", "version": 1,
            "guest": guest, "original_guest": original,
            "original_policy": original_policy,
            "network": "offline", "files": items,
        }))

    def check(self):
        return KaliRecoveryLink().inspect(self.plan, self.backup, self.staged)

    def test_identical_independent_offline_copy_matches_without_modifying_files(self):
        before = {
            p: p.read_bytes()
            for p in (
                self.plan, self.original_vm_disk, self.archive_disk,
                self.staged_disk, self.archive_xml, self.staged_xml,
            )
        }
        with patch("nightglass.kali_recovery_link.save_acceptance") as save, \
             patch("nightglass.kali_recovery_link._recovery_xml", wraps=_recovery_xml) as transformer:
            report = self.check()
            save.assert_not_called()
            transformer.assert_called_once()
        self.assertTrue(report.ok, report.describe())
        self.assertEqual(report.original_guest, OLD)
        self.assertEqual(report.recovered_guest, NEW)
        self.assertEqual(report.matched_assets, 1)
        self.assertIn("NOT RESTORE-PROVEN", report.describe())
        self.assertFalse(report.evidence()["guest_boot_tested"])
        self.assertFalse(report.evidence()["restore_tested"])
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_source_plan_wrong_guest_never_passes(self):
        save_setup_plan(build_setup_plan("web-audit"), self.root / "other-plan.json")
        self.plan = self.root / "other-plan.json"
        r = self.check()
        self.assertFalse(r.ok)
        self.assertIn("differs from the selected Kali setup plan", r.describe())

    def test_backup_source_and_staging_must_match_original_guest(self):
        self.write_backup(domain_name="other-guest")
        self.assertIn("Original backup guest differs", self.check().describe())
        self.write_backup()
        self.write_stage(original="other-guest")
        self.assertIn("Recovered staging source guest differs", self.check().describe())

    def test_tampered_staged_disk_fails_before_source_xml_reconstruction(self):
        self.staged_disk.write_bytes(b"modified-but-not-in-manifest")
        with patch("nightglass.kali_recovery_link._recovery_xml") as transformer:
            with self.assertRaisesRegex(ToolError, "Staging integrity failure"):
                self.check()
            transformer.assert_not_called()
        self.assertEqual(self.archive_disk.read_bytes(), self.expected_source_bytes)

    def test_rewritten_stage_digest_cannot_mask_changed_copy(self):
        self.staged_disk.write_bytes(b"modified-and-rehashed-copy")
        self.write_stage()
        result = self.check()
        self.assertFalse(result.ok)
        self.assertIn("kind/size/digest differs", result.describe())

    def test_stage_recomputed_xml_cannot_add_another_safe_looking_device(self):
        original = self.staged_xml.read_text()
        # A second separate local disk passes general offline policy if the
        # staging manifest also includes it, but should not pass exact
        # cold-source-to-generated-XML binding here.
        new_xml = original.replace(
            "</devices>",
            '<controller type="usb" model="qemu-xhci"/></devices>',
        )
        self.write_stage(xml_content=new_xml)
        result = self.check()
        self.assertFalse(result.ok)
        self.assertIn("differs from the exact restricted", result.describe())

    def test_guest_nvram_requires_separate_exact_verified_copy(self):
        self.original_nvram = self.root / "original-nvram.bin"
        self.original_nvram.write_bytes(b"original-not-touched")
        (self.backup / "firmware").mkdir()
        (self.staged / "firmware").mkdir()
        (self.backup / "firmware/nvram.bin").write_bytes(b"verified-firmware-state")
        (self.staged / "firmware/nvram.bin").write_bytes(b"verified-firmware-state")
        self.archive_xml.write_text(
            domain(str(self.original_vm_disk), nvram=str(self.original_nvram))
        )
        self.write_backup()
        self.write_stage()
        good = self.check()
        self.assertTrue(good.ok, good.describe())
        self.assertEqual(good.matched_assets, 2)
        (self.staged / "firmware/nvram.bin").write_bytes(b"different-firmware-state")
        self.write_stage()
        report = self.check()
        self.assertFalse(report.ok)
        self.assertIn("kind/size/digest differs", report.describe())
        self.assertEqual(self.original_nvram.read_bytes(), b"original-not-touched")

    def test_backup_and_stage_must_not_be_same_or_nested_directory(self):
        with self.assertRaisesRegex(ToolError, "separate, not nested"):
            KaliRecoveryLink().inspect(self.plan, self.backup, self.backup)
        inside = self.backup / "inside"
        inside.mkdir()
        with self.assertRaisesRegex(ToolError, "separate, not nested"):
            KaliRecoveryLink().inspect(self.plan, self.backup, inside)

    def test_hardlinked_staged_disk_refused_even_with_matching_hashes(self):
        self.staged_disk.unlink()
        self.staged_disk.hardlink_to(self.archive_disk)
        self.write_stage()
        report = self.check()
        self.assertFalse(report.ok)
        self.assertIn("one-link", report.describe())

    def test_backup_or_stage_symlinked_directory_refused(self):
        alias = self.root / "alias"
        try:
            alias.symlink_to(self.staged, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("OS denies creation of synthetic symlinks")
        with self.assertRaisesRegex(ToolError, "symlink path"):
            KaliRecoveryLink().inspect(self.plan, self.backup, alias)

    def test_incomplete_and_missing_staging_content_block_before_comparison(self):
        (self.staged / "INCOMPLETE").write_text("incomplete")
        with self.assertRaisesRegex(ToolError, "INCOMPLETE"):
            self.check()
        (self.staged / "INCOMPLETE").unlink()
        self.staged_disk.unlink()
        with self.assertRaises(ToolError):
            self.check()

    def test_private_json_is_new_0600_and_never_overwrites(self):
        report = self.check()
        destination = self.root / "new-evidence.json"
        self.assertEqual(save_kali_recovery_link(report, destination), destination)
        if os.name != "nt":
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        content = destination.read_text()
        self.assertNotIn(str(self.root), content)
        self.assertIn("guest_imported", content)
        self.assertIn('"restore_tested": false', content)
        before = destination.read_bytes()
        with self.assertRaisesRegex(ToolError, "already exists"):
            save_kali_recovery_link(report, destination)
        self.assertEqual(destination.read_bytes(), before)

    def test_cli_action_returns_clear_pass_and_blocked_codes(self):
        args = [
            "templates", "recovery-link", str(self.plan),
            "--backup", str(self.backup),
            "--staged", str(self.staged),
        ]
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(args), 0)
        self.assertIn("FILES/XML ONLY", output.getvalue())
        self.write_stage(original="different-original-guest")
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(main(args), 2)
            self.assertIn("BLOCKED", output.getvalue())


if __name__ == "__main__":
    unittest.main()
