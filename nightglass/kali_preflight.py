"""Fail-closed, read-only Fedora/Kali per-VM installer readiness preflight.

Connects a private, catalog-verified Kali setup plan to a REAL local ISO
hash, both virt-install dry-run XML stages, available host memory, active
system-libvirt guests and target storage headroom.

This does NOT reserve resources, verify software packages, install an ISO,
start/define/clone a guest, create a disk or authorize networking.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from .kali_setup import load_setup_plan
from .kali_templates import plan_template, get_template
from .portability import MachineBudget, current_budget
from .provisioning import OfflineProvisioner
from .resources import ResourceSnapshot, collect_resources
from .runner import ToolError

GIB = 1024 ** 3


@dataclass(frozen=True)
class KaliPreflightReport:
    guest: str
    template_id: str
    verified_iso_digest: str | None
    dry_run_stages: int
    free_storage_gib: float | None
    available_ram_gib: float | None
    active_vm_count: int | None
    blocked: tuple[str, ...]
    cautions: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.blocked and self.verified_iso_digest is not None and self.dry_run_stages == 2

    def describe(self) -> str:
        return "\n".join((
            "KALI TEMPLATE PREFLIGHT: " + (
                "DRY-RUN PASSED — MANUAL REVIEW ONLY" if self.ok else "BLOCKED / UNVERIFIED"
            ),
            f"Guest: {self.guest} | curated profile: {self.template_id}",
            "Local installer ISO hash: " + (
                "matched externally claimed digest" if self.verified_iso_digest else "NOT verified"
            ),
            f"Offline XML dry-run stages passed: {self.dry_run_stages}/2",
            "Available host RAM (GiB): " + (
                f"{self.available_ram_gib:.2f}" if self.available_ram_gib is not None else "UNKNOWN"
            ),
            "Registered active VMs: " + (
                str(self.active_vm_count) if self.active_vm_count is not None else "UNKNOWN"
            ),
            "Destination storage free (GiB): " + (
                f"{self.free_storage_gib:.2f}" if self.free_storage_gib is not None else "UNKNOWN"
            ),
            *(f"BLOCK {item}" for item in self.blocked),
            *(f"CAUTION {item}" for item in self.cautions),
            "READ-ONLY: no VM, virtual disk, guest packages, network, EFI or Windows files were changed.",
            "An available-space reading does not reserve space; sparse qcow2 disks can grow.",
            "No host/guest access, installed package state, secure boot, runtime confinement,",
            "actual network denial or future memory availability has been verified.",
            "Another privileged libvirt client can modify/start guests after this snapshot.",
        ))


class KaliPreflight:
    def __init__(
        self, *, provisioner: OfflineProvisioner | None = None,
        budget: MachineBudget | None = None,
        snapshot: ResourceSnapshot | None = None,
        disk_usage=None,
    ):
        self.provisioner = provisioner or OfflineProvisioner()
        self.budget = budget
        self.snapshot = snapshot
        self.disk_usage = disk_usage or shutil.disk_usage

    def inspect(self, manifest: Path, iso: Path, storage_dir: Path) -> KaliPreflightReport:
        plan_data = load_setup_plan(manifest)
        template = get_template(plan_data["template_id"])
        budget = self.budget or current_budget()
        blockers: list[str] = []
        cautions: list[str] = []
        free: float | None = None
        available: float | None = None
        active: int | None = None
        verified: str | None = None
        stages = 0

        digest_claim = plan_data["claimed_installer_iso_sha256"]
        if digest_claim is None:
            blockers.append(
                "Manifest contains no ISO SHA-256; export a NEW plan with "
                "--iso-sha256 from the official publisher"
            )

        # A user chooses a real existing destination volume. Check its
        # space without creating even a temporary directory or disk image.
        location = Path(storage_dir).expanduser()
        if location.is_symlink():
            blockers.append("Storage target cannot be a symlink")
        else:
            try:
                location = location.resolve(strict=True)
                if not location.is_dir():
                    blockers.append("Storage destination must be an existing directory")
                else:
                    free = self.disk_usage(location).free / GIB
                    # A sparse qcow2 file can expand to its advertised size.
                    # This is only a temporary headroom heuristic, not a full
                    # reservation or guarantee of future allocation success.
                    threshold = max(4.0, min(12.0, template.disk_gib / 4.0))
                    if free < threshold:
                        blockers.append(
                            f"Only {free:.2f} GiB free at the target, below the "
                            f"{threshold:.2f} GiB minimum preflight headroom heuristic"
                        )
                    if free < template.disk_gib:
                        cautions.append(
                            "Free storage is smaller than possible full qcow2 expansion; "
                            "monitor consumption and reserve disk capacity before use"
                        )
            except (OSError, ValueError) as exc:
                blockers.append("Storage destination cannot be inspected: " + type(exc).__name__)

        resources = self.snapshot
        if resources is None:
            resources = collect_resources(
                hypervisor=self.provisioner.hypervisor, budget=budget,
            )
        if resources.budget != budget:
            blockers.append("Resource snapshot and machine budget disagree; retry with fresh readings")
        memory = resources.memory.available_gib
        if memory is None or memory < 0:
            blockers.append("Host MemAvailable cannot be verified")
        else:
            available = memory
        if not resources.libvirt_available or resources.level == "UNKNOWN":
            blockers.append("Complete system libvirt VM activity cannot be verified")
        else:
            active = len(resources.active_vms)
            if active >= budget.active_vm_cap:
                blockers.append(
                    f"{active} running/paused guest(s) already consume the "
                    f"{budget.active_vm_cap} guest concurrency limit"
                )
        if resources.unbound_vms:
            cautions.append(
                "Active externally managed VMs are present; their configuration "
                "and resources can change outside Nightglass"
            )
        if resources.level in {"CAUTION", "CRITICAL"}:
            cautions.append(f"Host resource pressure reports {resources.level}")
        if memory is not None and digest_claim is not None:
            required_gib = min(template.ram_mib, int(budget.guest_ram_cap_gib * 1024)) / 1024.0 + 1.5
            if memory < required_gib:
                blockers.append(
                    f"Available RAM {memory:.2f} GiB is below guest allocation + "
                    f"1.5 GiB host breathing room ({required_gib:.2f} GiB)"
                )

        # Fail before hashing a potentially huge ISO or invoking virt-install
        # if the machine is already in an unsafe/unverifiable state.
        if not blockers:
            try:
                guest = plan_template(
                    template.identifier, iso, digest_claim,
                    name=plan_data["guest"], budget=budget,
                )
                preview = self.provisioner.preview(guest)
                verified = preview.verified_sha256
                stages = sum("audit passed" in message for message in preview.observations)
                if stages != 2:
                    blockers.append("Incomplete two-stage libvirt XML inspection")
            except (ToolError, OSError, ValueError) as exc:
                blockers.append("Local ISO/dry-run validation failed: " + str(exc)[:320])

        return KaliPreflightReport(
            guest=plan_data["guest"], template_id=template.identifier,
            verified_iso_digest=verified, dry_run_stages=stages,
            free_storage_gib=free, available_ram_gib=available,
            active_vm_count=active, blocked=tuple(blockers),
            cautions=tuple(cautions),
        )
