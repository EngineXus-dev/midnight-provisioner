# Midnight Provisioner Phase 26 — proposed change impact and unknowns

**DRAFT, NO WRITES, NO OS INSTALLATION.** This stage is a review of what a future OS installer *might* change, not a partition proposal precise enough to execute.

## Reason

The prior Phase25 target preview knows only the operator's intent and a coarse host observation: an approximately sized physical drive, its temporary label, and a reported count of partitions. **It does not know the current partition table, the relevant EFI System Partition, which disk firmware boots, the proposed Linux partitions, or a full before/after write manifest.** A safe installer must never make those up.

The user intends to freshly format the chosen install target, which may currently have files. The user is responsible for independently backing up anything they want to keep; Midnight Provisioner does not make or verify backups.

## Built in

- `midnight_provisioner/install_change_review.py` generates an immutable `midnight-provisioner.install-change-review.v1` document from Phase25's held preview.
- The **System discovery** page contains a new scrollable **Proposed partition / EFI / boot impact** read-only section. It refreshes whenever the user changes intent, observed disk, or backup-warning acknowledgment. It is reset when the hardware scan restarts.
- `midnight-provisioner install-changes --intent format_target [--disk-index N] [--ack-warning] [--json]` offers the same read-only review on native Windows or Fedora. It scans no personal subfolder names. Index `N` is *zero-based within the current recognition snapshot*, not a stable device identity or executable installer selection.
- For `format_target`: existing content loss is marked **INTENDED_EFFECT_NOT_VERIFIED** because the user wants whole-drive replacement. The existence or detailed identity of those partitions, and whether a format has actually occurred, is not certified.
- For `coexist`: existing partition preservation, resize, delete and new partition sizes are all **UNKNOWN_REQUIRES_INSTALLER**.
- All modes mark **EFI System Partition**, Windows boot and recovery, other physical disks, official installer media and physical boot behavior **UNKNOWN_REQUIRES_INSTALLER**, without a fake proposed partition table.
- Unknown or forged Phase25 evidence is rejected; even a checked acknowledgment or a selected protected disk cannot authorize disk operations. No persistent setup acceptance or device identifier is generated.

## Complete-knowledge requirement before any future write

A future *separately reviewed* installer would have to produce an authoritative machine-specific BEFORE/AFTER plan: exact hardware target identity, partitions and filesystem labels/sizes to be deleted/created, EFI and firmware targets, encryption/recovery implications, validated official media origin, and all drives it will touch. The user must explicitly confirm the exact destructive effects, with a right to cancel before writing.

**That future feature is NOT implemented here**. The Phase26 document always returns `HOLD_CHANGE_DETAILS_UNKNOWN_NO_WRITES`. All of `write_manifest_complete`, `destructive_consent_obtained`, `disk_write_authorized` and `os_install_authorized` are false. No partition management, formatting, OS/media installation, backup copying, USB, BitLocker, firmware or KVM/VM operations are present.

## Checks

`tests/test_install_change_review.py` introduces 12 pure tests across replacement/coexistence/unknown partition consequences, EFI/boot ambiguity, forged preview rejection, protected disk, no backup certification, CLI privacy and no write-capable calls. `tests/test_gui_smoke.py` adds a 26th offscreen Qt test for the read-only impact matrix and rescan invalidation.

**Cross-platform Phase26 verification is pending**, including the 12 new unit tests and a rerun of all previous Phase19–25 tests plus the 26 GUI tests. The parent Phase25 SHA `8470ad99a9d26e53c2e2f54deb42035f583decd1` was verified and is preserved on its draft PR #63.

All upstream PRs remain draft and unmerged.
