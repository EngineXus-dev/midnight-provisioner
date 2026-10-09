"""Read-only Fedora/KVM pre-import verification for a staged Nightglass recovery.

Passing this inspection does NOT register, boot, repair, modify, or prove the
isolation of a guest. It checks actual host tooling and disk headers before a
human reviews and manually imports any restored VM.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
from xml.etree import ElementTree as ET

from .hypervisor import (
    Hypervisor, assess_domain, declared_guest_memory_gib,
)
from .portability import current_budget
from .recovery import verify_staging
from .runner import Runner, ToolError


@dataclass(frozen=True)
class ReadinessReport:
    directory: Path
    guest: str
    policy: str
    disks: int
    checks: tuple[str, ...]
    warnings: tuple[str, ...]

    def describe(self) -> str:
        return "\n".join([
            f"RECOVERY IMPORT PREFLIGHT PASSED — {self.guest}",
            f"Staging location: {self.directory}",
            "Network: DISCONNECTED — policy audit passed",
            f"Disk images inspected: {self.disks}",
            *(f"PASS {line}" for line in self.checks),
            *(f"REVIEW {line}" for line in self.warnings),
            "NO VM WAS DEFINED, STARTED, IMPORTED OR MODIFIED.",
            "Preflight is NOT evidence of a successful boot, safe malware containment,"
            " or hardware-equivalent compatibility.",
        ])


def inspect_image_metadata(runner: Runner, path: Path, expected_format: str) -> dict:
    """Read metadata from a local disk image without converting or repairing it.

    This validates a native QEMU response, not just a filename extension.
    The caller must separately validate the path and image file integrity.
    """
    if expected_format not in {"qcow2", "raw"}:
        raise ToolError("Unknown disk image format")
    data = runner.run(
        ["qemu-img", "info", "--output=json", str(path)], timeout=90
    ).stdout
    try:
        meta = json.loads(data)
    except (ValueError, TypeError) as exc:
        raise ToolError(f"Malformed qemu-img metadata for {path.name}") from exc
    if not isinstance(meta, dict):
        raise ToolError("qemu-img did not return a single disk metadata object")
    if meta.get("format") != expected_format:
        raise ToolError(f"Disk format mismatch for {path.name}")
    if any(meta.get(k) for k in (
        "backing-filename", "full-backing-filename", "backing-filename-format",
        "encrypted", "snapshots",
    )):
        raise ToolError(f"Layered, encrypted or snapshotted disk requires manual review: {path.name}")
    if type(meta.get("virtual-size")) is not int or meta["virtual-size"] <= 0:
        raise ToolError(f"Invalid virtual disk size reported by qemu-img: {path.name}")
    return meta


class RecoveryReadiness:
    """Read-only checks involving libvirt, virt-xml-validate and qemu-img."""

    def __init__(self, runner: Runner | None = None, hypervisor: Hypervisor | None = None):
        self.runner = runner or Runner()
        self.hypervisor = hypervisor or Hypervisor(self.runner)

    def check(self, directory: Path) -> ReadinessReport:
        directory = Path(directory).expanduser()
        if directory.is_symlink():
            raise ToolError("Symlinked recovery staging folders are not supported")
        try:
            directory = directory.resolve(strict=True)
        except OSError as exc:
            raise ToolError(f"Recovery folder is missing: {exc}") from exc

        # Enforce trusted in-memory path validation BEFORE passing filenames to
        # native utilities which must not inspect arbitrary manifest paths.
        reports = verify_staging(directory)
        if platform.system() != "Linux":
            raise ToolError("Host readiness requires Fedora/Linux")
        if not os.path.exists("/dev/kvm") or not os.access("/dev/kvm", os.R_OK | os.W_OK):
            raise ToolError("KVM access unavailable; do not run Nightglass as root to work around permissions")

        manifest = json.loads((directory / "recovery-manifest.json").read_text(encoding="utf-8"))
        guest = manifest["guest"]
        if guest in self.hypervisor.list_domains():
            raise ToolError(f"Guest name {guest} is already registered; never overwrite an existing domain")

        xmlfile = directory / "domain.xml"
        xml = ET.fromstring(xmlfile.read_text(encoding="utf-8"))
        if xml.get("type") != "kvm":
            raise ToolError("Recovery XML is not configured for KVM")
        audit = assess_domain(ET.tostring(xml, encoding="unicode"), "isolated")
        if not audit.ok:
            raise ToolError("Offline VM configuration failed re-audit: " + "; ".join(audit.warnings))

        # Validate local schema. Do NOT use 'virsh define --validate':
        # that command ALSO REGISTERS the VM and is not a read-only preflight.
        self.runner.run(["virt-xml-validate", str(xmlfile), "domain"], timeout=35)

        disks = 0
        for item in manifest["files"]:
            if item["kind"] != "disk":
                continue
            path = directory / item["path"]
            # Metadata reads are only performed after hash/path verification.
            expected_format = item["path"].rsplit(".", 1)[-1]
            inspect_image_metadata(self.runner, path, expected_format)
            disks += 1

        # Machine budgets are advisory readiness gates and do not rewrite a VM.
        budget = current_budget()
        try:
            desired_ram = declared_guest_memory_gib(ET.tostring(xml, encoding="unicode"))
        except (ValueError, TypeError) as exc:
            raise ToolError(f"Cannot verify proposed guest RAM: {exc}") from exc
        if desired_ram > budget.guest_ram_cap_gib:
            raise ToolError(
                f"Recovered guest RAM {desired_ram:g} GiB exceeds the "
                f"{budget.guest_ram_cap_gib:g} GiB machine profile cap. "
                "Keep this VM offline until the definition is reviewed and tuned."
            )

        # Device-listing without a guest attached is only a schema check; host
        # firmware, SELinux labels and runtime permissions are still uncertain.
        warnings = [
            "Firmware/UEFI loader and saved NVRAM may be incompatible with this host",
            "Disk ownership and Fedora SELinux contexts need manual inspection",
            "A dedicated test boot and independent network-denial check remain required",
        ]
        if xml.find("./devices/tpm") is not None:
            warnings.append("Guest TPM state was not included in the recovery backup")
        # Verify collision again after potentially slow hashing/schema checks.
        if guest in self.hypervisor.list_domains():
            raise ToolError("New VM name was registered during preflight; refusing to approve import")
        return ReadinessReport(
            directory, guest, "isolated", disks,
            tuple(reports) + (
                "libvirt domain XML schema",
                f"QEMU disk metadata and RAM budget ({desired_ram:g} GiB)",
                "unused VM name on qemu:///system",
            ),
            tuple(warnings),
        )
