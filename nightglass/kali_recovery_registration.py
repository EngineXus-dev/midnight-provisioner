"""Read-only gate linking a Kali backup and its MANUALLY registered recovery VM.

Validates verified original-to-staged files first, then the existing
recovery-handoff audit. Separately rejects unexpected autostart, reused
recovery disk paths in other system-libvirt guests and original UUID reuse.
It NEVER imports, defines, boots, edits, installs tools, or changes networking.

A pass is metadata consistency only, NOT actual boot/rollback certification.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET

from .acceptance import save_acceptance
from .handoff import RecoveryHandoff
from .hypervisor import Hypervisor
from .kali_recovery_link import KaliRecoveryLink, _strict_directory
from .kali_registration import _other_disk_alias
from .kali_setup import load_setup_plan
from .recovery import verify_staging
from .runner import Runner, ToolError


def _autostart_off(text: str) -> bool:
    """Fail closed on unknown/missing/ambiguous libvirt dominfo autostart."""
    rows = re.findall(r"(?im)^\s*Autostart:\s*(\S+)\s*$", text)
    return len(rows) == 1 and rows[0].strip().lower() in {"disable", "disabled", "no"}


def _domain_identity(xml: str, guest: str, issues: list[str], label: str) -> str | None:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        issues.append(f"{label}: malformed registered VM XML")
        return None
    if root.tag != "domain" or root.findtext("name") != guest:
        issues.append(f"{label}: VM identity differs from registered recovery guest")
    if root.find("./devices/interface") is not None:
        issues.append(f"{label}: recovery guest has an unexpected network adapter")
    uid = (root.findtext("uuid") or "").strip()
    if not uid:
        issues.append(f"{label}: recovery guest UUID is missing")
    return uid or None


@dataclass(frozen=True)
class KaliRecoveryRegistration:
    original_guest: str
    recovered_guest: str
    template_id: str
    verified_assets: int
    registered_definitions: tuple[str, ...]
    issues: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.issues and self.verified_assets > 0 and len(self.registered_definitions) >= 2

    def describe(self) -> str:
        return "\n".join((
            "KALI REGISTERED RECOVERY: " + (
                "PASS (METADATA ONLY — NOT BOOT/RESTORE-PROVEN)"
                if self.ok else "BLOCKED / UNVERIFIED"
            ),
            f"Original: {self.original_guest} | Kali template: {self.template_id}",
            f"Separately registered recovery: {self.recovered_guest}",
            f"Backup-to-stage asset copies verified: {self.verified_assets}",
            f"Registered definitions inspected: {', '.join(self.registered_definitions) or 'NONE'}",
            *(f"BLOCK {problem}" for problem in self.issues),
            *(f"REVIEW {warning}" for warning in self.warnings),
            "The recovery guest must remain shut off with autostart disabled and no NIC.",
            "No VM definition, guest process, disk image or network setting was changed.",
            "A metadata pass does NOT prove signed image provenance, guest boot, restore,",
            "effective SELinux or firewall isolation, or that privileged clients cannot race this check.",
        ))

    def evidence(self) -> dict:
        return {
            "format": "nightglass-kali-registered-recovery", "version": 1,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "original_guest": self.original_guest, "template_id": self.template_id,
            "recovered_guest": self.recovered_guest,
            "verified_copy_assets": self.verified_assets,
            "registered_definitions": list(self.registered_definitions),
            "metadata_gate_passed": self.ok,
            "issues": list(self.issues), "warnings": list(self.warnings),
            "actual_guest_boot_verified": False,
            "successful_restore_verified": False,
            "packet_level_network_denial_verified": False,
            "host_selinux_runtime_verified": False,
            "package_publisher_provenance_verified": False,
        }


class KaliRecoveryRegistrationInspector:
    def __init__(
        self, hypervisor: Hypervisor | None = None, runner: Runner | None = None,
        linker: KaliRecoveryLink | None = None,
        handoff: RecoveryHandoff | None = None,
    ):
        self.hypervisor = hypervisor or Hypervisor()
        self.runner = runner or Runner()
        self.linker = linker or KaliRecoveryLink()
        self.handoff = handoff or RecoveryHandoff(self.hypervisor, self.runner)

    def inspect(self, plan_path: Path, backup_dir: Path, stage_dir: Path) -> KaliRecoveryRegistration:
        plan = load_setup_plan(Path(plan_path))
        backup = _strict_directory(backup_dir, "Kali cold backup")
        stage = _strict_directory(stage_dir, "Kali recovery staging")
        linked = self.linker.inspect(Path(plan_path), backup, stage)
        issues: list[str] = []
        warnings = [
            "This audit observes already-registered metadata, never guest boot or rollback",
            "Current/inactive XML and autostart may change immediately after the check",
            "Other guest path checks do not resolve outside-folder aliases, bind mounts or other hypervisors",
            "Guest-to-host traffic, actual restore, and effective SELinux need supervised Fedora/KVM tests",
        ]
        if not linked.ok:
            issues.append("Original Kali template backup and staged recovery do not match")
            return KaliRecoveryRegistration(
                plan["guest"], linked.recovered_guest, plan["template_id"], 0, (),
                tuple(issues), tuple(warnings),
            )
        if linked.original_guest != plan["guest"] or linked.template_id != plan["template_id"]:
            issues.append("Kali recovery link identity differs from curated setup plan")
        handoff = self.handoff.inspect(stage)
        if not handoff.ok:
            issues.append("Registered recovered guest fails the existing offline handoff audit")
        if handoff.guest != linked.recovered_guest:
            issues.append("Registered recovered guest differs from the verified staged recovery identity")
        guest = linked.recovered_guest
        inspected = handoff.definitions

        # A previously unregistered recovery guest receives a fresh UUID when
        # manually defined in libvirt. It must NOT inherit the original
        # original guest's UUID despite that original UUID being removed
        # from the generated staging XML.
        source_xml = (backup / "domain.xml").read_text(encoding="utf-8")
        try:
            original_root = ET.fromstring(source_xml)
            original_uuid = (original_root.findtext("uuid") or "").strip()
        except ET.ParseError:
            original_uuid = ""
        if not original_uuid:
            issues.append("Original Kali backup VM UUID is unverified")

        recovered_uids: set[str] = set()
        for label, flags in (
            ("Current recovery definition", ("dumpxml", guest)),
            ("Inactive recovery definition", ("dumpxml", "--inactive", guest)),
        ):
            try:
                xml = self.hypervisor._virsh(*flags)
                uuid = _domain_identity(xml, guest, issues, label)
                if uuid:
                    recovered_uids.add(uuid)
            except ToolError:
                issues.append(f"{label}: cannot read registered libvirt definition")
        if len(recovered_uids) != 1:
            issues.append("Registered recovered VM current/next-boot UUIDs disagree")
        if original_uuid and original_uuid in recovered_uids:
            issues.append("Recovered VM retained original Kali guest UUID")

        # System libvirt can autostart outside Nightglass. For a recovered,
        # initially offline security VM, refuse any unknown or enabled state.
        try:
            if not _autostart_off(self.hypervisor._virsh("dominfo", guest)):
                issues.append("Recovered Kali VM autostart is enabled or cannot be verified disabled")
        except ToolError:
            issues.append("Cannot query recovered Kali VM autostart metadata")

        # Inspect OTHER registered guest XML only, no arbitrary disk opens.
        # The backup-to-staged linker already checks one-link recovered disk
        # inode; lexical/same-folder aliases still need comparing against
        # every system libvirt guest that may try to use it.
        restored_disk = stage / "disks/disk-01.qcow2"
        try:
            names = self.hypervisor.list_domains()
        except ToolError:
            issues.append("Cannot enumerate registered guests for recovered disk sharing")
            names = []
        if guest not in names:
            issues.append("Manually recovered VM is not registered in qemu:///system")
        for other in names:
            if other == guest:
                continue
            for label, flags in (
                ("current", ("dumpxml", other)),
                ("inactive", ("dumpxml", "--inactive", other)),
            ):
                try:
                    root = ET.fromstring(self.hypervisor._virsh(*flags))
                    if root.tag != "domain":
                        raise ET.ParseError("Invalid other guest XML root")
                    for source in root.findall("./devices/disk/source"):
                        finding = _other_disk_alias(source.get("file"), restored_disk)
                        if finding:
                            issues.append(f"Other guest {label} disk collision: {finding}")
                except (ToolError, ET.ParseError):
                    issues.append(f"Cannot inspect other guest {label} disk metadata")
            try:
                saved = self.hypervisor._managed_save_xml(other)
                if saved is not None:
                    root = ET.fromstring(saved)
                    if root.tag != "domain":
                        raise ET.ParseError("Invalid saved guest XML")
                    for source in root.findall("./devices/disk/source"):
                        finding = _other_disk_alias(source.get("file"), restored_disk)
                        if finding:
                            issues.append("Other guest managed-save disk collision: " + finding)
            except (ToolError, ET.ParseError):
                issues.append("Cannot inspect another guest's managed-save disk metadata")

        # Recheck the already known staged files and state after slower XML
        # reads. This narrows but does NOT close all privileged TOCTOU races.
        verify_staging(stage)
        try:
            if self.hypervisor.state(guest).strip().lower() != "shut off":
                issues.append("Recovered guest no longer shut off after inspection")
            if not _autostart_off(self.hypervisor._virsh("dominfo", guest)):
                issues.append("Recovered guest autostart changed or became unknown during inspection")
        except ToolError:
            issues.append("Cannot reverify recovered VM state and autostart")
        return KaliRecoveryRegistration(
            plan["guest"], guest, plan["template_id"], linked.matched_assets,
            tuple(inspected), tuple(dict.fromkeys(issues)), tuple(warnings),
        )


def save_registered_recovery(report: KaliRecoveryRegistration, destination: Path) -> Path:
    """Private exclusive-create report only; no existing files overwritten."""
    return save_acceptance(report, destination)
