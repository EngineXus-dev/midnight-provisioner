"""Non-privileged, read-only Fedora *host prerequisite* evidence.

This is NOT a VM/guest acceptance tool. It does not boot, define, connect to,
or modify guests. SELinux labels of live QEMU processes, host firewall policy,
packet isolation, restored VM boot and backup rollback remain PENDING.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys

from .host_posture import HostPosture, inspect_host_posture
from .runner import Runner, ToolError
from .privatefiles import make_private

_FORMAT = "midnight-provisioner-fedora-host-prerequisites"
_UNVERIFIED = (
    "kde-session-and-host-package-provenance",
    "live-qemu-and-disk-inode-selinux-contexts",
    "libvirt-svirt-effective-enforcement",
    "host-bridge-and-packet-level-network-denial",
    "benign-manually-supervised-guest-boot",
    "independent-cold-backup-restore-and-rollback",
    "guest-hardware-and-firmware-compatibility",
)


@dataclass(frozen=True)
class Gate:
    key: str
    status: str
    detail: str

    def __post_init__(self):
        if self.status not in {"PASS", "BLOCKED", "PENDING"}:
            raise ValueError("Unsupported host prerequisite status")


@dataclass(frozen=True)
class HostPrerequisites:
    gates: tuple[Gate, ...]
    fedora_release: str | None

    @property
    def prerequisites_met(self) -> bool:
        required = ("fedora-host", "ordinary-user", "selinux-enforcing",
                    "kvm-device", "read-only-native-tools", "system-libvirt-readonly")
        return (tuple(item.key for item in self.gates) == required
                and all(item.status == "PASS" for item in self.gates))

    def evidence(self) -> dict:
        """Export only fixed labels and low-sensitivity release number.

        No guest names, hostnames, usernames, PID, IP, paths, command output,
        QEMU labels/MCS categories or VM disk identifiers are serialized.
        """
        return {
            "format": _FORMAT,
            "version": 1,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "fedora_release": self.fedora_release,
            "host_prerequisites_met": self.prerequisites_met,
            "hardware_security_acceptance": "PENDING",
            "checks": [
                {"key": item.key, "status": item.status, "detail": item.detail}
                for item in self.gates
            ],
            "not_verified": list(_UNVERIFIED),
            "notice": "HOST PREREQUISITES ONLY: not permission to boot/import guests or handle malware.",
        }

    def describe(self) -> str:
        lines = [
            "MIDNIGHT_PROVISIONER FEDORA HOST PREREQUISITES — READ-ONLY",
            *(f"{gate.status:7s} {gate.key}: {gate.detail}" for gate in self.gates),
            "HOST PREREQUISITES: " + ("MET" if self.prerequisites_met else "BLOCKED"),
            "HARDWARE SECURITY ACCEPTANCE: PENDING (not a guest-isolation certification)",
            "No root, sudo, VM boot, VM definition or host configuration changes.",
            "Only an explicitly requested NEW private evidence report writes a file.",
        ]
        return "\n".join(lines)


def _release() -> tuple[bool, str | None]:
    if platform.system() != "Linux":
        return False, None
    try:
        data = platform.freedesktop_os_release()
    except (AttributeError, OSError, ValueError):
        return False, None
    if str(data.get("ID", "")).lower() != "fedora":
        return False, None
    version = str(data.get("VERSION_ID", ""))
    # Avoid exporting arbitrary untrusted os-release content.
    if not re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,3})?", version):
        return True, None
    return True, version


def inspect_prerequisites(*, runner: Runner | None = None, which=None,
                          posture: HostPosture | None = None) -> HostPrerequisites:
    """Use only fixed read-only host queries. Never invoke a VM operation."""
    runner = runner if runner is not None else Runner()
    which = which if which is not None else shutil.which
    is_fedora, version = _release()
    posture = posture if posture is not None else inspect_host_posture(runner=runner, which=which)
    current = {check.name: check for check in posture.checks}
    gates = [
        Gate("fedora-host", "PASS" if is_fedora else "BLOCKED",
             "Fedora Linux detected" if is_fedora else "Fedora Linux not verified"),
    ]
    for name, key, ok_detail, error_detail in (
        ("Privileges", "ordinary-user", "Unprivileged user verified", "Non-root execution not verified"),
        ("SELinux", "selinux-enforcing", "Host SELinux enforcing reported",
         "Host SELinux enforcing not verified"),
        ("KVM", "kvm-device", "KVM device accessible to user",
         "KVM access unavailable or unverified"),
    ):
        item = current.get(name)
        status = "PASS" if item is not None and item.status == "OK" else "BLOCKED"
        gates.append(Gate(key, status, ok_detail if status == "PASS" else error_detail))
    tools = ("virsh", "virt-xml-validate", "qemu-img")
    available = all(which(tool) for tool in tools)
    gates.append(Gate("read-only-native-tools", "PASS" if available else "BLOCKED",
                      "Required libvirt/QEMU validation utilities found" if available
                      else "Required libvirt/QEMU validation utilities missing"))
    libvirt_ok = False
    if is_fedora and gates[1].status == "PASS" and which("virsh"):
        try:
            # Whitelisted argv: this lists names into memory only. Names are
            # never printed or serialized to the report.
            runner.run(["virsh", "--connect", "qemu:///system",
                        "list", "--all", "--name"], timeout=12)
            libvirt_ok = True
        except ToolError:
            pass
    gates.append(Gate("system-libvirt-readonly", "PASS" if libvirt_ok else "BLOCKED",
                      "Non-root system libvirt read-only inventory query succeeded"
                      if libvirt_ok else "Non-root system libvirt query not verified"))
    return HostPrerequisites(tuple(gates), version)


def save_private_evidence(report: HostPrerequisites, destination: Path) -> None:
    """Opt-in exclusive-create JSON. No overwrites, implicit directories or backups."""
    path = Path(destination).expanduser()
    if path.name in ("", ".", "..") or not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("Use a new file in an existing nonsymlink directory")
    if path.is_symlink():
        raise ValueError("Refusing a symlinked evidence destination")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        make_private(stream.fileno())
        json.dump(report.evidence(), stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Fedora host prerequisite inspection")
    parser.add_argument("--report", type=Path, help="Write a NEW private JSON file (optional)")
    args = parser.parse_args(argv)
    report = inspect_prerequisites()
    print(report.describe())
    if args.report is not None:
        try:
            save_private_evidence(report, args.report)
        except (OSError, ValueError) as exc:
            # Avoid echoing paths/usernames possibly present in OS exception text.
            print(f"[BLOCKED] Evidence write failed ({type(exc).__name__}); no existing file overwritten.",
                  file=sys.stderr)
            return 2
        print("New private JSON evidence file created; keep it local.")
    return 0 if report.prerequisites_met else 1


if __name__ == "__main__":
    raise SystemExit(main())
