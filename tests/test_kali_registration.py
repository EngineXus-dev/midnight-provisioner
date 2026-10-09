"""Synthetic registered Kali template VM audits: no actual guests or disk writes."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nightglass.kali_registration import (
    KaliRegistrationInspector, save_registration_report,
)
from nightglass.kali_setup import build_setup_plan, save_setup_plan
from nightglass.portability import budget_for
from nightglass.runner import Output, ToolError

GIB = 1024 ** 3
GUEST = "nightglass-kali-recon"
UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def domain(name, disk, *, identity=UUID, memory=2048, cpus=1,
           extra="", fmt="qcow2"):
    return (
        f'<domain type="kvm"><name>{name}</name><uuid>{identity}</uuid>'
        f'<memory unit="MiB">{memory}</memory><vcpu>{cpus}</vcpu>'
        '<devices><graphics type="vnc" listen="127.0.0.1"/>'
        f'<disk type="file" device="disk"><driver name="qemu" type="{fmt}"/>'
        f'<source file="{disk}"/><target dev="vda" bus="virtio"/></disk>'
        f'{extra}</devices></domain>'
    )


class FakeHV:
    def __init__(self, target, disk):
        self.docs = {
            target: {
                "current": domain(target, disk),
                "inactive": domain(target, disk),
                "saved": None,
            },
        }
        self.state_value = "shut off"
        self.calls = []
        self.target = target

    def list_domains(self):
        self.calls.append(("list",))
        return sorted(self.docs)

    def state(self, guest):
        self.calls.append(("state", guest))
        return self.state_value

    def _managed_save_xml(self, guest):
        self.calls.append(("saved", guest))
        return self.docs[guest]["saved"]

    def _virsh(self, *argv):
        self.calls.append(argv)
        if argv[0] == "dumpxml":
            if len(argv) == 3 and argv[1] == "--inactive":
                return self.docs[argv[2]]["inactive"]
            if len(argv) == 2:
                return self.docs[argv[1]]["current"]
        if argv[:2] == ("net-dumpxml", "nightglass-lab"):
            return '<network><name>nightglass-lab</name><bridge name="virbr-nglab"/></network>'
        raise AssertionError(f"Unexpected libvirt action: {argv}")


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.metadata = {
            "format": "qcow2", "virtual-size": 32 * GIB,
        }

    def run(self, argv, timeout=12):
        self.calls.append(tuple(argv))
        if argv[:3] == ["qemu-img", "info", "--output=json"]:
            return Output(json.dumps(self.metadata))
        raise AssertionError(f"Unapproved native operation: {argv}")


class RegisteredKaliTemplateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.disk = self.root / "independent-recon.qcow2"
        self.disk.write_bytes(b"synthetic-qcow2-header-read-is-mocked")
        self.other_disk = self.root / "separate-other-disk.qcow2"
        self.other_disk.write_bytes(b"not-shared")
        self.plan_path = self.root / "recon-plan.json"
        save_setup_plan(build_setup_plan("recon"), self.plan_path)
        self.hv = FakeHV(GUEST, str(self.disk))
        self.runner = FakeRunner()
        self.budget = budget_for(8.0, 6)

    def check(self, disk=None):
        with patch("nightglass.acceptance.current_budget", return_value=self.budget):
            return KaliRegistrationInspector(
                self.hv, self.runner, self.budget
            ).inspect(self.plan_path, disk or self.disk)

    def test_valid_registered_offline_guest_is_metadata_only(self):
        result = self.check()
        self.assertTrue(result.ok, result.describe())
        self.assertEqual(result.virtual_disk_gib, 32)
        self.assertEqual(result.inspected_definitions, ("Current definition", "Inactive definition"))
        self.assertIn("PASS (CONFIGURATION ONLY)", result.describe())
        self.assertIn("remain UNVERIFIED", result.describe())
        self.assertEqual(len(self.runner.calls), 1)
        self.assertEqual(self.runner.calls[0][:3], ("qemu-img", "info", "--output=json"))
        self.assertEqual(self.runner.calls[0][-1], str(self.disk))
        self.assertFalse(any(
            part in {"start", "define", "shutdown", "destroy", "create"}
            for action in self.hv.calls for part in action
        ))

    def test_registered_vm_identity_disagreement_blocks_before_disk_reads(self):
        self.hv.docs[GUEST]["inactive"] = domain(GUEST, str(self.disk), identity="different-uuid")
        r = self.check()
        self.assertFalse(r.ok)
        self.assertIn("UUIDs disagree", r.describe())
        self.assertEqual(self.runner.calls, [])

    def test_other_disk_source_and_second_registered_disk_are_blocked(self):
        self.hv.docs[GUEST]["inactive"] = domain(GUEST, str(self.other_disk))
        r = self.check()
        self.assertFalse(r.ok)
        self.assertIn("selected independent disk path", r.describe())
        self.assertEqual(self.runner.calls, [])
        extra = (
            '<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>'
            '<source file="/tmp/unrelated-other-disk.qcow2"/></disk>'
        )
        self.hv.docs[GUEST]["inactive"] = domain(GUEST, str(self.disk), extra=extra)
        self.assertFalse(self.check().ok)

    def test_shared_disk_path_in_other_current_or_inactive_definition_blocks(self):
        for key in ("current", "inactive", "saved"):
            with self.subTest(definition=key):
                self.hv.docs["someone-else"] = {
                    "current": domain("someone-else", str(self.other_disk)),
                    "inactive": domain("someone-else", str(self.other_disk)),
                    "saved": None,
                }
                self.hv.docs["someone-else"][key] = domain(
                    "someone-else", str(self.disk),
                )
                result = self.check()
                self.assertFalse(result.ok)
                self.assertIn("same disk image", result.describe())
                self.assertEqual(self.runner.calls, [])
                del self.hv.docs["someone-else"]

    def test_link_count_blocks_any_second_hardlink_even_outside_storage_folder(self):
        other_folder = self.root / "separate-existing-vm-folder"
        other_folder.mkdir()
        hardlink = other_folder / "alias.qcow2"
        hardlink.hardlink_to(self.disk)
        with self.assertRaisesRegex(ToolError, "multiple hardlinks"):
            self.check()
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.hv.calls, [])
        self.assertEqual(hardlink.read_bytes(), self.disk.read_bytes())

    def test_lexically_equivalent_xml_source_is_detected_without_opening_other_disk(self):
        # XML references can differ textually while resolving to the same path.
        # The intermediate folder doesn't even have to exist for normpath to
        # expose a lexical alias; no other disk is opened.
        alias = str(self.disk.parent / "unused" / ".." / self.disk.name)
        self.hv.docs["someone-else"] = {
            "current": domain("someone-else", alias),
            "inactive": domain("someone-else", str(self.other_disk)),
            "saved": None,
        }
        result = self.check()
        self.assertFalse(result.ok)
        self.assertIn("lexical path alias", result.describe())
        self.assertEqual(self.runner.calls, [])

    def test_same_folder_other_guest_symlink_is_blocked_without_following_it(self):
        link = self.root / "different-registered-guest.qcow2"
        link.symlink_to(self.disk)
        self.hv.docs["someone-else"] = {
            "current": domain("someone-else", str(link)),
            "inactive": domain("someone-else", str(self.other_disk)),
            "saved": None,
        }
        result = self.check()
        self.assertFalse(result.ok)
        self.assertIn("symlinked disk path", result.describe())
        self.assertEqual(self.runner.calls, [])
        self.assertTrue(link.is_symlink())

    def test_saved_state_path_alias_is_also_blocked(self):
        alias = str(self.disk.parent / "." / self.disk.name)
        # pathlib normalizes the path; explicitly inject lexical .. spelling.
        alias = str(self.disk.parent / "unused" / ".." / self.disk.name)
        self.hv.docs["someone-else"] = {
            "current": domain("someone-else", str(self.other_disk)),
            "inactive": domain("someone-else", str(self.other_disk)),
            "saved": domain("someone-else", alias),
        }
        result = self.check()
        self.assertFalse(result.ok)
        self.assertIn("Managed-save disk collision", result.describe())
        self.assertEqual(self.runner.calls, [])

    def test_missing_local_other_guest_disk_does_not_open_or_fail_alias_review(self):
        absent = self.root / "missing-other-vm.qcow2"
        self.hv.docs["someone-else"] = {
            "current": domain("someone-else", str(absent)),
            "inactive": domain("someone-else", str(absent)),
            "saved": None,
        }
        result = self.check()
        self.assertTrue(result.ok, result.describe())
        self.assertEqual(len(self.runner.calls), 1)
        self.assertFalse(absent.exists())

    def test_hardlink_added_during_qemu_inspection_rejects_stale_clearance(self):
        link = self.root / "created-later.qcow2"
        from nightglass import kali_registration
        original_inspect = kali_registration.inspect_image_metadata
        def add_link_on_metadata(runner, path, expected_format):
            data = original_inspect(runner, path, expected_format)
            link.hardlink_to(self.disk)
            return data
        with patch.object(kali_registration, "inspect_image_metadata", side_effect=add_link_on_metadata):
            result = self.check()
        self.assertFalse(result.ok)
        self.assertIn("became unavailable or hardlinked", result.describe())
        self.assertTrue(link.exists())
        self.assertEqual(len(self.runner.calls), 1)

    def test_independent_other_guest_disks_are_not_opened(self):
        self.hv.docs["someone-else"] = {
            "current": domain("someone-else", str(self.other_disk)),
            "inactive": domain("someone-else", str(self.other_disk)),
            "saved": None,
        }
        result = self.check()
        self.assertTrue(result.ok, result.describe())
        self.assertEqual([x[-1] for x in self.runner.calls], [str(self.disk)])

    def test_unreadable_other_vm_blocks_independence_claim(self):
        self.hv.docs["someone-else"] = {
            "current": "<bad", "inactive": "<bad", "saved": None,
        }
        result = self.check()
        self.assertFalse(result.ok)
        self.assertIn("cannot verify registered XML", result.describe())
        self.assertEqual(self.runner.calls, [])

    def test_running_vm_or_managed_save_state_block_offline_audit(self):
        self.hv.state_value = "running"
        self.assertIn("must be shut off", self.check().describe())
        self.hv.state_value = "shut off"
        self.hv.docs[GUEST]["saved"] = domain(GUEST, str(self.disk))
        self.assertIn("managed-save state", self.check().describe())
        self.assertEqual(self.runner.calls, [])

    def test_network_and_mounted_installer_are_disallowed(self):
        for xml_extra in (
            '<interface type="network"><source network="nightglass-lab"/></interface>',
            '<disk type="file" device="cdrom"><source file="/tmp/installer.iso"/></disk>',
        ):
            with self.subTest(extra=xml_extra):
                self.hv.docs[GUEST]["inactive"] = domain(GUEST, str(self.disk), extra=xml_extra)
                result = self.check()
                self.assertFalse(result.ok)
                self.assertEqual(self.runner.calls, [])
                self.hv.docs[GUEST]["inactive"] = domain(GUEST, str(self.disk))

    def test_qemu_driver_mismatch_or_backing_metadata_blocks(self):
        self.hv.docs[GUEST]["inactive"] = domain(GUEST, str(self.disk), fmt="raw")
        self.assertIn("qcow2", self.check().describe())
        self.hv.docs[GUEST]["inactive"] = domain(GUEST, str(self.disk))
        self.runner.metadata["backing-filename"] = "/tmp/base.qcow2"
        self.assertIn("metadata could not be verified", self.check().describe())

    def test_missing_or_symlinked_disk_is_never_passed_to_qemu_img(self):
        link = self.root / "link.qcow2"
        link.symlink_to(self.disk)
        with self.assertRaisesRegex(ToolError, "symlink"):
            self.check(link)
        with self.assertRaises(ToolError):
            self.check(self.root / "missing.qcow2")
        self.assertEqual(self.runner.calls, [])

    def test_virtual_capacity_and_resource_limit_rejections(self):
        self.runner.metadata["virtual-size"] = 15 * GIB
        result = self.check()
        self.assertFalse(result.ok)
        self.assertIn("unexpectedly small", result.describe())
        self.runner.metadata["virtual-size"] = 257 * GIB
        self.assertIn("256 GiB limit", self.check().describe())
        self.runner.metadata["virtual-size"] = 32 * GIB
        self.hv.docs[GUEST]["inactive"] = domain(GUEST, str(self.disk), cpus=99)
        self.assertIn("vCPU", self.check().describe())
        self.hv.docs[GUEST]["inactive"] = domain(GUEST, str(self.disk), memory=8096)
        self.assertIn("RAM exceeds", self.check().describe())

    def test_private_evidence_no_disk_path_and_no_overwrite(self):
        report = self.check()
        destination = self.root / "new-audit.json"
        self.assertEqual(save_registration_report(report, destination), destination)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        obj = json.loads(destination.read_text())
        self.assertEqual(obj["template_id"], "recon")
        self.assertIn("outside-folder-symlink-and-other-hypervisor-alias-check", obj["observations_not_performed"])
        self.assertNotIn(str(self.disk), destination.read_text())
        with self.assertRaisesRegex(ToolError, "already exists"):
            save_registration_report(report, destination)

    def test_cli_registered_action_returns_failure_for_blocked_report(self):
        from nightglass.cli import main
        argv = ["templates", "registered", str(self.plan_path), "--disk", str(self.disk)]
        for flag in (True, False):
            with self.subTest(ok=flag), patch(
                "nightglass.cli.KaliRegistrationInspector"
            ) as inspector, redirect_stdout(StringIO()) as out:
                result = type("Result", (), {
                    "ok": flag,
                    "describe": lambda self: "CONFIGURATION ONLY" if flag else "BLOCKED",
                })()
                inspector.return_value.inspect.return_value = result
                self.assertEqual(main(argv), 0 if flag else 2)
                inspector.return_value.inspect.assert_called_once_with(
                    self.plan_path, self.disk
                )
                self.assertIn("CONFIGURATION ONLY" if flag else "BLOCKED", out.getvalue())


if __name__ == "__main__":
    unittest.main()
