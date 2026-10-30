"""Regression tests for pre-launch live/inactive/managed-save audit parity.

Fake libvirt never changes VM state except when an explicit start call is
returned by the in-memory runner. Tests do not require Fedora, KVM or root.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from midnight_provisioner.hypervisor import Hypervisor
from midnight_provisioner.runner import Output, ToolError


def virsh(*parts):
    return ("virsh", "--connect", "qemu:///system", *parts)


def xml(*, name="safevm", devices="", ram=2048, uuid=None, maxram=None):
    ident = f"<uuid>{uuid}</uuid>" if uuid else ""
    memory_max = f'<maxMemory unit="MiB">{maxram}</maxMemory>' if maxram else ""
    return (
        f'<domain type="kvm"><name>{name}</name>{ident}'
        f'<memory unit="MiB">{ram}</memory>{memory_max}'
        '<devices><graphics type="vnc" listen="127.0.0.1"/>'
        f'{devices}</devices></domain>'
    )


NIC = '<interface type="network"><source network="default"/></interface>'
LAB_NIC = '<interface type="network"><source network="midnight-provisioner-lab"/></interface>'
LAB_NET = '<network><name>midnight-provisioner-lab</name><bridge name="virbr-nglab"/><dns enable="no"/></network>'


class FakeRunner:
    def __init__(self, *, current=None, inactive=None, saved=None, lab=None):
        self.calls = []
        self.mapping = {
            virsh("list", "--all", "--name"): "safevm\n",
            virsh("dumpxml", "safevm"): xml() if current is None else current,
            virsh("dumpxml", "--inactive", "safevm"): xml() if inactive is None else inactive,
            virsh("dominfo", "safevm"): "Managed save: no\n" if saved is None else "Managed save: yes\n",
            virsh("start", "safevm"): "Domain safevm started\n",
        }
        if saved is not None:
            self.mapping[virsh("managedsave-dumpxml", "safevm")] = saved
        if lab is not None:
            self.mapping[virsh("net-dumpxml", "midnight-provisioner-lab")] = lab

    def run(self, argv, timeout=12):
        key = tuple(argv)
        self.calls.append(key)
        value = self.mapping.get(key)
        if isinstance(value, ToolError):
            raise value
        if value is None:
            raise AssertionError(f"Unexpected VM operation: {argv}")
        return Output(value)


class LaunchParityTests(unittest.TestCase):
    def launch(self, runner, policy="isolated"):
        with patch("midnight_provisioner.hypervisor.total_ram_gib", return_value=8.0):
            return Hypervisor(runner).start("safevm", policy)

    @staticmethod
    def assert_no_start(runner):
        assert virsh("start", "safevm") not in runner.calls

    def test_safe_current_and_next_boot_pass_before_start(self):
        runner = FakeRunner()
        result = self.launch(runner)
        self.assertIn("started", result)
        self.assertIn(virsh("dumpxml", "--inactive", "safevm"), runner.calls)
        self.assertGreater(
            runner.calls.index(virsh("start", "safevm")),
            runner.calls.index(virsh("dumpxml", "--inactive", "safevm")),
        )
        self.assertFalse(any("define" in part or "destroy" in part for call in runner.calls for part in call))

    def test_unsafe_persistent_nic_blocks_even_if_live_is_disconnected(self):
        runner = FakeRunner(inactive=xml(devices=NIC))
        with self.assertRaisesRegex(ToolError, "Inactive definition: Offline analysis VM"):
            self.launch(runner)
        self.assert_no_start(runner)

    def test_unsafe_live_nic_blocks_even_if_persistent_is_disconnected(self):
        runner = FakeRunner(current=xml(devices=NIC))
        with self.assertRaisesRegex(ToolError, "Current definition: Offline analysis VM"):
            self.launch(runner)
        self.assert_no_start(runner)

    def test_saved_nic_cannot_bypass_secure_persistent_xml(self):
        runner = FakeRunner(saved=xml(devices=NIC))
        with self.assertRaisesRegex(ToolError, "Saved session: Offline analysis VM"):
            self.launch(runner)
        self.assert_no_start(runner)

    def test_missing_persistent_xml_is_fail_closed(self):
        runner = FakeRunner()
        runner.mapping[virsh("dumpxml", "--inactive", "safevm")] = ToolError("no persistent XML")
        with self.assertRaisesRegex(ToolError, "no persistent XML"):
            self.launch(runner)
        self.assert_no_start(runner)

    def test_inactive_memory_hotplug_cannot_bypass_ram_cap(self):
        runner = FakeRunner(inactive=xml(maxram=8192))
        with self.assertRaisesRegex(ToolError, "Low-memory guard: VM declares up to"):
            self.launch(runner)
        self.assert_no_start(runner)

    def test_name_drift_between_live_and_persistent_definition_denied(self):
        runner = FakeRunner(inactive=xml(name="wrong-name"))
        report = Hypervisor(runner).audit("safevm", "isolated")
        self.assertFalse(report.ok)
        self.assertIn("identity name", " ".join(report.warnings))
        self.assert_no_start(runner)

    def test_uuid_drift_denied_even_when_names_match(self):
        runner = FakeRunner(current=xml(uuid="aaaa"), inactive=xml(uuid="bbbb"))
        report = Hypervisor(runner).audit("safevm", "isolated")
        self.assertFalse(report.ok)
        self.assertIn("different uuid", " ".join(report.warnings))
        self.assert_no_start(runner)

    def test_managed_save_uuid_drift_is_denied(self):
        runner = FakeRunner(current=xml(uuid="aaaa"), inactive=xml(uuid="aaaa"),
                            saved=xml(uuid="bbbb"))
        report = Hypervisor(runner).audit("safevm", "isolated")
        self.assertFalse(report.ok)
        self.assertIn("different uuid", " ".join(report.warnings))

    def test_lab_inactive_nic_uses_read_only_network_definition(self):
        runner = FakeRunner(current=xml(), inactive=xml(devices=LAB_NIC), lab=LAB_NET)
        report = Hypervisor(runner).audit("safevm", "lab")
        self.assertTrue(report.ok)
        self.assertIn(virsh("net-dumpxml", "midnight-provisioner-lab"), runner.calls)
        self.assert_no_start(runner)

    def test_persistent_label_opt_out_denied_before_start(self):
        runner = FakeRunner(inactive=xml().replace(
            "<devices>", '<seclabel type="none"/><devices>'
        ))
        with self.assertRaisesRegex(ToolError, "security labeling"):
            self.launch(runner)
        self.assert_no_start(runner)


if __name__ == "__main__":
    unittest.main()
