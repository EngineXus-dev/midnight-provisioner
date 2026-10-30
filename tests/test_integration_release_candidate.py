"""Cumulative Midnight Provisioner source RC controls; never inspect real drives or merge."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "config/midnight-provisioner-integration-snapshot-v2.json"
AUDIT = ROOT / "scripts/release/Review-Midnight-Provisioner-Integration.py"
PACK = ROOT / "scripts/release/Package-Midnight-Provisioner-ReleaseCandidate.ps1"


class IntegrationReleaseCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(SNAP.read_text(encoding="utf-8"))
        spec = importlib.util.spec_from_file_location("midnight_provisioner_integration", AUDIT)
        cls.audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.audit)

    def test_exact_63_pr_snapshot_and_discrete_fork(self):
        d = self.audit.validate_snapshot(self.data)
        self.assertEqual(len(d["linear_prs"]), 63)
        self.assertEqual(len(d["divergent_prs"]), 1)
        self.assertEqual(d["divergent_prs"][0]["number"], 53)
        self.assertFalse(d["divergent_prs"][0]["auto_merge"])

    def test_live_snapshot_is_pinned_to_verified_phase27(self):
        self.assertEqual(self.data["candidate_sha"],
                         "2902acbeb1402cf1fc18d0374aad4951bd8d60a2")
        self.assertEqual(self.data["candidate_branch"],
                         "safety/phase27-untrusted-install-plan-review")

    def test_snapshot_never_authorizes_merge_or_hardware(self):
        self.assertIs(self.data["merge_authorized"], False)
        self.assertIs(self.data["deploy_authorized"], False)
        self.assertIn("user_explicit_merge_approval",
                      " ".join(self.data["required_checks"]))

    def test_main_pinned_and_pr30_is_not_fabricated(self):
        self.assertEqual(self.data["main_sha"],
                         "7ed599e9724551fffc203203a1ab4173bb7510c9")
        self.assertNotIn(30, [x["number"] for x in self.data["linear_prs"]])

    def test_source_packager_never_copies_workstation_environments(self):
        body = PACK.read_text(encoding="utf-8")
        for needle in ("ls-tree", "git -C $RepoPath archive", "Get-FileHash",
                       ".venv", ".env", "SOURCE_CANDIDATE_NOT_PRODUCTION_DEPLOYMENT",
                       "disk_write_authorized=$false",
                       "local_main_after=$mainAfter"):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)

    def test_packager_excludes_destructive_host_commands(self):
        text = PACK.read_text(encoding="utf-8")
        for needle in ("Clear-Disk ", "Format-Volume ", "Remove-Item ",
                       "git reset --hard", "git clean -fdx",
                       "Set-Partition ", "Initialize-Disk ", "Stop-VM "):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, text)

    def test_fork_reconciliation_is_explicit_not_deleted(self):
        text = (ROOT / "docs/PR53_DIVERGENT_BRANCH_RECONCILIATION.md").read_text(
            encoding="utf-8")
        self.assertIn("PR #53", text)
        self.assertIn("without modifying Fedora production mode", text)
        self.assertIn("Do not automatically merge", text)
        self.assertTrue((ROOT / "docs/HISTORICAL_PR53_WINDOWS_FAILURE_TRIAGE.md").is_file())


if __name__ == "__main__":
    unittest.main()
