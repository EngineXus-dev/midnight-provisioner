"""Read-only current host pressure and out-of-band libvirt VM activity.

Purely advisory: resource readings are never used to claim secure isolation
or stop external VMs. Inaccessible libvirt or missing /proc/meminfo fails to
UNKNOWN/CAUTION, never a false 'all clear'.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .hypervisor import Hypervisor
from .models import Workspace
from .portability import MachineBudget, current_budget
from .runner import ToolError

MEMINFO = Path("/proc/meminfo")
ACTIVE_STATES = ("running", "paused", "idle", "pmsuspended", "in shutdown")


@dataclass(frozen=True)
class MemoryPressure:
    total_gib: float | None
    available_gib: float | None
    swap_total_gib: float | None
    swap_used_gib: float | None

    @property
    def available_percent(self) -> float | None:
        if self.total_gib is None or self.available_gib is None or self.total_gib <= 0:
            return None
        return round(100.0 * self.available_gib / self.total_gib, 1)


def parse_meminfo(text: str) -> MemoryPressure:
    """Use MemAvailable rather than MemFree, including reclaimable cache."""
    entries = {}
    for line in text.splitlines():
        key, sep, remainder = line.partition(":")
        if not sep or key not in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
            continue
        parts = remainder.strip().split()
        if len(parts) != 2 or parts[1] != "kB":
            continue
        try:
            value = int(parts[0])
        except ValueError:
            continue
        if value >= 0:
            entries[key] = value / (1024 ** 2)
    total = entries.get("MemTotal")
    available = entries.get("MemAvailable")
    if total is None or total <= 0 or available is None or available > total:
        total, available = None, None
    swap_total = entries.get("SwapTotal")
    swap_free = entries.get("SwapFree")
    if swap_total is None or swap_free is None or swap_free > swap_total:
        swap_total, swap_used = None, None
    else:
        swap_used = max(0.0, swap_total - swap_free)
    return MemoryPressure(total, available, swap_total, swap_used)


def host_memory(path: Path = MEMINFO) -> MemoryPressure:
    try:
        return parse_meminfo(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return MemoryPressure(None, None, None, None)


@dataclass(frozen=True)
class ResourceSnapshot:
    memory: MemoryPressure
    budget: MachineBudget
    active_vms: tuple[str, ...]
    unbound_vms: tuple[str, ...]
    libvirt_available: bool
    level: str
    warnings: tuple[str, ...]

    def describe(self) -> str:
        mem = self.memory
        if mem.available_gib is None:
            memory_line = "Host memory pressure: unknown; MemAvailable unavailable"
        else:
            memory_line = (
                f"Host RAM available: {mem.available_gib:.2f} / {mem.total_gib:.2f} GiB"
                f" ({mem.available_percent:g}% available)"
            )
        swap_line = (
            "Swap: unknown" if mem.swap_total_gib is None else
            f"Swap used: {mem.swap_used_gib:.2f} / {mem.swap_total_gib:.2f} GiB"
        )
        return "\n".join([
            f"RESOURCE PRESSURE: {self.level}",
            memory_line,
            swap_line,
            f"Guest launch budget: {self.budget.active_vm_cap} simultaneous VM(s),"
            f" {self.budget.guest_ram_cap_gib:g} GiB each (limit, not a guarantee)",
            "Registered active VMs: " +
            (", ".join(self.active_vms) if self.active_vms else
             ("none reported" if self.libvirt_available else "unknown — libvirt unavailable")),
            "Unbound/externally managed active VMs: " +
            (", ".join(self.unbound_vms) if self.unbound_vms else
             ("none reported" if self.libvirt_available else "unknown")),
            *(f"CAUTION {warning}" for warning in self.warnings),
            "READ-ONLY: Midnight Provisioner neither stops VMs nor modifies memory or swap.",
            "Another client can start or change guests at any time. This is advisory, not isolation enforcement.",
        ])


def collect_resources(
    *, hypervisor: Hypervisor | None = None,
    memory: MemoryPressure | None = None,
    budget: MachineBudget | None = None,
    workspaces: tuple[Workspace, ...] | list[Workspace] = (),
) -> ResourceSnapshot:
    """Collect without creating, stopping, or changing any VM."""
    hypervisor = hypervisor or Hypervisor()
    memory = memory if memory is not None else host_memory()
    budget = budget or current_budget()
    warnings = []
    severity = 0  # 0 normal, 1 caution, 2 critical, 3 unknown/unverified

    if memory.available_gib is None:
        severity = max(severity, 3)
        warnings.append("Cannot measure available RAM; do not assume a guest is safe to start")
    elif memory.available_gib < 1.0:
        severity = max(severity, 2)
        warnings.append("Very little available RAM; starting another VM may exhaust host memory")
    elif memory.available_gib < max(1.5, 0.15 * memory.total_gib):
        severity = max(severity, 1)
        warnings.append("Host RAM pressure is elevated; close unnecessary workloads before starting a VM")

    if (memory.swap_total_gib is not None and memory.swap_total_gib > 0
            and memory.swap_used_gib is not None
            and memory.swap_used_gib / memory.swap_total_gib >= 0.8):
        severity = max(severity, 1)
        warnings.append("High swap occupancy observed (not itself a measure of current swap activity)")

    active = []
    available = True
    try:
        for name in hypervisor.list_domains():
            state = hypervisor.state(name).strip().lower()
            if state.startswith(ACTIVE_STATES):
                active.append(name)
            elif state not in {"shut off", "crashed"}:
                available = False
                warnings.append(f"Unknown state for VM '{name}'; resource safety is not verified")
    except (ToolError, ValueError) as exc:
        available = False
        warnings.append(f"Cannot inspect system libvirt: {exc}")
    active = tuple(sorted(set(active)))
    known = {space.identifier for space in workspaces if space.kind == "vm" and space.identifier}
    unbound = tuple(name for name in active if name not in known)
    if not available:
        severity = max(severity, 3)
    else:
        if len(active) > budget.active_vm_cap:
            severity = max(severity, 2)
            warnings.append("Existing active VM count exceeds the current Midnight Provisioner concurrency budget")
        elif len(active) >= budget.active_vm_cap:
            severity = max(severity, 1)
            warnings.append("Active VMs already consume the Midnight Provisioner concurrency budget")
    if unbound:
        severity = max(severity, 1)
        warnings.append(
            "Other libvirt clients can start or change unbound guests outside Midnight Provisioner launch checks"
        )
    level = ("NORMAL", "CAUTION", "CRITICAL", "UNKNOWN")[severity]
    return ResourceSnapshot(memory, budget, active, unbound, available, level, tuple(warnings))
