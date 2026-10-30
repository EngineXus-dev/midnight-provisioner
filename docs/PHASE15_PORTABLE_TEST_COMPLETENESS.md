# Phase 15 — Windows-portable test completeness

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Draft development branch. No system installation, hardware access, or merge.**

## Actual defect

The Midnight Provisioner Windows-only portable verification path in
`scripts/testing/verify_local.py` previously invoked `unittest discover`
for each allowlisted test module. Python unittest can exit **0**
when a pattern matches no cases or when every discovered case is
skipped. This could misrepresent missing or skipped regressions as
a successful Windows-portable suite.

The Python 3.11–3.13 Docker matrix and Fedora Qt/native suites
received similar hardening in Phase 9, but **this Windows-portable
per-file loop had remained unprotected**.

## Implementation

The portable loop now invokes:

```
python -B scripts/testing/run_portable_suite.py --pattern test_candidate_branch_contract.py
```

The named pattern is only an example; `verify_local.py` supplies
every entry from its existing `WINDOWS_PORTABLE_SUITES` allowlist.

The script refuses unexpected patterns, missing/symlinked test
files, an incorrect working directory, failed imports, zero tests
collected, all-skipped suites, incomplete test execution, ordinary
test failures, and expected-failure results. It requires at least
one **actually executed** passing test per allowlisted suite.

Some existing synthetic suites include optional platform-specific
test cases that legitimately skip under Windows. Partial skipping
remains allowed only when **at least one test really executed**,
and the number skipped is printed rather than counted as verified.

This is a *test completeness* check, not evidence that the
tests are effective security or hardware acceptance probes.

## Executed local evidence (not the full GitHub checkout)

An isolated disposable local Python test fixture of the new logic
was executed and gave:

- **7/7** dedicated regression tests PASS, including failing
  imports, zero discovery, all-skipped and incomplete execution
- A one-case permitted synthetic suite PASS
- An all-skipped fixture EXIT 1 (correctly blocked)
- An unknown pattern EXIT 2 (correctly blocked)

The actual new source and test logic was authored and exercised
locally before being committed to GitHub. The local fixture is
**not the entire Midnight Provisioner repository** and does not prove the
native Windows PowerShell parse, Docker images, GUI/native fixture
execution or physical Fedora host isolation.

## Updated candidate controls

Phase 15 tracks 48 predecessor draft PRs (#1–29, #31–49;
PR #30 absent) and uses the same candidate branch in the local
PR stack auditor, offline runner, evidence auditor, PowerShell
launcher and current operator guides.

The new `tests/test_portable_suite_coverage.py` also enters the
Windows-portable allowlist. The existing Phase 14 contract
continues enforcing branch/reference consistency.

## Outstanding holds

- Run the full Windows-portable suite on the user's native Windows
  checkout, confirming actual nonzero counts for *each* pattern.
- Run the current pinned SHA through Python 3.11/3.12/3.13
  isolated Docker checks and Fedora 43 Qt/native fixtures.
- Independently review private logs and v2 report integrity.
- Perform true Fedora KVM/SELinux/sVirt and backup restore testing
  later, only on approved hardware and non-destructive fixtures.

No GitHub Actions, PR merge, operating-system installation,
device/USB formatting, remote code signing or Windows Pro
activation has occurred. The example backup-drive capacity portable device remains
backup-only. Windows 11 Pro activation later is still the default.
