# Nightglass integration and no-Actions verification

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

- Test the entire latest cumulative code on Python 3.11/3.12/3.13
  where available, Qt offscreen and native fixtures.
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
packet-level network denial, guest cold restore or Python 3.11–3.13 results.
Existing draft PRs remain unmerged.


## Next draft phase: Fedora host prerequisites and Python compatibility

A new **unmerged** stacked branch, verification/fedora-host-acceptance-preflight,
starts from the verified Fedora Docker integration branch. It introduces:

- Read-only, nonroot Fedora OS / SELinux / KVM / libvirt prerequisite audit
  with opt-in, exclusive-create 0600 evidence, and synthetic negative tests
- A manually supervised real-host acceptance plan; no VM boot is automatic
- An opt-in Windows Docker Linux headless test matrix for Python 3.11–3.13,
  with separate read-only containers and no GitHub Actions

**Implementation is NOT evidence that either the real Fedora host audit
or new 3.11–3.13 matrix has been run.** These remain pending user-run
verification, alongside benign guest boot, packet-level network
isolation, effective host SELinux/sVirt contexts, cold recovery and
explicit integration/merge approval.

Do not merge any draft PR as part of this phase. See
[Fedora host prerequisite plan](FEDORA_HOST_PREFLIGHT.md) and
[Python compatibility matrix](PYTHON_COMPATIBILITY_MATRIX.md).
