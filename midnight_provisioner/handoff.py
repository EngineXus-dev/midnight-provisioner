"""Read-only handoff audit: verified recovery folder ↔ actual libvirt guest.

This *never* defines/starts a VM or opens unexpected registered disk sources.
It only reads the already-verified staging directory, native QEMU metadata of
those known files, and registered libvirt XML. Read-only checks are not
runtime isolation proof, and another privileged libvirt client can race them.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from .acceptance import RegisteredGuestAuditor, save_acceptance
from .hypervisor import Hypervisor
from .readiness import inspect_image_metadata
from .recovery import verify_staging
from .runner import Runner, ToolError


@dataclass(frozen=True)
class HandoffAudit:
    guest: str
    staged_disks: int
    definitions: tuple[str, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def describe(self) -> str:
        return "\n".join((
            "REGISTERED RECOVERY HANDOFF: " + ("PASS (METADATA ONLY)" if self.ok else "BLOCKED"),
            f"New guest: {self.guest}",
            f"Verified staged disk images: {self.staged_disks}",
            f"Registered definitions inspected: {', '.join(self.definitions)}",
            *(f"BLOCK {error}" for error in self.errors),
            *(f"REVIEW {warning}" for warning in self.warnings),
            "NO VM WAS DEFINED, STARTED, SHUT DOWN, IMPORTED, OR CHANGED.",
            "Matching paths and disk metadata do NOT prove guest boot, SELinux runtime",
            "enforcement, disk-content trustworthiness or actual network isolation.",
        ))

    def evidence(self) -> dict:
        """Keep local evidence free of absolute host storage paths."""
        return {
            "format": "midnight-provisioner-recovery-handoff",
            "version": 1,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "guest": self.guest,
            "staged_disk_count": self.staged_disks,
            "registered_definitions_inspected": list(self.definitions),
            "registered_metadata_matches_staging": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "observations_not_performed": [
                "guest-boot", "packet-level-network-denial", "SELinux-runtime-enforcement",
                "image-provenance", "hypervisor-escape-resistance", "recovery-rollback",
            ],
        }


def save_handoff(report: HandoffAudit, destination: Path) -> Path:
    """Reuse exclusive-create private evidence writer; never overwrite."""
    return save_acceptance(report, destination)


class RecoveryHandoff:
    def __init__(self, hypervisor: Hypervisor | None = None, runner: Runner | None = None):
        self.hypervisor = hypervisor or Hypervisor()
        self.runner = runner or Runner()

    def inspect(self, directory: Path) -> HandoffAudit:
        directory = Path(directory).expanduser()
        # All paths and digests must pass before any image metadata inspection
        # or native QEMU command sees a path.
        verify_staging(directory)
        if directory.is_symlink():
            raise ToolError("Symlinked recovery handoff folder is not supported")
        directory = directory.resolve(strict=True)
        manifest = json.loads(
            (directory / "recovery-manifest.json").read_text(encoding="utf-8")
        )
        guest = manifest["guest"]
        expected = {
            str(directory / item["path"]): item["path"].rsplit(".", 1)[-1]
            for item in manifest["files"] if item["kind"] == "disk"
        }
        expected_nvram = (
            str(directory / "firmware/nvram.bin")
            if any(item["kind"] == "nvram" for item in manifest["files"])
            else None
        )
        if not expected:
            raise ToolError("Recovery folder has no verified disk images")

        audit = RegisteredGuestAuditor(self.hypervisor).inspect(guest, "isolated")
        errors = list(audit.errors)
        if audit.state != "shut off":
            errors.append("Registered recovered guest must be shut off for offline handoff audit")
        if "Managed-save definition" in audit.documents:
            errors.append("Recovered guest has a managed-save state that could bypass its cold recovery")

        # Query the same three definitions that acceptance audited. These
        # commands read libvirt XML only and do not touch registered disk files.
        definitions = [
            ("Current definition", self.hypervisor._virsh("dumpxml", guest)),
            ("Inactive definition", self.hypervisor._virsh("dumpxml", "--inactive", guest)),
        ]
        saved_xml = self.hypervisor._managed_save_xml(guest)
        if saved_xml is not None:
            definitions.append(("Managed-save definition", saved_xml))

        identities = set()
        for label, xml in definitions:
            try:
                root = ET.fromstring(xml)
            except ET.ParseError:
                errors.append(f"{label}: malformed registered XML")
                continue
            if root.tag != "domain" or root.findtext("name") != guest:
                errors.append(f"{label}: registered guest identity mismatch")
            uuid = (root.findtext("uuid") or "").strip()
            if not uuid:
                errors.append(f"{label}: registered UUID is missing")
            else:
                identities.add(uuid)

            disks = root.findall("./devices/disk")
            actual: set[str] = set()
            for disk in disks:
                src = disk.find("source")
                source_path = src.get("file") if src is not None else None
                if disk.get("device", "disk") == "cdrom":
                    if src is not None and src.attrib:
                        errors.append(f"{label}: unexpected mounted ISO/CD-ROM source")
                    continue
                if disk.get("device", "disk") != "disk" or disk.get("type") != "file":
                    errors.append(f"{label}: unapproved registered disk device or source type")
                    continue
                if not source_path or source_path not in expected:
                    errors.append(f"{label}: disk source is outside verified staged recovery")
                    continue
                # Even a symlink to the correct digest-verified file must not
                # introduce a second, mutable or ambiguous disk source.
                if Path(source_path).is_symlink():
                    errors.append(f"{label}: symlinked registered disk source")
                if source_path in actual:
                    errors.append(f"{label}: duplicate disk source")
                actual.add(source_path)
                driver = disk.find("driver")
                if (driver is None or driver.get("name") != "qemu" or
                        driver.get("type") != expected[source_path]):
                    errors.append(f"{label}: QEMU disk driver format differs from staged image")
                backing = disk.find("backingStore")
                if backing is not None and (
                    backing.attrib or backing.find("source") is not None or
                    backing.find("backingStore") is not None
                ):
                    errors.append(f"{label}: unexpected registered disk backing chain")
            if actual != set(expected):
                errors.append(f"{label}: registered disk inventory differs from verified staging")

            nvram = root.find("./os/nvram")
            nvram_path = (nvram.text or "").strip() if nvram is not None else None
            if nvram_path != expected_nvram:
                errors.append(f"{label}: NVRAM path differs from staged recovery")
            if nvram_path and Path(nvram_path).is_symlink():
                errors.append(f"{label}: symlinked registered NVRAM")

            if any(root.find(f"./os/{tag}") is not None for tag in ("kernel", "initrd", "dtb")):
                errors.append(f"{label}: registered XML includes unapproved direct boot files")

        if len(identities) != 1:
            errors.append("Registered XML UUIDs disagree or are unavailable")

        # Never point QEMU at a path discovered in XML. Inspect ONLY known
        # verified staging files and compare actual header to declared format.
        if not errors:
            for source_path, expected_format in sorted(expected.items()):
                try:
                    inspect_image_metadata(
                        self.runner, Path(source_path), expected_format
                    )
                except ToolError as exc:
                    # Avoid exposing absolute host storage paths in exported
                    # reports (native tool output can contain them).
                    errors.append(
                        "Staged QEMU image metadata failed validation"
                        f" ({expected_format}): {type(exc).__name__}"
                    )
        # Recheck after native metadata reading, detecting accidental disk
        # changes in the meantime. This cannot eliminate all TOCTOU races.
        verify_staging(directory)

        warnings = [
            "Read-only XML comparison cannot prove effective libvirt/SELinux access controls",
            "A privileged process can change XML or disk files after inspection",
            "Staged hashes authenticate consistency, NOT trust in original image contents",
            "Only manual, supervised benign Fedora/KVM boot and packet tests establish runtime behavior",
        ]
        return HandoffAudit(
            guest, len(expected), tuple(label for label, _ in definitions),
            tuple(dict.fromkeys(errors)), tuple(warnings),
        )
