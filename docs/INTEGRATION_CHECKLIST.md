# Midnight Provisioner integration and no-Actions verification

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

> **Current integration handoff:** This checklist also retains **historical phase snapshots** (including its earlier PR #29/40 statements); do not treat those as the current PR census or merge readiness. For the cumulative owner-controlled PR #66, latest test ledger, exact-head gate and merge/pull plan, use [OWNER_MERGE_HANDOFF.md](OWNER_MERGE_HANDOFF.md). The full current-head Windows/Fedora retest is still unverified.


**Status: FEDORA CONTAINER VERIFICATION PASSED / HOST ACCEPTANCE HOLD — no merges until real Fedora/KVM gates and explicit reviewer/owner approval.**

Midnight Provisioner is developed as a cumulative chain of **29 open draft pull
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

In an existing Midnight Provisioner Git checkout, an **isolated sibling worktree**
lets you test the integration branch without overwriting the original
working folder:

\`\`\`bash
git fetch origin chore/offline-integration-verification
git worktree add ../midnight-provisioner-integration-check origin/chore/offline-integration-verification
cd ../midnight-provisioner-integration-check
\`\`\`

The destination \`../midnight-provisioner-integration-check\` must be a **NEW,
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
python3 -B scripts/testing/verify_local.py
\`\`\`

On **Windows 10/11**, the same command deliberately runs only six
portable unit modules plus selected synthetic QEMU process-label tests.
It does **not** claim the full suite passed: Windows cannot reproduce
Linux chmod 0600 permissions, Linux symlink semantics, SELinux,
os.geteuid, system libvirt filesystem paths or live Fedora isolation.
It reports **WINDOWS-PORTABLE SUBSET PASSED ONLY** if these checks pass.

To narrow down those QEMU synthetic fixtures:

\`\`\`powershell
python -B scripts/testing/verify_local.py --focused
\`\`\`

Use \`--full\` on Windows only when deliberately investigating
Linux-specific false failures; it is **not** an acceptance test.
Windows \`bash.exe\` may be the WSL launcher with no distro installed;
the verifier no longer invokes it or asks you to install WSL.

With **PySide6 already installed locally**, opt into the actual Qt
offscreen smoke tests:

\`\`\`bash
python3 -B scripts/testing/verify_local.py --gui
\`\`\`

With existing \`virt-xml-validate\` and \`qemu-img\` installed, test only
harmless native libvirt/QEMU **fixtures**, never guest creation:

\`\`\`bash
python3 -B scripts/testing/verify_local.py --native
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
`scripts/testing/Run-Midnight-Provisioner-Fedora-Checks.ps1` and its standalone
`scripts/testing/Start-Midnight-Provisioner-Fedora-Checks.ps1` bootstrap.
It fetches a clean **new git worktree**, builds Fedora 43 test tools
using an empty-source Docker build context and runs
`python3 -B scripts/testing/verify_local.py --all` in a **nonroot, read-only,
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
container stages returned zero. No Midnight Provisioner VMs, host disk alterations,
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
See [Midnight Provisioner one-USB plan](ONE_USB_MULTIBOOT_PLAN.md).

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

`Invoke-Midnight-Provisioner-Win11ProCustom.ps1` is read-only Preview by default;
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
Midnight Provisioner never accepts, stores or applies the actual key.

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

## Phase 5: latest source release-evidence audit — NOT YET VERIFIED

Stacked branch `verification/rc-evidence-and-stack-audit` adds
separately inspectable local v2 release-evidence consistency checking.
The cumulative runner records an exact detached tested SHA, observed
original `main` ref before and after (must match), and the SHA256 of
the finished local log. It explicitly labels all physical Fedora and
Windows/Fedora installation acceptance as NOT_TESTED/NOT_RUN, and
`release_attested=false` plus `deployment_approved=false`.

The independent read-only auditor requires the exact expected Git SHA
and matching local log, checks every mandatory stage and refuses
missing/blocked/failed tests, forged hardware/deployment claims, stale
SHAs, edited logs and unauthenticated-content confusion.
`tests/test_release_evidence_audit.py` contains synthetic coverage,
but **neither those new tests nor a fresh latest cumulative release gate
has been executed on the Windows host**.

A report's own hash is *not* a digital signature or independent
proof that tests were run honestly. It is a local engineering record.
No PR merge, OS install, USB format, user file copy or hardware
acceptance is authorized. See
[release evidence audit](RELEASE_EVIDENCE_AUDIT.md).

## Phase 6 — full PR stack audit, latest integration branch (tests pending)

I inspected GitHub PR metadata #1–40 on 2026-10-09. Exactly **39
PRs (#1–29 and #31–40) were OPEN, DRAFT and UNMERGED**. PR #30
returned NOT_FOUND, not "a failed/closed PR". Every observed
PR's base matched the predecessor's head, starting at main.
Prior final PR #40 branch comparison against main: **454 ahead,
0 behind, 136 changed files**. The changed list includes
`.github/workflows/verify.yml`, an explicit manual security review
item. This is historical evidence, not a persistent real-time check.

The new branch `verification/stack-integration-readiness` adds
`config/midnight-provisioner-pr-stack-snapshot.json`, a no-write-by-default
`scripts/release/Audit-Midnight-Provisioner-PR-Stack.py`, and synthetic
`tests/test_pr_stack_audit.py`, now in the Windows-portable
offline suite. The auditor reads only existing Git refs and path names;
it never fetches/merges, modifies source or invokes Windows/Fedora
tools. It refuses missing refs, non-linear stacks, main drift,
ambiguous origins and unexpected PR #30. Any passing result
**still requires full source/diff review, latest exact-SHA Docker
evidence, and live GitHub PR status checks**; `merge_authorized`
and `deployment_approved` stay FALSE.

**Neither Phase 6's tests nor the latest cumulative offline gate have
been run**. No PRs merged, no Actions used, no Windows 11 Pro
installation, no USB formatted and no portable backup drive touched.
Read [PR stack review](PR_STACK_INTEGRATION_READINESS.md).

## Phase 7 — main-checkout compatible pinned-source stack audit (UNTESTED)

The preceding `Audit-Midnight-Provisioner-PR-Stack.py` was not executable
as documented from the user's original `main` checkout: the draft-only
stack manifest wasn't present there. The new branch
`verification/remote-ref-stack-audit` fixes this without checking
out any PR or modifying local files: `--verify` reads the manifest
via `git show <candidate-SHA>:config/midnight-provisioner-pr-stack-snapshot.json`
after remote-tracking refs have been fetched explicitly.

The observed ancestor snapshot now lists **40 PRs through #41**
(#1–29 and #31–41), PR #30 absent. The auditor also reads the
same candidate commit's GitHub Actions workflow, demands
manual `workflow_dispatch` and global `contents: read`,
and flags mutable action tags. It does NOT run workflow jobs,
verify their actual dependencies, or merge drafts.

New tests were committed and source-level consistency checked
(manifest order, pinned blob, manual workflow event, read-only
permissions, flagged action versions). **No new Python test run,
Windows AST check, Docker/Fedora cumulative PASS or real hardware
acceptance is claimed.** All PRs still draft/unmerged and no
Windows/USB/portable backup drive changed. See
[pinned-source stack audit](REMOTE_REF_STACK_AUDIT.md).

## Phase 8 — optional Windows one-command offline verification

The repository now includes
`scripts/testing/Invoke-Midnight-Provisioner-OfflineChecks.ps1`, a Windows PowerShell
5.1 launcher designed to be fetched into a **new temporary folder**
while the user's actual Windows checkout remains on `main`.
Default execution only previews options; `-FetchRefs` updates Git
remote-tracking metadata, `-AuditStack` reads pinned Git-object
metadata and workflow source, and `-RunDockerGate` requires the
exact literal consent phrase to run isolated tests. Image download
and Fedora test build remain separate opt-ins.

The runner's `--expected-commit` pin is checked after fetch
**before worktree creation** and again after detached checkout,
preventing a silent run of a newer branch head. A new static
contract/Windows-native parser test is included in the portable
verification allowlist. The explicit predecessor stack now covers
PRs #1–29 and #31–42 (41 drafts; PR #30 absent).

**No new native Windows/PowerShell or Fedora Docker tests have yet been
executed against this code**. No Windows 11 installation, USB media
writing, portable example backup-drive capacity backup drive use, Windows debloat setting changes,
VM boot, PR merge or GitHub Actions invocation has occurred.

See [Windows offline one-command guide](WINDOWS_ONE_COMMAND_OFFLINE_CHECKS.md).

## Phase 9 — executed-test coverage hardening (UNVERIFIED RUNTIME)

The newest `verification/test-gate-reliability-hardening`
draft fixes a false-negative Git command-order assertion and prevents
zero/discovered-but-skipped tests from being accepted as PASS.
Each Python compatibility container requires at least 60 discovered
and 40 executed cases. Fedora Qt and native fixtures each require
five actual tests, zero skips. Missing Bash syntax validation in
a Linux `--all` test also blocks release evidence.

The snapshot now contains 42 predecessor PRs (#1–29 and #31–43;
#30 absent). All remain unmerged. No latest-branch native Windows,
Docker or Fedora tests have been run yet. No OS/USB/VM changes.
See [strict test completeness](OFFLINE_TEST_COMPLETENESS.md).

## Phase 10 — copied backup content integrity preflight (draft)

The user intends to back up important data to their **example backup-drive capacity portable
drive** before a *future* Windows 11 Pro clean install. Older Git
sync/update scripts accidentally overwrote local `.env`,
`.venv` and ignored/user-created files, so remote Git commits are
not sufficient data-preservation evidence.

`scripts/backup/Inspect-Midnight-Provisioner-Backup.py` now supports Preview
(default, **no filesystem access**), Inspect (metadata only), and
Verify (read-only SHA-256 of all regular files in two separately
selected folder trees). It includes hidden .git/.env/.venv,
reports missing/extra content, blocks reparse/link paths and
provides a new local JSON report only if explicitly selected.
Nothing is copied, deleted, mounted, restored, reformatted or
installed. True device independence and restorability remain
manual checks, not claimed as PASS.

A dedicated `tests/test_backup_integrity_preflight.py` uses
synthetic temporary data and is included in the portable suite.
**It has NOT yet been run on the target Windows laptop**, and no
live backups, operating systems or install media have been touched.
See [backup verification guide](BACKUP_INTEGRITY_PREFLIGHT.md).

## Phase 11 — multiple private backup-root validation (DRAFT)

Phase 10 verified one source/copied directory pair. A Windows 11
clean install could still destroy local-only files from *other*
repositories, Desktop, Documents, app-specific folders or datasets.
Phase 11 therefore adds `scripts/backup/Verify-Midnight-Provisioner-BackupSet.py`:
a pure Python, Preview-only-by-default tool that accepts a separate
PRIVATE local JSON catalog of source/backup directory pairs.

One Verify run hashes all regular files in every selected pair
and fails the full catalog when any required copy is missing,
different or an original hardlink rather than independent file
data. All roots must be nonoverlapping, and empty sources are
blocked. It reports aggregate counts and labels, not path names
or sensitive content. A matching report never proves the manifest
covers everything, that media is physically separate or that an
actual recovery test passed.

The tool and regression tests are staged in the newest
`deployment/multi-source-backup-readiness` draft; native Windows/
Fedora Docker execution remains PENDING. Private catalog filenames
are ignored by Git when they follow the documented suffixes, but
should be stored **outside the repo**. A synthetic example catalog
is provided; its drives/paths are intentionally nonfunctional.

No backups have been copied or checked on the user's computer.
No Windows/USB/Fedora installation, GitHub Actions or PR merging
has been performed. See [backup-set guide](MULTI_SOURCE_BACKUP_READINESS.md).

## Phase 12 — backup linked-parent security fix (draft)

The Phase 10/11 backup tools had a path-boundary bug: a normal final
directory beneath a symlink or Windows reparse/junction parent could
pass a final-component `lstat()` check. Report and private-manifest
paths had comparable exposure.

`security/backup-boundary-fix` adds
`reject_linked_ancestors()` and calls it before source/backup path
resolution, report path normalization/writing, and manifest opening.
Parent-traversal `..` is rejected. Tests cover linked parents,
symlinked report destinations, manifest redirection and synthetic
Windows reparse metadata. The previous Phase 12 disposable Linux
fixture PASS does NOT imply that these latest GitHub sources passed.

**Native Windows junction and cumulative Windows/Docker/Fedora
tests remain NOT RUN**. The guard is a conservative preflight,
not an atomic directory-handle sandbox; concurrent attackers may
still swap paths. No PR merge or deployment has occurred.
See [boundary hardening details](BACKUP_PATH_BOUNDARY_HARDENING.md).

## Phase 14 — latest-commit release gate reference repair (UNVERIFIED RUNTIME)

The Phase 13 draft kept its backup-security code but failed to
advance the test runner, PR graph validator, independent evidence
auditor and Windows launcher from Phase 12's branch. Testing such
scripts could silently check an **older commit**, so Phase 13 was
not an integrable release candidate.

The `verification/phase14-release-gate-repair` draft updates the
47-predecessor dependency snapshot through PR #48, explicitly
preserving absent PR #30. All active runner/auditor/launcher
branch constants and source regression expectations now agree
with that snapshot. The new portable
`tests/test_candidate_branch_contract.py` enforces those
invariants in future tests and checks that current runbooks point
to the same candidate. It does not fetch, install or modify the
project from inside a test.

**No native Windows, Docker, Fedora Qt/QEMU or real hardware
verification was performed here.** Exact candidate SHA, parsed
PowerShell source, real test counts and local log-digest evidence
are separate required gates before a user-approved merge.
No changes to user-installed Windows, local files, USB, backup
disk or Fedora host. See
[offline release gate](OFFLINE_RELEASE_CANDIDATE_GATE.md).

## Phase 15 — false-positive Windows-portable tests blocked

`verify_local.py` previously called plain unittest discovery for
each Windows-portable module. Python may exit with code 0 for
**zero discovered or all-skipped cases**. The new
`scripts/testing/run_portable_suite.py` checks each allowlisted module
against an actual executed-test count and refuses empty/missing,
unexpected, all-skipped, import-failed and incomplete runs. Some
platform-specific skips are allowed only when other tests actually
executed, and are disclosed as unverified.

The new `tests/test_portable_suite_coverage.py` was executed on an
isolated synthetic fixture (**7/7 PASS**); the actual Midnight Provisioner
Windows/Fedora test suites have **not** yet been run for the newest
GitHub commit. The branch also updates the 48-PR predecessor
snapshot and exact candidate references. See
[Phase 15 test completeness](PHASE15_PORTABLE_TEST_COMPLETENESS.md).

No PRs merged; Windows/Fedora/USB/portable backup media unchanged.

## Phase 16 — script mode Python package resolution fix (DRAFT)

Actual isolated Python 3.13 reproduction showed that unittest
discovery launched via `python scripts/runner.py` adds `scripts/`
and `tests/` but not necessarily the Midnight Provisioner package root.
This results in `ModuleNotFoundError` for legitimate
`from midnight_provisioner import ...` tests. The Windows portable,
Python Docker matrix and required Fedora GUI/native runners now
prioritize the exact current source root in `sys.path`.

New `tests/test_isolated_runner_imports.py` copies these
runner scripts into a disposable project with fake
`midnight-provisioner` test inputs and launches separate processes with
PYTHONPATH cleared; it detects successes and intentionally
missing packages. Local representative post-fix fixture tests
executed 65 / 75 / 5 cases without imports failing.
**The real latest branch's full tests are still NOT RUN.**

The branch `verification/phase16-isolated-import-paths` is
aligned across current verifier scripts and docs; the manifest
covers 49 predecessors (#1–29, #31–50; #30 absent). No merge,
Windows 11 Pro installation, Fedora host acceptance, USB
formatting or portable example backup-drive capacity backup-media writes occurred.
See [Phase 16 evidence](PHASE16_IMPORT_PATH_VERIFICATION.md).

## Phase 17 — Windows QEMU named-test completeness

The Windows-only `test_kali_process_label.py` subset previously
used multiple `unittest -k` filters. If a selected method were
renamed or removed, the remaining matching tests could still
return success. The new `scripts/testing/run_windows_qemu_subset.py`
requires each of the **14 selected names** exactly once and
zero skipped/failed cases. The original file contains 15 tests;
one intentionally omitted provenance test is not promoted to
Windows coverage without a separate review.

The new `tests/test_windows_qemu_subset_integrity.py` passed
**7/7** real tests on isolated local fixtures, and matching Git
blob hashes confirm the same files were committed. **Native Windows
and cumulative Python/Fedora Docker tests remain NOT RUN.**
See [Phase 17 test evidence](PHASE17_QEMU_TEST_COVERAGE.md).
