"""Offline recovery staging uses synthetic, signed-by-no-one backup fixtures.

No root, libvirt service, ISO, network connection or real guest is required.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from nightglass.recovery import RecoveryStager, verify_staging
from nightglass.runner import ToolError


class FakeHV:
    def __init__(self, names=()):
        self.names = names

    def list_domains(self):
        return list(self.names)


class RestoreTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.source = self.root / "backup"
        self.source.mkdir()
        (self.source / "disks").mkdir()
        self.original_disk_path = "/var/lib/libvirt/images/danger.qcow2"
        self.disk_bytes = b"synthetic, not a real guest disk" * 1024
        self.xml = self._xml()
        self._backup()
        self.service = RecoveryStager(FakeHV())

    def _xml(self, extra="", policy="isolated"):
        link = (
            '<interface type="network"><source network="nightglass-lab"/></interface>'
            if policy == "lab" else ""
        )
        return (
            '<domain type="kvm"><name>original-guest</name>'
            '<uuid>11111111-1111-1111-1111-111111111111</uuid>'
            '<genid>22222222-2222-2222-2222-222222222222</genid>'
            '<memory unit="MiB">2048</memory><devices>'
            '<graphics type="vnc" listen="127.0.0.1"/>'
            '<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>'
            f'<source file="{self.original_disk_path}"/></disk>'
            + link + extra + '</devices></domain>'
        )

    def _backup(self, policy="isolated", nvram=False):
        disk = self.source / "disks" / "disk-01.qcow2"
        disk.write_bytes(self.disk_bytes)
        rows = [
            self._row(disk, "disks/disk-01.qcow2", "disk", self.original_disk_path),
        ]
        if nvram:
            (self.source / "firmware").mkdir(exist_ok=True)
            nvram_file = self.source / "firmware" / "nvram.bin"
            nvram_file.write_bytes(b"synthetic firmware")
            self.xml = self.xml.replace(
                '<memory unit="MiB">2048</memory>',
                '<os><nvram>/var/lib/libvirt/qemu/nvram/original_VARS.fd</nvram></os>'
                '<memory unit="MiB">2048</memory>'
            )
            rows.append(self._row(
                nvram_file, "firmware/nvram.bin", "nvram",
                "/var/lib/libvirt/qemu/nvram/original_VARS.fd",
            ))
        (self.source / "domain.xml").write_text(self.xml, encoding="utf-8")
        rows.append(self._row(self.source / "domain.xml", "domain.xml", "xml"))
        (self.source / "manifest.json").write_text(json.dumps({
            "format": "nightglass-cold-backup",
            "version": 1,
            "domain": "original-guest",
            "policy": policy,
            "files": rows,
        }), encoding="utf-8")

    @staticmethod
    def _row(path, rel, kind, source=None):
        row = {
            "path": rel, "kind": kind,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        if source is not None:
            row["source"] = source
        return row

    def _stage(self, filename="new-guest", kind="analysis"):
        return self.service.stage(
            self.source, self.root / filename, f"nightglass-{kind}-restored",
            confirmed=True,
        )

    def test_plan_does_not_mutate_vm_or_create_files(self):
        plan = self.service.plan(self.source, self.root / "fresh", "recovered-guest")
        self.assertIn("OFFLINE", plan.describe())
        self.assertFalse((self.root / "fresh").exists())
        xml = ET.fromstring(plan.xml)
        self.assertEqual(xml.findtext("name"), "recovered-guest")
        self.assertIsNone(xml.find("uuid"))
        self.assertIsNone(xml.find("genid"))
        self.assertEqual(
            xml.find("./devices/disk/source").get("file"),
            str(self.root / "fresh" / "disks" / "disk-01.qcow2")
        )

    def test_stage_new_identity_and_verify_no_source_modification(self):
        old_data = (self.source / "domain.xml").read_bytes()
        new_dir = self._stage()
        self.assertFalse((new_dir / "INCOMPLETE").exists())
        self.assertEqual((new_dir / "disks/disk-01.qcow2").read_bytes(), self.disk_bytes)
        self.assertEqual((self.source / "domain.xml").read_bytes(), old_data)
        report = verify_staging(new_dir)
        self.assertEqual(len(report), 2)
        xml = ET.fromstring((new_dir / "domain.xml").read_text())
        self.assertEqual(xml.findtext("name"), "nightglass-analysis-restored")
        self.assertIsNone(xml.find("./devices/interface"))
        self.assertIsNone(xml.find("uuid"))
        self.assertEqual(
            xml.find("./devices/disk/source").get("file"),
            str(new_dir / "disks/disk-01.qcow2")
        )
        self.assertFalse((new_dir / "defined-in-libvirt").exists())

    def test_lab_backup_recovered_with_no_network(self):
        self.xml = self._xml(policy="lab")
        self._backup(policy="lab")
        recovered = self._stage(kind="pentest")
        root = ET.fromstring((recovered / "domain.xml").read_text())
        self.assertIsNone(root.find("./devices/interface"))
        self.assertEqual(len(verify_staging(recovered)), 2)

    def test_unknown_original_network_is_blocked(self):
        self.xml = self._xml(extra='<interface type="bridge"><source bridge="br0"/></interface>', policy="lab")
        self._backup(policy="lab")
        with self.assertRaisesRegex(ToolError, "unapproved network"):
            self.service.plan(self.source, self.root / "x", "restored")

    def test_inherited_host_channels_are_blocked(self):
        self.xml = self._xml(extra='<channel type="unix"/>')
        self._backup()
        with self.assertRaisesRegex(ToolError, "fails Nightglass policy"):
            self.service.plan(self.source, self.root / "x", "restored")

    def test_manifest_and_domain_disk_source_must_match(self):
        self.xml = self._xml().replace(self.original_disk_path, "/tmp/outside.qcow2")
        self._backup()
        with self.assertRaisesRegex(ToolError, "disk sources do not match"):
            self.service.plan(self.source, self.root / "x", "restored")

    def test_original_name_and_existing_vm_cannot_be_overwritten(self):
        with self.assertRaisesRegex(ToolError, "NEW guest name"):
            self.service.plan(self.source, self.root / "x", "original-guest")
        service = RecoveryStager(FakeHV(["restored"]))
        with self.assertRaisesRegex(ToolError, "already exists"):
            service.plan(self.source, self.root / "x", "restored")

    def test_existing_target_cannot_be_overwritten(self):
        target = self.root / "existing"
        target.mkdir()
        secret = target / "unique-project-data"
        secret.write_text("retain")
        with self.assertRaisesRegex(ToolError, "NEW and nonexistent"):
            self.service.stage(self.source, target, "restored", confirmed=True)
        self.assertEqual(secret.read_text(), "retain")

    def test_staging_into_backup_source_is_rejected(self):
        with self.assertRaisesRegex(ToolError, "cannot write inside"):
            self.service.plan(self.source, self.source / "recovered", "restored")

    def test_staging_confirmation_required(self):
        with self.assertRaisesRegex(ToolError, "explicit confirmation"):
            self.service.stage(self.source, self.root / "fresh", "restored")
        self.assertFalse((self.root / "fresh").exists())

    def test_corrupt_backup_fails_before_writing(self):
        (self.source / "disks/disk-01.qcow2").write_bytes(b"modified after manifest")
        with self.assertRaisesRegex(ToolError, "integrity FAILURE"):
            self.service.stage(self.source, self.root / "fresh", "restored", confirmed=True)
        self.assertFalse((self.root / "fresh").exists())

    def test_corrupt_staging_detected(self):
        folder = self._stage()
        (folder / "disks/disk-01.qcow2").write_bytes(b"malicious change")
        with self.assertRaisesRegex(ToolError, "Staging integrity failure"):
            verify_staging(folder)

    def test_staging_symlink_asset_rejected(self):
        folder = self._stage()
        asset = folder / "disks/disk-01.qcow2"
        asset.unlink()
        asset.symlink_to(self.source / "disks/disk-01.qcow2")
        with self.assertRaisesRegex(ToolError, "symlinked staging file"):
            verify_staging(folder)

    def test_incomplete_marker_rejected(self):
        folder = self._stage()
        (folder / "INCOMPLETE").write_text("interrupted")
        with self.assertRaisesRegex(ToolError, "INCOMPLETE"):
            verify_staging(folder)

    def test_tampered_xml_network_with_updated_manifest_still_rejected(self):
        folder = self._stage()
        xml_path = folder / "domain.xml"
        xml_path.write_text(
            xml_path.read_text().replace("</devices>",
                '<interface type="network"><source network="default"/></interface></devices>')
        )
        manifest = json.loads((folder / "recovery-manifest.json").read_text())
        xml_row = next(row for row in manifest["files"] if row["kind"] == "xml")
        xml_row.update(bytes=xml_path.stat().st_size,
                       sha256=hashlib.sha256(xml_path.read_bytes()).hexdigest())
        (folder / "recovery-manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ToolError, "offline policy"):
            verify_staging(folder)

    def test_nvram_is_copied_and_rewritten(self):
        self._backup(nvram=True)
        new_dir = self._stage()
        root = ET.fromstring((new_dir / "domain.xml").read_text())
        self.assertEqual(root.findtext("./os/nvram"),
                         str(new_dir / "firmware/nvram.bin"))
        self.assertEqual(len(verify_staging(new_dir)), 3)

    def test_manifest_traversal_never_read(self):
        file = self.source / "manifest.json"
        document = json.loads(file.read_text())
        document["files"][0]["path"] = "../sensitive"
        file.write_text(json.dumps(document))
        with self.assertRaisesRegex(ToolError, "Unsafe"):
            self.service.plan(self.source, self.root / "x", "restored")

    def test_incomplete_on_copied_file_corruption(self):
        with patch("nightglass.recovery.CHUNK_BYTES", 20):
            with patch("nightglass.recovery.hashlib.sha256") as mock_digest:
                # Avoid falsifying *preflight* hash verification; test a
                # real staged failure by rejecting the staged XML instead.
                pass
        # Source XML and source manifest are valid when staging starts, but
        # a competing edit can invalidate final validation.
        with patch("nightglass.recovery.verify_staging", side_effect=ToolError("post-copy audit failed")):
            with self.assertRaisesRegex(ToolError, "INCOMPLETE"):
                self.service.stage(self.source, self.root / "incomplete", "restored", confirmed=True)
        self.assertTrue((self.root / "incomplete/INCOMPLETE").exists())


if __name__ == "__main__":
    unittest.main()
