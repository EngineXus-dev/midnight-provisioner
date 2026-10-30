"""Synthetic verified Kali cold-backup baseline; never contact actual VMs."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from midnight_provisioner.cli import main
from midnight_provisioner.kali_cold_baseline import KaliColdBaselineInspector, save_cold_baseline_report
from midnight_provisioner.kali_setup import build_setup_plan, save_setup_plan
from midnight_provisioner.runner import Output, ToolError

GUEST = "midnight-provisioner-kali-recon"
UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
GIB = 1024 ** 3


def domain(disk, *, name=GUEST, uuid=UUID, nvram=None, extra=""):
    nvram_node = f"<os><nvram>{nvram}</nvram></os>" if nvram else ""
    return (
        f'<domain type="kvm"><name>{name}</name><uuid>{uuid}</uuid>'
        f'{nvram_node}<memory unit="MiB">2048</memory><vcpu>1</vcpu>'
        '<devices><graphics type="vnc" listen="127.0.0.1"/>'
        f'<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>'
        f'<source file="{disk}"/><target dev="vda" bus="virtio"/></disk>'
        f'{extra}</devices></domain>'
    )


# Native Windows cannot perform POSIX fchmod. Isolate this capability only
# while running synthetic module tests; production Linux enforcement is intact.
_fixture_mode_patch = None


def setUpModule():
    global _fixture_mode_patch
    if os.name == "nt":
        _fixture_mode_patch = patch("midnight_provisioner.kali_setup.os.fchmod", create=True)
        _fixture_mode_patch.start()


def tearDownModule():
    global _fixture_mode_patch
    if _fixture_mode_patch is not None:
        _fixture_mode_patch.stop()
        _fixture_mode_patch = None


class FakeHV:
    def __init__(self, current_xml):
        self.current = current_xml
        self.nextboot = current_xml
        self.state_value = "shut off"
        self.calls = []

    def _virsh(self, *args):
        self.calls.append(args)
        if args == ("dumpxml", GUEST):
            return self.current
        if args == ("dumpxml", "--inactive", GUEST):
            return self.nextboot
        raise AssertionError(f"Unexpected libvirt action: {args}")

    def state(self, guest):
        self.calls.append(("state", guest))
        return self.state_value


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.metadata = {"format": "qcow2", "virtual-size": 32 * GIB}

    def run(self, argv, timeout=12):
        self.calls.append(tuple(argv))
        if argv[:3] == ["qemu-img", "info", "--output=json"]:
            return Output(json.dumps(self.metadata))
        raise AssertionError(f"Unexpected operation: {argv}")


class KaliColdBaselineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.disk = self.root / "separate-recon.qcow2"
        self.disk.write_bytes(b"synthetic-source-disk-never-changed")
        self.original = self.disk.read_bytes()
        self.plan = self.root / "plan.json"
        save_setup_plan(build_setup_plan("recon"), self.plan)
        self.backup = self.root / "verified-backup"
        (self.backup / "disks").mkdir(parents=True)
        self.backed_disk = self.backup / "disks/disk-01.qcow2"
        self.backed_disk.write_bytes(b"synthetic-cold-archive-separate-file")
        self.backup_xml = self.backup / "domain.xml"
        self.backup_xml.write_text(domain(str(self.disk)), encoding="utf-8")
        self.hv = FakeHV(domain(str(self.disk)))
        self.runner = FakeRunner()
        self.registered = SimpleNamespace(
            inspect=lambda p, d: SimpleNamespace(ok=True, virtual_disk_gib=32.0)
        )
        self.write_manifest()

    def write_manifest(self):
        rows = []
        for kind, name, path, source in [
            ("disk", "disks/disk-01.qcow2", self.backed_disk, str(self.disk)),
            ("xml", "domain.xml", self.backup_xml, None),
        ]:
            data = path.read_bytes()
            item = {"kind": kind, "path": name, "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest()}
            if source is not None:
                item["source"] = source
            rows.append(item)
        nvram = self.backup / "firmware/nvram.bin"
        if nvram.exists():
            data = nvram.read_bytes()
            rows.append({"kind": "nvram", "path": "firmware/nvram.bin",
                         "source": self.nvram_source,
                         "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        (self.backup / "manifest.json").write_text(json.dumps({
            "format": "midnight-provisioner-cold-backup", "version": 1,
            "completed_at_utc": "2026-10-09T00:00:00+00:00",
            "domain": GUEST, "policy": "lab",
            "files": rows,
        }), encoding="utf-8")

    def inspect(self):
        return KaliColdBaselineInspector(
            hypervisor=self.hv, runner=self.runner,
            registered=self.registered,
        ).inspect(self.plan, self.disk, self.backup)

    def test_complete_cold_copy_is_only_hash_and_definition_consistent(self):
        result = self.inspect()
        self.assertTrue(result.ok, result.describe())
        self.assertEqual(result.checked_files, 2)
        self.assertEqual(result.backed_disk_gib, 32)
        self.assertIn("NOT RESTORE-PROVEN", result.describe())
        self.assertFalse(result.evidence()["backup_restoration_tested"])
        self.assertFalse(result.evidence()["signed_package_provenance_verified"])
        self.assertEqual(len(self.runner.calls), 1)
        self.assertEqual(self.runner.calls[0][-1], str(self.backed_disk))
        self.assertNotEqual(self.backed_disk.stat().st_ino, self.disk.stat().st_ino)
        self.assertEqual(self.disk.read_bytes(), self.original)
        self.assertTrue(all(action[0] in {"dumpxml", "state"} for action in self.hv.calls))
        self.assertIn("share a filesystem", result.describe())

    def test_corrupted_copy_fails_before_qemu_or_libvirt_metadata(self):
        self.backed_disk.write_bytes(b"modified-after-manifest")
        with self.assertRaisesRegex(ToolError, "integrity FAILURE"):
            self.inspect()
        self.assertEqual(self.hv.calls, [])
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.disk.read_bytes(), self.original)

    def test_unrelated_guest_or_wrong_policy_block(self):
        document = json.loads((self.backup / "manifest.json").read_text())
        document["domain"] = "unrelated-vm"
        (self.backup / "manifest.json").write_text(json.dumps(document))
        result = self.inspect()
        self.assertFalse(result.ok)
        self.assertIn("different registered Kali VM", result.describe())
        document["domain"] = GUEST
        document["policy"] = "isolated"
        (self.backup / "manifest.json").write_text(json.dumps(document))
        self.assertIn("restricted Kali lab policy", self.inspect().describe())

    def test_wrong_original_source_rejected_without_opening_external_disk(self):
        document = json.loads((self.backup / "manifest.json").read_text())
        document["files"][0]["source"] = "/tmp/unrelated-private-disk.qcow2"
        (self.backup / "manifest.json").write_text(json.dumps(document))
        result = self.inspect()
        self.assertFalse(result.ok)
        self.assertIn("source differs", result.describe())
        self.assertEqual(self.runner.calls, [])

    def test_archived_uuid_name_or_disk_config_drift_block(self):
        for replacement, message in [
            (domain(str(self.disk), uuid="other-uuid"), "UUID"),
            (domain(str(self.disk), name="other-vm"), "type/name"),
            (domain("/tmp/other-backup-source.qcow2"), "disk sources differ"),
        ]:
            with self.subTest(message=message):
                self.backup_xml.write_text(replacement)
                self.write_manifest()
                result = self.inspect()
                self.assertFalse(result.ok)
                self.assertIn(message, result.describe())
                self.assertEqual(self.runner.calls, [])
        self.backup_xml.write_text(domain(str(self.disk)))
        self.write_manifest()

    def test_network_adapter_or_installer_in_archive_blocks(self):
        for extra in (
            '<interface type="network"><source network="midnight-provisioner-lab"/></interface>',
            '<disk type="file" device="cdrom"><source file="/tmp/installer.iso"/></disk>',
        ):
            with self.subTest(extra=extra):
                self.backup_xml.write_text(domain(str(self.disk), extra=extra))
                self.write_manifest()
                result = self.inspect()
                self.assertFalse(result.ok)
                self.assertEqual(self.runner.calls, [])
        self.backup_xml.write_text(domain(str(self.disk)))
        self.write_manifest()

    def test_uefi_nvram_must_have_matching_verified_cold_copy(self):
        self.nvram_source = str(self.root / "per-guest-uefi-vars.fd")
        (self.backup / "firmware").mkdir()
        nvram = self.backup / "firmware/nvram.bin"
        nvram.write_bytes(b"offline-uefi-copy")
        nvram_xml = domain(str(self.disk), nvram=self.nvram_source)
        self.hv.current = self.hv.nextboot = nvram_xml
        self.backup_xml.write_text(nvram_xml)
        self.write_manifest()
        self.assertTrue(self.inspect().ok)
        nvram.unlink()
        self.write_manifest()
        self.assertIn("no matching verified cold copy", self.inspect().describe())
        nvram.write_bytes(b"offline-uefi-copy")
        self.write_manifest()
        self.hv.nextboot = domain(str(self.disk), nvram="/tmp/foreign-nvram")
        self.assertIn("NVRAM path differs", self.inspect().describe())

    def test_same_inode_backup_hardlink_is_not_an_independent_copy(self):
        self.backed_disk.unlink()
        self.backed_disk.hardlink_to(self.disk)
        self.write_manifest()
        # The earlier registration preflight refuses the selected live disk
        # once it has a second hardlink; it must fail before reading the backup.
        with self.assertRaisesRegex(ToolError, "multiple hardlinks"):
            self.inspect()
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.disk.read_bytes(), self.original)

    def test_qemu_metadata_layer_or_virtual_size_mismatch_fail(self):
        self.runner.metadata["backing-filename"] = "/tmp/external-layer.qcow2"
        report = self.inspect()
        self.assertFalse(report.ok)
        self.assertIn("native metadata failed", report.describe())
        self.runner.metadata.pop("backing-filename")
        self.runner.metadata["virtual-size"] = 31 * GIB
        report = self.inspect()
        self.assertFalse(report.ok)
        self.assertIn("virtual capacity differs", report.describe())

    def test_running_or_blocked_guest_cannot_get_backup_clearance(self):
        self.hv.state_value = "running"
        self.assertIn("changed state", self.inspect().describe())
        self.assertEqual(len(self.runner.calls), 1)
        self.registered = SimpleNamespace(inspect=lambda p, d: SimpleNamespace(ok=False))
        result = self.inspect()
        self.assertFalse(result.ok)
        self.assertIn("registration/disk audit is blocked", result.describe())
        self.assertEqual(result.checked_files, 0)

    def test_incomplete_or_symlinked_backup_never_passes(self):
        (self.backup / "INCOMPLETE").write_text("backup aborted")
        with self.assertRaisesRegex(ToolError, "INCOMPLETE"):
            self.inspect()
        (self.backup / "INCOMPLETE").unlink()
        alias = self.root / "alias-backup"
        try:
            alias.symlink_to(self.backup, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("OS denies creation of synthetic symlinks")
        with self.assertRaisesRegex(ToolError, "symlink"):
            KaliColdBaselineInspector(
                hypervisor=self.hv, runner=self.runner, registered=self.registered
            ).inspect(self.plan, self.disk, alias)

    def test_private_report_is_exclusive_without_host_storage_paths(self):
        result = self.inspect()
        output = self.root / "new-private-audit.json"
        self.assertEqual(save_cold_baseline_report(result, output), output)
        if os.name != "nt":
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        text = output.read_text()
        self.assertNotIn(str(self.disk), text)
        self.assertNotIn(str(self.backup), text)
        self.assertIn("backup_restoration_tested", text)
        before = output.read_bytes()
        with self.assertRaisesRegex(ToolError, "already exists"):
            save_cold_baseline_report(result, output)
        self.assertEqual(output.read_bytes(), before)

    def test_cli_reports_only_status_and_does_not_start_vms(self):
        arguments = [
            "templates", "baseline", str(self.plan), "--disk", str(self.disk),
            "--backup", str(self.backup),
        ]
        report = self.inspect()
        output = StringIO()
        with patch("midnight_provisioner.cli.KaliColdBaselineInspector") as checker, redirect_stdout(output):
            checker.return_value.inspect.return_value = report
            self.assertEqual(main(arguments), 0)
            checker.return_value.inspect.assert_called_once_with(
                self.plan, self.disk, self.backup
            )
            self.assertIn("NOT RESTORE-PROVEN", output.getvalue())
            checker.return_value.inspect.return_value = SimpleNamespace(
                ok=False, describe=lambda: "BLOCKED / UNVERIFIED"
            )
            self.assertEqual(main(arguments), 2)


if __name__ == "__main__":
    unittest.main()
