# Phase 9 — fail-closed test completeness for Nightglass

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Status: code committed on a new DRAFT branch. Current runtime result:
NOT TESTED on the user's Windows/Docker machine.**

Nightglass's offline test-runner machinery has grown alongside more than
40 unmerged stacked PRs. The project's user remains on Windows 10, plans
a **future** licensed Windows 11 Pro clean installation, and explicitly
does not want that installation or Fedora dual boot started now.

## Confirmed problems corrected

### 1. Broken Git-worktree regression test

`tests/test_offline_release_gate.py` asserted that the second Git
command must be `git worktree add`. That stopped being true when an
earlier phase added an essential fetched-SHA verification
`git rev-parse` **before** worktree creation. The old test would fail
even if the correct implementation refused unexpected commits.

The updated test checks that exactly one detached worktree command
appears, and that **fetch and SHA verification precede** the
worktree operation. It no longer relies on a fragile hard-coded call
index.

### 2. Required GUI/native suites could appear to pass when skipped

Python's standard unittest CLI returns exit code 0 when all cases
are skipped, or when a suite discovers zero cases. The previously
separate Fedora Qt-offscreen and native libvirt/QEMU checks were
requested by `--all`, but a missing/incorrectly skipped suite might
have yielded a misleading overall PASS.

New `scripts/run_required_suite.py` implements two narrow,
allowlisted suites:

- `--check gui` → `test_gui_smoke.py`, **at least 5 collected
  and executed**, **zero skipped cases**
- `--check native` → `test_native_tools.py`, same threshold,
  **zero skipped cases**

Both require execution from the disposable project checkout;
missing/symlinked test files, zero/incomplete discovery, failed
imports, expected failures, partial runs and skipped tests all BLOCK.

`scripts/verify_local.py --all` uses those strict checks in the
Fedora 43 container. It also fails if Linux Bash syntax validation
cannot run, rather than displaying NOT RUN while proceeding to
a final PASS.

### 3. Python version-matrix suite could pass with zero tests

The previous Python 3.11/3.12/3.13 Docker commands used generic
`python -m unittest discover -q`. A stale test pattern or
missing tests could return successful exit status after discovering
no cases.

New `scripts/run_headless_matrix.py` requires:

- At least **60 cases collected** from the full source tree
- At least **40 cases actually executed**, excluding skipped cases
- No import/discovery failures, failed test cases, unexpected
  successes or expected failures
- Exact equality between the collected count and reported test count

Platform/optional GUI/native tests may be **skipped in the Python slim
matrix** because those are independently required by the Fedora 43
test phase. Any skipped count is explicitly printed and cannot be
mistaken for equivalent Fedora hardware coverage.

Both runners are ordinary Python stdlib scripts, have no auto-download,
OS-install, Git merge, guest start or USB formatting operations, and
execute only on an expressly opted-in test path.

## Regression coverage

- `tests/test_required_integration_suites.py` mocks an empty,
  missing, partial, skipped, failed and successful required suite.
- `tests/test_headless_matrix_coverage.py` mocks under-collected,
  mostly-skipped, partially run and valid Python matrix results.
- Both are in the Windows-portable test allowlist.
- The updated worktree order test preserves the SHA pinning
  invariants rather than assuming obsolete Git call positions.

These are **new tests, not yet executed on Windows or in Fedora Docker**.
Do not infer a pass merely from the existence of test fixtures.

## How to use when owner elects local testing

From the user's existing Nightglass `main` checkout on Windows,
use the [preview-first launcher](WINDOWS_ONE_COMMAND_OFFLINE_CHECKS.md).
The relevant draft candidate is now:

`verification/test-gate-reliability-hardening`

Default launcher mode only previews, without Git/Docker operations.
The `-RunDockerGate` path requires the literal approval
`RUN NIGHTGLASS OFFLINE TESTS`; image downloads and Fedora image
builds require additional explicit switches.

The latest candidate still needs native PowerShell AST parsing,
Python matrix and Fedora Qt/native tests, exact-SHA local report
review, and ultimately real physical Fedora KDE KVM/SELinux/sVirt,
network-denial, cold recovery and restore-path verification.

## Protected deployment boundaries

The user-confirmed **example backup-drive capacity portable drive** is backup-only and never
a Windows/Fedora OS or bootable USB target. The separate **16 GB
USB** stays untouched, with actual ISO sizes/boot policy still to
be checked. The future Windows 11 Pro install can activate during
Microsoft setup or **later (default)**; the user-owned product key is
never written to this repository.

**No Windows or Fedora installation, debloat app removal, encryption
change, VM start, GitHub Actions dispatch, PR merge or force push is
part of this phase.**
