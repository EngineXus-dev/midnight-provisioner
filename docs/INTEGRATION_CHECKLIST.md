# Nightglass integration and no-Actions verification

**Status: INTEGRATION HOLD — do not merge until tests and reviewer approval.**

Nightglass is developed as a cumulative chain of **29 open draft pull
requests** as of October 9, 2026. No PR has been merged. PR #1 targets
\`main\` and each following PR targets the preceding phase branch.
Draft PR #30 in this workstream adds a manual test entry point and
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

For source syntax and the full synthetic unit suite, no sudo or actual
VM is required:

\`\`\`bash
python3 -B scripts/verify_local.py
\`\`\`

To narrow down just the latest Kali security/recovery changes:

\`\`\`bash
python3 -B scripts/verify_local.py --focused
\`\`\`

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

## 4. What remains blocked

- Fix and rerun genuine code regressions using local results. An
  identified recent defect in \`tests/test_kali_process_label.py\`
  placed the synthetic \`/proc/PID/stat\` process start time one column
  early (field 21 instead of Linux field 22); the fixture is corrected
  on this integration branch. This is **not** proof that it was the only
  failure in PR #29's hosted CI.
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

Keep PR #1 through #30 as **drafts**. Use the newest cumulative branch
for regression verification rather than wasting Actions on every PR.
When tests and physical safety gates appropriate to the phase are
met—and the repository owner **explicitly authorizes merges**—integrate
from the bottom of the stack in dependency order. Favor regular merge
commits to preserve ancestry. Before each merge, verify the next PR's
base, diff, tests, and effect on pending stacked branches. Do not
automatically close, squash, cherry-pick, reset, delete or rebase the
whole stack.

This guide is procedural. It is not a claim that the suite has passed
locally or that the existing draft PRs have been merged.
