"""Compact cyberpunk-inspired KDE controller. Only opt-in, guarded actions mutate VMs."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from dataclasses import replace
from functools import partial
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, QTimer, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget, QPlainTextEdit,
)
from .containers import Containers
from .diagnostics import collect_checks, resource_advice
from .hypervisor import Hypervisor
from .models import Workspace, WorkspaceError, safe_name
from .runner import ToolError
from .settings import load_workspaces, save_workspaces
from .portability import (
    MachinePreferences, current_budget, load_machine_preferences, save_machine_preferences,
)
from .updates import SourceUpdater
from .provisioning import OfflineProvisioner, build_plan
from .backups import ColdBackup, verify_backup
from .recovery import RecoveryStager, verify_staging
from .readiness import RecoveryReadiness
from .acceptance import RegisteredGuestAuditor, save_acceptance
from .handoff import RecoveryHandoff
from .theme import apply_theme, COLORS
from .resources import collect_resources
from .host_posture import inspect_host_posture
from .runtime_labels import RuntimeLabelInspector

class NoWheelComboBox(QComboBox):
    """Prevent incidental wheel scrolling from changing a saved profile."""
    def wheelEvent(self, event):
        event.ignore()


class WorkSignals(QObject):
    success = Signal(object)
    failure = Signal(str)


class Job(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = WorkSignals()

    def run(self):
        try:
            self.signals.success.emit(self.function())
        except Exception as exc:  # visible to user; never silently swallow task failures
            self.signals.failure.emit(str(exc))


class SpaceCard(QFrame):
    def __init__(self, space: Workspace, parent):
        super().__init__()
        self.space = space
        self.main = parent
        self.setObjectName("WorkspaceCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 17, 18, 17)
        outer.setSpacing(11)
        top = QHBoxLayout()
        title = QLabel(space.name)
        title.setObjectName("CardTitle")
        top.addWidget(title, 1)
        badge = QLabel(space.policy.upper())
        badge.setObjectName("Badge")
        top.addWidget(badge)
        outer.addLayout(top)
        self.details = QLabel(space.detail)
        self.details.setWordWrap(True)
        self.details.setObjectName("SubTitle")
        self.details.setMinimumHeight(37)
        outer.addWidget(self.details)
        self.state = QLabel("● Checking availability …")
        self.state.setStyleSheet("color: " + COLORS["text_muted"])
        outer.addWidget(self.state)
        self.policy = QLabel("Local-only controller · no cloud link")
        self.policy.setObjectName("SubTitle")
        self.policy.setWordWrap(True)
        outer.addWidget(self.policy)
        buttons = QHBoxLayout()
        self.launch = QPushButton("Open" if space.kind == "host" else "Start / Enter")
        self.launch.setObjectName("Primary")
        self.launch.clicked.connect(lambda: parent.launch_space(space.key))
        buttons.addWidget(self.launch)
        if space.kind == "vm":
            self.stop = QPushButton("Shut down")
            self.stop.clicked.connect(lambda: parent.shutdown_space(space.key))
            buttons.addWidget(self.stop)
            self.stop.setEnabled(False)
            self.prepare = QPushButton("Prepare new VM")
            self.prepare.clicked.connect(lambda: parent.prepare_space(space.key))
            buttons.addWidget(self.prepare)
            self.configure = QPushButton("Bind VM")
            self.configure.clicked.connect(lambda: parent.bind_space(space.key))
            buttons.addWidget(self.configure)
        else:
            self.stop = None
        outer.addLayout(buttons)
        if space.kind == "vm":
            more = QHBoxLayout()
            self.viewer = QPushButton("View console")
            self.viewer.clicked.connect(lambda: parent.view_space(space.key))
            self.viewer.setEnabled(False)
            more.addWidget(self.viewer)
            self.save = QPushButton("Save VM state")
            self.save.clicked.connect(lambda: parent.save_space(space.key))
            self.save.setEnabled(False)
            more.addWidget(self.save)
            self.backup = QPushButton("Cold backup")
            self.backup.clicked.connect(lambda: parent.backup_space(space.key))
            self.backup.setEnabled(False)
            more.addWidget(self.backup)
            outer.addLayout(more)
        else:
            self.save = self.viewer = self.backup = None

    def update_status(self, status: str, explanation: str, can_start: bool, running: bool):
        self.state.setText("● " + status)
        self.state.setStyleSheet("color: " + (COLORS["success"] if running else (COLORS["warning"] if not can_start else COLORS["text_muted"])))
        self.policy.setText(explanation[:220])
        self.launch.setEnabled((can_start and not running) if self.space.kind == "vm" else can_start)
        if self.stop:
            self.stop.setEnabled(running)
        if self.viewer:
            self.viewer.setEnabled(running)
        if self.save:
            self.save.setEnabled(running and self.space.policy != "isolated")
        if self.backup:
            self.backup.setEnabled(not running and can_start)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nightglass — Secure Workspaces")
        self.resize(1150, 760)
        self.setMinimumSize(880, 610)
        self.hv = Hypervisor()
        self.containers = Containers()
        self.spaces = load_workspaces()
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(3)
        self._jobs = set()
        self.cards = {}
        self._busy = False
        self.last_acceptance = None
        self._resource_monitor_enabled = False
        self._resource_monitor_busy = False
        self._build()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(30000)
        self.resource_timer = QTimer(self)
        self.resource_timer.timeout.connect(self.refresh_resources)
        self.resource_timer.start(20000)
        # Only contacts GitHub if the user explicitly opted into update notices.
        if load_machine_preferences().automatic_update_checks:
            QTimer.singleShot(4000, self.check_updates)

    def work(self, function, finished=None, failed=None):
        job = Job(function)
        self._jobs.add(job)

        def good(result):
            self._jobs.discard(job)
            if finished:
                finished(result)

        def bad(message):
            self._jobs.discard(job)
            if failed:
                failed(message)
            else:
                self.error(message)

        job.signals.success.connect(good)
        job.signals.failure.connect(bad)
        self.pool.start(job)

    def _build(self):
        shell = QWidget()
        self.setCentralWidget(shell)
        main = QHBoxLayout(shell)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        rail = QFrame()
        rail.setObjectName("Sidebar")
        rail.setFixedWidth(208)
        side = QVBoxLayout(rail)
        side.setContentsMargins(19, 26, 19, 18)
        side.setSpacing(12)
        logo = QLabel("NIGHTGLASS")
        logo.setObjectName("Brand")
        side.addWidget(logo)
        slogan = QLabel("ISOLATE  /  CREATE  /  RESTORE")
        slogan.setObjectName("Tagline")
        side.addWidget(slogan)
        side.addSpacing(8)
        accent_rail = QFrame()
        accent_rail.setObjectName("AccentRail")
        accent_rail.setFixedHeight(2)
        accent_rail.setAccessibleName("Subtle pink and purple accent divider")
        side.addWidget(accent_rail)
        side.addSpacing(16)
        self.stack = QStackedWidget()
        nav = [("▦  Workspaces", 0), ("◇  Security model", 1), ("✦  Diagnostics", 2), ("⚙  Machine settings", 3), ("⬡  Prepare VM", 4), ("↺  Backup & verify", 5)]
        self.nav_buttons = []
        for label, index in nav:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setChecked(index == 0)
            button.setMinimumHeight(43)
            button.clicked.connect(partial(self.goto, index))
            side.addWidget(button)
            self.nav_buttons.append(button)
        side.addStretch()
        side.addWidget(QLabel("LOCAL FIRST  •  v0.1.0"))
        main.addWidget(rail)
        pages = QWidget()
        right = QVBoxLayout(pages)
        right.setContentsMargins(26, 24, 26, 20)
        header = QHBoxLayout()
        title_area = QVBoxLayout()
        self.header_title = QLabel("Security workspaces")
        self.header_title.setObjectName("Title")
        title_area.addWidget(self.header_title)
        subtitle = QLabel("Fedora KDE  /  KVM + libvirt  /  trusted Distrobox")
        subtitle.setObjectName("SubTitle")
        title_area.addWidget(subtitle)
        header.addLayout(title_area, 1)
        refresh = QPushButton("↻ Refresh")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        right.addLayout(header)
        right.addSpacing(14)
        right.addWidget(self.stack, 1)
        footer = QLabel("PROTECTED BY SEPARATION, NOT BY THEME  ·  Launch checks are guardrails, not a substitute for hypervisor hardening")
        footer.setObjectName("AppFooter")
        footer.setWordWrap(True)
        right.addWidget(footer)
        main.addWidget(pages, 1)
        self._build_workspaces()
        self._build_security()
        self._build_diagnostics()
        self._build_machine()
        self._build_provisioning()
        self._build_recovery()

    def _build_workspaces(self):
        viewport = QScrollArea()
        viewport.setWidgetResizable(True)
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(1, 2, 1, 12)
        layout.setSpacing(18)
        intro = QLabel("Separate contexts, persistent environments. Host apps are not isolated; strict policies apply to lab VMs.")
        intro.setWordWrap(True)
        intro.setObjectName("SubTitle")
        layout.addWidget(intro)
        matrix = QGridLayout()
        matrix.setSpacing(15)
        for index, space in enumerate(self.spaces):
            card = SpaceCard(space, self)
            self.cards[space.key] = card
            matrix.addWidget(card, index // 2, index % 2)
        layout.addLayout(matrix)
        layout.addStretch()
        tools = QHBoxLayout()
        vm_manager = QPushButton("Open virt-manager")
        vm_manager.clicked.connect(lambda: self.open_program(["virt-manager", "--connect", "qemu:///system"]))
        tools.addWidget(vm_manager)
        tools.addStretch()
        layout.addLayout(tools)
        viewport.setWidget(holder)
        self.stack.addWidget(viewport)

    def _build_security(self):
        area = QScrollArea()
        area.setWidgetResizable(True)
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(4, 5, 4, 10)
        for name, desc in (
            ("PERSONAL HOST", "Native Fedora host. All personal apps on the host share the host trust boundary. This is NOT Qubes OS."),
            ("TRUSTED DEVELOPMENT", "Distrobox shares host files, display server, and often home data. Use it only for code you trust."),
            ("KALI LAB", "Before start, accept only disconnected networking or a verified no-forward libvirt network called nightglass-lab. This does not prevent guest access to services exposed by the host on that bridge."),
            ("MALWARE ANALYSIS", "Before start, require no network interfaces, no filesystem/USB/passthrough, no SPICE/guest agent channels, and loopback VNC or local sockets. Not a guarantee against hypervisor escape."),
            ("FILE TRANSFER", "No automated transfers from labs. Validate samples and move only intentional, scanned, non-executable artifacts into the host."),
            ("PERSISTENCE + RECOVERY", "Libvirt managedsave preserves running VM state; it is NOT a snapshot or backup. Keep separately tested backups, immutable offline baselines, and a disposable analysis workflow."),
        ):
            panel = QFrame()
            panel.setObjectName("Panel")
            inner = QVBoxLayout(panel)
            head = QLabel(name)
            head.setObjectName("SectionHeading")
            inner.addWidget(head)
            copy = QLabel(desc)
            copy.setWordWrap(True)
            inner.addWidget(copy)
            layout.addWidget(panel)
        layout.addStretch()
        area.setWidget(holder)
        self.stack.addWidget(area)

    def _build_diagnostics(self):
        shell = QWidget()
        layout = QVBoxLayout(shell)
        text = QLabel("Read-only host readiness checks. No disks, EFI settings, partitions or Windows data are modified.")
        text.setWordWrap(True)
        text.setObjectName("SubTitle")
        layout.addWidget(text)
        pressure_panel = QFrame()
        pressure_panel.setObjectName("Panel")
        pressure_layout = QVBoxLayout(pressure_panel)
        pressure_heading = QLabel("LIVE RESOURCE PRESSURE  ·  READ-ONLY")
        pressure_heading.setObjectName("SectionHeading")
        pressure_layout.addWidget(pressure_heading)
        self.resource_status = QLabel("Not checked — select Refresh resource monitor")
        self.resource_status.setObjectName("Badge")
        self.resource_status.setWordWrap(True)
        pressure_layout.addWidget(self.resource_status)
        self.resource_details = QPlainTextEdit()
        self.resource_details.setReadOnly(True)
        self.resource_details.setMinimumHeight(145)
        self.resource_details.setPlaceholderText(
            "Read MemAvailable, swap occupancy and all registered system libvirt VM states."
        )
        pressure_layout.addWidget(self.resource_details)
        refresh_pressure = QPushButton("Refresh resource monitor")
        refresh_pressure.setToolTip(
            "Enable advisory checks every 20 seconds while Diagnostics is displayed; "
            "never start, stop or reconfigure a guest."
        )
        refresh_pressure.clicked.connect(lambda: self.refresh_resources(activate=True))
        pressure_layout.addWidget(refresh_pressure)
        layout.addWidget(pressure_panel)
        posture_panel = QFrame()
        posture_panel.setObjectName("Panel")
        posture_layout = QVBoxLayout(posture_panel)
        posture_heading = QLabel("FEDORA HOST SECURITY POSTURE  ·  READ-ONLY")
        posture_heading.setObjectName("SectionHeading")
        posture_layout.addWidget(posture_heading)
        self.posture_summary = QLabel(
            "Not checked — SELinux, /dev/kvm and firewall routing require review"
        )
        self.posture_summary.setWordWrap(True)
        self.posture_summary.setObjectName("SubTitle")
        posture_layout.addWidget(self.posture_summary)
        posture_button = QPushButton("Audit Fedora host security")
        posture_button.setToolTip(
            "Read SELinux enforcement, KVM access, firewalld status and IPv4/IPv6 "
            "forwarding. No sudo, guest startup, firewall or SELinux changes."
        )
        posture_button.clicked.connect(self.check_host_security)
        posture_layout.addWidget(posture_button)
        observe = QPushButton("Observe running VM sVirt labels")
        observe.setToolTip(
            "Observe SELinux and libvirt label metadata of an ALREADY-running, "
            "registered restricted VM. Never starts the guest or verifies actual process confinement."
        )
        observe.clicked.connect(self.observe_guest_runtime_labels)
        posture_layout.addWidget(observe)
        save_observation = QPushButton("Save local runtime observation")
        save_observation.setToolTip("Save the last metadata report privately without overwriting files.")
        save_observation.clicked.connect(self.export_acceptance_report)
        posture_layout.addWidget(save_observation)
        layout.addWidget(posture_panel)
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setPlaceholderText("Select 'Run host checks' to inspect host readiness")
        layout.addWidget(self.diagnostics, 1)
        run = QPushButton("Run host checks")
        run.clicked.connect(self.check_host)
        layout.addWidget(run)
        self.stack.addWidget(shell)

    def _build_machine(self):
        """Machine-local tuning never recreates VMs or touches Windows."""
        page = QScrollArea()
        page.setWidgetResizable(True)
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(4, 5, 4, 10)
        layout.setSpacing(14)

        description = QLabel(
            "One installation on every machine. Nightglass detects host RAM and CPUs at runtime, "
            "then safely clamps these preferences. Your VMs, workspace definitions and data stay intact."
        )
        description.setObjectName("SubTitle")
        description.setWordWrap(True)
        layout.addWidget(description)

        panel = QFrame()
        panel.setObjectName("Panel")
        inner = QVBoxLayout(panel)
        inner.setSpacing(12)
        title = QLabel("RESOURCE PROFILE")
        title.setObjectName("SectionHeading")
        inner.addWidget(title)
        self.profile_combo = NoWheelComboBox()
        for label, value in (
            ("Automatic — recommended", "auto"),
            ("Compact — low RAM", "compact"),
            ("Balanced — 16 GB class", "balanced"),
            ("Performance — 24–32 GB class", "performance"),
        ):
            self.profile_combo.addItem(label, value)
        settings = load_machine_preferences()
        position = self.profile_combo.findData(settings.preset)
        self.profile_combo.setCurrentIndex(max(0, position))
        inner.addWidget(self.profile_combo)
        advanced = QLabel("Optional fine-tuning (leave blank for automatic)")
        advanced.setObjectName("SubTitle")
        inner.addWidget(advanced)
        controls = QGridLayout()
        self.ram_override = QLineEdit()
        self.ram_override.setPlaceholderText("Auto")
        self.ram_override.setValidator(QDoubleValidator(1.0, 128.0, 2, self))
        self.ram_override.setText(str(settings.guest_ram_cap_gib or ""))
        self.vm_override = QLineEdit()
        self.vm_override.setPlaceholderText("Auto")
        self.vm_override.setValidator(QIntValidator(1, 128, self))
        self.vm_override.setText(str(settings.active_vm_cap or ""))
        self.cpu_override = QLineEdit()
        self.cpu_override.setPlaceholderText("Auto")
        self.cpu_override.setValidator(QIntValidator(1, 128, self))
        self.cpu_override.setText(str(settings.vcpu_cap or ""))
        for index, (label, widget) in enumerate((
            ("VM memory cap (GiB)", self.ram_override),
            ("Concurrent VM limit", self.vm_override),
            ("Suggested vCPUs (advisory)", self.cpu_override),
        )):
            controls.addWidget(QLabel(label), index, 0)
            controls.addWidget(widget, index, 1)
            widget.textChanged.connect(self.preview_machine_profile)
        inner.addLayout(controls)
        self.profile_summary = QLabel("")
        self.profile_summary.setWordWrap(True)
        inner.addWidget(self.profile_summary)
        self.profile_combo.currentIndexChanged.connect(self.preview_machine_profile)
        save = QPushButton("Save machine profile")
        save.setObjectName("Primary")
        save.clicked.connect(self.save_machine_profile)
        inner.addWidget(save)
        layout.addWidget(panel)

        update_panel = QFrame()
        update_panel.setObjectName("Panel")
        updater = QVBoxLayout(update_panel)
        head = QLabel("APPLICATION UPDATES")
        head.setObjectName("SectionHeading")
        updater.addWidget(head)
        self.update_opt_in = QCheckBox("Check GitHub for new source versions when Nightglass opens")
        self.update_opt_in.setChecked(settings.automatic_update_checks)
        updater.addWidget(self.update_opt_in)
        caution = QLabel(
            "Checks are optional; nothing installs automatically. Source updates require "
            "a clean, official Nightglass main-branch checkout, your confirmation, and an app restart. "
            "Guest disks and workspace data are never part of this update operation."
        )
        caution.setObjectName("SubTitle")
        caution.setWordWrap(True)
        updater.addWidget(caution)
        actions = QHBoxLayout()
        check = QPushButton("Check for updates")
        check.clicked.connect(self.check_updates)
        actions.addWidget(check)
        apply = QPushButton("Install available update")
        apply.clicked.connect(self.apply_update)
        actions.addWidget(apply)
        updater.addLayout(actions)
        self.update_message = QLabel("No update check has been run.")
        self.update_message.setWordWrap(True)
        updater.addWidget(self.update_message)
        layout.addWidget(update_panel)
        layout.addStretch()
        page.setWidget(holder)
        self.stack.addWidget(page)
        self.preview_machine_profile()

    def machine_preferences_from_form(self) -> MachinePreferences:
        ram_value = self.ram_override.text().strip()
        vm_value = self.vm_override.text().strip()
        cpu_value = self.cpu_override.text().strip()
        return MachinePreferences(
            preset=self.profile_combo.currentData() or "auto",
            guest_ram_cap_gib=float(ram_value) if ram_value else None,
            active_vm_cap=int(vm_value) if vm_value else None,
            vcpu_cap=int(cpu_value) if cpu_value else None,
            automatic_update_checks=self.update_opt_in.isChecked(),
        )

    def preview_machine_profile(self, *_):
        try:
            prefs = self.machine_preferences_from_form()
            self.profile_summary.setText(
                current_budget(prefs).explain() +
                "\nHost safety limits always win; existing VM RAM allocations aren't rewritten. "
                "The vCPU value is a recommendation, not enforced by libvirt."
            )
        except (WorkspaceError, ValueError):
            self.profile_summary.setText("Enter valid resource numbers or leave the fields blank.")

    def save_machine_profile(self):
        try:
            save_machine_preferences(self.machine_preferences_from_form())
        except (WorkspaceError, OSError, ValueError) as exc:
            self.error(str(exc))
            return
        self.preview_machine_profile()
        self.inform("Machine settings saved. Current VM disks, sessions and workspace bindings are unchanged.")
        self.refresh()

    def check_updates(self):
        self.update_message.setText("Checking official main branch (read-only working tree) …")
        def completed(status):
            if status.behind and not status.ahead:
                message = f"{status.behind} commit(s) available. Select Install to confirm a clean fast-forward update."
            elif status.ahead:
                message = "Local source diverges from main; automatic update is blocked."
            else:
                message = "Source is up to date."
            self.update_message.setText(message)
        self.work(lambda: SourceUpdater().check(), completed,
                  lambda msg: self.update_message.setText("Check unavailable: " + msg))

    def apply_update(self):
        if QMessageBox.question(
            self, "Confirm Nightglass source update",
            "Fetch official main and fast-forward ONLY a clean checkout? "
            "No merge, reset, force-push, or VM changes. Restart Nightglass afterward.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.update_message.setText("Verifying clean source checkout …")
        self.work(
            lambda: SourceUpdater().apply(confirmed=True),
            lambda result: self.update_message.setText(result),
            lambda message: self.update_message.setText("Update blocked: " + message),
        )

    def _build_provisioning(self):
        """Read-only, fail-closed VM planning: never creates a disk or guest."""
        page = QScrollArea()
        page.setWidgetResizable(True)
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(4, 5, 4, 14)
        layout.setSpacing(12)
        intro = QLabel(
            "Prepare a new offline Kali/pentesting or analysis VM. "
            "Choose a LOCAL installer ISO and paste its SHA-256 from the publisher's official site. "
            "Nightglass verifies the file and checks BOTH virt-install XML phases using --dry-run. "
            "This preview does NOT create or boot a VM. Use virt-manager to install and then Bind VM."
        )
        intro.setObjectName("SubTitle")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        panel = QFrame()
        panel.setObjectName("Panel")
        grid = QGridLayout(panel)
        grid.setContentsMargins(18, 15, 18, 15)
        grid.setSpacing(10)
        self.provision_kind = NoWheelComboBox()
        self.provision_kind.addItem("Kali / authorized pentesting (offline initially)", "pentest")
        self.provision_kind.addItem("Disposable malware analysis (offline)", "analysis")
        self.provision_name = QLineEdit("nightglass-kali")
        self.provision_name.setPlaceholderText("Unique VM name")
        self.provision_kind.currentIndexChanged.connect(self.provision_kind_changed)
        self.provision_iso = QLineEdit()
        self.provision_iso.setPlaceholderText("Select downloaded Linux .iso file")
        iso_row = QHBoxLayout()
        iso_row.addWidget(self.provision_iso, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self.choose_provision_iso)
        iso_row.addWidget(browse)
        self.provision_sha = QLineEdit()
        self.provision_sha.setPlaceholderText("64-character official ISO SHA-256 checksum")
        self.provision_ram = QLineEdit()
        self.provision_ram.setPlaceholderText("Auto (MiB)")
        self.provision_ram.setValidator(QIntValidator(1024, 131072, self))
        self.provision_cpus = QLineEdit()
        self.provision_cpus.setPlaceholderText("Auto (vCPUs)")
        self.provision_cpus.setValidator(QIntValidator(1, 128, self))
        self.provision_disk = QLineEdit()
        self.provision_disk.setPlaceholderText("Auto (GiB)")
        self.provision_disk.setValidator(QIntValidator(20, 256, self))
        specs = [
            ("Workspace type", self.provision_kind),
            ("VM name", self.provision_name),
            ("SHA-256 from publisher", self.provision_sha),
            ("RAM in MiB", self.provision_ram),
            ("Virtual disk in GiB", self.provision_disk),
            ("vCPU count", self.provision_cpus),
        ]
        grid.addWidget(QLabel("Installer ISO"), 0, 0)
        grid.addLayout(iso_row, 0, 1)
        for index, (label, field) in enumerate(specs, start=1):
            grid.addWidget(QLabel(label), index, 0)
            grid.addWidget(field, index, 1)
        layout.addWidget(panel)

        controls = QHBoxLayout()
        self.provision_preview_button = QPushButton("Verify ISO + preview VM")
        self.provision_preview_button.setObjectName("Primary")
        self.provision_preview_button.clicked.connect(self.preview_provision)
        controls.addWidget(self.provision_preview_button)
        vm_manager = QPushButton("Open virt-manager")
        vm_manager.clicked.connect(lambda: self.open_program(["virt-manager", "--connect", "qemu:///system"]))
        controls.addWidget(vm_manager)
        layout.addLayout(controls)
        self.provision_result = QPlainTextEdit()
        self.provision_result.setReadOnly(True)
        self.provision_result.setMinimumHeight(265)
        self.provision_result.setPlaceholderText(
            "Preview is strictly read-only: no VM creation, no disk changes, no downloads."
        )
        layout.addWidget(self.provision_result)
        layout.addStretch()
        page.setWidget(holder)
        self.stack.addWidget(page)

    def provision_kind_changed(self, *_):
        kind = self.provision_kind.currentData()
        self.provision_name.setText("nightglass-malware" if kind == "analysis" else "nightglass-kali")
        self.provision_result.clear()

    def choose_provision_iso(self):
        selected, _ = QFileDialog.getOpenFileName(
            self, "Choose a local installer ISO", "", "Installer images (*.iso)"
        )
        if selected:
            self.provision_iso.setText(selected)
            self.provision_result.clear()

    def prepare_space(self, key: str):
        if key not in {"pentest", "analysis"}:
            self.error("Only dedicated guest workspaces support offline preparation.")
            return
        index = self.provision_kind.findData(key)
        self.provision_kind.setCurrentIndex(index)
        self.goto(4)

    def preview_provision(self):
        try:
            plan = build_plan(
                self.provision_kind.currentData(),
                self.provision_iso.text().strip(),
                self.provision_sha.text().strip(),
                name=self.provision_name.text().strip(),
                ram_mib=int(self.provision_ram.text()) if self.provision_ram.text() else None,
                vcpus=int(self.provision_cpus.text()) if self.provision_cpus.text() else None,
                disk_gib=int(self.provision_disk.text()) if self.provision_disk.text() else None,
            )
        except (WorkspaceError, ToolError, ValueError, OSError) as exc:
            self.error(str(exc))
            return
        if QMessageBox.question(
            self, "Read-only VM preflight",
            "Verify the ISO checksum and ask virt-install to print configuration XML "
            "for both phases? This may take time for a large ISO, but does not create a VM.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.provision_preview_button.setEnabled(False)
        self.provision_result.setPlainText("Checking local ISO checksum and validating offline guest XML…")
        def completed(preview):
            self.provision_preview_button.setEnabled(True)
            self.provision_result.setPlainText(preview.describe())
        def failed(message):
            self.provision_preview_button.setEnabled(True)
            self.provision_result.setPlainText(
                "PROVISIONING BLOCKED — NO VM CREATED\n" + message +
                "\nReview guest tools and ISO provenance before retrying."
            )
        self.work(lambda: OfflineProvisioner().preview(plan), completed, failed)

    def _build_recovery(self):
        area = QWidget()
        layout = QVBoxLayout(area)
        title = QLabel(
            "Cold backups require a powered-off guest and verified source files. "
            "Recovery staging creates a SEPARATE, unregistered guest copy with an "
            "offline XML definition and new identity. No import, start or overwrite is automatic."
        )
        title.setObjectName("SubTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        self.recovery_log = QPlainTextEdit()
        self.recovery_log.setReadOnly(True)
        self.recovery_log.setPlaceholderText(
            "Select Cold backup from a VM card, or verify a previously exported backup folder."
        )
        layout.addWidget(self.recovery_log)
        row = QHBoxLayout()
        verify = QPushButton("Verify saved backup")
        verify.clicked.connect(self.verify_backup_folder)
        row.addWidget(verify)
        stage = QPushButton("Recover into NEW folder")
        stage.clicked.connect(self.stage_backup_folder)
        row.addWidget(stage)
        stage_verify = QPushButton("Verify staged recovery")
        stage_verify.clicked.connect(self.verify_recovery_folder)
        row.addWidget(stage_verify)
        host_check = QPushButton("Check Fedora import readiness")
        host_check.clicked.connect(self.preflight_recovery_folder)
        row.addWidget(host_check)
        row.addStretch()
        layout.addLayout(row)
        acceptance_row = QHBoxLayout()
        inspect = QPushButton("Audit registered VM")
        inspect.clicked.connect(self.inspect_registered_guest)
        acceptance_row.addWidget(inspect)
        handoff = QPushButton("Verify registered handoff")
        handoff.setToolTip(
            "Read-only check of a registered powered-off VM against the disk and "
            "NVRAM paths, identity and disk formats in a verified recovery folder. "
            "Does not start, register or change the VM."
        )
        handoff.clicked.connect(self.verify_registered_handoff)
        acceptance_row.addWidget(handoff)
        export = QPushButton("Save local audit report")
        export.clicked.connect(self.export_acceptance_report)
        acceptance_row.addWidget(export)
        acceptance_row.addStretch()
        layout.addLayout(acceptance_row)
        self.stack.addWidget(area)

    def backup_space(self, key: str):
        space = self.get_space(key)
        if space.kind != "vm" or space.policy not in {"isolated", "lab"}:
            self.error("Cold export is only available for a dedicated restricted VM.")
            return
        parent = QFileDialog.getExistingDirectory(
            self, "Select a parent directory for a NEW cold backup", str(Path.home())
        )
        if not parent:
            return
        default = space.identifier + "-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        name, ok = QInputDialog.getText(
            self, "New backup folder", "New folder name (must not exist):", text=default
        )
        if not ok:
            return
        try:
            name = safe_name(name.strip())
        except WorkspaceError as exc:
            self.error(str(exc))
            return
        target = Path(parent) / name
        if target.exists() or target.is_symlink():
            self.error("The backup folder already exists. Choose a new unique name.")
            return
        self.goto(5)
        self.recovery_log.setPlainText("Inspecting offline guest and storage, without writing files …")
        def ready(plan):
            if QMessageBox.question(
                self,
                "Confirm NEW cold backup",
                plan.describe() +
                "\n\nCreate an additional copy of these files at:\n" + str(target) +
                "\n\nThe destination should be encrypted and must have adequate free space.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                self.recovery_log.setPlainText("Cancelled; no backup files created.")
                return
            self.recovery_log.setPlainText("Copying offline virtual disks and checking SHA-256…")
            self.work(
                lambda: ColdBackup().create(space.identifier, space.policy, target, confirmed=True),
                lambda saved: self.recovery_log.setPlainText(
                    f"Cold backup completed at: {saved}\n"
                    "Use Verify saved backup to check file hashes. "
                    "Recovery is manual, not automatic rollback."
                ),
                lambda msg: self.recovery_log.setPlainText("Backup failed or incomplete: " + msg),
            )
        self.work(
            lambda: ColdBackup().plan(space.identifier, space.policy),
            ready,
            lambda msg: self.recovery_log.setPlainText("Backup refused: " + msg),
        )

    def stage_backup_folder(self):
        source = QFileDialog.getExistingDirectory(
            self, "Select existing Nightglass cold backup", str(Path.home())
        )
        if not source:
            return
        parent = QFileDialog.getExistingDirectory(
            self, "Select writable parent folder for NEW restored copy", str(Path.home())
        )
        if not parent:
            return
        new_name, ok = QInputDialog.getText(
            self, "New recovered guest name",
            "Unique NEW libvirt guest identifier (not the original):",
            text="nightglass-recovered",
        )
        if not ok:
            return
        try:
            new_name = safe_name(new_name.strip())
        except WorkspaceError as exc:
            self.error(str(exc))
            return
        destination = Path(parent) / new_name
        self.recovery_log.setPlainText("Checking backup hashes and preparing a new offline VM plan …")
        def ready(plan):
            if QMessageBox.question(
                self, "Confirm NEW offline recovery staging",
                plan.describe() +
                "\n\nThis copies files but will NOT define or start the VM. Proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                self.recovery_log.setPlainText("Cancelled. No recovery staging created.")
                return
            self.recovery_log.setPlainText("Copying verified backup into new offline staging area …")
            self.work(
                lambda: RecoveryStager().stage(
                    Path(source), destination, new_name, confirmed=True
                ),
                lambda dest: self.recovery_log.setPlainText(
                    f"New offline recovery staged at: {dest}\n"
                    "No VM was defined or started. Review the generated domain.xml, "
                    "disk ownership, SELinux and firmware before importing in virt-manager. "
                    "Use Verify staged recovery to recheck SHA-256 integrity."
                ),
                lambda message: self.recovery_log.setPlainText(
                    "RECOVERY NOT COMPLETED: " + message
                ),
            )
        self.work(
            lambda: RecoveryStager().plan(Path(source), destination, new_name),
            ready,
            lambda message: self.recovery_log.setPlainText("Recovery refused: " + message),
        )

    def verify_recovery_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose staged Nightglass recovery", str(Path.home())
        )
        if not folder:
            return
        self.recovery_log.setPlainText("Rechecking staged recovery hashes and disconnected VM XML …")
        self.work(
            lambda: verify_staging(Path(folder)),
            lambda report: self.recovery_log.setPlainText(
                "RECOVERY STAGING VERIFIED — OFFLINE XML\n"
                + "\n".join(report) +
                "\n\nThis does not prove the VM boots or is securely isolated after manual import."
            ),
            lambda message: self.recovery_log.setPlainText("RECOVERY VERIFICATION FAILED: " + message),
        )

    def preflight_recovery_folder(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select staged Nightglass recovery for read-only Fedora checks", str(Path.home())
        )
        if not directory:
            return
        self.recovery_log.setPlainText("Validating local schema, image headers and KVM readiness …")
        self.work(
            lambda: RecoveryReadiness().check(Path(directory)),
            lambda report: self.recovery_log.setPlainText(report.describe()),
            lambda message: self.recovery_log.setPlainText(
                "FEDORA IMPORT PREFLIGHT BLOCKED: " + message +
                "\nNo VM was registered, started, or changed."
            ),
        )

    def inspect_registered_guest(self):
        guest, ok = QInputDialog.getText(
            self, "Read-only registered guest audit", "Exact registered VM name:"
        )
        if not ok:
            return
        try:
            guest = safe_name(guest.strip())
        except WorkspaceError as exc:
            self.error(str(exc))
            return
        policy, policy_ok = QInputDialog.getItem(
            self, "Choose audit policy", "Inspect registered guest as:",
            ["isolated", "lab"], 0, False
        )
        if not policy_ok:
            return
        self.last_acceptance = None
        self.recovery_log.setPlainText(
            "Inspecting registered guest (current, inactive and saved-state XML only) …"
        )
        def received(report):
            self.last_acceptance = report
            self.recovery_log.setPlainText(
                report.describe() +
                "\n\nYou may save this evidence locally. Unperformed network and boot tests "
                "remain explicitly marked NOT VERIFIED."
            )
        self.work(
            lambda: RegisteredGuestAuditor().inspect(guest, policy),
            received,
            lambda message: self.recovery_log.setPlainText(
                "VM AUDIT UNAVAILABLE: " + message +
                "\nNo VM was started or modified."
            ),
        )

    def verify_registered_handoff(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose verified recovery staging directory for read-only registered VM comparison"
        )
        if not folder:
            return
        self.last_acceptance = None
        self.recovery_log.setPlainText(
            "Verifying staged file hashes, registered VM disk paths, driver formats, "
            "UUIDs and offline policy. No guest will be started or modified …"
        )
        def received(report):
            self.last_acceptance = report
            self.recovery_log.setPlainText(
                report.describe() +
                "\n\nLocal audit evidence can be saved as a NEW private JSON file. "
                "A passing metadata handoff is not a Fedora/KVM runtime isolation test."
            )
        self.work(
            lambda: RecoveryHandoff().inspect(Path(folder)),
            received,
            lambda message: self.recovery_log.setPlainText(
                "REGISTERED HANDOFF UNAVAILABLE: " + message +
                "\nNo guest or staged file was modified."
            ),
        )

    def export_acceptance_report(self):
        if self.last_acceptance is None:
            self.error("Run Audit registered VM before saving evidence.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Choose a NEW local audit report",
            str(Path.home() / ("nightglass-" + self.last_acceptance.guest + "-audit.json")),
            "JSON files (*.json)",
        )
        if not filename:
            return
        try:
            target = save_acceptance(self.last_acceptance, Path(filename))
        except (ToolError, OSError) as exc:
            self.error(str(exc))
            return
        self.inform(
            "Evidence saved locally: " + str(target) +
            "\nNo information was uploaded. Existing reports are never overwritten."
        )

    def verify_backup_folder(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select a Nightglass cold backup folder", str(Path.home())
        )
        if not directory:
            return
        self.recovery_log.setPlainText("Hashing backup assets (read-only) …")
        self.work(
            lambda: verify_backup(Path(directory)),
            lambda lines: self.recovery_log.setPlainText(
                "BACKUP FILE INTEGRITY VERIFIED\n"
                + "\n".join(lines)
                + "\n\nThis is NOT proof of successful restoration. "
                "Test restore on a separate target first."
            ),
            lambda msg: self.recovery_log.setPlainText("BACKUP VERIFICATION FAILED: " + msg),
        )

    def goto(self, index: int):
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        self.header_title.setText(["Security workspaces", "Trust boundaries", "System diagnostics", "Machine settings", "Offline VM preparation", "VM backups"][index])
        if index == 2:
            self.check_host()
            self.refresh_resources()

    def get_space(self, key: str) -> Workspace:
        return next(w for w in self.spaces if w.key == key)

    def refresh(self):
        if self._busy:
            return
        self._busy = True
        def query():
            result = {}
            try:
                domains = set(self.hv.list_domains())
                domains_error = ""
            except ToolError as exc:
                domains, domains_error = set(), str(exc)
            try:
                boxes = set(self.containers.list_names())
                box_error = ""
            except ToolError as exc:
                boxes, box_error = set(), str(exc)
            for space in self.spaces:
                if space.kind == "host":
                    result[space.key] = ("Active host", "Not VM isolated", True, True)
                elif space.kind == "distrobox":
                    result[space.key] = (("Backend unavailable" if box_error else ("Available" if space.identifier in boxes else "Not created")),
                                         "Shares the host filesystem and display; trusted projects only" if not box_error else box_error,
                                         not bool(box_error), space.identifier in boxes)
                elif domains_error:
                    result[space.key] = ("Unavailable", domains_error, False, False)
                elif space.identifier not in domains:
                    result[space.key] = ("VM not found", f"Bind a defined libvirt VM to '{space.key}'", False, False)
                else:
                    try:
                        state = self.hv.state(space.identifier)
                        running = state.lower().startswith(("running", "paused", "idle"))
                        audit = self.hv.audit(space.identifier, space.policy)
                        details = ("Configuration and saved session approved" if audit.saved_state else "Configuration approved") if audit.ok else "POLICY BLOCK: " + "; ".join(audit.warnings)
                        if audit.saved_state and not running:
                            state = "Saved session — audited resume available"
                        result[space.key] = (state, details, audit.ok, running)
                    except ToolError as exc:
                        result[space.key] = ("Status error", str(exc), False, False)
            return result
        def received(states):
            self._busy = False
            for key, data in states.items():
                if key in self.cards:
                    self.cards[key].update_status(*data)
        self.work(query, received, lambda e: (setattr(self, "_busy", False), self.error(e)))

    def error(self, message):
        QMessageBox.warning(self, "Nightglass", message)

    def inform(self, message):
        QMessageBox.information(self, "Nightglass", message)

    def open_program(self, command: list[str]):
        if shutil.which(command[0]) is None:
            self.error(f"Not installed: {command[0]}")
            return
        try:
            subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, shell=False)
        except OSError as exc:
            self.error(str(exc))

    def launch_space(self, key: str):
        space = self.get_space(key)
        if space.kind == "host":
            self.inform("You're already on the personal host. For stronger personal isolation, run personal apps inside separate VMs on a higher-memory system.")
            return
        if space.kind == "distrobox":
            def prepare():
                if space.identifier not in self.containers.list_names():
                    self.containers.create(space.identifier)
                return space.identifier
            if QMessageBox.question(self, "Trusted environment", "Distrobox shares host data and display services. Proceed only with trusted development tools?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            self.work(prepare, lambda name: (self.open_program(["konsole", "-e", "distrobox", "enter", "--name", name]), self.refresh()), self.error)
            return
        if QMessageBox.question(self, "Start virtual machine", f"Start {space.name}? Nightglass will validate its current XML and network policy before issuing the start command.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.work(lambda: self.hv.start(space.identifier, space.policy), lambda msg: (self.inform(msg), self.refresh()), self.error)

    def shutdown_space(self, key: str):
        space = self.get_space(key)
        if QMessageBox.question(self, "Guest shutdown", f"Ask {space.name} to shut down gracefully? Unsaved guest changes may be lost if its OS ignores shutdown.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.work(lambda: self.hv.shutdown(space.identifier), lambda msg: (self.inform(msg), self.refresh()), self.error)

    def save_space(self, key: str):
        space = self.get_space(key)
        if space.policy == "isolated":
            self.error("Memory-state saving is disabled for potentially malicious guests. Shut down and restore them from a clean baseline instead.")
            return
        if QMessageBox.question(self, "Save VM memory state", f"Suspend {space.name} by saving memory to disk? This consumes storage, persists sensitive RAM, and is not a snapshot or backup.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.work(lambda: self.hv.managed_save(space.identifier, space.policy), lambda msg: (self.inform(msg), self.refresh()), self.error)

    def view_space(self, key: str):
        space = self.get_space(key)
        self.open_program(["virt-viewer", "--connect", "qemu:///system", space.identifier])

    def bind_space(self, key: str):
        space = self.get_space(key)
        name, ok = QInputDialog.getText(self, "Bind existing libvirt domain", f"Exact VM name for {space.name} (must already exist in qemu:///system):", text=space.identifier)
        if not ok:
            return
        try:
            name = safe_name(name.strip())
        except WorkspaceError as exc:
            self.error(str(exc))
            return
        def verify():
            if name not in self.hv.list_domains():
                raise ToolError("No such libvirt VM. Create it first using virt-manager, then bind it.")
            # Save only after obtaining the current domain audit.
            return self.hv.audit(name, space.policy)
        def done(audit):
            if any(s.kind == "vm" and s.key != key and s.identifier == name for s in self.spaces):
                self.error("The same VM cannot be bound to two security workspaces.")
                return
            updated = [replace(s, identifier=name) if s.key == key else s for s in self.spaces]
            try:
                save_workspaces(updated)
            except (WorkspaceError, OSError) as exc:
                self.error(str(exc))
                return
            self.spaces = updated
            self.cards[key].space = self.get_space(key)
            self.inform("VM bound. " + ("Launch policy currently passes." if audit.ok else "Start will be blocked until these settings are fixed:\n" + "\n".join(audit.warnings)))
            self.refresh()
        self.work(verify, done, self.error)

    def refresh_resources(self, *, activate: bool = False):
        if activate:
            self._resource_monitor_enabled = True
        if (not self._resource_monitor_enabled
                or self._resource_monitor_busy
                or self.stack.currentIndex() != 2):
            return
        self._resource_monitor_busy = True
        self.resource_status.setText("Checking host RAM and libvirt …")
        def received(snapshot):
            self._resource_monitor_busy = False
            self.resource_status.setText(
                "Resource status: " + snapshot.level +
                "  ·  " + str(len(snapshot.active_vms)) + " active VM(s)"
            )
            self.resource_details.setPlainText(snapshot.describe())
        def failed(message):
            self._resource_monitor_busy = False
            self.resource_status.setText("Resource status: UNKNOWN")
            self.resource_details.setPlainText(
                "READ-ONLY INSPECTION UNAVAILABLE: " + message +
                "\nDo not assume that launching another VM is safe."
            )
        self.work(
            lambda: collect_resources(workspaces=tuple(self.spaces)),
            received, failed,
        )

    def observe_guest_runtime_labels(self):
        guest, ok = QInputDialog.getText(
            self, "Read-only runtime sVirt observation",
            "Name of an ALREADY-running benign registered VM:"
        )
        if not ok:
            return
        try:
            guest = safe_name(guest.strip())
        except WorkspaceError as exc:
            self.error(str(exc))
            return
        policy, policy_ok = QInputDialog.getItem(
            self, "Restricted VM policy", "Observe guest as:",
            ["isolated", "lab"], 0, False
        )
        if not policy_ok:
            return
        self.last_acceptance = None
        self.diagnostics.setPlainText("Observing registered libvirt and host SELinux metadata (read-only) …")
        def received(report):
            self.last_acceptance = report
            self.diagnostics.setPlainText(
                report.describe() + "\n\nUse Save local runtime observation for a "
                "NEW private JSON record. Effective process labels and guest traffic remain untested."
            )
        self.work(
            lambda: RuntimeLabelInspector().inspect(guest, policy),
            received,
            lambda message: self.diagnostics.setPlainText(
                "RUNTIME LABEL OBSERVATION UNAVAILABLE: " + message +
                "\nNo VM was started or changed."
            ),
        )

    def check_host_security(self):
        self.posture_summary.setText("Inspecting nonprivileged host security state …")
        self.work(
            inspect_host_posture,
            lambda report: (
                self.posture_summary.setText(
                    "Host review: " + ("checks observed; runtime isolation unverified"
                                       if report.complete else "attention required")
                ),
                self.diagnostics.setPlainText(report.describe())
            ),
            lambda message: (
                self.posture_summary.setText("Host review: UNKNOWN"),
                self.diagnostics.setPlainText(
                    "Host security posture unavailable: " + message +
                    "\nNo configuration was changed."
                )
            ),
        )

    def check_host(self):
        self.diagnostics.setPlainText("Inspecting read-only host state …")
        def gather():
            checks = collect_checks()
            rows = [("PASS" if ch.ok else "WARN") + f"  {ch.name:24s} {ch.message}" for ch in checks]
            return "\n".join(rows) + "\n\n" + resource_advice() + "\n\nThis is a readiness check, not a certified security audit."
        self.work(gather, self.diagnostics.setPlainText, self.error)


def run_gui() -> int:
    if os.name != "posix":
        print("Nightglass desktop controller is built for Fedora Linux; use doctor/list from other OSes.")
        return 2
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("Nightglass must run as an unprivileged desktop user, never as root.")
        return 2
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    try:
        window = MainWindow()
    except (WorkspaceError, OSError) as exc:
        print(f"Unable to load configuration: {exc}")
        return 2
    window.show()
    return app.exec()
