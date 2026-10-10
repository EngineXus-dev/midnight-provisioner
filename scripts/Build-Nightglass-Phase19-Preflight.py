#!/usr/bin/env python3
"""Nightglass Phase 19: fail-closed preinstall blocker inventory.

Read only. Consumes a bounded, sanitized Phase 18 host report. Optionally hashes
an existing Fedora ISO against a checksum supplied by the operator. Neither a
matching hash nor a positive machine observation authorizes deployment.
No network, installation, formatting, media writes, copying or VM operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

HOST_SCHEMA = "nightglass.windows-host-observation.v1"
SCHEMA = "nightglass.preinstall-blockers.v1"
MAX_REPORT_BYTES = 64 * 1024
MIN_ISO_BYTES = 128 * 1024 * 1024
MAX_ISO_BYTES = 12 * 1024 * 1024 * 1024
EXPECTED = frozenset({
    "windows_servicing", "firmware", "secure_boot", "fast_startup",
    "volume_encryption", "ram_budget", "virtualization_firmware",
    "os_disk_layout", "partition_map",
})
MANUAL = (
    ("backup_independence", "Independent full-system and personal-data backups verified on separate media"),
    ("recovery_drill", "Controlled file restoration demonstrated without overwriting production files"),
    ("recovery_key", "Any BitLocker/device-encryption recovery key available securely offline"),
    ("recovery_media", "Windows recovery media and boot procedure independently confirmed"),
    ("partition_plan", "Physical EFI/Recovery/OEM/Windows partitions and disks reviewed before changes"),
    ("windows_servicing", "Windows version security servicing/ESU coverage verified independently"),
    ("shutdown_ntfs", "Windows Fast Startup and hibernated NTFS risk resolved before Linux access"),
    ("fedora_iso_provenance", "Authentic Fedora KDE image and official digest verified independently"),
    ("fedora_live_usb_trial", "Fedora live media checked on hardware before installation or partition changes"),
    ("fedora_security_acceptance", "Actual Fedora KVM/libvirt/SELinux/sVirt and guest network-denial acceptance"),
    ("cold_restore", "Separately authorized cold-recovery drill, including guest and Windows recovery paths"),
)


class GateError(ValueError):
    """Untrusted or incomplete local evidence; never return deployment approval."""


def pairs_unique(pairs: list[tuple[str, object]]) -> dict:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise GateError("Duplicate JSON key")
        obj[key] = value
    return obj


def reject_linked_path(path: Path) -> os.stat_result:
    if not path.is_absolute() or ".." in path.parts:
        raise GateError("Evidence path must be an explicit absolute path without traversal")
    current = path
    while True:
        try:
            st = current.lstat()
        except OSError as exc:
            raise GateError("Evidence path is missing or unreadable") from exc
        if (stat.S_ISLNK(st.st_mode)
                or getattr(st, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise GateError("Links and reparse points are not permitted for evidence")
        if current.parent == current:
            break
        current = current.parent
    if not stat.S_ISREG(path.lstat().st_mode):
        raise GateError("Evidence must be a regular file")
    return path.lstat()


def read_host_report(path: Path) -> dict:
    before = reject_linked_path(path)
    if not 1 <= before.st_size <= MAX_REPORT_BYTES:
        raise GateError("Host evidence missing or exceeds bounded size")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                    before.st_dev, before.st_ino, before.st_size):
                raise GateError("Host evidence changed during open")
            data = stream.read(MAX_REPORT_BYTES + 1)
            end = os.fstat(stream.fileno())
        after = reject_linked_path(path)
    except OSError as exc:
        raise GateError("Host evidence cannot be read safely") from exc
    signature = lambda obj: (obj.st_dev, obj.st_ino, obj.st_size, obj.st_mtime_ns)
    if len(data) > MAX_REPORT_BYTES or signature(before) != signature(end) or signature(end) != signature(after):
        raise GateError("Host evidence changed during read")
    try:
        item = json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(GateError("Non-finite JSON value")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GateError("Host evidence is not valid UTF-8 JSON") from exc
    return validate_host(item)


def validate_host(item: object) -> dict:
    if not isinstance(item, dict):
        raise GateError("Host evidence must be an object")
    if (item.get("schema") != HOST_SCHEMA
            or item.get("mode") != "READ_ONLY_NATIVE_WINDOWS"
            or item.get("status") != "HOLD_MANUAL_DEPLOYMENT_APPROVAL"):
        raise GateError("Unexpected host schema or unsafe authorization status")
    for flag in ("full_backup_verified", "restore_verified",
                 "bitlocker_recovery_key_verified", "windows_install_authorized",
                 "fedora_install_authorized", "disk_partition_write_authorized",
                 "real_fedora_host_isolation_verified",
                 "contains_serials_secrets_or_raw_disk_paths"):
        if item.get(flag) is not False:
            raise GateError("Host evidence contains missing or unsafe deployment assertion")
    observed = item.get("observations")
    if not isinstance(observed, list) or len(observed) != len(EXPECTED):
        raise GateError("Host observations are incomplete")
    names = set()
    for entry in observed:
        if not isinstance(entry, dict) or set(entry) != {"name", "state", "evidence", "next"}:
            raise GateError("Invalid host observation structure")
        name, state = entry["name"], entry["state"]
        if not isinstance(name, str) or name not in EXPECTED or name in names:
            raise GateError("Missing or repeated host observation")
        if state not in ("OBSERVED", "REVIEW", "HOLD", "UNKNOWN"):
            raise GateError("Unrecognized host observation state")
        if any(not isinstance(entry[key], str) or len(entry[key]) > 500
               for key in ("evidence", "next")):
            raise GateError("Oversized or malformed observation text")
        names.add(name)
    if names != EXPECTED:
        raise GateError("Incomplete host observation set")
    holds = sum(x["state"] == "HOLD" for x in observed)
    unknowns = sum(x["state"] == "UNKNOWN" for x in observed)
    if type(item.get("hold_checks")) is not int or item["hold_checks"] != holds:
        raise GateError("Inconsistent host HOLD count")
    if type(item.get("unknown_checks")) is not int or item["unknown_checks"] != unknowns:
        raise GateError("Inconsistent host UNKNOWN count")
    if item.get("observed_os_family") not in (
            "WINDOWS_10", "WINDOWS_11", "OTHER_WINDOWS", "UNKNOWN"):
        raise GateError("Invalid reported operating system family")
    manual = item.get("manual_requirements")
    if not isinstance(manual, list) or len(manual) < 8 or any(
            not isinstance(x, str) or len(x) > 500 for x in manual):
        raise GateError("Missing Phase 18 manual requirements")
    return item


def verify_iso(path: Path | None, expected: str | None) -> dict:
    if path is None and expected is None:
        return {"status": "NOT_SUPPLIED", "sha256_matches_operator_digest": False,
                "official_fedora_provenance_verified": False}
    if path is None or expected is None or not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
        raise GateError("Both ISO file and 64-digit expected SHA-256 are required")
    if path.suffix.lower() != ".iso":
        raise GateError("Expected a local .iso file")
    before = reject_linked_path(path)
    if not MIN_ISO_BYTES <= before.st_size <= MAX_ISO_BYTES:
        raise GateError("ISO file size outside bounded verification range")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                    before.st_dev, before.st_ino, before.st_size):
                raise GateError("ISO changed during open")
            digest = hashlib.sha256()
            while part := stream.read(1024 * 1024):
                digest.update(part)
            end = os.fstat(stream.fileno())
        after = reject_linked_path(path)
    except OSError as exc:
        raise GateError("Cannot safely read ISO") from exc
    signature = lambda obj: (obj.st_dev, obj.st_ino, obj.st_size, obj.st_mtime_ns)
    if signature(before) != signature(end) or signature(end) != signature(after):
        raise GateError("ISO modified during hashing")
    matched = digest.hexdigest() == expected.lower()
    return {
        "status": "HASH_MATCHES_OPERATOR_INPUT" if matched else "HASH_MISMATCH_BLOCKED",
        "sha256_matches_operator_digest": matched,
        "official_fedora_provenance_verified": False,
    }


def assess(host: dict, iso: dict | None = None) -> dict:
    verified = validate_host(host)
    observations = {x["name"]: x["state"] for x in verified["observations"]}
    iso = iso if iso is not None else verify_iso(None, None)
    if iso.get("official_fedora_provenance_verified") is not False:
        raise GateError("ISO hash comparison cannot certify authenticity")
    if iso.get("sha256_matches_operator_digest") is not True and iso.get("sha256_matches_operator_digest") is not False:
        raise GateError("Invalid ISO comparison")
    barriers = []
    for key, requirement in MANUAL:
        barriers.append({"id": key, "state": "PENDING_INDEPENDENT_EVIDENCE",
                         "requirement": requirement})
    for key in ("firmware", "secure_boot", "fast_startup", "volume_encryption",
                "virtualization_firmware", "os_disk_layout", "partition_map"):
        state = observations[key]
        if state in ("UNKNOWN", "HOLD"):
            barriers.append({"id": "observed_" + key, "state": state,
                             "requirement": "Resolve this native Windows observation before installation planning"})
    if iso["status"] != "HASH_MATCHES_OPERATOR_INPUT":
        barriers.append({"id": "fedora_iso_bytes", "state": iso["status"],
                         "requirement": "Provide an authentic, independently obtained official ISO hash and local image"})
    return {
        "schema": SCHEMA,
        "status": "HOLD_MANUAL_AND_PHYSICAL_ACCEPTANCE",
        "phase18_input_schema_verified": True,
        "host_observation_status": verified["status"],
        "observed_os_family": verified["observed_os_family"],
        "host_hold_count": verified["hold_checks"],
        "host_unknown_count": verified["unknown_checks"],
        "iso_verification": iso,
        "blockers": barriers,
        "pending_independent_checks": len(barriers),
        "backup_proven": False,
        "recovery_proven": False,
        "windows_security_servicing_proven": False,
        "physical_fedora_host_security_proven": False,
        "fedora_live_usb_safety_proven": False,
        "windows_install_authorized": False,
        "fedora_install_authorized": False,
        "disk_write_authorized": False,
        "vm_start_authorized": False,
        "report_contains_sensitive_hardware_identifiers": False,
        "note": "Read-only preinstall inventory. Human evidence, live Fedora host and rollback testing remain separate.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-report", type=Path, required=True)
    parser.add_argument("--iso", type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)
    try:
        host = read_host_report(args.host_report)
        iso = verify_iso(args.iso, args.expected_sha256)
        if iso["status"] == "HASH_MISMATCH_BLOCKED":
            raise GateError("ISO digest mismatch")
        result = assess(host, iso)
    except (GateError, OSError, ValueError) as exc:
        print("HOLD: " + type(exc).__name__ + "; phase19 evidence is invalid or incomplete.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
