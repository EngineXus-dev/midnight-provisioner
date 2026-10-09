#!/usr/bin/env python3
"""Nightglass draft PR stack audit. Read-only, fail-closed; NEVER merges PRs.

PLAN default: no Git/network/filesystem operations.
--verify: read local Git refs and diff *paths* only, no fetch or worktree edits.
Reports only local ref ancestry and risks; never claims GitHub PR status,
test success, Fedora security acceptance, or authorization to merge.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SCHEMA = "nightglass.stack.audit.v1"
CANDIDATE = "verification/phase15-portable-suite-coverage"
EXPECTED_REPOSITORY = "EngineXus-dev/nightglass-workspaces"
REPO_URL = re.compile(
    r"^(?:https://github\.com/|git@github\.com:)"
    r"enginexus-dev/nightglass-workspaces(?:\.git)?/?$", re.I
)
SAFE_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
HEX_SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_MANIFEST_BYTES = 32 * 1024
MANIFEST_PATH = "config/nightglass-pr-stack-snapshot.json"
WORKFLOW_PATH = ".github/workflows/verify.yml"
MAX_WORKFLOW_BYTES = 32 * 1024
LAST_STACK_HEAD = "verification/phase14-release-gate-repair"


class StackError(ValueError):
    """Invalid chain, unavailable ref, or unsafe/unexpected repository."""


def valid_branch(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(SAFE_BRANCH.fullmatch(value))
        and ".." not in value
        and "//" not in value
        and not value.endswith(("/", ".", ".lock"))
        and not value.startswith("refs/")
        and "@{" not in value
    )


def validate_manifest(data: dict) -> list[dict]:
    if not isinstance(data, dict):
        raise StackError("Stack snapshot is not a JSON object")
    if data.get("schema") != SCHEMA or data.get("repository") != EXPECTED_REPOSITORY:
        raise StackError("Wrong Nightglass stack snapshot")
    if data.get("default_branch") != "main" or data.get("candidate_branch") != CANDIDATE:
        raise StackError("Unexpected default or candidate branch")
    prs = data.get("pull_requests")
    if not isinstance(prs, list) or len(prs) != 48:
        raise StackError("The snapshot must contain 48 observed draft PRs")
    if data.get("pr30") != "NOT_FOUND":
        raise StackError("PR #30 must not be invented")
    expected_numbers = list(range(1, 30)) + list(range(31, 50))
    if ([x.get("pr") if isinstance(x, dict) else None for x in prs]
            != expected_numbers or any(type(x.get("pr")) is not int for x in prs)): 
        raise StackError("Unexpected PR count, order, or IDs")
    prior = "main"
    seen = set()
    for pr in prs:
        head, base = pr.get("head"), pr.get("base")
        if not valid_branch(base) or not valid_branch(head):
            raise StackError("Invalid branch name in snapshot")
        if base != prior or head in seen or head in ("main", CANDIDATE) or head == base:
            raise StackError("PR dependency graph is non-linear or contains repeats")
        seen.add(head)
        prior = head
    if CANDIDATE in seen or prior != LAST_STACK_HEAD:
        raise StackError("Wrong terminal PR or candidate already in snapshot")
    return prs


def reject_duplicate_keys(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise StackError("Duplicate field in stack JSON")
        result[name] = value
    return result


def parse_manifest_bytes(contents: bytes) -> list[dict]:
    """Parse a small pinned Git blob, rejecting ambiguous JSON fields."""
    if not isinstance(contents, bytes) or not contents or len(contents) > MAX_MANIFEST_BYTES:
        raise StackError("Missing or oversized Git manifest content")
    try:
        data = json.loads(contents.decode("utf-8"),
                          object_pairs_hook=reject_duplicate_keys,
                          parse_constant=lambda _x: (_ for _ in ()).throw(
                              StackError("Non-finite JSON value rejected")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StackError("Cannot read valid stack JSON") from exc
    return validate_manifest(data)


def read_manifest_at_ref(root: Path, *, candidate_sha: str) -> list[dict]:
    """Read the candidate's MANIFEST GIT BLOB, not the original worktree.

    The user is on main: the manifest does NOT exist there yet. Fetching
    branches only updates remote-tracking Git metadata. The content here
    is accessed from one verified immutable SHA through a fixed path.
    """
    if not isinstance(candidate_sha, str) or not HEX_SHA.fullmatch(candidate_sha):
        raise StackError("Manifest Git object needs exact SHA40")
    contents = git(["show", candidate_sha + ":" + MANIFEST_PATH], root=root, raw=True)
    return parse_manifest_bytes(contents)


def git(args: list[str], *, root: Path, timeout: int = 30,
        raw: bool = False) -> str | bytes:
    cmd = ["git", "-C", str(root), *args]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, shell=False, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StackError("Local read-only Git inspection unavailable") from exc
    if result.returncode != 0:
        raise StackError("Required Git ref/ancestry operation failed")
    if raw:
        return result.stdout
    return result.stdout.decode("utf-8", errors="replace").strip()


def git_ref(root: Path, ref: str) -> str:
    sha = git(["show-ref", "--verify", "--hash", ref], root=root)
    if not isinstance(sha, str) or not HEX_SHA.fullmatch(sha):
        raise StackError("Missing or ambiguous local Git branch ref")
    return sha


def warn_path(path: str) -> str | None:
    parts = path.replace("\\", "/").split("/")
    leaf = parts[-1].lower()
    segments = [p.lower() for p in parts]
    if not path or path.startswith("/") or ".." in segments:
        return "UNSAFE_DIFF_PATH"
    if ".github" in segments and "workflows" in segments:
        return "GITHUB_WORKFLOW_REVIEW"
    if (leaf.startswith(".env") or leaf in ("id_rsa", "id_ed25519")
            or leaf.endswith((".pem", ".pfx", ".p12", ".key"))
            or "secret" in segments):
        return "POSSIBLE_SECRET_FILE_REVIEW"
    if leaf.endswith((".exe", ".msi", ".iso", ".dll", ".sys")):
        return "BINARY_ARTIFACT_REVIEW"
    if ("installer" in leaf or "setup" in leaf or "partition" in leaf
            or "bitlocker" in leaf):
        return "OS_DEPLOYMENT_PATH_REVIEW"
    return None



def review_manual_workflow(contents: bytes) -> dict:
    """Fail closed on obvious CI auto-triggers and excessive token permissions.

    Purposefully conservative structural check, NOT a full YAML parser,
    actions supply-chain audit, or GitHub execution authorization.
    """
    if not isinstance(contents, bytes) or not contents or len(contents) > MAX_WORKFLOW_BYTES:
        raise StackError("Missing or oversized GitHub Actions workflow")
    try:
        lines = contents.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise StackError("Workflow must have unambiguous UTF-8 encoding") from exc
    significant = [line.rstrip() for line in lines
                   if line.strip() and not line.lstrip().startswith("#")]
    events = [i for i, line in enumerate(significant) if line == "on:"]
    perms = [i for i, line in enumerate(significant) if line == "permissions:"]
    if len(events) != 1 or len(perms) != 1:
        raise StackError("Workflow event or token permission block is ambiguous")

    def block(index: int) -> list[str]:
        selected = []
        for line in significant[index + 1:]:
            if line and not line[0].isspace():
                break
            selected.append(line)
        return selected

    if block(events[0]) != ["  workflow_dispatch:"]:
        raise StackError("Only explicit workflow_dispatch may trigger GitHub Actions")
    if block(perms[0]) != ["  contents: read"]:
        raise StackError("Workflow token must have only contents: read permission")
    if any(re.search(r"(?<![A-Za-z0-9_-])(?:self-hosted|pull_request_target|"
                     r"workflow_run|repository_dispatch)(?![A-Za-z0-9_-])", line, re.I)
           for line in significant):
        raise StackError("Unsafe workflow trigger or runner token")
    if any(re.match(r"^\s+permissions:", line) for line in significant):
        raise StackError("Unexpected job-level token permissions")
    mutable_actions = [
        line.strip() for line in significant
        if re.match(r"^\s+-?\s*uses:\s*[^#\s]+@v[0-9]+\s*$", line)
    ]
    return {
        "trigger": "MANUAL_WORKFLOW_DISPATCH_ONLY",
        "token_permissions": "contents: read",
        "source_integrity": "LOCAL_GIT_OBJECT_NOT_SIGNED",
        "mutable_action_refs_need_review": mutable_actions,
    }

def verify(root: Path, *, manifest: list[dict],
           expected_sha: str | None = None) -> dict:
    """Local metadata only; no checkout, fetch, rebase or merge."""
    if expected_sha is not None and not HEX_SHA.fullmatch(expected_sha):
        raise StackError("Expected candidate SHA must be full lowercase hex40")
    root = Path(root).resolve()
    observed = Path(git(["rev-parse", "--show-toplevel"], root=root)).resolve()
    if observed != root:
        raise StackError("Run against the Nightglass repository root only")
    origin = git(["remote", "get-url", "origin"], root=root)
    if not REPO_URL.fullmatch(origin):
        raise StackError("Git origin is not the authorized Nightglass repository")
    original_head = git_ref(root, "refs/heads/main")
    remote_main = git_ref(root, "refs/remotes/origin/main")
    if remote_main != original_head:
        raise StackError("Local main SHA differs from origin/main; review manually")
    refs = {"main": original_head}
    for item in manifest:
        ref = "refs/remotes/origin/" + item["head"]
        refs[item["head"]] = git_ref(root, ref)
    refs[CANDIDATE] = git_ref(root, "refs/remotes/origin/" + CANDIDATE)
    if expected_sha is not None and refs[CANDIDATE] != expected_sha:
        raise StackError("Candidate branch SHA mismatches independently expected SHA")
    errors = []
    for item in manifest:
        parent, child = item["base"], item["head"]
        out = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor",
             refs[parent], refs[child]],
            capture_output=True, timeout=30, check=False, shell=False,
        )
        if out.returncode != 0:
            errors.append("PR #%d is NOT a verified descendant of its base" % item["pr"])
    out = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor",
         refs[manifest[-1]["head"]], refs[CANDIDATE]],
        capture_output=True, timeout=30, check=False, shell=False,
    )
    if out.returncode != 0:
        errors.append("Latest candidate is not a descendant of the final draft PR")
    # Three-dot symmetric history: local main-only commits are blockers.
    deltas = git(["rev-list", "--left-right", "--count",
                  refs["main"] + "..." + refs[CANDIDATE]], root=root).split()
    if len(deltas) != 2 or not all(x.isdigit() for x in deltas):
        raise StackError("Cannot interpret main/candidate divergence")
    behind, ahead = [int(x) for x in deltas]
    if behind:
        errors.append("Candidate is behind main: main-only commits exist")
    if ahead <= 0:
        errors.append("Candidate contains no new commits beyond main")
    paths = git(["diff", "--no-ext-diff", "--name-only", "-z",
                 refs["main"] + "..." + refs[CANDIDATE]], root=root, raw=True)
    if not isinstance(paths, bytes):
        raise StackError("Diff path listing was not binary-safe")
    try:
        names = [x.decode("utf-8", errors="strict")
                 for x in paths.split(b"\0") if x]
    except UnicodeDecodeError as exc:
        raise StackError("Non-UTF8 changed path requires independent review") from exc
    alerts = [{"category": warn_path(name), "path": name}
              for name in names if warn_path(name) is not None]
    # Inspect the CI policy from the EXACT candidate Git object, not
    # a possibly stale .github file in the user's main checkout.
    workflow = git(["show", refs[CANDIDATE] + ":" + WORKFLOW_PATH],
                   root=root, raw=True)
    workflow_review = review_manual_workflow(workflow)
    for action in workflow_review["mutable_action_refs_need_review"]:
        alerts.append({"category": "MUTABLE_ACTION_REF_REVIEW",
                       "path": WORKFLOW_PATH, "detail": action})
    end = git_ref(root, "refs/heads/main")
    if end != original_head:
        errors.append("Main ref changed during inspection")
    return {
        "schema": SCHEMA,
        "inspection": "LOCAL_GIT_REFS_ONLY_NO_FETCH",
        "candidate_branch": CANDIDATE,
        "candidate_sha": refs[CANDIDATE],
        "main_sha": original_head,
        "observed_pr_count": len(manifest),
        "manifest_source": "PINNED_CANDIDATE_GIT_BLOB_NOT_WORKTREE",
        "missing_pr_30": True,
        "main_only_commits": behind,
        "candidate_only_commits": ahead,
        "changed_path_count": len(names),
        "review_flags": alerts,
        "workflow_policy_review": workflow_review,
        "structure_pass": not errors,
        "blockers": errors,
        "github_live_pr_status_verified": False,
        "local_remote_ref_freshness_verified": False,
        "cumulative_tests_verified": False,
        "hardware_fedora_acceptance_verified": False,
        "deployment_approved": False,
        "merge_authorized": False,
        "next_step": "Review all PRs, workflow changes and cumulative exact-SHA test evidence before a separate user-approved integration.",
    }


def create_report(path: Path, data: dict) -> None:
    """Create NEW report only, never overwrite a file/symlink."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nightglass draft PR stack local-readiness check")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--verify", action="store_true",
                        help="Read existing LOCAL Git refs; never fetch, merge or checkout")
    parser.add_argument("--expected-candidate-sha",
                        help="Optional expected full SHA independently copied from GitHub PR")
    parser.add_argument("--report", type=Path, help="NEW JSON path (exclusive create)")
    args = parser.parse_args(argv)
    if not args.verify:
        if args.report or args.expected_candidate_sha:
            parser.error("--report and --expected-candidate-sha require --verify")
        print("NIGHTGLASS STACK AUDIT — PLAN ONLY")
        print("48 observed unmerged draft PRs: #1–29, #31–49; #30 not found.")
        print("No Git, network, Docker, OS, filesystem or installer activity.")
        print("Use --verify to inspect already-fetched LOCAL Git refs and the candidate Git blob only.")
        print("Even a successful chain audit NEVER authorizes PR merge or deployment.")
        return 0
    try:
        root = args.repo.resolve()
        candidate_sha = git_ref(root, "refs/remotes/origin/" + CANDIDATE)
        if (args.expected_candidate_sha is not None
                and candidate_sha != args.expected_candidate_sha):
            raise StackError("Expected candidate SHA differs from remote-tracking ref")
        manifest = read_manifest_at_ref(root, candidate_sha=candidate_sha)
        result = verify(root, manifest=manifest,
                        expected_sha=candidate_sha)
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.report:
            create_report(args.report, result)
        if result["blockers"]:
            print("BLOCKED: branch stack is not verified linear.", file=sys.stderr)
            return 1
        print("LOCAL GRAPH ONLY: passed, but LIVE GitHub status, test evidence and merge approval remain PENDING.")
        return 0
    except (OSError, StackError) as exc:
        print("BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
