"""Kali runtime observation: synthetic libvirt/sVirt only; no guest execution."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nightglass.cli import main
from nightglass.kali_running import KaliRunningInspector, save_kali_running_observation
from nightglass.kali_setup import build_setup_plan, save_setup_plan
from nightglass.runner import ToolError

OLD = "nightglass-kali-recon"
GUEST = "nightglass-kali-recon-rehearsal"
UUID_OLD = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
UUID_NEW = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"


def xml(name, disk, uuid=UUID_NEW, extra=""):
    return (
        f'<domain type="kvm"><name>{name}</name><uuid>{uuid}</uuid>'
        '<memory unit="MiB">2048</memory><vcpu>1</vcpu>'
        '<devices><graphics type="vnc" listen="127.0.0.1"/>'
        f'<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>'
        f'<source file="{disk}"/></disk>{extra}</devices></domain>'
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


class FakeHV:
    def __init__(self, guest, disk):
        self.guest = guest
        self.disk = disk
        self.current = xml(guest, str(disk))
        self.inactive = self.current
        self.other_current = xml(OLD, "/independent/source.qcow2", uuid=UUID_OLD)
        self.other_inactive = self.other_current
        self.other_saved = None
        self.saved = None
        self.names = [guest, OLD]
        self.autostart = "disable"
        self.live_state = "running"
        self.calls = []

    def _virsh(self, *args):
        self.calls.append(args)
        if args == ("dumpxml", self.guest):
            return self.current
        if args == ("dumpxml", "--inactive", self.guest):
            return self.inactive
        if args == ("dumpxml", OLD):
            return self.other_current
        if args == ("dumpxml", "--inactive", OLD):
            return self.other_inactive
        if args == ("dominfo", self.guest):
            return f"Name: {self.guest}\nAutostart: {self.autostart}\n"
        raise AssertionError("Unexpected potentially mutating libvirt command: " + repr(args))

    def _managed_save_xml(self, guest):
        self.calls.append(("saved", guest))
        return self.saved if guest == self.guest else self.other_saved

    def list_domains(self):
        self.calls.append(("list",))
        return self.names

    def state(self, guest):
        self.calls.append(("state", guest))
        return self.live_state


class Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.plan = self.root / "original-recon-plan.json"
        save_setup_plan(build_setup_plan("recon"), self.plan)
        self.backup = self.root / "existing-cold-backup"
        self.backup.mkdir()
        (self.backup / "domain.xml").write_text(
            xml(OLD, "/original-disk.qcow2", uuid=UUID_OLD)
        )
        (self.backup / "manifest.json").write_text(json.dumps({
            "format": "nightglass-cold-backup", "domain": OLD, "policy": "lab",
            "files": [],
        }))
        self.disk = self.root / "selected-live-recovery.qcow2"
        self.disk.write_bytes(b"live-guest-qcow2-not-to-be-hashed-or-modified")
        self.hv = FakeHV(GUEST, self.disk)
        self.runtime = SimpleNamespace(inspect=lambda name, policy:
                                       SimpleNamespace(state="running", errors=()))
        self.verification_calls = []

    def check(self, *, guest=GUEST, disk=None):
        inspector = KaliRunningInspector(
            hypervisor=self.hv, runtime=self.runtime,
        )
        with patch("nightglass.kali_running.verify_backup",
                   side_effect=lambda folder: self.verification_calls.append(folder)):
            return inspector.inspect(self.plan, self.backup, guest, disk or self.disk)

    def test_valid_manual_runtime_is_metadata_only_not_boot_or_restore(self):
        before = self.disk.read_bytes()
        result = self.check()
        self.assertTrue(result.ok, result.describe())
        self.assertEqual(result.state, "running")
        self.assertIn("PASS (LIBVIRT/SELINUX METADATA ONLY)", result.describe())
        self.assertEqual(self.verification_calls, [self.backup, self.backup])
        self.assertEqual(before, self.disk.read_bytes())
        record = result.evidence()
        for key in ("guest_operating_system_boot_verified",
                    "successful_recovery_verified",
                    "actual_qemu_process_selinux_verified",
                    "packet_level_network_isolation_verified",
                    "live_disk_hash_verified"):
            self.assertIs(record[key], False)
        self.assertFalse(any(any(part in {"start", "define", "destroy", "shutdown", "qemu-img"}
                                 for part in args) for args in self.hv.calls))

    def test_original_kali_guest_cannot_be_used_as_recovered_guest(self):
        with self.assertRaisesRegex(ToolError, "own NEW name"):
            self.check(guest=OLD)
        self.assertEqual(self.verification_calls, [])
        self.assertEqual(self.hv.calls, [])

    def test_only_already_running_guest_is_allowed(self):
        self.runtime.inspect = lambda *args: SimpleNamespace(
            state="shut off", errors=("Guest is not running",)
        )
        report = self.check()
        self.assertFalse(report.ok)
        self.assertIn("must already be running", report.describe())

    def test_svirt_enforcement_failure_blocks_even_if_xml_is_safe(self):
        self.runtime.inspect = lambda *args: SimpleNamespace(
            state="running", errors=("Host SELinux enforcing state was not positively verified",)
        )
        report = self.check()
        self.assertFalse(report.ok)
        self.assertIn("SELinux enforcing", report.describe())

    def test_network_interface_in_current_or_nextboot_xml_blocks(self):
        nic = '<interface type="network"><source network="default"/></interface>'
        for field in ("current", "inactive"):
            with self.subTest(field=field):
                self.verification_calls.clear()
                original = getattr(self.hv, field)
                setattr(self.hv, field, xml(GUEST, str(self.disk), extra=nic))
                report = self.check()
                self.assertFalse(report.ok)
                self.assertIn("network adapter", report.describe())
                setattr(self.hv, field, original)

    def test_original_guest_uuid_reuse_and_live_inactive_uuid_drift(self):
        self.hv.current = xml(GUEST, str(self.disk), uuid=UUID_OLD)
        self.hv.inactive = self.hv.current
        self.assertIn("retained original", self.check().describe())
        self.hv.inactive = xml(GUEST, str(self.disk), uuid=UUID_NEW)
        self.assertIn("UUIDs disagree", self.check().describe())

    def test_different_disk_or_extra_disk_and_mounted_cdrom_block(self):
        self.hv.current = xml(GUEST, "/another/unsafe.qcow2")
        self.assertIn("selected recovery qcow2", self.check().describe())
        for device in (
            '<disk type="file" device="disk"><driver name="qemu" type="qcow2"/><source file="/other.qcow2"/></disk>',
            '<disk type="file" device="cdrom"><source file="/installer.iso"/></disk>',
            '<hostdev mode="subsystem" type="usb"/>',
        ):
            with self.subTest(device=device):
                self.hv.current = xml(GUEST, str(self.disk), extra=device)
                self.assertFalse(self.check().ok)

    def test_autostart_enabled_unknown_or_managed_save_block(self):
        for state in ("enable", "unexpected", ""):
            with self.subTest(autostart=state):
                self.hv.autostart = state
                self.assertFalse(self.check().ok)
        self.hv.autostart = "disable"
        self.hv.saved = xml(GUEST, str(self.disk))
        self.assertIn("managed-save", self.check().describe())

    def test_cross_guest_current_inactive_and_saved_disk_aliases_block(self):
        for field in ("other_current", "other_inactive", "other_saved"):
            with self.subTest(field=field):
                original = getattr(self.hv, field)
                alias = str(self.disk.parent / "unused" / ".." / self.disk.name)
                setattr(self.hv, field, xml(OLD, alias, uuid=UUID_OLD))
                report = self.check()
                self.assertFalse(report.ok)
                self.assertIn("disk collision", report.describe())
                setattr(self.hv, field, original)

    def test_foreign_guest_unparseable_xml_and_changed_state_fail_closed(self):
        self.hv.other_current = "<bad"
        self.assertIn("Cannot inspect another registered", self.check().describe())
        self.hv.other_current = xml(OLD, "/independent/source.qcow2", uuid=UUID_OLD)
        self.hv.live_state = "shut off"
        self.assertIn("stopped or changed state", self.check().describe())

    def test_running_disk_is_not_hashed_or_native_probed(self):
        before = self.disk.read_bytes()
        with patch("nightglass.kali_running._safe_disk", wraps=__import__(
            "nightglass.kali_registration", fromlist=["_safe_disk"]
        )._safe_disk) as safe, patch(
            "nightglass.kali_running.RuntimeLabelInspector"
        ) as label_class:
            report = self.check()
            self.assertTrue(report.ok)
            self.assertEqual(safe.call_count, 2)
            label_class.assert_not_called()
        self.assertEqual(before, self.disk.read_bytes())

    def test_archive_identity_or_network_policy_conflict_is_blocked(self):
        doc = json.loads((self.backup / "manifest.json").read_text())
        doc["domain"] = "some-other-guest"
        (self.backup / "manifest.json").write_text(json.dumps(doc))
        self.assertIn("does not match", self.check().describe())

    def test_selected_image_hardlink_and_symlink_refused_before_libvirt(self):
        hardlink = self.root / "another-hardlink.qcow2"
        hardlink.hardlink_to(self.disk)
        with self.assertRaisesRegex(ToolError, "multiple hardlinks"):
            self.check()
        hardlink.unlink()
        link = self.root / "disk-symlink.qcow2"
        try:
            link.symlink_to(self.disk)
        except (OSError, NotImplementedError):
            self.skipTest("OS denies creation of synthetic symlinks")
        with self.assertRaisesRegex(ToolError, "symlink"):
            self.check(disk=link)
        self.assertEqual(self.hv.calls, [])

    def test_optional_private_metadata_only_report_no_overwrite(self):
        report = self.check()
        dest = self.root / "new-kali-runtime-report.json"
        self.assertEqual(save_kali_running_observation(report, dest), dest)
        if os.name != "nt":
            self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
        contents = dest.read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), contents)
        self.assertNotIn(str(self.disk), contents)
        self.assertIn('"guest_operating_system_boot_verified": false', contents)
        with self.assertRaisesRegex(ToolError, "already exists"):
            save_kali_running_observation(report, dest)

    def test_cli_status_tracks_observation_without_automatically_starting_guest(self):
        args = [
            "templates", "observe-running", str(self.plan),
            "--backup", str(self.backup), "--guest", GUEST,
            "--disk", str(self.disk),
        ]
        output = StringIO()
        report = self.check()
        with patch("nightglass.cli.KaliRunningInspector") as checker, redirect_stdout(output):
            checker.return_value.inspect.return_value = report
            self.assertEqual(main(args), 0)
            checker.return_value.inspect.assert_called_once_with(
                self.plan, self.backup, GUEST, self.disk
            )
            checker.return_value.inspect.return_value = SimpleNamespace(
                ok=False, describe=lambda: "BLOCKED / UNVERIFIED"
            )
            self.assertEqual(main(args), 2)
        self.assertIn("LIBVIRT/SELINUX METADATA ONLY", output.getvalue())


if __name__ == "__main__":
    unittest.main()
