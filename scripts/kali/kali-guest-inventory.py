#!/usr/bin/env python3
"""Offline, read-only inventory for manual use inside an ALREADY-installed Kali VM.

Python standard library only. It does not install/update packages, start a
guest, invoke sudo, access network services, or modify system configuration.
Only a NEW private output JSON file is created. Not an attestation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

MAX_JSON_BYTES = 256 * 1024
PACKAGE = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
VERSION = re.compile(r"^[0-9][A-Za-z0-9.+~:_-]{0,127}$")
GUEST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
RELEASE = re.compile(r"^kali-[a-z0-9][a-z0-9.~-]{0,63}$")
FORMAT = "midnight-provisioner-kali-guest-inventory"


class InventoryError(Exception):
    pass


def _read_small_file(path: Path, limit: int = MAX_JSON_BYTES) -> str:
    if path.is_symlink():
        raise InventoryError("Refusing symlinked input")
    try:
        if not path.is_file() or not 0 < path.stat().st_size <= limit:
            raise InventoryError("Input file missing, empty or too large")
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise InventoryError("Oversized input")
        return data.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise InventoryError("Input unavailable or malformed") from exc


def read_plan(path: Path) -> tuple[str, tuple[str, ...]]:
    """Check core safety fields; host must independently check catalog digest."""
    try:
        plan = json.loads(_read_small_file(path))
    except ValueError as exc:
        raise InventoryError("Invalid setup plan JSON") from exc
    if (not isinstance(plan, dict) or
            plan.get("format") != "midnight-provisioner-kali-setup-plan" or
            type(plan.get("version")) is not int or plan["version"] != 1):
        raise InventoryError("Unsupported setup plan format/version")
    for key, value in (
        ("status", "PLANNED_ONLY"), ("initial_network", "none"),
        ("guest_policy", "lab"), ("separate_guest_disk_required", True),
        ("package_installation_performed", False),
        ("supply_chain_provenance_verified", False),
        ("guest_boot_observed", False), ("dependency_audit_performed", False),
    ):
        if plan.get(key) != value or type(plan.get(key)) is not type(value):
            raise InventoryError("Unsafe or modified planned-only policy fields")
    guest = plan.get("guest")
    packages = plan.get("packages")
    if (not isinstance(guest, str) or not GUEST.fullmatch(guest) or
            not isinstance(packages, list) or not 1 <= len(packages) <= 7 or
            any(not isinstance(p, str) or not PACKAGE.fullmatch(p) or
                p.startswith(("kali-linux-", "kali-tools-")) for p in packages) or
            len(set(packages)) != len(packages)):
        raise InventoryError("Unsafe guest or package list")
    versions = plan.get("package_versions")
    if (not isinstance(versions, dict) or set(versions) != set(packages) or
            any(value is not None for value in versions.values())):
        raise InventoryError("Package versions are not in planned-only state")
    return guest, tuple(packages)


def kali_release(path: Path = Path("/etc/os-release")) -> str:
    """Refuse other Linux distros rather than pretending a host is Kali."""
    fields = {}
    for row in _read_small_file(path, 8192).splitlines():
        if not row or row.startswith("#") or "=" not in row:
            continue
        key, value = row.split("=", 1)
        fields[key.strip()] = value.strip().strip('"').strip("'")
    if fields.get("ID") != "kali":
        raise InventoryError("Only run inside an intended Kali guest (ID=kali)")
    codename = fields.get("VERSION_CODENAME", "")
    release = codename if codename.startswith("kali-") else "kali-" + fields.get("VERSION_ID", "")
    if not RELEASE.fullmatch(release):
        raise InventoryError("Kali release identity unknown")
    return release


def _query(argv: list[str], timeout: int = 12) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "LC_ALL": "C", "DEBIAN_FRONTEND": "noninteractive"}
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, check=False,
            shell=False, timeout=timeout, env=env,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise InventoryError(f"Read-only local query unavailable: {argv[0]}") from exc


def package_versions(package: str) -> tuple[str | None, str | None]:
    if not PACKAGE.fullmatch(package):
        raise InventoryError("Invalid package name")
    # dpkg-query format escapes remain literal until interpreted by dpkg-query.
    fmt = "-f=" + "$" + r"{Status}\t" + "$" + r"{Version}\n"
    status = _query(["dpkg-query", "-W", fmt, "--", package])
    installed = None
    if status.returncode == 0:
        rows = [row for row in status.stdout.splitlines() if row.strip()]
        if len(rows) != 1:
            raise InventoryError("Unexpected dpkg-query output")
        fields = rows[0].split("\t")
        if len(fields) != 2:
            raise InventoryError("Malformed dpkg-query status")
        if fields[0] == "install ok installed":
            installed = fields[1].strip()
            if not VERSION.fullmatch(installed):
                raise InventoryError("Invalid installed Debian version")
    elif status.returncode != 1 or "no packages found matching" not in status.stderr.lower():
        raise InventoryError("dpkg-query failed; installed state UNKNOWN")

    candidate_query = _query(["apt-cache", "policy", package])
    if candidate_query.returncode != 0:
        raise InventoryError("apt-cache policy failed; candidate state UNKNOWN")
    matches = re.findall(r"(?m)^\s*Candidate:\s*(\S+)\s*$", candidate_query.stdout)
    if len(matches) != 1:
        raise InventoryError("Missing/ambiguous locally cached apt candidate")
    candidate = None if matches[0] == "(none)" else matches[0]
    if candidate is not None and not VERSION.fullmatch(candidate):
        raise InventoryError("Invalid candidate Debian version")
    return installed, candidate


def dpkg_audit() -> bool:
    result = _query(["dpkg", "--audit"], timeout=20)
    return result.returncode == 0 and not result.stdout.strip() and not result.stderr.strip()


def collect(plan_path: Path, release_file: Path = Path("/etc/os-release")) -> dict:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise InventoryError("Run under ordinary Kali desktop user, not root/sudo")
    guest, packages = read_plan(plan_path)
    release = kali_release(release_file)
    results = []
    for name in packages:
        installed, candidate = package_versions(name)
        results.append({
            "name": name, "installed_version": installed,
            "candidate_version": candidate,
        })
    return {
        "format": FORMAT, "version": 1, "guest": guest,
        "kali_release": release, "packages": results,
        "dpkg_audit_clean": dpkg_audit(),
    }


def save_new(document: dict, destination: Path) -> Path:
    target = Path(destination).expanduser()
    if target.exists() or target.is_symlink():
        raise InventoryError("Output already exists; refusing overwrite")
    try:
        parent = target.parent.resolve(strict=True)
    except OSError as exc:
        raise InventoryError("Output directory must already exist") from exc
    if not parent.is_dir() or target.suffix != ".json":
        raise InventoryError("Choose a NEW .json file in an existing directory")
    target = parent / target.name
    raw = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(raw) > MAX_JSON_BYTES:
        raise InventoryError("Inventory output too large")
    try:
        fd = os.open(
            target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
            getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    except OSError as exc:
        raise InventoryError("Could not safely create new inventory file") from exc
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline nonprivileged, self-reported Kali package inventory"
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        destination = save_new(collect(args.plan), args.output)
    except InventoryError as exc:
        print(f"Inventory unavailable: {exc}", file=sys.stderr)
        return 2
    print(f"New private guest inventory: {destination}")
    print("No installation/network activity. This JSON is not authenticated.")
    print("Transfer to the host only through a separately reviewed safe process.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
