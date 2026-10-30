#!/usr/bin/env python3
"""Midnight Provisioner Phase 22: offline recovery and selected-folder backup review.

Preview (default) reads NOTHING. Assess reads explicitly supplied local JSON
reports only; never scans disks, modifies backup files, restores files, enables
WinRE, mounts drives, downloads an ISO, elevates, starts a VM or installs an OS.
A JSON assertion is not independent backup/restore/media authenticity evidence.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import stat
import sys

SCHEMA = "midnight_provisioner.recovery-backup-acceptance.v1"
WINRE_SCHEMA = "midnight-provisioner.winre-triage.v1"
BACKUP_SCHEMA = "midnight-provisioner.backup-set.v1"
MAX_JSON = 65536
REASONS = frozenset((
    "OS_ROOT_UNAVAILABLE", "UTILITY_MISSING", "UTILITY_NONZERO_EXIT",
    "UTILITY_INVOCATION_ERROR", "UTILITY_OUTPUT_TOO_LARGE",
    "UTILITY_OUTPUT_EMPTY", "UTILITY_OUTPUT_UNRECOGNIZED",
    "STATUS_ENGLISH_ENABLED", "STATUS_ENGLISH_DISABLED",
))
FLAGS = (
    "windows_recovery_boot_proven", "recovery_media_proven",
    "backup_independence_proven", "restoration_proven",
    "bitlocker_recovery_key_proven", "ntfs_clean_shutdown_proven",
    "secure_boot_proven", "official_fedora_iso_provenance_proven",
    "real_fedora_isolation_proven", "windows_install_authorized",
    "fedora_install_authorized", "disk_write_authorized", "vm_start_authorized",
)
BACKUP_FALSE = (
    "full_machine_backup_completeness_proven", "physical_external_media_verified",
    "restore_drill_performed", "restore_proven", "windows_install_authorized",
    "fedora_install_authorized", "usb_format_authorized",
    "file_copy_performed", "data_deleted_or_modified",
)


class EvidenceError(ValueError):
    """Evidence is unsafe, incomplete or cannot prove what it asserts."""


def distinct_keys(items: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise EvidenceError("Duplicate JSON member")
        result[key] = value
    return result


def checked_file(path: Path) -> os.stat_result:
    if not path.is_absolute() or ".." in path.parts:
        raise EvidenceError("Evidence path must be absolute without parent traversal")
    part = path
    while True:
        try:
            info = part.lstat()
        except OSError as exc:
            raise EvidenceError("Evidence path unavailable") from exc
        if (stat.S_ISLNK(info.st_mode) or
                getattr(info, "st_file_attributes", 0) &
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise EvidenceError("Symlink/reparse evidence paths are not accepted")
        if part.parent == part:
            break
        part = part.parent
    latest = path.lstat()
    if not stat.S_ISREG(latest.st_mode):
        raise EvidenceError("Evidence must be a regular file")
    return latest


def read_json(path: Path) -> dict:
    before = checked_file(path)
    if before.st_size < 2 or before.st_size > MAX_JSON:
        raise EvidenceError("Evidence JSON size exceeds strict bound")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(path, flags), "rb") as reader:
            opened = os.fstat(reader.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                    before.st_dev, before.st_ino, before.st_size):
                raise EvidenceError("Evidence changed during open")
            raw = reader.read(MAX_JSON + 1)
            end = os.fstat(reader.fileno())
        after = checked_file(path)
    except OSError as exc:
        raise EvidenceError("Evidence cannot be opened safely") from exc
    sig = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns)
    if len(raw) > MAX_JSON or sig(before) != sig(end) or sig(end) != sig(after):
        raise EvidenceError("Evidence changed during read")
    try:
        obj = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=distinct_keys,
            parse_constant=lambda _: (_ for _ in ()).throw(
                EvidenceError("Nonfinite numbers are forbidden")),
        )
    except EvidenceError:
        raise  # keep the specific message (e.g. duplicate key)
    except (ValueError, RecursionError) as exc:  # incl. JSON, Unicode and int-digit-limit errors
        raise EvidenceError("Evidence must be UTF-8 JSON") from exc
    if not isinstance(obj, dict):
        raise EvidenceError("JSON root must be an object")
    return obj


def validate_winre(doc: dict) -> dict:
    if (doc.get("schema") != WINRE_SCHEMA or
            doc.get("mode") != "NATIVE_WINDOWS_READ_ONLY_NO_ELEVATION" or
            doc.get("status") != "HOLD_INDEPENDENT_RECOVERY_EVIDENCE"):
        raise EvidenceError("Unexpected WinRE evidence schema/status")
    if doc.get("raw_reagentc_output_in_report") is not False:
        raise EvidenceError("Raw WinRE output must never be copied to evidence")
    for field in FLAGS:
        if doc.get(field) is not False:
            raise EvidenceError("WinRE evidence improperly claims verified recovery or approval")
    reason = doc.get("diagnostic_reason")
    state = doc.get("winre_state")
    status = doc.get("winre_result")
    if reason not in REASONS or state not in ("UNKNOWN", "REVIEW", "HOLD"):
        raise EvidenceError("Unrecognized WinRE diagnostic")
    if doc.get("process_token_class") not in ("STANDARD_TOKEN", "ADMINISTRATOR_TOKEN", "UNKNOWN"):
        raise EvidenceError("Unrecognized token class")
    expected = {
        "STATUS_ENGLISH_ENABLED": ("REVIEW", "REPORTED_ENABLED"),
        "STATUS_ENGLISH_DISABLED": ("HOLD", "REPORTED_DISABLED"),
    }.get(reason, ("UNKNOWN", ""))
    if (state, status) != expected:
        raise EvidenceError("Contradictory WinRE diagnostic reason and result")
    return {"state": state, "reason": reason,
            "query_reached_an_unambiguous_status": reason in (
                "STATUS_ENGLISH_ENABLED", "STATUS_ENGLISH_DISABLED"),
            "recovery_boot_proven": False}


def validate_backup(doc: dict) -> dict:
    if doc.get("schema") != BACKUP_SCHEMA or doc.get("mode") != "Verify":
        raise EvidenceError("Only selected-folder SHA256 Verify evidence is accepted")
    for field in BACKUP_FALSE:
        if doc.get(field) is not False:
            raise EvidenceError("Backup checker cannot certify independent media, restore or installation")
    if doc.get("source_identity_scope") != "ALL_SELECTED_SOURCE_ROOTS":
        raise EvidenceError("Backup source hard-link check scope missing")
    entries = doc.get("entries")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 32:
        raise EvidenceError("Invalid selected-folder backup entries")
    if type(doc.get("entry_count")) is not int or doc["entry_count"] != len(entries):
        raise EvidenceError("Backup entry count mismatch")
    ids = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise EvidenceError("Invalid backup pair")
        label = entry.get("id")
        if (not isinstance(label, str) or
                re.fullmatch(r"[a-z][a-z0-9_-]{1,30}", label) is None or
                label in ids):
            raise EvidenceError("Ambiguous or repeated private backup group")
        ids.add(label)
        # The normalized reports must not contain absolute paths or hashes.
        if any(key in entry for key in ("source", "backup", "path", "sha256", "hash")):
            raise EvidenceError("Raw file metadata in normalized backup report")
        if type(entry.get("verification_succeeded")) is not bool:
            raise EvidenceError("Backup entry result missing")
    matched = doc.get("all_selected_content_matched")
    if type(matched) is not bool or matched != all(
            entry["verification_succeeded"] is True for entry in entries):
        raise EvidenceError("Backup evidence contradicts per-group results")
    extras = doc.get("additional_backup_files_to_review")
    if type(extras) is not int or extras < 0:
        raise EvidenceError("Invalid backup extra-file count")
    permitted = ("CONTENT_MATCH", "CONTENT_MATCH_EXTRAS_REVIEW", "INCOMPLETE")
    if doc.get("status") not in permitted:
        raise EvidenceError("Backup verification status is not a content-hash result")
    if matched and doc["status"] != (
            "CONTENT_MATCH_EXTRAS_REVIEW" if extras else "CONTENT_MATCH"):
        raise EvidenceError("Backup status contradicts content hash results")
    if not matched and doc["status"] != "INCOMPLETE":
        raise EvidenceError("A failing backup may not be described as matched")
    return {"selected_group_count": len(entries),
            "selected_folder_copies_match": matched,
            "extra_backup_files_to_review": extras,
            "full_machine_backup_proven": False,
            "physical_separate_media_proven": False,
            "restore_test_proven": False}


def assess(winre: dict, backup: dict | None = None) -> dict:
    recovery = validate_winre(winre)
    groups = (validate_backup(backup) if backup is not None
              else {"selected_group_count": 0,
                    "selected_folder_copies_match": False,
                    "extra_backup_files_to_review": 0,
                    "full_machine_backup_proven": False,
                    "physical_separate_media_proven": False,
                    "restore_test_proven": False})
    remaining = [
        "Confirm WinRE operational boot and trusted recovery media independently",
        "Confirm offline BitLocker or device-encryption key custody privately",
        "Verify complete independent Windows/data backup scope",
        "Perform a controlled restore into a safe separate destination",
        "Resolve Fast Startup and hibernated Windows NTFS risk",
        "Confirm Secure Boot, encryption state and supported Windows servicing",
        "Validate genuine Fedora KDE signed checksum and live-media hardware",
        "Validate real Fedora KVM/SELinux/sVirt and offline VM network denial",
    ]
    if backup is None:
        remaining.insert(2, "Optionally verify specifically selected original/copy directory pairs")
    return {
        "schema": SCHEMA,
        "status": "HOLD_RECOVERY_BACKUP_AND_PHYSICAL_ACCEPTANCE",
        "winre": recovery,
        "backup_set": groups,
        "backup_evidence_supplied": backup is not None,
        "manual_requirements": remaining,
        "full_machine_backup_proven": False,
        "controlled_restore_proven": False,
        "bitlocker_key_custody_proven": False,
        "windows_recovery_boot_proven": False,
        "clean_ntfs_shutdown_proven": False,
        "physical_fedora_host_isolation_proven": False,
        "fedora_install_authorized": False,
        "windows_install_authorized": False,
        "disk_write_authorized": False,
        "vm_start_authorized": False,
        "raw_paths_secrets_or_hashes_in_report": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("Preview", "Assess"), default="Preview")
    parser.add_argument("--winre-report", type=Path)
    parser.add_argument("--backup-report", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "Preview":
        if args.winre_report or args.backup_report:
            parser.error("Preview cannot access any reports")
        print("MIDNIGHT_PROVISIONER PHASE22 PREVIEW: no files or hardware accessed.")
        print("Assess requires a sanitized Phase21 WinRE report; backup report optional.")
        print("No report can authorize disk or OS operations.")
        return 0
    if args.winre_report is None:
        parser.error("Assess requires an explicit local WinRE report")
    try:
        winre = read_json(args.winre_report)
        backup = read_json(args.backup_report) if args.backup_report else None
        result = assess(winre, backup)
    except (EvidenceError, OSError, ValueError) as exc:
        print("HOLD: " + type(exc).__name__ +
              "; recovery/backup evidence missing or untrusted.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
