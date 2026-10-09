"""Machine-local resource budgets. Workspace identities remain portable.

Preferences are hints; runtime ceilings are clamped to physical host resources.
No hardware serial numbers, hostnames, disk identifiers or secrets are collected.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat

from .diagnostics import total_ram_gib
from .models import WorkspaceError

PRESETS = ("auto", "compact", "balanced", "performance")


@dataclass(frozen=True)
class MachinePreferences:
    preset: str = "auto"
    guest_ram_cap_gib: float | None = None
    active_vm_cap: int | None = None
    vcpu_cap: int | None = None
    automatic_update_checks: bool = False

    def __post_init__(self):
        if self.preset not in PRESETS:
            raise WorkspaceError("Unknown machine resource preset")
        if self.guest_ram_cap_gib is not None:
            if isinstance(self.guest_ram_cap_gib, bool) or not isinstance(self.guest_ram_cap_gib, (int, float)):
                raise WorkspaceError("RAM cap must be a number")
            if not (1.0 <= self.guest_ram_cap_gib <= 128):
                raise WorkspaceError("RAM cap must be within 1–128 GiB")
        for name, value in (("active_vm_cap", self.active_vm_cap), ("vcpu_cap", self.vcpu_cap)):
            if value is not None and (type(value) is not int or not (1 <= value <= 128)):
                raise WorkspaceError(f"{name} must be an integer in 1–128")
        if type(self.automatic_update_checks) is not bool:
            raise WorkspaceError("automatic_update_checks must be a boolean")


@dataclass(frozen=True)
class MachineBudget:
    preset: str
    ram_gib: float | None
    logical_cpus: int
    guest_ram_cap_gib: float
    active_vm_cap: int
    vcpu_cap: int
    update_checks_enabled: bool

    def explain(self) -> str:
        total = "unknown" if self.ram_gib is None else f"{self.ram_gib:.1f} GiB"
        return (f"Profile: {self.preset} | Host RAM: {total} | Logical CPUs: {self.logical_cpus} | "
                f"Max VM RAM: {self.guest_ram_cap_gib:g} GiB | Max active VMs: {self.active_vm_cap} | "
                f"Suggested vCPU maximum: {self.vcpu_cap} | Auto-check for updates: "
                f"{'on' if self.update_checks_enabled else 'off'}")


def budget_for(
    ram_gib: float | None, logical_cpus: int | None, prefs: MachinePreferences | None = None
) -> MachineBudget:
    prefs = prefs or MachinePreferences()
    cpus = max(1, int(logical_cpus or 1))
    # Unknown capacity intentionally maps to the most conservative budget.
    if ram_gib is None or ram_gib < 11:
        hard_ram, hard_vms = max(1.0, min(3.5, (ram_gib or 6.0) - 4.0)), 1
    elif ram_gib < 20:
        hard_ram, hard_vms = min(6.0, ram_gib - 5.0), 2
    else:
        hard_ram, hard_vms = min(12.0, ram_gib * 0.45), 3
    mode = prefs.preset
    if mode == "compact":
        desired_ram, desired_vms, desired_cpu = 2.5, 1, 2
    elif mode == "balanced":
        desired_ram, desired_vms, desired_cpu = 6.0, 2, 4
    elif mode == "performance":
        desired_ram, desired_vms, desired_cpu = hard_ram, hard_vms, cpus - 1
    else:
        desired_ram, desired_vms, desired_cpu = hard_ram, hard_vms, min(4, cpus - 1)
    ram = min(hard_ram, desired_ram, prefs.guest_ram_cap_gib or hard_ram)
    vms = min(hard_vms, desired_vms, prefs.active_vm_cap or hard_vms)
    vcpus = min(max(1, cpus - 1), max(1, desired_cpu), prefs.vcpu_cap or cpus)
    return MachineBudget(mode, ram_gib, cpus, round(ram, 2), max(1, vms), max(1, vcpus), prefs.automatic_update_checks)


def current_budget(prefs: MachinePreferences | None = None) -> MachineBudget:
    return budget_for(total_ram_gib(), os.cpu_count(), prefs or load_machine_preferences())


def machine_prefs_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "nightglass" / "machine.json"


def load_machine_preferences(path: Path | None = None) -> MachinePreferences:
    path = path if path is not None else machine_prefs_file()
    if not path.exists():
        return MachinePreferences()
    try:
        if path.is_symlink():
            raise WorkspaceError("Refusing symlinked machine preferences")
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("version") != 1:
            raise WorkspaceError("Unsupported machine preferences format")
        fields = {k: v for k, v in document.items() if k != "version"}
        return MachinePreferences(**fields)
    except (OSError, ValueError, TypeError) as exc:
        raise WorkspaceError(f"Cannot load machine preferences: {exc}") from exc


def save_machine_preferences(prefs: MachinePreferences, path: Path | None = None) -> None:
    path = path if path is not None else machine_prefs_file()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise WorkspaceError("Refusing symlinked machine preferences")
    content = json.dumps({
        "version": 1,
        "preset": prefs.preset,
        "guest_ram_cap_gib": prefs.guest_ram_cap_gib,
        "active_vm_cap": prefs.active_vm_cap,
        "vcpu_cap": prefs.vcpu_cap,
        "automatic_update_checks": prefs.automatic_update_checks,
    }, indent=2) + "\n"
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        with tmp.open("x", encoding="utf-8") as fh:
            os.fchmod(fh.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
