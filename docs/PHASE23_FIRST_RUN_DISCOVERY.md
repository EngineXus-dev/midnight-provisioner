# Nightglass Phase 23 — first-run system recognition

> **Phase 24 correction:** The planned installer will **format the user-selected target**, which can already contain data. Users are responsible for their own backups before consenting. Nightglass will prominently warn them but does not create or verify those backups. Descriptions in this historical Phase 23 document about requiring an already-blank drive or exempting an empty disk have been superseded by [Phase 24 — format-during-install warning](PHASE24_FORMAT_WARNING.md). Phase 23 recognition still does not select or modify any drive.


**Status: DRAFT; no OS installation, partition writing, USB formatting, VM startup or firmware changes.**

## Why this exists

Nightglass should run on a new machine without making assumptions based on any previous PC. A Windows folder survey and backup-drive probe were useful one-off operator scripts, but the same **recognition step now belongs inside the main Nightglass software**, rather than requiring people to download and understand many separate scripts.

The user may intend to install Nightglass on a **truly blank dedicated drive**. A brand-new verified-empty drive contains no old files to back up, and Nightglass should **not** demand a backup of nonexistent data. That does **not** imply that a drive marked `RAW`, a disk with zero reported partitions, or any other unclassified drive is actually safe or empty. Nor does it mean Windows, an existing EFI System Partition, other attached disks or device-encryption recovery state can be ignored if an installer might touch them.

## Behavior

- The Fedora PySide6 application now has a seventh page: **System discovery**. The previous six pages keep their indexes and behavior.
- A bounded local, read-only hardware/storage probe is scheduled shortly after ordinary GUI startup. The dedicated discovery page can rerun it manually.
- `nightglass discover` runs the same probe headlessly (Windows or Fedora) without GUI dependencies or modification; `nightglass discover --json` prints the private local observation.
- All devices are classified **PROTECTED_IN_USE** if the OS reports system/boot use (Windows) or mounted filesystems (Linux), otherwise **UNVERIFIED_NOT_EMPTY_PROVEN**. No disk is automatically chosen. If the query fails, `UNKNOWN` is shown rather than claiming no disks or empty disks.
- RAM/CPU and rough disk size/type/observed partition count are advisory. Disk numbers, drive letters and labels can change across boots; the local observation is **not** durable disk identity. Serial numbers, UUIDs, encryption keys, file content and registry secrets are not collected.
- The only read of personal directories by default is a bounded existence probe for the conventional Desktop/Documents/Downloads/Pictures/Videos folders. **Names of subfolders require a separate unchecked opt-in.** Under opt-in, the scanner reads only directory names (not files) to depth two, with a finite node budget, and refuses symlinks/reparse points and known sensitive dot directories. Nothing is uploaded or saved automatically.
- The user explicitly selects an *intent*: Undecided (default), dedicated blank drive, or coexist alongside an existing OS. Selection is a statement of intent, not proof of disk condition; no actual target-selection control or install action is present.
- `HOLD_USER_REVIEW_ALL_UNKNOWN_DETAILS`, `install_target_confirmed=false`, `blank_drive_independently_verified=false`, and every install/partition/USB/firmware/VM authorization flag remain **false** for every result.

## New system setup sequence

1. **Auto-recognize** host OS, RAM where readable, CPU and storage (read-only).
2. **Review uncertainties**: missing/corrupt storage responses, source/target ambiguity, mounted partitions, disk identity and encryption. Leave unknowns to the user; never silently default.
3. **Choose intended install mode**: blank dedicated drive, alongside existing OS, or undecided.
4. **Independent physical verification, outside automated discovery**: user confirms which device is an empty target, the real boot disk, whether any partitions/EFI will be shared, and that disconnected/untouched disks truly cannot be affected.
5. **Conditional backup decision**: no old files on an independently verified blank dedicated disk means a backup *of that blank target* is not applicable. If existing Windows/EFI/data disks could be modified, independent backup/recovery checks still apply to those disks. For a purely dedicated build with isolated media, mark backup of existing systems NOT APPLICABLE only after this has been independently established.
6. **Separate authorization**: verified signed official Fedora installer image, test boot/live hardware, supported Windows servicing (if dual-boot), encryption/recovery keys (when relevant), rollback/cold restore, and KVM/SELinux/sVirt network isolation acceptance. Future stages require user confirmation and separate software changes. Phase23 does NOT install or modify anything.

## Launching

On Fedora after existing Nightglass application installation:

```bash
nightglass gui
nightglass discover
nightglass discover --json
nightglass discover --folder-names  # explicit opt-in; personal names remain local
```

On Windows with Python and a Nightglass source checkout:

```powershell
python -m nightglass discover
python -m nightglass discover --json
```

The native desktop UI is still Fedora-only; Windows preparation uses read-only Python CLI. No network access is made by the scanner and it does not need administrator/root privileges. Under source-only or unsupported OS runtimes, unknown fields remain unknown.

## Testing

`tests/test_system_discovery.py` contains 12 self-contained Windows/Linux simulated device and consent tests. The existing offscreen Qt GUI tests were updated for a seventh page and add a discovery-panel interaction test, including verification that the suite **never starts a real host discovery probe** when `NIGHTGLASS_GUI_SMOKE=1`. Runtime Windows PowerShell 5.1, Fedora real-`lsblk` and offscreen Qt behavior **must still be operator-verified** at an exact source SHA before claiming release readiness.

Do not merge the Phase23 PR until independent operator testing passes. Existing Phase22 and earlier draft PRs remain unmerged and reversible.
