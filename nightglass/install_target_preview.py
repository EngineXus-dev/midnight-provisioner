"""Read-only Nightglass installer target preview.

Never selects a target automatically, detects a safe-to-wipe disk, executes
installer commands, writes a file, or grants approval. Discovery device labels
and indices are TEMPORARY OBSERVATIONS; the actual future OS installer must
independently reidentify and display the physical device immediately before
asking for a separate destructive-operation confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .install_disclosure import (
    UNDECIDED, FORMAT_TARGET, COEXIST, disclosure_for,
)

SCHEMA = "nightglass.install-target-preview.v1"
SCOPES = {
    UNDECIDED: "NONE",
    FORMAT_TARGET: "ENTIRE_SELECTED_DISK",
    COEXIST: "PARTITION_CHANGES_NOT_YET_SPECIFIED",
}
WARNING = (
    "No physical disk has been verified for erasure. A disk number, device "
    "name, apparent size or discovered partition count cannot identify a "
    "permanent install target. Existing files may be destroyed by formatting; "
    "Nightglass does not make or verify your backups."
)


@dataclass(frozen=True)
class TargetPreview:
    schema: str
    status: str
    intent: str
    proposed_scope: str
    target_observed_label: str
    target_size_gib_approx: int | None
    target_bus: str
    target_partitions_observed: int | None
    target_classification: str
    target_selection_source: str
    user_backup_warning_acknowledged: bool
    user_backups_proven_by_nightglass: bool
    chosen_disk_identity_verified: bool
    boot_and_efi_impact_verified: bool
    complete_writes_list_known: bool
    install_media_verified: bool
    independent_install_authorization: bool
    disk_write_authorized: bool
    os_install_authorized: bool
    warning: str
    unresolved: tuple[str, ...]


def build_target_preview(
    discovery: dict[str, Any] | None, *,
    target_index: int | None = None,
    intent: str = UNDECIDED,
    backup_warning_acknowledged: bool = False,
) -> TargetPreview:
    """Produce a frozen, fail-closed advisory record: ALWAYS HOLD.

    target_index refers only to this particular in-memory snapshot. It must
    never be turned into a Linux device path, Windows disk number or write command.
    """
    disclosure = disclosure_for(intent)
    if type(backup_warning_acknowledged) is not bool:
        raise ValueError("Acknowledgment must be a boolean")

    valid_report = (
        isinstance(discovery, dict)
        and discovery.get("schema") == "nightglass.system-discovery.v1"
        and discovery.get("read_only") is True
        and discovery.get("status") == "HOLD_USER_REVIEW_ALL_UNKNOWN_DETAILS"
        and discovery.get("installation_authorized") is False
        and discovery.get("partition_write_authorized") is False
        and discovery.get("install_target_confirmed") is False
        and discovery.get("storage_query") == "OBSERVED"
        and isinstance(discovery.get("disks"), list)
    )
    disks = discovery["disks"] if valid_report else []
    candidate: dict | None = None
    valid_selection = (
        type(target_index) is int and 0 <= target_index < len(disks)
        and len(disks) <= 32
    )
    if valid_selection and isinstance(disks[target_index], dict):
        candidate = disks[target_index]

    label = "NOT_SELECTED"
    size: int | None = None
    bus = "UNKNOWN"
    parts: int | None = None
    classification = "UNKNOWN"
    if candidate is not None:
        raw_label = candidate.get("local_id")
        if (isinstance(raw_label, str) and 0 < len(raw_label) <= 48
                and raw_label != "UNKNOWN"
                and all(ch.isalnum() or ch in " _.-" for ch in raw_label)):
            label = raw_label
        raw_size = candidate.get("size_gib_approx")
        if type(raw_size) is int and 0 < raw_size <= 10**9:
            size = raw_size
        raw_parts = candidate.get("partition_count_observed")
        if type(raw_parts) is int and 0 <= raw_parts <= 256:
            parts = raw_parts
        raw_bus = candidate.get("bus")
        if (isinstance(raw_bus, str) and 0 < len(raw_bus) <= 48
                and all(ch.isalnum() or ch in "_.-" for ch in raw_bus)):
            bus = raw_bus
        if candidate.get("target_classification") in (
                "PROTECTED_IN_USE", "UNVERIFIED_NOT_EMPTY_PROVEN"):
            classification = candidate["target_classification"]

    selected = label != "NOT_SELECTED" and classification != "UNKNOWN"
    unresolved = []
    if not valid_report:
        unresolved.append("The local hardware discovery did not produce a trusted bounded disk inventory.")
    if not selected:
        unresolved.append("Choose a specific observed disk for a non-destructive preview; nothing is preselected.")
    if classification == "PROTECTED_IN_USE":
        unresolved.append("OS reports target as BOOT/SYSTEM or MOUNTED. It must NOT be considered an available installer target.")
    if classification == "UNVERIFIED_NOT_EMPTY_PROVEN":
        unresolved.append("Observed storage may contain valuable data. It is NOT verified blank or safe to erase.")
    if intent == UNDECIDED:
        unresolved.append("Choose the intended formatting method.")
    if intent == COEXIST:
        unresolved.append("No exact partition edits, shared EFI effects, or Windows boot impact have been established.")
    if intent == FORMAT_TARGET:
        unresolved.append("ENTIRE DISK REPLACEMENT is proposed; existing partitions and their contents would be erased.")
    if not backup_warning_acknowledged:
        unresolved.append("Review and acknowledge the personal-backup and irreversible data-loss warning.")
    unresolved.extend((
        "Independently confirm the permanent physical target identity immediately before installation.",
        "Review the full write/format/EFI/boot plan and all OTHER drives that could be changed.",
        "Verify the official installation medium and actual hardware boot compatibility.",
        "Obtain a separate, specific confirmation in the real future installer; no writes are possible here.",
    ))
    return TargetPreview(
        schema=SCHEMA,
        status="HOLD_PREVIEW_ONLY_NO_INSTALLER_OR_DISK_WRITES",
        intent=intent,
        proposed_scope=SCOPES[intent],
        target_observed_label=label if selected else "NOT_SELECTED",
        target_size_gib_approx=size if selected else None,
        target_bus=bus if selected else "UNKNOWN",
        target_partitions_observed=parts if selected else None,
        target_classification=classification if selected else "UNKNOWN",
        target_selection_source="VOLATILE_READ_ONLY_DISCOVERY_SNAPSHOT",
        user_backup_warning_acknowledged=backup_warning_acknowledged,
        user_backups_proven_by_nightglass=False,
        chosen_disk_identity_verified=False,
        boot_and_efi_impact_verified=False,
        complete_writes_list_known=False,
        install_media_verified=False,
        independent_install_authorization=False,
        disk_write_authorized=False,
        os_install_authorized=False,
        warning=disclosure.warning + "\n\n" + WARNING,
        unresolved=tuple(unresolved),
    )


def describe_target_preview(preview: TargetPreview) -> str:
    """Human-readable, no private file names or device serial numbers."""
    text = [
        "NIGHTGLASS INSTALL TARGET PREVIEW — READ ONLY",
        f"Status: {preview.status}",
        f"Intended operation: {preview.proposed_scope}",
        f"Observed target: {preview.target_observed_label}",
        f"Observed size: {preview.target_size_gib_approx} GiB (approximate)",
        f"Bus: {preview.target_bus}",
        f"Partitions currently reported: {preview.target_partitions_observed}",
        f"Host classification: {preview.target_classification}",
        "Target identity: NOT INDEPENDENTLY VERIFIED",
        "User backup notice: " + (
            "ACKNOWLEDGED (NOT backup proof)" if preview.user_backup_warning_acknowledged
            else "NOT ACKNOWLEDGED"),
        "",
        preview.warning,
        "",
        "REMAINING CHECKS:",
    ]
    text.extend("- " + issue for issue in preview.unresolved)
    text.append("No physical disk operation, OS install, backup or VM action is authorized.")
    return "\n".join(text)
