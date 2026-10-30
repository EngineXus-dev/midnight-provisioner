# Phase 17 — Exact Windows QEMU/SELinux test inventory

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Draft only. No merges, hardware activity or VM launches.**

## Confirmed risk

`scripts/testing/verify_local.py` previously invoked the Windows-safe
`test_kali_process_label.py` subset with one `unittest -k`
argument for each selected method name. Unittest may return success
when one of those names no longer exists, provided other matching
tests still pass. Phase 15 had hardened each *file-level* portable
suite, but **the Windows QEMU method-level subset was still open
to a silent regression omission**.

At this commit, 14 method names are intentionally listed in
`WINDOWS_QEMU_CASES` out of the 15 methods in the original
synthetic process-label test file. The remaining provenance
report test is not newly added to the Windows subset; changing
that scope must be a separate decision.

## Repair

The Windows QEMU section now invokes
`python -B scripts/testing/run_windows_qemu_subset.py` rather than raw
unittest `-k` filters. The new stdlib runner:

- accepts only the fixed `test_kali_process_label.py` module and
  the preexisting `WINDOWS_QEMU_CASES` exact-name allowlist
- requires every named test method to be discovered **exactly once**
- fails closed on missing modules, import errors, duplicate or
  missing expected method names and incorrect working directories
- executes only the selected synthetic tests and requires all of
  them to pass with **zero skips or expected failures**
- reports how many named cases actually executed, rather than
  treating a nonempty partial subset as full coverage
- never starts a guest, calls `virsh`, accesses Docker, fetches Git
  references or changes Windows/SELinux configuration

The intentional omitted test still remains unexecuted by this
Windows-only subset; this is clearly not Fedora host acceptance.

## Executed evidence

The **exact source and regression test files committed to GitHub**
were first authored and executed in an isolated local Python
environment. Their Git object SHA values were then compared to
the fetched GitHub source and both **match exactly**:

- `scripts/testing/run_windows_qemu_subset.py`
  SHA: `d20e74b09d6c01cc6e1b18d44fbcb9ec1ba3efa0`
- `tests/test_windows_qemu_subset_integrity.py`
  SHA: `ba9f8a9c6991a8a364848aa7c75f5ecccc97e235`

Running the exact seven regression tests locally produced
**Ran 7 tests — OK** (Python unittest). Additional isolated
direct runs gave:

- 3/3 selected synthetic test cases executed: exit 0
- One selected test renamed or missing: exit 1
- One selected test marked skipped: exit 1
- Duplicate selected name, import failure, missing module and
  deliberate excluded test coverage are exercised by the seven
  regression cases

**This is a test of the committed runner in a disposable project,
not a run of the full Midnight Provisioner checkout, the user's native
Windows 10 test suite, or Fedora 43/libvirt infrastructure.**
This evidence cannot prove physical sVirt network isolation.

## Integration controls

The candidate is
`verification/phase17-qemu-subset-integrity`.
Its explicit manifest tracks **50 predecessor draft PRs**
(#1–29, #31–51; PR #30 absent). The cumulative offline
test runner, SHA report auditor, PR ancestry inspector,
PowerShell launcher and current runbooks are all being kept
on that same candidate.

Still required before considering integration:
run the actual exact-SHA Windows-portable checks, the complete
isolated Python 3.11/3.12/3.13 and Fedora 43 test matrix, review
local evidence against the commit, and independently verify
real Fedora hardware security and recovery later.

The original Windows 10 installation, Windows 11 Pro clean-install
plan (activate later default), 16 GB installation USB and example backup-drive capacity
backup-only external drive remain untouched. No GitHub Actions,
PR merge, partition/format or guest launch was performed.
