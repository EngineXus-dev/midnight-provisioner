# Phase 6–7 — draft PR integration readiness (read-only)

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Phase 7 correction:** the original source-audit proposal expected the
snapshot JSON to exist in the user's original `main` checkout.
That was wrong: the file exists only in the unmerged draft branch.
The new auditor reads it from the **verified candidate Git object**
without branch checkout or overwrite. It now includes **40 predecessor
draft PRs (#1–29 and #31–41)**. PR #30 is absent. See
[remote-ref audit fix](REMOTE_REF_STACK_AUDIT.md). Current tests of this
new candidate have NOT yet executed. No PR is merged or approved.

## Historical Phase 6 snapshot (PRs through #40)


**Current state: SOURCE AUDIT IMPLEMENTED, TESTS NOT YET RUN.**
No Nightglass changes have been merged to main. No Windows 11 Pro
install, Fedora install, USB preparation, BitLocker/TPM change,
Windows debloat script execution or Linux VM has been performed.

## What GitHub actually showed (2026-10-09 snapshot)

GitHub metadata was checked for PR #1 through PR #40. **39 PRs
were open drafts and unmerged; PR #30 returned NOT_FOUND**.
Each observed PR has a base equal to the previous PR's head, beginning
with PR #1 into main. This is one *dependent stack*, NOT 39
independent changes ready to merge in arbitrary order.

Comparing main with draft PR #40's head on October 9 showed
**454 commits ahead, zero behind, 136 changed files**. Among
the changed paths was **.github/workflows/verify.yml**. The presence
of a GitHub Actions workflow requires manual review of triggering
conditions and permissions before integration, especially because
hosted Actions minutes are currently exhausted. No GitHub Actions
jobs have been started by this audit.

These observations represent an initial GitHub metadata snapshot;
the **local audit tool cannot re-confirm live GitHub draft/review/merge
status** from offline Git refs. A remote branch may have changed
since the snapshot. An audit result is never merge approval.

## Implementation

Files:
- `config/nightglass-pr-stack-snapshot.json` — explicit PR #1–29,
  #31–40 base/head chain, PR #30 marked missing, candidate branch,
  and mandatory external review gates
- `scripts/Audit-Nightglass-PR-Stack.py` — no-write plan-only
  default, opt-in local Git ancestry/path inspection
- `tests/test_pr_stack_audit.py` — synthetic offline safety
  tests, including forged/nonlinear graph, missing #30,
  modified main, workflow alerts, and no-merge constraints

The auditor always reports `merge_authorized=false`,
`deployment_approved=false`, and separate FALSE values for current
GitHub PR status verification, ref freshness, test evidence and
physical Fedora hardware acceptance.

### Command modes

**Default plan** (no Git calls, filesystem changes or network):

    python scripts/Audit-Nightglass-PR-Stack.py

**Read-only local verification** on an explicitly prepared candidate
checkout (does not fetch branches or alter worktree files):

    python scripts/Audit-Nightglass-PR-Stack.py --repo "." --verify

The tool requires all 39 **already fetched** origin tracking refs,
an origin URL exactly matching EngineXus-dev/nightglass-workspaces,
local main ref equal to origin/main, and a candidate ref at
origin/verification/stack-integration-readiness. It performs
`git merge-base --is-ancestor` for every PR base/head,
main/candidate history comparison, and path-name-only diff review
from main to the candidate. It never runs git merge, reset, clean,
rebase, checkout, push or GitHub Actions.

You can optionally supply the full SHA independently copied from
the draft PR head:

    python scripts/Audit-Nightglass-PR-Stack.py --repo "." --verify --expected-candidate-sha "<40-hex-SHA>"

The script will BLOCK if that SHA does not match the local remote
tracking ref. The SHA is not a user password.

**Fetching missing refs is separate, explicit Git metadata work:**

    git fetch --no-tags origin

This may transfer substantial history (the stack was already
454 commits beyond main at the snapshot) and update remote tracking
refs, but normally does not overwrite local tracked, untracked,
.env or .venv files. Do not use `git pull`, `reset --hard`,
`clean`, a force push or a mass script that replaces project
folders. Do not attempt to reduce the stack by merging draft PRs
without explicit later approval.

For an optional NEW JSON report, add `--report "new-report.json"`
along with `--verify`. Existing reports are never overwritten.

### Conditions for a local graph-only PASS

- Complete exactly ordered 39-PR manifest, no fictional PR #30
- Valid branch names with no control/path ambiguity
- Authorized Git origin and unchanged local main SHA
- Every local origin/head ref resolves to a single 40-character SHA
- Every PR head descends from its corresponding base
- Latest candidate descends from PR #40
- No main-only commits that the candidate omits
- Diff path names identify any flagged workflow, potentially
  secret-bearing or OS-deployment/binary paths

Even if all pass, the status is **LOCAL_GRAPH_ONLY, REVIEW REQUIRED**.
A verified branch chain cannot prove that the correct source code
is safe, that every GitHub PR is still draft, or that isolated
Windows/Fedora tests passed. Reviewing workflow source and full
pull-request diffs and verifying the latest exact-SHA cumulative
test evidence remain mandatory.

### Integration approach (future only)

**Do not blindly click Merge 39 times.** A safer future approach is
to produce and independently review one *cumulative integration
candidate* from the approved stacked head against main, with
independent tests and rollback plan, while keeping the original
draft PR stack and history intact. A single cumulative PR still
contains ALL dependent changes and requires careful review; it is
not magically less risky than the component PRs.

If the owner later approves integration, use ordinary reversible
Git commits or a merge commit, preserve original branches, and
prepare a documented revert strategy. Never squash 454 commits
or force-push main without a separate, specific reason and consent.
Do not treat synthetic Qt/QEMU fixtures as a substitute for actual
Fedora SELinux/KVM/sVirt, offline network, guest restore or Windows
11 hardware acceptance.

## Separate user-requested deployment remains deferred

Windows 11 Pro clean install on the internal 500 GB disk is future
work. User has a Pro key and may activate it **later** by choosing
the no-product-key option in genuine setup *if shown*, ensuring
Windows 11 Pro is selected, and entering the key later in Settings.
OneDrive/AI/Xbox/privacy customizations are staged but not executed.
The user-confirmed example backup-drive capacity portable drive is BACKUP ONLY; the separate
16 GB USB is a possible ISO media target only after independent
contents/capacity checks and explicit authorization.

See RELEASE_EVIDENCE_AUDIT.md and
OFFLINE_RELEASE_CANDIDATE_GATE.md for the separate test evidence gate.
