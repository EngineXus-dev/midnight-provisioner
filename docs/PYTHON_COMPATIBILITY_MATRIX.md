# Local Python compatibility matrix (no GitHub Actions)

**Status:** First Docker Desktop execution FAILED on Python 3.11 due to
insufficient test tmpfs capacity; runner corrected, **rerun pending**.
No Python 3.11/3.12/3.13 compatibility PASS has been established yet.

The already tested Fedora 43 container used Python 3.14.7. Nightglass
declares Python >=3.11, so this opt-in script checks headless Linux
synthetic tests on independent 3.11, 3.12 and 3.13 images. These are
official Debian-based Python slim images, **not Fedora host tests**.

## Start from the existing Windows repository without checking out files

In PowerShell, from the original Nightglass checkout:

    git fetch --no-tags origin verification/fedora-host-acceptance-preflight
    if ($LASTEXITCODE -ne 0) { throw "Git fetch failed" }

    $dir = Join-Path $env:TEMP ("Nightglass-Matrix-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $dir | Out-Null
    $runner = Join-Path $dir "Run-Nightglass-Python-Matrix.ps1"

    git show origin/verification/fedora-host-acceptance-preflight:scripts/Run-Nightglass-Python-Matrix.ps1 |
        Set-Content -LiteralPath $runner -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw "Runner retrieval failed" }

    powershell -NoProfile -ExecutionPolicy Bypass -File $runner -RepoPath (Get-Location).Path

This intentionally does NOT pull or checkout code over an existing
working folder. It creates a fresh detached sibling worktree and a
uniquely named results transcript beside the original repository.
Fetch updates only Git metadata. Neither .env, .venv, generated files,
local VM images, main, nor the existing worktree is overwritten.

Docker Desktop must have a running Linux engine. Python 3.11/3.12/3.13
images are pulled from Docker Hub when missing, so image acquisition
can use the host's network. Each subsequent test container uses
network=none, a read-only source tree and root filesystem, unprivileged
UID 10001, all capabilities dropped, no-new-privileges, 1 GiB RAM,
two CPUs, disposable temp storage, no KVM/Docker daemon sockets, and
no elevated host operations.

Tests use Python's standard-library unittest discovery with no
guest startup, install commands, sudo, UI or native image tools.
The GUI and six real native libvirt/QEMU fixtures already PASSED in the
separate Fedora 43 Docker verification; do not falsely attribute those
tests to this Python version matrix. The headless test suites can
SKIP the GUI and native-tool tests due to absent dependencies; skipped
tests are not counted as validated on those Python versions.

Expected output has a per-version PASS/FAIL and a new -results.txt
file. A failed test or unavailable image stops the runner nonzero.
No GitHub Actions, branch merge, push, rebase, reset or git clean.

**Even if the matrix passes, this is not real Fedora host acceptance.**
See [Fedora host preflight](FEDORA_HOST_PREFLIGHT.md) and
[Fedora physical acceptance](FEDORA_ACCEPTANCE.md).

## First Windows Docker Desktop execution — 2026-10-09

The first matrix execution at commit `adbb1b0` pulled the official
`python:3.11-slim` container and ran Linux unittest discovery
offline. It reported **396 tests, 3 failures, 15 errors, 29 skips**
and stopped before trying Python 3.12 or 3.13.

All 18 observed failures/errors were the same test-container resource
problem: the original runner mounted `/tmp` on a **256 MiB tmpfs**,
while Nightglass's backup and recovery planning policy correctly
requires **256 MiB *free reserve* plus the copied data**. The
protection fired before the intended synthetic backup/recovery
behavior could be exercised. It should not be weakened.

The runner now allows a **512 MiB** disposable tmpfs while retaining
the 1 GiB container-memory cap, rootless UID, read-only source,
network-denied operation and original 256 MiB application reserve.
Regression coverage checks the configured space exceeds that reserve
and confirms the backup/recovery checks still exist.

**This resource correction is committed but has not been re-executed.**
Rerun the complete three-version matrix. Do not infer that Python
3.11 passed, that versions 3.12/3.13 were attempted, or that real
Fedora host isolation has been verified.
