"""Read-only binding of a separately installed Kali template to a COLD backup.

Verifies stored backup checksums, guest/UUID/device identity, independent
backup-file inode and native qcow2 metadata. Does not create backups, register,
start, change, or restore guests. Passing is NOT a tested recovery/rollback.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import stat
from xml.etree import ElementTree as ET

from .acceptance import save_acceptance
from .backups import verify_backup
from .hypervisor import Hypervisor, assess_domain
from .kali_registration import KaliRegistrationInspector, _safe_disk
from .kali_setup import load_setup_plan
from .readiness import inspect_image_metadata
from .runner import Runner, ToolError

GIB = 1024 ** 3


@dataclass(frozen=True)
class KaliColdBaseline:
    guest: str
    template_id: str
    checked_files: int
    backed_disk_gib: float | None
    problems: tuple[str, ...]
    warnings: tuple[str, ...]
    inventory_fingerprint: str | None

    @property
    def ok(self) -> bool:
        return not self.problems and self.checked_files >= 2 and self.backed_disk_gib is not None

    def describe(self) -> str:
        return "\n".join((
            "KALI COLD BASELINE: " + (
                "HASHES/DEFINITIONS MATCH (NOT RESTORE-PROVEN)" if self.ok
                else "BLOCKED / UNVERIFIED"
            ),
            f"Guest: {self.guest} | template: {self.template_id}",
            f"Backup assets checksum-checked: {self.checked_files}",
            ("Backup disk virtual capacity: "
             + (f"{self.backed_disk_gib:.2f} GiB" if self.backed_disk_gib is not None else "UNVERIFIED")),
            *(f"BLOCK {item}" for item in self.problems),
            *(f"CAUTION {item}" for item in self.warnings),
            "No guest, live VM disk, backup, network or EFI/NVRAM file was changed.",
            "A valid copy/hash proves consistency with a locally supplied manifest,",
            "NOT a trustworthy image, safe guest boot, or tested cold restoration.",
            "Rollback, network isolation, signed Kali packages and sVirt remain untested.",
        ))

    def evidence(self) -> dict:
        return {
            "format": "nightglass-kali-cold-baseline", "version": 1,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "guest": self.guest, "template_id": self.template_id,
            "backup_assets_checksum_checked": self.checked_files,
            "backup_virtual_disk_gib": self.backed_disk_gib,
            "backup_binding_checks_passed": self.ok,
            "backup_manifest_sha256": self.inventory_fingerprint,
            "problems": list(self.problems), "warnings": list(self.warnings),
            "backup_restoration_tested": False,
            "guest_boot_tested": False,
            "signed_package_provenance_verified": False,
            "guest_network_denial_verified": False,
            "SELinux_runtime_verified": False,
        }


def _xml_root(source: str, label: str, issues: list[str]) -> ET.Element | None:
    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        issues.append(f"{label}: invalid VM XML")
        return None
    if root.tag != "domain":
        issues.append(f"{label}: expected one domain XML")
        return None
    return root


def _disk_inventory(root: ET.Element, label: str, issues: list[str]) -> list[str]:
    disks: list[str] = []
    for node in root.findall("./devices/disk"):
        source = node.find("source")
        if node.get("device", "disk") == "cdrom":
            if source is not None and source.attrib:
                issues.append(f"{label}: backup has a mounted installer/ISO")
            continue
        if node.get("type") != "file" or node.get("device", "disk") != "disk":
            issues.append(f"{label}: unapproved archived disk backend or device")
            continue
        driver = node.find("driver")
        if driver is None or driver.get("name") != "qemu" or driver.get("type") != "qcow2":
            issues.append(f"{label}: backup disk driver is not explicitly qcow2")
        if node.find("backingStore") is not None:
            issues.append(f"{label}: unsupported backingStore chain")
        disks.append(source.get("file") if source is not None else None)
    return disks


class KaliColdBaselineInspector:
    def __init__(self, *,
                 hypervisor: Hypervisor | None = None,
                 runner: Runner | None = None,
                 registered: KaliRegistrationInspector | None = None):
        self.hypervisor = hypervisor or Hypervisor()
        self.runner = runner or Runner()
        self.registered = registered or KaliRegistrationInspector(
            hypervisor=self.hypervisor, runner=self.runner
        )

    def inspect(self, plan_path: Path, expected_disk: Path,
                backup_dir: Path) -> KaliColdBaseline:
        plan = load_setup_plan(Path(plan_path))
        guest = plan["guest"]
        disk = _safe_disk(Path(expected_disk))
        issues: list[str] = []
        warnings = [
            "The backup and its manifest are not cryptographically signed or authenticated",
            "A saved disk image can become stale after guest updates; changes to live data are not compared",
            "Another privileged process can change VM definitions/files after inspection",
            "Cold restore, firmware compatibility, guest boot and network denial require separate supervised tests",
        ]
        checked = 0
        virtual = None
        fingerprint = None

        registration = self.registered.inspect(Path(plan_path), disk)
        if not registration.ok:
            return KaliColdBaseline(
                guest, plan["template_id"], 0, None,
                ("Current offline Kali VM registration/disk audit is blocked",),
                tuple(warnings), None
            )

        directory = Path(backup_dir).expanduser()
        if any(part.is_symlink() for part in (directory, *directory.parents)):
            raise ToolError("Backup directory includes a symlink path component")
        try:
            directory = directory.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ToolError("Existing cold backup directory cannot be resolved") from exc

        # No manifest/XML contents or paths are trusted until all archived
        # assets have passed independent size, symlink and SHA-256 checks.
        checks = verify_backup(directory)
        checked = len(checks)
        manifest_path = directory / "manifest.json"
        raw_manifest = manifest_path.read_bytes()
        fingerprint = hashlib.sha256(raw_manifest).hexdigest()
        document = json.loads(raw_manifest)
        if document.get("domain") != guest:
            issues.append("Backup belongs to a different registered Kali VM")
        if document.get("policy") != "lab":
            issues.append("Backup does not use the restricted Kali lab policy")

        rows = document["files"]
        disks = [row for row in rows if row["kind"] == "disk"]
        nvram_rows = [row for row in rows if row["kind"] == "nvram"]
        if len(disks) != 1 or disks[0]["path"] != "disks/disk-01.qcow2":
            issues.append("Cold baseline must include exactly one independent qcow2 disk")
        elif disks[0].get("source") != str(disk):
            issues.append("Backed-up disk source differs from the selected registered Kali disk")
        if len(nvram_rows) > 1:
            issues.append("Cold baseline has multiple NVRAM copies")

        archive_xml = (directory / "domain.xml").read_text(encoding="utf-8")
        archived = _xml_root(archive_xml, "Archived definition", issues)
        current = None
        nextboot = None
        try:
            current = _xml_root(self.hypervisor._virsh("dumpxml", guest), "Registered definition", issues)
            nextboot = _xml_root(
                self.hypervisor._virsh("dumpxml", "--inactive", guest),
                "Next-boot definition", issues
            )
        except ToolError:
            issues.append("Cannot compare current and persistent registered Kali definitions")
        if archived is not None:
            if not assess_domain(archive_xml, "lab").ok:
                issues.append("Archived Kali definition violates restricted lab policy")
            if archived.find("./devices/interface") is not None:
                issues.append("Archived Kali baseline unexpectedly includes a network interface")

        identity_set: set[str] = set()
        nvram_paths: list[str | None] = []
        for label, root in (("Archived definition", archived),
                            ("Registered definition", current),
                            ("Next-boot definition", nextboot)):
            if root is None:
                continue
            if root.get("type") != "kvm" or root.findtext("name") != guest:
                issues.append(f"{label}: VM type/name does not match Kali setup plan")
            uuid = (root.findtext("uuid") or "").strip()
            if not uuid:
                issues.append(f"{label}: VM UUID is missing")
            else:
                identity_set.add(uuid)
            if root.find("./devices/interface") is not None:
                issues.append(f"{label}: network adapter must not be present")
            if _disk_inventory(root, label, issues) != [str(disk)]:
                issues.append(f"{label}: disk sources differ from chosen independent qcow2")
            nvram_paths.append((root.findtext("./os/nvram") or "").strip() or None)
        if len(identity_set) != 1 or len(nvram_paths) != 3:
            issues.append("Backup and registered guest UUID or XML definitions disagree")
        if len(set(nvram_paths)) != 1:
            issues.append("Backup NVRAM path differs from registered VM definitions")
        configured_nvram = nvram_paths[0] if nvram_paths else None
        if configured_nvram:
            if len(nvram_rows) != 1 or nvram_rows[0].get("source") != configured_nvram:
                issues.append("Kali UEFI NVRAM file has no matching verified cold copy")
        elif nvram_rows:
            issues.append("Unexpected NVRAM file in cold backup archive")

        backup_disk = directory / "disks/disk-01.qcow2"
        if not issues:
            # Hash passed before inspecting this ONLY known archived image.
            # Refuse hardlinks between backup and any other path (especially
            # the running guest's disk) to avoid illusory independent backups.
            old = backup_disk.stat()
            if old.st_nlink != 1 or (
                old.st_dev == disk.stat().st_dev and old.st_ino == disk.stat().st_ino
            ):
                issues.append("Backup qcow2 is hardlinked/shared, not an independent cold copy")
            else:
                try:
                    meta = inspect_image_metadata(self.runner, backup_disk, "qcow2")
                    virtual = meta["virtual-size"] / GIB
                    if abs(virtual - registration.virtual_disk_gib) > (1.0 / GIB):
                        issues.append("Backed-up disk virtual capacity differs from registered VM disk")
                except ToolError:
                    issues.append("Archived Kali qcow2 native metadata failed independent validation")
            try:
                new = backup_disk.stat()
                if (old.st_dev, old.st_ino, old.st_size, old.st_mtime_ns) != (
                    new.st_dev, new.st_ino, new.st_size, new.st_mtime_ns
                ) or new.st_nlink != 1:
                    issues.append("Backup disk changed while inspecting its metadata")
            except OSError:
                issues.append("Backup disk disappeared after its checksum was verified")

        if not issues:
            try:
                if self.hypervisor.state(guest).strip().lower() != "shut off":
                    issues.append("Registered Kali VM changed state during cold baseline audit")
            except ToolError:
                issues.append("Cannot reverify Kali guest shutdown state after cold baseline audit")
        if not issues and directory.stat().st_dev == disk.stat().st_dev:
            warnings.append(
                "Backup and live VM disk share a filesystem; loss of that volume may destroy both"
            )

        return KaliColdBaseline(
            guest, plan["template_id"], checked, virtual,
            tuple(dict.fromkeys(issues)), tuple(warnings), fingerprint
        )


def save_cold_baseline_report(report: KaliColdBaseline, destination: Path) -> Path:
    """Create NEW private local evidence only; never overwrite."""
    return save_acceptance(report, destination)
