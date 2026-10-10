# Phase 25 — guided target review without destructive access

**Draft software milestone. No operating system installation, disk formatting or EFI/boot modification exists in this feature.** This phase is the *advisory stage* of a future new-system installer, stacked on the user-managed-backup warning in Phase 24.

## Expected experience

1. Nightglass automatically observes available host and disk metadata **read-only** on ordinary Fedora GUI startup; the Windows command-line path is also supported.
2. On **System discovery**, the user first selects the intended operation: **Undecided**, **Freshly format selected target (delete its data)** or **Alongside existing OS**. No target device is selected initially.
3. The user selects a **currently observed disk** to preview. Nightglass shows its observed label, rough size, bus, current partition count and whether Windows reports it as a boot/system disk or Linux reports a mounted filesystem. It does not infer that any disk is empty or safe merely because no partitions were reported.
4. It shows **ENTIRE_SELECTED_DISK** as the proposed destructive scope for a fresh full-drive installation, or **PARTITION_CHANGES_NOT_YET_SPECIFIED** for coexistence. This is not a write blueprint. It does **not** determine final EFI entries, which partitions actually get formatted, whether other drives are affected, or the installer's hardware target identity.
5. The Phase 24 **DATA LOSS WARNING** states that formatting would remove everything on the affected area, that data loss may be irreversible and that the user is responsible for backing up anything they want to keep. Nightglass does not make or verify those backups. A checkbox records acknowledgment **only in memory**; it is never backup proof or approval to erase.
6. When hardware is rescanned, the prior selected disk and acknowledgment are **discarded**. Changing the intended operation or selected target also clears acknowledgment. The preview is refreshed on each change.
7. Every possible plan returns `HOLD_PREVIEW_ONLY_NO_INSTALLER_OR_DISK_WRITES`, with installation and disk-write flags **false**, even when an acknowledged user selects an existing disk. Protected Windows boot/system or Linux mounted drives receive an additional warning.
8. Real installation remains an entirely separate feature and permission gate. It must re-detect the exact hardware device, disclose an exact partition/EFI/format plan, independently validate official installation media and obtain new device-specific destructive-operation confirmation. The user can back out before any write.

## CLI (Windows and Fedora)

From a Python checkout containing this draft branch:

```powershell
python -m nightglass discover
python -m nightglass install-preview
python -m nightglass install-preview --intent format_target --disk-index 1
python -m nightglass install-preview --intent format_target --disk-index 1 --ack-warning --json
```

`--disk-index` is **zero-based within the newly returned discovery array**, NOT a persistent Windows physical disk number, stable Linux `/dev` path or permission to modify hardware. Re-examine the reported list each time; physical disk numbering can change. Without `--disk-index`, no device is selected. The preview can only print text/JSON and cannot write to or mount the device.

`--ack-warning` records only that a caller opted to acknowledge the notice in the current ephemeral preview. It is not a stored acceptance and never changes any authorization boolean.

No personal subfolder names are scanned by `install-preview`. No file is created by the CLI and no network or elevation is needed for this feature. The existing read-only discovery subprocesses may return UNKNOWN if unavailable or unsupported. No device serials, disk IDs, recovery keys or private folder contents are logged.

## Verification and scope

- `nightglass/install_target_preview.py` is pure and immutable; its explicit target comes from a bounded, schema-checked **in-memory discovery snapshot**.
- `tests/test_install_target_preview.py` has 16 cases for an unselected default, whole-device data-loss warning, Windows system disk blocks, coexist EFI caveats, non-authorizing acknowledgment, missing/forged discovery evidence, input validation, immutable reports, safe output and CLI dispatch.
- `tests/test_gui_smoke.py` adds an opt-in offscreen Qt integration case for no target preselection, manual target preview, protected disk detection, backup warning acknowledgment and rescan invalidation. This augments the original 24 cases to 25.
- Prior source unit tests and real Fedora Qt/QEMU fixtures must be rerun at the new exact commit before claiming any platform verification.

**Not present:** Live OS installer, automatic partitioning, bootloader changes, encryption toggles, format/overwrite operation, snapshot/backup/restore, live Fedora hardware install, confirmed physical virtualization or production-ready guest confinement.

The user chooses whether to trust an independently prepared backup; Nightglass cannot assume the selected target is blank or that a personally acknowledged warning certifies recoverability. Every Nightglass PR remains a reversible **DRAFT, UNMERGED** change.
