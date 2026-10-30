# Midnight Provisioner Phase 21 — Windows recovery diagnosis without system changes

**Status:** DRAFT / strictly read-only / deployment blocked. Stacked on PR #58 at verified Phase 20 SHA `ac650554f7e8dbcfbdb630157e4ea2827b8e1ea0`.

## Purpose

The earlier native Phase 20 check reported WinRE status **UNKNOWN**, without distinguishing absent `reagentc.exe`, an unsuccessful command invocation or an output format the parser could not recognize. The report did **not** establish Windows recovery failure. Phase 21 adds `scripts/windows/Read-Midnight-Provisioner-WinRE-Triage.ps1` to categorize why the non-elevated Windows RE inspection is inconclusive, while still treating every observed result as insufficient for recovery or installation approval.

The new observer uses only Windows' real `[Environment]::SystemDirectory` and `reagentc.exe /info`, a documented read-only status query. It never invokes `/enable`, `/disable`, `/boottore`, DISM, BCD changes, BitLocker changes, disk operations, a reboot, elevation or VM tools. It does **not** download files or create a report file; it emits a bounded, sanitized JSON value to stdout. The separate opt-in operator harness preserves that JSON and test logs in uniquely named archives.

The WinRE reason is one of **OS_ROOT_UNAVAILABLE**, **UTILITY_MISSING**, **UTILITY_NONZERO_EXIT**, **UTILITY_INVOCATION_ERROR**, **UTILITY_OUTPUT_TOO_LARGE**, **UTILITY_OUTPUT_EMPTY**, **UTILITY_OUTPUT_UNRECOGNIZED**, **STATUS_ENGLISH_ENABLED**, or **STATUS_ENGLISH_DISABLED**. The last two require a single unambiguous English WinRE status line. Localized or inconsistent text stays unknown. The process token is labeled **STANDARD_TOKEN**, **ADMINISTRATOR_TOKEN**, or **UNKNOWN** without exposing the account identity, and the program does **not** request an elevated token. Do not infer a particular reason for earlier Phase 20 UNKNOWN from today's result alone.

### Privacy and authorization

Raw REAgentC command output can contain recovery image locations and BCD identifiers. It is always discarded and never published, logged, zipped or uploaded to GitHub. The JSON schema is `midnight-provisioner.winre-triage.v1`, with **status=HOLD_INDEPENDENT_RECOVERY_EVIDENCE**. All the following always remain **false**: Windows recovery boot proof; recovery media possession; independent backups; real restoration proof; BitLocker key custody; clean NTFS shutdown; Secure Boot validation; ISO provenance; Fedora physical isolation; Windows/Fedora install, partition/disk write and VM-start permission.

An **ENABLED** status is a configuration observation, not proof that WinRE boots or recovers any files. An unrecognized string is not proof it is disabled.

## Independent tasks that still block deployment

1. Confirm Windows RE locally with an authorized administrator if the non-elevated observation cannot read status. Keep raw output private; **do not paste `Windows RE location`, BCD identifiers, raw volume maps or keys into a GitHub issue or chat**.
2. Verify possession of separately stored Windows recovery media and any device/BitLocker recovery keys, without uploading key material.
3. Independently verify complete Windows/data backup coverage and perform a controlled restore into a clean/disposable destination before installation plans. Existing `Verify-Midnight-Provisioner-BackupSet.py` can verify selected file copies but does **not** certify a complete machine image or restore.
4. Safely resolve the Fast Startup/hibernated NTFS risk before Linux read-write access; no setting is altered by this phase.
5. Confirm Secure Boot and OS encryption in Windows settings/firmware, review Windows 10 servicing/ESU, identify physical EFI/Recovery/OEM partitions.
6. Verify Fedora KDE image **signature and checksum from trusted Fedora sources**, then separately approve a live-USB hardware trial (no installer/disk changes yet).
7. Only after a separately authorized installation and independent backups: physically validate Fedora KVM/libvirt, SELinux/sVirt, offline guest traffic denial and controlled cold recovery.

Official source: Microsoft [REAgentC /info](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/reagentc-command-line-options); Microsoft [WinRE inspection](https://support.microsoft.com/en-us/servicing/os/windows/safeos-du/2026/03/methods-to-verify-the-winre-version-installed).

## Source-level verification

`tests/test_phase21_winre_triage.py` contains eight cases: seven cross-platform static/no-write/privacy safety checks plus a native Windows-only **PowerShell 5.1 AST parser** check. No actual REAgentC command is executed by the unittest suite. All eight must run on the operator's Windows host before collecting observations; Fedora syntax/suite checking can validate the seven platform-independent cases separately. The v21 operator runner must pin an exact SHA and abort if GitHub's branch head differs. Leave all PRs draft and unmerged, preserve old failed and successful evidence, and never modify the operator's `main`, `.env`, `.venv`, backup or USB disks.

**Even if every Phase21 software test passes, actual dual-boot deployment and physical guest isolation remain unverified and unauthorized.**
