#!/usr/bin/env python3
"""Inspect a Nightglass offline test report, not an installer.

Read-only and offline. This validates structural consistency and the
declared commit, NOT that a test log is authentic or hardware is secure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

SCHEMA = "nightglass-offline-rc-gate-v2"
BRANCH = "deployment/readonly-backup-integrity"
CHECKS = (
    "windows_powershell_ast", "python_source_ast",
    "python_311", "python_312", "python_313", "fedora_43",
)
STATUSES = frozenset({"PASS", "FAIL", "BLOCKED", "NOT_RUN"})
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_REPORT_BYTES = 128 * 1024
MAX_LOG_BYTES = 32 * 1024 * 1024


class EvidenceError(ValueError):
    """Untrusted or internally contradictory local verification evidence."""


def reject_duplicates(items):
    result = {}
    for key, value in items:
        if key in result:
            raise EvidenceError("Duplicate JSON field")
        result[key] = value
    return result


def safe_file_bytes(path: Path, limit: int) -> bytes:
    """Read a regular file once; avoid path symlinks, directories and huge logs."""
    if path.is_symlink():
        raise EvidenceError("Evidence path cannot be a symbolic link")
    try:
        before = path.lstat()
    except OSError as exc:
        raise EvidenceError("Evidence file is missing or inaccessible") from exc
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise EvidenceError("Evidence must be a reasonably sized regular file")
    # O_NOFOLLOW closes a symlink-swap race on POSIX; Windows still
    # gets before/opened/after file-identity checks below.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        identity = stream.fileno()
        opened = os.fstat(identity)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
                before.st_dev, before.st_ino, before.st_size):
            raise EvidenceError("Evidence source changed before inspection")
        content = stream.read(limit + 1)
        after_read = os.fstat(identity)
    after = path.lstat()
    if len(content) > limit or len(content) != opened.st_size:
        raise EvidenceError("Evidence size changed or exceeds permitted limit")
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise EvidenceError("Evidence path changed while reading")
    if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            after_read.st_dev, after_read.st_ino, after_read.st_size, after_read.st_mtime_ns):
        raise EvidenceError("Evidence content changed while reading")
    return content


def read_report(path: Path) -> dict:
    try:
        document = json.loads(
            safe_file_bytes(path, MAX_REPORT_BYTES).decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                EvidenceError("Non-finite JSON numeric value is forbidden")),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("Report is not a valid UTF-8 JSON object") from exc
    if not isinstance(document, dict):
        raise EvidenceError("Report must be a JSON object")
    return document


def audit(data: dict, *, expected_commit: str, log_bytes: bytes | None) -> list[str]:
    """Return all blockers. An empty list is only a *synthetic* report PASS."""
    reasons = []
    if not SHA40.fullmatch(expected_commit):
        raise EvidenceError("Expected commit must be an exact lowercase 40-character SHA")
    if data.get("format") != SCHEMA:
        reasons.append("Report schema is missing, stale or unsupported")
    if data.get("branch") != BRANCH:
        reasons.append("Report branch does not match the audited candidate branch")
    sha = data.get("tested_commit")
    if not isinstance(sha, str) or not SHA40.fullmatch(sha) or sha != expected_commit:
        reasons.append("Exact tested Git commit does not match expected commit")
    checks = data.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(CHECKS):
        reasons.append("Mandatory check inventory is incomplete, unexpected or duplicated")
    else:
        for key in CHECKS:
            if not isinstance(checks[key], str) or checks[key] not in STATUSES:
                reasons.append("Invalid status for " + key)
            elif checks[key] != "PASS":
                reasons.append("Mandatory check not PASS: " + key)
    if type(data.get("test_gate_passed")) is not bool or data.get("test_gate_passed") is not True:
        reasons.append("Cumulative test gate is not explicitly PASS")
    if data.get("execution_error") is not None:
        reasons.append("Cumulative runner recorded an execution error")
    start = data.get("original_main_before")
    end = data.get("original_main_after")
    if not isinstance(start, str) or not SHA40.fullmatch(start):
        reasons.append("Original main before SHA is missing or invalid")
    if not isinstance(end, str) or not SHA40.fullmatch(end) or start != end:
        reasons.append("Original main branch changed or could not be verified")
    if data.get("physical_fedora_kvm_svirt_network_restore") != "NOT_TESTED":
        reasons.append("Physical Fedora status must remain explicitly NOT_TESTED")
    if data.get("windows11_clean_install_usb_formatter") != "NOT_RUN":
        reasons.append("Windows/USB deployment status must remain explicitly NOT_RUN")
    if data.get("github_pr_merge_or_actions") != "NOT_PERFORMED":
        reasons.append("GitHub merge/Actions status must remain explicitly NOT_PERFORMED")
    log_digest = data.get("local_log_sha256")
    if not isinstance(log_digest, str) or not SHA256.fullmatch(log_digest):
        reasons.append("Local test log digest is missing or invalid")
    elif log_bytes is None:
        reasons.append("Matching original test log was not provided for hash checking")
    elif hashlib.sha256(log_bytes).hexdigest() != log_digest:
        reasons.append("Local test log hash differs from the report")
    if data.get("deployment_approved") is not False:
        reasons.append("Deployment approval must explicitly remain FALSE")
    if data.get("release_attested") is not False:
        reasons.append("Security/release attestation must explicitly remain FALSE")
    if data.get("report_authentication") != "LOCAL_UNAUTHENTICATED":
        reasons.append("Report must disclose it is local, unauthenticated evidence")
    return reasons


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Nightglass offline test-evidence consistency checker")
    ap.add_argument("--report", required=True, type=Path,
                    help="Private JSON summary written by the Nightglass offline gate")
    ap.add_argument("--log", required=True, type=Path,
                    help="Original local full test log; used only to compare SHA-256")
    ap.add_argument("--expected-commit", required=True,
                    help="Exact 40-character Git SHA independently verified from the intended PR")
    args = ap.parse_args(argv)
    try:
        data = read_report(args.report)
        log = safe_file_bytes(args.log, MAX_LOG_BYTES)
        reasons = audit(data, expected_commit=args.expected_commit, log_bytes=log)
    except (EvidenceError, OSError) as exc:
        print("INCOMPLETE / REJECTED: " + type(exc).__name__, file=sys.stderr)
        return 2
    if reasons:
        print("INCOMPLETE / BLOCKED: " + str(len(reasons)) + " evidence issue(s)")
        for reason in reasons:
            print(" - " + reason)
        return 1
    print("SYNTHETIC LOCAL REPORT CONSISTENT with expected Git commit.")
    print("This is not trusted/cryptographic attestation of test execution.")
    print("NOT DEPLOYMENT READY: real Fedora KVM/sVirt, packet denial, rollback,")
    print("Windows 11 installation, official ISO provenance and physical security remain PENDING.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
