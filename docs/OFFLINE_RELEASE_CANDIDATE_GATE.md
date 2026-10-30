# Midnight Provisioner — offline cumulative integration release gate

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Status: IMPLEMENTED ON A DRAFT BRANCH; LATEST-RUN RESULTS PENDING.**
This is source/test readiness only, not permission to install Windows,
Fedora, a guest VM, a modified ISO or a USB bootloader.

## Purpose

Midnight Provisioner has many unmerged stacked draft PRs and no remaining
hosted GitHub Actions minutes. Earlier successful Fedora 43 Docker
and Python 3.11/3.12/3.13 tests apply to older Git commits.
The new offline release gate checks the **entire latest cumulative**
verification/phase17-qemu-subset-integrity branch without overwriting
the user's original Windows checkout or consuming GitHub Actions.

Six mandatory checks must all pass:

| Check | Execution | Meaning |
| --- | --- | --- |
| windows_powershell_ast | Native Windows PowerShell **parse only** | Every PowerShell file under scripts parses |
| python_source_ast | Native Python **parse only** | Python source syntax valid, without running fetched Python |
| python_311 | Python 3.11 slim Docker | Headless synthetic tests passed, with skips disclosed |
| python_312 | Python 3.12 slim Docker | Headless synthetic tests passed, with skips disclosed |
| python_313 | Python 3.13 slim Docker | Headless synthetic tests passed, with skips disclosed |
| fedora_43 | Fedora 43 Docker | Full synthetic suite, actual Qt offscreen and QEMU/libvirt fixture checks |

A FAIL, BLOCKED or NOT_RUN in ANY check means the overall test gate
is not passed. No synthetic/container PASS ever proves real Fedora
KVM, SELinux/sVirt labels, network packet isolation, disk recovery
or Windows 11 Pro functionality.

## Non-destructive execution model

The new runner defaults to PLAN ONLY: no Git fetch, Docker, file write,
tests, host change or network connection. Explicit --run verifies
the authorized GitHub origin, fetches only one named feature branch
(Git metadata changes in the original repo), creates a completely
NEW detached sibling worktree, writes a new unique private log and
JSON summary, and never changes main, tracked/untracked user files,
.env, .venv, datasets, VMs, boot settings, partitions or USB drives.

PowerShell and Python fetched from Git are ONLY parsed on Windows.
Actual fetched unit tests are executed in ROOTLESS, OFFLINE Docker:
network=none, read-only root + source, UID 10001, no capabilities,
no-privileges, no /dev/kvm or Docker socket, 512 MiB ephemeral tmpfs.
Python images have a 1 GiB memory cap; Fedora has a 2 GiB cap.
All containers run SEQUENTIALLY on this approximately 8 GB laptop.
Image pulls or the Fedora test-image build are disabled unless
separately requested. The Docker image build context contains ONLY
the Containerfile (not private files or repo secrets).

The runner has no Git merge, rebase, reset, clean, force-push,
GitHub Actions invocation, Windows Setup, ISO customizer,
Win11Debloat ApplyCore, Fedora installer or VM boot logic.
The detached worktree and logs are retained after tests rather
than force-removed automatically.

## Preview the plan on Windows (no test execution)

