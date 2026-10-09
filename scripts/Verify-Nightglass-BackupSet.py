#!/usr/bin/env python3
"""Nightglass multi-source backup coverage gate (read-only; preview default).

Checks individually chosen source/copied-directory pairs through the
Phase 10 read-only backup checker. Preview does not read the manifest or
selected directory trees. No copies, restores, archive extraction,
installer operations, Git calls, network, USB or volume writes.

A user's PRIVATE mapping manifest stays local and must never be committed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

SCHEMA = "nightglass.backup-set.v1"
MODES = ("Preview", "Inspect", "Verify")
ID = re.compile(r"[a-z][a-z0-9_-]{1,30}\Z")
MAX_MANIFEST_BYTES = 64 * 1024
MAX_PAIRS = 32
BASE = Path(__file__).absolute().parent
CHECKER = BASE / "Inspect-Nightglass-Backup.py"


class SetError(ValueError):
    """Incomplete, unsafe or ambiguous collection of backup folders."""


def unique_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise SetError("Duplicate manifest field")
        obj[key] = value
    return obj


def checker_module():
    """Load ONLY the fixed companion module, never a manifest-supplied path."""
    if CHECKER.is_symlink() or not CHECKER.is_file():
        raise SetError("Nightglass backup checker unavailable")
    spec = importlib.util.spec_from_file_location("nightglass_local_backup_checker", CHECKER)
    if spec is None or spec.loader is None:
        raise SetError("Cannot load companion backup checker")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # needed for postponed-annotation dataclasses
    spec.loader.exec_module(module)
    return module


def read_manifest(path: Path, module) -> list[tuple[str, Path, Path]]:
    """Regular, size-limited, duplicate-key-free JSON from explicit local path."""
    try:
        module.reject_linked_ancestors(path)
        before = path.lstat()
        if module.is_link_or_reparse(path, before) or not stat.S_ISREG(before.st_mode):
            raise SetError("Manifest must be a regular file, not a link/reparse point")
        if before.st_size < 1 or before.st_size > MAX_MANIFEST_BYTES:
            raise SetError("Manifest empty or exceeds fixed size limit")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                    before.st_dev, before.st_ino, before.st_size):
                raise SetError("Manifest changed during open")
            payload = stream.read(MAX_MANIFEST_BYTES + 1)
            end = os.fstat(stream.fileno())
        after = path.lstat()
        ids = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if (len(payload) > MAX_MANIFEST_BYTES or ids(before) != ids(end)
                or ids(end) != ids(after)):
            raise SetError("Manifest changed or exceeded limit during read")
        data = json.loads(
            payload.decode("utf-8"), object_pairs_hook=unique_keys,
            parse_constant=lambda _: (_ for _ in ()).throw(
                SetError("Non-finite JSON values forbidden")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SetError("Manifest missing, unreadable or invalid JSON") from exc
    if (not isinstance(data, dict) or type(data.get("version")) is not int
            or data["version"] != 1 or set(data) != {"version", "entries"}):
        raise SetError("Unsupported or ambiguous backup-set manifest schema")
    entries = data["entries"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_PAIRS:
        raise SetError("Choose 1–32 explicit source/backup directory pairs")
    seen_ids: set[str] = set()
    selected: list[tuple[str, Path, Path]] = []
    all_roots: list[Path] = []
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"id", "source", "backup"}:
            raise SetError("Every entry must contain only id, source and backup")
        label, src, dst = item["id"], item["source"], item["backup"]
        if not isinstance(label, str) or not ID.fullmatch(label) or label in seen_ids:
            raise SetError("Entry IDs must be unique, short, and non-sensitive")
        if any(not isinstance(v, str) or not v or "\x00" in v
               or not Path(v).is_absolute() for v in (src, dst)):
            raise SetError("Both directory paths must be explicit absolute paths")
        seen_ids.add(label)
        s = module.checked_root(Path(src))
        b = module.checked_root(Path(dst))
        module.separated(s, b)
        for current in (s, b):
            if any((current == other or current in other.parents
                    or other in current.parents) for other in all_roots):
                raise SetError("Backup-set roots must all be distinct and nonoverlapping")
            all_roots.append(current)
        selected.append((label, s, b))
    return selected


def evaluate(entries, module, *, mode: str, max_files: int, max_bytes: int):
    reports = []
    roots = []
    for label, source, backup in entries:
        roots.extend((source, backup))
        a = module.inventory(source, max_files=max_files, max_bytes=max_bytes)
        b = module.inventory(backup, max_files=max_files, max_bytes=max_bytes)
        # Empty source directories cannot establish that a useful
        # project/data backup exists. Block instead of vacuous PASS.
        if not a.files:
            raise SetError("A selected source contains no regular files; review backup scope")
        source_device = source.stat().st_dev
        backup_device = backup.stat().st_dev
        result, _ = module.compare(
            a, b, verify=(mode == "Verify"),
            source_device=source_device, backup_device=backup_device,
        )
        reports.append({"id": label, **result})
    all_content = mode == "Verify" and all(
        x["verification_succeeded"] for x in reports)
    any_difference = any(
        x["missing_files"] or x["missing_folders"] or x["different_file_sizes"]
        or x["same_file_identity_count"]
        or (mode == "Verify" and not x["verification_succeeded"])
        for x in reports)
    total_extra = sum(x["extra_backup_files"] for x in reports)
    report = {
        "schema": SCHEMA,
        "mode": mode,
        "status": ("CONTENT_MATCH_EXTRAS_REVIEW" if all_content and total_extra
                   else "CONTENT_MATCH" if all_content
                   else "INCOMPLETE" if any_difference
                   else "INVENTORY_ONLY_NOT_CONTENT_VERIFIED"),
        "entry_count": len(reports),
        "entries": reports,
        "all_selected_content_matched": bool(all_content),
        "additional_backup_files_to_review": total_extra,
        "full_machine_backup_completeness_proven": False,
        "physical_external_media_verified": False,
        "restore_drill_performed": False,
        "restore_proven": False,
        "windows_install_authorized": False,
        "fedora_install_authorized": False,
        "usb_format_authorized": False,
        "file_copy_performed": False,
        "data_deleted_or_modified": False,
    }
    return report, roots


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Nightglass multi-directory backup evidence gate")
    ap.add_argument("--mode", choices=MODES, default="Preview")
    ap.add_argument("--manifest", type=Path, help="PRIVATE local JSON mapping source/backup pairs")
    ap.add_argument("--report", type=Path, help="Optional NEW report outside all scanned roots")
    ap.add_argument("--max-files", type=int, default=50_000)
    ap.add_argument("--max-bytes", type=int, default=250 * 1024**3)
    args = ap.parse_args(argv)
    if args.mode == "Preview":
        if args.report:
            ap.error("Preview never writes a report")
        print("NIGHTGLASS BACKUP SET — PREVIEW ONLY")
        print("No access to selected manifest/data trees, no hashing, copying, USB or OS changes.")
        print("Inspect: selected tree metadata; Verify: content hashes for all selected trees.")
        print("Manifest must remain local and outside GitHub; no actual paths are printed.")
        return 0
    if args.manifest is None:
        ap.error("Inspect and Verify require an explicit PRIVATE manifest path")
    if not (1 <= args.max_files <= 1_000_000
            and 1 <= args.max_bytes <= 32 * 1024**4):
        ap.error("Unsupported explicit audit limits")
    try:
        module = checker_module()
        entries = read_manifest(args.manifest, module)
        report, roots = evaluate(
            entries, module, mode=args.mode,
            max_files=args.max_files, max_bytes=args.max_bytes)
        print(json.dumps(report, indent=2, sort_keys=True))
        if args.report:
            # The companion helper refuses reports inside either root.
            module.write_report_new(args.report, report, tuple(roots))
        if report["status"] == "INCOMPLETE":
            return 1
        return 0
    except (SetError, OSError, ValueError) as exc:
        # No secret-bearing paths, file data or machine identifiers logged.
        print("HOLD: " + type(exc).__name__ +
              " — selected backup set was not verified.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
