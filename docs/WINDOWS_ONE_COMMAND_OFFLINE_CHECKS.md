# Phase 8 — One-entry-point Windows offline verification

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**New draft, not executed on the user's computer.** The user continues
working from a Windows 10 Nightglass repository on `main`. This phase
adds an optional Windows PowerShell 5.1 launcher to reduce copy/paste
mistakes when checking the growing Nightglass PR stack. It does not
merge PRs, install Windows/Fedora, execute Win11 debloat tools, start
Kali/offline analysis guests or erase any device.

## Default behavior: PLAN ONLY

`scripts/Invoke-Nightglass-OfflineChecks.ps1` has these modes:

| Switch | Effect | Filesystem/network behavior |
| --- | --- | --- |
| *No switches* | Show planned actions | **No Git, Docker, file write or network call** |
| `-FetchRefs` | Fetch Nightglass `origin` refs | **Git metadata only**, source checkout not replaced |
| `-AuditStack` | Audit branch ancestry and manual-only CI policy | Reads existing refs; creates a **new temporary copy** of a pinned Python script |
| `-RunDockerGate` | Run six cumulative tests (native AST + rootless offline Docker) | **Requires exact consent**; creates detached sibling worktree and new log/JSON |
| `-PullPythonImages` | Allow Python slim Docker image downloads | Only combined with `-RunDockerGate` |
| `-BuildFedoraImage` | Allow Fedora test-image build/RPM downloads | Only combined with `-RunDockerGate` |
| `-ExpectedCommit` | Require exact candidate SHA40 | FAIL if the fetched branch differs |

The execution branch is
`verification/phase16-isolated-import-paths`. The PR stack
snapshot now includes **41 predecessor PRs** (#1–29 and #31–42).
PR #30 is absent. Those predecessor status observations are
historical and must be refreshed before integration.

If a release-candidate branch is updated after the user reviews it,
the runner rejects the mismatching `--expected-commit` **before
creating a test worktree**, then checks again before starting tests.
No older test results are quietly applied to the newer commit.

### Fetch and preview safely from current `main`

Run in native Windows PowerShell from the existing Nightglass checkout.
No existing source, ignored files, `.env`, `.venv` or untracked
files are overwritten by the following bootstrap:

```powershell
git fetch --no-tags origin
if ($LASTEXITCODE -ne 0) { throw "Fetch failed" }

$dir = Join-Path $env:TEMP ("Nightglass-Checks-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $dir -ErrorAction Stop | Out-Null
$launcher = Join-Path $dir "Invoke-Nightglass-OfflineChecks.ps1"

$lines = @(git show origin/verification/phase16-isolated-import-paths:scripts/Invoke-Nightglass-OfflineChecks.ps1)
if ($LASTEXITCODE -ne 0 -or $lines.Count -eq 0) { throw "Script retrieval failed" }
$lines | Set-Content -LiteralPath $launcher -Encoding UTF8

$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    $launcher, [ref]$tokens, [ref]$errors
) | Out-Null
if ($errors.Count -gt 0) {
    $errors | Format-Table
    throw "PowerShell syntax validation failed"
}

# Preview only: this last command performs no further Git or Docker work.
powershell.exe -NoProfile -NonInteractive -File $launcher
```

**Note:** the explicitly requested `git fetch` above updates
remote-tracking Git metadata and creates the new isolated temp
PowerShell file. The launcher itself is preview-only without switches.

### Audit already-fetched PR ancestry and CI triggers

```powershell
powershell.exe -NoProfile -NonInteractive -File $launcher -AuditStack -RepoPath (Get-Location).Path
```

The manifest and GitHub Actions YAML are read from the **exact
fetched candidate commit** and no draft branch is checked out.
It checks local ancestry, missing refs and basic manual trigger /
read-only token policy. A successful *local graph* check is
**not** approval to merge or proof that the GitHub PRs are currently
open drafts. Run `-FetchRefs` explicitly if additional remote refs
are required; missing refs otherwise remain blockers.

### Explicit cumulative Docker tests (NOT an installation)

Only when the owner is ready to run local tests:

```powershell
powershell.exe -NoProfile -NonInteractive -File $launcher -RunDockerGate -RepoPath (Get-Location).Path -ConfirmOfflineTests "RUN NIGHTGLASS OFFLINE TESTS"
```

Optional image preparation requires separate switches
`-PullPythonImages` and/or `-BuildFedoraImage`, which allow Docker
network use **during image preparation only**. Test containers retain
`--network none`, read-only mounts, unprivileged UID and sequential
memory-limited execution. Missing images without authorization are
reported BLOCKED, never PASS.

The launch script writes an entirely new temp copy of the Python test
runner, which fetches a new detached sibling worktree. The source
`main` tree and personal untracked files are not overwritten; Git
worktree metadata is added. Local test logs may contain machine paths
and should be reviewed privately before being uploaded anywhere.

The cumulative six-check runner performs Windows PowerShell AST
parse, Python AST parse-only, Python 3.11/3.12/3.13 synthetic Linux
Docker tests and Fedora 43 Qt offscreen/native QEMU/libvirt
fixtures. **The latest code has not yet been executed on the user's
Windows/Docker host.** A future PASS remains a synthetic-only result;
real Fedora KVM, sVirt labels, network isolation, guest recovery and
Windows 11 Pro clean-install acceptance remain independent blockers.

## Explicitly deferred

- No Windows 11 Pro ISO editing, clean install, OneDrive/Copilot removal
  or automatic device-encryption changes have been performed.
- The user may activate Windows 11 Pro **later** or during genuine
  setup. Nightglass does not collect or embed activation keys.
- The example backup-drive capacity portable drive remains BACKUP ONLY.
- The separate 16 GB USB stays untouched until a future independent
  media selection, ISO integrity and explicit user authorization.
- All Nightglass GitHub PRs remain **draft and unmerged**; neither this
  tool nor synthetic tests approve merge or deployment.

## Phase 9 — missing/skipped tests are blocking failures

The current candidate requires at least 60 collected / 40 executed
cases in each Python 3.11/3.12/3.13 container, plus five actually
executed cases with ZERO SKIPS for each Fedora Qt/native suite.
A regression assertion was corrected for the runner's legitimate
extra SHA verification before worktree creation.

The original checkout, GitHub Actions status and installation holds
remain unchanged. The new test paths are committed but NOT YET RUN.
See [Phase 9 completeness](OFFLINE_TEST_COMPLETENESS.md).

## Phase 12: backup-path regression integration

The newest branch `verification/phase16-isolated-import-paths` adds regression
tests for symlink-parent roots, manifest paths, report destinations,
parent-traversal inputs and simulated Windows reparse metadata.
The Windows launcher's default mode is still preview-only and the
exact-SHA candidate should be audited before running Docker tests.
No real Windows junction acceptance is claimed yet.

## Phase 15: safer Windows-portable verifier

For a native Windows `python scripts/verify_local.py` run,
every file in the portable allowlist now uses
`scripts/run_portable_suite.py` to reject zero-test and
all-skipped unittest results. It does not claim Fedora security
acceptance for skipped platform-specific cases. The new checker
was exercised in a 7-test isolated local fixture, **not**
the real Windows target environment. See
[Phase 15](PHASE15_PORTABLE_TEST_COMPLETENESS.md).
