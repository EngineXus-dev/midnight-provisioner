# Nightglass — offline cumulative integration release gate

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Status: IMPLEMENTED ON A DRAFT BRANCH; LATEST-RUN RESULTS PENDING.**
This is source/test readiness only, not permission to install Windows,
Fedora, a guest VM, a modified ISO or a USB bootloader.

## Purpose

Nightglass has many unmerged stacked draft PRs and no remaining
hosted GitHub Actions minutes. Earlier successful Fedora 43 Docker
and Python 3.11/3.12/3.13 tests apply to older Git commits.
The new offline release gate checks the **entire latest cumulative**
deployment/windows11-pro-activation-media-preflight branch without overwriting
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

From the user's original nightglass-workspaces PowerShell directory:

    git fetch --no-tags origin deployment/windows11-pro-activation-media-preflight
    if ($LASTEXITCODE -ne 0) { throw "Fetch failed" }

    $dir = Join-Path $env:TEMP ("Nightglass-RC-Runner-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $dir | Out-Null
    $runner = Join-Path $dir "Run-Nightglass-Offline-Release-Gate.py"

    $scriptText = & git show origin/deployment/windows11-pro-activation-media-preflight:scripts/Run-Nightglass-Offline-Release-Gate.py
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
