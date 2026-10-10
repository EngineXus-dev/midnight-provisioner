# Phase 12 — Backup-path ancestor and Windows reparse boundary

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Status: new draft branch; main unchanged.** The latest connected
GitHub source of the two backup inspectors was reviewed, then patched
directly on an isolated branch named `security/backup-boundary-fix`.
This is a different scope from the original review-only ZIP.

## Security issue

The previous single-folder checker inspected the selected root's
*last* path component with `lstat()`, and then resolved its name.
A regular directory below a symlink or Windows junction could be
accepted because **the final directory was not itself linked**.
The same class of error affected a report output path and the
private multi-source JSON manifest.

Example (synthetic paths, not user data):

```
temp/
  real/project/     <- actual data
  link -> real       <- symlink/junction
  link/project/      <- final component appears ordinary
```

Previously, `checked_root('temp/link/project')` could follow the
linked ancestor and silently inspect `real/project`, which was not
the literal directory tree the user selected.

This is a boundary/identity mismatch, **not evidence of data theft,
a successful OS exploit or any writes to the user's machine**.

## Changes

`scripts/backup/Inspect-Nightglass-Backup.py` now has
`reject_linked_ancestors(path)`:

- Walks the chosen path component-by-component back to the volume
  root and checks each existing component with `lstat()`.
- Rejects Python symlinks and Windows entries carrying
  `FILE_ATTRIBUTE_REPARSE_POINT` (including junctions), even when
  the **selected final component looks like an ordinary directory**.
- Rejects `..` parent traversal. A lexical normalization such as
  `alias/../target` could otherwise hide an alias before the
  system traverses the original path.
- Is called **before** `checked_root` resolves the selected source
  or backup directory.
- Is called on the **original report parent spelling before**
  `absolute()`, and again on the resulting report parent before
  the exclusive-create file write. The report still cannot be
  created within either inspected tree and cannot overwrite an
  existing file.

`scripts/backup/Verify-Nightglass-BackupSet.py` invokes the same guard
on the explicitly named private manifest path **before opening
the manifest**. Every subsequent source/backup root is passed
through `checked_root`.

Paths through legitimate Windows junctions, symlinked home or
OneDrive folders may therefore be **blocked on purpose**.
Choose an independent ordinary directory and manually confirm
what is actually being inspected. Do not disable this safeguard
or auto-follow aliases just to make a report turn green.

## Tests added

- Linked ancestor of a selected source/backup directory is refused.
- Linked ancestor of a report directory is refused; no output created.
- Parent-traversal `..` variants block selected sources, reports
  and private manifests.
- A private manifest located below a linked parent is refused and
  CLI returns a blocked status.
- Synthetic Windows reparse attributes are recognized even when
  `st_mode` does not indicate a symlink.

The existing Phase 10/11 tests still check ordinary copied data,
byte-level mismatches, hardlinked fake backups, empty source
directories, missing/extra files, privacy, file-read stability and
write restrictions.

**Evidence status:** The older standalone representative Phase 12
fixture was executed successfully on a disposable Linux filesystem,
demonstrating the linked-parent bug and basic blocking behavior.
That fixture **is not a full test of the actual GitHub repository**.
The new direct-GitHub edits and added tests have been statically
cross-checked; they have **not yet been executed natively on
Windows or through the cumulative Python/Fedora Docker matrix**.
Real Windows junction creation/handling needs native acceptance.

## Remaining limitation — not a race-free sandbox

Checking each component via `lstat()` before file open does **not
atomically lock the entire path**. Another local process with write
permission could swap a parent directory or junction between checks
and reads. Likewise, an SMB/network filesystem may have unfamiliar
file-identity behavior. A future hardened implementation could use
platform-specific directory handles and verified relative opens,
but requires careful Windows and Linux compatibility review.

The tool is intended for user-controlled, stable folders; do not
use it to inspect malicious, concurrently modified directory
trees or claim a security-isolation guarantee. Even a matching
backup only verifies the **explicitly selected data**, not complete
machine coverage, physical backup-device independence or recovery
success.

## Deployment remains held

No installer images, Win11 Pro activation keys, Windows 11 or Fedora
partitions, startup settings, encryption policies, USB boot media,
actual backups or external example backup-drive capacity backup media have been changed.
All PRs remain unmerged and subject to a separate human decision.
The user's Pro activation later option remains the default.

Read `docs/MULTI_SOURCE_BACKUP_READINESS.md`,
`docs/BACKUP_INTEGRITY_PREFLIGHT.md` and
`docs/WINDOWS_ONE_COMMAND_OFFLINE_CHECKS.md` before any future
locally authorized verification.
