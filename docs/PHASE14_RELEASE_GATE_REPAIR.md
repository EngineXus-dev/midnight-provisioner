# Phase 14 — Candidate branch repair and local fixture verification

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Draft only. No merges, Windows/Fedora installation or media writes.**

## Root cause and actual fix

The Phase 13 cross-root backup safety pull request (#48) had new
backup code but its cumulative offline release runner, independent
evidence auditor, PR ancestry checker, PowerShell launcher and older
test expectations still referenced the Phase 12 candidate branch.
A subsequent test could therefore have verified the wrong commit.
The predecessor snapshot also stopped before #48.

On branch `verification/phase14-release-gate-repair`, the active
candidate is the same across:

- `config/midnight-provisioner-pr-stack-snapshot.json` (47 predecessors:
  PRs #1–29 and #31–48, PR #30 absent)
- `scripts/release/Audit-Midnight-Provisioner-PR-Stack.py`
- `scripts/release/Audit-Midnight-Provisioner-Release-Evidence.py`
- `scripts/testing/Run-Midnight-Provisioner-Offline-Release-Gate.py`
- `scripts/testing/Invoke-Midnight-Provisioner-OfflineChecks.ps1`
- `tests/test_pr_stack_audit.py` and
  `tests/test_offline_release_gate.py`
- The current Windows launch, cumulative gate, and evidence runbooks

An existing `test_offline_release_gate.py` line also had a real
syntax error: a missing closing parenthesis in its branch assertion.
This was corrected.

## Permanent prevention

`tests/test_candidate_branch_contract.py` adds **8 tests** which
check that all Python candidate constants and the PowerShell
launcher match the exact manifest candidate, that the chain is
linear/uniquely numbered with missing PR #30 represented accurately,
and that current operator runbooks reference the same branch.
It also deliberately exercises malformed manifests and stale
branch values.

The contract suite is in the Windows-portable offline test allowlist,
so a future run catches another mismatch instead of accepting
stale-commit reports.

## What was really tested here

In the isolated model-side Python 3.13 container, an exact local
copy of the authored contract test was run against a disposable
fixture with mock candidate source files, manifest, launcher and
runbook text. No user files or real OS paths were inspected.

**Fixture results:**
- Normal consistent manifest and branch fixture: **8/8 tests pass**
- Deliberately altered PowerShell launcher pointing at an old branch:
  **test fails (exit code 1)** and names the wrong launcher branch

This is a real exercise of the contract test logic, but **not**
the native Windows, exact-GitHub-checkout or Docker release suite.
GitHub source-level checks separately confirmed the updated manifest,
candidate constants, predecessor numbering and operator runbook
references. A lightweight bracket/string-balance scan of the
affected Python source found no further apparent imbalance; that is
not a Python AST or runtime test.

## Next mandatory verification

Run the currently pinned candidate SHA on the owner's native Windows
workstation using `docs/WINDOWS_ONE_COMMAND_OFFLINE_CHECKS.md`.
The runner defaults to PLAN ONLY and only conducts the Docker
tests with explicit opt-in. Missing Docker images remain BLOCKED
unless their download/build is separately approved.

Require real native PowerShell AST parsing; Python syntax and
3.11/3.12/3.13 executed-test minimums; Fedora 43 Qt/native
non-skipped synthetic suites; a private full local log and
v2 SHA-pinned status report; and a separate human review of the
unchanged `main` ref. Never equate a synthetic PASS with
physical Fedora SELinux/KVM/sVirt isolation, VM recovery or
full portable-backup restoration.

The user's Windows 11 Pro installation/activation, separate
16 GB installer USB and example backup-drive capacity backup-only portable drive remain
untouched. All GitHub PRs remain draft and unmerged.
