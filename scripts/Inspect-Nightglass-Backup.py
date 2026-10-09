#!/usr/bin/env python3
"""Nightglass read-only backup inventory and byte-for-byte content preflight.

Preview DEFAULT makes NO filesystem calls. Inspect reads directory metadata;
Verify additionally hashes each regular file on SOURCE and BACKUP.
Nothing is backed up, restored, copied, deleted, moved, formatted or mounted.
No GitHub/network access and no Windows/Linux OS installer operations.

All hidden files (including .env, .git and .venv) are INCLUDED.
Results are evidence of a particular read, NOT proof of recoverability.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

MODES = ("Preview", "Inspect", "Verify")
SCHEMA = "nightglass.backup-integrity.v1"
DEFAULT_MAX_FILES = 50_000
DEFAULT_MAX_BYTES = 250 * 1024**3
CHUNK_SIZE = 1024 * 1024


class BackupError(ValueError):
    """Invalid, unsafe, or incomplete source/backup inspection."""


@dataclass(frozen=True)
class FileInfo:
    path: Path
    size: int
    device: int
    inode: int
    mtime_ns: int


@dataclass
class Inventory:
    files: dict[str, FileInfo]
    folders: set[str]
    total_bytes: int
    markers: dict[str, bool]


def is_link_or_reparse(path: Path, st: os.stat_result) -> bool:
    # Windows directory junctions and other reparse points may not be
    # reported as Path.is_symlink(); never follow them during inventory.
    return (stat.S_ISLNK(st.st_mode)
            or bool(getattr(st, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)))



def reject_linked_ancestors(path: Path) -> None:
    """Fail closed if ANY existing path component is a link/reparse point.

    This conservative preflight includes the chosen leaf and its parents.
    On Windows, junctions and other reparse points are refused. This
    does not make traversals atomic against concurrent filesystem writes.
    """
    current = Path(os.path.abspath(path))
    while True:
        try:
            info = current.lstat()
        except OSError as exc:
            raise BackupError("A selected path component is inaccessible") from exc
        if is_link_or_reparse(current, info):
            raise BackupError("A selected path component is linked or reparsed")
        if current.parent == current:
            break
        current = current.parent


def checked_root(path: Path) -> Path:
    try:
        reject_linked_ancestors(path)
        before = path.lstat()
        if is_link_or_reparse(path, before) or not stat.S_ISDIR(before.st_mode):
            raise BackupError("Selected root is linked/reparsed or is not a directory")
        return path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise BackupError("Selected directory is missing, linked or inaccessible") from exc


def separated(source: Path, backup: Path) -> bool:
    # Do not compare a directory to itself, or scan recursively into
    # either tree from inside the other one.
    if source == backup or source in backup.parents or backup in source.parents:
        raise BackupError("Source and backup roots must be separate non-nested directories")
    return True


def inventory(root: Path, *, max_files: int, max_bytes: int) -> Inventory:
    files: dict[str, FileInfo] = {}
    folders: set[str] = set()
    canonical: set[str] = set()
    markers = {".env": False, ".git": False, ".venv": False}
    total = 0
    pending = [(root, Path("."))]
    while pending:
        directory, prefix = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise BackupError("Cannot enumerate an explicitly selected directory") from exc
        for entry in entries:
            if entry.name in (".", ".."):
                raise BackupError("Invalid directory name in backup tree")
            rel = Path(entry.name) if prefix == Path(".") else prefix / entry.name
            key = rel.as_posix()
            folded = key.casefold()
            if folded in canonical:
                raise BackupError("Case-ambiguous path detected")
            canonical.add(folded)
            if len(canonical) > max_files:
                raise BackupError("Entry count limit exceeded; narrow the selected tree or increase --max-files")
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise BackupError("A source or backup entry cannot be inspected") from exc
            path = Path(entry.path)
            if is_link_or_reparse(path, info):
                raise BackupError("Symlink or Windows reparse point is not supported")
            for marker in markers:
                if entry.name.casefold() == marker:
                    markers[marker] = True
            if stat.S_ISDIR(info.st_mode):
                folders.add(key)
                pending.append((path, rel))
            elif stat.S_ISREG(info.st_mode):
                total += info.st_size
                if len(files) + 1 > max_files or total > max_bytes:
                    raise BackupError("Read budget exceeded; narrow the selected source or raise the explicit limit")
                files[key] = FileInfo(path, info.st_size, info.st_dev,
                                      info.st_ino, info.st_mtime_ns)
            else:
                raise BackupError("Special devices, sockets and nonregular files are unsupported")
    return Inventory(files, folders, total, markers)


def fingerprint(file: FileInfo) -> str:
    """Open a single regular file, reject identity changes and stream SHA256."""
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(file.path, flags), "rb") as stream:
            start = os.fstat(stream.fileno())
            if (not stat.S_ISREG(start.st_mode)
                    or (start.st_dev, start.st_ino, start.st_size, start.st_mtime_ns)
                    != (file.device, file.inode, file.size, file.mtime_ns)):
                raise BackupError("File changed between inventory and content verification")
            sha = hashlib.sha256()
            while True:
                data = stream.read(CHUNK_SIZE)
                if not data:
                    break
                sha.update(data)
            end = os.fstat(stream.fileno())
        current = file.path.lstat()
        for obj in (end, current):
            if (not stat.S_ISREG(obj.st_mode) or is_link_or_reparse(file.path, obj)
                    or (obj.st_dev, obj.st_ino, obj.st_size, obj.st_mtime_ns)
                    != (file.device, file.inode, file.size, file.mtime_ns)):
                raise BackupError("File changed during hashing; repeat after data is idle")
    except OSError as exc:
        raise BackupError("File unreadable or changed during comparison") from exc
    return sha.hexdigest()


def compare(source: Inventory, backup: Inventory, *, verify: bool,
            source_device: int, backup_device: int) -> tuple[dict, list[str]]:
    missing = sorted(source.files.keys() - backup.files.keys())
    extras = sorted(backup.files.keys() - source.files.keys())
    missing_dirs = sorted(source.folders - backup.folders)
    changed_sizes = sorted(key for key in source.files.keys() & backup.files.keys()
                           if source.files[key].size != backup.files[key].size)
    # A same-volume hard link is not a separately recoverable backup.
    # Only compare nonzero inode identifiers; some Windows mounts report
    # unavailable/zero IDs and therefore remain unverified by this test.
    aliases = sorted(
        key for key in source.files.keys() & backup.files.keys()
        if source.files[key].device == backup.files[key].device
        and source.files[key].inode != 0
        and source.files[key].inode == backup.files[key].inode
    )
    modified: list[str] = []
    common = sorted(source.files.keys() & backup.files.keys())
    if verify:
        # Hash *every* file on both sides, including same-size files and
        # files missing their counterpart. This detects mid-run changes.
        a = {name: fingerprint(item) for name, item in sorted(source.files.items())}
        b = {name: fingerprint(item) for name, item in sorted(backup.files.items())}
        modified = [name for name in common if a[name] != b[name]]
    complete = not (missing or missing_dirs or changed_sizes or modified or aliases)
    if verify:
        status = ("CONTENT_MATCH_EXTRAS_REVIEW" if extras else "CONTENT_MATCH")
        if aliases:
            status = "NOT_INDEPENDENT_FILE_COPY"
        elif not complete:
            status = "BACKUP_CONTENT_MISMATCH"
    else:
        status = "INVENTORY_ONLY_NOT_CONTENT_VERIFIED"
    result = {
        "schema": SCHEMA,
        "status": status,
        "content_hashed": verify,
        "required_files": len(source.files),
        "backup_files": len(backup.files),
        "source_bytes": source.total_bytes,
        "backup_bytes": backup.total_bytes,
        "missing_files": len(missing),
        "missing_folders": len(missing_dirs),
        "different_file_sizes": len(changed_sizes),
        "different_file_hashes": len(modified),
        "same_file_identity_count": len(aliases),
        "extra_backup_files": len(extras),
        "source_markers_present": source.markers,
        "backup_markers_present": backup.markers,
        "device_check": ("SAME_DEVICE_REPORTED_OR_UNKNOWN"
                         if source_device == backup_device
                         else "DIFFERENT_DEVICE_IDS_NOT_PHYSICAL_PROOF"),
        "data_copy_performed": False,
        "restore_test_performed": False,
        "external_media_confirmed": False,
        "backup_recovery_proven": False,
        "os_install_authorized": False,
        "usb_format_authorized": False,
        "verification_succeeded": bool(verify and complete),
    }
    return result, missing[:12] + missing_dirs[:12] + changed_sizes[:12] + modified[:12] + aliases[:12]


def write_report_new(path: Path, payload: dict, roots: tuple[Path, Path]) -> None:
    target = path.absolute()
    try:
        reject_linked_ancestors(target.parent)
        parent_st = target.parent.lstat()
        if is_link_or_reparse(target.parent, parent_st):
            raise BackupError("Linked/junction report parent is unsupported")
        # Reject alternate path spellings through an earlier parent link.
        # The destination must not resolve into either inspected tree.
        resolved = target.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise BackupError("Report parent is inaccessible or circularly linked") from exc
    for root in roots:
        if (target == root or root in target.parents
                or resolved == root or root in resolved.parents):
            raise BackupError("Report must be outside both inspected trees")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(target, flags, 0o600), "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Nightglass no-copy backup integrity verification")
    ap.add_argument("--mode", choices=MODES, default="Preview")
    ap.add_argument("--source", type=Path, help="Exact original source directory")
    ap.add_argument("--backup", type=Path, help="Exact corresponding copied directory")
    ap.add_argument("--report", type=Path, help="Optional NEW, non-overwriting local summary outside both roots")
    ap.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    ap.add_argument("--show-differences", action="store_true",
                    help="Display up to 48 relative path names locally; filenames may be private")
    args = ap.parse_args(argv)
    if args.mode == "Preview":
        if args.report or args.show_differences:
            ap.error("Preview never writes a report or lists private filenames")
        print("NIGHTGLASS BACKUP PRESERVATION — PREVIEW ONLY")
        print("No directory enumeration, file reads, hash calculations, media selection or writes.")
        print("Inspect: metadata comparison; Verify: stream-hash both explicit source and backup.")
        print("Includes hidden .git/.env/.venv content; symbolic links/junctions block.")
        print("This tool does NOT copy files, authorize an OS install, or prove recovery.")
        return 0
    if args.source is None or args.backup is None:
        ap.error("Inspect and Verify require BOTH explicitly supplied directories")
    if not (1 <= args.max_files <= 1_000_000 and 1 <= args.max_bytes <= 32 * 1024**4):
        ap.error("Explicit audit budgets out of supported range")
    try:
        original = checked_root(args.source)
        replica = checked_root(args.backup)
        separated(original, replica)
        original_st = original.stat()
        backup_st = replica.stat()
        a = inventory(original, max_files=args.max_files, max_bytes=args.max_bytes)
        b = inventory(replica, max_files=args.max_files, max_bytes=args.max_bytes)
        result, differences = compare(a, b, verify=args.mode == "Verify",
                                      source_device=original_st.st_dev,
                                      backup_device=backup_st.st_dev)
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.show_differences:
            for rel in differences[:48]:
                print("LOCAL REVIEW FILE: " + rel)
        if args.report:
            write_report_new(args.report, result, (original, replica))
        # Missing copied content is a blocker even for metadata-only Inspect.
        if (result["missing_files"] or result["missing_folders"]
                or result["different_file_sizes"] or result["same_file_identity_count"]):
            return 1
        if args.mode == "Verify" and not result["verification_succeeded"]:
            return 1
        return 0
    except (BackupError, OSError) as exc:
        # No machine paths, file names, credential contents or hashes printed.
        print("HOLD: " + type(exc).__name__ + " — backup readiness not proven.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
