"""No network, Docker, shell execution or Git changes: PR stack audit tests.

Mocks simulate all Git read requests; project/user Git trees stay untouched.
"""
from __future__ import annotations

import copy
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Audit-Nightglass-PR-Stack.py"
spec = importlib.util.spec_from_file_location("nightglass_stack_audit_tests", SCRIPT)
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit)

MANIFEST = ROOT / "config" / "nightglass-pr-stack-snapshot.json"
CANDIDATE_SHA = "c" * 40
MAIN_SHA = "a" * 40
BASE_SHA = "b" * 40


class StackAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.chain = audit.validate_manifest(cls.snapshot)

    def test_exact_observed_42_pr_chain_and_missing_30(self):
        self.assertEqual(len(self.chain), 42)
        self.assertEqual(self.chain[0], {
            "pr": 1, "base": "main", "head": "feat/nightglass-phase-01"
        })
        self.assertEqual(self.chain[-1]["pr"], 43)
        self.assertEqual(self.chain[-1]["head"],
                         "verification/windows-one-command-offline-gates")
        self.assertNotIn(30, [p["pr"] for p in self.chain])
        self.assertEqual(self.snapshot["candidate_branch"],
                         "verification/test-gate-reliability-hardening")

    def test_non_linear_duplicate_wrong_repo_and_made_up_pr_rejected(self):
        mutations = (
            lambda x: x["pull_requests"].pop(),
            lambda x: x["pull_requests"][20].update({"base": "main"}),
            lambda x: x["pull_requests"][20].update({"head": x["pull_requests"][19]["head"]}),
            lambda x: x.update({"repository": "unauthorized/repo"}),
            lambda x: x.update({"pr30": "draft"}),
            lambda x: x.update({"candidate_branch": "main"}),
            lambda x: x["pull_requests"][0].update({"head": "evil/../backtrack"}),
            lambda x: x["pull_requests"][0].update({"pr": 30}),
        )
        for fn in mutations:
            with self.subTest(index=mutations.index(fn)):
                model = copy.deepcopy(self.snapshot)
                fn(model)
                with self.assertRaises(audit.StackError):
                    audit.validate_manifest(model)

    def test_snapshot_rejects_duplicate_keys_and_bool_pr_ids(self):
        with self.assertRaises(audit.StackError):
            audit.parse_manifest_bytes(b'{"schema": "one", "schema": "two"}')
        with self.assertRaises(audit.StackError):
            audit.parse_manifest_bytes(b'{"bad": NaN}')
        with self.assertRaises(audit.StackError):
            audit.parse_manifest_bytes(b"")
        with self.assertRaises(audit.StackError):
            audit.parse_manifest_bytes(b"x" * (audit.MAX_MANIFEST_BYTES + 1))
        modified = copy.deepcopy(self.snapshot)
        modified["pull_requests"][0]["pr"] = True
        with self.assertRaises(audit.StackError):
            audit.validate_manifest(modified)
        modified = copy.deepcopy(self.snapshot)
        modified["pull_requests"][10]["head"] = "main"
        with self.assertRaises(audit.StackError):
            audit.validate_manifest(modified)

    def test_dangerous_branch_names_rejected(self):
        for name in ("../main", "refs/heads/main", "origin//main",
                     "evil;rm -rf /", "bad@{0}", "evil.lock", "",
                     "prefix/../other", "-feature", "ends/"):
            with self.subTest(name=name):
                self.assertFalse(audit.valid_branch(name))
        self.assertTrue(audit.valid_branch("verification/remote-ref-stack-audit"))

    def test_preview_reads_nothing_or_runs_no_git(self):
        with patch.object(audit, "read_manifest_at_ref",
                          side_effect=AssertionError("Unexpected manifest read")), \
             patch.object(audit, "verify",
                          side_effect=AssertionError("Unexpected Git inspection")):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(audit.main([]), 0)
        self.assertIn("PLAN ONLY", output.getvalue())
        self.assertIn("NEVER authorizes", output.getvalue())

    def test_manifest_is_read_from_candidate_git_blob_not_main_worktree(self):
        raw = MANIFEST.read_bytes()
        with patch.object(audit, "git", return_value=raw) as local_git:
            entries = audit.read_manifest_at_ref(ROOT, candidate_sha=CANDIDATE_SHA)
        self.assertEqual(len(entries), 42)
        local_git.assert_called_once_with(
            ["show", CANDIDATE_SHA + ":" + audit.MANIFEST_PATH],
            root=ROOT, raw=True)
        self.assertEqual(audit.MANIFEST_PATH,
                         "config/nightglass-pr-stack-snapshot.json")
        with self.assertRaises(audit.StackError):
            audit.read_manifest_at_ref(ROOT, candidate_sha="INVALID")
        with patch.object(audit, "git", return_value=b""):
            with self.assertRaises(audit.StackError):
                audit.read_manifest_at_ref(ROOT, candidate_sha=CANDIDATE_SHA)

    def test_sensitive_diff_file_classification(self):
        examples = (
            (".github/workflows/verify.yml", "GITHUB_WORKFLOW_REVIEW"),
            ("foo/.env", "POSSIBLE_SECRET_FILE_REVIEW"),
            ("secrets/accounts.json", "POSSIBLE_SECRET_FILE_REVIEW"),
            ("keys/id_ed25519", "POSSIBLE_SECRET_FILE_REVIEW"),
            ("dist/nightglass.iso", "BINARY_ARTIFACT_REVIEW"),
            ("scripts/windows-installer.ps1", "OS_DEPLOYMENT_PATH_REVIEW"),
            ("nightglass/app.py", None),
        )
        for value, expected in examples:
            with self.subTest(path=value):
                self.assertEqual(audit.warn_path(value), expected)

    def run_fake(self, *, sha=CANDIDATE_SHA, main_tail=MAIN_SHA,
                 merged_failure=False, main_only=0, diff_bytes=None):
        calls = []
        root = ROOT

        def fake_git(args, *, root, timeout=30, raw=False):
            calls.append(tuple(args))
            if args[:2] == ["rev-parse", "--show-toplevel"]:
                return str(ROOT)
            if args[:3] == ["remote", "get-url", "origin"]:
                return "https://github.com/EngineXus-dev/nightglass-workspaces.git"
            if args[:2] == ["show-ref", "--verify"]:
                key = args[3]
                if key == "refs/heads/main":
                    count = sum(1 for c in calls if c == tuple(args))
                    return MAIN_SHA if count < 2 else main_tail
                if key == "refs/remotes/origin/main":
                    return MAIN_SHA
                if key.endswith(audit.CANDIDATE):
                    return sha
                return BASE_SHA
            if args[0] == "show" and args[1].endswith(
                    ":" + audit.WORKFLOW_PATH):
                assert raw is True
                return (ROOT / audit.WORKFLOW_PATH).read_bytes()
            if args[0] == "rev-list":
                return f"{main_only} 454"
            if args[0] == "diff":
                assert raw is True
                return (diff_bytes if diff_bytes is not None else
                        b".github/workflows/verify.yml\0nightglass/app.py\0")
            raise AssertionError("unexpected Git query: " + str(args))

        def fake_run(args, **kwargs):
            if not isinstance(args, list) or "merge-base" not in args:
                raise AssertionError("Only merge-base read queries allowed")
            return subprocess.CompletedProcess(args, 1 if merged_failure else 0,
                                               stdout=b"", stderr=b"")
        with patch.object(audit, "git", side_effect=fake_git), \
             patch.object(audit.subprocess, "run", side_effect=fake_run):
            result = audit.verify(root, manifest=self.chain,
                                  expected_sha=sha)
        return result, calls

    def test_local_graph_pass_is_never_merge_or_deployment_approval(self):
        result, calls = self.run_fake()
        self.assertTrue(result["structure_pass"])
        self.assertFalse(result["merge_authorized"])
        self.assertFalse(result["deployment_approved"])
        self.assertFalse(result["cumulative_tests_verified"])
        self.assertFalse(result["github_live_pr_status_verified"])
        self.assertEqual(result["manifest_source"], "PINNED_CANDIDATE_GIT_BLOB_NOT_WORKTREE")
        self.assertEqual(result["candidate_sha"], CANDIDATE_SHA)
        self.assertEqual(result["changed_path_count"], 2)
        self.assertIn("GITHUB_WORKFLOW_REVIEW",
                      [x["category"] for x in result["review_flags"]])
        self.assertEqual(result["workflow_policy_review"]["trigger"],
                         "MANUAL_WORKFLOW_DISPATCH_ONLY")
        self.assertEqual(result["workflow_policy_review"]["token_permissions"],
                         "contents: read")
        self.assertIn("MUTABLE_ACTION_REF_REVIEW",
                      [x["category"] for x in result["review_flags"]])
        self.assertFalse(any(c and c[0] in ("fetch", "merge", "checkout",
                                            "reset", "clean", "pull", "push")
                             for c in calls))

    def test_wrong_candidate_sha_or_non_descendant_fails_closed(self):
        with self.assertRaises(audit.StackError):
            audit.verify(ROOT, manifest=self.chain, expected_sha="not a sha")
        failure, _ = self.run_fake(merged_failure=True)
        self.assertFalse(failure["structure_pass"])
        self.assertTrue(failure["blockers"])
        diverged, _ = self.run_fake(main_only=1)
        self.assertFalse(diverged["structure_pass"])
        moved, _ = self.run_fake(main_tail="d" * 40)
        self.assertFalse(moved["structure_pass"])

    def test_workflow_parser_rejects_automatic_triggers_and_write_tokens(self):
        workflow = (ROOT / audit.WORKFLOW_PATH).read_bytes()
        baseline = audit.review_manual_workflow(workflow)
        self.assertEqual(baseline["trigger"], "MANUAL_WORKFLOW_DISPATCH_ONLY")
        for injected in (
            workflow.replace(b"  workflow_dispatch:", b"  push:"),
            workflow.replace(b"  workflow_dispatch:",
                             b"  workflow_dispatch:\n  pull_request:"),
            workflow.replace(b"  contents: read", b"  contents: write"),
            workflow.replace(b"  contents: read", b"  contents: read\n  actions: write"),
            workflow + b"\npermissions:\n  contents: write\n",
            workflow + b"\njobs:\n  test:\n    permissions: write-all\n",
            workflow.replace(b"ubuntu-latest", b"self-hosted"),
        ):
            with self.subTest(blob=injected[-90:]):
                with self.assertRaises(audit.StackError):
                    audit.review_manual_workflow(injected)
        with self.assertRaises(audit.StackError):
            audit.review_manual_workflow(b"x" * (audit.MAX_WORKFLOW_BYTES + 1))
        with self.assertRaises(audit.StackError):
            audit.review_manual_workflow(b"")

    def test_diff_paths_must_have_valid_utf8(self):
        with self.assertRaises(audit.StackError):
            self.run_fake(diff_bytes=b"\xffbad.py\0")

    def test_exclusive_local_report_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "audit.json"
            record = {"structure_pass": False, "merge_authorized": False}
            audit.create_report(target, record)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), record)
            with self.assertRaises(FileExistsError):
                audit.create_report(target, {"merge_authorized": True})
            self.assertEqual(json.loads(target.read_text())["merge_authorized"], False)

    def test_no_implicit_network_merge_checkout_or_installer(self):
        source = SCRIPT.read_text(encoding="utf-8")
        forbidden = ("shell=True", "git merge", "git reset", "git clean",
                     "git checkout", "Invoke-WebRequest", "docker run",
                     "Start-Process", "setup.exe", "powershell.exe",
                     "git fetch")
        for term in forbidden:
            with self.subTest(term=term):
                self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
