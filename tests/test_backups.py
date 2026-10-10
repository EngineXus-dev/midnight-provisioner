"""Cold backup tests use tiny local fixtures; never contact real libvirt or disks."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nightglass.backups import ColdBackup, verify_backup
from nightglass.hypervisor import Audit, assess_domain
from nightglass.runner import Output, ToolError


def domain_xml(path, extra="", nvram=None):
    firmware = f"<os><nvram>{nvram}</nvram></os>" if nvram else ""
    return (
        '<domain type="kvm"><name>demo-vm</name><memory unit="MiB">2048</memory>'
        + firmware
        + '<devices><graphics type="vnc" listen="127.0.0.1"/>'
        + f'<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>'
        + f'<source file="{path}"/></disk>'
        + extra
        + '</devices></domain>'
    )


class Guest:
    def __init__(self, xml, state="shut off", saved=False):
        self.xml = xml
        self.current_state = state
        self.saved = saved
        self.calls = []

    def list_domains(self):
        return ["demo-vm"]

    def state(self, name):
        self.calls.append(("state", name))
        return self.current_state

    def _managed_save_xml(self, name):
        self.calls.append(("save", name))
        return "<domain/>" if self.saved else None

    def audit(self, name, policy):
        return assess_domain(self.xml, policy)

    def _virsh(self, *args):
        self.calls.append(args)
        if args == ("dumpxml", "--inactive", "demo-vm"):
            return self.xml
        raise AssertionError(f"Unexpected virsh: {args}")


class ImageInspector:
    def __init__(self, backing=False, format_name="qcow2"):
        self.backing = backing
        self.format_name = format_name
        self.calls = []

    def run(self, argv, timeout=12):
        self.calls.append(tuple(argv))
        assert argv[:3] == ["qemu-img", "info", "--output=json"]
        document = {"format": self.format_name}
        if self.backing:
            document["backing-filename"] = "/different-disk.qcow2"
        return Output(json.dumps(document))


class ColdBackupTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.disk = self.root / "vm source.qcow2"
        self.disk.write_bytes(b"qcow2-fixture" * 200)
        self.xml = domain_xml(self.disk)
        self.vm = Guest(self.xml)
        self.img = ImageInspector()
        self.service = ColdBackup(self.vm, self.img)

    def test_plan_is_read_only_and_requires_shutoff(self):
        plan = self.service.plan("demo-vm", "isolated")
        self.assertIn("NOT a checkpoint", plan.describe())
        self.assertEqual(plan.estimated_bytes, self.disk.stat().st_size)
        self.assertEqual(self.img.calls[0][0], "qemu-img")
        self.assertEqual(list(self.root.glob("backup*")), [])
        self.vm.current_state = "running"
        with self.assertRaisesRegex(ToolError, "fully shut-off"):
            self.service.plan("demo-vm", "isolated")

    def test_completed_backup_has_consistent_checksums(self):
        dest = self.root / "backup-A"
        with self.assertRaisesRegex(ToolError, "confirmation"):
            self.service.create("demo-vm", "isolated", dest)
        result = self.service.create("demo-vm", "isolated", dest, confirmed=True)
        self.assertEqual(result, dest)
        self.assertTrue((dest / "domain.xml").is_file())
        self.assertTrue((dest / "disks" / "disk-01.qcow2").is_file())
        self.assertFalse((dest / "INCOMPLETE").exists())
        lines = verify_backup(dest)
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(item.startswith("PASS") for item in lines))
        manifest = json.loads((dest / "manifest.json").read_text())
        self.assertEqual(manifest["domain"], "demo-vm")
        self.assertEqual(manifest["policy"], "isolated")

    def test_existing_destination_will_not_be_overwritten(self):
        dest = self.root / "backup-A"
        dest.mkdir()
        keep = dest / "important"
        keep.write_text("retain this")
        with self.assertRaisesRegex(ToolError, "nonexistent"):
            self.service.create("demo-vm", "isolated", dest, confirmed=True)
        self.assertEqual(keep.read_text(), "retain this")

    def test_hash_corruption_detected(self):
        dest = self.service.create("demo-vm", "isolated", self.root / "backup-B", confirmed=True)
        (dest / "disks" / "disk-01.qcow2").write_bytes(b"tampered")
        with self.assertRaisesRegex(ToolError, "integrity FAILURE"):
            verify_backup(dest)

    def test_incomplete_folder_rejected(self):
        dest = self.service.create("demo-vm", "isolated", self.root / "backup-C", confirmed=True)
        (dest / "INCOMPLETE").write_text("interrupted")
        with self.assertRaisesRegex(ToolError, "INCOMPLETE"):
            verify_backup(dest)

    def test_symlink_source_and_symlinked_backup_rejected(self):
        link = self.root / "link.qcow2"
        try:
            link.symlink_to(self.disk)
        except (OSError, NotImplementedError):
            self.skipTest("OS denies symlink creation in synthetic fixture")
        self.vm.xml = domain_xml(link)
        with self.assertRaisesRegex(ToolError, "non-symlinked"):
            self.service.plan("demo-vm", "isolated")
        self.vm.xml = self.xml
        dest = self.service.create("demo-vm", "isolated", self.root / "backup-D", confirmed=True)
        (dest / "disks" / "disk-01.qcow2").unlink()
        (dest / "disks" / "disk-01.qcow2").symlink_to(self.disk)
        with self.assertRaisesRegex(ToolError, "symlinked"):
            verify_backup(dest)

    def test_managed_save_is_not_a_cold_backup(self):
        self.vm.saved = True
        with self.assertRaisesRegex(ToolError, "managed-save"):
            self.service.plan("demo-vm", "isolated")

    def test_backing_chains_forbidden(self):
        self.img.backing = True
        with self.assertRaisesRegex(ToolError, "Layered images"):
            self.service.plan("demo-vm", "isolated")

    def test_detach_installer_media(self):
        extra = '<disk type="file" device="cdrom"><source file="/home/user/installer.iso"/></disk>'
        self.vm.xml = domain_xml(self.disk, extra=extra)
        with self.assertRaisesRegex(ToolError, "Detach"):
            self.service.plan("demo-vm", "isolated")

    def test_non_file_storage_and_extra_host_channels_blocked(self):
        self.vm.xml = domain_xml(self.disk, extra='<channel type="unix"/>')
        with self.assertRaisesRegex(ToolError, "policy"):
            self.service.plan("demo-vm", "isolated")

    def test_nvram_is_included_and_verified(self):
        nvram = self.root / "guest.nvram"
        nvram.write_bytes(b"nvram fixture")
        self.vm.xml = domain_xml(self.disk, nvram=str(nvram))
        dest = self.service.create("demo-vm", "isolated", self.root / "backup-E", confirmed=True)
        self.assertEqual((dest / "firmware" / "nvram.bin").read_bytes(), nvram.read_bytes())
        self.assertEqual(len(verify_backup(dest)), 3)

    def test_verifier_rejects_unsafe_manifest_paths(self):
        dest = self.service.create("demo-vm", "isolated", self.root / "backup-F", confirmed=True)
        file = dest / "manifest.json"
        document = json.loads(file.read_text())
        document["files"][0]["path"] = "../private.txt"
        file.write_text(json.dumps(document))
        with self.assertRaisesRegex(ToolError, "Unsafe"):
            verify_backup(dest)

    def test_runtime_restart_aborts_with_incomplete_marker(self):
        original_state = self.vm.state
        calls = [0]
        def state(*args):
            calls[0] += 1
            if calls[0] >= 6:
                return "running"
            return original_state(*args)
        with patch.object(self.vm, "state", side_effect=state):
            with self.assertRaisesRegex(ToolError, "INCOMPLETE"):
                self.service.create("demo-vm", "isolated", self.root / "backup-G", confirmed=True)
        self.assertTrue((self.root / "backup-G" / "INCOMPLETE").exists())

    def test_verifier_enforces_xml_and_disk_inventory(self):
        dest = self.service.create("demo-vm", "isolated", self.root / "backup-H", confirmed=True)
        document = json.loads((dest / "manifest.json").read_text())
        document["files"] = document["files"][:-1]
        (dest / "manifest.json").write_text(json.dumps(document))
        with self.assertRaisesRegex(ToolError, "unexpected file inventory|at least one disk and one XML"):
            verify_backup(dest)


if __name__ == "__main__":
    unittest.main()
