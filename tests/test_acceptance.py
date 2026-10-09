"""Synthetic tests for read-only actual libvirt definition inspection."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nightglass.acceptance import RegisteredGuestAuditor, save_acceptance
from nightglass.portability import budget_for
from nightglass.runner import ToolError


# Windows lacks POSIX fchmod; mock only while running synthetic tests.
_fixture_mode_patch = None


def setUpModule():
    global _fixture_mode_patch
    if os.name == "nt":
        _fixture_mode_patch = patch("nightglass.acceptance.os.fchmod", create=True)
        _fixture_mode_patch.start()


def tearDownModule():
    global _fixture_mode_patch
    if _fixture_mode_patch is not None:
        _fixture_mode_patch.stop()
        _fixture_mode_patch = None


VNC = '<graphics type="vnc" listen="127.0.0.1"/>'
LAB_NIC = '<interface type="network"><source network="nightglass-lab"/></interface>'
OTHER_NIC = '<interface type="network"><source network="default"/></interface>'
LAB_NET = '<network><name>nightglass-lab</name><bridge name="virbr-nglab"/></network>'
FORWARD_NET = '<network><name>nightglass-lab</name><forward mode="nat"/><bridge name="virbr-nglab"/></network>'


def vm_xml(name="restored-safe", devices="", ram=2048):
    return (
        f'<domain type="kvm"><name>{name}</name>'
        f'<memory unit="MiB">{ram}</memory><devices>'
        f'{VNC}{devices}</devices></domain>'
    )


class FakeHypervisor:
    def __init__(self, *, current=None, inactive=None, saved=None, lab=None, state="shut off"):
        self.current = current or vm_xml()
        self.inactive = inactive or vm_xml()
        self.saved = saved
        self.lab = lab
        self.current_state = state
        self.calls = []

    def list_domains(self):
        self.calls.append(("list_domains",))
        return ["restored-safe"]

    def state(self, guest):
        self.calls.append(("state", guest))
        return self.current_state

    def _virsh(self, *args):
        self.calls.append(args)
        if args == ("dumpxml", "restored-safe"):
            return self.current
        if args == ("dumpxml", "--inactive", "restored-safe"):
            return self.inactive
        if args == ("net-dumpxml", "nightglass-lab"):
            if self.lab is None:
                raise ToolError("Network unavailable")
            return self.lab
        raise AssertionError(f"Unexpected command {args}")

    def _managed_save_xml(self, guest):
        self.calls.append(("managed-save", guest))
        return self.saved


class RegisteredAcceptanceTests(unittest.TestCase):
    def audited(self, hv, policy="isolated"):
        with patch("nightglass.acceptance.current_budget", return_value=budget_for(8.0, 6)):
            return RegisteredGuestAuditor(hv).inspect("restored-safe", policy)

    def test_safe_new_guest_checks_all_definitions_without_starting(self):
        hv = FakeHypervisor()
        report = self.audited(hv)
        self.assertTrue(report.ok)
        self.assertEqual(report.interfaces, 0)
        self.assertEqual(len(report.documents), 2)
        self.assertIn(("dumpxml", "--inactive", "restored-safe"), hv.calls)
        self.assertNotIn(("start", "restored-safe"), hv.calls)
        self.assertIn("NOT a packet-level", report.describe())

    def test_inactive_network_is_blocked(self):
        hv = FakeHypervisor(inactive=vm_xml(devices=OTHER_NIC))
        report = self.audited(hv)
        self.assertFalse(report.ok)
        self.assertIn("Inactive definition: Offline analysis VM has a network interface", report.errors)
        self.assertEqual(report.interfaces, 1)

    def test_current_network_is_blocked(self):
        hv = FakeHypervisor(current=vm_xml(devices=OTHER_NIC), state="running")
        report = self.audited(hv)
        self.assertFalse(report.ok)
        self.assertTrue(any("Current definition:" in x for x in report.errors))
        self.assertTrue(any("Guest is not powered off" in x for x in report.warnings))

    def test_saved_state_network_is_blocked(self):
        hv = FakeHypervisor(saved=vm_xml(devices=OTHER_NIC))
        report = self.audited(hv)
        self.assertFalse(report.ok)
        self.assertEqual(len(report.documents), 3)
        self.assertTrue(any("Managed-save definition:" in x for x in report.errors))

    def test_memory_pressure_guard_on_maximum_definition(self):
        hv = FakeHypervisor(inactive=vm_xml(ram=4096))
        report = self.audited(hv)
        self.assertFalse(report.ok)
        self.assertTrue(any("Guest RAM" in x for x in report.errors))

    def test_identity_mismatch_rejected(self):
        hv = FakeHypervisor(inactive=vm_xml(name="wrong-domain"))
        report = self.audited(hv)
        self.assertFalse(report.ok)
        self.assertTrue(any("VM name is different" in x for x in report.errors))

    def test_safe_lab_link_and_explicit_warning(self):
        hv = FakeHypervisor(current=vm_xml(devices=LAB_NIC),
                            inactive=vm_xml(devices=LAB_NIC), lab=LAB_NET)
        report = self.audited(hv, "lab")
        self.assertTrue(report.ok)
        self.assertEqual(report.interfaces, 1)
        self.assertTrue(any("host bridge" in x for x in report.warnings))
        self.assertIn(("net-dumpxml", "nightglass-lab"), hv.calls)

    def test_nat_lab_network_denied(self):
        hv = FakeHypervisor(current=vm_xml(devices=LAB_NIC),
                            inactive=vm_xml(devices=LAB_NIC), lab=FORWARD_NET)
        report = self.audited(hv, "lab")
        self.assertFalse(report.ok)
        self.assertTrue(any("forwards traffic" in x for x in report.errors))

    def test_missing_lab_net_fails_closed(self):
        hv = FakeHypervisor(inactive=vm_xml(devices=LAB_NIC))
        report = self.audited(hv, "lab")
        self.assertFalse(report.ok)
        self.assertTrue(any("Cannot inspect authorized" in x for x in report.errors))

    def test_malformed_xml_is_blocked(self):
        hv = FakeHypervisor(inactive="<bad")
        report = self.audited(hv)
        self.assertFalse(report.ok)
        self.assertTrue(any("could not be parsed" in x for x in report.errors))

    def test_nonexistent_domain_rejected(self):
        hv = FakeHypervisor()
        hv.list_domains = lambda: []
        with self.assertRaisesRegex(ToolError, "not registered"):
            self.audited(hv)

    def test_transitional_state_is_not_trusted(self):
        hv = FakeHypervisor(state="migrating")
        with self.assertRaisesRegex(ToolError, "transitional"):
            self.audited(hv)

    def test_no_accepted_trusted_policy(self):
        hv = FakeHypervisor()
        with self.assertRaisesRegex(ToolError, "isolated or lab"):
            self.audited(hv, "trusted")

    def test_local_report_is_private_explicit_and_no_overwrite(self):
        report = self.audited(FakeHypervisor())
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "acceptance.json"
            self.assertEqual(save_acceptance(report, destination), destination)
            if os.name != "nt":
                self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            obj = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(obj["guest"], "restored-safe")
            self.assertTrue(obj["xml_policy_passed"])
            self.assertIn("packet-level-network-denial", obj["observations_not_performed"])
            self.assertNotIn("disk_path", obj)
            with self.assertRaisesRegex(ToolError, "already exists"):
                save_acceptance(report, destination)
            self.assertEqual(json.loads(destination.read_text()), obj)

    def test_symlink_report_destination_refused(self):
        report = self.audited(FakeHypervisor())
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / "important"
            original.write_text("cannot overwrite")
            alias = Path(folder) / "acceptance.json"
            try:
                alias.symlink_to(original)
            except (OSError, NotImplementedError):
                self.skipTest("OS denies synthetic symlink creation")
            with self.assertRaisesRegex(ToolError, "already exists"):
                save_acceptance(report, alias)
            self.assertEqual(original.read_text(), "cannot overwrite")


if __name__ == "__main__":
    unittest.main()
