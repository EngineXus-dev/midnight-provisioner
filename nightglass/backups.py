"""Conservative cold VM backup creation, checksum validation, and manual restore notes.

A backup must never be confused with a libvirt internal snapshot, a managed-save
session or an automatic restore. Only offline, file-backed, non-layered guests
can be exported here. No live disk or VM definition is modified.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import shutil

from .hypervisor import Hypervisor
from .models import safe_name
from .runner import Runner, ToolError

BACKUP_VERSION = 1
MAX_DISKS = 8
CHUNK_BYTES = 4 * 1024 * 1024
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
REL_PATH_RE = re.compile(r"^(disks/disk-[0-9]{2}\.(qcow2|raw)|firmware/nvram\.bin|domain\.xml)$")
ALLOWED_FORMATS = {"qcow2", "raw"}


@dataclass(frozen=True)
class BackupAsset:
    source: Path
    relative_path: str
    kind: str
    size: int


@dataclass(frozen=True)
class BackupPlan:
    domain: str
    policy: str
    domain_xml: str
    assets: tuple[BackupAsset, ...]

    @property
    def estimated_bytes(self) -> int:
        return sum(asset.size for asset in self.assets)

    def describe(self) -> str:
        return "\n".join([
            f"Guest: {self.domain} ({self.policy})",
            "State: verified shut off, no managed-save session",
            f"Files: {len(self.assets)} | Bytes to copy: {self.estimated_bytes:,}",
            *(f"  {asset.relative_path} <- {asset.source} ({asset.size:,} bytes)" for asset in self.assets),
            "This is a cold backup, NOT a checkpoint or automatic restore.",
            "The backup destination should be on encrypted, independent storage.",
            "Guest configuration contains ORIGINAL machine-specific disk paths.",
            "Restore is manual and requires separate verification of boot, firmware and networking.",
        ])


def _regular_file(path_text: str) -> tuple[Path, int]:
    path = Path(path_text)
    if not path.is_absolute() or path.is_symlink():
        raise ToolError(f"Backup source must be an absolute, non-symlinked file: {path}")
    try:
        details = path.stat()
        if not stat.S_ISREG(details.st_mode):
            raise ToolError(f"Not a regular file: {path}")
        if not os.access(path, os.R_OK):
            raise ToolError(f"Cannot read VM storage as the current user: {path}")
        return path, details.st_size
    except OSError as exc:
        raise ToolError(f"Backup source cannot be inspected: {path}: {exc}") from exc


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK_BYTES), b""):
            count += len(block)
            digest.update(block)
    return count, digest.hexdigest()


class ColdBackup:
    def __init__(self, hypervisor: Hypervisor | None = None, runner: Runner | None = None):
        self.runner = runner or Runner()
        self.hypervisor = hypervisor or Hypervisor(self.runner)

    def plan(self, domain: str, policy: str) -> BackupPlan:
        domain = safe_name(domain)
        if policy not in {"lab", "isolated"}:
            raise ToolError("Cold backup requires a dedicated VM workspace policy")
        if domain not in self.hypervisor.list_domains():
            raise ToolError("VM is not defined")
        if self.hypervisor.state(domain).strip().lower() != "shut off":
            raise ToolError("Cold backup requires a fully shut-off VM (not paused or running)")
        saved_xml = self.hypervisor._managed_save_xml(domain)
        if saved_xml is not None:
            raise ToolError("VM has a managed-save memory image; shut down cleanly rather than copying an inconsistent session")
        audit = self.hypervisor.audit(domain, policy)
        if not audit.ok:
            raise ToolError("VM must pass Nightglass policy before backup: " + "; ".join(audit.warnings))
        # '--inactive' ensures the definition that would be used on the next boot.
        xml = self.hypervisor._virsh("dumpxml", "--inactive", domain)
        from xml.etree import ElementTree as ET
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise ToolError(f"VM XML cannot be parsed: {exc}") from exc
        if root.tag != "domain" or root.findtext("name") != domain:
            raise ToolError("Inactive VM definition identity mismatch")
        # The independent inactive definition must also satisfy the policy.
        from .hypervisor import assess_domain, ISOLATED_NETWORK
        netxml = None
        if policy == "lab" and root.find("./devices/interface") is not None:
            netxml = self.hypervisor._virsh("net-dumpxml", ISOLATED_NETWORK)
        check = assess_domain(xml, policy, netxml)
        if not check.ok:
            raise ToolError("Inactive VM definition violates policy: " + "; ".join(check.warnings))

        assets = []
        seen: set[Path] = set()
        disks = root.findall("./devices/disk")
        for item in disks:
            device = item.get("device", "disk")
            if device == "cdrom":
                if item.find("source") is not None:
                    raise ToolError("Detach installation ISO/CD-ROM before creating a cold backup")
                continue
            if device != "disk" or item.get("type") != "file":
                raise ToolError("Cold backup supports local file-backed virtual disks only")
            source = item.find("source")
            if source is None or not source.get("file"):
                raise ToolError("Virtual disk has no local source file")
            file_path, size = _regular_file(source.get("file"))
            if file_path in seen:
                raise ToolError("VM definition references a duplicate disk file")
            seen.add(file_path)
            if len(seen) > MAX_DISKS:
                raise ToolError("Too many VM disks for this safe backup workflow")
            info = self.runner.run(["qemu-img", "info", "--output=json", str(file_path)], timeout=40).stdout
            try:
                meta = json.loads(info)
            except ValueError as exc:
                raise ToolError("qemu-img did not return valid disk metadata") from exc
            format_name = meta.get("format")
            if format_name not in ALLOWED_FORMATS:
                raise ToolError(f"Unsupported disk format: {format_name}")
            driver = item.find("driver")
            if driver is not None and driver.get("type") not in (None, format_name):
                raise ToolError("Disk XML format and qemu-img format disagree")
            if any(meta.get(key) for key in ("backing-filename", "full-backing-filename", "backing-filename-format")):
                raise ToolError("Layered images/backing chains are not supported by this cold backup")
            relative = f"disks/disk-{len(assets)+1:02d}.{format_name}"
            assets.append(BackupAsset(file_path, relative, "disk", size))
        if not assets:
            raise ToolError("VM definition has no eligible persistent virtual disks")

        nvram_text = root.findtext("./os/nvram")
        if nvram_text:
            nvram_path, nvram_size = _regular_file(nvram_text.strip())
            if nvram_path in seen:
                raise ToolError("NVRAM source overlaps with a virtual disk")
            assets.append(BackupAsset(nvram_path, "firmware/nvram.bin", "nvram", nvram_size))
        if self.hypervisor.state(domain).strip().lower() != "shut off":
            raise ToolError("VM state changed while reviewing its storage; nothing copied")
        return BackupPlan(domain, policy, xml, tuple(assets))

    def create(self, domain: str, policy: str, destination: Path, *, confirmed: bool = False) -> Path:
        if not confirmed:
            raise ToolError("Backup creation requires explicit user confirmation")
        plan = self.plan(domain, policy)
        destination = Path(destination).expanduser()
        if destination.exists() or destination.is_symlink():
            raise ToolError("Backup destination must be a new, nonexistent folder; never overwrite")
        parent = destination.parent.resolve(strict=True)
        if not parent.is_dir() or not os.access(parent, os.W_OK):
            raise ToolError("Backup parent directory is missing or not writable")
        # Do not silently spill a large VM export onto an almost full volume.
        free = shutil.disk_usage(parent).free
        if free < plan.estimated_bytes + (256 * 1024 * 1024):
            raise ToolError("Backup destination has insufficient free space plus 256 MiB reserve")
        # Guard against source changes since the preview; still not a global
        # lock against other privileged programs changing the VM mid-copy.
        if self.hypervisor.state(plan.domain).strip().lower() != "shut off":
            raise ToolError("Guest is no longer shut off")
        try:
            destination.mkdir(mode=0o700, exist_ok=False)
        except OSError as exc:
            raise ToolError(f"Cannot create new backup directory: {exc}") from exc
        try:
            (destination / "INCOMPLETE").write_text(
                "Backup unfinished; do not restore from this directory.\n", encoding="utf-8"
            )
            written = []
            for asset in plan.assets:
                if self.hypervisor.state(plan.domain).strip().lower() != "shut off":
                    raise ToolError("Guest started during backup: export is INCOMPLETE")
                current, current_size = _regular_file(str(asset.source))
                if current != asset.source or current_size != asset.size:
                    raise ToolError("Guest disk changed since preflight: export is INCOMPLETE")
                target = destination / asset.relative_path
                target.parent.mkdir(mode=0o700, exist_ok=True)
                digest = hashlib.sha256()
                count = 0
                with asset.source.open("rb") as origin, target.open("xb") as output:
                    os.chmod(target, 0o600)
                    for block in iter(lambda: origin.read(CHUNK_BYTES), b""):
                        if self.hypervisor.state(plan.domain).strip().lower() != "shut off":
                            raise ToolError("Guest started during disk copy: export is INCOMPLETE")
                        output.write(block)
                        count += len(block)
                        digest.update(block)
                    output.flush()
                    os.fsync(output.fileno())
                if count != asset.size:
                    raise ToolError("Source disk changed during copy: export is INCOMPLETE")
                written.append({
                    "kind": asset.kind, "path": asset.relative_path,
                    "source": str(asset.source), "bytes": count, "sha256": digest.hexdigest()
                })
            xml_path = destination / "domain.xml"
            with xml_path.open("x", encoding="utf-8") as xmlout:
                xmlout.write(plan.domain_xml)
                xmlout.flush()
                os.fsync(xmlout.fileno())
            os.chmod(xml_path, 0o600)
            xml_bytes, xml_hash = _hash_file(xml_path)
            written.append({"kind": "xml", "path": "domain.xml", "bytes": xml_bytes, "sha256": xml_hash})
            if self.hypervisor.state(plan.domain).strip().lower() != "shut off":
                raise ToolError("Guest restarted during backup: export is INCOMPLETE")
            manifest = {
                "format": "nightglass-cold-backup", "version": BACKUP_VERSION,
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "domain": plan.domain, "policy": plan.policy,
                "files": written,
                "warning": "Manual restore only. XML source paths are host-specific; boot test required.",
            }
            with (destination / "manifest.json").open("x", encoding="utf-8") as output:
                json.dump(manifest, output, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.chmod(destination / "manifest.json", 0o600)
            (destination / "INCOMPLETE").unlink()
        except (OSError, ToolError) as exc:
            # Never remove unknown or partially copied files. User can inspect
            # an INCOMPLETE directory, then explicitly decide what to do.
            raise ToolError(
                f"Cold backup INCOMPLETE at {destination}. No VM files were modified: {exc}"
            ) from exc
        return destination


def verify_backup(directory: Path) -> list[str]:
    """Independently hash and validate an exported cold backup. Read-only."""
    directory = Path(directory).expanduser()
    if directory.is_symlink() or not directory.is_dir():
        raise ToolError("Backup must be a real directory")
    if (directory / "INCOMPLETE").exists():
        raise ToolError("Backup is marked INCOMPLETE; it is not safe to restore")
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > 1024 * 1024:
        raise ToolError("Missing, symlinked or oversized manifest")
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(f"Cannot read backup manifest: {exc}") from exc
    if not isinstance(document, dict) or document.get("format") != "nightglass-cold-backup" or document.get("version") != BACKUP_VERSION:
        raise ToolError("Unrecognized backup format/version")
    try:
        safe_name(document.get("domain"))
    except (ValueError, TypeError) as exc:
        raise ToolError("Backup domain identifier is invalid") from exc
    rows = document.get("files")
    if not isinstance(rows, list) or not 2 <= len(rows) <= MAX_DISKS + 2:
        raise ToolError("Manifest has an unexpected file inventory")
    seen: set[str] = set()
    output = []
    disk_count = 0
    xml_count = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ToolError("Invalid manifest entry")
        name = row.get("path")
        kind = row.get("kind")
        expected = row.get("sha256")
        size = row.get("bytes")
        if not isinstance(name, str) or not REL_PATH_RE.fullmatch(name) or name in seen:
            raise ToolError("Unsafe or duplicate path in manifest")
        if not isinstance(expected, str) or not DIGEST_RE.fullmatch(expected):
            raise ToolError("Invalid digest in manifest")
        if type(size) is not int or size < 0:
            raise ToolError("Invalid file size in manifest")
        if kind not in {"disk", "nvram", "xml"}:
            raise ToolError("Invalid file type in manifest")
        if (kind == "disk") != name.startswith("disks/"):
            raise ToolError("Manifest file type/path mismatch")
        if kind == "nvram" and name != "firmware/nvram.bin":
            raise ToolError("Manifest NVRAM path mismatch")
        if kind == "xml" and name != "domain.xml":
            raise ToolError("Manifest XML path mismatch")
        seen.add(name)
        disk_count += kind == "disk"
        xml_count += kind == "xml"
        path = directory / name
        if ((path.parent != directory and path.parent.is_symlink())
                or path.is_symlink() or not path.is_file()):
            raise ToolError(f"Missing or symlinked backup file: {name}")
        try:
            actual_bytes, actual_hash = _hash_file(path)
        except OSError as exc:
            raise ToolError(f"Cannot read {name}: {exc}") from exc
        if actual_bytes != size or actual_hash != expected:
            raise ToolError(f"Backup integrity FAILURE: {name} differs from its manifest")
        output.append(f"PASS {name}: {actual_bytes:,} bytes SHA-256 {actual_hash}")
    if disk_count == 0 or xml_count != 1:
        raise ToolError("Backup must contain at least one disk and one XML definition")
    return output
