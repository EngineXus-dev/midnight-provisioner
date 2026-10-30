"""Read-only verification of a MANUALLY registered Kali template guest.

No VM registration/start, image copying, disk writes, or guest commands.
Compares existing libvirt definitions with a private curated setup plan
and a user-selected expected independent qcow2. Other guests are inspected
via XML only; no arbitrary disk paths from other guests are opened.

A passed report is a point-in-time metadata consistency check, NOT a
boot, disk provenance, network-denial, or SELinux confinement attestation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import stat
import posixpath
from xml.etree import ElementTree as ET

from .acceptance import RegisteredGuestAuditor, save_acceptance
from .hypervisor import Hypervisor, declared_guest_memory_gib
from .kali_setup import load_setup_plan
from .kali_templates import get_template
from .portability import MachineBudget, current_budget
from .readiness import inspect_image_metadata
from .runner import Runner, ToolError

GIB = 1024 ** 3


def _safe_disk(path: Path) -> Path:
    """Refuse symlink path components before trusting path for qemu-img info."""
    path = Path(path).expanduser()
    if not path.is_absolute() or path.suffix.lower() != ".qcow2":
        raise ToolError("Expected independent disk must be an absolute local .qcow2 path")
    try:
        # is_symlink is checked on each component to prevent accepting
        # a symlinked parent even when the final image is a regular file.
        for part in (path, *path.parents):
            if part.is_symlink():
                raise ToolError("Expected independent disk path includes a symlink")
        resolved = path.resolve(strict=True)
        details = resolved.stat()
    except ToolError:
        # Preserve the meaningful security finding; ToolError is a RuntimeError.
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise ToolError("Expected independent Kali VM disk cannot be inspected") from exc
    if not stat.S_ISREG(details.st_mode) or details.st_size <= 0:
        raise ToolError("Expected independent Kali VM disk must be a nonempty regular file")
    # st_nlink is a kernel inode attribute, unlike a VM's declared disk
    # filename. Refuse a disk that could be written through another hardlink,
    # including one outside the folder or referenced by an unregistered VM.
    if details.st_nlink != 1:
        raise ToolError("Selected Kali disk has multiple hardlinks; independent VM storage cannot be asserted")
    return resolved


def _other_disk_alias(source: str | None, disk: Path) -> str | None:
    """Inspect other VM XML path strings; lstat ONLY within chosen disk folder.

    Never resolve/open a foreign VM's path and never follow a symlink in
    another guest's disk definition. Outside-folder symlinks and other
    storage technologies remain unverified and are disclosed in reports.
    """
    if not source:
        return None
    if not posixpath.isabs(source):
        return "Other registered VM has a relative disk path; independence cannot be verified"
    normalized = posixpath.normpath(source)
    # POSIX normpath keeps a leading "//", but Linux treats it as "/".
    if normalized.startswith("//"):
        normalized = "/" + normalized.lstrip("/")
    if normalized == str(disk):
        return "Another registered VM references the same disk image (including a lexical path alias)"
    candidate = Path(normalized)
    if candidate.parent != disk.parent:
        return None
    # Stay within the explicitly selected local VM-disk directory. The
    # selected parent was already verified symlink-free by _safe_disk().
    try:
        details = candidate.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        return "Cannot inspect a disk alias in the selected Kali storage directory"
    if stat.S_ISLNK(details.st_mode):
        return "Another registered VM uses a symlinked disk path in the selected directory"
    # st_nlink == 1 on the selected disk should prevent same-inode hardlinks,
    # but compare inode identity again in case of a concurrent filesystem race.
    try:
        selected = disk.stat()
    except OSError:
        return "Selected Kali disk disappeared during alias inspection"
    if (details.st_dev, details.st_ino) == (selected.st_dev, selected.st_ino):
        return "Another registered VM disk source resolves to the selected disk inode"
    return None


def _disks(root: ET.Element, *, label: str, errors: list[str]) -> list[str]:
    devices = root.find("devices")
    if devices is None:
        errors.append(f"{label}: missing VM device inventory")
        return []
    sources = []
    for device in devices.findall("disk"):
        kind = device.get("device", "disk")
        source = device.find("source")
        if kind == "cdrom":
            if source is not None and source.attrib:
                errors.append(f"{label}: installer/other CD-ROM remains mounted")
            continue
        if kind != "disk" or device.get("type") != "file":
            errors.append(f"{label}: unapproved disk device or storage backend")
            continue
        if source is None or source.get("file") is None:
            errors.append(f"{label}: disk has no local file source")
            continue
        src = source.get("file")
        driver = device.find("driver")
        if (driver is None or driver.get("name") != "qemu" or
                driver.get("type") != "qcow2"):
            errors.append(f"{label}: disk QEMU driver is not explicitly qcow2")
        if device.find("backingStore") is not None:
            errors.append(f"{label}: unexpected disk backingStore XML")
        sources.append(src)
    return sources


def _xml(hv: Hypervisor, domain: str, label: str, errors: list[str], *,
         inactive: bool = False) -> ET.Element | None:
    try:
        source = hv._virsh("dumpxml", "--inactive", domain) if inactive else hv._virsh("dumpxml", domain)
        root = ET.fromstring(source)
    except (ToolError, ET.ParseError):
        errors.append(f"{label}: cannot verify registered XML")
        return None
    if root.tag != "domain":
        errors.append(f"{label}: unexpected libvirt XML document")
        return None
    return root


@dataclass(frozen=True)
class KaliRegistrationReport:
    guest: str
    template_id: str
    state: str
    inspected_definitions: tuple[str, ...]
    virtual_disk_gib: float | None
    issues: tuple[str, ...]
    cautions: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.issues and self.virtual_disk_gib is not None

    def describe(self) -> str:
        return "\n".join((
            "KALI REGISTERED TEMPLATE: " + (
                "PASS (CONFIGURATION ONLY)" if self.ok else "BLOCKED / UNVERIFIED"
            ),
            f"Guest: {self.guest} | template: {self.template_id} | state: {self.state}",
            f"Disk virtual capacity (GiB): {self.virtual_disk_gib:.2f}" if self.virtual_disk_gib
                is not None else "Disk virtual capacity: UNVERIFIED",
            f"Libvirt definitions inspected: {', '.join(self.inspected_definitions)}",
            *(f"BLOCK {entry}" for entry in self.issues),
            *(f"CAUTION {entry}" for entry in self.cautions),
            "READ-ONLY — no VM created/changed/started, disk mounted/modified or packages installed.",
            "Selected disk has exactly one hardlink; normalized XML aliases and same-folder",
            "symlink paths are checked. Outside-folder symlink aliases, non-file",
            "storage, unregistered guests and other hypervisors remain UNVERIFIED.",
            "This check cannot establish guest boot, signed Kali packages, network",
            "packet denial, sVirt enforcement, disk-content trust or rollback readiness.",
        ))

    def evidence(self) -> dict:
        return {
            "format": "midnight-provisioner-kali-registered-template",
            "version": 1,
            "guest": self.guest,
            "template_id": self.template_id,
            "state": self.state,
            "inspected_definitions": list(self.inspected_definitions),
            "disk_capacity_gib": self.virtual_disk_gib,
            "configuration_checks_passed": self.ok,
            "issues": list(self.issues),
            "cautions": list(self.cautions),
            "observations_not_performed": [
                "guest-boot", "disk-image-signature-and-publisher",
                "outside-folder-symlink-and-other-hypervisor-alias-check",
                "unregistered-or-other-hypervisor-disk-shares",
                "packet-level-network-denial", "SELinux-runtime-enforcement",
                "Kali-package-installation", "cold-snapshot-rollback",
            ],
        }


class KaliRegistrationInspector:
    def __init__(
        self, hypervisor: Hypervisor | None = None,
        runner: Runner | None = None,
        budget: MachineBudget | None = None,
    ):
        self.hypervisor = hypervisor or Hypervisor()
        self.runner = runner or Runner()
        self.budget = budget

    def inspect(self, plan_path: Path, expected_disk: Path) -> KaliRegistrationReport:
        plan = load_setup_plan(Path(plan_path))
        template = get_template(plan["template_id"])
        guest = plan["guest"]
        disk = _safe_disk(Path(expected_disk))
        # Compare identity after the lengthy XML and qemu-img metadata checks.
        # This narrows, but cannot eliminate, privileged guest/storage races.
        initial_stat = disk.stat()
        initial_inode = (initial_stat.st_dev, initial_stat.st_ino)
        issues: list[str] = []
        cautions = [
            "Offline libvirt XML is metadata, not a measurement of actual guest isolation",
            "A privileged process can change disk files/VM definitions after this check",
            "No boot, package provenance, effective SELinux, or cold restore test was performed",
        ]
        inspected = []
        virtual_gib = None

        # Reuse the registered VM audit, which validates current and next-boot
        # device policies, managed-save definition and local RAM safety cap.
        # A template must be shut off and must NOT have a saved resume state.
        hv = self.hypervisor
        try:
            acceptance = RegisteredGuestAuditor(hv).inspect(guest, "lab")
        except (ToolError, ValueError) as exc:
            raise ToolError("Cannot inspect registered Kali guest: " + str(exc)[:240]) from exc
        issues.extend(acceptance.errors)
        if acceptance.state != "shut off":
            issues.append("Template guest must be shut off for an offline registration audit")
        if "Managed-save definition" in acceptance.documents:
            issues.append("Template guest has managed-save state; refuse resumable guest handoff")

        # Inspect the exact proposed guest by active + persistent definition,
        # and independently detect shared source paths in ALL registered VMs.
        target_xml = [
            ("Current definition", _xml(hv, guest, "Current definition", issues)),
            ("Inactive definition", _xml(hv, guest, "Inactive definition", issues, inactive=True)),
        ]
        inspected.extend(label for label, _ in target_xml)
        uuids = set()
        for label, root in target_xml:
            if root is None:
                continue
            if root.findtext("name") != guest:
                issues.append(f"{label}: VM name differs from selected template")
            identity = (root.findtext("uuid") or "").strip()
            if not identity:
                issues.append(f"{label}: persistent UUID is missing")
            else:
                uuids.add(identity)
            if root.find("./devices/interface") is not None:
                issues.append(f"{label}: Kali template VM must remain fully disconnected")
            actual = _disks(root, label=label, errors=issues)
            if actual != [str(disk)]:
                issues.append(f"{label}: VM must use exactly the selected independent disk path")
            # The plan's RAM and CPUs are suggestions only, but Midnight Provisioner's
            # physical host cap remains authoritative. Avoid false exact-match
            # claims if a manually installed VM uses less RAM than suggested.
            try:
                ram = declared_guest_memory_gib(ET.tostring(root, encoding="unicode"))
                if ram * 1024 < 1024:
                    issues.append(f"{label}: registered RAM is below 1024 MiB")
                if ram > (self.budget or current_budget()).guest_ram_cap_gib:
                    issues.append(f"{label}: registered RAM exceeds current host budget")
                cpu = root.find("vcpu")
                if cpu is None or not (cpu.text or "").strip().isdigit():
                    issues.append(f"{label}: registered CPU count cannot be verified")
                else:
                    cpus = int(cpu.text.strip())
                    if not 1 <= cpus <= (self.budget or current_budget()).vcpu_cap:
                        issues.append(f"{label}: registered vCPU count exceeds current host budget")
            except (ValueError, TypeError, ET.ParseError):
                issues.append(f"{label}: registered CPU/RAM cannot be verified")
        if len(uuids) != 1:
            issues.append("Current and next-boot VM identity UUIDs disagree or are missing")

        try:
            inventory = hv.list_domains()
        except ToolError:
            issues.append("Cannot inventory all system libvirt guests for disk-source collisions")
            inventory = []
        if guest not in inventory:
            issues.append("Selected Kali template guest disappeared during inspection")
        for other in inventory:
            if other == guest:
                continue
            # A conservative collision check: failure to read even one other
            # guest's next-boot/current XML means sharing cannot be excluded.
            for label, inactive in (("current", False), ("inactive", True)):
                other_xml = _xml(hv, other, f"Other VM {label} definition", issues, inactive=inactive)
                if other_xml is None:
                    continue
                for source in other_xml.findall("./devices/disk/source"):
                    finding = _other_disk_alias(source.get("file"), disk)
                    if finding:
                        issues.append(finding)
            try:
                saved = hv._managed_save_xml(other)
                if saved is not None:
                    saved_root = ET.fromstring(saved)
                    for source in saved_root.findall("./devices/disk/source"):
                        finding = _other_disk_alias(source.get("file"), disk)
                        if finding:
                            issues.append("Managed-save disk collision: " + finding)
            except (ToolError, ET.ParseError):
                issues.append("Cannot verify another VM's managed-save disk sources")
        if not issues:
            # qemu-img is invoked only on the user-selected validated path,
            # NEVER on a path obtained from an unrelated libvirt guest.
            try:
                meta = inspect_image_metadata(self.runner, disk, "qcow2")
                virtual_gib = meta["virtual-size"] / GIB
                if virtual_gib < max(20, template.disk_gib * 0.5):
                    issues.append("Virtual disk is unexpectedly small for this template")
                if virtual_gib > 256:
                    issues.append("Virtual disk exceeds Midnight Provisioner's conservative 256 GiB limit")
                if virtual_gib < template.disk_gib:
                    cautions.append(
                        "Actual disk capacity is below the template recommendation; "
                        "review Kali tools and dependency size before manual installation"
                    )
            except ToolError:
                issues.append("Selected independent disk QEMU metadata could not be verified")
        if not issues:
            # Detect unexpected replacement/new hardlinks while querying XML
            # or QEMU. No file content is read/written by this stat-based guard.
            try:
                _safe_disk(disk)
                final_stat = disk.stat()
                if (final_stat.st_dev, final_stat.st_ino) != initial_inode:
                    issues.append("Selected Kali disk inode changed during inspection")
            except (OSError, ToolError):
                issues.append("Selected Kali disk became unavailable or hardlinked during inspection")
        if not issues:
            # Observe the guest's state again after slower image and XML reads.
            try:
                if hv.state(guest).strip().lower() != "shut off":
                    issues.append("Kali template VM changed state during offline inspection")
            except ToolError:
                issues.append("Cannot reverify Kali VM shut-off state after disk inspection")

        return KaliRegistrationReport(
            guest, template.identifier, acceptance.state,
            tuple(inspected), virtual_gib, tuple(dict.fromkeys(issues)),
            tuple(cautions),
        )


def save_registration_report(report: KaliRegistrationReport, destination: Path) -> Path:
    """Use the existing exclusive-create private report writer."""
    return save_acceptance(report, destination)
