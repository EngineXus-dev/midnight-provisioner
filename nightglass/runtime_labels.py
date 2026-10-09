"""Read-only libvirt sVirt label observation for ALREADY-running benign guests.

Evidence comes from libvirt XML and host SELinux observation. This is a
metadata check, NOT a /proc label inspection, packet-level network test,
malware containment proof, or permission to start any untrusted guest.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from xml.etree import ElementTree as ET

from .acceptance import RegisteredGuestAuditor, save_acceptance
from .host_posture import HostPosture, inspect_host_posture
from .hypervisor import Hypervisor
from .models import safe_name
from .runner import Runner, ToolError

PROCESS_LABEL = re.compile(
    r"^system_u:system_r:svirt_t:s0:(c[0-9]+,c[0-9]+)$"
)
IMAGE_LABEL = re.compile(
    r"^system_u:object_r:svirt_image_t:s0:(c[0-9]+,c[0-9]+)$"
)
LIVE_STATES = {"running", "paused", "idle"}


@dataclass(frozen=True)
class RuntimeLabelObservation:
    guest: str
    policy: str
    state: str
    checks: tuple[str, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def describe(self) -> str:
        return "\n".join((
            "RUNTIME SVIRT OBSERVATION: " + ("PASS (METADATA ONLY)" if self.ok else "UNVERIFIED / BLOCKED"),
            f"Guest: {self.guest} | policy: {self.policy} | libvirt state: {self.state}",
            *(f"PASS {item}" for item in self.checks),
            *(f"BLOCK {item}" for item in self.errors),
            *(f"REVIEW {item}" for item in self.warnings),
            "Read-only libvirt/host metadata. No VM was defined, started, shut down or changed.",
            "Does NOT verify effective QEMU process labels, on-disk SELinux contexts,",
            "network packet denial, successful guest boot or resistance to VM escape.",
        ))

    def evidence(self) -> dict:
        return {
            "format": "nightglass-runtime-svirt-observation",
            "version": 1,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "guest": self.guest,
            "policy": self.policy,
            "libvirt_state": self.state,
            "metadata_checks_passed": self.ok,
            "checks": list(self.checks),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            # SELinux category IDs and full local image paths are intentionally
            # not exported. The consistency check happens in memory only.
            "observations_not_performed": [
                "effective-qemu-process-selinux-context",
                "actual-disk-inode-selinux-context",
                "packet-level-guest-network-denial",
                "guest-boot",
                "host-security-certification",
                "vm-escape-resistance",
            ],
        }


class RuntimeLabelInspector:
    """Inspect an already-running registered restricted VM without guest I/O."""

    def __init__(
        self, hypervisor: Hypervisor | None = None,
        runner: Runner | None = None,
        host_probe=None,
    ):
        self.hypervisor = hypervisor or Hypervisor()
        self.runner = runner or Runner()
        self.host_probe = host_probe or inspect_host_posture

    def inspect(self, guest: str, policy: str = "isolated") -> RuntimeLabelObservation:
        guest = safe_name(guest)
        if policy not in {"isolated", "lab"}:
            raise ToolError("Runtime label checks require isolated or lab policy")
        acceptance = RegisteredGuestAuditor(self.hypervisor).inspect(guest, policy)
        errors = list(acceptance.errors)
        checks = []
        warnings = [
            "Libvirt XML is not a direct observation of the running QEMU process security context",
            "Host or libvirt settings may change after observation; the report is point-in-time only",
            "Review actual SELinux contexts and guest network behavior on a supervised Fedora host",
        ]

        state = acceptance.state
        if state not in LIVE_STATES:
            errors.append(
                "Guest is not running in an inspectable state; no runtime security label "
                "can be asserted for a shut-off or saved VM"
            )
        else:
            checks.append("Registered current/inactive/saved XML is auditable")

        host: HostPosture = self.host_probe(runner=self.runner)
        selinux = next((item for item in host.checks if item.name == "SELinux"), None)
        if selinux is None or selinux.status != "OK" or "enforcement is enabled" not in selinux.message:
            errors.append("Host SELinux enforcing state was not positively verified")
        else:
            checks.append("Host reports SELinux enforcing (not effective guest-label proof)")

        try:
            capabilities = ET.fromstring(self.hypervisor._virsh("capabilities"))
            models = [
                (node.text or "").strip()
                for node in capabilities.findall("./host/secmodel/model")
            ]
            if capabilities.tag != "capabilities" or "selinux" not in models:
                errors.append("System libvirt does not report an SELinux security model")
            else:
                checks.append("System libvirt advertises its SELinux security model")
        except (ET.ParseError, ToolError):
            errors.append("Cannot read valid system libvirt SELinux security capabilities")

        # Read only the ACTUAL currently registered domain XML. This is not
        # domiflist/guest-agent probing and cannot wake or interact with a VM.
        try:
            current_xml = ET.fromstring(self.hypervisor._virsh("dumpxml", guest))
        except (ET.ParseError, ToolError):
            errors.append("Cannot inspect current libvirt domain security labels")
            current_xml = None

        if current_xml is not None:
            labels = [
                item for item in current_xml.findall("seclabel")
                if item.get("model") == "selinux"
            ]
            if len(labels) != 1:
                errors.append("Expected exactly one explicit libvirt SELinux domain label")
            else:
                label = labels[0]
                if label.get("type") != "dynamic" or label.get("relabel") == "no":
                    errors.append("Runtime domain label is not dynamic and relabel-enabled")
                domain_label = (label.findtext("label") or "").strip()
                image_label = (label.findtext("imagelabel") or "").strip()
                proc = PROCESS_LABEL.fullmatch(domain_label)
                image = IMAGE_LABEL.fullmatch(image_label)
                if proc is None or image is None:
                    errors.append("Missing or unexpected sVirt process/image label metadata")
                elif proc.group(1) != image.group(1):
                    errors.append("sVirt process and image MCS category sets differ")
                else:
                    checks.append(
                        "Libvirt reports matching sVirt process/image MCS categories "
                        "(categories withheld from evidence)"
                    )
            # If another client changes the VM state during observations, do
            # not return green results based on a stale mixed-time snapshot.
            try:
                end_state = self.hypervisor.state(guest).strip().lower()
                if end_state != state:
                    errors.append("VM state changed while collecting runtime label evidence")
            except ToolError:
                errors.append("VM state could not be reverified after label inspection")

        return RuntimeLabelObservation(
            guest, policy, state,
            tuple(checks), tuple(dict.fromkeys(errors)), tuple(warnings),
        )


def save_runtime_observation(report: RuntimeLabelObservation, destination) -> object:
    """Use existing exclusive-create private JSON report handling."""
    return save_acceptance(report, destination)
