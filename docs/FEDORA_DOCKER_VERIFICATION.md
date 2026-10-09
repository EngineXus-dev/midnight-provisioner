# Fedora Docker verification from Windows 10/11

This is Nightglass's **full Linux synthetic test runner**, designed for
the existing Windows workstation and a Docker Desktop **Linux containers**
engine. It does **not** require GitHub Actions minutes, a Fedora installation
on the host, WSL distribution installation, elevated PowerShell, or actual
VM creation.

## Run

From your original Nightglass Git checkout, if this integration branch's
runner is already available:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Run-Nightglass-Fedora-Checks.ps1
```

If your local checkout is still on `main`, use the standalone
**Start-Nightglass-Fedora-Checks.ps1** launcher distributed with this update,
or manually retrieve the committed runner from Git without checking it
out over your existing files:

```powershell
git fetch --no-tags origin chore/offline-integration-verification
git show origin/chore/offline-integration-verification:scripts/Run-Nightglass-Fedora-Checks.ps1 |
    Set-Content -Encoding UTF8 "$env:TEMP\Run-Nightglass-Fedora-Checks.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\Run-Nightglass-Fedora-Checks.ps1"
```

The PowerShell runner discovers the existing repo (or accepts
`-RepoPath "C:\path\to\nightglass-workspaces"`), checks that Docker's
daemon uses **Linux containers**, fetches only the named integration
branch, and creates a **NEW sibling git worktree** named
`Nightglass-Fedora-Check-<timestamp>-<random>`. Your original checkout's
`.env`, `.venv`, custom folders and tracked/untracked files are not
copied, deleted, reset or overwritten. Shared Git metadata is updated
only for fetch/worktree registration. A new `-results.txt` transcript
is saved beside the worktree.

Use `-Focused` to run only recent Kali tests **plus the complete GUI and
native fixtures**; use `-ForceImageBuild` to rebuild the Fedora test
image after a package problem. Default is the **full** suite.

## Test image and security

The image is built from `fedora:43` using Fedora's RPM packages
`python3`, `python3-pyside6`, `qt6-qtbase-gui`,
`libvirt-client`, `qemu-img`, `libxml2` and `bash`.
Initial image build can download the Fedora base image and package
updates; subsequent runs reuse the cached image identified by the
Dockerfile SHA-256.

The Docker build context contains **only the Containerfile**, not the
Git checkout, secrets, source trees or .env files. At test runtime the
new, clean checkout is mounted **read-only** at `/workspace`.
The container uses:

- **`--network none`**; no internet access during tests
- **`--read-only`** root filesystem and a bounded, disposable tmpfs
- **`--user 10001:10001`**, **`--cap-drop ALL`** and no-new-privileges
- Limits of 2 logical CPUs, 2 GiB memory and 160 processes
- No `--privileged`, `/dev/kvm`, Docker socket, host libvirt socket,
  Windows disk devices, clipboard or host runtime configuration mounted

Docker Desktop uses its own virtualization backend to run containers.
This workflow does **not** create or start *Nightglass* Kali/KVM guest
VMs, inspect host libvirt state or modify disk images. The
`test_native_tools.py` suite creates only tiny throwaway qcow2/raw
fixtures **inside container tmpfs**, and deletes them automatically.

## What is run

The committed `scripts/verify_local.py --all` performs:

1. AST syntax parse of all project Python source
2. `bash -n` script syntax check (no shell setup scripts are executed)
3. Full Python `unittest` discovery on **Linux**, including
   real POSIX symlink/mode semantics and mocked virtualization policy
4. PySide6 offscreen GUI smoke tests (`QT_QPA_PLATFORM=offscreen`)
5. Actual Fedora `virt-xml-validate` and `qemu-img` harmless fixtures

Each section reports PASS or FAIL. An unavailable requested tool or a
failing test returns a **nonzero exit**; no misleading full pass.
The PowerShell wrapper preserves exit status and a complete log.

## Known limitations / integration gate

- Fedora **container** tests do **not** prove the Fedora KDE host's
  SELinux/sVirt enforcement, actual `/proc` context of a running
  QEMU guest, KVM acceleration, packet-level network isolation, VM
  startup or successful cold recovery/rollback.
- Fedora 43 provides Python 3.14, not the exact GitHub Actions Python
  3.11/3.12/3.13 matrix. Those versions need separate verification.
- Image builds use Fedora's network repositories; do not claim a
  completely offline build. **Test runtime** is offline.
- Docker Desktop must be installed **and its Linux engine running**.
  If the daemon is stopped, the runner **fails safely**; Docker being
  installed alone is not sufficient.
- No GitHub Actions are triggered, no branch is merged, and no
  existing worktree is replaced or cleaned.
- Pull requests remain draft until the container log is reviewed and
  later hardware acceptance gates pass.

**Please return the newly generated `Nightglass-Fedora-Check-...-results.txt`
log if any tests fail.** The code can then be corrected in the connected
GitHub integration branch without a merge or history rewrite.
