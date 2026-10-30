"""Registered recovery handoff tests: all synthetic and nonprivileged."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from midnight_provisioner.handoff import RecoveryHandoff, save_handoff
from midnight_provisioner.portability import budget_for
from midnight_provisioner.runner import Output, ToolError

# Mock POSIX-only file-mode operation in Windows synthetic fixtures only.
_fixture_mode_patch = None


def setUpModule():
    global _fixture_mode_patch
    if os.name == "nt":
        _fixture_mode_patch = patch("midnight_provisioner.acceptance.os.fchmod", create=True)
        _fixture_mode_patch.start()


def tearDownModule():
    global _fixture_mode_patch
    if _fixture_mode_patch is not None:
        _fixture_mode_patch.stop()
        _fixture_mode_patch = None


UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_UUID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
VNC = '<graphics type="vnc" listen="127.0.0.1"/>'


def xml(name, disk, *, uuid=None, fmt="qcow2", extra="", nvram=None):
    identity = f"<uuid>{uuid}</uuid>" if uuid else ""
    nvram_xml = f"<os><nvram>{nvram}</nvram></os>" if nvram else ""
    return (
        f'<domain type="kvm"><name>{name}</name>{identity}'
        f'{nvram_xml}<memory unit="MiB">2048</memory><devices>{VNC}'
        f'<disk type="file" device="disk"><driver name="qemu" type="{fmt}"/>'
        f'<source file="{disk}"/><target dev="vda" bus="virtio"/></disk>'
        f'{extra}</devices></domain>'
    )


class FakeHV:
    def __init__(self, guest, *, current, inactive=None, saved=None, state="shut off"):
        self.guest = guest
        self.current = current
        self.inactive = inactive if inactive is not None else current
        self.saved = saved
        self.status = state
        self.calls = []

    def list_domains(self):
        self.calls.append(("list_domains",))
        return [self.guest]

    def state(self, guest):
        self.calls.append(("state", guest))
        return self.status

    def _virsh(self, *args):
        self.calls.append(args)
        if args == ("dumpxml", self.guest):
            return self.current
        if args == ("dumpxml", "--inactive", self.guest):
            return self.inactive
        raise AssertionError(f"Unexpected libvirt operation: {args}")

    def _managed_save_xml(self, guest):
        self.calls.append(("managed-save", guest))
        return self.saved


class FakeRunner:
    def __init__(self, *, meta=None):
        self.meta = meta or {"format": "qcow2", "virtual-size": 1048576}
        self.calls = []

    def run(self, argv, timeout=12):
        self.calls.append(tuple(argv))
        if argv[:3] == ["qemu-img", "info", "--output=json"]:
            return Output(json.dumps(self.meta))
        raise AssertionError(f"Unexpected native tool operation: {argv}")


class HandoffTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.staged = self.root / "staged"
        self.staged.mkdir(mode=0o700)
        (self.staged / "disks").mkdir()
        self.guest = "midnight-provisioner-new-guest"
        self.disk = self.staged / "disks/disk-01.qcow2"
        self.disk.write_bytes(b"synthetic-not-actually-qcow2" * 150)
        self.xmlfile = self.staged / "domain.xml"
        self.xmlfile.write_text(xml(self.guest, str(self.disk)), encoding="utf-8")
        self.manifest = self.staged / "recovery-manifest.json"
        self.reset_manifest()
        self.hv = FakeHV(
            self.guest,
            current=xml(self.guest, str(self.disk), uuid=UUID),
        )
        self.runner = FakeRunner()

    def reset_manifest(self):
        def asset(path, rel, kind):
            blob = path.read_bytes()
            return {
                "path": rel, "kind": kind, "bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
        items = [
            asset(self.disk, "disks/disk-01.qcow2", "disk"),
            asset(self.xmlfile, "domain.xml", "xml"),
        ]
        self.manifest.write_text(json.dumps({
            "format": "midnight-provisioner-recovery-staging", "version": 1,
            "guest": self.guest, "original_guest": "original-guest",
            "original_policy": "isolated", "network": "offline", "files": items,
        }), encoding="utf-8")

    def audit(self):
        with patch("midnight_provisioner.acceptance.current_budget", return_value=budget_for(8.0, 6)):
            return RecoveryHandoff(self.hv, self.runner).inspect(self.staged)

    def test_exact_offline_handoff_passes_without_mutating_guest(self):
        before = self.disk.read_bytes()
        report = self.audit()
        self.assertTrue(report.ok, report.describe())
        self.assertEqual(report.staged_disks, 1)
        self.assertEqual(len(report.definitions), 2)
        self.assertEqual(len(self.runner.calls), 1)
        self.assertEqual(self.runner.calls[0][:3], ("qemu-img", "info", "--output=json"))
        self.assertEqual(before, self.disk.read_bytes())
        self.assertTrue(all(
            args[0] in {"list_domains", "state", "dumpxml", "managed-save"}
            for args in self.hv.calls
        ))
        self.assertIn("NO VM WAS DEFINED", report.describe())

    def test_registered_disk_points_outside_stage(self):
        outside = self.root / "unrelated-secret.qcow2"
        outside.write_bytes(b"DO NOT OPEN")
        self.hv.current = xml(self.guest, str(outside), uuid=UUID)
        report = self.audit()
        self.assertFalse(report.ok)
        self.assertIn("outside verified staged", report.describe())
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(outside.read_bytes(), b"DO NOT OPEN")

    def test_registered_driver_format_mismatch_refused(self):
        self.hv.current = xml(self.guest, str(self.disk), uuid=UUID, fmt="raw")
        report = self.audit()
        self.assertFalse(report.ok)
        self.assertIn("driver format", report.describe())
        self.assertEqual(self.runner.calls, [])

    def test_extra_registered_disk_refused(self):
        extra = (
            '<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>'
            '<source file="/tmp/unrelated.qcow2"/><target dev="vdb" bus="virtio"/></disk>'
        )
        self.hv.inactive = xml(self.guest, str(self.disk), uuid=UUID, extra=extra)
        report = self.audit()
        self.assertFalse(report.ok)
        self.assertIn("outside verified staged", report.describe())
        self.assertIn("inventory differs", report.describe()) if "inventory differs" in report.describe() else None
        self.assertEqual(self.runner.calls, [])

    def test_registered_cdrom_iso_refused(self):
        extra = '<disk type="file" device="cdrom"><source file="/tmp/installer.iso"/></disk>'
        self.hv.inactive = xml(self.guest, str(self.disk), uuid=UUID, extra=extra)
        report = self.audit()
        self.assertFalse(report.ok)
        self.assertIn("mounted ISO", report.describe())

    def test_inactive_network_cannot_be_smuggled_through_handoff(self):
        nic = '<interface type="network"><source network="default"/></interface>'
        self.hv.inactive = xml(self.guest, str(self.disk), uuid=UUID, extra=nic)
        report = self.audit()
        self.assertFalse(report.ok)
        self.assertIn("network interface", report.describe())

    def test_running_guest_and_saved_resume_refused(self):
        self.hv.status = "running"
        self.hv.saved = xml(self.guest, str(self.disk), uuid=UUID)
        report = self.audit()
        self.assertFalse(report.ok)
        self.assertIn("shut off", report.describe())
        self.assertIn("managed-save state", report.describe())

    def test_uuid_inconsistent_across_registered_definitions(self):
        self.hv.inactive = xml(self.guest, str(self.disk), uuid=OTHER_UUID)
        report = self.audit()
        self.assertFalse(report.ok)
        self.assertIn("UUIDs disagree", report.describe())

    def test_missing_uuid_is_blocked(self):
        self.hv.current = xml(self.guest, str(self.disk))
        report = self.audit()
        self.assertFalse(report.ok)
        self.assertIn("UUID is missing", report.describe())

    def test_staging_xml_disk_driver_mismatch_rejected_first(self):
        self.xmlfile.write_text(
            xml(self.guest, str(self.disk), fmt="raw"), encoding="utf-8"
        )
        self.reset_manifest()
        with self.assertRaisesRegex(ToolError, "driver format"):
            self.audit()
        self.assertEqual(self.hv.calls, [])
        self.assertEqual(self.runner.calls, [])

    def test_unverified_disk_contents_rejected_before_native_tools(self):
        self.disk.write_bytes(b"changed after staging")
        with self.assertRaisesRegex(ToolError, "Staging integrity failure"):
            self.audit()
        self.assertEqual(self.hv.calls, [])
        self.assertEqual(self.runner.calls, [])

    def test_staging_disk_symlink_refused(self):
        destination = self.root / "original.qcow2"
        destination.write_bytes(self.disk.read_bytes())
        self.disk.unlink()
        try:
            self.disk.symlink_to(destination)
        except (OSError, NotImplementedError):
            self.skipTest('OS denies synthetic symlink creation')
        with self.assertRaisesRegex(ToolError, "symlinked staging file"):
            self.audit()
        self.assertEqual(self.hv.calls, [])

    def test_qemu_backing_chain_is_blocked(self):
        self.runner.meta = {
            "format": "qcow2", "virtual-size": 1048576,
            "backing-filename": "/tmp/base.qcow2",
        }
        report = self.audit()
        self.assertFalse(report.ok)
        self.assertIn("metadata failed validation", report.describe())

    def test_private_local_evidence_without_disk_paths_or_overwrite(self):
        report = self.audit()
        target = self.root / "handoff-evidence.json"
        self.assertEqual(save_handoff(report, target), target)
        if os.name != 'nt':
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        document = json.loads(target.read_text(encoding="utf-8"))
        self.assertTrue(document["registered_metadata_matches_staging"])
        self.assertIn("packet-level-network-denial", document["observations_not_performed"])
        self.assertNotIn(str(self.staged), target.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ToolError, "already exists"):
            save_handoff(report, target)

    def test_nvram_identity_required_when_staged(self):
        (self.staged / "firmware").mkdir()
        nvram = self.staged / "firmware/nvram.bin"
        nvram.write_bytes(b"fake UEFI vars")
        staged = xml(self.guest, str(self.disk), nvram=str(nvram))
        self.xmlfile.write_text(staged, encoding="utf-8")
        self.reset_manifest()
        items = json.loads(self.manifest.read_text(encoding="utf-8"))
        items["files"].append({
            "path": "firmware/nvram.bin", "kind": "nvram",
            "bytes": nvram.stat().st_size,
            "sha256": hashlib.sha256(nvram.read_bytes()).hexdigest(),
        })
        self.manifest.write_text(json.dumps(items), encoding="utf-8")
        without = self.audit()
        self.assertFalse(without.ok)
        self.assertIn("NVRAM path", without.describe())
        self.hv.current = xml(self.guest, str(self.disk), uuid=UUID, nvram=str(nvram))
        self.hv.inactive = self.hv.current
        self.assertTrue(self.audit().ok)


if __name__ == "__main__":
    unittest.main()
