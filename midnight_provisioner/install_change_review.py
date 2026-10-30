"""Phase26 proposed installation-impact review: advisory, never executable.

The discovery report contains approximate drive-level properties and a
partition COUNT, not a partition table, UUIDs, mount relations, ESP ownership
or a concrete installer write plan. Do not fabricate before/after partitions
or disk paths. This review deliberately marks these as unresolved even when
the user selects a target and acknowledges the backup warning.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .install_disclosure import FORMAT_TARGET, COEXIST, UNDECIDED
from .install_target_preview import TargetPreview, build_target_preview

SCHEMA = "midnight-provisioner.install-change-review.v1"
STATES = ("INTENDED_EFFECT_NOT_VERIFIED", "UNKNOWN_REQUIRES_INSTALLER")
STATUS = "HOLD_CHANGE_DETAILS_UNKNOWN_NO_WRITES"


@dataclass(frozen=True)
class ChangeImpact:
    component: str
    state: str
    description: str

    def __post_init__(self):
        if self.state not in STATES:
            raise ValueError("Unknown impact state")


@dataclass(frozen=True)
class ChangeReview:
    schema: str
    status: str
    intent: str
    observed_target: str
    target_classification: str
    observed_partition_count: int | None
    intended_whole_disk_replacement: bool
    exact_existing_partition_table_known: bool
    exact_new_partition_layout_known: bool
    efi_system_partition_identity_known: bool
    windows_boot_impact_known: bool
    other_disks_impact_known: bool
    install_media_and_publisher_verified: bool
    target_identity_independently_verified: bool
    user_backup_warning_acknowledged: bool
    backups_certified_by_midnight_provisioner: bool
    destructive_consent_obtained: bool
    write_manifest_complete: bool
    disk_write_authorized: bool
    os_install_authorized: bool
    impacts: tuple[ChangeImpact, ...]
    blockers: tuple[str, ...]


def build_change_review(preview: TargetPreview) -> ChangeReview:
    """Derive a no-write impact matrix from the immutable Phase25 preview.

    This accepts a preview only as an observation. It cannot elevate its
    authority, even if an upstream caller forges a proposed preview object.
    """
    if not isinstance(preview, TargetPreview):
        raise TypeError("A Phase25 TargetPreview observation is required")
    if preview.intent not in (UNDECIDED, FORMAT_TARGET, COEXIST):
        raise ValueError("Unrecognized intent")
    if preview.status != "HOLD_PREVIEW_ONLY_NO_INSTALLER_OR_DISK_WRITES":
        raise ValueError("Not a held Phase25 preview")
    if any((
        preview.chosen_disk_identity_verified,
        preview.boot_and_efi_impact_verified,
        preview.complete_writes_list_known,
        preview.install_media_verified,
        preview.independent_install_authorization,
        preview.disk_write_authorized,
        preview.os_install_authorized,
        preview.user_backups_proven_by_midnight_provisioner,
    )):
        raise ValueError("A preview claiming verified or authorized state is untrusted")

    selected = preview.target_observed_label != "NOT_SELECTED"
    parts = preview.target_partitions_observed
    if type(parts) is not int or not (0 <= parts <= 256):
        parts = None
    whole = preview.intent == FORMAT_TARGET
    impacts = []
    if preview.intent == UNDECIDED:
        impacts.extend((
            ChangeImpact("TARGET_DATA", "UNKNOWN_REQUIRES_INSTALLER",
                         "No installation type or physical target has been chosen."),
            ChangeImpact("PARTITION_LAYOUT", "UNKNOWN_REQUIRES_INSTALLER",
                         "Existing and proposed partitions have not been reviewed."),
        ))
    elif whole:
        impacts.extend((
            ChangeImpact("EXISTING_TARGET_CONTENTS", "INTENDED_EFFECT_NOT_VERIFIED",
                         "A future whole-disk installation intends to replace all partitions and data on the selected target. It has NOT selected or changed a disk."),
            ChangeImpact("NEW_PARTITIONS", "UNKNOWN_REQUIRES_INSTALLER",
                         "Number, sizes, filesystems, encryption and mounting of future partitions are not provided by the current installer."),
        ))
    else:
        impacts.extend((
            ChangeImpact("EXISTING_TARGET_CONTENTS", "UNKNOWN_REQUIRES_INSTALLER",
                         "Coexistence partition preservation/resizing/deletion is unspecified; do not assume existing data remains untouched."),
            ChangeImpact("NEW_PARTITIONS", "UNKNOWN_REQUIRES_INSTALLER",
                         "Proposed new partitions, filesystem types, sizes and free-space policy are unverified."),
        ))
    impacts.extend((
        ChangeImpact("EFI_SYSTEM_PARTITION", "UNKNOWN_REQUIRES_INSTALLER",
                     "Whether the EFI System Partition would be reused, created or changed and on which physical drive is unknown."),
        ChangeImpact("WINDOWS_BOOT_AND_RECOVERY", "UNKNOWN_REQUIRES_INSTALLER",
                     "Windows boot entries, recovery partitions and encryption state are not independently reviewed."),
        ChangeImpact("OTHER_PHYSICAL_DRIVES", "UNKNOWN_REQUIRES_INSTALLER",
                     "The eventual installer must independently list every physical drive it would modify, including firmware boot entries."),
        ChangeImpact("INSTALLER_MEDIA_AND_BOOT", "UNKNOWN_REQUIRES_INSTALLER",
                     "Official media authenticity, live boot compatibility, UEFI mode and rollback are unverified."),
        ChangeImpact("LINUX_DISK_ENCRYPTION",
                     "INTENDED_EFFECT_NOT_VERIFIED" if preview.disk_encryption in ("luks2", "luks2-tpm2-pin")
                     else "UNKNOWN_REQUIRES_INSTALLER",
                     {"luks2": "Planned: Fedora installer 'Encrypt my data' (LUKS2), passphrase at startup; /boot and EFI stay unencrypted.",
                      "luks2-tpm2-pin": "Planned: LUKS2 via 'Encrypt my data', then TPM2 + PIN enrollment after install; passphrase kept as fallback.",
                      "none": "Planned: NO encryption; Linux files readable by anyone with the disk.",
                      }.get(preview.disk_encryption, "Not decided; choose before installing.")
                     + " Verify after install with 'midnight-provisioner encryption-check'."),
    ))
    blockers = [
        "No installation or physical disk write capability exists in Midnight Provisioner at this stage.",
        "Observed disk names and approximate sizes are not permanent hardware identity.",
        "A partition count is not a partition table or a list of files to retain.",
        "Complete exact BEFORE/AFTER partition operations have not been generated by a real OS installer.",
        "EFI, Windows boot/recovery and all other drives must be independently reviewed.",
        "Official installation media, target filesystem options and physical boot behavior are unverified.",
        "The user must back up anything they want to keep; Midnight Provisioner does not make or verify those backups.",
        "This review is not consent. A future installer needs an independent device-specific destructive confirmation.",
    ]
    if not selected:
        blockers.insert(1, "NO TARGET SELECTED: choose only a temporary disk observation to review its intended consequences.")
    if preview.target_classification == "PROTECTED_IN_USE":
        blockers.insert(1, "PROTECTED HOST DISK: the current OS reports it as boot/system or mounted.")
    if preview.intent == UNDECIDED:
        blockers.insert(1, "The intended installation mode is undecided.")
    if not preview.user_backup_warning_acknowledged:
        blockers.append("Personal backup and data-loss warning has not been acknowledged.")
    return ChangeReview(
        schema=SCHEMA,
        status=STATUS,
        intent=preview.intent,
        observed_target=preview.target_observed_label if selected else "NOT_SELECTED",
        target_classification=preview.target_classification,
        observed_partition_count=parts if selected else None,
        intended_whole_disk_replacement=whole,
        exact_existing_partition_table_known=False,
        exact_new_partition_layout_known=False,
        efi_system_partition_identity_known=False,
        windows_boot_impact_known=False,
        other_disks_impact_known=False,
        install_media_and_publisher_verified=False,
        target_identity_independently_verified=False,
        user_backup_warning_acknowledged=preview.user_backup_warning_acknowledged,
        backups_certified_by_midnight_provisioner=False,
        destructive_consent_obtained=False,
        write_manifest_complete=False,
        disk_write_authorized=False,
        os_install_authorized=False,
        impacts=tuple(impacts),
        blockers=tuple(blockers),
    )


def review_from_discovery(
    discovery: dict[str, Any] | None, *,
    target_index: int | None = None,
    intent: str = UNDECIDED,
    backup_warning_acknowledged: bool = False,
    encryption: str = "undecided",
) -> ChangeReview:
    """No host actions; delegates input validation to the Phase25 preview."""
    return build_change_review(build_target_preview(
        discovery, target_index=target_index, intent=intent,
        backup_warning_acknowledged=backup_warning_acknowledged, encryption=encryption))


def describe_change_review(review: ChangeReview) -> str:
    parts = [
        "MIDNIGHT_PROVISIONER PROPOSED INSTALLATION IMPACT — READ ONLY",
        f"Status: {review.status}",
        f"Observed target: {review.observed_target} ({review.target_classification})",
        f"Partitions observed: {review.observed_partition_count}",
        f"Intent: {review.intent}",
        "EXACT PARTITION CHANGES: UNKNOWN — no authoritative installer proposal.",
        "EXACT EFI/BOOT CHANGES: UNKNOWN — no verified physical boot path.",
        "BACKUPS: USER RESPONSIBILITY; NOT CREATED OR VERIFIED HERE.",
        "",
        "IMPACT REVIEW:",
    ]
    for effect in review.impacts:
        parts.append(f"- {effect.component} [{effect.state}]: {effect.description}")
    parts.append("")
    parts.append("BLOCKERS:")
    parts.extend("- " + item for item in review.blockers)
    parts.append("")
    parts.append("NO PHYSICAL DISK WRITES, INSTALLATION, EFI MODIFICATION OR BACKUP ACTION AUTHORIZED.")
    return "\n".join(parts)
