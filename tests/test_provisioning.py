"""Mocked VM provisioning checks: no actual guests or root privileges needed."""
from __future__ import annotations
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nightglass.portability import budget_for
from nightglass.provisioning import (
    MIN_ISO_BYTES, OfflineProvisioner, build_plan, verify_iso,
)
from nightglass.runner import Output, ToolError


def good_xml(name="nightglass-malware", extra="", ram=2048):
    return (
        '<domain type="kvm"><name>' + name + '</name>'
        f'<memory unit="MiB">{ram}</memory><devices>'
        '<graphics type="vnc" listen="127.0.0.1"/>' + extra +
        '</devices></domain>'
    )


class FakeRunner:
    def __init__(self, xml1, xml2):
        self.calls = []
        self.xml = (xml1, xml2)

    def run(self, argv, timeout=12):
        self.calls.append(tuple(argv))
        if argv[:4] == ["virsh", "--connect", "qemu:///system", "list"]:
            return Output("")
        if argv[0] != "virt-install":
            raise AssertionError(f"Unexpected command: {argv}")
        assert "--dry-run" in argv
        assert "--print-xml" in argv
        stage = int(argv[-1])
        return Output(self.xml[stage - 1])


class OfflineProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.iso = Path(self.temp.name) / "official test installer.iso"
        with self.iso.open("wb") as fp:
            fp.truncate(MIN_ISO_BYTES)
        digest = hashlib.sha256()
        with self.iso.open("rb") as fp:
            for block in iter(lambda: fp.read(1024 * 1024), b""):
                digest.update(block)
        self.expected = digest.hexdigest()
        self.budget = budget_for(7.7, 6)

    def make(self, kind="analysis", **kwargs):
        return build_plan(kind, self.iso, self.expected, budget=self.budget, **kwargs)

    def test_both_install_xml_phases_are_audited(self):
        plan = self.make()
        runner = FakeRunner(good_xml(), good_xml())
        preview = OfflineProvisioner(runner).preview(plan)
        self.assertIn("PREVIEW ONLY", preview.describe())
        self.assertEqual(len(preview.observations), 2)
        self.assertEqual(len([x for x in runner.calls if x[0] == "virt-install"]), 2)
        for command in runner.calls:
            if command[0] == "virt-install":
                self.assertIn("--dry-run", command)
                self.assertIn("--network", command)
                self.assertIn("none", command)
        self.assertEqual(verify_iso(plan), self.expected)

    def test_security_regression_in_second_phase_fails_closed(self):
        plan = self.make()
        runner = FakeRunner(good_xml(), good_xml(extra='<interface type="bridge"/>'))
        with self.assertRaisesRegex(ToolError, "stage 2"):
            OfflineProvisioner(runner).preview(plan)
        self.assertFalse(any("--force" in call for call in runner.calls))

    def test_spice_console_and_sharing_fail_closed(self):
        plan = self.make()
        for element in (
            '<console type="pty"/>',
            '<filesystem type="mount"/>',
            '<graphics type="spice"/>',
            '<channel type="spicevmc"/>',
        ):
            with self.subTest(element=element):
                with self.assertRaisesRegex(ToolError, "stage 1"):
                    OfflineProvisioner(
                        FakeRunner(good_xml(extra=element), good_xml())
                    ).preview(plan)

    def test_invalid_or_mismatched_image_never_invokes_virtinstall(self):
        with self.assertRaises(ToolError):
            build_plan("analysis", self.iso, "not a sha256", budget=self.budget)
        bad = build_plan("analysis", self.iso, "a" * 64, budget=self.budget)
        runner = FakeRunner(good_xml(), good_xml())
        with self.assertRaisesRegex(ToolError, "SHA-256 mismatch"):
            OfflineProvisioner(runner).preview(bad)
        self.assertFalse(any(c[0] == "virt-install" for c in runner.calls))

    def test_existing_guest_name_blocks_preview(self):
        plan = self.make()
        fake = FakeRunner(good_xml(), good_xml())
        class ExistingVM:
            def list_domains(self):
                return ["nightglass-malware"]
        with self.assertRaisesRegex(ToolError, "already exists"):
            OfflineProvisioner(fake, ExistingVM()).preview(plan)
        self.assertEqual(fake.calls, [])

    def test_ram_cap_and_name_validation(self):
        with self.assertRaises(ToolError):
            self.make(ram_mib=4096)
        with self.assertRaises(ToolError):
            self.make(vcpus=20)
        with self.assertRaises(ValueError):
            self.make(name="--delete-all")

    def test_iso_must_be_local_large_regular_file(self):
        little = Path(self.temp.name) / "tiny.iso"
        little.write_bytes(b"not a real ISO")
        with self.assertRaises(ToolError):
            build_plan("analysis", little, self.expected, budget=self.budget)
        link = Path(self.temp.name) / "symlink.iso"
        link.symlink_to(self.iso)
        with self.assertRaises(ToolError):
            build_plan("analysis", link, self.expected, budget=self.budget)
        with self.assertRaises(ToolError):
            build_plan("analysis", Path(self.temp.name) / "missing.iso", self.expected, budget=self.budget)

    def test_pentest_is_offline_even_before_lab_network_setup(self):
        plan = self.make(kind="pentest")
        args = plan.command()
        self.assertEqual(args[args.index("--network") + 1], "none")
        self.assertEqual(plan.policy, "lab")

    def test_malformed_or_wrong_domain_xml_is_blocked(self):
        plan = self.make()
        for xml in ('<notdomain/>', '<invalid', good_xml(name="other")):
            with self.subTest(xml=xml):
                with self.assertRaises(ToolError):
                    OfflineProvisioner(FakeRunner(xml, good_xml())).preview(plan)

    def test_no_auto_download_or_storage_write(self):
        plan = self.make()
        args = plan.command()
        forbidden = ("--force", "--autostart", "--unattended", "--import", "--reinstall")
        for item in forbidden:
            self.assertNotIn(item, args)
        self.assertIn("--noautoconsole", args)


if __name__ == "__main__":
    unittest.main()
