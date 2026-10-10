# PR #53 divergence reconciliation — no silent merge

**Recorded October 10, 2026.** Nightglass has 63 open draft PRs on the principal chained path: #1–29, #31–52, #54–65. Draft #53 is a **separate child of #52**, diverged from #54 and therefore never an ancestor of the cumulative candidate. PR #30 does not exist in this sequence. The later mainline was independently tested through #65; the same tests do not imply physical hardware acceptance.

## PR #53's 16 changed files compared with current mainline

The PR was a response to an interrupted Windows synthetic test run against #52. It included:
- Windows-only fabricated-QEMU-test fixture monkeypatch for a POSIX file-mode syscall. Mainline \`tests/test_kali_process_label.py\` instead uses narrowly scoped patches on the production-module references, so the specific Windows synthetic failure is addressed **without modifying Fedora production mode enforcement**.
- A corrected literal assertion for \`if ($disk.Number -eq $osPartition.DiskNumber) { continue }\`. That assertion is **already present** in the linear mainline's \`tests/test_windows_dualboot_review.py\`.
- Identification of \`secrets/\` as a sensitive path in the PR-stack auditor; the mainline scanner already includes both \`"secret"\` and \`"secrets"\`.
- A new historical test-triage document and README/status notes.
- Candidate SHA/branch-number rewrites across older release-gate scripts, PR manifests, and their tests. These point specifically at PR #53 as the latest candidate and **must not be transplanted to the latest release**; they are superseded, could make the current gate test the wrong code, and would break later cumulative source contracts.

The source file \`docs/HISTORICAL_PR53_WINDOWS_FAILURE_TRIAGE.md\` preserves PR #53's original triage account verbatim under a historical path, without implying that its original runtime claims or stale candidate constants apply to today's code.

## Disposition and explicit blockers

**Do not automatically merge or cherry-pick PR #53.** Reconcile its semantics via the three mainline fixes above; retain the untouched PR and original git history until final independent review or explicit user instruction to close it as superseded. The PR's stale metadata changes are deliberately excluded from the cumulative integration candidate.

**No attempt is made to disguise the fork as merged.** The checked candidate is cumulative branch PR #65 plus transparent integration-only files. No Windows/Fedora OS installation, EFI changes, USB formatting, external backup manipulation, VM launch or GitHub default-branch merge is authorized. Before any merge, require an owner review of the exact cumulative diff, scan for secrets/binaries, run full exact-source Windows/Fedora Qt regressions, verify main has not advanced and confirm explicit owner approval.
