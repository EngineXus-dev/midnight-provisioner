# Phase 5 — local release evidence integrity and integration hold

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Status: DRAFT / NO RELEASE.** All previous Nightglass PRs remain
unmerged. The user has explicitly deferred the Windows 11 Pro clean
installation, 16 GB USB writing and Fedora dual boot. The user's
separate example backup-drive capacity portable drive is backup-only, never a target disk.

## What this phase addresses

Before integrating the stacked PRs, we need one **fresh cumulative test**
against the exact latest Git commit. The earlier Python compatibility
and Fedora Docker passes are meaningful but cover **older SHA values**.

A new test report format (v2) binds the latest local synthetic results
to the candidate Git SHA and retains evidence that the original
main ref was unchanged at the start and end. Its separate, completed
local test transcript is hashed with SHA-256. The report itself is a
local JSON file with no digital signature; this is consistency
evidence, **NOT independent cryptographic attestation** and not proof
against an adversary who can modify the entire report and log together.

## Cumulative gate

`scripts/Run-Nightglass-Offline-Release-Gate.py` defaults to PLAN
ONLY and has no host/system effects. An explicitly authorized
`--run` creates a new sibling detached Git worktree from the single
`verification/phase17-qemu-subset-integrity` branch and writes new,
non-overwriting private log/JSON files outside the original
checkout. The branch-specific scripts and tests are parsed on the
Windows host; actual downloaded branch Python tests execute **only
inside non-root, no-network Docker**.

It requires every one of these stages to PASS:
1. Windows PowerShell AST parse-only on native Windows.
2. Python AST parse-only, without importing candidate modules.
3. Python 3.11 synthetic Linux Docker suite.
4. Python 3.12 synthetic Linux Docker suite.
5. Python 3.13 synthetic Linux Docker suite.
6. Fedora 43 full Qt offscreen/native QEMU/libvirt fixture suite.

Docker environments enforce `--network none`, read-only source,
no privileges/capabilities or KVM device, and run sequentially.
Image downloading and Fedora test-image building must be explicitly
enabled if images are not cached. Docker verification does not prove
hardware security isolation.

The v2 JSON contains `original_main_before`,
`original_main_after`, `tested_commit`, six check statuses,
`local_log_sha256`, and explicit
`deployment_approved=false`, `release_attested=false`.
A missing/changed main SHA prevents synthetic PASS. It does NOT
automatically merge, reset, clean, tag, release or deploy anything.

## Independent consistency review

`scripts/Audit-Nightglass-Release-Evidence.py` is read-only and
requires three inputs from a completed `--run`:

- `--report`: the *new* status-only JSON (not an older v1 report).
- `--log`: the matching full local test log, used only for SHA-256
  comparison. The auditor does not copy/publish its contents.
- `--expected-commit`: exact Git SHA independently confirmed by
  the user from the intended PR, not automatically trusted from the
  report. It must be 40 lowercase hexadecimal characters.

The auditor rejects duplicate JSON fields, oversized files, symlinks,
invalid or missing stages, non-PASS stages, unexpected "hardware
approved" claims, absent log/digest, report-log mismatch and
different observed main SHAs. A green audit means only that the
reported synthetic result and log digest are internally consistent.
It cannot prove the tests honestly executed: the local evidence is
unauthenticated and the runner and its host can be compromised.

### Example on the Windows workstation (no data loss)

From the existing Nightglass Git checkout in Windows PowerShell,
the commands below fetch just this feature branch and create two
**new temp files** outside the original checkout:

    git fetch --no-tags origin verification/phase17-qemu-subset-integrity
    if ($LASTEXITCODE -ne 0) { throw "Fetch failed" }

    $tmp = Join-Path $env:TEMP ("Nightglass-RC-Audit-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null

    $runner = Join-Path $tmp "Run-Nightglass-Offline-Release-Gate.py"
    $audit = Join-Path $tmp "Audit-Nightglass-Release-Evidence.py"

    git show origin/verification/phase17-qemu-subset-integrity:scripts/Run-Nightglass-Offline-Release-Gate.py |
        Set-Content -LiteralPath $runner -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw "Failed to retrieve runner" }

    git show origin/verification/phase17-qemu-subset-integrity:scripts/Audit-Nightglass-Release-Evidence.py |
        Set-Content -LiteralPath $audit -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw "Failed to retrieve auditor" }

    # Safe preview: no further Git/Docker/file writes.
    python $runner --repo (Get-Location).Path

If the user later opts into local testing:

    python $runner --repo (Get-Location).Path --run

Previously cached test images are used without downloading.
Missing images return BLOCKED; only optional flags allow isolated
Docker pull or Fedora image build. The runner prints the resulting
new report and log locations. Never infer a passed test from a
missing, timed-out or blocked stage.

After completion, validate the private evidence (replace placeholders
only with the actual displayed report and log paths):

    $expected = git rev-parse refs/remotes/origin/verification/phase17-qemu-subset-integrity
    if ($LASTEXITCODE -ne 0) { throw "Could not verify commit" }

    python $audit --report "C:\path\to\new-summary.json" --log "C:\path\to\matching-local-log.txt" --expected-commit $expected

**Important:** If the remote branch advanced since the test, expected
SHA will disagree and the audit will block. That is intentional; run
the entire suite again against the new code rather than silently
declaring stale results valid.

Do not upload the full raw log without checking for local paths or
secrets. The audit does not need private Windows product keys, ISO
files, a bootable USB, admin privileges or a Fedora installation.

## Mandatory next milestones after a synthetic PASS

- Independently review all stacked PR diffs and dependency order.
- Verify no unwanted edits to current Windows, portable backup drive
  or original repository files.
- Run native Fedora KDE KVM/SELinux/sVirt, offline guest network-denial,
  benign VM startup and cold recovery acceptance **when installed**.
- Verify Windows 11 Pro setup, licence/activate-later, ISO publisher
  provenance, full backup recovery and physical USB target only
  **when the user explicitly authorizes that future deployment**.
- Explicitly approve PR integration separately; no automatic merge,
  force-push, GitHub Actions or installer operation here.

The local report/audit is an engineering gate, not permission to run
malware, start high-risk VMs or declare system security certified.

## Phase 9 — strict executed test counts

The newest local gate refuses zero-test Python matrix results and
skipped Fedora Qt/native suites. The v2 local evidence report remains
unauthenticated and cannot prove physical SELinux/KVM or guest
network isolation. This exact branch still needs runtime verification.
See [test completeness](OFFLINE_TEST_COMPLETENESS.md).
