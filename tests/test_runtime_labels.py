"""Synthetic sVirt runtime metadata checks: zero guest interaction or root."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nightglass.host_posture import HostPosture, PostureCheck
from nightglass.portability import budget_for
from nightglass.runtime_labels import RuntimeLabelInspector, save_runtime_observation
from nightglass.runner import ToolError

# Windows synthetic runtime-evidence tests do not provide POSIX fchmod.
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


UUID = "01234567-89ab-cdef-0123-456789abcdef"
MCS = "c101,c209"
VNC = '<graphics type="vnc" listen="127.0.0.1"/>'
LAB_NIC = '<interface type="network"><source network="nightglass-lab"/></interface>'
LAB_NET = '<network><name>nightglass-lab</name><bridge name="virbr-nglab"/><dns enable="no"/></network>'

LABEL = (
    '<seclabel type="dynamic" model="selinux" relabel="yes">'
    f'<label>system_u:system_r:svirt_t:s0:{MCS}</label>'
    f'<imagelabel>system_u:object_r:svirt_image_t:s0:{MCS}</imagelabel>'
    '</seclabel>'
)
CAP = (
    "<capabilities><host><secmodel><model>selinux</model>"
    "<doi>0</doi></secmodel></host></capabilities>"
)


def xml(*, security=LABEL, nic="", name="safevm", uuid=UUID):
    return (
        f'<domain type="kvm"><name>{name}</name><uuid>{uuid}</uuid>'
        f'{security}<memory unit="MiB">2048</memory>'
        f'<devices>{VNC}{nic}</devices></domain>'
    )


class FakeHV:
    def __init__(self):
        self.current = xml()
        self.inactive = xml()
        self.saved = None
        self.running_state = "running"
        self.capabilities = CAP
        self.lab = LAB_NET
        self.calls = []
        self.end_state = None

    def list_domains(self):
        self.calls.append("list_domains")
        return ["safevm"]

    def state(self, guest):
        self.calls.append("state")
        # Acceptance samples state, then RuntimeLabelInspector samples again.
        if self.end_state is not None and self.calls.count("state") > 1:
            return self.end_state
        return self.running_state

    def _managed_save_xml(self, guest):
        self.calls.append("managed-save")
        return self.saved

    def _virsh(self, *args):
        self.calls.append(args)
        if args == ("dumpxml", "safevm"):
            return self.current
        if args == ("dumpxml", "--inactive", "safevm"):
            return self.inactive
        if args == ("capabilities",):
            return self.capabilities
        if args == ("net-dumpxml", "nightglass-lab"):
            return self.lab
        raise AssertionError(f"Unexpected libvirt call: {args}")


class FakeRunner:
    def run(self, argv, timeout=12):
        raise AssertionError(f"No guest command should run: {argv}")


def host_enforcing(**kwargs):
    return HostPosture((
        PostureCheck(
            "SELinux", "OK",
            "Kernel enforcement is enabled (guest sVirt labels not proven)",
        ),
    ))


def host_permissive(**kwargs):
    return HostPosture((PostureCheck("SELinux", "WARN", "Permissive"),))


class RuntimeLabelTests(unittest.TestCase):
    def setUp(self):
        self.hv = FakeHV()
        self.probe = host_enforcing
        self.runner = FakeRunner()

    def inspect(self, policy="isolated"):
        with patch("nightglass.acceptance.current_budget", return_value=budget_for(8.0, 6)):
            return RuntimeLabelInspector(
                self.hv, self.runner, self.probe
            ).inspect("safevm", policy)

    def test_valid_running_is_metadata_only_not_security_certification(self):
        report = self.inspect()
        self.assertTrue(report.ok, report.describe())
        self.assertEqual(report.state, "running")
        self.assertIn("METADATA ONLY", report.describe())
        self.assertIn("effective-qemu-process-selinux-context", report.evidence()["observations_not_performed"])
        self.assertEqual(self.hv.calls.count("state"), 2)
        self.assertIn(("capabilities",), self.hv.calls)
        self.assertTrue(all(
            operation in {"list_domains", "state", "managed-save"} or
            (isinstance(operation, tuple) and operation[0] in {"dumpxml", "capabilities"})
            for operation in self.hv.calls
        ))

    def test_shut_off_and_saved_state_never_pass_as_runtime_proof(self):
        self.hv.running_state = "shut off"
        result = self.inspect()
        self.assertFalse(result.ok)
        self.assertIn("not running", result.describe())

    def test_host_permissive_or_missing_selinux_never_passes(self):
        self.probe = host_permissive
        self.assertFalse(self.inspect().ok)
        self.assertIn("not positively verified", self.inspect().describe())

    def test_host_enforcing_status_must_be_explicit(self):
        self.probe = lambda **kwargs: HostPosture((PostureCheck("SELinux", "INFO", "Possibly enforcing"),))
        self.assertFalse(self.inspect().ok)

    def test_missing_host_selinux_reading_is_blocked(self):
        self.probe = lambda **kwargs: HostPosture(tuple())
        self.assertFalse(self.inspect().ok)

    def test_no_libvirt_secmodel_is_blocked(self):
        self.hv.capabilities = "<capabilities><host></host></capabilities>"
        self.assertIn("does not report", self.inspect().describe())

    def test_invalid_libvirt_capabilities_fails_closed(self):
        self.hv.capabilities = "<bad"
        self.assertFalse(self.inspect().ok)
        self.assertIn("Cannot read valid", self.inspect().describe())

    def test_missing_runtime_seclabel_is_blocked(self):
        self.hv.current = xml(security="")
        self.assertFalse(self.inspect().ok)
        self.assertIn("exactly one", self.inspect().describe())

    def test_static_or_opted_out_relabel_is_blocked(self):
        for replacement in ('type="static"', 'relabel="no"'):
            with self.subTest(replacement=replacement):
                self.hv.current = xml(security=LABEL.replace(
                    'type="dynamic"' if replacement.startswith("type") else 'relabel="yes"',
                    replacement,
                ))
                self.assertFalse(self.inspect().ok)

    def test_unexpected_selinux_type_is_blocked(self):
        self.hv.current = xml(security=LABEL.replace("svirt_t", "unconfined_t"))
        self.assertFalse(self.inspect().ok)
        self.assertIn("unexpected sVirt", self.inspect().describe())

    def test_mismatched_image_mcs_is_blocked(self):
        self.hv.current = xml(security=LABEL.replace(
            "svirt_image_t:s0:c101,c209", "svirt_image_t:s0:c110,c220"
        ))
        self.assertFalse(self.inspect().ok)
        self.assertIn("MCS category sets differ", self.inspect().describe())

    def test_duplicate_selinux_label_is_blocked(self):
        self.hv.current = xml(security=LABEL + LABEL)
        self.assertFalse(self.inspect().ok)

    def test_unsafe_live_nic_still_blocked_by_acceptance(self):
        self.hv.current = xml(nic='<interface type="bridge"><source bridge="br0"/></interface>')
        self.assertFalse(self.inspect().ok)
        self.assertIn("network interface", self.inspect().describe())

    def test_lab_connected_to_approved_network_is_not_automatically_proven_isolated(self):
        self.hv.current = xml(nic=LAB_NIC)
        self.hv.inactive = xml(nic=LAB_NIC)
        report = self.inspect("lab")
        self.assertTrue(report.ok, report.describe())
        self.assertIn("packet-level-guest-network-denial", report.evidence()["observations_not_performed"])

    def test_saved_state_policy_bypass_is_blocked(self):
        self.hv.saved = xml(nic='<interface type="bridge"><source bridge="br0"/></interface>')
        self.assertFalse(self.inspect().ok)

    def test_runtime_state_change_during_inspection_blocks_pass(self):
        self.hv.end_state = "shut off"
        result = self.inspect()
        self.assertFalse(result.ok)
        self.assertIn("state changed", result.describe())

    def test_evidence_omits_mcs_values_and_host_paths(self):
        report = self.inspect()
        blob = json.dumps(report.evidence())
        self.assertNotIn(MCS, blob)
        self.assertNotIn("system_u:system_r", blob)
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "new-private-runtime.json"
            save_runtime_observation(report, destination)
            if os.name != "nt":
                self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(MCS, destination.read_text())
            with self.assertRaisesRegex(ToolError, "already exists"):
                save_runtime_observation(report, destination)

    def test_invalid_policy_rejected_before_guest_commands(self):
        with self.assertRaisesRegex(ToolError, "isolated or lab"):
            self.inspect("trusted")
        self.assertEqual(self.hv.calls, [])


if __name__ == "__main__":
    unittest.main()
