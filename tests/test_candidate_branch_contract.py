"""Fail-closed contract: every offline verifier must target the same Git SHA branch.

Pure stdlib, file reads only, no subprocess/Git/Docker/Windows operations.
Prevents cumulative test reports being attributed to an earlier branch.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "nightglass-pr-stack-snapshot.json"
SOURCES = (
    ("scripts/testing/Run-Nightglass-Offline-Release-Gate.py", "BRANCH"),
    ("scripts/release/Audit-Nightglass-Release-Evidence.py", "BRANCH"),
    ("scripts/release/Audit-Nightglass-PR-Stack.py", "CANDIDATE"),
)


def constant_string(filename: Path, name: str) -> str:
    source = filename.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(filename))
    matches = []
    for node in tree.body:
        if (isinstance(node, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == name
                    for t in node.targets)):
            if isinstance(node.value, ast.Constant) and type(node.value.value) is str:
                matches.append(node.value.value)
            else:
                raise ValueError("Expected a literal string branch constant")
    if len(matches) != 1:
        raise ValueError("Expected exactly one literal branch constant")
    return matches[0]


def pr_chain_is_linear(manifest: dict) -> bool:
    items = manifest["pull_requests"]
    if (not isinstance(items, list) or not items
            or manifest.get("pr30") != "NOT_FOUND"):
        return False
    ids = [i for i in range(1, 30)] + [
        i for i in range(31, 31 + (len(items) - 29))
    ]
    if (any(not isinstance(x, dict) for x in items)
            or [x.get("pr") for x in items] != ids
            or any(type(x["pr"]) is not int for x in items)):
        return False
    prior = "main"
    known = {"main"}
    for item in items:
        head = item.get("head")
        if (item.get("base") != prior or
                not isinstance(head, str) or not head or
                head in known):
            return False
        known.add(head)
        prior = head
    candidate = manifest.get("candidate_branch")
    return isinstance(candidate, str) and bool(candidate) and candidate not in known


class CandidateBranchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.branch = cls.manifest["candidate_branch"]

    def test_manifest_chain_has_no_missing_or_duplicated_predecessors(self):
        self.assertTrue(pr_chain_is_linear(self.manifest))
        self.assertEqual(self.manifest["repository"],
                         "EngineXus-dev/nightglass-workspaces")
        self.assertEqual(self.manifest["default_branch"], "main")

    def test_python_gate_and_evidence_candidates_match_manifest(self):
        for filename, constant in SOURCES:
            with self.subTest(filename=filename):
                self.assertEqual(constant_string(ROOT / filename, constant),
                                 self.branch)

    def test_powershell_launcher_targets_same_candidate(self):
        code = (ROOT / "scripts" / "testing" / "Invoke-Nightglass-OfflineChecks.ps1").read_text(
            encoding="utf-8")
        matches = re.findall(r"(?m)^\$branch\s*=\s*'([^']+)'\s*$", code)
        self.assertEqual(matches, [self.branch])

    def test_stack_auditor_last_head_matches_snapshot(self):
        target = ROOT / "scripts" / "release" / "Audit-Nightglass-PR-Stack.py"
        self.assertEqual(constant_string(target, "LAST_STACK_HEAD"),
                         self.manifest["pull_requests"][-1]["head"])

    def test_current_operator_runbooks_point_at_same_candidate(self):
        for path in (
            "docs/OFFLINE_RELEASE_CANDIDATE_GATE.md",
            "docs/RELEASE_EVIDENCE_AUDIT.md",
            "docs/WINDOWS_ONE_COMMAND_OFFLINE_CHECKS.md",
        ):
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn(self.branch, text)

    def test_synthetic_old_branch_drift_is_rejected_by_contract(self):
        self.assertFalse(pr_chain_is_linear({
            **self.manifest,
            "candidate_branch": self.manifest["pull_requests"][-1]["head"],
        }))
        for filename, key in SOURCES:
            value = constant_string(ROOT / filename, key)
            self.assertNotEqual(value, "main")

    def test_corrupted_manifest_graph_returns_false_not_exception(self):
        for mutation in (
            lambda m: m["pull_requests"].__setitem__(3, False),
            lambda m: m["pull_requests"][4].update({"pr": True}),
            lambda m: m["pull_requests"][2].update({"head": "main"}),
            lambda m: m.update({"candidate_branch": False}),
            lambda m: m["pull_requests"][3].update({"base": "main"}),
        ):
            with self.subTest(mutation=mutation):
                sample = json.loads(json.dumps(self.manifest))
                mutation(sample)
                self.assertFalse(pr_chain_is_linear(sample))

    def test_every_ancestor_pr_number_is_unique_and_strict_integer(self):
        values = [x["pr"] for x in self.manifest["pull_requests"]]
        self.assertTrue(all(type(x) is int for x in values))
        self.assertEqual(len(values), len(set(values)))
        self.assertNotIn(30, values)


if __name__ == "__main__":
    unittest.main()
