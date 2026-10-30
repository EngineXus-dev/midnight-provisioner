"""New-name, new-directory *offline recovery staging* for Midnight Provisioner cold backups.

This module NEVER defines or starts a libvirt VM. It copies checksum-validated
backup assets into an exclusive new folder and generates a conservative
network-disconnected guest XML for a human to inspect before import.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from xml.etree import ElementTree as ET

from .backups import CHUNK_BYTES, MAX_DISKS, REL_PATH_RE, verify_backup
from .hypervisor import Hypervisor, assess_domain
from .models import safe_name
from .runner import ToolError
from .privatefiles import make_private

STAGING_FORMAT = "midnight-provisioner-recovery-staging"
STAGING_VERSION = 1


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _inventory(source: Path) -> tuple[dict, tuple[dict, ...]]:
    # Verify every backup asset before using its manifest or XML contents.
    verify_backup(source)
    try:
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(f"Cannot parse validated backup manifest: {exc}") from exc
    if manifest.get("policy") not in ("lab", "isolated"):
        raise ToolError("Recovery requires a restricted lab or offline analysis backup")
    rows = tuple(manifest["files"])
    if sum(row["kind"] == "xml" for row in rows) != 1:
        raise ToolError("Recovery requires exactly one domain XML definition")
    if not any(row["kind"] == "disk" for row in rows):
        raise ToolError("Recovery requires a virtual disk")
    return manifest, rows


def _recovery_xml(
    source: Path, rows: tuple[dict, ...], original: str, new_name: str, policy: str,
    target: Path,
) -> str:
    try:
        root = ET.parse(source / "domain.xml").getroot()
    except (OSError, ET.ParseError) as exc:
        raise ToolError(f"Backup XML is malformed: {exc}") from exc
    if root.tag != "domain" or root.findtext("name") != original:
        raise ToolError("Backup XML guest identity differs from the manifest")
    # Accept the original lab's named, non-forwarding virtual link only as
    # untrusted metadata. The staging XML always has *zero* NICs.
    # An archived XML definition must never be allowed to reference the
    # original host's direct-boot kernel/initrd or external disk layers.
    if any(root.find(f"./os/{tag}") is not None for tag in ("kernel", "initrd", "dtb")):
        raise ToolError("Backup includes external direct-boot files; manual recovery only")
    if policy == "isolated" and root.findall("./devices/interface"):
        raise ToolError("Offline analysis backup unexpectedly contains an interface")
    if policy == "lab":
        for interface in root.findall("./devices/interface"):
            entry = interface.find("source")
            if (interface.get("type") != "network" or entry is None or
                    entry.get("network") != "midnight-provisioner-lab"):
                raise ToolError("Lab backup contains an unapproved network interface")

    name_node = root.find("name")
    name_node.text = new_name
    # New restored guest must not inherit the source identity.
    for tag in ("uuid", "genid"):
        node = root.find(tag)
        if node is not None:
            root.remove(node)
    devices = root.find("devices")
    if devices is None:
        raise ToolError("Backup XML is missing guest devices")
    for interface in list(devices.findall("interface")):
        devices.remove(interface)
    # This is a generated *review* definition, not an automatically defined VM.
    # Its storage paths must refer exclusively to newly staged files.
    disk_rows = [row for row in rows if row["kind"] == "disk"]
    sources = {row["source"]: row for row in disk_rows}
    if len(sources) != len(disk_rows):
        raise ToolError("Backup manifest contains duplicate original disk sources")
    observed: set[str] = set()
    for disk in devices.findall("disk"):
        if disk.find("backingStore") is not None:
            raise ToolError("Recovery refuses layered disk XML and external backing stores")
        if disk.get("device", "disk") == "cdrom":
            if disk.find("source") is not None:
                raise ToolError("Backup XML still references external installer media")
            continue
        if disk.get("device", "disk") != "disk" or disk.get("type") != "file":
            raise ToolError("Backup has a disk outside the file-backed recovery policy")
        src = disk.find("source")
        if src is None or not src.get("file") or src.get("file") not in sources:
            raise ToolError("Backup disk sources do not match the verified manifest")
        original_path = src.get("file")
        if original_path in observed:
            raise ToolError("Backup reuses the same original disk more than once")
        observed.add(original_path)
        src.set("file", str(target / sources[original_path]["path"]))
    if len(observed) != len(disk_rows):
        raise ToolError("Backup XML/manifest disk inventory mismatch")

    nvram_rows = [row for row in rows if row["kind"] == "nvram"]
    if len(nvram_rows) > 1:
        raise ToolError("Only one UEFI NVRAM image can be staged")
    nvram = root.find("./os/nvram")
    if nvram_rows:
        if nvram is None or not nvram.text or nvram.text.strip() != nvram_rows[0]["source"]:
            raise ToolError("UEFI NVRAM file differs from the backup manifest")
        nvram.text = str(target / nvram_rows[0]["path"])
    elif nvram is not None and (nvram.text or "").strip():
        raise ToolError("Backup XML references NVRAM missing from its manifest")

    staged = ET.tostring(root, encoding="unicode")
    # The strongest policy is enforced on the newly staged offline XML,
    # regardless of whether the original was an offline or lab VM.
    audit = assess_domain(staged, "isolated")
    if not audit.ok:
        raise ToolError("New offline guest XML fails Midnight Provisioner policy: " + "; ".join(audit.warnings))
    return staged + "\n"


@dataclass(frozen=True)
class RecoveryPlan:
    source: Path
    destination: Path
    new_name: str
    original_name: str
    original_policy: str
    assets: tuple[dict, ...]
    xml: str

    def describe(self) -> str:
        size = sum(asset["bytes"] for asset in self.assets if asset["kind"] != "xml")
        return "\n".join([
            f"Original: {self.original_name} ({self.original_policy})",
            f"New guest: {self.new_name}",
            f"Destination: {self.destination}",
            f"Assets to copy: {len(self.assets) - 1} | bytes: {size:,}",
            "Recovery staging is OFFLINE: every virtual network interface is removed.",
            "A NEW guest identity is generated; existing VM definitions are NEVER changed.",
            "New files only. No automatic virt-manager import, virsh define or VM start.",
            "UEFI firmware, SELinux, disk ownership and boot compatibility need manual review.",
            "Restoring or running a malware image may be dangerous: use an isolated host.",
        ])


class RecoveryStager:
    def __init__(self, hypervisor: Hypervisor | None = None):
        self.hypervisor = hypervisor or Hypervisor()

    def plan(self, source: Path, destination: Path, new_name: str) -> RecoveryPlan:
        new_name = safe_name(new_name)
        source = Path(source).expanduser()
        if source.is_symlink():
            raise ToolError("Symlinked backup directories are not accepted")
        try:
            source = source.resolve(strict=True)
        except OSError as exc:
            raise ToolError(f"Cannot access backup: {exc}") from exc
        if not source.is_dir():
            raise ToolError("Backup source must be a directory")
        manifest, rows = _inventory(source)
        if new_name == manifest["domain"]:
            raise ToolError("Use a NEW guest name to prevent accidental restoration over an existing VM")
        if new_name in self.hypervisor.list_domains():
            raise ToolError("A VM with the requested new name already exists")
        destination = Path(destination).expanduser()
        if destination.is_symlink() or destination.exists():
            raise ToolError("Recovery destination must be NEW and nonexistent")
        try:
            parent = destination.parent.resolve(strict=True)
        except OSError as exc:
            raise ToolError(f"Recovery destination parent does not exist: {exc}") from exc
        if not parent.is_dir() or not os.access(parent, os.W_OK):
            raise ToolError("Recovery destination parent is not a writable directory")
        destination = parent / destination.name
        if destination.name in ("", ".", "..") or _inside(destination, source):
            raise ToolError("Recovery cannot write inside the backup source")
        if destination.exists() or destination.is_symlink():
            raise ToolError("Recovery destination changed or already exists")
        xml = _recovery_xml(source, rows, manifest["domain"], new_name, manifest["policy"], destination)
        required = sum(row["bytes"] for row in rows if row["kind"] != "xml")
        if shutil.disk_usage(parent).free < required + 256 * 1024 * 1024:
            raise ToolError("Not enough free disk space, including 256 MiB safety reserve")
        return RecoveryPlan(source, destination, new_name, manifest["domain"], manifest["policy"], rows, xml)

    def stage(self, source: Path, destination: Path, new_name: str, *, confirmed: bool = False) -> Path:
        if not confirmed:
            raise ToolError("Recovery staging needs explicit confirmation")
        plan = self.plan(source, destination, new_name)
        try:
            plan.destination.mkdir(mode=0o700, exist_ok=False)
        except OSError as exc:
            raise ToolError(f"Cannot create fresh staging folder: {exc}") from exc
        incomplete = plan.destination / "INCOMPLETE"
        try:
            incomplete.write_text("Recovery staging interrupted; do not import.\n", encoding="utf-8")
            copied = []
            for asset in plan.assets:
                if asset["kind"] == "xml":
                    continue
                src = plan.source / asset["path"]
                if src.parent.is_symlink() or src.is_symlink():
                    raise ToolError("Backup source path changed into a symlink during staging")
                dst = plan.destination / asset["path"]
                dst.parent.mkdir(mode=0o700, exist_ok=True)
                digest = hashlib.sha256()
                count = 0
                # O_NOFOLLOW prevents final-component symlink swapping; the
                # source must remain a real regular file while opened.
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(src, flags)
                with os.fdopen(fd, "rb") as origin, dst.open("xb") as output:
                    if not stat.S_ISREG(os.fstat(origin.fileno()).st_mode):
                        raise ToolError("Backup source is no longer a regular file")
                    make_private(output.fileno())
                    for chunk in iter(lambda: origin.read(CHUNK_BYTES), b""):
                        output.write(chunk)
                        digest.update(chunk)
                        count += len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if count != asset["bytes"] or digest.hexdigest() != asset["sha256"]:
                    raise ToolError(f"Copied file no longer matches verified backup: {asset['path']}")
                copied.append({
                    "kind": asset["kind"], "path": asset["path"],
                    "bytes": count, "sha256": digest.hexdigest(),
                })
            xml_path = plan.destination / "domain.xml"
            with xml_path.open("x", encoding="utf-8") as output:
                make_private(output.fileno())
                output.write(plan.xml)
                output.flush()
                os.fsync(output.fileno())
            xml_bytes = xml_path.stat().st_size
            xml_hash = hashlib.sha256(xml_path.read_bytes()).hexdigest()
            copied.append({"kind": "xml", "path": "domain.xml",
                           "bytes": xml_bytes, "sha256": xml_hash})
            manifest = {
                "format": STAGING_FORMAT,
                "version": STAGING_VERSION,
                "guest": plan.new_name,
                "original_guest": plan.original_name,
                "original_policy": plan.original_policy,
                "network": "offline",
                "files": copied,
                "warning": "Not a defined VM; inspect XML, paths, SELinux and firmware before manual import.",
            }
            output_file = plan.destination / "recovery-manifest.json"
            with output_file.open("x", encoding="utf-8") as output:
                make_private(output.fileno())
                json.dump(manifest, output, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            # A complete staging folder is only promoted after every hash and
            # offline XML recheck has passed.
            verify_staging(plan.destination, allow_incomplete=True)
            incomplete.unlink()
        except (OSError, ValueError, ToolError) as exc:
            raise ToolError(
                f"Recovery staging INCOMPLETE at {plan.destination}; no source files or VM definitions changed: {exc}"
            ) from exc
        return plan.destination


def verify_staging(directory: Path, *, allow_incomplete: bool = False) -> list[str]:
    directory = Path(directory).expanduser()
    if directory.is_symlink() or not directory.is_dir():
        raise ToolError("Staging source must be a real directory")
    try:
        directory = directory.resolve(strict=True)
    except OSError as exc:
        raise ToolError(f"Cannot resolve staged recovery: {exc}") from exc
    if (directory / "INCOMPLETE").exists() and not allow_incomplete:
        raise ToolError("Recovery staging is INCOMPLETE and must not be imported")
    file = directory / "recovery-manifest.json"
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 1024 * 1024:
        raise ToolError("Missing or untrusted recovery staging manifest")
    try:
        record = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(f"Cannot parse staging manifest: {exc}") from exc
    if (not isinstance(record, dict) or record.get("format") != STAGING_FORMAT
            or record.get("version") != STAGING_VERSION or record.get("network") != "offline"):
        raise ToolError("Recovery staging format or offline policy is invalid")
    try:
        safe_name(record.get("guest"))
    except (ValueError, TypeError) as exc:
        raise ToolError("Invalid recovered guest name") from exc
    rows = record.get("files")
    if not isinstance(rows, list) or not 2 <= len(rows) <= MAX_DISKS + 2:
        raise ToolError("Staging manifest has an invalid file inventory")
    seen = set()
    disks, xml_entries = 0, 0
    reports = []
    for row in rows:
        if not isinstance(row, dict):
            raise ToolError("Invalid staging manifest row")
        name = row.get("path")
        kind = row.get("kind")
        if not isinstance(name, str) or not REL_PATH_RE.fullmatch(name):
            raise ToolError("Unsafe path in staging manifest")
        if name in seen or kind not in ("disk", "nvram", "xml"):
            raise ToolError("Duplicate or invalid staging asset")
        if ((kind == "disk") != name.startswith("disks/") or
                (kind == "nvram" and name != "firmware/nvram.bin") or
                (kind == "xml" and name != "domain.xml")):
            raise ToolError("Staging manifest path/kind mismatch")
        seen.add(name)
        disks += kind == "disk"
        xml_entries += kind == "xml"
        expected, size = row.get("sha256"), row.get("bytes")
        if (not isinstance(expected, str) or len(expected) != 64 or
                any(c not in "0123456789abcdef" for c in expected) or
                type(size) is not int or size < 0):
            raise ToolError("Invalid staging digest or file size")
        path = directory / name
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
            raise ToolError(f"Missing or symlinked staging file: {name}")
        digest = hashlib.sha256()
        total = 0
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
                    total += len(chunk)
                    digest.update(chunk)
        except OSError as exc:
            raise ToolError(f"Cannot verify {name}: {exc}") from exc
        if total != size or digest.hexdigest() != expected:
            raise ToolError(f"Staging integrity failure: {name}")
        reports.append(f"PASS {name}: {total:,} bytes")
    if not disks or xml_entries != 1:
        raise ToolError("Staging is missing guest disks or domain XML")
    try:
        root = ET.parse(directory / "domain.xml").getroot()
    except (OSError, ET.ParseError) as exc:
        raise ToolError(f"Invalid recovery guest XML: {exc}") from exc
    if root.findtext("name") != record["guest"]:
        raise ToolError("Recovered XML identity does not match staging manifest")
    if root.find("uuid") is not None or root.find("genid") is not None:
        raise ToolError("Recovered guest retains original identity")
    audit = assess_domain(ET.tostring(root, encoding="unicode"), "isolated")
    if not audit.ok:
        raise ToolError("Recovered guest violates offline policy: " + "; ".join(audit.warnings))
    # Prevent XML that points at an external disk or unrelated file.
    images = {str(directory / row["path"]) for row in rows if row["kind"] == "disk"}
    actual = []
    for disk in root.findall("./devices/disk"):
        if disk.get("device", "disk") == "cdrom":
            if disk.find("source") is not None:
                raise ToolError("Recovered XML retains an attached external ISO")
            continue
        src = disk.find("source")
        if disk.get("type") != "file" or src is None or not src.get("file"):
            raise ToolError("Recovered XML contains an unsupported disk")
        declared_path = src.get("file")
        # An XML driver is just as important as the QEMU image header:
        # incorrectly interpreting QCOW2 bytes as raw can be dangerous.
        driver = disk.find("driver")
        expected_format = declared_path.rsplit(".", 1)[-1]
        if (expected_format not in {"qcow2", "raw"} or driver is None or
                driver.get("name") != "qemu" or
                driver.get("type") != expected_format):
            raise ToolError("Staged XML disk driver format differs from its image extension")
        actual.append(declared_path)
    if len(actual) != len(images) or set(actual) != images:
        raise ToolError("Recovered guest disk paths differ from the staged manifest")
    if any(disk.find("backingStore") is not None for disk in root.findall("./devices/disk")):
        raise ToolError("Recovered guest XML has a prohibited backing chain")
    nvram_rows = [row for row in rows if row["kind"] == "nvram"]
    nvram = root.find("./os/nvram")
    if nvram_rows:
        if nvram is None or (nvram.text or "").strip() != str(directory / "firmware/nvram.bin"):
            raise ToolError("Recovered UEFI NVRAM path is wrong")
    elif nvram is not None and (nvram.text or "").strip():
        raise ToolError("Recovered XML references unbundled NVRAM")
    return reports
