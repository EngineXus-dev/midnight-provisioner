"""Offline synthetic 63-PR chain, branch drift and separate fork regressions."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

FILE = Path(__file__).resolve().parents[1] / "scripts/release/Review-Nightglass-Integration.py"
spec = importlib.util.spec_from_file_location("nightglass_integration_graph", FILE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def git(root, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME":"Nightglass Test",
           "GIT_AUTHOR_EMAIL":"test@example.org",
           "GIT_COMMITTER_NAME":"Nightglass Test",
           "GIT_COMMITTER_EMAIL":"test@example.org"}
    p = subprocess.run(["git", "-C", str(root), *args], text=True,
                       capture_output=True, check=True, timeout=15, env=env)
    return p.stdout.strip()


def synthetic_repo(root):
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin",
        "https://github.com/EngineXus-dev/nightglass-workspaces.git")
    git(root, "commit", "-q", "--allow-empty", "-m", "baseline")
    main = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/main", main)
    git(root, "checkout", "--quiet", "--detach", main)
    chain = []
    predecessor, sha = "main", main
    fork_base = None
    for n in (i for i in range(1, 66) if i not in (30, 53)):
        git(root, "commit", "-q", "--allow-empty", "-m", "phase-%d" % n)
        head = git(root, "rev-parse", "HEAD")
        name = "draft/test-%02d" % n
        git(root, "update-ref", "refs/remotes/origin/" + name, head)
        chain.append(dict(number=n, branch=name, sha=head,
                          base=predecessor, base_sha=sha, draft=True))
        predecessor, sha = name, head
        if n == 52:
            fork_base = head
    git(root, "checkout", "--quiet", "--detach", fork_base)
    git(root, "commit", "-q", "--allow-empty", "-m", "separate-pr53")
    fork = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/draft/pr53", fork)
    git(root, "checkout", "--quiet", "main")
    return {
        "schema": mod.SCHEMA, "repository": mod.REPOSITORY,
        "default_branch": "main", "main_sha": main,
        "candidate_branch": predecessor, "candidate_sha": sha,
        "merge_authorized": False, "deploy_authorized": False,
        "open_pr_count": 64, "linear_pr_count": 63, "linear_prs": chain,
        "divergent_prs": [{
            "number":53, "branch":"draft/pr53", "sha":fork,
            "base":"draft/test-52", "base_sha":fork_base,
            "disposition":"PENDING_INDEPENDENT_CONTENT_RECONCILIATION",
            "auto_merge":False,
        }],
    }


class StackIntegrationGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One complete, disposable 63-commit Git graph per unittest module,
        # not one graph per test. Windows Git process startup otherwise
        # multiplies this fixture cost and can exceed operator time budgets.
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        try:
            cls.base_data = synthetic_repo(cls.root)
        except BaseException:
            cls.temp.cleanup()
            raise
        cls._refs_to_restore = {
            "refs/heads/main": cls.base_data["main_sha"],
            "refs/remotes/origin/draft/test-25": next(
                x["sha"] for x in cls.base_data["linear_prs"] if x["number"] == 25),
        }

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        # Tests mutate snapshot dictionaries while probing invalid states.
        # Reuse the expensive Git graph but deep-copy its in-memory manifest.
        # This prevents one test's mutation from poisoning subsequent cases.
        self.data = copy.deepcopy(self.base_data)
        # Some tests deliberately mutate disposable refs to prove that the
        # reviewer detects drift. Restore ONLY those synthetic fixture refs
        # before each test; never touch the user's repository or real refs.
        for ref_name, original_sha in self._refs_to_restore.items():
            git(self.root, "update-ref", ref_name, original_sha)

    def test_linear_chain_and_fork_reported_without_authorizing_merge(self):
        r = mod.verify(mod.validate_snapshot(self.data), self.root)
        self.assertEqual(r["status"], "PASS_LINEAR_63_DRAFT_PRS_PR53_UNRESOLVED")
        self.assertEqual(r["PRs_checked"], 63)
        self.assertFalse(r["merge_authorized"])

    def test_missing_middle_pr_blocks(self):
        self.data["linear_prs"].pop(32)
        self.assertEqual(len(self.base_data["linear_prs"]), 63)
        with self.assertRaises(mod.GateError):
            mod.validate_snapshot(self.data)

    def test_invalid_merge_authorization_blocks(self):
        self.data["merge_authorized"] = True
        self.assertFalse(self.base_data["merge_authorized"])
        with self.assertRaises(mod.GateError):
            mod.validate_snapshot(self.data)

    def test_remote_branch_sha_drift_blocks(self):
        git(self.root, "update-ref", "refs/remotes/origin/draft/test-25",
            self.data["main_sha"])
        with self.assertRaises(mod.GateError):
            mod.verify(mod.validate_snapshot(self.data), self.root)

    def test_main_drift_blocks(self):
        git(self.root, "commit", "-q", "--allow-empty", "-m", "drift-main")
        with self.assertRaises(mod.GateError):
            mod.verify(mod.validate_snapshot(self.data), self.root)

    def test_fork_auto_merge_not_accepted(self):
        self.data["divergent_prs"][0]["auto_merge"] = True
        self.assertFalse(self.base_data["divergent_prs"][0]["auto_merge"])
        with self.assertRaises(mod.GateError):
            mod.validate_snapshot(self.data)

    def test_duplicate_manifest_json_properties_block(self):
        f = self.root / "bad.json"
        f.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
        with self.assertRaises(mod.GateError):
            mod.read_snapshot(f)

    def test_main_ref_remains_unchanged_by_audit(self):
        before = git(self.root, "rev-parse", "main")
        mod.verify(mod.validate_snapshot(self.data), self.root)
        self.assertEqual(git(self.root, "rev-parse", "main"), before)

    def test_plan_only_does_not_need_local_git_queries(self):
        f = self.root / "data.json"
        f.write_text(json.dumps(self.data), encoding="utf-8")
        self.assertEqual(mod.main(["--manifest", str(f)]), 0)


if __name__ == "__main__":
    unittest.main()
