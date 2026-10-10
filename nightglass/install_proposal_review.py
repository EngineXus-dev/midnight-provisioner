"""Review an untrusted, user-supplied installer operation proposal; never execute it.

Input is intentionally *not* a source of verified physical disk identity,
complete partition geometry, official installer provenance, user backups or
consent. The proposal may be fabricated, partial, out of date or malicious.
This parser never produces write-capable command arguments or permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import stat
from typing import Any

SCHEMA = "nightglass.untrusted-install-proposal.v1"
REVIEW_SCHEMA = "nightglass.install-proposal-review.v1"
STATUS = "HOLD_UNTRUSTED_PROPOSAL_NO_DISK_WRITES"
MAX_BYTES = 65536
MAX_DEVICES = 16
MAX_OPERATIONS = 96
OPAQUE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
ACTIONS = frozenset((
    "create_partition", "delete_partition", "format_partition", "resize_partition",
    "write_bootloader", "update_firmware_entry",
))
PART_ACTIONS = frozenset(("delete_partition", "format_partition", "resize_partition"))
BOOT_ACTIONS = frozenset(("write_bootloader", "update_firmware_entry"))
EXPECTED_KEYS = frozenset(("schema", "source", "intent", "target_ref", "devices", "operations"))
DEVICE_KEYS = frozenset(("ref", "role", "partition_count"))
OPERATION_KEYS = frozenset(("action", "device_ref", "partition_ref"))


class ProposalError(ValueError):
    """Bad or incomplete proposal, never a reason to infer that a disk is empty."""


@dataclass(frozen=True)
class ProposedImpact:
    action: str
    device_ref: str
    partition_ref: str | None
    outside_declared_target: bool
    boot_or_firmware_related: bool


@dataclass(frozen=True)
class ProposalReview:
    schema: str
    status: str
    source_trust: str
    intent: str
    target_ref: str
    declared_device_count: int
    declared_operation_count: int
    claimed_target_partitions: int | None
    impacts: tuple[ProposedImpact, ...]
    other_drive_changes_claimed: bool
    boot_or_firmware_changes_claimed: bool
    completeness_independently_verified: bool
    physical_device_identity_verified: bool
    actual_partition_geometry_verified: bool
    all_connected_disks_accounted_for: bool
    official_installer_origin_verified: bool
    user_backups_verified_by_nightglass: bool
    independent_destructive_consent: bool
    disk_write_authorized: bool
    os_install_authorized: bool
    blockers: tuple[str, ...]


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ProposalError("Duplicate JSON key refused")
        result[name] = value
    return result


def _reject_constant(value: str) -> None:
    raise ProposalError("Nonfinite JSON number refused")


def _name(value: Any) -> bool:
    return type(value) is str and OPAQUE.fullmatch(value) is not None


def _keys(value: Any, keys: frozenset[str]) -> bool:
    return type(value) is dict and set(value) == keys


def parse_proposal(content: str) -> dict[str, Any]:
    """Strict bounded in-memory JSON; no external commands or filesystem reads."""
    if type(content) is not str:
        raise ProposalError("Expected JSON text")
    if len(content.encode("utf-8")) > MAX_BYTES:
        raise ProposalError("Proposal exceeds maximum size")
    try:
        result = json.loads(content, object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except ProposalError:
        raise  # keep the specific message (e.g. duplicate key)
    except (ValueError, RecursionError) as exc:  # incl. JSON, Unicode and int-digit-limit errors
        raise ProposalError("Malformed or excessively nested JSON") from exc
    if not _keys(result, EXPECTED_KEYS):
        raise ProposalError("Unexpected or missing proposal fields")
    if result["schema"] != SCHEMA or result["source"] != "unverified_user_supplied":
        raise ProposalError("Unsupported or falsely authoritative proposal source")
    if result["intent"] not in ("format_target", "coexist"):
        raise ProposalError("Expected explicit format_target or coexist intent")
    if not _name(result["target_ref"]):
        raise ProposalError("Target reference must be a bounded opaque token")
    devices = result["devices"]
    operations = result["operations"]
    if (type(devices) is not list or not 1 <= len(devices) <= MAX_DEVICES
            or type(operations) is not list or not 1 <= len(operations) <= MAX_OPERATIONS):
        raise ProposalError("Incomplete or oversized devices/operations inventory")
    ids: set[str] = set()
    target_count = 0
    for device in devices:
        if not _keys(device, DEVICE_KEYS) or not _name(device["ref"]):
            raise ProposalError("Invalid device entry; labels/paths/serials are not permitted")
        if device["ref"] in ids or device["role"] not in ("target", "other"):
            raise ProposalError("Duplicate device or unknown declared role")
        ids.add(device["ref"])
        if device["role"] == "target":
            target_count += 1
            if device["ref"] != result["target_ref"]:
                raise ProposalError("Declared target does not match intended target")
        elif device["ref"] == result["target_ref"]:
            raise ProposalError("Target mislabeled as other")
        count = device["partition_count"]
        if count is not None and (type(count) is not int or not 0 <= count <= 256):
            raise ProposalError("Partition count must be unknown or a bounded integer")
    if target_count != 1 or result["target_ref"] not in ids:
        raise ProposalError("Exactly one declared target device required")
    seen: set[tuple[str, str, str | None]] = set()
    for operation in operations:
        if not _keys(operation, OPERATION_KEYS):
            raise ProposalError("Invalid operation fields; no command strings accepted")
        a, d, partition = (operation["action"], operation["device_ref"],
                           operation["partition_ref"])
        if not _name(a) or a not in ACTIONS or not _name(d) or d not in ids:
            raise ProposalError("Unsupported operation or undeclared destination")
        if partition is not None and not _name(partition):
            raise ProposalError("Partition reference must be a bounded opaque token")
        if (a in PART_ACTIONS and partition is None) or (
                a in BOOT_ACTIONS and partition is not None):
            raise ProposalError("Incomplete partition operation or unexpected boot partition token")
        key = (a, d, partition)
        if key in seen:
            raise ProposalError("Duplicate operation entry")
        seen.add(key)
    return result


def read_proposal_file(path: Path) -> dict[str, Any]:
    """Explicit small local file only. Refuse links and uncertain file types."""
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ProposalError("Provide an absolute, non-traversing local JSON file path")
    # Reject linked ancestors, including reparse points on Windows.
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except OSError as exc:
            raise ProposalError("File path cannot be inspected") from exc
        attributes = getattr(info, "st_file_attributes", 0)
        if stat.S_ISLNK(info.st_mode) or (
                attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise ProposalError("Linked/reparse input path refused")
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ProposalError("Input must be a bounded ordinary JSON file")
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ProposalError("Input changed or oversized")
        data = raw.decode("utf-8-sig", errors="strict")
        return parse_proposal(data)
    except (OSError, UnicodeError) as exc:
        raise ProposalError("Input is inaccessible or not valid UTF-8") from exc


def review_proposal(plan: dict[str, Any]) -> ProposalReview:
    """Re-validate even programmatically supplied dictionaries; ALWAYS HOLD."""
    try:
        content = json.dumps(plan, allow_nan=False, ensure_ascii=True)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ProposalError("Invalid proposal object") from exc
    valid = parse_proposal(content)
    target = valid["target_ref"]
    devices = {d["ref"]: d for d in valid["devices"]}
    impacts = tuple(
        ProposedImpact(
            action=entry["action"],
            device_ref=entry["device_ref"],
            partition_ref=entry["partition_ref"],
            outside_declared_target=entry["device_ref"] != target,
            boot_or_firmware_related=entry["action"] in BOOT_ACTIONS,
        )
        for entry in valid["operations"]
    )
    other = any(effect.outside_declared_target for effect in impacts)
    boot = any(effect.boot_or_firmware_related for effect in impacts)
    blockers = [
        "This is an UNTRUSTED USER-SUPPLIED PROPOSAL, not an official installer dry run.",
        "Opaque target references are not verified physical drives or stable device identities.",
        "Declared partition counts and operation lists may be incomplete, stale or false.",
        "All connected physical disks and EFI/firmware side effects require independent verification.",
        "No complete official BEFORE/AFTER partition or boot write manifest has been proved.",
        "You must independently back up anything you want to retain; Nightglass does not verify backups.",
        "A real installer must reidentify targets, verify genuine media and obtain separate destructive consent.",
    ]
    if other:
        blockers.insert(1, "DECLARED EFFECT ON OTHER DRIVE: explicit additional user review required.")
    else:
        blockers.insert(1, "No other-drive edits declared does NOT prove other disks will remain unchanged.")
    if boot:
        blockers.insert(1, "EFI/BOOT/FIRMWARE CHANGE DECLARED; exact device/boot impact unverified.")
    else:
        blockers.insert(1, "No boot changes declared does NOT prove EFI/firmware will remain unchanged.")
    return ProposalReview(
        schema=REVIEW_SCHEMA,
        status=STATUS,
        source_trust="UNTRUSTED_USER_SUPPLIED_NO_INSTALLER_PROVENANCE",
        intent=valid["intent"],
        target_ref=target,
        declared_device_count=len(devices),
        declared_operation_count=len(impacts),
        claimed_target_partitions=devices[target]["partition_count"],
        impacts=impacts,
        other_drive_changes_claimed=other,
        boot_or_firmware_changes_claimed=boot,
        completeness_independently_verified=False,
        physical_device_identity_verified=False,
        actual_partition_geometry_verified=False,
        all_connected_disks_accounted_for=False,
        official_installer_origin_verified=False,
        user_backups_verified_by_nightglass=False,
        independent_destructive_consent=False,
        disk_write_authorized=False,
        os_install_authorized=False,
        blockers=tuple(blockers),
    )


def describe_proposal(review: ProposalReview) -> str:
    lines = [
        "NIGHTGLASS OPERATION PROPOSAL REVIEW — UNTRUSTED / READ ONLY",
        f"STATUS: {review.status}",
        f"Intent: {review.intent} | Opaque target: {review.target_ref}",
        f"Declared devices: {review.declared_device_count}",
        f"Declared operations: {review.declared_operation_count}",
        "PHYSICAL TARGET, PARTITION GEOMETRY AND EFI PATH: NOT VERIFIED",
        "Declared operations (NOT COMMANDS):",
    ]
    for impact in review.impacts:
        flags = []
        if impact.outside_declared_target:
            flags.append("OTHER-DRIVE")
        if impact.boot_or_firmware_related:
            flags.append("BOOT")
        labels = " / ".join(flags) if flags else "TARGET"
        lines.append(f"  {impact.action} on {impact.device_ref} [{labels}]"
                     + (f" ({impact.partition_ref})" if impact.partition_ref else ""))
    lines.extend(("", "REQUIRED INDEPENDENT CHECKS:"))
    lines.extend("- " + blocker for blocker in review.blockers)
    lines.append("No disk writes, OS installation, EFI update or backup operation is authorized.")
    return "\n".join(lines)
