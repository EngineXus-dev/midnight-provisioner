# Phase 11 — multi-source backup coverage before Windows 11 Pro

**Status: IMPLEMENTED IN A DRAFT BRANCH, NOT YET RUN ON USER DATA.**

Nightglass is an independent Fedora KDE / Windows dual-boot project.
The existing Phase 10 read-only inspector could verify **one**
original folder against **one** backup folder. That is useful but
insufficient before a future Windows clean install: files may live
in multiple project roots, Desktop, Documents, other drives, VM image
folders and application-specific settings directories.

Phase 11 adds a **private, explicit catalog of multiple directory
pairs**. It still does not perform backups or restore files.

## Safety and access

`scripts/Verify-Nightglass-BackupSet.py` defaults to **Preview**,
which reads **no manifest, directories or files**. There are three
modes:

| Mode | Reads | What it establishes |
| --- | --- | --- |
| Preview | Nothing | Explains the safe workflow |
| Inspect | A private local JSON manifest and metadata of each nominated source/copy | Directory entries, missing files, different sizes; **not data equality** |
| Verify | The above plus streaming SHA-256 of every regular file in each pair | Each specifically selected directory's files matched their copy **at the time of reading** |

The program calls only the repository's own fixed
`Inspect-Nightglass-Backup.py` checker. It never runs a downloaded
script, invokes a shell command, probes all Windows drives,
selects a USB, accesses GitHub or alters the source/backup files.
By default it outputs counts and short, user-chosen *IDs*,
not actual paths, file contents, secret values or SHA-256 digests.

Important holds:
- **No copying:** you must independently decide what to back up and
  copy it using your preferred trusted Windows file/backup method
  before any verification is meaningful.
- **No complete-system claim:** only directories explicitly listed
  are checked. Registry settings, installed apps, scheduled tasks,
  game/application databases, encryption recovery keys, Docker
  volumes, VM images, cloud-only files, browser exports and any
  directories you omit are **outside the evidence**.
- **No actual recovery proof:** a matching backup is not a tested
  restore. An independent harmless restore drill is still needed.
- **No physical drive certification:** this code cannot prove that
  the copy is on your independent portable hardware. A USB drive
  letter or filesystem device identifier is not reliable evidence.
- **No installer authority:** Windows 11 Pro installation, Fedora
  partitioning, the separate 16 GB installer USB and all disk-format
  operations remain unauthorized.

## Step 1 — prepare your own PRIVATE mapping

See `examples/backup-set.EXAMPLE.json` for a deliberately
nonfunctional **example**, with explicit REPLACE placeholders.

Create a NEW local JSON file such as
`my-backups.nightglass-backup-set.local.json`, stored outside the
GitHub repository when possible. Use this shape:

```json
{
  "version": 1,
  "entries": [
    {
      "id": "projects",
      "source": "C:\\REPLACE_WITH_YOUR_ACCOUNT\\Documents\\Important-Projects",
      "backup": "E:\\REPLACE_WITH_YOUR_PORTABLE_DRIVE\\Important-Projects"
    }
  ]
}
```

**The E: drive is only an illustration.** The portable disk was
previously recognized as Disk 1 on Windows 10, but disk numbers and
letters can change. Verify it yourself; never assume an example
drive letter is correct. No Windows drive is accessed during Preview.

Paths must be absolute, existing **directories**, and source/copy
must not overlap. The catalog supports 1–32 uniquely named groups.
IDs use lowercase letters/numbers, hyphens and underscores, and
should not contain people's names, product keys or sensitive details.

The manifest is inherently sensitive because it names your private
folders. Never add a real manifest to GitHub, Discord, chat logs,
a publicly accessible ZIP or your installer image. This repository's
`.gitignore` ignores
`*.nightglass-backup-set.local.json` and
`*.nightglass-backup-report.local.json`, but a file already
tracked by Git or saved under an unrelated filename is NOT protected
by those patterns. **Keeping the file outside Git entirely is safer.**

## Step 2 — preview first

From a checkout that contains the new script:

```powershell
python scripts/Verify-Nightglass-BackupSet.py
```

No file access, hashing, manifest parsing, backup copying,
restore, registry change, Git operation, USB write or Windows Setup.

## Step 3 — inspect only when copies exist

```powershell
python scripts/Verify-Nightglass-BackupSet.py --mode Inspect `
  --manifest "C:\\REPLACE\\my-backups.nightglass-backup-set.local.json"
```

Inspect compares file/folder inventory and sizes across all selected
pairs. Missing source data on a nominated backup **blocks**.
An inventory-only result **never** counts as matched content.

## Step 4 — opt into content verification

After copies are complete and source applications have stopped
writing to those files:

```powershell
python scripts/Verify-Nightglass-BackupSet.py --mode Verify `
  --manifest "C:\\REPLACE\\my-backups.nightglass-backup-set.local.json"
```

`Verify` reads and hashes each file on both sides, including
hidden `.env`, `.venv`, `.git` and other files located inside
the selected trees. A difference in **any** required entry makes
the **entire set** incomplete. Backup-side extras are preserved
and flagged for review, never deleted.

The checker also refuses symbolic links, Windows junction/reparse
points, nested/overlapping roots, unsafe/nonregular entries,
an empty source tree, changed-on-read files, and a destination
file that is actually a **hard link to the original** (same
nonzero filesystem device + inode identity). On filesystems that
do not provide reliable file identity, this hard-link detection
cannot be guaranteed, so **external media remains unverified**.

A regular-file set that matches can report
`all_selected_content_matched=true`, but it always reports:

```
full_machine_backup_completeness_proven = false
physical_external_media_verified = false
restore_drill_performed = false
restore_proven = false
windows_install_authorized = false
fedora_install_authorized = false
usb_format_authorized = false
```

**No green backup report authorizes a Windows reinstall or disk erase.**

## Optional local report

Add a new path outside ALL inspected source/backup roots:

```powershell
python scripts/Verify-Nightglass-BackupSet.py --mode Verify `
  --manifest "C:\\REPLACE\\my-backups.nightglass-backup-set.local.json" `
  --report "C:\\REPLACE\\my-check.nightglass-backup-report.local.json"
```

Reports use exclusive-create: they cannot overwrite an existing
file or be placed under an inspected tree. They do not contain
the absolute file paths or data hashes.

The default scope is **50,000 filesystem entries and 250 GiB of
regular-file data per selected tree**. Limits can be expanded
explicitly with `--max-files` and `--max-bytes`, but scanning
large live working datasets, cloud placeholders or VM disks while
applications are modifying them may produce inconsistent results.
An incomplete run is not a backup pass.

## After the user elects to deploy later

Before formatting anything: complete a personally reviewed backup
inventory that covers **all** important locations; verify actual
portable drive identity and independent copies; test a harmless
restore; confirm Windows 11 hardware support, recovery keys and
genuine Pro activation rights; independently validate original
Windows/Fedora ISOs and the separate disposable 16 GB USB.

The future Windows 11 Pro workflow retains both modes:
**Activate later (default)** and **activate during official setup**.
No activation key belongs in these manifests.

The new tests are committed but **have not yet passed the complete
native Windows/isolated Fedora Docker test matrix**. No backups,
OS installs, USB formatting or PR merges happened in this phase.
