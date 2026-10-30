"""Read-only Kali VM package drift against a previous self-reported version lock.

Checks one curated guest identity and a narrow package set. Does not query the
guest, apt, libvirt, network, host processes or external services. Reports are
about UNTRUSTED user-supplied metadata: not provenance or rollback evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from .kali_setup import (
    DEBIAN_VERSION, DIGEST, FORMAT_VERSION, KALI_RELEASE, LOCK_FORMAT,
    _canonical, _new_private_json, _read_bounded_json,
    compare_inventory, load_setup_plan, verify_setup_plan,
)
from .runner import ToolError

LOCK_KEYS = frozenset({
    "format", "version", "guest", "template_id", "catalog_digest",
    "kali_release", "claimed_installer_iso_sha256", "reported_installed_versions",
    "snapshot_sha256", "source", "apt_repository_signatures_verified",
    "dependency_closure_verified", "rollback_snapshot_verified", "status",
})


def verify_version_lock(plan: dict, record: dict) -> dict[str, str]:
    """Reject stale, cross-guest, fabricated or malformed lock claims."""
    verify_setup_plan(plan)
    if not isinstance(record, dict) or set(record) != LOCK_KEYS:
        raise ToolError("Malformed Kali version lock schema")
    if (record["format"] != LOCK_FORMAT or
            type(record["version"]) is not int or
            record["version"] != FORMAT_VERSION or
            record["status"] != "VERSION_SNAPSHOT_ONLY" or
            record["source"] != "UNTRUSTED_USER_EXPORTED_GUEST_JSON"):
        raise ToolError("Unsupported or misrepresented Kali version lock")
    for name in ("guest", "template_id", "catalog_digest"):
        expected = plan["guest"] if name == "guest" else (
            plan["template_id"] if name == "template_id" else plan["catalog_digest"]
        )
        if record[name] != expected:
            raise ToolError("Version lock is for a different guest, template or catalog revision")
    if record["claimed_installer_iso_sha256"] != plan["claimed_installer_iso_sha256"]:
        raise ToolError("Version lock ISO digest claim does not match setup plan")
    if not isinstance(record["kali_release"], str) or not KALI_RELEASE.fullmatch(record["kali_release"]):
        raise ToolError("Version lock Kali release is missing or malformed")
    if (not isinstance(record["snapshot_sha256"], str)
            or not DIGEST.fullmatch(record["snapshot_sha256"])):
        raise ToolError("Version lock inventory fingerprint is invalid")
    if any(record[key] is not False for key in (
        "apt_repository_signatures_verified", "dependency_closure_verified",
        "rollback_snapshot_verified",
    )):
        raise ToolError("Version lock wrongly claims verified provenance or rollback")
    versions = record["reported_installed_versions"]
    if not isinstance(versions, dict) or set(versions) != set(plan["packages"]):
        raise ToolError("Version lock package set differs from the curated template")
    if any(not isinstance(version, str) or not DEBIAN_VERSION.fullmatch(version)
           for version in versions.values()):
        raise ToolError("Version lock has an unknown or invalid installed version")
    return versions


@dataclass(frozen=True)
class KaliDriftReview:
    guest: str
    template_id: str
    baseline_release: str
    observed_release: str
    changed: tuple[tuple[str, str, str], ...]
    missing: tuple[str, ...]
    unavailable: tuple[str, ...]
    problems: tuple[str, ...]
    warnings: tuple[str, ...]
    baseline_fingerprint: str
    observation_fingerprint: str

    @property
    def unchanged(self) -> bool:
        return not (self.changed or self.missing or self.unavailable or self.problems)

    def describe(self) -> str:
        return "\n".join((
            "KALI GUEST PACKAGE DRIFT: " + (
                "NO REPORTED DRIFT (UNVERIFIED)" if self.unchanged
                else "DRIFT / UNVERIFIED — REVIEW REQUIRED"
            ),
            f"Guest: {self.guest} | template: {self.template_id}",
            f"Baseline release: {self.baseline_release} | current reported release: {self.observed_release}",
            *(f"VERSION CHANGE (DIRECTION UNKNOWN) {package}: {before} -> {after}"
              for package, before, after in self.changed),
            *(f"MISSING OR NOT INSTALLED {package}" for package in self.missing),
            *(f"CANDIDATE NOT REPORTED {package}" for package in self.unavailable),
            *(f"BLOCK {problem}" for problem in self.problems),
            *(f"REVIEW {warning}" for warning in self.warnings),
            "The two SHA-256 fingerprints identify supplied local JSON content,",
            "NOT an authenticated Kali VM, signed package, trusted origin or baseline.",
            "No apt query, guest command, libvirt operation, file transfer or network access occurred.",
        ))

    def evidence(self) -> dict:
        """Explicitly mark comparison as metadata-only, not an attestation."""
        return {
            "format": "midnight-provisioner-kali-drift-review", "version": FORMAT_VERSION,
            "guest": self.guest, "template_id": self.template_id,
            "baseline_release": self.baseline_release,
            "observed_release": self.observed_release,
            "reported_versions_unchanged": self.unchanged,
            "changed_versions_direction_unknown": [
                {"name": name, "baseline": before, "reported": after}
                for name, before, after in self.changed
            ],
            "missing_packages": list(self.missing),
            "missing_candidates": list(self.unavailable),
            "problems": list(self.problems), "warnings": list(self.warnings),
            "baseline_lock_json_sha256": self.baseline_fingerprint,
            "current_inventory_json_sha256": self.observation_fingerprint,
            "source": "UNTRUSTED_USER_SUPPLIED_METADATA",
            "authenticated_guest": False, "apt_signatures_verified": False,
            "dependency_closure_verified": False, "rollback_verified": False,
        }


def compare_version_lock(plan: dict, lock: dict, inventory: dict) -> KaliDriftReview:
    baseline_versions = verify_version_lock(plan, lock)
    current = compare_inventory(plan, inventory)
    problems = list(current.error)
    if current.kali_release != lock["kali_release"]:
        problems.append("Kali release changed or mismatches baseline")
    if inventory["dpkg_audit_clean"] is not True:
        problems.append("Current guest dpkg audit is not positively reported clean")
    reported = {
        row["name"]: row["installed_version"]
        for row in inventory["packages"] if row["name"] in baseline_versions
    }
    changed = tuple(
        (name, baseline_versions[name], reported[name])
        for name in plan["packages"]
        if name in reported and reported[name] is not None
        and reported[name] != baseline_versions[name]
    )
    missing = tuple(
        name for name in plan["packages"]
        if name not in reported or reported[name] is None
    )
    # Installed version strings don't support safe lexicographic
    # upgrading/downgrading classification. Treat every difference as drift.
    warnings = [
        "Guest inventory and baseline are user-supplied, not authenticated",
        "Changes are not classified as upgrades/downgrades; Debian version order is nontrivial",
        "No old apt candidate versions are captured in v1 locks; candidate changes cannot be compared",
        "SHA-256 detects byte changes only, not malicious fabrication or guest compromise",
    ]
    if current.upgrade_candidates:
        warnings.append("Current apt candidates differ from installed versions")
    return KaliDriftReview(
        guest=plan["guest"], template_id=plan["template_id"],
        baseline_release=lock["kali_release"],
        observed_release=current.kali_release, changed=changed,
        missing=missing, unavailable=current.unavailable,
        problems=tuple(dict.fromkeys(problems)), warnings=tuple(warnings),
        baseline_fingerprint=hashlib.sha256(_canonical(lock)).hexdigest(),
        observation_fingerprint=hashlib.sha256(_canonical(inventory)).hexdigest(),
    )


def compare_version_lock_files(
    plan_path: Path, lock_path: Path, inventory_path: Path,
) -> KaliDriftReview:
    """Parse bounded local JSON only, rejecting symlinked files; no VM access."""
    return compare_version_lock(
        load_setup_plan(plan_path),
        _read_bounded_json(lock_path),
        _read_bounded_json(inventory_path),
    )


def save_drift_review(report: KaliDriftReview, destination: Path) -> Path:
    return _new_private_json(destination, report.evidence())
