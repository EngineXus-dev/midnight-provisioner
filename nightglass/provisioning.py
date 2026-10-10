"""Guarded, non-mutating planning for separately installed VM guests.

Never creates guest disks, defines domains, downloads ISOs or changes host
networking. A dry-run asks installed virt-install to render both install and
post-install XML, then uses Nightglass's conservative libvirt policy checks.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import re
import shlex
from xml.etree import ElementTree as ET

from .hypervisor import Hypervisor, LIBVIRT_URI, assess_domain
from .models import safe_name
from .portability import MachineBudget, current_budget
from .runner import Runner, ToolError

ISO_HASH = re.compile(r"^[a-fA-F0-9]{64}$")
GUEST_KINDS = {
    "pentest": ("lab", "nightglass-kali", 48),
    "analysis": ("isolated", "nightglass-malware", 32),
}
MIN_ISO_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class GuestPlan:
    kind: str
    name: str
    iso_path: Path
    expected_sha256: str
    ram_mib: int
    vcpus: int
    disk_gib: int

    @property
    def policy(self) -> str:
        return GUEST_KINDS[self.kind][0]

    def command(self) -> list[str]:
        """Explicit all-offline install defaults; no command shell or sudo."""
        return [
            "virt-install", "--connect", LIBVIRT_URI, "--name", self.name,
            "--memory", str(self.ram_mib), "--vcpus", str(self.vcpus),
            "--disk", f"size={self.disk_gib},format=qcow2,bus=virtio",
            "--cdrom", str(self.iso_path),
            "--network", "none", "--graphics", "vnc,listen=127.0.0.1",
            "--serial", "none", "--console", "none", "--channel", "none",
            "--sound", "none", "--tpm", "none", "--rng", "none",
            "--smartcard", "none", "--redirdev", "none",
            "--boot", "uefi",
            "--osinfo", "detect=on,require=off",
            "--noautoconsole",
        ]

    def display_command(self) -> str:
        """Show syntax for inspection; NEVER execute from this preview."""
        return shlex.join(self.command())


def build_plan(
    kind: str,
    iso_path: str | Path,
    expected_sha256: str,
    *,
    name: str | None = None,
    ram_mib: int | None = None,
    vcpus: int | None = None,
    disk_gib: int | None = None,
    budget: MachineBudget | None = None,
) -> GuestPlan:
    if kind not in GUEST_KINDS:
        raise ToolError("Unsupported guest profile: choose pentest or analysis")
    policy, default_name, default_disk = GUEST_KINDS[kind]
    del policy
    budget = budget or current_budget()
    name = safe_name(name or default_name)
    if not isinstance(expected_sha256, str) or not ISO_HASH.fullmatch(expected_sha256):
        raise ToolError("Enter a 64-character SHA-256 digest from the official ISO publisher")
    path = Path(iso_path).expanduser()
    if path.is_symlink():
        raise ToolError("ISO symlinks are not accepted for provisioning")
    try:
        path = path.resolve(strict=True)
        size = path.stat().st_size
    except (OSError, RuntimeError) as exc:
        raise ToolError(f"Cannot access the selected ISO: {exc}") from exc
    if not path.is_file() or path.suffix.lower() != ".iso" or size < MIN_ISO_BYTES:
        raise ToolError("Choose a real local .iso file of at least 16 MiB")

    max_mib = int(budget.guest_ram_cap_gib * 1024)
    if max_mib < 1024:
        raise ToolError("Insufficient detected host RAM for a 1 GiB guest")
    ram_mib = ram_mib if ram_mib is not None else min(3072, max_mib)
    vcpus = vcpus if vcpus is not None else min(2, budget.vcpu_cap)
    disk_gib = disk_gib if disk_gib is not None else default_disk
    if type(ram_mib) is not int or not 1024 <= ram_mib <= max_mib:
        raise ToolError(f"Guest RAM must be 1024–{max_mib} MiB under the current machine profile")
    if type(vcpus) is not int or not 1 <= vcpus <= budget.vcpu_cap:
        raise ToolError(f"Guest vCPUs must be 1–{budget.vcpu_cap}")
    if type(disk_gib) is not int or not 20 <= disk_gib <= 256:
        raise ToolError("Guest virtual disk must be 20–256 GiB")
    return GuestPlan(kind, name, path, expected_sha256.lower(), ram_mib, vcpus, disk_gib)


def verify_iso(plan: GuestPlan) -> str:
    """Chunked integrity verification; does not assume trusted provenance."""
    digest = hashlib.sha256()
    try:
        with plan.iso_path.open("rb") as stream:
            for block in iter(lambda: stream.read(2 * 1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ToolError(f"ISO cannot be read: {exc}") from exc
    found = digest.hexdigest()
    if not hmac.compare_digest(plan.expected_sha256, found):
        raise ToolError("ISO SHA-256 mismatch. Reject the file and verify its official source.")
    return found


@dataclass(frozen=True)
class ProvisionPreview:
    name: str
    policy: str
    ram_mib: int
    vcpus: int
    disk_gib: int
    verified_sha256: str
    command: str
    observations: tuple[str, ...]

    def describe(self) -> str:
        return "\n".join([
            f"Guest: {self.name} | Policy: {self.policy}",
            f"RAM: {self.ram_mib} MiB | vCPUs: {self.vcpus} | new virtual disk: {self.disk_gib} GiB",
            f"ISO SHA-256 verified: {self.verified_sha256}",
            "Network: DISCONNECTED by requested configuration; local VNC only",
            "Both installation and installed-guest XML passed Nightglass's conservative audit.",
            "PREVIEW ONLY: no guest, disk, network or Windows system was changed.",
            "Review the VM's ACTUAL XML before its first boot. A dry run does not prove runtime isolation.",
            *self.observations,
            "",
            "Proposed command for manual review (NOT executed by Nightglass):",
            self.command,
        ])


class OfflineProvisioner:
    def __init__(self, runner: Runner | None = None, hypervisor: Hypervisor | None = None):
        self.runner = runner or Runner()
        self.hypervisor = hypervisor or Hypervisor(self.runner)

    def preview(self, plan: GuestPlan) -> ProvisionPreview:
        if plan.name in self.hypervisor.list_domains():
            raise ToolError(f"A libvirt domain named {plan.name} already exists; existing VMs are never overwritten")
        verified = verify_iso(plan)
        observations = []
        base = plan.command()
        for stage in (1, 2):
            # --dry-run is crucial: --print-xml WITHOUT it may create disk files.
            result = self.runner.run([*base, "--dry-run", "--print-xml", str(stage)], timeout=120)
            try:
                root = ET.fromstring(result.stdout.strip())
            except ET.ParseError as exc:
                raise ToolError(f"virt-install stage {stage} yielded no valid single XML definition: {exc}") from exc
            if root.tag != "domain":
                raise ToolError(f"Unexpected XML for virt-install stage {stage}")
            if root.findtext("name") != plan.name:
                raise ToolError(f"virt-install stage {stage} does not preserve the requested guest name")
            if root.find("./devices/interface") is not None:
                raise ToolError(f"virt-install stage {stage} unexpectedly includes guest networking")
            audit = assess_domain(result.stdout, plan.policy)
            if not audit.ok:
                raise ToolError(
                    f"virt-install stage {stage} violates the {plan.policy} workspace rules: "
                    + "; ".join(audit.warnings)
                )
            observations.append(f"Install stage {stage}: offline XML audit passed")
        return ProvisionPreview(
            plan.name, plan.policy, plan.ram_mib, plan.vcpus, plan.disk_gib,
            verified, plan.display_command(), tuple(observations),
        )
