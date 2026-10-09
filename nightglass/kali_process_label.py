"""Nonprivileged, READ-ONLY /proc QEMU SELinux label inspection on Fedora.

A running benign Kali recovery VM must already be started by the operator.
Verify a single QEMU process matches the current libvirt UUID AND guest name,
then compare /proc/PID/attr/current with the dynamic SELinux process label
reported by libvirt. Re-read process identity, start time, label, domain XML
and VM state to narrow PID-reuse/race windows. No sudo, ptrace, guest agent,
guest I/O, disk probing, subprocess calls or host config writes.

A /proc match is NOT cryptographic attestation; cmdlines can be spoofed and
privileged clients can modify VM state immediately after inspection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import re
import uuid
from xml.etree import ElementTree as ET

from .acceptance import save_acceptance
from .hypervisor import Hypervisor
from .kali_setup import load_setup_plan
from .models import safe_name
from .runtime_labels import PROCESS_LABEL, RuntimeLabelInspector
from .runner import ToolError

MAX_PROC_FILE = 65536
QEMU_EXECUTABLE = re.compile(r"^(?:qemu-system-[a-zA-Z0-9_-]+|qemu-kvm)$")


def _read_proc(path: Path) -> bytes:
    """Bound reads; never follow an explicitly symlinked PID component."""
    try:
        with path.open("rb") as file:
            data = file.read(MAX_PROC_FILE + 1)
    except (OSError, PermissionError) as exc:
        raise ToolError("QEMU /proc metadata unavailable to the current unprivileged user") from exc
    if len(data) > MAX_PROC_FILE:
        raise ToolError("QEMU /proc metadata exceeded bounded input limit")
    return data


def _start_time(pid_dir: Path) -> str:
    """Linux /proc/PID/stat field 22, accounting for parentheses in comm."""
    data = _read_proc(pid_dir / "stat").decode("utf-8", errors="replace").strip()
    idx = data.rfind(") ")
    if idx < 0 or data[:idx].split("(", 1)[0].strip() != pid_dir.name:
        raise ToolError("QEMU process stat identity could not be verified")
    fields = data[idx + 2:].split()
    if len(fields) < 20 or not fields[19].isdigit() or int(fields[19]) <= 0:
        raise ToolError("QEMU process start time could not be verified")
    return fields[19]


def _arguments(pid_dir: Path) -> list[str]:
    raw = _read_proc(pid_dir / "cmdline")
    if not raw.endswith(b"\0"):
        raise ToolError("QEMU process argv metadata is incomplete")
    try:
        return [arg.decode("utf-8") for arg in raw[:-1].split(b"\0")]
    except UnicodeError as exc:
        raise ToolError("QEMU process argv is not valid UTF-8") from exc


def _flag_value(args: list[str], flag: str) -> str | None:
    indexes = [i for i, part in enumerate(args) if part == flag]
    if len(indexes) != 1 or indexes[0] + 1 >= len(args):
        return None
    return args[indexes[0] + 1]


def _matches_qemu(args: list[str], guest: str, domain_uuid: str) -> bool:
    if not args or not QEMU_EXECUTABLE.fullmatch(os.path.basename(args[0])):
        return False
    candidate_uuid = _flag_value(args, "-uuid")
    name = _flag_value(args, "-name")
    if not candidate_uuid or not name:
        return False
    try:
        normalized = str(uuid.UUID(candidate_uuid))
    except (ValueError, AttributeError):
        return False
    return normalized == domain_uuid and name.split(",", 1)[0] == "guest=" + guest


def _domain_label(xml: str, guest: str) -> tuple[str, str]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ToolError("Cannot parse current registered QEMU guest XML") from exc
    if root.tag != "domain" or root.findtext("name") != guest:
        raise ToolError("Registered XML does not match the selected recovery guest")
    raw_uuid = (root.findtext("uuid") or "").strip()
    try:
        domain_uuid = str(uuid.UUID(raw_uuid))
    except ValueError as exc:
        raise ToolError("Registered guest UUID is missing or invalid") from exc
    labels = [x for x in root.findall("seclabel") if x.get("model") == "selinux"]
    if len(labels) != 1 or labels[0].get("type") != "dynamic" or labels[0].get("relabel") == "no":
        raise ToolError("Expected one dynamic libvirt SELinux process label")
    expected = (labels[0].findtext("label") or "").strip()
    if not PROCESS_LABEL.fullmatch(expected):
        raise ToolError("Libvirt did not expose a supported sVirt process label")
    return domain_uuid, expected


@dataclass(frozen=True)
class KaliProcessLabelReport:
    source_guest: str
    running_guest: str
    template_id: str
    inspected_matching_processes: int
    checks: tuple[str, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors and self.inspected_matching_processes == 1 and len(self.checks) >= 3

    def describe(self) -> str:
        return "\n".join((
            "KALI QEMU PROCESS LABEL: " + (
                "MATCHED (READ-ONLY /PROC OBSERVATION)" if self.ok
                else "BLOCKED / UNVERIFIED"
            ),
            f"Original profile guest: {self.source_guest} | template: {self.template_id}",
            f"Already-running recovery guest: {self.running_guest}",
            "Matching QEMU processes (count only): " + str(self.inspected_matching_processes),
            *(f"OBSERVED {msg}" for msg in self.checks),
            *(f"BLOCK {msg}" for msg in self.errors),
            *(f"REVIEW {msg}" for msg in self.warnings),
            "No PID, raw process command line, SELinux MCS categories or host file paths exported.",
            "No VM started or changed; no sudo, ptrace, guest access, guest disk I/O or network tests.",
            "OS boot, on-disk SELinux contexts, network packet denial and successful restore",
            "remain UNVERIFIED. Process argv matching is not cryptographic authentication.",
        ))

    def evidence(self) -> dict:
        return {
            "format": "nightglass-kali-qemu-process-label", "version": 1,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "original_guest": self.source_guest,
            "running_guest": self.running_guest,
            "template_id": self.template_id,
            "matching_process_count": self.inspected_matching_processes,
            "read_only_process_label_observed": self.ok,
            "checks": list(self.checks),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "guest_os_boot_verified": False,
            "guest_disk_inode_label_verified": False,
            "packet_level_network_denial_verified": False,
            "recovery_restoration_verified": False,
            "authenticated_qemu_executable_verified": False,
        }


class KaliProcessLabelInspector:
    def __init__(
        self,
        hypervisor: Hypervisor | None = None,
        runtime: RuntimeLabelInspector | None = None,
        proc_root: Path = Path("/proc"),
    ):
        self.hypervisor = hypervisor or Hypervisor()
        self.runtime = runtime or RuntimeLabelInspector(hypervisor=self.hypervisor)
        self.proc_root = Path(proc_root)

    def inspect(self, plan_path: Path, guest: str) -> KaliProcessLabelReport:
        plan = load_setup_plan(Path(plan_path))
        guest = safe_name(guest)
        if guest == plan["guest"]:
            raise ToolError("Select a NEW recovery VM, never the original Kali guest")

        checks: list[str] = []
        errors: list[str] = []
        warnings = [
            "QEMU cmdline can be spoofed; process UUID/name matching is not secure guest attestation",
            "Unprivileged /proc access can be blocked by Fedora permissions or hidepid; no sudo fallback",
            "A privileged VM manager may change guest/process state after observation",
            "Actual QEMU executable provenance, disk context, Kali boot, packet denial and restore are unverified",
        ]
        try:
            observation = self.runtime.inspect(guest, "isolated")
        except (ToolError, ValueError, OSError):
            errors.append("Restricted live SELinux/libvirt metadata inspection could not complete")
            observation = None
        if observation is None or not observation.ok or observation.state != "running":
            errors.append("The guest is not verified already running with valid libvirt sVirt metadata")
            return KaliProcessLabelReport(
                plan["guest"], guest, plan["template_id"], 0,
                tuple(checks), tuple(dict.fromkeys(errors)), tuple(warnings),
            )
        checks.append("Host enforcing + libvirt restricted sVirt metadata passed")

        try:
            domain_uuid, expected_label = _domain_label(
                self.hypervisor._virsh("dumpxml", guest), guest
            )
        except ToolError:
            errors.append("Could not establish current guest UUID and expected SELinux process label")
            return KaliProcessLabelReport(
                plan["guest"], guest, plan["template_id"], 0,
                tuple(checks), tuple(errors), tuple(warnings),
            )

        # /proc is a kernel virtual filesystem; enumerate process IDs only.
        # Never read environ, maps, mem, fd, cwd, guest files or QEMU disks.
        candidates: list[tuple[Path, str, str]] = []
        try:
            entries = list(self.proc_root.iterdir())
        except OSError:
            errors.append("System /proc process list cannot be read without elevation")
            entries = []
        for entry in entries:
            if not entry.name.isdecimal() or entry.is_symlink() or not entry.is_dir():
                continue
            try:
                argv = _arguments(entry)
            except ToolError:
                # Other users' processes may be unreadable. Never assume they
                # are the selected VM; a positive unique exact match is still
                # required to return a matched observation.
                continue
            if not _matches_qemu(argv, guest, domain_uuid):
                continue
            try:
                started = _start_time(entry)
                observed_label = _read_proc(entry / "attr" / "current").decode("utf-8").strip()
                if not observed_label or not PROCESS_LABEL.fullmatch(observed_label):
                    errors.append("Matched QEMU has missing or unexpected effective SELinux process context")
                elif observed_label != expected_label:
                    errors.append("Actual QEMU SELinux process context differs from libvirt's current label")
                candidates.append((entry, started, observed_label))
            except (ToolError, UnicodeError):
                errors.append("Matched QEMU process label/start-time cannot be read without privileges")

        if len(candidates) != 1:
            errors.append("Expected exactly one readable QEMU process with matching libvirt UUID and guest name")
        else:
            checks.append("One QEMU process cmdline matches the current guest UUID and name")
            pid_dir, started, label = candidates[0]
            try:
                if (_start_time(pid_dir) != started or
                        _arguments(pid_dir) is None or
                        not _matches_qemu(_arguments(pid_dir), guest, domain_uuid) or
                        _read_proc(pid_dir / "attr" / "current").decode("utf-8").strip() != label):
                    errors.append("QEMU process identity or effective SELinux label changed during inspection")
                else:
                    checks.append("QEMU /proc attr/current equals libvirt dynamic sVirt process context")
            except (ToolError, UnicodeError):
                errors.append("QEMU process exited or became unreadable during recheck")
        try:
            last_uuid, last_label = _domain_label(
                self.hypervisor._virsh("dumpxml", guest), guest
            )
            if (last_uuid, last_label) != (domain_uuid, expected_label):
                errors.append("Guest UUID or libvirt sVirt label changed during inspection")
            if self.hypervisor.state(guest).strip().lower() != "running":
                errors.append("Guest is no longer in libvirt running state")
            if not errors:
                checks.append("Libvirt UUID, process label and running state remained consistent")
        except ToolError:
            errors.append("Could not recheck current libvirt running process metadata")
        return KaliProcessLabelReport(
            plan["guest"], guest, plan["template_id"],
            len(candidates), tuple(checks), tuple(dict.fromkeys(errors)),
            tuple(warnings),
        )


def save_kali_process_label(report: KaliProcessLabelReport, destination: Path) -> Path:
    """Create a NEW private 0600 metadata-only report; never overwrite."""
    return save_acceptance(report, destination)
