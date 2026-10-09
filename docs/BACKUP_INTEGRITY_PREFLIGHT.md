# Phase 10 — Verify your Nightglass backup before a future Windows 11 clean install

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**No backup copy is created by this phase. No USB/disk writer exists.**
The user's Windows 11 Pro clean installation is explicitly deferred;
the current Windows 10 OS drive stays intact until a later
user-approved installation. The separately owned **example backup-drive capacity portable
drive is BACKUP MEDIA ONLY**, not a Windows/Fedora installation
target or Ventoy installation target.

The user previously had local files such as `.env`, `.venv`,
untracked changes and uncommitted data overwritten by overly broad
Git update scripts. A clean OS installation can similarly lose
irreplaceable local-only files even where GitHub source is safely
preserved. **A GitHub commit or a successful `git pull` is not a
personal data backup.**

## New read-only tool

`scripts/Inspect-Nightglass-Backup.py` uses only the Python standard
library, runs on Windows 10/11 or Linux, and supports the following
separate modes:

| Mode | Access | Confidence |
| --- | --- | --- |
| `Preview` (default) | **No file access or filesystem changes** | Explains what the tool would inspect |
| `Inspect` | Read-only directory listing and metadata of two explicit paths | File/folder presence and sizes **only**; no proof of identical content |
| `Verify` | Read-only directory listing **and SHA-256 streaming** of each file on both sides | Byte equality of inspected original and backup at inspection time, **not restore success** |

Both Inspect and Verify require two **explicitly selected** directories:
the original project folder and the corresponding folder the user has
**already copied** to the portable drive. Nightglass never identifies,
selects, formats, writes to or mounts a drive on the user's behalf.
Neither source nor destination must be inferred from Windows disk
number (which can change after reboot).

### Default Preview (safe today)

From a checkout containing the new tool:

```powershell
python scripts/Inspect-Nightglass-Backup.py
```

This has **no file reads, no GitHub/network requests, no hash work,
no disk enumeration and no writes**. The script can also be retrieved
later into a separate temporary folder using a pinned Git source
without switching the user's working `main` checkout.

### After the user separately copies files to the portable drive

The following directories are *EXAMPLES ONLY*: replace both quoted
paths with the user's actual original project and verified portable
copy. Do not interpret the sample `E:` letter as a known drive.

```powershell
# Metadata / relative-path inventory only. Does NOT prove byte equality.
python scripts/Inspect-Nightglass-Backup.py --mode Inspect `
  --source "C:\Users\YOURNAME\Documents\nightglass-workspaces" `
  --backup "E:\MY-BACKUP\nightglass-workspaces"

# Stronger read-only matching after copying is finished and files are idle.
python scripts/Inspect-Nightglass-Backup.py --mode Verify `
  --source "C:\Users\YOURNAME\Documents\nightglass-workspaces" `
  --backup "E:\MY-BACKUP\nightglass-workspaces"
```

Verify streams one MiB at a time rather than loading large virtual
disk images or repositories into memory. It includes hidden
`.env`, `.venv` and `.git`, if those are under the chosen source
directory. It reports presence of these categories without
printing their contents, any secret keys, raw SHA digests,
or absolute file paths. Files missing from the backup, same-size
file-content changes, different sizes or missing directories cause
a nonzero exit status. Extra files in the backup are **not deleted**,
but clearly marked for review.

Use `--show-differences` *only when inspecting private output on
your own machine*, because relative filenames can themselves reveal
private details. The default output contains summary counts but
not paths. Use a **new, nonexisting** path outside both trees with
`--report "C:\path\to\new-summary.json"` if a private status record
is desired; existing reports cannot be overwritten.

The default audit reads at most 50,000 filesystem entries (including
empty directories) and 250 GiB of regular files per tree.
It fails closed if exceeded. The owner can consciously expand the
budget with `--max-files` and `--max-bytes`. A failing or
incomplete scan never proves a complete backup.

## What a content match means

A `CONTENT_MATCH` status establishes that the two **explicitly
selected directory trees** had matching regular files at the time of
the comparison, as far as the filesystem reads were consistent.

It does **not** prove:

- that the directory selection includes every important local file
  (for example Desktop, Downloads, browser exports, game saves,
  personal photos, CAI development work, Docker volumes, SSH keys,
  encryption recovery material or data in other repositories);
- that the portable copy is on a truly separate physical disk,
  healthy medium or offsite storage (the OS device IDs are only
  **advisory** and may be ambiguous on Windows);
- that a Windows profile, Python environment, mounted game files,
  app settings, secret backups, guest disk image or database can
  actually be restored and used successfully;
- that encrypted data is decryptable or a BitLocker/device
  encryption recovery key is safely held;
- that a source which changed during the scan was captured as a
  consistent point-in-time snapshot.

The tool refuses symlinks/Windows junction/reparse entries, nesting
a backup inside a source, impossible size/file-count budgets,
nonregular files and content changes noticed during hashing.
Some Windows placeholder/reparse-based cloud files are intentionally
blocked rather than implicitly materialized. Reconcile those
separately using a trustworthy backup process.

**Full backup confidence requires independently checking what matters,
plus performing a harmless test restore to a NEW, separate location
under user control. This tool deliberately does NOT restore data.**

## Separate Windows 11 and Fedora safety holds

After a later actual backup, the user must also independently verify
Windows 11 supported hardware eligibility, the genuine Windows 11
Pro edition and activation key, driver/recovery access, automatic
device encryption choices, and a truly separate expendable installer
USB. A Windows installer wipe, Fedora partitioning or formatting
remains a completely separate manual approval step.

The Pro key can be entered during authentic Windows setup **or
activated later (default)** in Windows Settings. It must never be
embedded in this repo, ISO, report or backup inspector.

See [clean install plan](WINDOWS11_CLEAN_INSTALL_STAGED.md),
[activate later](WINDOWS11_PRO_ACTIVATE_LATER.md), and
[one-USB plan](ONE_USB_MULTIBOOT_PLAN.md).

**This Phase 10 source has not yet run its Windows-native and
full offline Docker test matrix. No source files or backup media on
the user's workstation have been modified.**

## Phase 11: optional private multiple-location catalog

To verify more than one copied directory, use the new
[Multi-source backup coverage](MULTI_SOURCE_BACKUP_READINESS.md) tool.
It reuses this single-folder checker and aggregates outcomes
without copying or writing user files. The original checker also
refuses a content match where copied files are merely hard links
sharing the same nonzero inode and device identifier as originals.
This is a safety check, **not proof of physical media independence**.

## Phase 12: linked ancestors are blocked

The read-only checker no longer accepts a normal-looking source or
backup directory whose **parent** is a symlink or Windows reparse/
junction. Report output paths are checked before and after lexical
normalization. Parent-traversal `..` paths are rejected. This can
block paths redirected through legitimate OneDrive or folder
junctions; choose and verify a physical directory explicitly.
This guard is not atomic against concurrent path swaps.

See [backup path security review](BACKUP_PATH_BOUNDARY_HARDENING.md).
Native Windows junction testing remains pending.

## Phase 13 identity check

The backup checker now rejects a backup hardlink to any source file in its selected source tree, even when filenames differ. Physical drive independence remains unverified.
