# HISTORICAL PR53 TRIAGE — SUPERSEDED BRANCH

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

This document is preserved from PR #53 for audit/history only. Its candidate branch, test status and runtime suggestions must NOT override the cumulative integration candidate. See `docs/PR53_DIVERGENT_BRANCH_RECONCILIATION.md`.

---

# Phase 18 — Native Windows test triage after PR #52

**Draft repair, not a new verified release candidate.**

## Input evidence

The owner ran the full Windows-portable test stage on native
Windows 10 with Python 3.12, against pinned PR #52 commit
`dc1e173b9f9dd577d2ccc416072510f538c89c2e`.
The verification launcher successfully fetched the immutable
candidate and created a detached sibling worktree; the
Windows-portable test stage returned **exit 1** and the
Docker/Fedora stage was correctly **not started**.

Five suites failed:

- `test_windows_dualboot_review.py`
- `test_pr_stack_audit.py`
- `test_backup_integrity_preflight.py`
- `test_backup_set_preflight.py`
- The explicitly selected 14-case synthetic Kali process-label subset

Only the **last 120 lines of stderr** were supplied. Those lines
contained 14 identical errors from `test_kali_process_label.py`
setup, all at `os.fchmod()`, which is not provided by Windows Python.
The complete failure details for the other four suites were **not
included**, so they are unresolved pending an earlier/full excerpt.

## Source defects confirmed independently

1. **Synthetic QEMU/SELinux tests require a POSIX permission syscall**
   even on Windows, before they reach their label parsing.
   The Windows-only fabricated-fixture setup now scopes a mock
   `os.fchmod` to the current unittest case and registers its cleanup.
   This also covers generated fake report cases. The **production**
   `nightglass/kali_setup.py` and `nightglass/acceptance.py` remain
   unchanged, as do Fedora/Linux permission checks.

2. **Windows OS-disk exclusion test asserted nonexistent text.**
   `test_windows_dualboot_review.py` had demanded the literal
   `DiskNumber -eq $osPartition.DiskNumber`; the inspected script
   safely excludes the Windows disk using
   `if ($disk.Number -eq $osPartition.DiskNumber) { continue }`.
   The assertion now covers the actual guard, without touching the
   PowerShell disk-review code or any partition.

3. **Local PR-stack audit missed `secrets/` directories.**
   `warn_path("secrets/accounts.json")` was supposed to flag a
   possible secret but matched only a path segment named
   `secret` (singular). The scanner now checks both singular
   and plural segments; this **strengthens** the review gate
   and aligns it with the existing test expectation.

These changes were made on reversible branch
`verification/phase18-windows-failures` based on PR #52, with
no edits to `main`.

## What has NOT been verified

- The full native Windows stage has not been rerun against this fix.
- The exact traceback for the two backup-integrity suites was not
  provided; no speculative change was made to source backup
  protections or path/identity rules.
- Whether the dual-boot suite also has a genuine PowerShell parser
  failure is still unknown from the truncated log.
- Whether the PR-stack audit has more than the confirmed plural
  secret-folder classification failure is also unknown.
- Docker Linux/Fedora, isolated native QEMU/libvirt and actual
  KVM/sVirt hardware acceptance remain pending.

## Retrieve remaining failures without rerunning tests

Locate the private prior Windows verification session's
`windows-portable-tests.stderr.txt`. View the failures
**locally**, rather than uploading the full log with personal paths
and incidental environment data:

```powershell
$session = 'REPLACE_WITH_PRIOR_NIGHTGLASS_TEMP_SESSION_PATH'
$log = Join-Path $session 'windows-portable-tests.stderr.txt'
Get-Content -LiteralPath $log |
    Select-String '^(FAIL|ERROR):|^(AssertionError|AttributeError|TypeError|ValueError|OSError|KeyError|ImportError|BackupError|StackError):|^Ran [0-9]+ tests|^FAILED \(' |
    Select-Object -First 100
```

Inspect and redact accidental secrets or private paths before
sharing even these selected lines. Full traceback context may be
needed for any unresolved case.

## Safety holds

No GitHub Actions, PR merges, resets, force pushes, Windows 11 Pro
installation/activation, Fedora dual-boot setup, USB formatting,
VM launch, or writes to the external example backup-drive capacity backup-only drive.
The future Windows 11 Pro default remains **activate later**.
