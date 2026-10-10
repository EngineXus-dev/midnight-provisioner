# Nightglass — Owner Merge & Next-AI Handoff

**Authority and intent:** This repository is the source of Nightglass Workspaces, independent of EngineXus/Enginexus/YenEngine. The human repository owner — **not the next AI and not this handoff** — chooses if and when to merge the cumulative integration PR into `main`. Preparing a PR as *ready for review* does not authorize a merge, OS installation, destructive disk operation, or production deployment.

## One cumulative GitHub change to review

- Repository: `EngineXus-dev/nightglass-workspaces`
- Cumulative PR: **[#66](https://github.com/EngineXus-dev/nightglass-workspaces/pull/66)**, head `integration/review-merge-stack`, base `main`.
- Source main snapshot at the start of this integration: `7ed599e9724551fffc203203a1ab4173bb7510c9`. **Check current live base and head SHAs immediately before review/merge; they are not fixed by this document.**
- PR #66 carries the original dependent chain: #1–29, #31–52, #54–65 (63 linked draft PRs). PR #30 never existed in that series. PR #53 forked separately from #52 and **must not be blindly merged or cherry-picked**; see `docs/PR53_DIVERGENT_BRANCH_RECONCILIATION.md` and historical triage.
- Do not merge the original 63 PRs individually before or after merging the cumulative PR. Retain their branches and PR metadata as history until the owner explicitly disposes of them. Do not force-push or rewrite `main`.

## Deliverable and actual capabilities

The deliverable is a **Fedora KDE Nightglass Python application source tree**, with CLI and PySide6 interface, Qubes-inspired workspace organization, distinct Kali-purpose template profiles, offline-analysis and development contexts, libvirt/QEMU and Distrobox integrations, Windows/Fedora discovery and conservative device recognition, install-impact previews, recovery/backup checks, and tests. Some features are read-only plans/gates rather than deployed enforcement. Read `README.md`, `docs/INTEGRATION_RELEASE_CANDIDATE.md`, `docs/SECURITY_MODEL.md`, `docs/KALI_TEMPLATES.md`, `docs/PHASE23_FIRST_RUN_DISCOVERY.md`, and `docs/PHASE27_UNTRUSTED_PROPOSAL_REVIEW.md` for exact behavior.

**Not delivered:** a bootable Fedora installer or OS image; a customer-ready Windows binary; a proved Windows/Fedora dual-boot; proven physical KVM/SELinux/sVirt isolation or VM containment; a disk formatter; verified external backups or recovery from them; or a deployable appliance. `scripts/setup-nightglass.sh` is application setup on an already-installed Fedora host, not an OS installation. No physical disks, EFI, USB media, firmware, installed OSes, backups, or hardware VMs were modified during this PR integration work.

## Verification ledger — do not overstate

1. **Phase 27 predecessor #65** was verified independently on Windows and in a cached Fedora 43 container at its exact source SHA `2902acbeb1402cf1fc18d0374aad4951bd8d60a2`: Windows 65 passes and two symlink-permission skips; Fedora 681 collected, 646 pass and 35 expected skips; separately, 27 offscreen PySide6 GUI tests and six native libvirt/QEMU fixture tests. These are predecessor results only, not current-PR acceptance.
2. **RC66 source `c4aafee38ef1019c6e33399498b21354b6f7fb48`:** Windows integration snapshot 7 pass; Phase24 8 pass; Phase25 16 pass; Phase26 12 pass; Phase27 18 run with one skip; Phase23 13 run with one skip. The nine-case Git synthetic graph suite hit the 75-second process timeout (exit 124) before final unittest summary. Native proposal review, Fedora suite and source packaging were correctly blocked.
3. **RC66 optimization `f09f7b505857039e0c2adff2ca072d9fc02349e1`:** graph history is created once per class and the deliberately mutated disposable Git refs are reset per test; nine original cases retained. This source change was committed, but fresh Windows/Fedora results were not obtained.
4. **RC66 isolation correction `1d41ed3794d5a67a0b9e0f83d542bbabeb14445e`:** fixes a newly identified flaw in the optimization: tests shared and mutated the same Python manifest. Now the expensive Git fixture stays shared while `copy.deepcopy(cls.base_data)` provides isolated per-test input, with additional assertions against state leakage. **The full suite has NOT yet been reported as passing on this correction or later documentation-only commits.**
5. GitHub Actions minutes were exhausted; `.github/workflows/verify.yml` on this branch has explicit `workflow_dispatch` only, without automatic push/PR triggers. No completed Actions status should be inferred from an empty check list.
6. Earlier Windows evidence was preserved under `Documents/Nightglass-Verification-Results` on the user's PC, and old reports are not proofs for a new head. Never relabel synthetic, container or mock tests as real Fedora host acceptance.

## Owner merge review checklist (pre-merge)

- [ ] Confirm PR #66 targets `main`, is conflict-free, and its exact SHA matches the reviewed checkout/evidence. No unexpected new commits or base drift.
- [ ] Review the *complete cumulative diff*, especially `.github/workflows/verify.yml`, storage discovery and destructive-operation boundaries, dependency/build scripts, potential secrets, `.env` files, binaries or VM images.
- [ ] Review the deliberate PR #53 fork disposition; do not silently fold its stale candidate-SHA edits back in.
- [ ] Run all nine synthetic graph regressions and seven source RC contract tests on the **current** candidate SHA, plus the required Windows Phase23–27 synthetic/CLI tests; do not accept timeout exit 124, missing suite summaries or unexplained skips.
- [ ] Independently run Fedora 43 full tests in a source-isolated container, real PySide6 offscreen tests and native libvirt/QEMU fixture checks on that same exact candidate SHA. CI is optional if quota-limited; evidence must identify the SHA and any skipped tests.
- [ ] Check the pinned integration snapshot with `scripts/Review-Nightglass-Integration.py`. Its `merge_authorized=false` value is an intentional non-authorizing safety result, not a CI failure. A script cannot grant owner authorization.
- [ ] **Owner personally approves the actual merge**, with no automatic merge of old drafts. Prefer a normal **merge commit** to preserve cumulative history. Do not force push.
- [ ] Post-merge, verify `main` contains the intended commit, check the merge commit, and keep the PR graph and evidence accessible.

**Current readiness:** PREPARED FOR OWNER REVIEW; NOT VERIFIED OR APPROVED FOR MERGE by full current-head Windows/Fedora acceptance. No code or document claiming verification can replace running these gates.

## After the owner merges — safe Windows pull

Local location historically: `%USERPROFILE%\Documents\nightglass-workspaces`. Existing local untracked files, `.env`, `.venv`, data and local edits must be preserved.

In that existing directory, inspect first:

```powershell
git status --short
git branch --show-current
git fetch --no-tags origin main
git log --oneline -3 origin/main
```

If on `main` and with no conflicting local edits, the owner may then choose `git merge --ff-only origin/main`. If the fast-forward cannot proceed, **stop and inspect** rather than `git reset --hard`, `git clean`, force-push, or replacing local project folders. Do not overwrite local secrets or environments. Do not assume fetching or merging installs Fedora.

## Next AI's starting instructions — after owner merge

Use merged `main` as the authoritative starting baseline and compare its final Git SHA to the owner's merge result. Do not merge PRs or alter system disks. Audit the implementation against `docs/INTEGRATION_RELEASE_CANDIDATE.md` and security/acceptance docs; separate working capabilities from previews, mocks, stubs and unverified claims. Prioritize reproducible current-head tests, real Fedora GUI and KVM/SELinux/sVirt isolation testing, safe installer engineering with explicit target confirmation, Kali-purpose template lifecycle, dual-boot/recovery and release packaging. Preserve source history, evidence, manual-consent gates and local private data. Changes must be reversible and proposed through independent feature branches/PRs, never overwrite the owner's working checkout.

This handoff is source documentation, not a verified release, merge authorization, or deployment instruction.
