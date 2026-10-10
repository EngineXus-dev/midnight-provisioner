# Phase 7 — verifying the existing main checkout without checking out draft code

**Draft only / no deployment / no merges.** This phase corrects a
practical integration issue in the prior stack auditor: the snapshot
JSON existed only in the newest draft branch, while the user's real
Windows checkout was on **main**. The old auditor tried to read a
manifest file from that main working tree, causing a false failure
unless the user switched branches—contrary to the project requirement
to preserve local and untracked files.

## Solution: read one immutable, fetched Git object

`scripts/release/Audit-Nightglass-PR-Stack.py` now reads the manifest from
the **full 40-character SHA** of
`refs/remotes/origin/verification/remote-ref-stack-audit` using:

    git show <VERIFIED_COMMIT_SHA>:config/nightglass-pr-stack-snapshot.json

That command only reads Git's local object database. It does **not**
checkout or copy the candidate into the user's working tree. The
auditor fails closed on absent refs, invalid/oversized JSON,
duplicate fields, a broken base/head chain, unexpected PR numbers
or diverging histories.

The manifest includes **40 existing draft PRs (#1–29, #31–41)**,
with PR #30 genuinely absent from the earlier GitHub query. The
present candidate will become a **new draft PR #42**, stacked on
#41; the file intentionally tracks only its existing ancestors.
Live PR status still requires a new independent GitHub query before
any integration.

## GitHub Actions workflow review

The same pinned Git object also supplies
`.github/workflows/verify.yml`. The auditor implements a small,
strict, **not general-purpose YAML** review:

- Exactly **manual** `workflow_dispatch` in the top-level
  trigger block; **no push, pull_request, schedule or workflow_run**
- Exactly one global token permission block:
  `contents: read`
- No job-level permission overrides or self-hosted runner declarations
- Any `uses: action/name@vN` entry is recorded as a
  **mutable-action-tag review item**, not quietly treated as an
  immutable pinned digest

The observed workflow used only manual dispatch with read-only
token permissions and **seven mutable major-version action refs**
(`checkout@v4`, `setup-python@v5`,
`upload-artifact@v4` repeated across jobs). This supports
keeping CI **disabled for now**, not enabling GitHub Actions or
proving all third-party action code safe. GitHub Actions minutes
remain exhausted. Actual job scripts, dependencies and action
version pinning need human review before future workflow activation.

## Safely run the existing main checkout on Windows

On the user's **original Nightglass main directory** in PowerShell,
after reviewing the source for the proposed audit:

```powershell
# Updates Git remote-tracking metadata; does NOT check out/merge.
git fetch --no-tags origin
if ($LASTEXITCODE -ne 0) { throw "Nightglass fetch failed" }

$folder = Join-Path $env:TEMP ("Nightglass-StackAudit-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $folder | Out-Null
$audit = Join-Path $folder "Audit-Nightglass-PR-Stack.py"

$source = git show origin/verification/remote-ref-stack-audit:scripts/release/Audit-Nightglass-PR-Stack.py
if ($LASTEXITCODE -ne 0) { throw "Failed to obtain audit script" }
$source | Set-Content -LiteralPath $audit -Encoding UTF8

# Safe plan only; no Git calls.
python $audit --repo (Get-Location).Path

# If explicitly desired, check already-fetched local Git refs.
$expected = git rev-parse refs/remotes/origin/verification/remote-ref-stack-audit
if ($LASTEXITCODE -ne 0) { throw "Candidate Git ref missing" }
python $audit --repo (Get-Location).Path --verify --expected-candidate-sha $expected
```

If some older draft PR branches were not fetched, the local
verification reports **BLOCKED**; it does not substitute imagined
SHAs or automatically fetch extra remotes. `--verify` never writes
a report unless an optional *new* `--report` file is explicitly
requested. `main`, `.env`, `.venv`, untracked files, local datasets,
portable drive and firmware remain unchanged by the auditor.

## Verification status

GitHub source inspection confirmed the new 40-PR JSON snapshot
order, pinned Git object reading, strictly manual workflow trigger,
read-only token and mutable action-tag flags. Those are **static
checks**, not actual Python unit tests or a native Windows run.
The unit tests and newest cumulative Fedora/Docker tests **remain
NOT RUN**, and no `git merge` or GitHub Actions job was triggered.

Success would establish only local Git graph consistency and some
limited workflow configuration invariants. It would **not**
authorize PR integration, Windows 11 Pro installation, USB
formatting, Fedora dual boot, hardware SELinux/KVM/sVirt acceptance,
or automatic execution of the staged debloat changes.

See [stack integration decision gates](PR_STACK_INTEGRATION_READINESS.md),
[offline exact-commit runner](OFFLINE_RELEASE_CANDIDATE_GATE.md)
and [independent evidence audit](RELEASE_EVIDENCE_AUDIT.md).
