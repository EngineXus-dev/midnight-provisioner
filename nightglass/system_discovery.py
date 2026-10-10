"""First-run system reconnaissance for Nightglass.

Local-only, read-only detection for Windows preparation and Fedora desktop.
No storage device is chosen, declared empty, formatted, or mounted here.
Every uncertain result is held for a human decision. Directory names are
inspected only with an explicit opt-in, and never automatically exported.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
from typing import Any

SCHEMA = "nightglass.system-discovery.v1"
MAX_COMMAND_BYTES = 65536
MAX_DISKS = 32
MAX_FOLDER_NODES = 600
DISK_NAME = re.compile(r"^[a-zA-Z0-9_.-]{1,48}$")
PRIVATE_DIRS = frozenset((".git", ".venv", ".ssh", "appdata", ".cache", "node_modules",
                          "secrets", "credentials", "recoverykeys", "bitlocker"))

# Read-only fixed shell commands. No operator input goes into a command.
WINDOWS_QUERY = (
    "$ErrorActionPreference='Stop'; "
    "$d=@(Get-Disk | Select-Object Number,Size,PartitionStyle,IsBoot,IsSystem,IsReadOnly,BusType); "
    "$p=@(Get-Partition | Select-Object DiskNumber,DriveLetter); "
    "@{disks=$d;partitions=$p}|ConvertTo-Json -Compress -Depth 4"
)
LINUX_QUERY = ("lsblk", "-J", "-b", "-o",
               "NAME,TYPE,SIZE,RM,RO,TRAN,MOUNTPOINTS")


def _run_fixed(args: tuple[str, ...], *, limit: int = MAX_COMMAND_BYTES) -> dict | None:
    try:
        completed = subprocess.run(
            args, shell=False, capture_output=True, timeout=7, check=False,
        )
        if (completed.returncode != 0 or not completed.stdout
                or len(completed.stdout) > limit):
            return None
        data = json.loads(completed.stdout.decode("utf-8-sig", errors="strict"))
        return data if isinstance(data, dict) else None
    except (OSError, subprocess.TimeoutExpired, UnicodeError, ValueError):
        return None


def _safe_size(value: Any) -> int | None:
    # Refuse bool-as-int and nonsense sizes: unknown instead of inference.
    if type(value) is int and 0 < value <= 1 << 65:
        return value
    return None


def _gib(size: int | None) -> int | None:
    return round(size / 1024**3) if size is not None else None


def _bool(value: Any) -> bool | None:
    if type(value) is bool:
        return value
    if value in (0, 1) and type(value) is int:
        return bool(value)
    return None


def _label(value: Any) -> str:
    if isinstance(value, str) and DISK_NAME.fullmatch(value):
        return value
    return "UNKNOWN"


def _linux_mounts(device: dict) -> bool:
    mounts = device.get("mountpoints")
    if isinstance(mounts, list) and any(isinstance(m, str) and m for m in mounts):
        return True
    return any(_linux_mounts(c) for c in device.get("children", [])
               if isinstance(c, dict)) if isinstance(device.get("children", []), list) else False


def linux_storage(raw: dict | None) -> list[dict]:
    if not isinstance(raw, dict) or not isinstance(raw.get("blockdevices"), list):
        return []
    candidates = raw["blockdevices"]
    if len(candidates) > 256:
        return []
    results = []
    for item in candidates:
        if not isinstance(item, dict) or item.get("type") != "disk":
            continue
        if len(results) >= MAX_DISKS:
            return []
        mounted = _linux_mounts(item)
        removable = _bool(item.get("rm"))
        readonly = _bool(item.get("ro"))
        children = item.get("children")
        child_count = len(children) if isinstance(children, list) else None
        results.append({
            "local_id": _label(item.get("name")),
            "size_gib_approx": _gib(_safe_size(item.get("size"))),
            "bus": _label(str(item.get("tran") or "UNKNOWN")),
            "partition_count_observed": child_count,
            "removable": removable,
            "read_only": readonly,
            "system_use_evidence": "MOUNTED_PARTITION_FOUND" if mounted else "NOT_ESTABLISHED",
            "target_classification": "PROTECTED_IN_USE" if mounted else "UNVERIFIED_NOT_EMPTY_PROVEN",
        })
    return results


def windows_storage(raw: dict | None) -> list[dict]:
    if not isinstance(raw, dict):
        return []
    disks = raw.get("disks", [])
    partitions = raw.get("partitions", [])
    if not isinstance(disks, list) or not isinstance(partitions, list):
        return []
    if len(disks) > MAX_DISKS or len(partitions) > 256:
        return []
    counts: dict[int, int] = {}
    for part in partitions:
        if isinstance(part, dict) and type(part.get("DiskNumber")) is int:
            n = part["DiskNumber"]
            counts[n] = counts.get(n, 0) + 1
    out = []
    for disk in disks:
        if not isinstance(disk, dict) or type(disk.get("Number")) is not int:
            return []
        n = disk["Number"]
        is_boot = _bool(disk.get("IsBoot"))
        is_system = _bool(disk.get("IsSystem"))
        protected = is_boot is True or is_system is True
        out.append({
            "local_id": "Disk " + str(n) if 0 <= n < 1024 else "UNKNOWN",
            "size_gib_approx": _gib(_safe_size(disk.get("Size"))),
            "bus": _label(str(disk.get("BusType") or "UNKNOWN")),
            "partition_count_observed": counts.get(n),  # not proof of emptiness
            "removable": None,  # BusType never proves this reliably.
            "read_only": _bool(disk.get("IsReadOnly")),
            "system_use_evidence": "WINDOWS_BOOT_OR_SYSTEM" if protected else "NOT_ESTABLISHED",
            "target_classification": "PROTECTED_IN_USE" if protected else "UNVERIFIED_NOT_EMPTY_PROVEN",
        })
    return out


def _roots_for_user(home: Path) -> list[tuple[str, Path]]:
    return [(label, home / label) for label in
            ("Desktop", "Documents", "Downloads", "Pictures", "Videos")]


def _safe_dir(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    reparse = bool(getattr(info, "st_file_attributes", 0) &
                   getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    return stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and not reparse


def folder_summary(*, include_names: bool = False, home: Path | None = None) -> list[dict]:
    """Never read file bytes. Opt-in names are bounded to two levels.

    Omit full absolute paths, sensitive/private dot directories, files and
    file names. Scans are local-only. No links/reparse points are followed.
    """
    home = home or Path.home()
    results = []
    budget = MAX_FOLDER_NODES
    for label, root in _roots_for_user(home):
        available = _safe_dir(root)
        row: dict[str, Any] = {"category": label, "exists": available,
                               "names_scan": "NOT_REQUESTED"}
        if include_names and available:
            found = []
            pending: list[tuple[Path, str, int]] = [(root, "", 0)]
            while pending and budget > 0:
                location, prefix, depth = pending.pop()
                try:
                    with os.scandir(location) as it:
                        children = sorted(
                            (entry for entry in it if entry.is_dir(follow_symlinks=False)),
                            key=lambda d: d.name.casefold(),
                        )
                except OSError:
                    row["names_scan"] = "INCOMPLETE"
                    break
                for child in children:
                    if budget <= 0:
                        break
                    budget -= 1
                    if child.name.casefold() in PRIVATE_DIRS or child.name.startswith("."):
                        continue
                    path = Path(child.path)
                    if not _safe_dir(path):
                        continue
                    rel = prefix + child.name
                    if len(rel) > 160:
                        continue
                    found.append(rel)
                    if depth < 1:
                        pending.append((path, rel + "/", depth + 1))
                else:
                    continue
                row["names_scan"] = "TRUNCATED"
                break
            else:
                if row["names_scan"] != "INCOMPLETE":
                    row["names_scan"] = "COMPLETE"
            if budget <= 0:
                row["names_scan"] = "TRUNCATED"
            row["directory_names"] = found[:MAX_FOLDER_NODES]
        results.append(row)
    return results


def collect_system(*, include_folder_names: bool = False,
                   system: str | None = None,
                   storage_data: dict | None = None,
                   run_live: bool = True,
                   home: Path | None = None) -> dict:
    """Return a bounded, non-authorizing observation snapshot.

    For tests, run_live=False and inject storage_data. A missing storage
    query NEVER becomes 'no disks' or 'empty disk'.
    """
    system = system or platform.system()
    if system not in ("Windows", "Linux"):
        system = "UNKNOWN"
    cpu = os.cpu_count()
    try:
        from .diagnostics import total_ram_gib
        ram = total_ram_gib()  # None on unsupported hosts
    except (OSError, ValueError):
        ram = None
    if ram is not None and not 0 < ram < 65536:
        ram = None
    if run_live:
        if system == "Windows":
            storage_data = _run_fixed(
                ("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", WINDOWS_QUERY)
            )
        elif system == "Linux":
            storage_data = _run_fixed(LINUX_QUERY)
        else:
            storage_data = None
    storage = (windows_storage(storage_data) if system == "Windows"
               else linux_storage(storage_data) if system == "Linux" else [])
    return {
        "schema": SCHEMA,
        "read_only": True,
        "host_family": system,
        "host_ram_gib_approx": round(ram, 1) if ram is not None else None,
        "logical_cpu_count": cpu if type(cpu) is int and 0 < cpu <= 4096 else None,
        "storage_query": "OBSERVED" if storage_data is not None and storage else "UNKNOWN",
        "disks": storage,
        "personal_folders": folder_summary(include_names=include_folder_names, home=home),
        "folder_names_opted_in": bool(include_folder_names),
        "setup_intent": "UNDECIDED",
        "install_target_confirmed": False,
        "blank_drive_independently_verified": False,
        "backup_of_empty_target_required": "NOT_APPLICABLE_ONLY_AFTER_INDEPENDENT_EMPTY_DRIVE_PROOF",
        "other_drive_backup_scope_assessed": False,
        "installation_authorized": False,
        "partition_write_authorized": False,
        "usb_format_authorized": False,
        "firmware_change_authorized": False,
        "vm_start_authorized": False,
        "status": "HOLD_USER_REVIEW_ALL_UNKNOWN_DETAILS",
        "next_steps": [
            "Choose dedicated blank drive, coexist with existing OS, or undecided.",
            "Review physical target identification separately; no automatic disk selection.",
            "Uncertain partition, firmware, encryption and ownership checks require operator review.",
            "Only an independently confirmed truly blank dedicated target has no existing data to back up.",
            "Protect any OTHER drive or existing OS before changing EFI/boot or shared hardware.",
            "Installation and VM actions remain blocked until separate acceptance and consent.",
        ],
    }


def describe(report: dict) -> str:
    lines = [
        f"Host: {report['host_family']} | RAM: {report['host_ram_gib_approx']} GiB"
        f" | CPUs: {report['logical_cpu_count']}",
        "Storage discovery: " + report["storage_query"],
    ]
    for disk in report["disks"]:
        lines.append(
            f"{disk['local_id']}: ~{disk['size_gib_approx']} GiB / "
            f"{disk['bus']} / partitions observed={disk['partition_count_observed']} "
            f"/ {disk['target_classification']}"
        )
    if not report["disks"]:
        lines.append("NO TRUSTED DISK INVENTORY: not evidence that the machine has no disks.")
    lines.append("Personal folders: " + ", ".join(
        row["category"] + (" present" if row["exists"] else " not observed")
        for row in report["personal_folders"]
    ))
    lines.append("INTENT UNDECIDED; NO disk/OS/VM action authorized. Review uncertain facts manually.")
    return "\n".join(lines)
