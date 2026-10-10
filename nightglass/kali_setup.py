"""Private, versioned Kali template setup records — never guest execution.

Plans capture a curated package set and independent guest identity without
changing libvirt or installing software. Optional guest inventory is provided
by the user as a bounded JSON export: it is untrusted self-reported metadata,
NOT proof of packages, signed repositories or the installed guest state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .kali_templates import get_template, PACKAGE_NAME
from .models import safe_name
from .runner import ToolError

PLAN_FORMAT = "nightglass-kali-setup-plan"
INVENTORY_FORMAT = "nightglass-kali-guest-inventory"
LOCK_FORMAT = "nightglass-kali-version-lock"
FORMAT_VERSION = 1
MAX_JSON_BYTES = 256 * 1024
DIGEST = re.compile(r"^[0-9a-f]{64}$")
DEBIAN_VERSION = re.compile(r"^[0-9][A-Za-z0-9.+~:_-]{0,127}$")
KALI_RELEASE = re.compile(r"^kali-[a-z0-9][a-z0-9.~-]{0,63}$")


def guest_inventory_instructions(identifier: str) -> str:
    """Return manual, non-executable steps for one approved Kali guest."""
    template = get_template(identifier)
    return "\n".join((
        f"READ-ONLY KALI GUEST INVENTORY — {template.name}",
        f"Separate guest name: {template.default_name}",
        "1. On the host, generate and verify a NEW setup plan:",
        f"   nightglass templates export {template.identifier} /path/to/new-plan.json",
        "   nightglass templates verify /path/to/new-plan.json",
        "2. Only for a manually installed BENIGN Kali VM: arrange an independently",
        "   reviewed one-way transfer of the plan and the standalone source script",
        "   scripts/kali-guest-inventory.py into that VM.",
        "   Nightglass does NOT provide host/guest file sharing or transfer.",
        "3. As a normal user INSIDE Kali, with no network needed, run:",
        "   python3 kali-guest-inventory.py --plan new-plan.json --output NEW-inventory.json",
        "4. If a separately validated transfer back to the host is available:",
        "   nightglass templates compare /path/to/new-plan.json /path/to/NEW-inventory.json",
        "No package installs, apt update, VM start, networking or host writes are",
        "performed by the helper. The output is NOT authenticated, does not attest",
        "to installed package contents or prove signed Kali provenance.",
    ))


def _canonical(document: dict) -> bytes:
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")


def catalog_digest(identifier: str) -> str:
    """Detect a maintainer-side change in exact package and resource policy."""
    template = get_template(identifier)
    specification = {
        "identifier": template.identifier,
        "category": template.category,
        "name": template.name,
        "packages": list(template.packages),
        "ram_mib": template.ram_mib,
        "disk_gib": template.disk_gib,
        "vcpus": template.vcpus,
    }
    return hashlib.sha256(_canonical(specification)).hexdigest()


def build_setup_plan(
    identifier: str, *, guest: str | None = None, iso_sha256: str | None = None,
) -> dict:
    """Return pure plan data; an ISO digest is a CLAIM until verified elsewhere."""
    template = get_template(identifier)
    guest = safe_name(guest or template.default_name)
    if iso_sha256 is not None:
        if not isinstance(iso_sha256, str) or not DIGEST.fullmatch(iso_sha256.lower()):
            raise ToolError("ISO checksum must be 64 hexadecimal characters")
        iso_sha256 = iso_sha256.lower()
    return {
        "format": PLAN_FORMAT,
        "version": FORMAT_VERSION,
        "template_id": template.identifier,
        "catalog_digest": catalog_digest(identifier),
        "category": template.category,
        "guest": guest,
        "guest_policy": "lab",
        "initial_network": "none",
        "separate_guest_disk_required": True,
        "packages": list(template.packages),
        "suggested_resources": {
            "ram_mib": template.ram_mib, "vcpus": template.vcpus,
            "disk_gib": template.disk_gib,
        },
        "claimed_installer_iso_sha256": iso_sha256,
        "package_versions": {name: None for name in template.packages},
        "package_installation_performed": False,
        "guest_boot_observed": False,
        "dependency_audit_performed": False,
        "supply_chain_provenance_verified": False,
        "status": "PLANNED_ONLY",
    }


def _new_private_json(destination: Path, document: dict) -> Path:
    """Only create a NEW file; symlinks and overwrites are refused."""
    path = Path(destination).expanduser()
    if path.exists() or path.is_symlink():
        raise ToolError("Destination already exists; never overwrite a local file")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise ToolError(f"Destination parent unavailable: {exc}") from exc
    if not parent.is_dir():
        raise ToolError("Destination parent is not a directory")
    path = parent / path.name
    if path.exists() or path.is_symlink() or not path.name.endswith(".json"):
        raise ToolError("Choose a NEW .json filename; do not overwrite existing data")
    encoded = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if len(encoded.encode("utf-8")) > MAX_JSON_BYTES:
        raise ToolError("Report would exceed maximum safe size")
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
    except OSError as exc:
        raise ToolError(f"Could not create new local plan: {exc}") from exc
    return path


def save_setup_plan(document: dict, destination: Path) -> Path:
    verify_setup_plan(document)
    return _new_private_json(destination, document)


def _read_bounded_json(path: Path) -> dict:
    path = Path(path).expanduser()
    if path.is_symlink():
        raise ToolError("Symlinked JSON inputs are not accepted")
    try:
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_JSON_BYTES:
            raise ToolError("Missing, empty or oversized JSON document")
        with path.open("rb") as source:
            raw = source.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise ToolError("Oversized JSON document")
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ToolError(f"Unreadable JSON input: {exc}") from exc
    if not isinstance(document, dict):
        raise ToolError("JSON record must be an object")
    return document


def verify_setup_plan(document: dict) -> None:
    if not isinstance(document, dict):
        raise ToolError("Invalid Kali setup plan format")
    identifier = document.get("template_id")
    template = get_template(identifier)
    expected = build_setup_plan(
        template.identifier,
        guest=document.get("guest"),
        iso_sha256=document.get("claimed_installer_iso_sha256"),
    )
    # All fields are intentionally immutable: an edited package list or
    # falsified verification bool must not become a trusted setup plan.
    if document != expected:
        raise ToolError(
            "Kali template manifest differs from catalog, offline safety defaults, "
            "or the planned-only state; regenerate a NEW plan"
        )


def load_setup_plan(path: Path) -> dict:
    document = _read_bounded_json(path)
    verify_setup_plan(document)
    return document


@dataclass(frozen=True)
class InventoryComparison:
    guest: str
    template_id: str
    kali_release: str
    installed: tuple[tuple[str, str], ...]
    missing: tuple[str, ...]
    unavailable: tuple[str, ...]
    upgrade_candidates: tuple[str, ...]
    error: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.error and not self.missing and not self.unavailable

    def describe(self) -> str:
        return "\n".join((
            "KALI TEMPLATE INVENTORY: " + (
                "MATCHED (SELF-REPORTED ONLY)" if self.complete else "INCOMPLETE / DRIFT"
            ),
            f"Guest: {self.guest} | template: {self.template_id} | release: {self.kali_release}",
            f"Reported installed planned packages: {len(self.installed)}",
            *(f"INSTALLED (SELF-REPORTED) {name}={version}" for name, version in self.installed),
            *(f"MISSING {name}" for name in self.missing),
            *(f"NO CANDIDATE {name}" for name in self.unavailable),
            *(f"CANDIDATE DIFFERS {name}" for name in self.upgrade_candidates),
            *(f"BLOCK {msg}" for msg in self.error),
            *(f"REVIEW {msg}" for msg in self.warnings),
            "No packages were installed, guest commands executed, or VMs started.",
            "User-supplied JSON is NOT authenticated or proof of package provenance.",
            "Dependencies, apt signatures, VM baseline rollback and real guest state remain unverified.",
        ))


def compare_inventory(plan: dict, inventory: dict) -> InventoryComparison:
    verify_setup_plan(plan)
    if not isinstance(inventory, dict):
        raise ToolError("Invalid Kali inventory")
    if set(inventory) != {"format", "version", "guest", "kali_release", "packages", "dpkg_audit_clean"}:
        raise ToolError("Inventory schema has missing or unexpected fields")
    if inventory["format"] != INVENTORY_FORMAT or type(inventory["version"]) is not int or inventory["version"] != FORMAT_VERSION:
        raise ToolError("Unsupported Kali inventory format")
    if safe_name(inventory["guest"]) != plan["guest"]:
        raise ToolError("Inventory belongs to another VM; never cross-apply template evidence")
    release = inventory["kali_release"]
    if not isinstance(release, str) or not KALI_RELEASE.fullmatch(release):
        raise ToolError("Invalid or unidentified Kali distribution release")
    packages = inventory["packages"]
    if not isinstance(packages, list) or len(packages) > 512:
        raise ToolError("Invalid or oversized package inventory")
    observed = {}
    for item in packages:
        if not isinstance(item, dict) or set(item) != {"name", "installed_version", "candidate_version"}:
            raise ToolError("Invalid package inventory row")
        name = item["name"]
        if not isinstance(name, str) or not PACKAGE_NAME.fullmatch(name) or name in observed:
            raise ToolError("Invalid or duplicate package name in inventory")
        for field in ("installed_version", "candidate_version"):
            v = item[field]
            if v is not None and (not isinstance(v, str) or not DEBIAN_VERSION.fullmatch(v)):
                raise ToolError("Invalid package version syntax in inventory")
        observed[name] = item
    planned = set(plan["packages"])
    extras = sorted(set(observed) - planned)
    missing = sorted(planned - set(observed))
    unavailable, installed, upgrades = [], [], []
    for name in plan["packages"]:
        row = observed.get(name)
        if row is None:
            continue
        if row["candidate_version"] is None:
            unavailable.append(name)
        if row["installed_version"] is not None:
            installed.append((name, row["installed_version"]))
            if row["candidate_version"] is not None and row["installed_version"] != row["candidate_version"]:
                upgrades.append(name)
        else:
            missing.append(name)
    clean = inventory["dpkg_audit_clean"]
    if clean is not None and type(clean) is not bool:
        raise ToolError("dpkg audit field must be true, false or null")
    errors = []
    if extras:
        errors.append("Inventory contains packages outside this selected template: " + ", ".join(extras[:10]))
    if clean is False:
        errors.append("User reports dpkg audit problems in the guest")
    warnings = [
        "Package data is user-provided and not independently inspected inside the guest",
        "Candidate versions can change in rolling Kali repositories",
    ]
    if clean is None:
        warnings.append("No guest dpkg --audit evidence supplied")
    if upgrades:
        warnings.append("Candidate/installed package versions differ; decide manually whether to update")
    return InventoryComparison(
        plan["guest"], plan["template_id"], release, tuple(installed),
        tuple(dict.fromkeys(missing)), tuple(unavailable), tuple(upgrades),
        tuple(errors), tuple(warnings),
    )


def compare_inventory_files(plan_path: Path, inventory_path: Path) -> InventoryComparison:
    return compare_inventory(load_setup_plan(plan_path), _read_bounded_json(inventory_path))


def save_version_lock(
    plan_path: Path, inventory_path: Path, destination: Path,
) -> Path:
    """Freeze self-reported versions for later drift review — NOT proof of install."""
    plan = load_setup_plan(plan_path)
    inventory = _read_bounded_json(inventory_path)
    comparison = compare_inventory(plan, inventory)
    if not comparison.complete or len(comparison.installed) != len(plan["packages"]):
        raise ToolError("Refuse to lock missing, uninstalled or mismatched guest packages")
    if inventory["dpkg_audit_clean"] is not True:
        raise ToolError("Guest dpkg audit status is unverified or has errors")
    record = {
        "format": LOCK_FORMAT,
        "version": FORMAT_VERSION,
        "guest": comparison.guest,
        "template_id": comparison.template_id,
        "catalog_digest": plan["catalog_digest"],
        "kali_release": comparison.kali_release,
        "claimed_installer_iso_sha256": plan["claimed_installer_iso_sha256"],
        "reported_installed_versions": dict(comparison.installed),
        "snapshot_sha256": hashlib.sha256(_canonical(inventory)).hexdigest(),
        "source": "UNTRUSTED_USER_EXPORTED_GUEST_JSON",
        "apt_repository_signatures_verified": False,
        "dependency_closure_verified": False,
        "rollback_snapshot_verified": False,
        "status": "VERSION_SNAPSHOT_ONLY",
    }
    return _new_private_json(destination, record)
