"""Read-only VM inspection and guarded libvirt lifecycle operations.

Security checks are a launch-time safety rail, not an isolation boundary: a
privileged user or another program can change libvirt definitions independently.
"""
from __future__ import annotations
from dataclasses import dataclass
import os
import re
from threading import Lock
from xml.etree import ElementTree as ET
from .models import safe_name
from .runner import Runner, ToolError
from .diagnostics import total_ram_gib
from .portability import budget_for, load_machine_preferences

LIBVIRT_URI = "qemu:///system"
ISOLATED_NETWORK = "nightglass-lab"


@dataclass(frozen=True)
class Audit:
    ok: bool
    warnings: tuple[str, ...]
    policy: str
    saved_state: bool = False

    @property
    def summary(self) -> str:
        return "Allowed" if self.ok else "Blocked"


def assess_domain(xml_text: str, policy: str, lab_net_xml: str | None = None) -> Audit:
    """Fail-closed XML check for VMs controlled as isolated/lab workspaces."""
    issues: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return Audit(False, ("Domain XML could not be parsed",), policy)
    if root.tag != "domain":
        return Audit(False, ("Unexpected domain XML root",), policy)
    if policy not in {"trusted", "isolated", "lab"}:
        return Audit(False, ("Unsupported VM security policy",), policy)
    devices = root.find("devices")
    if devices is None:
        return Audit(False, ("Domain device inventory is missing",), policy)
    if policy == "trusted":
        # Trusted means development guests only: not an audit for hostile code.
        return Audit(True, ("Trusted VM: no strict network/device isolation enforced",), policy)
    # An explicit opt-out from sVirt/SELinux relabeling undermines the
    # restricted-guest host boundary even when its NIC inventory is empty.
    # Absence of a seclabel is not by itself proof of a problem: libvirt may
    # supply dynamic labels at domain definition/launch time.
    for label in [*root.findall("seclabel"), *devices.findall(".//seclabel")]:
        if label.get("type") == "none":
            issues.append("Guest or disk explicitly disables security labeling")
        if label.get("relabel") == "no":
            issues.append("Guest or disk explicitly disables security relabeling")
    # Namespaced QEMU extensions can redefine ordinary devices, create host
    # channels or inject extra command arguments. Reject all such extensions.
    if any(node.tag.startswith("{http://libvirt.org/schemas/domain/qemu/1.0}") for node in root.iter()):
        issues.append("QEMU extension bypasses the restricted device policy")
    for tag, explanation in (
        ("filesystem", "Host filesystem passthrough is configured"),
        ("hostdev", "Physical host device passthrough is configured"),
        ("redirdev", "USB redirection is configured"),
        ("shmem", "Shared memory device is configured"),
        ("vsock", "Host/guest vsock communication is configured"),
        ("serial", "Serial console can provide a host communication channel"),
        ("parallel", "Parallel port can provide a host communication channel"),
        ("console", "Guest console can provide a host communication channel"),
        ("smartcard", "Smartcard host passthrough is configured"),
        ("tpm", "TPM device requires separate isolation assessment"),
        ("rng", "RNG backend requires separate host-integration assessment"),
        ("sound", "Host audio output is not approved for restricted VMs"),
        ("audio", "Host audio backend is not approved for restricted VMs"),
    ):
        if devices.find(tag) is not None:
            issues.append(explanation)
    for disk in devices.findall("disk"):
        # A block/network-backed CD-ROM or floppy is still a host-device escape
        # from the declared policy. Libvirt volume pools may also be block-backed.
        if disk.get("type") != "file" or disk.get("device", "disk") not in {"disk", "cdrom"}:
            issues.append("Disk/CD-ROM uses an unapproved device or storage type")
        for storage in [disk, *disk.findall(".//backingStore")]:
            if storage is not disk and storage.get("type") not in {None, "file"}:
                issues.append("Disk backing chain uses an unapproved storage type")
            source = storage.find("source")
            if source is not None:
                if any(source.get(attr) for attr in ("dev", "protocol", "name", "pool", "volume")):
                    issues.append("Disk or backing chain references host device, network or storage pool")
                path = source.get("file", "")
                if path.startswith(("/dev/", "/proc/", "/sys/")):
                    issues.append("Disk image path is a special host filesystem")
    for channel in devices.findall("channel"):
        issues.append("Guest agent or SPICE channel may provide host integration")
    for graphics in devices.findall("graphics"):
        if graphics.get("type") == "spice":
            issues.append("SPICE display can expose host integration/clipboard")
        listen = graphics.get("listen", "")
        listens = graphics.findall("listen")
        for item in listens:
            if item.get("type") == "address":
                listen = item.get("address", listen)
            elif item.get("type") not in {"none", "socket"}:
                issues.append("Unapproved graphics listen mode")
        if graphics.get("type") not in {"vnc", "none"}:
            issues.append("Isolated VMs require VNC or no graphical device")
        if listen not in {"127.0.0.1", "::1"} and not any(it.get("type") in {"none", "socket"} for it in listens):
            issues.append("Graphics must explicitly bind to loopback or a UNIX socket")
    interfaces = devices.findall("interface")
    if policy == "isolated" and interfaces:
        issues.append("Offline analysis VM has a network interface")
    if policy == "lab":
        for iface in interfaces:
            source = iface.find("source")
            if (iface.get("type") != "network" or source is None or
                    source.get("network") != ISOLATED_NETWORK):
                issues.append("Pentest VM network must be nightglass-lab only")
        if interfaces:
            try:
                network_root = ET.fromstring(lab_net_xml or "")
                if network_root.tag != "network" or network_root.findtext("name") != ISOLATED_NETWORK:
                    issues.append("Lab network definition does not match expected name")
                if network_root.find("forward") is not None:
                    issues.append("Lab network forwards traffic: not isolated")
                if network_root.find("bridge") is None:
                    issues.append("Lab network bridge configuration is missing")
            except ET.ParseError:
                issues.append("Could not validate the lab network definition")
    return Audit(not issues, tuple(dict.fromkeys(issues)), policy)


