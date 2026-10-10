"""Nightglass intended target formatting disclosure (not an OS installer).

The future OS-install workflow expects that users back up any files they
want to retain BEFORE approving destruction of a selected drive. Nightglass
does not make backups, inspect personal files for completeness, or guarantee
recovery. This module cannot authorize formatting, partition writes, or
changes to Windows, Fedora, boot configuration or external USB drives.
"""
from __future__ import annotations

from dataclasses import dataclass

UNDECIDED = "undecided"
FORMAT_TARGET = "format_target"
COEXIST = "coexist"
INTENTS = (UNDECIDED, FORMAT_TARGET, COEXIST)

FORMAT_WARNING = (
    "DATA LOSS WARNING: Installation will format the target drive or selected "
    "partitions. Everything on the formatted area will be deleted, including "
    "existing operating systems, documents, applications and hidden files. "
    "This may be irreversible. You are responsible for independently backing "
    "up everything you want to keep BEFORE installation. Nightglass does "
    "not make or verify those backups and assumes you have handled them yourself. "
    "If you have not backed up important data or are unsure which drive will be "
    "formatted, STOP and cancel setup."
)
COEXIST_WARNING = (
    "PARTITION CHANGE WARNING: Installing alongside an existing OS can alter "
    "partitions, boot/EFI data or the OS startup configuration. Data loss or "
    "loss of boot access is possible. You are responsible for independently "
    "backing up anything you want to keep BEFORE installation. Nightglass "
    "does not create or verify those backups. If you are unsure, STOP."
)
UNDECIDED_WARNING = (
    "Select an intended installation method. No target drive has been chosen. "
    "Any eventual formatting or repartitioning can destroy data. Before any "
    "installer proceeds, you must review the specific device and confirm "
    "that you are personally responsible for your backups."
)
ACKNOWLEDGMENT = (
    "I understand that formatting can permanently delete existing data and "
    "that I must have backed up anything I want to keep myself."
)


@dataclass(frozen=True)
class FormatDisclosure:
    intent: str
    warning: str
    requires_user_warning: bool = True
    installer_creates_backup: bool = False
    installer_verifies_backup: bool = False
    backups_presumed_user_responsibility: bool = True
    acknowledgment_is_not_backup_evidence: bool = True
    target_selected: bool = False
    target_safe_to_format: bool = False
    target_format_authorized: bool = False
    existing_os_safe: bool = False
    disk_write_authorized: bool = False
    installation_authorized: bool = False

    def __post_init__(self):
        if self.intent not in INTENTS:
            raise ValueError("Unknown installation intent")


def disclosure_for(intent: str = UNDECIDED) -> FormatDisclosure:
    """A warning, not a waiver, backup certification or authorization."""
    if intent == FORMAT_TARGET:
        return FormatDisclosure(intent=intent, warning=FORMAT_WARNING)
    if intent == COEXIST:
        return FormatDisclosure(intent=intent, warning=COEXIST_WARNING)
    if intent == UNDECIDED:
        return FormatDisclosure(intent=intent, warning=UNDECIDED_WARNING)
    raise ValueError("Unknown installation intent")
