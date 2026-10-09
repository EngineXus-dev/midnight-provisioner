"""Offline Kali setup/version manifests: untrusted evidence, no VM changes."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nightglass.cli import main
from nightglass.kali_setup import (
    PLAN_FORMAT, LOCK_FORMAT, INVENTORY_FORMAT,
    build_setup_plan, catalog_digest, compare_inventory,
    compare_inventory_files, load_setup_plan, save_setup_plan,
    save_version_lock, verify_setup_plan,
)
from nightglass.runner import ToolError


class KaliSetupTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.folder = Path(td.name)
        self.plan = build_setup_plan("recon")
        self.plan_path = self.folder / "recon-plan.json"
        self.inventory_path = self.folder / "guest-inventory.json"
        self.good_inventory = {
            "format": INVENTORY_FORMAT,
            "version": 1,
            "guest": self.plan["guest"],
            "kali_release": "kali-rolling",
            "packages": [
                {
                    "name": pkg,
                    "installed_version": "1.2.3-1",
                    "candidate_version": "1.2.3-1",
                }
                for pkg in self.plan["packages"]
            ],
            "dpkg_audit_clean": True,
        }

    def save_inventory(self, record=None):
        self.inventory_path.write_text(
            json.dumps(self.good_inventory if record is None else record),
            encoding="utf-8",
        )

    def test_build_is_pure_and_unknown_versions_remain_unknown(self):
        plan = build_setup_plan("recon", iso_sha256="A" * 64)
        self.assertEqual(plan["format"], PLAN_FORMAT)
        self.assertEqual(plan["status"], "PLANNED_ONLY")
        self.assertEqual(plan["initial_network"], "none")
        self.assertTrue(plan["separate_guest_disk_required"])
        self.assertFalse(plan["package_installation_performed"])
        self.assertFalse(plan["dependency_audit_performed"])
        self.assertFalse(plan["supply_chain_provenance_verified"])
        self.assertEqual(plan["claimed_installer_iso_sha256"], "a" * 64)
        self.assertEqual(plan["catalog_digest"], catalog_digest("recon"))
        self.assertEqual(set(plan["package_versions"]), set(plan["packages"]))
        self.assertTrue(all(x is None for x in plan["package_versions"].values()))
        self.assertFalse(list(self.folder.iterdir()))

    def test_private_plan_roundtrip_exclusive_no_overwrite(self):
        self.assertEqual(save_setup_plan(self.plan, self.plan_path), self.plan_path)
        self.assertEqual(self.plan_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(load_setup_plan(self.plan_path), self.plan)
        data = self.plan_path.read_bytes()
        with self.assertRaisesRegex(ToolError, "already exists"):
            save_setup_plan(self.plan, self.plan_path)
        self.assertEqual(self.plan_path.read_bytes(), data)

    def test_refuse_symlink_plan_and_output(self):
        real = self.folder / "keep-data.json"
        real.write_text(json.dumps(self.plan), encoding="utf-8")
        alias = self.folder / "alias.json"
        alias.symlink_to(real)
        with self.assertRaisesRegex(ToolError, "Symlinked"):
            load_setup_plan(alias)
        with self.assertRaisesRegex(ToolError, "already exists"):
            save_setup_plan(self.plan, alias)
        self.assertEqual(json.loads(real.read_text()), self.plan)

    def test_plan_policy_and_catalog_tampering_fail_closed(self):
        for patchset in (
            {"initial_network": "default"},
            {"status": "INSTALLED_AND_VERIFIED"},
            {"package_installation_performed": True},
            {"supply_chain_provenance_verified": True},
            {"packages": ["kali-linux-everything"]},
            {"catalog_digest": "0" * 64},
            {"extra_injected_command": "shell -c bad"},
            {"package_versions": {"nmap": "0:1.2"}},
        ):
            with self.subTest(patchset=patchset):
                with self.assertRaisesRegex(ToolError, "differs from catalog"):
                    verify_setup_plan({**self.plan, **patchset})

    def test_plan_wrong_guest_iso_digest_and_missing_input(self):
        with self.assertRaisesRegex(ToolError, "checksum"):
            build_setup_plan("recon", iso_sha256="X" * 64)
        with self.assertRaisesRegex(ToolError, "Missing"):
            load_setup_plan(self.folder / "missing.json")
        with self.assertRaises(ToolError):
            build_setup_plan("fake-id")

    def test_self_reported_matching_inventory_never_claims_security(self):
        result = compare_inventory(self.plan, self.good_inventory)
        self.assertTrue(result.complete)
        self.assertEqual(len(result.installed), len(self.plan["packages"]))
        self.assertIn("SELF-REPORTED ONLY", result.describe())
        self.assertIn("NOT authenticated", result.describe())
        self.assertIn("remain unverified", result.describe())

    def test_missing_or_uninstalled_packages_block_completion(self):
        inventory = json.loads(json.dumps(self.good_inventory))
        inventory["packages"].pop()
        result = compare_inventory(self.plan, inventory)
        self.assertFalse(result.complete)
        self.assertIn("MISSING", result.describe())
        inventory = json.loads(json.dumps(self.good_inventory))
        inventory["packages"][0]["installed_version"] = None
        self.assertFalse(compare_inventory(self.plan, inventory).complete)

    def test_missing_candidate_prevents_false_complete(self):
        inventory = json.loads(json.dumps(self.good_inventory))
        inventory["packages"][0]["candidate_version"] = None
        result = compare_inventory(self.plan, inventory)
        self.assertFalse(result.complete)
        self.assertEqual(result.unavailable, ("nmap",))

    def test_upgradable_package_is_visible_without_auto_update(self):
        inventory = json.loads(json.dumps(self.good_inventory))
        inventory["packages"][0]["candidate_version"] = "9.9.9-1"
        result = compare_inventory(self.plan, inventory)
        self.assertTrue(result.complete)
        self.assertEqual(result.upgrade_candidates, ("nmap",))
        self.assertIn("decide manually", result.describe())

    def test_extra_cross_template_package_or_corrupt_dpkg_audit(self):
        inventory = json.loads(json.dumps(self.good_inventory))
        inventory["packages"].append(
            {"name": "metasploit-framework", "installed_version": "1.0", "candidate_version": "1.0"}
        )
        self.assertFalse(compare_inventory(self.plan, inventory).complete)
        inventory = json.loads(json.dumps(self.good_inventory))
        inventory["dpkg_audit_clean"] = False
        self.assertFalse(compare_inventory(self.plan, inventory).complete)
        inventory["dpkg_audit_clean"] = None
        result = compare_inventory(self.plan, inventory)
        self.assertTrue(result.complete)
        self.assertIn("No guest dpkg --audit evidence", result.describe())

    def test_wrong_guest_schema_invalid_versions_and_duplicate_package_rejected(self):
        tests = []
        wrong = json.loads(json.dumps(self.good_inventory))
        wrong["guest"] = "another-vm"
        tests.append(wrong)
        wrong = json.loads(json.dumps(self.good_inventory))
        wrong["kali_release"] = "ubuntu-24.04"
        tests.append(wrong)
        wrong = json.loads(json.dumps(self.good_inventory))
        wrong["packages"][0]["installed_version"] = "1.0; id"
        tests.append(wrong)
        wrong = json.loads(json.dumps(self.good_inventory))
        wrong["packages"].append(dict(wrong["packages"][0]))
        tests.append(wrong)
        wrong = json.loads(json.dumps(self.good_inventory))
        wrong["unknown_field"] = True
        tests.append(wrong)
        wrong = json.loads(json.dumps(self.good_inventory))
        wrong["dpkg_audit_clean"] = "true"
        tests.append(wrong)
        for data in tests:
            with self.subTest(value=data), self.assertRaises(ToolError):
                compare_inventory(self.plan, data)

    def test_lock_requires_fully_reported_versions_and_clean_dpkg(self):
        save_setup_plan(self.plan, self.plan_path)
        self.save_inventory()
        locked = self.folder / "private-lock.json"
        self.assertEqual(
            save_version_lock(self.plan_path, self.inventory_path, locked), locked
        )
        self.assertEqual(locked.stat().st_mode & 0o777, 0o600)
        body = json.loads(locked.read_text())
        self.assertEqual(body["format"], LOCK_FORMAT)
        self.assertEqual(body["status"], "VERSION_SNAPSHOT_ONLY")
        self.assertEqual(set(body["reported_installed_versions"]), set(self.plan["packages"]))
        self.assertFalse(body["apt_repository_signatures_verified"])
        self.assertFalse(body["dependency_closure_verified"])
        self.assertFalse(body["rollback_snapshot_verified"])
        self.assertNotIn(str(self.folder), locked.read_text())
        with self.assertRaisesRegex(ToolError, "already exists"):
            save_version_lock(self.plan_path, self.inventory_path, locked)

    def test_lock_refuses_incomplete_unavailable_and_unverified_dpkg(self):
        save_setup_plan(self.plan, self.plan_path)
        incomplete = json.loads(json.dumps(self.good_inventory))
        incomplete["packages"][0]["installed_version"] = None
        self.save_inventory(incomplete)
        with self.assertRaisesRegex(ToolError, "missing"):
            save_version_lock(self.plan_path, self.inventory_path, self.folder / "none.json")
        incomplete = json.loads(json.dumps(self.good_inventory))
        incomplete["dpkg_audit_clean"] = None
        self.save_inventory(incomplete)
        with self.assertRaisesRegex(ToolError, "dpkg audit"):
            save_version_lock(self.plan_path, self.inventory_path, self.folder / "none.json")

    def test_bounded_inventory_json_rejects_symlinks_and_large_files(self):
        save_setup_plan(self.plan, self.plan_path)
        self.save_inventory()
        link = self.folder / "linked.json"
        link.symlink_to(self.inventory_path)
        with self.assertRaisesRegex(ToolError, "Symlinked"):
            compare_inventory_files(self.plan_path, link)
        big = self.folder / "huge.json"
        big.write_bytes(b"z" * (300 * 1024))
        with self.assertRaisesRegex(ToolError, "oversized"):
            compare_inventory_files(self.plan_path, big)

    def test_cli_export_verify_compare_lock_never_calls_vm_or_installer(self):
        target = self.folder / "cli-plan.json"
        out = StringIO()
        with patch("nightglass.cli.OfflineProvisioner") as install, \
             patch("nightglass.cli.Hypervisor") as hypervisor, redirect_stdout(out):
            self.assertEqual(main([
                "templates", "export", "recon", str(target),
            ]), 0)
            self.assertIn("no guest or host software", out.getvalue())
            self.assertEqual(main(["templates", "verify", str(target)]), 0)
            self.save_inventory()
            self.assertEqual(main([
                "templates", "compare", str(target), str(self.inventory_path),
            ]), 0)
            lock = self.folder / "cli-lock.json"
            self.assertEqual(main([
                "templates", "lock", str(target), str(self.inventory_path), str(lock),
            ]), 0)
            self.assertTrue(lock.exists())
            install.assert_not_called()
            hypervisor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
