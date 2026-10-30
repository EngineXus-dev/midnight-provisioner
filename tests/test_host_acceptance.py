"""Synthetic host prerequisite tests. No real VM, sudo, SELinux changes or network."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from midnight_provisioner.host_acceptance import (
    HostPrerequisites, Gate, inspect_prerequisites, save_private_evidence,
)
from midnight_provisioner.host_posture import HostPosture, PostureCheck
from midnight_provisioner.runner import Output, ToolError


class FakeRunner:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def run(self, argv, timeout=12):
        self.calls.append((tuple(argv), timeout))
        if self.fail:
            raise ToolError("private host diagnostic: do not disclose")
        return Output("sensitive-guest-name\n")


def healthy_posture(*, kvm="OK", selinux="OK", privileges="OK"):
    return HostPosture((
        PostureCheck("Privileges", privileges, "synthetic"),
        PostureCheck("SELinux", selinux, "synthetic"),
        PostureCheck("KVM", kvm, "synthetic"),
    ))


def fake_which(tool):
    return "/usr/bin/" + tool if tool in {"virsh", "virt-xml-validate", "qemu-img"} else None


class FedoraHostPrerequisiteTests(unittest.TestCase):
    def run_probe(self, *, release="fedora", version="43", posture=None,
                  runner=None, which=fake_which, system="Linux"):
        runner = runner if runner is not None else FakeRunner()
        posture = posture if posture is not None else healthy_posture()
        with patch("midnight_provisioner.host_acceptance.platform.system", return_value=system), \
             patch("midnight_provisioner.host_acceptance.platform.freedesktop_os_release",
                   return_value={"ID": release, "VERSION_ID": version}):
            report = inspect_prerequisites(runner=runner, which=which, posture=posture)
        return report, runner

    def test_fedora_nonroot_selinux_kvm_native_and_libvirt_prerequisites(self):
        result, runner = self.run_probe()
        self.assertTrue(result.prerequisites_met)
        self.assertEqual(result.fedora_release, "43")
        self.assertEqual(len(result.gates), 6)
        self.assertTrue(all(item.status == "PASS" for item in result.gates))
        self.assertEqual(runner.calls, [
            (("virsh", "--connect", "qemu:///system", "list", "--all", "--name"), 12)
        ])
        self.assertIn("HARDWARE SECURITY ACCEPTANCE: PENDING", result.describe())
        self.assertEqual(result.evidence()["hardware_security_acceptance"], "PENDING")

    def test_non_fedora_never_attempts_vm_or_libvirt_query(self):
        for system, release in (("Linux", "debian"), ("Windows", "fedora")):
            with self.subTest(system=system, release=release):
                result, runner = self.run_probe(system=system, release=release)
                self.assertFalse(result.prerequisites_met)
                self.assertEqual(result.gates[0].status, "BLOCKED")
                self.assertEqual(runner.calls, [])

    def test_root_selinux_permissive_kvm_missing_fail_closed(self):
        result, runner = self.run_probe(posture=healthy_posture(
            privileges="WARN", selinux="UNKNOWN", kvm="WARN"
        ))
        self.assertFalse(result.prerequisites_met)
        self.assertEqual([item.status for item in result.gates[:4]],
                         ["PASS", "BLOCKED", "BLOCKED", "BLOCKED"])
        self.assertEqual(runner.calls, [])

    def test_unreadable_libvirt_stays_blocked_and_does_not_echo_exception(self):
        report, runner = self.run_probe(runner=FakeRunner(fail=True))
        self.assertFalse(report.prerequisites_met)
        self.assertEqual(report.gates[-1].status, "BLOCKED")
        self.assertNotIn("private host diagnostic", json.dumps(report.evidence()))
        self.assertEqual(len(runner.calls), 1)

    def test_tools_missing_block_without_invalid_libvirt_invocation(self):
        report, runner = self.run_probe(which=lambda _tool: None)
        self.assertFalse(report.prerequisites_met)
        self.assertEqual(report.gates[-2].status, "BLOCKED")
        self.assertEqual(report.gates[-1].status, "BLOCKED")
        self.assertEqual(runner.calls, [])

    def test_release_version_malformed_is_never_exported(self):
        report, _ = self.run_probe(version="43 private-hostname=/home/user")
        self.assertTrue(report.prerequisites_met)
        self.assertIsNone(report.evidence()["fedora_release"])

    def test_no_private_names_or_process_labels_appear_in_evidence(self):
        report, _ = self.run_probe()
        payload = json.dumps(report.evidence())
        self.assertNotIn("sensitive-guest-name", payload)
        self.assertNotIn("/usr/bin", payload)
        self.assertNotIn("system_u:system_r", payload)
        for expected in (
            "live-qemu-and-disk-inode-selinux-contexts",
            "host-bridge-and-packet-level-network-denial",
            "independent-cold-backup-restore-and-rollback",
        ):
            self.assertIn(expected, payload)

    def test_evidence_file_is_private_new_and_exclusive(self):
        report, _ = self.run_probe()
        with tempfile.TemporaryDirectory() as home:
            destination = Path(home) / "new-host-evidence.json"
            save_private_evidence(report, destination)
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
            payload = json.loads(destination.read_text(encoding="utf-8"))
            self.assertTrue(payload["host_prerequisites_met"])
            self.assertEqual(payload["hardware_security_acceptance"], "PENDING")
            with self.assertRaises(FileExistsError):
                save_private_evidence(report, destination)
            self.assertTrue(payload == json.loads(destination.read_text(encoding="utf-8")))

    def test_symlink_destination_is_refused(self):
        report, _ = self.run_probe()
        with tempfile.TemporaryDirectory() as home:
            parent = Path(home)
            original = parent / "real.json"
            original.write_text("do-not-overwrite", encoding="utf-8")
            link = parent / "alias.json"
            try:
                link.symlink_to(original)
            except (OSError, NotImplementedError):
                self.skipTest("OS denies creation of symlinks")
            with self.assertRaises(ValueError):
                save_private_evidence(report, link)
            self.assertEqual(original.read_text(encoding="utf-8"), "do-not-overwrite")

    def test_parent_must_exist_without_implicit_creation(self):
        report, _ = self.run_probe()
        with tempfile.TemporaryDirectory() as home:
            dest = Path(home) / "missing" / "out.json"
            with self.assertRaises(ValueError):
                save_private_evidence(report, dest)
            self.assertFalse(dest.parent.exists())

    def test_invalid_status_cannot_claim_green(self):
        with self.assertRaises(ValueError):
            Gate("host-isolated", "CERTIFIED", "unsupported")
        self.assertFalse(HostPrerequisites((Gate("test", "PENDING", "pending"),), None).prerequisites_met)


if __name__ == "__main__":
    unittest.main()