def declared_guest_memory_gib(xml_text: str) -> float:
    """Use the maximum declared RAM, including hotplug, for low-memory limits."""
    root = ET.fromstring(xml_text)
    units = {"kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "b": 1}
    sizes = []
    for name in ("memory", "currentMemory", "maxMemory"):
        mem = root.find(name)
        if mem is None:
            if name == "memory":
                raise ValueError("VM RAM declaration missing")
            continue
        if not mem.text:
            raise ValueError(f"{name} size is missing")
        unit = (mem.get("unit") or "KiB").lower()
        if unit not in units:
            raise ValueError(f"Unsupported {name} memory unit")
        amount = int(mem.text.strip())
        if amount <= 0:
            raise ValueError(f"Invalid {name} memory value")
        sizes.append(amount * units[unit] / (1024 ** 3))
    return max(sizes)

class Hypervisor:
    def __init__(self, runner: Runner | None = None):
        self.runner = runner or Runner()
        self._launch_lock = Lock()

    def _virsh(self, *args: str, timeout: int = 12) -> str:
        return self.runner.run(["virsh", "--connect", LIBVIRT_URI, *args], timeout=timeout).stdout

    def list_domains(self) -> list[str]:
        return [line.strip() for line in self._virsh("list", "--all", "--name").splitlines() if line.strip()]

    def state(self, domain: str) -> str:
        return self._virsh("domstate", safe_name(domain)).strip()

    def _managed_save_xml(self, domain: str) -> str | None:
        """Query libvirt, not a user-controlled flag, before evaluating a resume."""
        info = self._virsh("dominfo", safe_name(domain))
        match = re.search(r"(?im)^\s*Managed save\s*:\s*(yes|no)\s*$", info)
        if not match:
            raise ToolError("Cannot verify managed-save status from libvirt dominfo")
        if match.group(1).lower() == "yes":
            return self._virsh("managedsave-dumpxml", domain)
        return None

    def audit(self, domain: str, policy: str) -> Audit:
        """Inspect current, persistent and saved definitions of restricted VMs.

        A running VM's live XML can differ from its next-boot definition. Both
        need to pass policy before a future start or managed-save operation.
        This is still a point-in-time check, not a lock on other libvirt clients.
        """
        try:
            domain = safe_name(domain)
            live_xml = self._virsh("dumpxml", domain)
            if policy == "trusted":
                return assess_domain(live_xml, policy)
            if policy not in {"lab", "isolated"}:
                return Audit(False, ("Unsupported VM security policy",), policy)

            # --inactive is an inspection, NOT a define or guest state change.
            inactive_xml = self._virsh("dumpxml", "--inactive", domain)
            saved_xml = self._managed_save_xml(domain)
            documents = [
                ("Current definition", live_xml),
                ("Inactive definition", inactive_xml),
            ]
            if saved_xml is not None:
                documents.append(("Saved session", saved_xml))

            lab_xml = None
            if policy == "lab":
                try:
                    if any(
                        ET.fromstring(doc).find("./devices/interface") is not None
                        for _, doc in documents
                    ):
                        lab_xml = self._virsh("net-dumpxml", ISOLATED_NETWORK)
                except ET.ParseError:
                    pass  # malformed documents are rejected in policy checks
            failures = []
            identities = []
            for label, doc in documents:
                audit = assess_domain(doc, policy, lab_xml)
                if not audit.ok:
                    failures.extend(f"{label}: {warning}" for warning in audit.warnings)
                try:
                    root = ET.fromstring(doc)
                    name = root.findtext("name")
                    uuid = root.findtext("uuid")
                    if name != domain:
                        failures.append(f"{label}: identity name does not match registered guest")
                    identities.append((label, name, uuid))
                except ET.ParseError:
                    pass  # assess_domain already rejected malformed XML
            for label, name, uuid in identities[1:]:
                if name != identities[0][1]:
                    failures.append(f"{label}: different name from current definition")
                if uuid and identities[0][2] and uuid != identities[0][2]:
                    failures.append(f"{label}: different uuid from current definition")
            return Audit(not failures, tuple(dict.fromkeys(failures)), policy, saved_xml is not None)
        except ToolError as exc:
            return Audit(False, (str(exc),), policy)

    def start(self, domain: str, policy: str) -> str:
        # Serialize all Nightglass-issued launches; not a lock on external tools.
        with self._launch_lock:
            return self._start_checked(domain, policy)

    def _start_checked(self, domain: str, policy: str) -> str:
        safe_name(domain)
        if domain not in self.list_domains():
            raise ToolError("VM is not defined in system libvirt")
        check = self.audit(domain, policy)
        if not check.ok:
            raise ToolError("Blocked by workspace policy: " + "; ".join(check.warnings))
        ram = total_ram_gib()
        budget = budget_for(ram, os.cpu_count(), load_machine_preferences())
        active = []
        for other in self.list_domains():
            if other == domain:
                continue
            if self.state(other).lower().startswith(("running", "paused", "idle")):
                active.append(other)
        if len(active) >= budget.active_vm_cap:
            raise ToolError(
                "Low-memory guard: another VM is already active. "
                f"Machine profile allows at most {budget.active_vm_cap} active VM(s)."
            )
        try:
            # Include a libvirt saved session's own declared maximum RAM.
            xml_docs = [self._virsh("dumpxml", domain)]
            if policy in {"lab", "isolated"}:
                # Recheck the actual next-boot definition as well as any
                # saved session for the memory budget; neither must bypass it.
                xml_docs.append(self._virsh("dumpxml", "--inactive", domain))
                saved = self._managed_save_xml(domain)
                if saved is not None:
                    xml_docs.append(saved)
            vm_gib = max(declared_guest_memory_gib(xml) for xml in xml_docs)
        except (ET.ParseError, ValueError, TypeError) as exc:
            raise ToolError(f"Low-memory guard: cannot verify VM RAM size ({exc})") from exc
        if vm_gib > budget.guest_ram_cap_gib:
            raise ToolError(
                f"Low-memory guard: VM declares up to {vm_gib:.1f} GiB; "
                f"machine profile permits {budget.guest_ram_cap_gib:.1f} GiB per guest."
            )
        if active:
            # On larger machines also account for VMs started by other tools.
            # In particular, an external oversized VM should consume the
            # budget instead of giving Nightglass permission to oversubscribe.
            try:
                active_memory = sum(
                    declared_guest_memory_gib(self._virsh("dumpxml", other))
                    for other in active
                )
            except (ET.ParseError, ValueError, TypeError) as exc:
                raise ToolError(f"Cannot verify active VM memory: {exc}") from exc
            host_reserve = 6.0 if ram is not None and ram < 20 else 8.0
            if ram is None or active_memory + vm_gib > max(1.0, ram - host_reserve):
                raise ToolError("VM memory exceeds host reserve after existing guests")
        return self._virsh("start", domain, timeout=120).strip() or "VM started"

    def shutdown(self, domain: str) -> str:
        safe_name(domain)
        return self._virsh("shutdown", domain, timeout=30).strip() or "Shutdown requested"

    def managed_save(self, domain: str, policy: str) -> str:
        safe_name(domain)
        if policy == "isolated":
            raise ToolError("Analysis VMs must be shut down/discarded; saving a potentially infected RAM image is disabled")
        check = self.audit(domain, policy)
        if not check.ok:
            raise ToolError("Cannot save a VM that violates its workspace policy: " + "; ".join(check.warnings))
        return self._virsh("managedsave", domain, timeout=600).strip() or "VM state saved"
