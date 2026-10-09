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

The repository also has `scripts/Start-Nightglass-Fedora-Checks.ps1`
as a small bootstrap: it fetches the versioned runner into a NEW
temporary directory and executes it. The independently distributed
bootstrap is convenient while your original checkout remains on
`main`. It never checks out `main` or replaces your existing local
PowerShell scripts.

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

## 2026-10-09: first Docker execution and follow-up triage

The first real Docker Desktop execution on Windows 10 successfully built Fedora 43
and reached the full Linux test suite. Results were **NOT a full pass**:
62 Python sources parsed; native libvirt/QEMU fixtures **6/6 PASS**;
full unittest discovery **378 tests, 11 failures, 2 errors, 22 skipped**;
Bash syntax check **FAIL**; separate PySide6 GUI smoke **FAIL** without a
Python traceback visible in the supplied transcript.

The failures were investigated and follow-up commits on the same draft
integration branch now:
- Enforce LF checkout of `*.sh` using `.gitattributes`, avoiding CRLF in
  Windows-created worktrees while leaving existing worktrees untouched.
- Refactor the unchanged KVM accessibility policy into an independently
  mockable helper, removing a test's globally patched
  `os.path.exists` that falsely claimed every staging directory had
  an `INCOMPLETE` marker (accounting for the repeated readiness errors).
- Give a synthetic nominal-VM startup test a deterministic simulated
  host memory/CPU budget rather than inadvertently using Docker's 2 GiB
  limit. Runtime guest memory limits remain enforced.
- Enable Python faulthandler and report subprocess exit codes/signals to
  distinguish a GUI crash, kill or assertion failure on the next run.
- Add regression coverage for the Docker cache-miss and shell line endings.

**Pending:** rerun the latest dedicated integration worktree using the runner
documented above. Do not claim Linux suite, GUI, host SELinux/sVirt, live
guest isolation or physical Fedora/KVM acceptance passed on the basis of the
first Docker execution. Do not merge draft PRs until the remaining failures
and later hardware acceptance gates have been addressed.

## 2026-10-09: second Docker run, GUI SIGSEGV isolated

The follow-up Docker Desktop run of commit `6a3cc5f` was materially better:
- Python source syntax: **62 files PASS**
- Bash syntax: **PASS** after new LF checkout rules
- Full Fedora/Linux unittest discovery: **379 tests, OK (skipped=22)**
- Native libvirt/QEMU fixture suite: **6/6 PASS**
- Real Qt offscreen GUI smoke: **FAIL — SIGSEGV**, exit `-11`

Python faulthandler identified the first crash site at
`nightglass/ui.py:383`: `posture_button.clicked.connect(self.check_host_security)`.
The C backtrace entered PySide6 6.10 `qobjectConnectCallback` /
`MetaObjectBuilder` on Fedora Python 3.14. This is consistent with a
PySide signal-registration interoperability issue; **the exact
upstream cause is not independently established**.

The integration branch now routes MainWindow's direct Python-bound
signal connections through small callable adapters instead of asking
PySide to register those methods dynamically as slots. A static
guardrail test prevents reintroducing direct bound connections, and
an opt-in real Qt GUI test checks that two read-only diagnostics
buttons still dispatch to their handlers with host actions mocked.

**Unverified after the patch:** actual Qt offscreen smoke success, real
Fedora SELinux/sVirt and KVM host isolation, guest boot/rollback, and
Python 3.11–3.13 matrix. Continue to treat the overall gate as
**INTEGRATION HOLD** until the new GUI container log succeeds and later
physical Fedora checks are performed.
