# Midnight Provisioner Phase 19 — Offline pre-install blocker inventory

Status: **DRAFT / READ ONLY / INSTALLATION BLOCKED**. This phase adds an independent, machine-readable review of unresolved Windows-to-Fedora deployment prerequisites. It is not a disk planner, installer, USB writer, partition resizer, bootloader editor, backup copier or recovery tool. The data flow is limited to sanitized Phase 18 evidence and optionally an existing ISO file read for hashing.

## Phase 18 baseline

Exact previously verified PR #56 commit: `cdbfa223842c6016075c78377134ce5e543ac8e4`. Native Windows Phase 18 safety tests and bounded machine observation PASSED. The resulting deployment status was `HOLD_MANUAL_DEPLOYMENT_APPROVAL`; independent backups, recovery, physical firmware/disk inspection and Fedora live-host testing remain unproven.

## New Phase 19 gate

`scripts/windows/Build-Midnight-Provisioner-Phase19-Preflight.py` reads one **sanitized**, local `midnight-provisioner.windows-host-observation.v1` JSON file with an absolute, ordinary-file path. It rejects duplicate JSON keys, symlinks/reparse-point ancestors, traversal, oversized files, malformed facts, missing/duplicate observations and any indication that backup/restore/install/partition write permissions were granted. It never reads raw disk identifiers, backup media, machine secrets or TPM/recovery-key material.

It emits a `midnight-provisioner.preinstall-blockers.v1` JSON report, with all manually required checks marked **PENDING_INDEPENDENT_EVIDENCE** and every write/install/guest-launch permission **false**. The report itself cannot approve a system modification. The runner creates an isolated pinned worktree and retakes a fresh sanitized Phase 18 host observation, verifies the Phase 19 source contract, and archives the original evidence under `Documents/Midnight-Provisioner-Verification-Results`. No actual host read query is attempted if its safety gate fails.

### Optional offline Fedora KDE ISO byte verification

The Python gate supports `--iso <absolute-path-to-existing-file.iso> --expected-sha256 <64-hex-digits>`. Both are required together. A bounded, read-only SHA-256 stream comparison checks whether **this existing file matches the value provided by the operator**. It does not access any downloads or write to a USB drive. A match does **not** prove the value originated with Fedora, a signed checksum file was verified, the ISO is the expected architecture, or that the live USB boots safely.

Official references:

- Current Fedora KDE Plasma Desktop image and verification instructions: https://fedoraproject.org/kde/download/
- Verify the CHECKSUM file signature and digest using Fedora OpenPGP public keys independently: https://fedoraproject.org/security/
- Microsoft Windows 10 support/ESU options: https://support.microsoft.com/en-us/windows/deployment/updates-lifecycle/windows-10-support-has-ended-on-october-14-2025
- Microsoft Device Encryption / BitLocker: https://support.microsoft.com/en-us/windows/security/encryption/device-encryption-in-windows
- Microsoft recovery-key custody: https://support.microsoft.com/en-us/windows/security/encryption/back-up-your-bitlocker-recovery-key
- Microsoft shutdown and hibernation guidance: https://support.microsoft.com/en-us/windows/experience/power-battery/shut-down-sleep-or-hibernate-your-pc

## Actual outstanding manual gates

1. Independent Windows and personal-data backup set on physically separate media, with a **controlled restore proof**.
2. Windows recovery media plus recovery/BitLocker key custody without disclosure. Confirm BitLocker/device-encryption status separately.
3. Manually confirm real EFI System Partition, Windows Recovery Environment and any OEM partitions, actual physical disk identity and safety margins. Free space inside C: is **not** unallocated installation space.
4. Resolve Windows Fast Startup/hibernation before any read-write Fedora access to NTFS. A registry flag alone does not prove a cold shutdown.
5. Confirm a supported Windows security servicing path. Windows 10 ordinary support ended October 14, 2025; do not infer ESU enrollment from an update package or eligibility alone.
6. Verify the genuine current Fedora KDE image, signed CHECKSUM provenance and a clean local SHA256 match.
7. Separately authorize an *actual* Fedora live-USB boot and exercise display, Wi-Fi, keyboard, audio, sleep and storage detection **without** running the installer or mounting Windows partitions read-write.
8. Only after separate authorization and vetted backups, plan partition changes and subsequent real Fedora KVM/libvirt, SELinux/sVirt running guest labels, no-network guest traffic, cold restore and rollback.

Do not store BitLocker recovery keys, device serials, raw storage maps or personal backups in Midnight Provisioner GitHub issues/PR comments, uploaded logs or build evidence. Even all manual attestations combined cannot make Phase 19 output an install approval.

## Verification

Python syntax and `test_phase19_preinstall.py` regression should be run on both Windows Python 3.12 and Fedora/Python 3.14 where available. The Phase 18 native PowerShell AST source gate also remains required. All source-SHA or baseline-branch drift blocks execution. A future test run must not retroactively be described as the previous PR #56 baseline verification; commits changed in this phase require new exact-head evidence.

PRs #52/#54/#55/#56 and this phase remain draft, unmerged, no physical media or VM actions authorized.
