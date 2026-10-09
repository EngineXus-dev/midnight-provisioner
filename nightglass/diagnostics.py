"""Read-only host diagnostics and resource-budget hints."""
from __future__ import annotations
import os
import platform
import shutil
from dataclasses import dataclass
from .runner import Runner, ToolError


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    message: str


def total_ram_gib() -> float | None:
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    return None


def resource_advice() -> str:
    ram = total_ram_gib()
    if ram is None:
        return "Memory unavailable: use one VM at a time until measured."
    if ram < 11:
        return f"{ram:g} GiB host RAM: use one VM, about 2–3 GiB guest RAM; close heavy host apps."
    if ram < 20:
        return f"{ram:g} GiB host RAM: 1–2 modest VMs, monitor swap and host pressure."
    return f"{ram:g} GiB host RAM: multi-VM labs feasible; still reserve memory for the host."


def collect_checks(runner: Runner | None = None) -> list[Check]:
    runner = runner or Runner()
    checks = [Check("Linux host", platform.system() == "Linux", platform.platform())]
    checks.append(Check("KVM device", os.path.exists("/dev/kvm"), "/dev/kvm accessible" if os.access("/dev/kvm", os.R_OK | os.W_OK) else "Missing or insufficient permissions to /dev/kvm"))
    for binary in ["virsh", "virt-manager", "virt-viewer", "podman", "distrobox"]:
        loc = shutil.which(binary)
        checks.append(Check(binary, loc is not None, loc or "Not installed"))
    if shutil.which("virsh"):
        try:
            runner.run(["virsh", "--connect", "qemu:///system", "list", "--all", "--name"])
            checks.append(Check("libvirt connection", True, "Connected to qemu:///system"))
        except ToolError as exc:
            checks.append(Check("libvirt connection", False, str(exc)))
    return checks
