"""Read-only runtime metadata observation of a manually started, benign Kali VM.

A preboot cold backup is verified as the identity anchor; the SELECTED live
qcow2 file is never hashed, opened with qemu-img, frozen or modified while
QEMU might be writing to it. Inspects host SELinux and libvirt sVirt
metadata only, not real QEMU process SELinux contexts or network packets.

This cannot attest that Kali finished booting or that rollback succeeded.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from .acceptance import save_acceptance
from .backups import verify_backup
from .hypervisor import Hypervisor
from .kali_recovery_link import _strict_directory
from .kali_registration import _other_disk_alias, _safe_disk
from .kali_recovery_registration import _autostart_off
from .kali_setup import load_setup_plan
from .models import safe_name
from .runner import Runner, ToolError
from .runtime_labels import RuntimeLabelInspector


@dataclass(frozen=True)
class KaliRunningObservation:
    original_guest: str
    observed_guest: str
    template_id: str
    state: str
    definitions: tuple[str, ...]
    issues: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.issues and self.state == "running" and len(self.definitions) == 2

    def describe(self) -> str:
        return "\n".join((
            "KALI RUNNING-GUEST OBSERVATION: " + (
                "PASS (LIBVIRT/SELINUX METADATA ONLY)" if self.ok
                else "BLOCKED / UNVERIFIED"
            ),
            f"Original Kali guest: {self.original_guest} | template: {self.template_id}",
            f"Manually running recovered guest: {self.observed_guest}",
            f"Libvirt state: {self.state}",
            f"Current/next-boot definitions inspected: {', '.join(self.definitions) or 'NONE'}",
            *(f"BLOCK {item}" for item in self.issues),
            *(f"REVIEW {item}" for item in self.warnings),
            "NO VM was started, changed, shut down, imported, rebooted or restored.",
            "Selected live guest disk was NOT hashed or probed by qemu-img.",
            "Libvirt running state does NOT prove Kali OS completed boot.",
            "No actual QEMU process SELinux context, packet-level network denial,",
            "authenticated package provenance or successful recovery was verified.",
        ))

    def evidence(self) -> dict:
        return {
            "format": "midnight-provisioner-kali-running-observation",
            "version": 1,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "original_guest": self.original_guest,
            "observed_guest": self.observed_guest,
            "template_id": self.template_id,
            "libvirt_state": self.state,
            "definitions_inspected": list(self.definitions),
            "read_only_metadata_passed": self.ok,
            "issues": list(self.issues),
            "warnings": list(self.warnings),
            "guest_operating_system_boot_verified": False,
            "successful_recovery_verified": False,
            "actual_qemu_process_selinux_verified": False,
            "packet_level_network_isolation_verified": False,
            "live_disk_hash_verified": False,
            "package_publisher_provenance_verified": False,
        }


class KaliRunningInspector:
    def __init__(
        self,
        hypervisor: Hypervisor | None = None,
        runner: Runner | None = None,
        runtime: RuntimeLabelInspector | None = None,
    ):
        self.hypervisor = hypervisor or Hypervisor()
        self.runner = runner or Runner()
        self.runtime = runtime or RuntimeLabelInspector(
            hypervisor=self.hypervisor, runner=self.runner
        )

    def inspect(
        self, plan_path: Path, backup_dir: Path, observed_guest: str,
        expected_disk: Path,
    ) -> KaliRunningObservation:
        plan = load_setup_plan(Path(plan_path))
        observed_guest = safe_name(observed_guest)
        if observed_guest == plan["guest"]:
            raise ToolError("Recovered Kali guest must have its own NEW name")
        disk = _safe_disk(Path(expected_disk))
        # Only stat this selected disk, never hash an active guest disk.
        original_disk_id = (disk.stat().st_dev, disk.stat().st_ino)
        backup = _strict_directory(backup_dir, "Original Kali cold backup")
        if backup in disk.parents:
            raise ToolError("Live recovered Kali disk cannot be inside the cold backup")
        verify_backup(backup)
        archive = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        problems: list[str] = []
        warnings = [
            "This pass observes libvirt XML and reported SELinux metadata, not QEMU's actual process context",
            "Actual Kali desktop boot, signed package supply chain and successful recovery remain untested",
            "No packet-level network denial or guest-to-host reachability was measured",
            "A privileged libvirt client may change VM definitions immediately after the check",
            "Only exact/normalized disk references and same-folder symlinks are checked for other registered VMs",
            "The live recovered qcow2 was intentionally not hashed because QEMU may be writing to it",
        ]
        if archive.get("domain") != plan["guest"] or archive.get("policy") != "lab":
            problems.append("Original cold backup does not match Kali template guest and restricted lab policy")
        try:
            source_root = ET.fromstring((backup / "domain.xml").read_text(encoding="utf-8"))
            source_uuid = (source_root.findtext("uuid") or "").strip()
            if source_root.tag != "domain" or source_root.findtext("name") != plan["guest"]:
                problems.append("Original cold backup domain identity differs from selected template")
            if not source_uuid:
                problems.append("Original cold backup UUID is missing")
        except (ET.ParseError, OSError):
            source_uuid = ""
            problems.append("Original cold backup XML identity cannot be verified")

        # This inspector is intentionally for a guest an operator already
        # started. RuntimeLabelInspector validates host SELinux enforcement,
        # libvirt security capabilities, domain sVirt labels and restricted
        # policy against registered live/inactive/managed-save XML.
        try:
            observation = self.runtime.inspect(observed_guest, "isolated")
            state = observation.state
            problems.extend(observation.errors)
        except (ToolError, OSError, ValueError):
            state = "unknown"
            problems.append("Live guest SELinux/libvirt runtime metadata cannot be inspected")
        if state != "running":
            problems.append("Recovered Kali guest must already be running; no VM is started by this check")

        identities: set[str] = set()
        labels: list[str] = []
        hv = self.hypervisor
        for label, argv in (
            ("Current definition", ("dumpxml", observed_guest)),
            ("Next-boot definition", ("dumpxml", "--inactive", observed_guest)),
        ):
            try:
                root = ET.fromstring(hv._virsh(*argv))
            except (ToolError, ET.ParseError):
                problems.append(f"{label}: missing/unparseable libvirt domain XML")
                continue
            labels.append(label)
            if root.tag != "domain" or root.findtext("name") != observed_guest:
                problems.append(f"{label}: wrong recovered guest name")
            uid = (root.findtext("uuid") or "").strip()
            if not uid:
                problems.append(f"{label}: recovery guest UUID missing")
            else:
                identities.add(uid)
            if root.find("./devices/interface") is not None:
                problems.append(f"{label}: recovered guest has a network adapter")
            if root.find("./devices/hostdev") is not None:
                problems.append(f"{label}: recovered guest declares host device passthrough")
            actual_disks = []
            for item in root.findall("./devices/disk"):
                source = item.find("source")
                if item.get("device", "disk") == "cdrom":
                    if source is not None and source.attrib:
                        problems.append(f"{label}: installer ISO/CD-ROM remains mounted")
                    continue
                if item.get("type") != "file" or item.get("device", "disk") != "disk":
                    problems.append(f"{label}: unexpected disk backend/device")
                    continue
                driver = item.find("driver")
                if driver is None or driver.get("name") != "qemu" or driver.get("type") != "qcow2":
                    problems.append(f"{label}: QEMU disk driver is not explicitly qcow2")
                if item.find("backingStore") is not None:
                    problems.append(f"{label}: unexpected disk backing XML")
                actual_disks.append(source.get("file") if source is not None else None)
            if actual_disks != [str(disk)]:
                problems.append(f"{label}: expected exactly the selected recovery qcow2 disk path")
        if len(identities) != 1:
            problems.append("Recovered live/inactive VM UUIDs disagree or are missing")
        if source_uuid and source_uuid in identities:
            problems.append("Running recovery guest retained original Kali VM UUID")
        try:
            saved = hv._managed_save_xml(observed_guest)
            if saved is not None:
                problems.append("Recovered guest has a managed-save state")
        except ToolError:
            problems.append("Cannot verify absence of recovered guest managed-save state")
        try:
            if not _autostart_off(hv._virsh("dominfo", observed_guest)):
                problems.append("Recovered Kali VM autostart is enabled or not explicitly disabled")
        except ToolError:
            problems.append("Cannot inspect recovered guest autostart")

        try:
            domains = hv.list_domains()
        except ToolError:
            domains = []
            problems.append("Cannot enumerate other libvirt guests for disk-source collisions")
        if observed_guest not in domains:
            problems.append("Running recovered Kali VM is no longer registered")
        for other in domains:
            if other == observed_guest:
                continue
            for label, args in (
                ("current", ("dumpxml", other)),
                ("inactive", ("dumpxml", "--inactive", other)),
            ):
                try:
                    other_xml = ET.fromstring(hv._virsh(*args))
                    if other_xml.tag != "domain":
                        raise ET.ParseError("unexpected domain XML")
                    for source in other_xml.findall("./devices/disk/source"):
                        conflict = _other_disk_alias(source.get("file"), disk)
                        if conflict:
                            problems.append(f"Another registered guest {label} disk collision: {conflict}")
                except (ToolError, ET.ParseError):
                    problems.append(f"Cannot inspect another registered guest's {label} disk sources")
            try:
                saved = hv._managed_save_xml(other)
                if saved is not None:
                    root = ET.fromstring(saved)
                    if root.tag != "domain":
                        raise ET.ParseError("unexpected saved XML root")
                    for source in root.findall("./devices/disk/source"):
                        conflict = _other_disk_alias(source.get("file"), disk)
                        if conflict:
                            problems.append("Another guest managed-save disk collision: " + conflict)
            except (ToolError, ET.ParseError):
                problems.append("Cannot inspect another guest's saved disk sources")

        # Final rechecks narrow races without trying to freeze a live guest.
        try:
            current = _safe_disk(disk)
            new_id = (current.stat().st_dev, current.stat().st_ino)
            if new_id != original_disk_id:
                problems.append("Live recovered disk inode changed during metadata inspection")
        except (OSError, ToolError):
            problems.append("Live recovered qcow2 became unsafe/unavailable during inspection")
        try:
            if hv.state(observed_guest).strip().lower() != "running":
                problems.append("Recovered guest stopped or changed state during observation")
            if not _autostart_off(hv._virsh("dominfo", observed_guest)):
                problems.append("Recovered guest autostart changed while inspecting")
        except ToolError:
            problems.append("Cannot reverify running guest state and autostart")
        # Hash only the INACTIVE backup, never the live disk.
        verify_backup(backup)
        return KaliRunningObservation(
            original_guest=plan["guest"], observed_guest=observed_guest,
            template_id=plan["template_id"], state=state,
            definitions=tuple(labels), issues=tuple(dict.fromkeys(problems)),
            warnings=tuple(warnings),
        )


def save_kali_running_observation(
    report: KaliRunningObservation, destination: Path,
) -> Path:
    """Create a NEW local, private 0600 evidence file (never overwrite)."""
    return save_acceptance(report, destination)
