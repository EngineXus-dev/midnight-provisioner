"""Read-only VM inspection and guarded libvirt lifecycle operations.

Security checks are a launch-time safety rail, not an isolation boundary: a
privileged user or another program can change libvirt definitions independently.
"""
from __future__ import annotations
from dataclasses import dataclass
from threading import Lock
from xml.etree import ElementTree as ET
from .models import safe_name
from .runner import Runner, ToolError
from .diagnostics import total_ram_gib

LIBVIRT_URI = "qemu:///system"
ISOLATED_NETWORK = "nightglass-lab"


@dataclass(frozen=True)
class Audit:
    ok: bool
    warnings: tuple[str, ...]
    policy: str

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
    for tag, explanation in (
        ("filesystem", "Host filesystem passthrough is configured"),
        ("hostdev", "Physical host device passthrough is configured"),
        ("redirdev", "USB redirection is configured"),
        ("shmem", "Shared memory device is configured"),
        ("vsock", "Host/guest vsock communication is configured"),
    ):
        if devices.find(tag) is not None:
            issues.append(explanation)
    for disk in devices.findall("disk"):
        if disk.get("device", "disk") == "disk" and disk.get("type") not in {"file", "volume"}:
            issues.append("Disk uses an unapproved backing type (block devices forbidden)")
        source = disk.find("source")
        if source is not None and source.get("dev"):
            issues.append("Direct host block device attached")
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

    def audit(self, domain: str, policy: str) -> Audit:
        try:
            xml = self._virsh("dumpxml", safe_name(domain))
            lab_xml = None
            if policy == "lab":
                try:
                    root = ET.fromstring(xml)
                    interfaces = root.findall("./devices/interface")
                    if interfaces:
                        lab_xml = self._virsh("net-dumpxml", ISOLATED_NETWORK)
                except ET.ParseError:
                    pass  # assess_domain will reject malformed XML
            # assess_domain also detects and fails if the lab network cannot be verified.
            return assess_domain(xml, policy, lab_xml)
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
        if ram is not None and ram < 11:
            for other in self.list_domains():
                if other == domain:
                    continue
                if self.state(other).lower().startswith(("running", "paused", "idle")):
                    raise ToolError("Low-memory guard: another VM is already active. Stop or save it before starting a second VM.")
            try:
                xml = ET.fromstring(self._virsh("dumpxml", domain))
                mem = xml.find("memory")
                if mem is None or not mem.text:
                    raise ValueError("VM RAM declaration missing")
                units = {"kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "b": 1}
                unit = (mem.get("unit") or "KiB").lower()
                if unit not in units:
                    raise ValueError("Unsupported VM memory unit")
                vm_gib = int(mem.text.strip()) * units[unit] / (1024 ** 3)
            except (ET.ParseError, ValueError, TypeError) as exc:
                raise ToolError(f"Low-memory guard: cannot verify VM RAM size ({exc})") from exc
            if vm_gib > 3.5:
                raise ToolError(f"Low-memory guard: VM requests {vm_gib:.1f} GiB; limit this 8-GB-class host to <=3.5 GiB per guest.")
        return self._virsh("start", domain, timeout=120).strip() or "VM started"

    def shutdown(self, domain: str) -> str:
        safe_name(domain)
        return self._virsh("shutdown", domain, timeout=30).strip() or "Shutdown requested"

    def managed_save(self, domain: str) -> str:
        safe_name(domain)
        return self._virsh("managedsave", domain, timeout=600).strip() or "VM state saved"
