"""Nonprivileged Fedora host security posture inspection.

Read-only queries only: SELinux mode, KVM device permissions, system firewall
service state and host IP forwarding sysctls. Neither firewalld being active
nor a clean libvirt XML means packet-level isolation has been verified.

All unknown outcomes are explicitly UNKNOWN, never silently marked as safe.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shutil

from .runner import Runner, ToolError

KVM_DEVICE = Path("/dev/kvm")
SELINUX_ENFORCE = Path("/sys/fs/selinux/enforce")
IPV4_FORWARD = Path("/proc/sys/net/ipv4/ip_forward")
IPV6_FORWARD = Path("/proc/sys/net/ipv6/conf/all/forwarding")


@dataclass(frozen=True)
class PostureCheck:
    name: str
    status: str
    message: str

    def __post_init__(self):
        if self.status not in {"OK", "WARN", "UNKNOWN", "INFO"}:
            raise ValueError("Unsupported host posture check status")


@dataclass(frozen=True)
class HostPosture:
    checks: tuple[PostureCheck, ...]

    @property
    def blockers(self) -> tuple[PostureCheck, ...]:
        return tuple(ch for ch in self.checks if ch.status in {"WARN", "UNKNOWN"})

    @property
    def complete(self) -> bool:
        return not self.blockers

    def describe(self) -> str:
        return "\n".join((
            "HOST SECURITY POSTURE — READ-ONLY",
            *(f"{check.status:7s} {check.name}: {check.message}" for check in self.checks),
            "No configuration, firewall, libvirt domain, SELinux policy, or host disk was changed.",
            "INFO is not a security pass. Passing local checks CANNOT prove guest network denial,",
            "sVirt enforcement, host-guest separation, malware containment, or a successful VM boot.",
        ))


def _read_value(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        value = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError, ValueError):
        return None
    return value or None


def _selinux_mode(runner: Runner, which) -> PostureCheck:
    # Fedora normally exposes getenforce; /sys is an independent view of
    # kernel enforcement if the command is absent/unavailable.
    kernel = _read_value(SELINUX_ENFORCE)
    if kernel not in {None, "0", "1"}:
        return PostureCheck("SELinux", "UNKNOWN", "Invalid kernel enforcement state")
    state = None
    if which("getenforce"):
        try:
            state = runner.run(["getenforce"], timeout=6).stdout.strip()
        except ToolError:
            state = None
    if state not in {None, "Enforcing", "Permissive", "Disabled"}:
        return PostureCheck("SELinux", "UNKNOWN", "Unrecognized SELinux mode response")
    if state is not None and kernel is not None:
        expected = {"Enforcing": "1", "Permissive": "0", "Disabled": None}[state]
        if expected is not None and kernel != expected:
            return PostureCheck("SELinux", "UNKNOWN", "Conflicting SELinux command/kernel results")
    if state is None:
        state = {"1": "Enforcing", "0": "Permissive"}.get(kernel)
    if state == "Enforcing":
        return PostureCheck("SELinux", "OK", "Kernel enforcement is enabled (guest sVirt labels not proven)")
    if state in {"Permissive", "Disabled"}:
        return PostureCheck("SELinux", "WARN", f"{state} — not suitable for relying on mandatory host enforcement")
    return PostureCheck("SELinux", "UNKNOWN", "Could not verify SELinux enforcement")


def _forwarding(name: str, path: Path) -> PostureCheck:
    value = _read_value(path)
    if value == "0":
        return PostureCheck(name, "INFO", "Host routing flag off; guest network isolation is NOT established")
    if value == "1":
        return PostureCheck(name, "INFO", "Host forwarding enabled; review routes and firewall separately")
    return PostureCheck(name, "UNKNOWN", "Host forwarding state unavailable or malformed")


def inspect_host_posture(
    *, runner: Runner | None = None, which=None,
) -> HostPosture:
    """Never opens persistent state for writing or executes privileged commands."""
    runner = runner or Runner()
    which = which or shutil.which
    checks: list[PostureCheck] = []
    if platform.system() != "Linux":
        checks.append(PostureCheck("Platform", "WARN", "Midnight Provisioner host audit requires Linux"))
    else:
        checks.append(PostureCheck("Platform", "OK", "Linux host detected; Fedora-specific behavior not yet verified"))
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        checks.append(PostureCheck("Privileges", "WARN", "Running as root; use the ordinary desktop user"))
    else:
        checks.append(PostureCheck("Privileges", "OK", "Not running with root effective UID"))

    checks.append(_selinux_mode(runner, which))
    if KVM_DEVICE.is_symlink():
        checks.append(PostureCheck("KVM", "UNKNOWN", "KVM device is a symbolic link; inspect manually"))
    elif not KVM_DEVICE.exists():
        checks.append(PostureCheck("KVM", "WARN", "No /dev/kvm; hardware virtualization unavailable"))
    elif not KVM_DEVICE.is_char_device():
        checks.append(PostureCheck("KVM", "UNKNOWN", "/dev/kvm is not a character device"))
    elif not os.access(KVM_DEVICE, os.R_OK | os.W_OK):
        checks.append(PostureCheck("KVM", "WARN", "Cannot read/write /dev/kvm as this user; do not use sudo as workaround"))
    else:
        checks.append(PostureCheck("KVM", "OK", "Current user can access /dev/kvm (not proof of a working guest)"))

    if which("firewall-cmd"):
        try:
            # This queries the state of firewalld, not its zone/routing rules.
            state = runner.run(["firewall-cmd", "--state"], timeout=6).stdout.strip()
            if state == "running":
                checks.append(PostureCheck("firewalld", "INFO", "Daemon running; filtering of guest/host traffic NOT verified"))
            elif state == "not running":
                checks.append(PostureCheck("firewalld", "INFO", "Daemon stopped; inspect actual nftables policy separately"))
            else:
                checks.append(PostureCheck("firewalld", "UNKNOWN", "Unexpected firewall-cmd output"))
        except ToolError:
            checks.append(PostureCheck("firewalld", "UNKNOWN", "Daemon state could not be queried; other firewall backends may exist"))
    else:
        checks.append(PostureCheck("firewalld", "INFO", "firewall-cmd unavailable; no claim about other firewall rules"))

    checks.append(_forwarding("IPv4 forwarding", IPV4_FORWARD))
    checks.append(_forwarding("IPv6 forwarding", IPV6_FORWARD))
    return HostPosture(tuple(checks))
