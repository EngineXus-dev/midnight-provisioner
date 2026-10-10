# Nightglass Phase 20 — Native Windows recovery posture, read-only

**Project branch:** `safety/phase20-windows-recovery-posture` (stacked draft on PR #57). **No install/partition/USB/VM authorization.**

Phase 19 passed the defined Windows and Fedora 43 container test gates at `81aa392df0b388c3f19bc55de803343c56d7c98e`. Phase 19 still reported 15 unresolved prerequisite checks, including Fast Startup, Windows recovery/backup and Secure Boot/device encryption. Phase 20 narrows those unknowns without requesting elevation or modifying the machine.

## New observer

`scripts/Read-Nightglass-Recovery-Posture.ps1` uses only:

- `reagentc.exe /info` to read Windows Recovery Environment (WinRE) status (Microsoft documents **/info** as the display-only operation).
- `powercfg.exe /a` to view **available** sleep states (NOT to enable/disable hibernation).
- `Get-ItemProperty -Name HiberbootEnabled` for the already-observed Fast Startup registry flag.

Both executable locations are derived from the running Windows system directory; both argument lists are fixed, non-configurable and read-only. Failure to read, ambiguous output and non-English output are reported **UNKNOWN**. Only bounded summaries are returned in JSON; the raw `reagentc` output may contain WinRE and BCD paths or identifiers and is intentionally discarded.

The report has schema `nightglass.windows-recovery-posture.v1`, mode `READ_ONLY_NON_ELEVATED_WINDOWS`, always reports `HOLD_MANUAL_RECOVERY_AND_DEPLOYMENT`, and keeps EVERY recovery, backup, credential, NTFS clean-shutdown, ISO authenticity, Fedora isolation, install, disk-write and VM-start assertion **false**.

**Do not misread any observation as proof:** Enabled WinRE does not mean recovery media can boot or data can be restored. `powercfg /a` describes capabilities rather than a clean current NTFS state. A disabled `HiberbootEnabled` registry flag alone is not a proof of a clean current shutdown. Secure Boot and BitLocker custody stay independent manual checks.

### References (official)

- Microsoft REAgentC `/info`: https://learn.microsoft.com/windows-hardware/manufacture/desktop/reagentc-command-line-options
- Microsoft powercfg `/a`: https://learn.microsoft.com/windows-hardware/design/device-experiences/powercfg-command-line-options
- Microsoft SecureBoot PowerShell privileges: https://learn.microsoft.com/powershell/module/secureboot/confirm-securebootuefi
- Fedora signed image checks: https://fedoraproject.org/security/

Per Microsoft, `Confirm-SecureBootUEFI` requires Windows PowerShell **administrator** privilege. Phase20 does **not** elevate or falsely report a non-admin Secure Boot query as verified; check `msinfo32` or firmware manually.

## Backup/recovery gate remains independent

The existing `scripts/Verify-Nightglass-BackupSet.py` can read source/backup pairs **only when** the operator supplies an explicit PRIVATE manifest; it hashes a bounded set of selected files and does not modify either copy. This can provide byte-match evidence of selected folders but cannot prove full-machine backup completeness or successful restoration.

The operator must still, privately, confirm: a verified independent full-system backup and recovery medium, a controlled restore into a disposable/new target, offline Windows/device-encryption recovery keys, exact physical EFI/recovery/OEM layout, Windows 10 support/ESU coverage, authentic signed Fedora KDE checksum, live-USB hardware support, and, later on an authorized Fedora installation, KVM/libvirt/SELinux/sVirt guest and offline network-denial isolation.

No utility in this phase copies personal files, writes a bootloader, formats disks, changes firmware settings, disables Fast Startup, turns BitLocker on/off, writes a Fedora USB, starts a guest, reboots, or installs an OS.

## Verification and retention

Phase20 adds 8 static/unittest contracts including one Windows-only **real PowerShell 5.1 AST parsing** case. These are not Windows hardware tests. The external operator script must be pinned to the exact Git commit, use a new detached worktree, run tests before observing host state, validate the output schema/flags, and store **both passing and failed results** with SHA-256 in `Documents/Nightglass-Verification-Results`. No automatic Git merges, `git clean`, reset, overwrite of working checkout or edits to private env files.

After the Windows gate, running the unchanged Fedora container **new source** tests (Windows-native case skipped) on a separate exact-SHA Linux gate is still useful, but no container represents real physical Fedora acceptance.
