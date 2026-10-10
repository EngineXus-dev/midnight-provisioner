# Phase 18 — native Windows host readiness (observation-only)

**State:** PRE-INSTALL REVIEW ONLY. Does not approve, prepare or perform any Windows/Fedora installation, disk resize, UEFI/bootloader change, encryption change, VM launch or USB operation.

## Why this gate follows PR #55

PR #55 has cross-platform **synthetic** Windows/Fedora container tests at exact SHA `af220ecd382ad59ce4f18694bbc2ae349be14589`. A container cannot prove physical Fedora/KVM/sVirt network isolation or backup recovery. First, collect a minimal, bounded read-only Windows posture report **on the machine that would eventually dual boot**.

The existing `scripts/Review-Windows-DualBoot.ps1` remains an interactive console inventory. This phase adds `scripts/Read-Nightglass-Windows-HostGate.ps1`, a **sanitized JSON-only observer** suitable for archiving and reviewing without accidentally disclosing full disk identifiers, serials, hostnames, personal file paths, machine GUIDs, TPM owner data or BitLocker recovery keys. It uses only native read queries and does not require elevation.

## Information observed (NOT certified)

- Windows OS family (10, 11, other/unknown), with explicit servicing uncertainty and no inference of Windows 10 Extended Security Updates enrollment
- Reported boot firmware mode and Secure Boot status
- Fast Startup registry flag, which is **not** proof that Windows is fully shut down
- OS volume BitLocker protection state only; recovery key possession is never checked or displayed
- Coarse system memory bucket and advisory CPU virtualization firmware flag
- Windows OS disk partition style and whether partition inventory can be queried; never a proposed installation target

If a Windows API cannot answer, output `UNKNOWN`. If a reported state may be unsafe, output `HOLD`. `OBSERVED` never means the environment is approved for modification.

The JSON schema is `nightglass.windows-host-observation.v1`. The status is **always** `HOLD_MANUAL_DEPLOYMENT_APPROVAL`, and every install/disk/backup/restore permission flag is **false**. The collector prints to stdout only, writing no file by itself. The opt-in operator runner archives this sanitized report and individual test evidence under `Documents/Nightglass-Verification-Results`.

## Required independent manual checks — all outstanding

1. Independent full-machine Windows and personal-data backups and a controlled file-restore trial on separately held media
2. Windows recovery media, keys and EFI/Recovery/Windows/OEM partition mapping, reviewed before any install or resize
3. Current Windows edition/build/security support: Windows 10 ordinary consumer servicing ended **October 14, 2025**; supported ESU or an upgrade must be checked **independently**, not assumed
4. Genuine Fedora KDE ISO checksum and live-USB compatibility: Wi-Fi, storage, graphics, touchpad, sleep and power
5. Human-approved partition and dual-boot plan with Windows volumes preserved, based on actual disk identity
6. After separately approved Fedora installation: real libvirt/KVM, SELinux enforcing + effective sVirt labels, no-network malware guest packet-denial check, resource headroom and cold recovery rehearsal

**Do not post private keys, BitLocker recovery passwords, raw volume maps, user file names or serial numbers.** A sanitized machine summary and synthetic source tests do not replace any of the manual gates.

## Review/test discipline

- Keep PRs #52/#54/#55 unmerged; create new work on a stacked draft branch.
- Run `python -B -m unittest discover -s tests -p test_windows_host_gate.py -v` and parse every PowerShell file natively on Windows.
- Execute the host script only after the exact Git commit has been pinned in an isolated detached worktree.
- Never install packages, request administrator elevation, change partitions, enable BitLocker/TPM or alter boot settings as part of this review.
- Keep every successful or failed result ZIP and session metadata with SHA-256 hashes, distinguish `OBSERVED` from `HOLD/UNKNOWN`, and **never describe this as physical Fedora or release acceptance**.

Windows servicing reference: https://support.microsoft.com/en-us/windows/deployment/updates-lifecycle/windows-10-support-has-ended-on-october-14-2025
