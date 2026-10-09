"""Host-posture policy tests: synthetic values, no privileged actions."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import nightglass.host_posture as posture
from nightglass.runner import Output, ToolError


class FakeRunner:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def run(self, argv, timeout=6):
        self.calls.append((tuple(argv), timeout))
        outcome = self.responses.get(tuple(argv))
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome is None:
            raise AssertionError(f"Unexpected command {argv}")
        return Output(outcome)


class HostPostureTests(unittest.TestCase):
    def run_posture(self, *, kernel="1", mode="Enforcing", firewall="running",
                    ipv4="0", ipv6="0", kvm_exists=True, kvm_access=True,
                    root_uid=1000):
        runner = FakeRunner({
            ("getenforce",): mode,
            ("firewall-cmd", "--state"): firewall,
        })
        mapping = {
            str(posture.SELINUX_ENFORCE): kernel,
            str(posture.IPV4_FORWARD): ipv4,
            str(posture.IPV6_FORWARD): ipv6,
        }
        def read(path):
            return mapping[str(path)]
        with patch.object(posture, "_read_value", side_effect=read), \
             patch.object(posture.platform, "system", return_value="Linux"), \
             patch.object(posture.os, "geteuid", return_value=root_uid, create=True), \
             patch.object(posture.KVM_DEVICE.__class__, "is_symlink", return_value=False), \
             patch.object(posture.KVM_DEVICE.__class__, "exists", return_value=kvm_exists), \
             patch.object(posture.KVM_DEVICE.__class__, "is_char_device", return_value=True), \
             patch.object(posture.os, "access", return_value=kvm_access):
            result = posture.inspect_host_posture(
                runner=runner, which=lambda name: "/usr/bin/" + name
            )
        return result, runner

    def check(self, result, name):
        return next(x for x in result.checks if x.name == name)

    def test_enforcing_selinux_and_accessible_kvm(self):
        report, runner = self.run_posture()
        self.assertTrue(report.complete)
        self.assertEqual(self.check(report, "SELinux").status, "OK")
        self.assertEqual(self.check(report, "KVM").status, "OK")
        self.assertEqual(self.check(report, "firewalld").status, "INFO")
        self.assertIn("NOT verified", self.check(report, "firewalld").message)
        self.assertEqual(self.check(report, "IPv4 forwarding").status, "INFO")
        self.assertTrue(all(
            argv in {("getenforce",), ("firewall-cmd", "--state")}
            for argv, _ in runner.calls
        ))

    def test_permissive_or_disabled_is_not_safe(self):
        for state, kernel in (("Permissive", "0"), ("Disabled", None)):
            with self.subTest(state=state):
                report, _ = self.run_posture(kernel=kernel, mode=state)
                self.assertFalse(report.complete)
                self.assertEqual(self.check(report, "SELinux").status, "WARN")

    def test_conflicting_selinux_reports_unknown(self):
        report, _ = self.run_posture(kernel="1", mode="Permissive")
        self.assertFalse(report.complete)
        self.assertEqual(self.check(report, "SELinux").status, "UNKNOWN")

    def test_unreadable_or_malformed_selinux_never_claims_enforcing(self):
        for kernel, mode in ((None, None), ("weird", None), ("1", "something-else")):
            with self.subTest(kernel=kernel, mode=mode):
                if mode is None:
                    mode = ToolError("Failed to run getenforce")
                report, _ = self.run_posture(kernel=kernel, mode=mode)
                self.assertNotEqual(self.check(report, "SELinux").status, "OK")

    def test_selinux_kernel_fallback_when_getenforce_unavailable(self):
        report, _ = self.run_posture(kernel="1", mode=ToolError("missing"))
        self.assertEqual(self.check(report, "SELinux").status, "OK")

    def test_kvm_permission_denial_is_warning(self):
        report, _ = self.run_posture(kvm_access=False)
        self.assertEqual(self.check(report, "KVM").status, "WARN")
        self.assertIn("do not use sudo", self.check(report, "KVM").message)

    def test_kvm_missing_is_warning(self):
        report, _ = self.run_posture(kvm_exists=False)
        self.assertEqual(self.check(report, "KVM").status, "WARN")

    def test_running_as_root_is_warning(self):
        report, _ = self.run_posture(root_uid=0)
        self.assertEqual(self.check(report, "Privileges").status, "WARN")
        self.assertFalse(report.complete)

    def test_forwarding_is_only_informational_not_a_guest_denial_proof(self):
        report, _ = self.run_posture(ipv4="1", ipv6="1")
        self.assertTrue(report.complete)
        self.assertIn("enabled", self.check(report, "IPv4 forwarding").message)
        self.assertIn("NOT", report.describe())

    def test_missing_forwarding_state_is_unknown(self):
        report, _ = self.run_posture(ipv4=None)
        self.assertFalse(report.complete)
        self.assertEqual(self.check(report, "IPv4 forwarding").status, "UNKNOWN")

    def test_firewalld_unavailable_is_unknown_not_a_pass(self):
        report, _ = self.run_posture(firewall=ToolError("permission denied"))
        self.assertEqual(self.check(report, "firewalld").status, "UNKNOWN")
        self.assertFalse(report.complete)

    def test_status_names_are_strict(self):
        with self.assertRaises(ValueError):
            posture.PostureCheck("anything", "CERTIFIED", "False assurance")


if __name__ == "__main__":
    unittest.main()
