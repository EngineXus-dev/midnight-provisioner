"""Read-only, fail-closed Kali guest lock-to-inventory comparison."""
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
from nightglass.kali_drift import (
    LOCK_KEYS, compare_version_lock, compare_version_lock_files,
    save_drift_review, verify_version_lock,
)
from nightglass.kali_setup import (
    INVENTORY_FORMAT, build_setup_plan, save_setup_plan, save_version_lock,
)
from nightglass.runner import ToolError


# Native Windows cannot perform POSIX fchmod. Isolate this capability only
# while running synthetic module tests; production Linux enforcement is intact.
_fixture_mode_patch = None


def setUpModule():
    global _fixture_mode_patch
    if os.name == "nt":
        _fixture_mode_patch = patch("nightglass.kali_setup.os.fchmod", create=True)
        _fixture_mode_patch.start()


def tearDownModule():
    global _fixture_mode_patch
    if _fixture_mode_patch is not None:
        _fixture_mode_patch.stop()
        _fixture_mode_patch = None


class KaliVersionDriftTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.plan = build_setup_plan("recon")
        self.plan_path = self.folder / "new-plan.json"
        self.inventory_path = self.folder / "original-inventory.json"
        self.lock_path = self.folder / "existing-versions.json"
        self.current_path = self.folder / "new-inventory.json"
        self.inventory = {
            "format": INVENTORY_FORMAT, "version": 1,
            "guest": self.plan["guest"], "kali_release": "kali-rolling",
            "packages": [
                {"name": name, "installed_version": "1:1.2.3-1", "candidate_version": "1:1.2.3-1"}
                for name in self.plan["packages"]
            ],
            "dpkg_audit_clean": True,
        }
        save_setup_plan(self.plan, self.plan_path)
        self.inventory_path.write_text(json.dumps(self.inventory), encoding="utf-8")
        save_version_lock(self.plan_path, self.inventory_path, self.lock_path)
        self.lock = json.loads(self.lock_path.read_text(encoding="utf-8"))

    def review(self, inventory=None):
        payload = self.inventory if inventory is None else inventory
        self.current_path.write_text(json.dumps(payload), encoding="utf-8")
        return compare_version_lock_files(self.plan_path, self.lock_path, self.current_path)

    def mutated(self):
        return json.loads(json.dumps(self.inventory))

    def test_unchanged_qualified_as_unverified_not_attested(self):
        result = self.review()
        self.assertTrue(result.unchanged)
        self.assertEqual(result.changed, ())
        self.assertEqual(result.missing, ())
        text = result.describe()
        self.assertIn("NO REPORTED DRIFT (UNVERIFIED)", text)
        self.assertIn("NOT an authenticated Kali VM", text)
        evidence = result.evidence()
        self.assertFalse(evidence["authenticated_guest"])
        self.assertFalse(evidence["apt_signatures_verified"])
        self.assertFalse(evidence["rollback_verified"])
        self.assertEqual(evidence["guest"], self.plan["guest"])
        self.assertEqual(len(evidence["baseline_lock_json_sha256"]), 64)

    def test_changed_version_is_reported_without_fabricating_upgrade_direction(self):
        inventory = self.mutated()
        inventory["packages"][0]["installed_version"] = "0:0.9-1"
        result = self.review(inventory)
        self.assertFalse(result.unchanged)
        self.assertEqual(
            result.changed,
            (("nmap", "1:1.2.3-1", "0:0.9-1"),),
        )
        self.assertIn("DIRECTION UNKNOWN", result.describe())
        self.assertNotIn("DOWNGRADE DETECTED", result.describe())
        self.assertIn("Changes are not classified", result.describe())

    def test_multiple_independent_package_changes_remain_in_catalog_order(self):
        inventory = self.mutated()
        inventory["packages"][2]["installed_version"] = "2:2.0"
        inventory["packages"][0]["installed_version"] = "1:9.9"
        report = self.review(inventory)
        self.assertEqual([row[0] for row in report.changed], ["nmap", "whois"])
        self.assertFalse(report.unchanged)

    def test_missing_uninstalled_and_unavailable_are_not_silent_passes(self):
        inventory = self.mutated()
        inventory["packages"].pop(0)
        inventory["packages"][0]["installed_version"] = None
        inventory["packages"][1]["candidate_version"] = None
        result = self.review(inventory)
        self.assertFalse(result.unchanged)
        self.assertIn("nmap", result.missing)
        self.assertIn("dnsrecon", result.missing)
        self.assertIn("whois", result.unavailable)
        self.assertIn("CANDIDATE NOT REPORTED", result.describe())

    def test_changed_distribution_cannot_be_mistaken_for_old_kali_baseline(self):
        inventory = self.mutated()
        inventory["kali_release"] = "kali-2026.4"
        result = self.review(inventory)
        self.assertFalse(result.unchanged)
        self.assertTrue(any("Kali release changed" in problem for problem in result.problems))

    def test_uncertain_or_failed_guest_dpkg_audit_is_not_green(self):
        for value in (None, False):
            with self.subTest(dpkg=value):
                inventory = self.mutated()
                inventory["dpkg_audit_clean"] = value
                result = self.review(inventory)
                self.assertFalse(result.unchanged)
                self.assertIn("not positively reported clean", result.describe())

    def test_extra_packages_in_user_inventory_cannot_be_ignored(self):
        inventory = self.mutated()
        inventory["packages"].append({
            "name": "unrelated-package", "installed_version": "1",
            "candidate_version": "1",
        })
        result = self.review(inventory)
        self.assertFalse(result.unchanged)
        self.assertIn("outside this selected template", result.describe())

    def test_wrong_guest_and_wrong_package_schema_fail_before_drift_report(self):
        inventory = self.mutated()
        inventory["guest"] = "nightglass-kali-different"
        with self.assertRaisesRegex(ToolError, "another VM"):
            self.review(inventory)
        inventory = self.mutated()
        inventory["packages"][0]["installed_version"] = "$(echo hello)"
        with self.assertRaisesRegex(ToolError, "Invalid package version"):
            self.review(inventory)

    def test_lock_tampering_is_rejected_for_every_assertion_and_package(self):
        candidates = (
            {"guest": "other-vm"},
            {"template_id": "exploit-lab"},
            {"catalog_digest": "0" * 64},
            {"kali_release": "ubuntu-24.04"},
            {"status": "TRUSTED"},
            {"source": "AUTHENTICATED_GUEST"},
            {"snapshot_sha256": "bad"},
            {"apt_repository_signatures_verified": True},
            {"dependency_closure_verified": True},
            {"rollback_snapshot_verified": True},
            {"reported_installed_versions": {"nmap": "9.9"}},
            {"claimed_installer_iso_sha256": "a" * 64},
            {"extra_command": "apt update"},
        )
        for edits in candidates:
            with self.subTest(edit=edits), self.assertRaises(ToolError):
                verify_version_lock(self.plan, {**self.lock, **edits})
        self.assertEqual(set(self.lock), LOCK_KEYS)

    def test_reject_non_string_and_unavailable_baseline_versions(self):
        for invalid in (None, 42, "not valid", "-1", "1.0; uname"):
            with self.subTest(version=invalid):
                lock = self.lock.copy()
                lock["reported_installed_versions"] = dict(self.lock["reported_installed_versions"])
                lock["reported_installed_versions"]["nmap"] = invalid
                with self.assertRaises(ToolError):
                    verify_version_lock(self.plan, lock)

    def test_lock_from_another_curated_profile_never_cross_matches(self):
        other_plan = build_setup_plan("web-audit")
        with self.assertRaisesRegex(ToolError, "different guest"):
            verify_version_lock(other_plan, self.lock)

    def test_symlinked_or_oversized_inventory_and_lock_are_rejected(self):
        self.current_path.write_text(json.dumps(self.inventory), encoding="utf-8")
        link = self.folder / "linked-lock.json"
        try:
            link.symlink_to(self.lock_path)
        except (OSError, NotImplementedError):
            self.skipTest("OS denies creation of synthetic symlinks")
        with self.assertRaisesRegex(ToolError, "Symlinked"):
            compare_version_lock_files(self.plan_path, link, self.current_path)
        huge = self.folder / "huge.json"
        huge.write_bytes(b"x" * (300 * 1024))
        with self.assertRaisesRegex(ToolError, "oversized"):
            compare_version_lock_files(self.plan_path, self.lock_path, huge)

    def test_private_optional_review_evidence_never_overwrites(self):
        result = self.review()
        destination = self.folder / "review.json"
        self.assertEqual(save_drift_review(result, destination), destination)
        if os.name != "nt":
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        document = json.loads(destination.read_text(encoding="utf-8"))
        self.assertIn("UNTRUSTED_USER_SUPPLIED_METADATA", document["source"])
        self.assertNotIn(str(self.folder), destination.read_text(encoding="utf-8"))
        old = destination.read_bytes()
        with self.assertRaisesRegex(ToolError, "already exists"):
            save_drift_review(result, destination)
        self.assertEqual(destination.read_bytes(), old)

    def test_cli_never_calls_libvirt_apt_or_guest_helper(self):
        output = StringIO()
        self.current_path.write_text(json.dumps(self.inventory), encoding="utf-8")
        with patch("nightglass.cli.OfflineProvisioner") as installer, \
             patch("nightglass.cli.Hypervisor") as hypervisor, \
             redirect_stdout(output):
            self.assertEqual(main([
                "templates", "drift", str(self.plan_path),
                str(self.lock_path), str(self.current_path)
            ]), 0)
            self.assertIn("UNVERIFIED", output.getvalue())
            current = self.mutated()
            current["packages"][0]["installed_version"] = "1:5.5"
            self.current_path.write_text(json.dumps(current), encoding="utf-8")
            report_path = self.folder / "new-review.json"
            self.assertEqual(main([
                "templates", "drift", str(self.plan_path),
                str(self.lock_path), str(self.current_path),
                "--report", str(report_path)
            ]), 2)
            self.assertTrue(report_path.exists())
            self.assertIn("VERSION CHANGE", output.getvalue())
            installer.assert_not_called()
            hypervisor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
