"""Read-only registered libvirt guest acceptance audit.

Audits actual registered/live and inactive definitions plus managed-save XML.
No guest is started, imported, connected, repaired, or reconfigured. A passing
XML audit does not prove effective firewall isolation or successful guest boot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from xml.etree import ElementTree as ET

from .hypervisor import (
    Hypervisor, ISOLATED_NETWORK, assess_domain, declared_guest_memory_gib,
)
from .models import safe_name
from .portability import current_budget
from .runner import ToolError
from .privatefiles import make_private

ACCEPTANCE_VERSION = 1
STATES = {"shut off", "running", "paused", "idle", "pmsuspended"}


@dataclass(frozen=True)
class GuestAcceptance:
    guest: str
    policy: str
    state: str
    documents: tuple[str, ...]
    max_memory_gib: float
    interfaces: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def describe(self) -> str:
        headline = "PASS (XML ONLY)" if self.ok else "BLOCKED"
        return "\n".join((
            f"REGISTERED VM ACCEPTANCE: {headline}",
            f"Guest: {self.guest} | policy: {self.policy} | state: {self.state}",
            f"Definitions inspected: {', '.join(self.documents)}",
            f"Maximum declared RAM: {self.max_memory_gib:g} GiB",
            f"Network interfaces declared (maximum per definition): {self.interfaces}",
            *(f"BLOCK {err}" for err in self.errors),
            *(f"REVIEW {warn}" for warn in self.warnings),
            "No guest was started, imported, shut down, or reconfigured.",
            "This is NOT a packet-level network test, boot verification or security certification.",
        ))

    def evidence(self) -> dict:
        """Explicitly mark unobserved runtime properties as unverified."""
        return {
            "format": "midnight-provisioner-guest-acceptance",
            "version": ACCEPTANCE_VERSION,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "guest": self.guest,
            "policy": self.policy,
            "state": self.state,
            "definitions_inspected": list(self.documents),
            "max_declared_memory_gib": self.max_memory_gib,
            "declared_network_interface_count": self.interfaces,
            "xml_policy_passed": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "observations_not_performed": [
                "guest-boot",
                "packet-level-network-denial",
                "SELinux-runtime-enforcement",
                "hypervisor-escape-resistance",
                "recovery-rollback",
            ],
            "notes": "Read-only local audit of declared libvirt state; not a security certification.",
        }


class RegisteredGuestAuditor:
    def __init__(self, hypervisor: Hypervisor | None = None):
        self.hypervisor = hypervisor or Hypervisor()

    def inspect(self, guest: str, policy: str = "isolated") -> GuestAcceptance:
        guest = safe_name(guest)
        if policy not in {"isolated", "lab"}:
            raise ToolError("Choose isolated or lab for a registered-guest acceptance audit")
        if guest not in self.hypervisor.list_domains():
            raise ToolError(f"Guest {guest} is not registered in qemu:///system")
        state = self.hypervisor.state(guest).strip().lower()
        if state not in STATES:
            raise ToolError(f"Unrecognized or transitional libvirt guest state: {state}")

        # Default XML shows the live definition of a running VM; --inactive is
        # the persistent definition it would boot with next time.
        # A managed-save image may contain yet another older device inventory.
        xmls = [
            ("Current definition", self.hypervisor._virsh("dumpxml", guest)),
            ("Inactive definition", self.hypervisor._virsh("dumpxml", "--inactive", guest)),
        ]
        saved = self.hypervisor._managed_save_xml(guest)
        if saved is not None:
            xmls.append(("Managed-save definition", saved))

        errors = []
        warnings = []
        max_memory = 0.0
        count_network = 0
        lab_xml = None
        if policy == "lab":
            # Network definition must be inspected if any registered XML has a NIC.
            try:
                need_lab = any(
                    ET.fromstring(xml).find("./devices/interface") is not None
                    for _, xml in xmls
                )
            except ET.ParseError:
                need_lab = True
            if need_lab:
                try:
                    lab_xml = self.hypervisor._virsh("net-dumpxml", ISOLATED_NETWORK)
                except ToolError as exc:
                    errors.append(f"Cannot inspect authorized lab network: {exc}")

        for label, xml in xmls:
            audit = assess_domain(xml, policy, lab_xml)
            errors.extend(f"{label}: {problem}" for problem in audit.warnings if not audit.ok)
            try:
                root = ET.fromstring(xml)
                if root.findtext("name") != guest:
                    errors.append(f"{label}: VM name is different from registered name")
                count_network = max(count_network, len(root.findall("./devices/interface")))
                max_memory = max(max_memory, declared_guest_memory_gib(xml))
            except (ET.ParseError, ValueError, TypeError) as exc:
                errors.append(f"{label}: cannot inspect guest RAM and identity: {exc}")

        budget = current_budget()
        if max_memory > budget.guest_ram_cap_gib:
            errors.append(
                f"Guest RAM {max_memory:g} GiB exceeds local Midnight Provisioner cap "
                f"{budget.guest_ram_cap_gib:g} GiB"
            )
        if state != "shut off":
            warnings.append(
                "Guest is not powered off; this audit does not observe real network traffic "
                "or stop an active guest"
            )
        if saved is not None:
            warnings.append("Managed-save state exists; actual resume needs a separate start-time policy check")
        if policy == "lab" and count_network:
            warnings.append(
                "No-forward libvirt networking does not prove that the guest cannot reach "
                "services on its host bridge or other host routes"
            )
        warnings.extend((
            "Effective SELinux, firewalld, QEMU runtime and guest boot behavior were not tested",
            "Another privileged process can change a libvirt definition after this audit",
        ))

        return GuestAcceptance(
            guest, policy, state, tuple(label for label, _ in xmls), max_memory,
            count_network, tuple(dict.fromkeys(errors)), tuple(warnings),
        )


def save_acceptance(report: GuestAcceptance, destination: Path) -> Path:
    """Save one non-sensitive local evidence record, refusing overwrite."""
    destination = Path(destination).expanduser()
    if destination.exists() or destination.is_symlink():
        raise ToolError("The acceptance report already exists; never overwrite local files")
    try:
        parent = destination.parent.resolve(strict=True)
    except OSError as exc:
        raise ToolError(f"Report destination parent is missing: {exc}") from exc
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        raise ToolError("Report destination parent must be writable")
    target = parent / destination.name
    if target.exists() or target.is_symlink():
        raise ToolError("Report destination is already in use")
    try:
        with target.open("x", encoding="utf-8") as stream:
            make_private(stream.fileno())
            json.dump(report.evidence(), stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise ToolError(f"Could not save acceptance report: {exc}") from exc
    return target
