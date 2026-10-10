"""Bind a Kali template's verified cold backup to a distinct OFFLINE recovery stage.

All operations are READ-ONLY. Neither a guest nor a disk is created, copied,
registered, started or altered. The verified backup/staged manifests are local
untrusted self-consistency evidence, NOT signatures or successful restore proof.
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
from .kali_setup import load_setup_plan
from .recovery import _recovery_xml, verify_staging
from .runner import ToolError

KIND = "nightglass-kali-recovery-link"
FORMAT_VERSION = 1


def _strict_directory(value: Path, label: str) -> Path:
    path = Path(value).expanduser()
    if any(component.is_symlink() for component in (path, *path.parents)):
        raise ToolError(f"{label} includes a symlink path component")
    try:
        result = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ToolError(f"{label} is unavailable") from exc
    if not result.is_dir():
        raise ToolError(f"{label} must be an existing directory")
    return result


def _manifest(path: Path, name: str) -> tuple[dict, str]:
    data = (path / name).read_bytes()
    # Callers must have already completed verify_backup/verify_staging.
    parsed = json.loads(data)
    return parsed, hashlib.sha256(data).hexdigest()


def _assets(document: dict) -> dict[str, dict]:
    return {
        row["path"]: row
        for row in document["files"]
        if row["kind"] != "xml"
    }


def _disk_identity(path: Path) -> tuple[int, int, int, int, int]:
    """Never open a disk via XML; only inspect independently verified paths."""
    if path.is_symlink() or path.parent.is_symlink():
        raise ToolError("Recovery disk path became symlinked")
    details = path.stat()
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise ToolError("Recovery disk is not an independent regular one-link file")
    return (
        details.st_dev, details.st_ino, details.st_nlink,
        details.st_size, details.st_mtime_ns,
    )


@dataclass(frozen=True)
class KaliRecoveryLinkReport:
    original_guest: str
    recovered_guest: str
    template_id: str
    matched_assets: int
    backup_manifest_hash: str
    stage_manifest_hash: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors and self.matched_assets > 0

    def describe(self) -> str:
        return "\n".join((
            "KALI RECOVERY LINK: " + (
                "MATCHED (FILES/XML ONLY — NOT RESTORE-PROVEN)"
                if self.ok else "BLOCKED / UNVERIFIED"
            ),
            f"Original guest: {self.original_guest} | template: {self.template_id}",
            f"NEW offline guest: {self.recovered_guest}",
            f"Copied disk/NVRAM files matched: {self.matched_assets}",
            *(f"BLOCK {error}" for error in self.errors),
            *(f"REVIEW {warning}" for warning in self.warnings),
            "No guest was defined, started, imported, repaired or changed.",
            "No source disk, backup file, staged recovery file or network was modified.",
            "Matching hashes/definitions do NOT prove signed source authenticity,",
            "boot, SELinux confinement, packet denial or successful recovery.",
        ))

    def evidence(self) -> dict:
        return {
            "format": KIND,
            "version": FORMAT_VERSION,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "original_guest": self.original_guest,
            "recovered_guest": self.recovered_guest,
            "template_id": self.template_id,
            "matched_copy_assets": self.matched_assets,
            "backup_manifest_sha256": self.backup_manifest_hash,
            "recovery_manifest_sha256": self.stage_manifest_hash,
            "file_and_definition_binding_passed": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "guest_imported": False,
            "guest_boot_tested": False,
            "restore_tested": False,
            "packet_level_network_denial_tested": False,
            "selinux_runtime_tested": False,
            "publisher_authenticated": False,
        }


class KaliRecoveryLink:
    def inspect(
        self, plan_path: Path, backup_dir: Path, stage_dir: Path,
    ) -> KaliRecoveryLinkReport:
        plan = load_setup_plan(Path(plan_path))
        backup = _strict_directory(backup_dir, "Cold backup directory")
        stage = _strict_directory(stage_dir, "Recovered staging directory")
        if backup == stage or backup in stage.parents or stage in backup.parents:
            raise ToolError("Backup and staging directories must be separate, not nested")

        # Validate BOTH archives before trusting any metadata/path or XML.
        verify_backup(backup)
        verify_staging(stage)
        old, old_hash = _manifest(backup, "manifest.json")
        new, new_hash = _manifest(stage, "recovery-manifest.json")

        errors: list[str] = []
        warnings = [
            "The cold backup and staged manifests are untrusted, unsigned local records",
            "Copy/definition consistency does not prove an image can actually boot",
            "No libvirt registration, network tests, hardware acceptance or restore rehearsal occurred",
            "Privileged host processes can change files after this point-in-time check",
        ]
        if old.get("domain") != plan["guest"]:
            errors.append("Original backup guest differs from the selected Kali setup plan")
        if old.get("policy") != "lab":
            errors.append("Original Kali backup must use the restricted lab policy")
        if new.get("original_guest") != plan["guest"]:
            errors.append("Recovered staging source guest differs from the selected Kali plan")
        if new.get("original_policy") != "lab":
            errors.append("Recovered staging original policy is not lab")
        recovered = new["guest"]
        if recovered == plan["guest"]:
            errors.append("Restored VM must have a NEW identity, never the original name")
        if new.get("network") != "offline":
            errors.append("Restored VM must have no network interface")

        originals = _assets(old)
        copies = _assets(new)
        expected_asset = {"disks/disk-01.qcow2"}
        if set(originals) - {"firmware/nvram.bin"} != expected_asset:
            errors.append("Original Kali backup must contain exactly one qcow2 disk")
        if set(copies) != set(originals):
            errors.append("Recovery copy disk/NVRAM inventory differs from the original backup")
        matched = 0
        old_identities = {}
        new_identities = {}
        for name, item in originals.items():
            staged_item = copies.get(name)
            if staged_item is None:
                continue
            if (item["kind"], item["bytes"], item["sha256"]) != (
                staged_item["kind"], staged_item["bytes"], staged_item["sha256"]
            ):
                errors.append("Copied asset's kind/size/digest differs from the verified cold backup")
                continue
            origin = backup / name
            copied = stage / name
            try:
                old_identities[name] = _disk_identity(origin)
                new_identities[name] = _disk_identity(copied)
            except OSError as exc:
                errors.append("Verified disk/NVRAM copy became unavailable: " + type(exc).__name__)
                continue
            except ToolError as exc:
                errors.append(str(exc))
                continue
            if old_identities[name][:2] == new_identities[name][:2]:
                errors.append("Recovered asset shares an inode with the backup (not an independent copy)")
                continue
            matched += 1

        # A staged domain XML must be exactly what the conservative recovery
        # transformer would derive from the ORIGINAL checksum-verified XML.
        # This catches an added safe-looking (but unauthorized) device, changed
        # RAM, EFI path or other retained identity even when its staging
        # manifest hashes have been intentionally recomputed.
        if not errors:
            try:
                expected_xml = _recovery_xml(
                    backup, tuple(old["files"]), old["domain"],
                    recovered, old["policy"], stage,
                )
                actual_xml = (stage / "domain.xml").read_text(encoding="utf-8")
                if ET.canonicalize(expected_xml) != ET.canonicalize(actual_xml):
                    errors.append(
                        "Recovered XML differs from the exact restricted, offline transformed backup definition"
                    )
            except (ToolError, OSError, ET.ParseError, ValueError):
                errors.append("Cannot reconstruct expected safe recovery XML from cold backup")

        # Catch changes to the archive between digest verification and final
        # XML or inode observations. This is not a global filesystem lock.
        verify_backup(backup)
        verify_staging(stage)
        for name in old_identities:
            try:
                if (_disk_identity(backup / name) != old_identities[name]
                        or _disk_identity(stage / name) != new_identities[name]):
                    errors.append("Recovered disk/NVRAM inode metadata changed during inspection")
            except (ToolError, OSError):
                errors.append("Recovered disk/NVRAM became unsafe during inspection")

        return KaliRecoveryLinkReport(
            original_guest=plan["guest"], recovered_guest=recovered,
            template_id=plan["template_id"], matched_assets=matched,
            backup_manifest_hash=old_hash, stage_manifest_hash=new_hash,
            errors=tuple(dict.fromkeys(errors)), warnings=tuple(warnings),
        )


def save_kali_recovery_link(report: KaliRecoveryLinkReport, destination: Path) -> Path:
    """Private, new JSON report; never overwrite a user file."""
    return save_acceptance(report, destination)
