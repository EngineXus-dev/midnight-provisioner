# Nightglass integration and no-Actions verification

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Status: FEDORA CONTAINER VERIFICATION PASSED / HOST ACCEPTANCE HOLD — no merges until real Fedora/KVM gates and explicit reviewer/owner approval.**

Nightglass is developed as a cumulative chain of **29 open draft pull
requests** as of October 9, 2026. No PR has been merged. PR #1 targets
\`main\` and each following PR targets the preceding phase branch.
Draft PR #31 in this workstream adds a manual test entry point and
prepares future CI to run **only on explicit workflow_dispatch**. It
does not merge anything or activate a high-risk guest capability.

## 1. Stop wasting hosted Actions minutes

The workflow on the **integration branch** removes \`push\` and
\`pull_request\` triggers and retains only:

\`\`\`yaml
on:
  workflow_dispatch:
\`\`\`

**Important:** this file is branch-scoped. GitHub can still run older
automatic workflows on \`main\` or other PR branches with old workflow
definitions. If every hosted runner must remain quiet, an owner should
disable **Verify source** via GitHub's repository
**Actions → Verify source → ... → Disable workflow**, or adjust
repository Actions settings temporarily. Re-enable it deliberately only
after the allowance resets. **We have not changed repository-level
Actions settings or the default branch.**

Never infer that a cancelled workflow equals failing code. Jobs that
failed may indicate bugs, runner setup problems, quota limits or another
issue. The PR #29 logs were unavailable for retrieval; their exact
failure cause is **UNVERIFIED**. No failed/cancelled jobs were re-run.

## 2. Check out the integration branch SAFELY

**Do not use \`git reset --hard\`, \`git clean -fdx\`, or a pull script
that writes into an existing workstation environment.** The original
checkout can contain private \`.env\`, \`.venv\`, generated data, and
guest image files not tracked by Git. Keep those untouched.

In an existing Nightglass Git checkout, an **isolated sibling worktree**
lets you test the integration branch without overwriting the original
working folder:

\`\`\`bash
git fetch origin chore/offline-integration-verification
git worktree add ../nightglass-integration-check origin/chore/offline-integration-verification
cd ../nightglass-integration-check
\`\`\`

The destination \`../nightglass-integration-check\` must be a **NEW,
nonexistent** directory. Git refuses to use an existing worktree
destination. Use a different new name if you have one already.
Do not delete the original checkout or copy its secrets to the test
worktree. Avoid a live VM directory.

Alternatively, clone the branch into a new clean directory (not on top
of any existing files).

## 3. Run completely local verification

On **Fedora/Linux**, the default runs source syntax and the full
Python synthetic unit suite (and bash syntax when bash is available):

\`\`\`bash
python3 -B scripts/verify_local.py
\`\`\`

On **Windows 10/11**, the same command deliberately runs only six
portable unit modules plus selected synthetic QEMU process-label tests.
It does **not** claim the full suite passed: Windows cannot reproduce
Linux chmod 0600 permissions, Linux symlink semantics, SELinux,
os.geteuid, system libvirt filesystem paths or live Fedora isolation.
It reports **WINDOWS-PORTABLE SUBSET PASSED ONLY** if these checks pass.

To narrow down those QEMU synthetic fixtures:

\`\`\`powershell
python -B scripts/verify_local.py --focused
\`\`\`

Use \`--full\` on Windows only when deliberately investigating
Linux-specific false failures; it is **not** an acceptance test.
Windows \`bash.exe\` may be the WSL launcher with no distro installed;
the verifier no longer invokes it or asks you to install WSL.

With **PySide6 already installed locally**, opt into the actual Qt
offscreen smoke tests:

\`\`\`bash
python3 -B scripts/verify_local.py --gui
\`\`\`

With existing \`virt-xml-validate\` and \`qemu-img\` installed, test only
harmless native libvirt/QEMU **fixtures**, never guest creation:

\`\`\`bash
python3 -B scripts/verify_local.py --native
\`\`\`

Use \`--all\` to request both optional suites, or \`--dry-run\` to see
the commands without running them. The script does not install any
dependencies, connect to GitHub, use sudo, start VMs, enable networking,
create/overwrite workspace files, or spend hosted Actions minutes.
Python AST parsing avoids generating pyc files.

**Unit-only PASS** is *not* GUI/native verification. A Qt/native suite
can legitimately fail because tools or libraries are missing, and the
report must say that plainly. A local green result does **not** change
the PR's GitHub checks, validate actual Fedora hardware behavior or
prove malicious guest isolation.

## Fedora Docker verification from the Windows workstation

For fuller **Linux test semantics** without hosted Actions minutes, an
additional PowerShell runner is now available:
`scripts/Run-Nightglass-Fedora-Checks.ps1` and its standalone
`scripts/Start-Nightglass-Fedora-Checks.ps1` bootstrap.
It fetches a clean **new git worktree**, builds Fedora 43 test tools
using an empty-source Docker build context and runs
`python3 -B scripts/verify_local.py --all` in a **nonroot, read-only,
network-disabled container**. This includes the complete Linux unit
suite, actual PySide6 offscreen Qt widgets and native QEMU/libvirt
fixture validators. The initial image build may download packages,
while test execution itself has no network connectivity.

**Docker Desktop verification now PASSED on 2026-10-09:** the user supplied
a successful, offline Fedora 43 container log for integration commit
`d4bf4b9d7748b1d75c077e4f37031374bd9d2029`:
62 Python sources parsed; Bash syntax passed; 381 full Linux unit
tests completed with 23 GUI-only tests skipped in unit discovery;
the same 23 GUI tests all passed in the explicit PySide6 offscreen
suite; and 6 native QEMU/libvirt fixture tests passed. All requested
container stages returned zero. No Nightglass VMs, host disk alterations,
GitHub Actions or PR merges were involved. This is container evidence,
**not real host security acceptance**.

See [Fedora Docker verification instructions](FEDORA_DOCKER_VERIFICATION.md).
This still cannot certify an actual running Fedora/KVM guest, host
SELinux/sVirt, packet isolation or cold recovery on physical hardware.

## 4. What remains blocked

- **Windows baseline, 2026-10-09:** the first isolated local run parsed
  61 Python sources but reported 372 tests: **41 failures, 35 errors,
  28 skips**. Many were Windows-only artifacts: symlink creation denied
  (WinError 1314), absent POSIX \`os.geteuid()\`, non-POSIX reported
  \`st_mode\` permissions, POSIX-only paths and the unconfigured WSL
  \`bash.exe\` launcher. Do not call that run a passing Fedora test or
  assume 76 separate product defects.
- Corrected a **genuine synthetic QEMU fixture defect** from an earlier
  mistaken change: after Linux \`/proc/PID/stat\`'s state field (field 3,
  split-field index 0), the process start time is field 22 (index 19).
  Therefore the fixture needs exactly **18 filler fields** between state
  and starttime, not 19. Added an explicit field-22 regression test
  and POSIX executable basename semantics for Windows fixture runs.
  The user still needs to rerun the checks; this is NOT proof of real
  Fedora process-label or network isolation.

- **Headless synthetic Python 3.11/3.12/3.13 matrix PASSED** on the
  user's Docker Desktop at commit `4864998`: each interpreter ran 397
  tests, 368 passed, 29 skipped, zero failures/errors. GUI/native
  tools were not run in these three slim-image environments; Qt and
  native fixtures PASSED separately in Fedora 43/Python 3.14.7.
  Actual host compatibility and VM isolation are still unverified.
- Check PR #28/#29 ancestry and forward-revert interactions before
  merging; those branches include reversible correction commits. Do
  not force-push to "tidy" them.
- Complete the separately supervised Fedora/KVM acceptance checklist:
  package provenance, actual QEMU/SELinux contexts, packet-level
  network denial and a benign recovery boot/rollback rehearsal.
- Never enable automatic risky VM boot, import, arbitrary host/guest
  file transfer or all-tools Kali installation based on metadata alone.

## 5. Integration policy

Keep the 29 preceding PRs and integration PR #31 as **drafts**. Use the newest cumulative branch
for regression verification rather than wasting Actions on every PR.
When tests and physical safety gates appropriate to the phase are
met—and the repository owner **explicitly authorizes merges**—integrate
from the bottom of the stack in dependency order. Favor regular merge
commits to preserve ancestry. Before each merge, verify the next PR's
base, diff, tests, and effect on pending stacked branches. Do not
automatically close, squash, cherry-pick, reset, delete or rebase the
whole stack.

This guide records the verified Fedora container test result on commit
`d4bf4b9`; it does not establish real-host SELinux/sVirt/KVM, guest isolation,
packet-level network denial or guest cold restore. The Python 3.11–3.13
**headless synthetic matrix** now passed separately on 2026-10-09.
Existing draft PRs remain unmerged.


## Next draft phase: Fedora host prerequisites and Python compatibility

A new **unmerged** stacked branch, verification/fedora-host-acceptance-preflight,
starts from the verified Fedora Docker integration branch. It introduces:

- Read-only, nonroot Fedora OS / SELinux / KVM / libvirt prerequisite audit
  with opt-in, exclusive-create 0600 evidence, and synthetic negative tests
- A manually supervised real-host acceptance plan; no VM boot is automatic
- An opt-in Windows Docker Linux headless test matrix for Python 3.11–3.13,
  with separate read-only containers and no GitHub Actions

**The headless Python 3.11–3.13 matrix has now PASSED** in isolated
Linux Docker containers (397 tests/version, 29 skips/version).
**The real Fedora host audit has NOT been run.** Benign guest boot,
packet-level network isolation, effective host SELinux/sVirt contexts,
cold recovery, and explicit integration/merge approval remain pending.

Do not merge any draft PR as part of this phase. See
[Fedora host prerequisite plan](FEDORA_HOST_PREFLIGHT.md) and
[Python compatibility matrix](PYTHON_COMPATIBILITY_MATRIX.md).

## Deployment preparation draft phase: Windows dual-boot safety gates

A further stacked draft branch `deployment/windows-dualboot-readiness-gates`
prepares (but **does not perform**) the Windows-to-Fedora dual-boot transition.
The native PowerShell reader observes current Windows OS/firmware/secure-boot,
BitLocker **status only**, Fast Startup flag, sanitized partition/disk inventory,
RAM and virtualization hints, with **NO** partition/boot/firmware/encryption
writes, disk selection, elevation, recovery-key collection or report creation.
Read-only status is never installation permission.

The branch includes static Python safety contract checks, adds these to the
portable Windows verifier allowlist, and documents manual **HOLD** gates:
tested disconnected Windows backup and recovery USB; offline recovery keys;
independently reviewed disk/ESP/Recovery/firmware plan; Fedora live-USB trial;
and actual post-install Windows/Fedora boots plus rollback path. The install
and physical Fedora acceptance stages remain **UNVERIFIED**, requiring
separate explicit owner approval.

**Verification:** the new Windows reviewer has not been executed on a real
Windows host or passed a Windows PowerShell AST parser run yet. Prior Fedora
Docker and Python 3.11–3.13 PASS results apply to their previously recorded
code commits, not the newly changed deployment branch. Do not merge PRs or
alter Windows hardware as part of this change. See
[dual-boot deployment gates](DEPLOYMENT_SAFETY_GATES.md) and
[private decision template](DEPLOYMENT_DECISION_TEMPLATE.md).

## Optional Windows 11-first planning (additional draft PR)

User-supplied Windows 10 Home hardware review passed the native
PowerShell AST parser and the read-only query script on 2026-10-09.
Observations: UEFI, Windows GPT Disk 0 with ESP/MSR/C:/Recovery,
another measured backup-disk capacity GPT disk **now user-confirmed portable** and
EXCLUDED from OS installation/USB media formatting, Windows C:
measured filesystem free space filesystem free (NOT unallocated), detected RAM capacity usable RAM,
firmware virtualization enabled, Secure Boot/encryption unknown and
Fast Startup enabled.

The next draft branch `deployment/windows11-upgrade-first-planning`
adds Windows 10/11 reviewer TPM advisory fields and other-disk
read-only partition/bus details, updated tests and an **optional**
Windows 11 upgrade-first plan. Microsoft's supported-CPU list includes
the reported target CPU (verify compatibility), but actual Windows 11 device readiness
(including TPM 2.0, Secure Boot capability, graphics/drivers) must be
checked via the official PC Health Check/Windows Update.

**Pending:** the revised PowerShell parser + actual non-admin
Windows execution. Prior successful Windows reviewer logs apply to
the earlier script only. No Windows 11 upgrade, Fedora dual boot,
partition writes or live KVM security acceptance has occurred.
Windows 11 (if elected) must be completed, backed up and re-baselined
before Fedora target-disk selection. All PRs remain draft/unmerged,
no Actions or release status change. Read
[Windows 11-first plan](WINDOWS11_UPGRADE_FIRST.md).

## Dedicated multiboot USB — planning only

The user confirmed **Disk 1 (measured backup-disk capacity) is a portable drive**.
It must not be used as a Fedora OS target, USB writer target or empty
storage assumption. Planning now favours a **third, explicitly empty USB**
holding independently verified official Windows 11 and Fedora KDE ISO files
through a multiboot boot menu. Ventoy Secure Boot policy and firmware
compatibility remain unverified. This is a convenience proposal, not an
automated Windows+Fedora install, approval to erase USB media, or a
change to real disks. User has subsequently chosen a **future CLEAN Windows 11 installation**,
not an in-place upgrade; portable backup and recovery must be verified,
then Fedora remains a later manual installation.
See [Nightglass one-USB plan](ONE_USB_MULTIBOOT_PLAN.md).

## Deferred clean Windows 11 selection and 16 GB media (2026-10-09)

The user clarified that a separate **16 GB USB** is available and they
intend a **clean Windows 11 install**, not in-place upgrade. They plan
to back up desired files to the confirmed **portable example backup-drive capacity Disk 1** and
have explicitly said they are **NOT installing soon**.

The revised one-USB plan covers combined ISO fit checks for 16 GB,
mandatory USB identity/erase approval, verified selective and optional
system-image backups, preserved local Git ignored/untracked files
(including secure .env/config handling), and disconnection of portable
Disk 1 before any eventual installer boot.

**No data copy, USB write, Windows clean install, Fedora installation
or partition operation has been performed by this phase.**
No prior script should be interpreted as consent to install or wipe
the Windows internal disk. See
[clean Windows 11 staged plan](WINDOWS11_CLEAN_INSTALL_STAGED.md).

## Optional Windows 11 Lite profile — development draft, NOT installed

A new stacked draft branch documents the NTLite Free conservative
two-stage process for the **currently official Windows 11 26H2 ISO**
and removes the community post's outdated default to 25H2.
**Windows 10 Home licence** must be respected; a trimmed Pro-only
ISO can be considered following the user's report of a separate Pro
key, but its legitimacy and Windows 11 Pro activation must first be
verified; the pre-existing Windows 10 Home licence is not sufficient.

A preview-first, local HKCU-only PowerShell preference helper and
static safety tests are added. Its Apply/Undo functionality is NOT
yet verified by native Windows 11 PowerShell/VM testing. No Windows
components, drivers, Defender, updates, servicing or disk partitions
are removed; no external debloat scripts are automatically downloaded.
Avoid chaining WinUtil, Win11Debloat and RemoveWindowsAI because
their changes may overlap or harm servicing.

The main purpose of the proposed one-USB stick remains official,
independently verifiable Windows/Fedora ISOs. The optional Lite image
is not needed merely to fit the user's separate 16 GB USB. All
Windows clean install and hardware integration gates remain ON HOLD.
See [Lite build profile](WINDOWS11_LITE_IMAGE_PROFILE.md).

## User-requested Windows 11 Pro post-install profile — staged

the selected edition requires a valid Windows Pro key and requests removal of
OneDrive, Xbox/Game Bar, Widgets/promotional apps, Copilot/Recall/Click
to Do plus a detailed 32-item list of privacy, update, Explorer, UI,
location, AI and virtualization settings. The plan has been encoded in
`config/windows11-pro-custom.json` (35 grouped requests) and documented
in [Windows 11 Pro profile](WINDOWS11_PRO_32_POINT_PROFILE.md).

`Invoke-Nightglass-Win11ProCustom.ps1` is read-only Preview by default;
optional future ApplyCore requires Windows 11 Pro, explicit consent,
backup flag and locally reviewed, SHA256-pinned actual Win11Debloat.ps1.
The uploaded **Get.ps1** is a remote downloader/elevated launcher;
the supplied WinUtil ZIP has broad presets, and neither is executed.
The core excludes OneDrive/Appx uninstalls, automatic-encryption setting,
Sandbox/WSL installation and Start pinned-layout deletion.

**Not run/verified:** new Windows 11 Pro PowerShell AST parse, `ApplyCore`
execution, Win11Debloat sourced version compatibility, actual ISO
customization, app removals, new OS installation, USB writing, or Fedora
hardware acceptance. Existing local Windows and main remain untouched.

## Stage: Windows 11 Pro activation later option and media capacity preflight

User has a Pro key and requests the option to **activate after a clean
installation** instead of typing the key into Setup immediately. Both
modes are modeled; activate_later is the default. Genuine Setup's
'I don't have a product key' choice may be used if available; OEM
Home key auto-detection requires verifying Pro edition selection.
Nightglass never accepts, stores or applies the actual key.

A new pure-Python plan-only script can *read* two separately downloaded
official ISOs, compute their sizes and optional SHA256, and estimate
whether their combined sizes plus 1 GiB headroom fit the user's
measured USB usable byte capacity. **No download, USB detection,
formatting, ISO editing, Windows Setup, disk writing, activation or
Fedora deployment happens.** Neither a hash nor capacity estimate
authenticates the ISO publisher or UEFI Secure Boot behavior.

New source and regression tests are committed but **not yet executed**
on the user's latest branch. All PRs remain draft/unmerged and hardware
acceptance remains pending. See
[Pro activation and USB preflight](WINDOWS11_PRO_ACTIVATE_LATER.md).

## New cumulative offline release gate — not yet executed (draft)

A new stacked branch `verification/offline-release-candidate-gate` adds
an opt-in, fail-closed **latest-code** offline verification runner.
Default preview has no Git or Docker effects. Explicit execution fetches
only the branch into a NEW detached sibling worktree; native Windows
PowerShell and Python AST are **parse-only**, while actual unit tests
run only in disconnected/rootless read-only Docker environments
(Python 3.11, 3.12, 3.13 and Fedora 43 Qt/native fixtures).

Earlier PASS results do NOT apply to this newest code SHA. No new
matrix/Fedora test run has been performed for this branch.
A mandatory gate cannot turn green on blocked/missing test images.
Private exclusive-create local log/JSON records exact commit and
statuses; physical Fedora hardware acceptance is ALWAYS separate.

The previously stale Windows 11 Lite test's Home-only wording was
corrected for the valid Pro licence. No keys collected/stored.
No branch has been merged. The user remains unready to format the
16 GB stick, change internal 500 GB drive, install Windows 11 Pro
or Fedora, or make Win11Debloat changes; portable example backup-drive capacity disk stays
backup-only. See [offline gate](OFFLINE_RELEASE_CANDIDATE_GATE.md).
