# Nightglass Phase 22 — recovery and backup acceptance evidence (read-only)

**Status: DRAFT; deployment authorization remains BLOCKED.** Stacked on Phase 21 draft PR #59, previously verified at exact SHA `5e40ae0428684e29c6d492f4dfd8ab11369c9ec4`.

## Objective

Replace repetitive synthetic readiness checks with useful **private evidence for actual backup coverage and Windows recovery preparation**, without making any claim that an OS can be reinstalled safely. Phase 21's non-elevated `reagentc /info` attempt returned `UTILITY_INVOCATION_ERROR` under a standard token. That did **not** establish whether WinRE is enabled, disabled, broken, or unbootable. Phase 22 preserves that uncertainty and allows a later independent authorized manual query.

### New offline evidence reviewer

`scripts/backup/Review-Nightglass-Recovery-Backup.py`:

- **Preview (default)**: does not read *any* files or media.
- **Assess**: accepts an explicit sanitized `nightglass.winre-triage.v1` JSON report; optionally a separate `nightglass.backup-set.v1` report generated in `--mode Verify` by `scripts/backup/Verify-Nightglass-BackupSet.py`.
- Rejects contradictory approval assertions, duplicate-key JSON, malformed report schemas, oversized payloads, symlink/reparse files or ancestor paths, missing or inconsistent selected-backup groups and unsafe raw file paths in standard fields.
- Produces `nightglass.recovery-backup-acceptance.v1` JSON with selected-folder hash match counts, outstanding requirements and a permanent `HOLD_RECOVERY_BACKUP_AND_PHYSICAL_ACCEPTANCE` status.
- **Does not** open original backup files, write a report file, copy or restore data, scan Windows storage automatically, download an ISO, enable BitLocker/WinRE, elevate, write an installer/USB, start a guest, modify boot/EFI or change Windows power policy.

Even a **CONTENT_MATCH** result proves only that the selected directory pairs' contents matched at verification time. It does not prove external-drive independence, a full-machine image, the scope of personal/cloud/VM/container data, successful restoration, or safe Windows/Fedora installation. A supplied JSON report may be forged; its existence is NOT cryptographic origin proof.

### Optional genuinely useful selected-folder comparison

To collect direct, private content evidence, the operator must first create their own **PRIVATE** JSON mapping outside GitHub as described in `docs/MULTI_SOURCE_BACKUP_READINESS.md` and `examples/backup-set.EXAMPLE.json`:

```json
{
  "version": 1,
  "entries": [
    {
      "id": "projects",
      "source": "C:\\REPLACE_WITH_REAL_SOURCE",
      "backup": "E:\\REPLACE_WITH_REAL_BACKUP"
    }
  ]
}
```

Do not assume `E:` or an existing drive number identifies the right physical disk. Do not copy this example unchanged or upload your real private path list. The optional checker is run in **Verify** mode only after the operator explicitly supplies its exact manifest file path. It streams SHA-256 for each regular file in explicitly selected source/copy roots, including hidden `.env` and `.venv` if included, but outputs neither the file content, private paths nor hashes. A large scan can take considerable time; stop active writers first and confirm the chosen external media independently. A hash match on selected folders is NOT the same as testing the restoration of a real system backup. Empty or mismatching backup pairs cause a HOLD.

The separate one-click Windows runner is pinned to an exact source SHA and:

1. Runs the eight Phase 21 WinRE source/AST safety tests and the 13 Phase 22 evidence tests **before** any read-only host query.
2. Creates a new isolated detached Git worktree; no pull, reset, clean or merge to the user's checkout.
3. Re-queries non-elevated WinRE status only using its reviewed `reagentc /info` tool; no admin elevation.
4. With **no `-BackupManifest`**, does not read backup drives or hash data, and reports backup evidence NOT SUPPLIED.
5. Only with explicit `-BackupManifest "<PRIVATE-LOCAL-JSON>"` plus `-VerifyBackupSet`, runs the existing bounded read-only selected-folder verifier and passes its sanitized output to the Phase 22 evidence review.
6. Archives local tests, sanitized reports, SHA-256 inventory, exact SHA and both **passing and failing** results under `Documents\Nightglass-Verification-Results`; never bundles the PRIVATE manifest or raw WinRE text.

This is **not** a backup/restore creator. The user must separately decide and accomplish real backups and a safe controlled restore drill with trusted tools.

## Independent blockers before even planning dual boot

1. **WinRE:** Privately inspect `reagentc /info` in an explicitly user-opened elevated Windows console if appropriate. The only information to share is a coarse Enabled/Disabled/error category; raw WinRE/BCD locations stay private. Do not issue `reagentc /enable` or `/disable` through Nightglass.
2. **Independent recovery:** Verify genuine Windows recovery media, encryption recovery-key possession (keep private, never upload keys), correct system-image scope and an actual controlled restore to an independent/disposable destination.
3. **Windows shutdown:** Windows Fast Startup was observed enabled. Review its impact before Linux touches NTFS; do not auto-disable it or infer a clean shutdown from a flag.
4. **Windows security:** Resolve Secure Boot and encryption UNKNOWN statuses, verify Windows 10 supported servicing/ESU or a supported Windows upgrade, and review physical EFI/Recovery/OEM partition layout.
5. **Fedora authenticity and on-device behavior:** independently verify signed Fedora KDE checksum and live USB hardware support. **Do not create/write a USB or start an installer in this phase.**
6. **Security acceptance after separately authorized installation:** physical Fedora KVM/libvirt, SELinux enforcing and sVirt labels, offline guest packet-denial, memory budget, cold restore and Windows rollback.

Official Microsoft guidance: [REAgentC status](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/reagentc-command-line-options) and [Windows 10 servicing / ESU](https://support.microsoft.com/en-us/windows/deployment/updates-lifecycle/windows-10-support-has-ended-on-october-14-2025).

**No result in Phase 22 can grant OS installation, disk or USB writes, firmware changes, guest VM launch or repository merge.** All Nightglass PRs must remain draft/unmerged.
