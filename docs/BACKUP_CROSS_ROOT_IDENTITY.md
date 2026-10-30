# Phase 13 — Cross-file and cross-group hardlink identity protection

**Draft source changes — latest native Windows/Docker tests not yet run.**

## The gap

Earlier Midnight Provisioner backup checks rejected a backup hardlink only when
it had the same relative filename as its source. A backup could
still appear content-identical while one file referred directly to
a *different* original source file. The multi-source catalog had a
second limitation: it compared each project independently and
could miss a purported backup in group B that was hardlinked to
an original file in group A.

A matching SHA-256 hash cannot detect this independence problem
because a hardlinked file has exactly the same bytes as its source.

## Phase 13 changes

In `scripts/backup/Inspect-Midnight-Provisioner-Backup.py`, `compare()` builds a
set of **all nonzero filesystem (device, inode) identifiers from
the selected source inventory**. It then checks **every backup
regular file**, including extra backup files and those with
different names. Any shared identity causes
`NOT_INDEPENDENT_FILE_COPY`, `verification_succeeded=false`
and a nonzero CLI outcome.

An optional `forbidden_source_ids` argument allows the group
inspector to supply the combined source identity set.
`scripts/backup/Verify-Midnight-Provisioner-BackupSet.py` first inventories
ALL selected source/backup groups and builds this combined
source set. Only then does it compare each pair. Thus a
backup file linked to another group's source is rejected,
even when all file sizes and SHA-256 content hashes match.

The report discloses `identity_scope` and
`identity_evidence` without printing absolute file paths,
personal keys, file contents or raw hashes.

## Synthetic regression additions

- Backup `second.bin` hardlinked to *source/first.bin*,
  with a separate *source/second.bin* of identical bytes
- An extra backup file hardlinked to an original source file
- A multi-root catalog where group B's .env backup is
  hardlinked to the group A source .env instead of its own
- The same cross-group alias must also fail metadata-only
  Inspect, without pretending to hash file content

All new tests use disposable temporary files and skip the
hardlink-specific assertion only when the filesystem does
not provide stable nonzero inode identity.

## Limitations

This detects known hardlink aliases only when the filesystem
reports reliable nonzero device and inode values. Windows or
network/cloud filesystems may return different or unstable
identifiers. A reflink/copy-on-write clone has a different
inode and is not automatically proof of independent hardware
storage. As before, ancestor-path preflight is not atomic
against a concurrent malicious file-system writer.

The result still cannot prove that all user-important files
were selected, the portable drive is a separate physical
disk, the backup is readable after a disaster, or a harmless
restore drill succeeds. Even a content match does NOT
authorize formatting, Windows 11 Pro installation, Fedora
partitioning or a pull-request merge.

## Verification state

The source and tests are committed on
`security/backup-cross-root-alias-guard`. The private repository
cannot be cloned from the current isolated test container,
and the full native Windows/Python/Fedora test matrix has NOT
been executed for this newest SHA. A prior source-contract
check is not a substitute for running these new tests.
