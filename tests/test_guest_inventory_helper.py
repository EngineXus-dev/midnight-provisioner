"""Standalone Kali guest inventory helper — synthetic non-root, no guest/VMM calls."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from nightglass.kali_setup import (
    build_setup_plan, compare_inventory, guest_inventory_instructions,
    save_setup_plan,
)
from nightglass.cli import main as host_cli

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "kali-guest-inventory.py"

spec = importlib.util.spec_from_file_location("kali_guest_inventory", SCRIPT)
guest_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest_helper)


def completed(argv, stdout="", stderr="", code=0):
    return subprocess.CompletedProcess(argv, code, stdout, stderr)


class GuestInventoryHelperTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.folder = Path(td.name)
        self.plan_path = self.folder / "new-plan.json"
        self.plan = build_setup_plan("recon")
        save_setup_plan(self.plan, self.plan_path)
        self.kali_release = self.folder / "os-release"
        self.kali_release.write_text('NAME="Kali GNU/Linux"\nID=kali\nVERSION_CODENAME=kali-rolling\n')
        self.commands = []

    def fake_query(self, argv, timeout=12):
        self.commands.append(tuple(argv))
        name = argv[-1]
        if argv[0] == "dpkg-query":
            return completed(argv, stdout="install ok installed\t1:1.2.3-1\n")
        if argv[:2] == ["apt-cache", "policy"]:
            return completed(argv, stdout=f"{name}:\n  Installed: 1:1.2.3-1\n  Candidate: 1:1.2.3-1\n")
        if argv == ["dpkg", "--audit"]:
            return completed(argv, stdout="")
        raise AssertionError("Unexpected guest command requested")

    def collect(self):
        with patch.object(guest_helper.os, "geteuid", return_value=1000), \
             patch.object(guest_helper, "_query", side_effect=self.fake_query):
            return guest_helper.collect(self.plan_path, self.kali_release)

    def test_report_is_consumable_by_existing_host_plan_comparer(self):
        report = self.collect()
        self.assertEqual(report["format"], "nightglass-kali-guest-inventory")
        self.assertEqual(report["guest"], self.plan["guest"])
        self.assertEqual(report["kali_release"], "kali-rolling")
        self.assertTrue(report["dpkg_audit_clean"])
        self.assertEqual([r["name"] for r in report["packages"]], self.plan["packages"])
        self.assertTrue(compare_inventory(self.plan, report).complete)
        self.assertEqual(len(self.commands), len(self.plan["packages"]) * 2 + 1)
        self.assertTrue(all(call[0] in ("dpkg-query", "apt-cache", "dpkg")
                            for call in self.commands))

    def test_missing_package_is_reported_not_fabricated_installed(self):
        def runner(argv, timeout=12):
            if argv[0] == "dpkg-query":
                return completed(argv, stderr="dpkg-query: no packages found matching dnsrecon",
                                 code=1)
            return completed(argv, stdout="dnsrecon:\n  Installed: (none)\n  Candidate: (none)\n")
        with patch.object(guest_helper, "_query", side_effect=runner):
            actual, candidate = guest_helper.package_versions("dnsrecon")
        self.assertIsNone(actual)
        self.assertIsNone(candidate)

    def test_unrecognized_dpkg_failures_and_invalid_candidate_fail_closed(self):
        for bad in [
            completed([], stderr="dpkg: permission denied", code=1),
            completed([], stdout="unknown output", code=0),
        ]:
            with self.subTest(bad=bad.stdout or bad.stderr), \
                 patch.object(guest_helper, "_query", return_value=bad), \
                 self.assertRaises(guest_helper.InventoryError):
                guest_helper.package_versions("nmap")
        with patch.object(guest_helper, "_query",
                          side_effect=[
                              completed([], stdout="install ok installed\t1.0\n"),
                              completed([], stdout="nmap:\n  Candidate: 1.0;rm\n"),
                          ]):
            with self.assertRaisesRegex(guest_helper.InventoryError, "Invalid candidate"):
                guest_helper.package_versions("nmap")

    def test_non_kali_release_and_root_execution_refused_before_queries(self):
        self.kali_release.write_text("ID=ubuntu\nVERSION_ID=24.04\n")
        with self.assertRaisesRegex(guest_helper.InventoryError, "Only run inside"):
            guest_helper.kali_release(self.kali_release)
        self.kali_release.write_text("ID=kali\nVERSION_CODENAME=kali-rolling\n")
        with patch.object(guest_helper.os, "geteuid", return_value=0), \
             patch.object(guest_helper, "_query") as query, \
             self.assertRaisesRegex(guest_helper.InventoryError, "not root"):
            guest_helper.collect(self.plan_path, self.kali_release)
        query.assert_not_called()

    def test_readonly_queries_use_no_shell_and_fixed_argv(self):
        with patch.object(guest_helper.subprocess, "run",
                          return_value=completed([], stdout="")) as run:
            result = guest_helper._query(["dpkg", "--audit"])
            self.assertEqual(result.returncode, 0)
            run.assert_called_once()
            argv, = run.call_args.args
            self.assertEqual(argv, ["dpkg", "--audit"])
            self.assertIs(run.call_args.kwargs["shell"], False)
            self.assertIs(run.call_args.kwargs["check"], False)
            self.assertEqual(run.call_args.kwargs["env"]["LC_ALL"], "C")
        with patch.object(guest_helper.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("dpkg", 1)):
            with self.assertRaisesRegex(guest_helper.InventoryError, "unavailable"):
                guest_helper._query(["dpkg", "--audit"])
        with self.assertRaisesRegex(guest_helper.InventoryError, "Invalid package name"):
            guest_helper.package_versions("--bad")

    def test_plan_tampering_and_symlinks_are_rejected(self):
        for patchset in (
            {"initial_network": "default"},
            {"status": "INSTALLED"},
            {"packages": ["kali-linux-everything"]},
            {"packages": ["nmap", "nmap"]},
            {"package_installation_performed": True},
        ):
            with self.subTest(patchset=patchset):
                original = self.plan_path.read_text()
                self.plan_path.write_text(json.dumps({**self.plan, **patchset}))
                with self.assertRaises(guest_helper.InventoryError):
                    guest_helper.read_plan(self.plan_path)
                self.plan_path.write_text(original)
        linked = self.folder / "alias.json"
        linked.symlink_to(self.plan_path)
        with self.assertRaisesRegex(guest_helper.InventoryError, "symlink"):
            guest_helper.read_plan(linked)

    def test_save_private_new_inventory_never_overwrites_other_files(self):
        report = self.collect()
        target = self.folder / "new-guest-inventory.json"
        guest_helper.save_new(report, target)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(target.read_text()), report)
        old = target.read_bytes()
        with self.assertRaisesRegex(guest_helper.InventoryError, "already exists"):
            guest_helper.save_new(report, target)
        self.assertEqual(target.read_bytes(), old)
        linked = self.folder / "symlink.json"
        linked.symlink_to(target)
        with self.assertRaisesRegex(guest_helper.InventoryError, "already exists"):
            guest_helper.save_new(report, linked)

    def test_audit_error_never_sets_clean_true(self):
        with patch.object(guest_helper, "_query",
                          return_value=completed([], stdout="1 partially installed package\n")):
            self.assertFalse(guest_helper.dpkg_audit())
        with patch.object(guest_helper, "_query",
                          return_value=completed([], stderr="permission denied", code=2)):
            self.assertFalse(guest_helper.dpkg_audit())

    def test_host_cli_and_instructions_do_not_contact_guest_or_libvirt(self):
        from contextlib import redirect_stdout
        from io import StringIO
        output = StringIO()
        with patch("nightglass.cli.OfflineProvisioner") as provisioning, \
             patch("nightglass.cli.Hypervisor") as hypervisor, redirect_stdout(output):
            self.assertEqual(host_cli(["templates", "guest-help", "recon"]), 0)
            provisioning.assert_not_called()
            hypervisor.assert_not_called()
        text = output.getvalue()
        self.assertIn("python3 kali-guest-inventory.py --plan", text)
        self.assertIn("does NOT provide host/guest file sharing", text)
        self.assertIn("BENIGN", text)
        self.assertIn("\n3. As a normal user", text)
        self.assertIn("not authenticated", text.lower())


if __name__ == "__main__":
    unittest.main()
