"""Synthetic Kali backup->stage->registered guest handoff security tests."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nightglass.cli import main
from nightglass.kali_recovery_registration import (
    KaliRecoveryRegistrationInspector, save_registered_recovery,
)
from nightglass.kali_setup import build_setup_plan, save_setup_plan
from nightglass.runner import ToolError

OLD = "nightglass-kali-recon"
RESTORED = "nightglass-kali-recon-restore-test"
OLD_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
NEW_UUID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"


def xml(name, disk, *, uuid=NEW_UUID, nic="", other_device=""):
    return (
        f'<domain type="kvm"><name>{name}</name><uuid>{uuid}</uuid>'
        '<memory unit="MiB">2048</memory><vcpu>1</vcpu>'
        '<devices><graphics type="vnc" listen="127.0.0.1"/>'
        f'<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>'
        f'<source file="{disk}"/></disk>{nic}{other_device}</devices></domain>'
    )


class FakeHV:
    def __init__(self, disk: Path):
        self.disk = disk
        self.current = xml(RESTORED, str(disk))
        self.inactive = self.current
        self.other_current = xml(OLD, "/unrelated/original-disk.qcow2", uuid=OLD_UUID)
        self.other_inactive = self.other_current
        self.other_saved = None
        self.names = [RESTORED, OLD]
        self.status = "shut off"
        self.auto = "disable"
        self.calls = []

    def _virsh(self, *parts):
        self.calls.append(parts)
        if parts == ("dominfo", RESTORED):
            return f"Id: -\nName: {RESTORED}\nAutostart: {self.auto}\n"
        if parts == ("dumpxml", RESTORED):
            return self.current
        if parts == ("dumpxml", "--inactive", RESTORED):
            return self.inactive
        if parts == ("dumpxml", OLD):
            return self.other_current
        if parts == ("dumpxml", "--inactive", OLD):
            return self.other_inactive
        raise AssertionError("Unexpected or mutating libvirt operation: " + repr(parts))

    def _managed_save_xml(self, domain):
        self.calls.append(("saved", domain))
        if domain == OLD:
            return self.other_saved
        return None

    def state(self, domain):
        self.calls.append(("state", domain))
        return self.status

    def list_domains(self):
        self.calls.append(("list",))
        return self.names


class Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.plan = self.root / "recon-plan.json"
        save_setup_plan(build_setup_plan("recon"), self.plan)
        self.backup = self.root / "cold-backup"
        self.stage = self.root / "recovery-stage"
        self.backup.mkdir()
        (self.stage / "disks").mkdir(parents=True)
        self.disk = self.stage / "disks/disk-01.qcow2"
        self.disk.write_bytes(b"synthetic-recovery-disk-never-touched")
        (self.backup / "domain.xml").write_text(
            xml(OLD, "/original/other-disk.qcow2", uuid=OLD_UUID),
            encoding="utf-8",
        )
        self.link = SimpleNamespace(
            ok=True, original_guest=OLD, recovered_guest=RESTORED,
            template_id="recon", matched_assets=1,
        )
        self.handoff_result = SimpleNamespace(
            ok=True, guest=RESTORED,
            definitions=("Current definition", "Inactive definition"),
        )
        self.hv = FakeHV(self.disk)
        self.linker = SimpleNamespace(inspect=lambda *args: self.link)
        self.handoff = SimpleNamespace(inspect=lambda *args: self.handoff_result)

    def audit(self):
        checker = KaliRecoveryRegistrationInspector(
            hypervisor=self.hv, linker=self.linker, handoff=self.handoff,
        )
        with patch("nightglass.kali_recovery_registration.verify_staging") as verify:
            report = checker.inspect(self.plan, self.backup, self.stage)
            if self.link.ok:
                verify.assert_called_once_with(self.stage)
            else:
                verify.assert_not_called()
        return report

    def test_valid_metadata_match_is_not_claimed_boot_or_restore(self):
        before = self.disk.read_bytes()
        result = self.audit()
        self.assertTrue(result.ok, result.describe())
        self.assertIn("NOT BOOT/RESTORE-PROVEN", result.describe())
        self.assertIn("autostart disabled", result.describe())
        self.assertFalse(result.evidence()["actual_guest_boot_verified"])
        self.assertFalse(result.evidence()["successful_restore_verified"])
        self.assertFalse(result.evidence()["packet_level_network_denial_verified"])
        self.assertEqual(before, self.disk.read_bytes())
        self.assertFalse(any("start" in action or "define" in action
                             for action in self.hv.calls))

    def test_backup_to_stage_failure_never_reads_registered_vm(self):
        self.link = SimpleNamespace(
            ok=False, original_guest=OLD, recovered_guest=RESTORED,
            template_id="recon", matched_assets=0,
        )
        result = self.audit()
        self.assertFalse(result.ok)
        self.assertIn("do not match", result.describe())
        self.assertEqual(self.hv.calls, [])

    def test_registered_handoff_failure_never_claims_recovery_safety(self):
        self.handoff_result = SimpleNamespace(
            ok=False, guest=RESTORED, definitions=("Current definition",),
        )
        r = self.audit()
        self.assertFalse(r.ok)
        self.assertIn("handoff audit", r.describe())

    def test_wrong_recovered_vm_or_original_link_identity_blocks(self):
        self.handoff_result = SimpleNamespace(
            ok=True, guest="someone-else",
            definitions=("Current definition", "Inactive definition"),
        )
        r = self.audit()
        self.assertFalse(r.ok)
        self.assertIn("differs from the verified staged recovery identity", r.describe())
        self.handoff_result.guest = RESTORED
        self.link.template_id = "exploit-lab"
        r = self.audit()
        self.assertFalse(r.ok)
        self.assertIn("differs from curated setup plan", r.describe())

    def test_original_vm_uuid_reuse_and_live_inactive_uuid_drift_block(self):
        self.hv.current = xml(RESTORED, str(self.disk), uuid=OLD_UUID)
        self.hv.inactive = self.hv.current
        r = self.audit()
        self.assertFalse(r.ok)
        self.assertIn("retained original Kali guest UUID", r.describe())
        self.hv.inactive = xml(RESTORED, str(self.disk), uuid=NEW_UUID)
        self.assertIn("UUIDs disagree", self.audit().describe())

    def test_missing_original_uuid_fails_closed(self):
        (self.backup / "domain.xml").write_text(
            '<domain type="kvm"><name>' + OLD + "</name></domain>",
            encoding="utf-8",
        )
        r = self.audit()
        self.assertFalse(r.ok)
        self.assertIn("Original Kali backup VM UUID is unverified", r.describe())

    def test_autostart_enabled_unknown_or_missing_metadata_block(self):
        for value in ("enable", "yes", "garbled"):
            with self.subTest(value=value):
                self.hv.auto = value
                result = self.audit()
                self.assertFalse(result.ok)
                self.assertIn("autostart is enabled", result.describe())
        self.hv.auto = "disable"
        self.assertTrue(self.audit().ok)

    def test_autostart_recheck_catches_mid_inspection_change(self):
        count = [0]
        original = self.hv._virsh
        def changed(*args):
            if args == ("dominfo", RESTORED):
                count[0] += 1
                if count[0] == 2:
                    self.hv.auto = "enable"
            return original(*args)
        self.hv._virsh = changed
        r = self.audit()
        self.assertFalse(r.ok)
        self.assertIn("autostart changed", r.describe())

    def test_running_after_handoff_is_blocked(self):
        self.hv.status = "running"
        self.assertIn("no longer shut off", self.audit().describe())

    def test_other_guest_reusing_recovery_disk_current_inactive_or_saved_blocks(self):
        for definition in ("other_current", "other_inactive", "other_saved"):
            with self.subTest(definition=definition):
                original = getattr(self.hv, definition)
                setattr(self.hv, definition, xml(OLD, str(self.disk), uuid=OLD_UUID))
                result = self.audit()
                self.assertFalse(result.ok)
                self.assertIn("disk collision", result.describe())
                setattr(self.hv, definition, original)

    def test_other_guest_lexical_alias_and_local_symlink_are_blocked(self):
        lexical = str(self.disk.parent / "unused" / ".." / self.disk.name)
        self.hv.other_inactive = xml(OLD, lexical, uuid=OLD_UUID)
        r = self.audit()
        self.assertFalse(r.ok)
        self.assertIn("lexical path alias", r.describe())
        symlink = self.disk.parent / "another-name.qcow2"
        symlink.symlink_to(self.disk)
        self.hv.other_inactive = xml(OLD, str(symlink), uuid=OLD_UUID)
        r = self.audit()
        self.assertFalse(r.ok)
        self.assertIn("symlinked disk path", r.describe())
        self.assertTrue(symlink.is_symlink())

    def test_other_guest_malformed_xml_or_inaccessible_inventory_blocks(self):
        self.hv.other_current = "<bad"
        self.assertIn("Cannot inspect other guest current", self.audit().describe())
        self.hv.other_current = xml(OLD, "/different/file.qcow2", uuid=OLD_UUID)
        self.hv.names = []
        r = self.audit()
        self.assertFalse(r.ok)
        self.assertIn("not registered", r.describe())

    def test_absent_other_guest_disk_not_opened_or_changed(self):
        other = self.root / "untouched-other-disk.qcow2"
        other.write_bytes(b"do-not-read-or-write")
        self.hv.other_current = xml(OLD, str(other), uuid=OLD_UUID)
        self.hv.other_inactive = self.hv.other_current
        self.assertTrue(self.audit().ok)
        self.assertEqual(other.read_bytes(), b"do-not-read-or-write")

    def test_private_report_exclusive_and_no_absolute_paths(self):
        result = self.audit()
        target = self.root / "new-registered-recovery-report.json"
        self.assertEqual(save_registered_recovery(result, target), target)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        data = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(data["recovered_guest"], RESTORED)
        self.assertFalse(data["actual_guest_boot_verified"])
        self.assertNotIn(str(self.root), target.read_text())
        before = target.read_bytes()
        with self.assertRaisesRegex(ToolError, "already exists"):
            save_registered_recovery(result, target)
        self.assertEqual(target.read_bytes(), before)

    def test_cli_registered_recovery_cannot_start_any_guest(self):
        args = [
            "templates", "recovery-registered", str(self.plan),
            "--backup", str(self.backup), "--staged", str(self.stage),
        ]
        result = self.audit()
        out = StringIO()
        with patch("nightglass.cli.KaliRecoveryRegistrationInspector") as inspect, redirect_stdout(out):
            inspect.return_value.inspect.return_value = result
            self.assertEqual(main(args), 0)
            inspect.return_value.inspect.assert_called_once_with(self.plan, self.backup, self.stage)
            self.assertIn("NOT BOOT/RESTORE-PROVEN", out.getvalue())
            inspect.return_value.inspect.return_value = SimpleNamespace(
                ok=False, describe=lambda: "BLOCKED / UNVERIFIED"
            )
            self.assertEqual(main(args), 2)


if __name__ == "__main__":
    unittest.main()