From the user's original midnight-provisioner PowerShell directory:

    git fetch --no-tags origin verification/phase17-qemu-subset-integrity
    if ($LASTEXITCODE -ne 0) { throw "Fetch failed" }

    $dir = Join-Path $env:TEMP ("Midnight-Provisioner-RC-Runner-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $dir | Out-Null
    $runner = Join-Path $dir "Run-Midnight-Provisioner-Offline-Release-Gate.py"

    $scriptText = & git show origin/verification/phase17-qemu-subset-integrity:scripts/testing/Run-Midnight-Provisioner-Offline-Release-Gate.py
    if ($LASTEXITCODE -ne 0) { throw "Runner retrieval failed" }
    $scriptText | Set-Content -LiteralPath $runner -Encoding UTF8

    python $runner --repo (Get-Location).Path

This optional bootstrap fetch updates Git metadata and creates ONE
new temp runner copy. The last command is PLAN ONLY; it neither
contacts GitHub nor runs tests or changes Windows.

To opt in later to the full isolated test pass:

    python $runner --repo (Get-Location).Path --run

Previously used Python slim and Fedora test images may be cached.
If missing, the runner returns BLOCKED without an image download.
Explicit opt-in alternatives, if wanted:

    python $runner --repo (Get-Location).Path --run --pull-python-images
    python $runner --repo (Get-Location).Path --run --build-fedora-image

Both switches can be combined. Pull/build uses network only during
image preparation. Test containers ALWAYS use no-network runtime.

After a run the runner prints the detached commit SHA and new local
log/report paths. Review local raw logs for private machine paths
before sharing them. The small JSON summary includes check statuses,
tested SHA and explicit NOT_TESTED for physical Fedora acceptance.
No automatic PR merge or hosted Actions report is created.

## Remain on HOLD

- Actual licensed Windows 11 Pro clean install, USB preparation and
  Pro activation are not part of this phase.
- The example backup-drive capacity user-confirmed portable drive remains BACKUP ONLY;
  the separate 16 GB stick must never be silently formatted.
- The user is not installing soon; no OS deployment is scheduled.
- OneDrive/Widgets/Xbox/Copilot removal, BitLocker automatic-encryption
  decisions and enabling Windows Sandbox/WSL require separate approval.
- Actual Fedora KDE host, KVM and VM isolation acceptance remains
  unverified until appropriate supervised hardware testing.
- PRs remain DRAFT and UNMERGED; owner approval is mandatory before
  branch integration and release.

This phase also reconciles stale Home-versus-Pro test assertions
after the user reported owning a Pro key. No licence key is read,
transmitted or stored in project config/logs.

See the integration checklist, Fedora acceptance plan and
Windows 11 Pro 32-point customization profile for later milestones.

## Phase 5 extension: independently auditable evidence

The new [Release evidence audit](RELEASE_EVIDENCE_AUDIT.md) introduces
a v2 report with the exact tested commit, unchanged original main
before/after SHA values, a completed local test-log SHA-256 and explicit
`deployment_approved=false`, `release_attested=false`.
A separate read-only script,
`scripts/release/Audit-Midnight-Provisioner-Release-Evidence.py`, rejects missing or
failed checks, stale commits and tampered logs, and never treats
synthetic Docker verification as real hardware certification.

**No test output for this latest cumulative branch has been run or
validated.** The v2 log hash and report are local unauthenticated
consistency evidence, not third-party attestation. Do not merge any
draft PR or deploy Windows/Fedora from this gate alone.

## Phase 8 convenience wrapper and exact-SHA pin

For native Windows 10, the new
[PowerShell launcher](WINDOWS_ONE_COMMAND_OFFLINE_CHECKS.md)
lets the user preview, fetch Git refs, perform the PR ancestry
audit and later launch cumulative Docker tests without checking out
a draft branch or overwriting local ignored data.

The release runner now supports optional `--expected-commit
<40-character-lowercase-SHA>`; a changed fetched branch causes a
hard blocker **before creating a detached worktree** and a second
post-checkout equality assertion. The wrapper always supplies the
SHA from its exact pinned candidate when `-RunDockerGate` is
explicitly approved. This is additional protection, not
independent trustworthy evidence of Windows/Fedora security.

New tests are committed but have not yet been run on Windows/Docker.

## Phase 9 — strict suite completeness (newest candidate)

The latest test candidate fixes a stale Git-worktree regression
assertion and prevents empty/skipped test suites from reporting PASS.
Python 3.11–3.13 now invoke `scripts/testing/run_headless_matrix.py`,
requiring 60 collected / 40 executed tests. Fedora 43's `--all`
requires real, non-skipped Qt and QEMU/libvirt fixture suites
(at least five tests each). Missing Linux Bash syntax validation
is also a blocker, not a silent NOT RUN.

Read [strict test completeness](OFFLINE_TEST_COMPLETENESS.md).
These changes have not yet been run on the Windows/Docker host.

## Phase 10 backup integrity synthetic suite

The latest cumulative candidate includes
`tests/test_backup_integrity_preflight.py`, synthetic tests of
preview-only behavior, content changes without size changes, extra
and missing files, Windows reparse/symlink blocking, and
exclusive-create report rules. They use only disposable temp data
and do not inspect user data or the portable drive. The
real latest branch's Windows/Docker test pass remains pending.
See [backup safety](BACKUP_INTEGRITY_PREFLIGHT.md).

## Phase 11 backup-set regression coverage

The portable Windows/Fedora test catalog now includes
`tests/test_backup_set_preflight.py`, with multi-directory matching,
missing/altered content, overlapping roots, empty sources,
hardlinks, unsafe local manifests and read-only report checks.
The newest cumulative branch remains unexecuted on the user's
actual Windows/Docker host; synthetic tests do not authorize
an OS install or a PR merge.

## Phase 12: current backup security integration candidate

The latest cumulative candidate includes new path-boundary tests in
`tests/test_backup_integrity_preflight.py` and
`tests/test_backup_set_preflight.py`. They must pass as part of the
same pinned SHA release gate; the prior isolated fixture test cannot
substitute for a native Windows junction acceptance.

## Phase 16 — Python runner module import reliability

All `scripts/`-launched unittest helpers now place the exact
checkout root at the front of sys.path before discovery. Without
this, discovered test modules which import `midnight-provisioner` may
fail to load on an otherwise complete checkout. The new synthetic
subprocess test `tests/test_isolated_runner_imports.py` is
part of the Windows portable and headless Docker discovery paths.

The source-level fix was reproduced in a disposable local
Python 3.13 fixture; the actual current GitHub candidate remains
unverified on native Windows and the Docker/Fedora test matrix.
See [Phase 16](PHASE16_IMPORT_PATH_VERIFICATION.md).
