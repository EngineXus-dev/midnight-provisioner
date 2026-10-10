#!/usr/bin/env python3
"""Offline Nightglass PR-stack integrity review. NEVER merges or rewrites Git refs.

PLAN: inspect a pinned local snapshot only.
VERIFY: read Git object/ref ancestry and original local main; no fetch,
checkout, merge, reset, clean, disk or OS operations. PR53 fork blocks a
complete-integration verdict until independently reconciled.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

SCHEMA = "nightglass.merge-integration-snapshot.v2"
REPOSITORY = "EngineXus-dev/nightglass-workspaces"
SHA = re.compile(r"^[0-9a-f]{40}$")
BRANCH = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,110}$")
ORIGIN = re.compile(r"^(?:https://github\.com/|git@github\.com:)enginexus-dev/nightglass-workspaces(?:\.git)?/?$", re.I)
MAX_MANIFEST_BYTES = 512 * 1024


class GateError(ValueError):
    pass


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GateError("Duplicate JSON property")
        result[key] = value
    return result


def sha(value):
    return isinstance(value, str) and bool(SHA.fullmatch(value))


def branch(value):
    return (isinstance(value, str) and bool(BRANCH.fullmatch(value))
            and ".." not in value and "//" not in value and not value.endswith(("/", ".", ".lock")))


def read_snapshot(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise GateError("Missing or oversized snapshot")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=no_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as e:
        raise GateError("Cannot parse snapshot safely") from e
    return validate_snapshot(data)


def validate_snapshot(d):
    if not isinstance(d, dict) or d.get("schema") != SCHEMA or d.get("repository") != REPOSITORY:
        raise GateError("Unexpected snapshot identity")
    if d.get("default_branch") != "main" or not sha(d.get("main_sha")):
        raise GateError("Main branch reference missing or invalid")
    if d.get("merge_authorized") is not False or d.get("deploy_authorized") is not False:
        raise GateError("Snapshot must NEVER be considered authorization")
    chain = d.get("linear_prs")
    if type(chain) is not list or len(chain) != 63 or d.get("linear_pr_count") != 63:
        raise GateError("Expected precisely 63 linear draft PRs")
    if d.get("open_pr_count") != 64:
        raise GateError("PR census drift: expected 64 with one explicit fork")
    seen_branches = set()
    seen_numbers = set()
    prev_name, prev_sha = "main", d["main_sha"]
    for p in chain:
        if not isinstance(p, dict) or not all(k in p for k in ("number", "branch", "sha", "base", "base_sha", "draft")):
            raise GateError("Malformed PR entry")
        n, name, head = p["number"], p["branch"], p["sha"]
        if type(n) is not int or n < 1 or n > 65 or n in (30, 53):
            raise GateError("Unexpected PR number")
        if n in seen_numbers or name in seen_branches or not branch(name) or not sha(head):
            raise GateError("Duplicate/malformed PR head")
        if p["draft"] is not True or p["base"] != prev_name or p["base_sha"] != prev_sha:
            raise GateError(f"Broken pinned stacked PR edge at #{n}")
        seen_numbers.add(n)
        seen_branches.add(name)
        prev_name, prev_sha = name, head
    required_nums = set(range(1, 66)) - {30, 53}
    if seen_numbers != required_nums or d.get("candidate_branch") != prev_name or d.get("candidate_sha") != prev_sha:
        raise GateError("Snapshot not a complete and exact anchored chain through #65")
    forks = d.get("divergent_prs")
    if (type(forks) is not list or len(forks) != 1 or not isinstance(forks[0], dict)
            or forks[0].get("number") != 53 or forks[0].get("auto_merge") is not False
            or forks[0].get("disposition") != "PENDING_INDEPENDENT_CONTENT_RECONCILIATION"):
        raise GateError("Unresolved PR53 fork MUST be explicit")
    fork = forks[0]
    if (not branch(fork.get("branch")) or not sha(fork.get("sha"))
            or not branch(fork.get("base")) or not sha(fork.get("base_sha"))
            or fork["branch"] in seen_branches):
        raise GateError("Invalid fork metadata")
    pr52 = next(p for p in chain if p["number"] == 52)
    if fork["base"] != pr52["branch"] or fork["base_sha"] != pr52["sha"]:
        raise GateError("PR53 must descend from PR52")
    return d


def git(root, *args, status_ok=(0,)):
    cmd = ["git", "-C", str(root), *args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=35, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GateError("Git read-only query unavailable") from e
    if p.returncode not in status_ok:
        raise GateError(f"Git metadata query failed (exit {p.returncode}, operation {args[0]})")
    return p.returncode, p.stdout.strip()


def ref(root, name):
    if not branch(name):
        raise GateError("Unsafe ref name")
    output = git(root, "rev-parse", "--verify", "refs/remotes/origin/" + name + "^{commit}")[1]
    if not sha(output):
        raise GateError("Invalid remote-tracking SHA")
    return output


def ancestor(root, older, newer):
    if not sha(older) or not sha(newer):
        raise GateError("Unsafe SHA")
    code, _ = git(root, "merge-base", "--is-ancestor", older, newer, status_ok=(0, 1))
    return code == 0


def verify(d, root):
    root = Path(root).expanduser().resolve(strict=True)
    toplevel = Path(git(root, "rev-parse", "--show-toplevel")[1]).resolve(strict=True)
    if toplevel != root:
        raise GateError("Run from exact Nightglass checkout root")
    origin = git(root, "remote", "get-url", "origin")[1]
    if not ORIGIN.fullmatch(origin):
        raise GateError("Refusing non-Nightglass origin")
    main_before = git(root, "rev-parse", "--verify", "refs/heads/main^{commit}")[1]
    if main_before != d["main_sha"] or ref(root, "main") != d["main_sha"]:
        raise GateError("Original main or origin/main drifted from pinned snapshot")
    refs = {"main": main_before}
    for p in d["linear_prs"]:
        remote = ref(root, p["branch"])
        if remote != p["sha"]:
            raise GateError(f"Remote-tracking head drifted for PR #{p['number']}")
        refs[p["branch"]] = remote
    fork = d["divergent_prs"][0]
    if ref(root, fork["branch"]) != fork["sha"]:
        raise GateError("PR53 fork SHA drifted")
    for p in d["linear_prs"]:
        if not ancestor(root, refs[p["base"]], p["sha"]):
            raise GateError(f"PR #{p['number']} cannot be fast-forwarded from declared parent")
    if not ancestor(root, main_before, d["candidate_sha"]):
        raise GateError("Cumulative candidate is NOT a direct descendant of main")
    if not ancestor(root, fork["base_sha"], fork["sha"]):
        raise GateError("PR53 fork does not descend from declared PR52")
    fork_included = ancestor(root, fork["sha"], d["candidate_sha"])
    if fork_included:
        raise GateError("PR53 fork unexpectedly integrated; snapshot must be reconciled")
    counts = git(root, "rev-list", "--left-right", "--count",
                 main_before + "..." + d["candidate_sha"])[1].split()
    if len(counts) != 2 or not all(x.isdecimal() for x in counts):
        raise GateError("Cannot evaluate cumulative commit reachability")
    behind, ahead = map(int, counts)
    if behind != 0 or ahead < len(d["linear_prs"]):
        raise GateError("Candidate behind main or missing cumulative history")
    if git(root, "rev-parse", "--verify", "refs/heads/main^{commit}")[1] != main_before:
        raise GateError("Main changed DURING audit")
    return {
        "schema": "nightglass.merge-local-audit.v2",
        "status": "PASS_LINEAR_63_DRAFT_PRS_PR53_UNRESOLVED",
        "linear_fast_forward_graph": True,
        "PRs_checked": len(d["linear_prs"]),
        "cumulative_commits_after_main": ahead,
        "main_sha": main_before,
        "candidate_sha": d["candidate_sha"],
        "pr53_integrated": False,
        "pr53_disposition": "HOLD_INDEPENDENT_RECONCILIATION",
        "live_GitHub_reviews_and_protection_verified": False,
        "physical_host_acceptance_verified": False,
        "merge_authorized": False,
        "deployment_authorized": False,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--repo", type=Path)
    ap.add_argument("--verify", action="store_true", help="Read local Git refs/objects only; NO fetch or merge")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        data = read_snapshot(args.manifest)
        if args.verify:
            if args.repo is None:
                raise GateError("--verify requires --repo")
            result = verify(data, args.repo)
        else:
            result = {
                "schema": "nightglass.merge-local-audit.v2",
                "status": "PLAN_ONLY_NO_GIT_OPERATIONS",
                "linear_prs_declared": len(data["linear_prs"]),
                "forked_pr": data["divergent_prs"][0]["number"],
                "candidate_sha": data["candidate_sha"],
                "merge_authorized": False,
                "deployment_authorized": False,
            }
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Nightglass merge-stack audit:", result["status"])
            for k, v in result.items():
                if k not in ("schema", "status"):
                    print(f"  {k}: {v}")
            print("No fetch, checkout, merge, disk change or OS operation performed by this audit.")
        return 0
    except (GateError, OSError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
