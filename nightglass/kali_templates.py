"""Curated, non-installing Kali VM templates for authorized assessments.

Each profile plans a distinct guest identity/disk; no install-everything
profile or default Internet bridge. All software names are fixed maintainer-
controlled Kali/Debian package identifiers, not user-provided shell code.

Neither this module nor provisioning dry-run installs packages, clones VMs,
starts guests, downloads an ISO or authorizes an external network.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

from .portability import MachineBudget, current_budget
from .provisioning import GuestPlan, build_plan
from .runner import ToolError

PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
TEMPLATE_ID = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
MAX_TOOLS = 7


@dataclass(frozen=True)
class KaliTemplate:
    identifier: str
    name: str
    category: str
    purpose: str
    packages: tuple[str, ...]
    ram_mib: int
    disk_gib: int
    vcpus: int
    caution: str

    def __post_init__(self):
        if (not TEMPLATE_ID.fullmatch(self.identifier) or
                self.category not in {"white-hat", "red-team"} or
                not 1 <= len(self.packages) <= MAX_TOOLS or
                len(set(self.packages)) != len(self.packages) or
                any(not PACKAGE_NAME.fullmatch(pkg) or pkg.startswith("kali-linux-")
                    or pkg.startswith("kali-tools-") for pkg in self.packages)):
            raise ValueError("Unsafe or excessively broad Kali template")
        if not (1024 <= self.ram_mib <= 3584 and 24 <= self.disk_gib <= 96
                and 1 <= self.vcpus <= 2):
            raise ValueError("Kali templates must use conservative laptop-first limits")

    @property
    def default_name(self) -> str:
        return "nightglass-kali-" + self.identifier

    def install_preview(self) -> str:
        """Human-readable in-guest only; NEVER executed by Nightglass."""
        return (
            "Inside the separately installed, verified Kali guest ONLY, after\n"
            "the owner intentionally configures approved update connectivity:\n"
            "  sudo apt update\n"
            "  sudo apt install --no-install-recommends " + " ".join(self.packages)
        )

    def describe(self) -> str:
        return "\n".join((
            f"TEMPLATE: {self.name} [{self.identifier}]",
            f"Focus: {self.category} | Authorized use: {self.purpose}",
            f"Independent VM: {self.default_name}",
            f"Suggested RAM: {self.ram_mib} MiB | vCPU: {self.vcpus} | disk: {self.disk_gib} GiB",
            f"Suggested individual packages ({len(self.packages)}): {', '.join(self.packages)}",
            "Connectivity: NONE (no adapter during initial VM install).",
            "Guest policy: lab, but the proposed VM definition is initially DISCONNECTED.",
            "This is a TEMPLATE PLAN — no downloads, software installation, VM disk, clone,",
            "VM registration or start, guest networking or host changes were performed.",
            "Each template uses a different NEW virtual disk; never share live writable images.",
            "Never enable general Internet forwarding or attach a host directory by default.",
            "CAUTION: " + self.caution,
            "Package names/dependencies may change across Kali releases: confirm",
            "origin, license, footprint and dependencies INSIDE the guest first.",
            "DO NOT use kali-linux-everything, kali-linux-large or broad kali-tools-* groups.",
            "",
            self.install_preview(),
        ))


# Kali upstream documentation: docs/KALI_TEMPLATES.md
# "Red-team" designates an authorized security exercise, not permission to
# assess public or third-party assets.
CATALOG: tuple[KaliTemplate, ...] = (
    KaliTemplate(
        "recon", "Recon & Asset Inventory", "white-hat",
        "Asset enumeration and documentation on systems in an agreed scope",
        ("nmap", "dnsrecon", "whois", "traceroute", "curl", "jq"),
        2048, 32, 1,
        "Scans can cause alerts or service load; respect scope and rate limits.",
    ),
    KaliTemplate(
        "web-audit", "Web Application Assessment", "white-hat",
        "Web inspection, endpoint testing and vulnerability verification",
        ("burpsuite", "whatweb", "nikto", "ffuf", "sqlmap"),
        3072, 48, 2,
        "Active fuzzing and SQL tests can be disruptive; use only approved targets.",
    ),
    KaliTemplate(
        "defense", "Defensive Triage & Forensics", "white-hat",
        "Packet review, file inspection and host audit in a disposable VM",
        ("wireshark", "tcpdump", "yara", "sleuthkit", "lynis"),
        2560, 40, 2,
        "Treat captured files and evidence as untrusted; no automatic host mounts.",
    ),
    KaliTemplate(
        "wireless", "Wireless Survey Lab", "white-hat",
        "Authorized wireless observation and adapter-independent preparation",
        ("aircrack-ng", "kismet", "iw", "wireshark"),
        2560, 48, 2,
        "RF operations need explicit local authorization and compatible adapter "
        "passthrough; Nightglass restricted VMs do not enable USB passthrough.",
    ),
    KaliTemplate(
        "ad-review", "Directory & Identity Review", "red-team",
        "Defender-approved Active Directory posture and service review",
        ("impacket-scripts", "netexec", "ldap-utils", "smbclient", "nmap"),
        3072, 56, 2,
        "Authenticate only with sanctioned lab accounts; broad enumeration "
        "or credential testing may lock accounts and affect production.",
    ),
    KaliTemplate(
        "exploit-lab", "Controlled Exploit Research", "red-team",
        "Disposable, non-production exploit reproduction and debugging",
        ("metasploit-framework", "exploitdb", "gdb", "nmap"),
        3072, 72, 2,
        "Potentially dangerous payloads: use benign practice targets only, "
        "do not enable public egress, and never execute malware on the host.",
    ),
    KaliTemplate(
        "web-validation", "Red-Team Web Validation", "red-team",
        "Scoped, lab-only web attack-surface and input validation exercises",
        ("ffuf", "sqlmap", "burpsuite", "whatweb"),
        3072, 48, 2,
        "Do not run unsanctioned exploitation or high-rate testing against public services.",
    ),
)
_BY_ID = {item.identifier: item for item in CATALOG}
if len(_BY_ID) != len(CATALOG):
    raise RuntimeError("Duplicate Kali template identifier")


def list_templates(category: str | None = None) -> tuple[KaliTemplate, ...]:
    if category is None:
        return CATALOG
    if category not in {"white-hat", "red-team"}:
        raise ToolError("Template category must be white-hat or red-team")
    return tuple(item for item in CATALOG if item.category == category)


def get_template(identifier: str) -> KaliTemplate:
    try:
        return _BY_ID[identifier]
    except (KeyError, TypeError) as exc:
        raise ToolError("Unknown Kali template. Run nightglass templates list.") from exc


def plan_template(
    identifier: str,
    iso_path,
    expected_sha256: str,
    *,
    name: str | None = None,
    ram_mib: int | None = None,
    vcpus: int | None = None,
    disk_gib: int | None = None,
    budget: MachineBudget | None = None,
) -> GuestPlan:
    """Delegate existing ISO/hash/name/resource checks to build_plan."""
    template = get_template(identifier)
    budget = budget or current_budget()
    cap = int(budget.guest_ram_cap_gib * 1024)
    if cap < 1024:
        raise ToolError("Host budget cannot support a separate Kali VM")
    return build_plan(
        "pentest", iso_path, expected_sha256,
        name=name or template.default_name,
        ram_mib=ram_mib if ram_mib is not None else min(template.ram_mib, cap),
        vcpus=vcpus if vcpus is not None else min(template.vcpus, budget.vcpu_cap),
        disk_gib=disk_gib if disk_gib is not None else template.disk_gib,
        budget=budget,
    )
