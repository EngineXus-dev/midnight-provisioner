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
from .kali_templates import get_template, list_templates, plan_template
from .kali_setup import build_setup_plan, save_setup_plan, load_setup_plan, compare_inventory_files, guest_inventory_instructions
from .kali_preflight import KaliPreflight
from .kali_registration import KaliRegistrationInspector
from .kali_cold_baseline import KaliColdBaselineInspector
from .kali_recovery_link import KaliRecoveryLink
from .kali_recovery_registration import KaliRecoveryRegistrationInspector
from .kali_running import KaliRunningInspector
from .kali_process_label import KaliProcessLabelInspector
from .kali_drift import compare_version_lock_files
from .backups import ColdBackup, verify_backup
from .recovery import RecoveryStager, verify_staging
from .readiness import RecoveryReadiness
from .acceptance import RegisteredGuestAuditor, save_acceptance
from .handoff import RecoveryHandoff
from .theme import apply_theme, COLORS
from .resources import collect_resources
from .host_posture import inspect_host_posture
from .runtime_labels import RuntimeLabelInspector
from .system_discovery import collect_system, describe as describe_discovery
from .install_disclosure import disclosure_for, ACKNOWLEDGMENT
from .install_target_preview import build_target_preview, describe_target_preview
from .install_change_review import build_change_review, describe_change_review
from .install_encryption import CHOICES as ENCRYPTION_CHOICES, LABELS as ENCRYPTION_LABELS
from .install_proposal_review import read_proposal_file, review_proposal, describe_proposal, ProposalError

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
        self.discovery_snapshot = None  # volatile; never saved or installed from
        self._resource_monitor_enabled = False
        self._resource_monitor_busy = False
        self._build()
        self.refresh()
        # Automatically recognize the host on startup; no personal-folder names
        # or write-capable action is accessed without a separate user opt-in.
        if os.environ.get("NIGHTGLASS_GUI_SMOKE") != "1":
            QTimer.singleShot(400, self.begin_system_discovery)
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda *_args: self.refresh())
        self.timer.start(30000)
        self.resource_timer = QTimer(self)
        self.resource_timer.timeout.connect(lambda *_args: self.refresh_resources())
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
        nav = [("▦  Workspaces", 0), ("◇  Security model", 1), ("✦  Diagnostics", 2), ("⚙  Machine settings", 3), ("⬡  Prepare VM", 4), ("↺  Backup & verify", 5), ("⌕  System discovery", 6)]
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
        refresh.clicked.connect(lambda *_args: self.refresh())
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
        self._build_discovery()

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
        # Security evidence can grow longer than a compact laptop screen.
        # Scroll the whole page rather than clipping lower inspection controls.
        page = QScrollArea()
        page.setWidgetResizable(True)
        shell = QWidget()
        layout = QVBoxLayout(shell)
        layout.setSpacing(12)
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
        posture_button.clicked.connect(lambda *_args: self.check_host_security())
        posture_layout.addWidget(posture_button)
        observe = QPushButton("Observe running VM sVirt labels")
        observe.setToolTip(
            "Observe SELinux and libvirt label metadata of an ALREADY-running, "
            "registered restricted VM. Never starts the guest or verifies actual process confinement."
        )
        observe.clicked.connect(lambda *_args: self.observe_guest_runtime_labels())
        posture_layout.addWidget(observe)
        save_observation = QPushButton("Save local runtime observation")
        save_observation.setToolTip("Save the last metadata report privately without overwriting files.")
        save_observation.clicked.connect(lambda *_args: self.export_acceptance_report())
        posture_layout.addWidget(save_observation)
        layout.addWidget(posture_panel)
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setPlaceholderText("Select 'Run host checks' to inspect host readiness")
        layout.addWidget(self.diagnostics, 1)
        run = QPushButton("Run host checks")
        run.clicked.connect(lambda *_args: self.check_host())
        layout.addWidget(run)
        page.setWidget(shell)
        self.stack.addWidget(page)

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
            widget.textChanged.connect(lambda *_args: self.preview_machine_profile())
        inner.addLayout(controls)
        self.profile_summary = QLabel("")
        self.profile_summary.setWordWrap(True)
        inner.addWidget(self.profile_summary)
        self.profile_combo.currentIndexChanged.connect(lambda *_args: self.preview_machine_profile())
        save = QPushButton("Save machine profile")
        save.setObjectName("Primary")
        save.clicked.connect(lambda *_args: self.save_machine_profile())
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
        check.clicked.connect(lambda *_args: self.check_updates())
        actions.addWidget(check)
        apply = QPushButton("Install available update")
        apply.clicked.connect(lambda *_args: self.apply_update())
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
        self.provision_template = NoWheelComboBox()
        self.provision_template.addItem("Custom Kali — no tool bundle", None)
        for template in list_templates():
            self.provision_template.addItem(
                ("WHITE HAT  ·  " if template.category == "white-hat" else "RED TEAM  ·  ")
                + template.name, template.identifier
            )
        self.provision_template.setToolTip(
            "Curated package lists only. Every preset is a separate, initially OFFLINE Kali VM. "
            "Nothing is installed until you manually approve it inside that guest."
        )
        self.provision_name = QLineEdit("nightglass-kali")
        self.provision_name.setPlaceholderText("Unique VM name")
        self.provision_iso = QLineEdit()
        self.provision_iso.setPlaceholderText("Select downloaded Linux .iso file")
        iso_row = QHBoxLayout()
        iso_row.addWidget(self.provision_iso, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(lambda *_args: self.choose_provision_iso())
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
        self.provision_kind.currentIndexChanged.connect(lambda *_args: self.provision_kind_changed())
        self.provision_template.currentIndexChanged.connect(lambda *_args: self.provision_template_changed())
        specs = [
            ("Workspace type", self.provision_kind),
            ("Kali toolkit (one VM per template)", self.provision_template),
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
        template_info = QHBoxLayout()
        self.kali_template_note = QLabel(
            "Choose a compact Kali toolkit; all packages are suggestions for one "
            "separate VM and are NOT installed by Nightglass."
        )
        self.kali_template_note.setObjectName("SubTitle")
        self.kali_template_note.setWordWrap(True)
        template_info.addWidget(self.kali_template_note, 1)
        view_template = QPushButton("View toolkit details")
        view_template.clicked.connect(lambda *_args: self.show_kali_template())
        template_info.addWidget(view_template)
        layout.addLayout(template_info)
        plan_actions = QHBoxLayout()
        save_plan = QPushButton("Save private Kali setup plan")
        save_plan.clicked.connect(lambda *_args: self.save_kali_setup_plan())
        save_plan.setToolTip(
            "Write a NEW private JSON record of a selected template and separate VM; "
            "package versions are unknown and no software is installed."
        )
        plan_actions.addWidget(save_plan)
        compare_plan = QPushButton("Compare guest inventory")
        compare_plan.clicked.connect(lambda *_args: self.compare_kali_guest_inventory())
        compare_plan.setToolTip(
            "Read a setup plan and manually exported guest package inventory JSON. "
            "No VM or guest commands are executed; supplied metadata is untrusted."
        )
        plan_actions.addWidget(compare_plan)
        guest_help = QPushButton("Guest inventory instructions")
        guest_help.setToolTip(
            "Show manual read-only Kali package inventory steps. "
            "No host/guest transfer, commands or packages run."
        )
        guest_help.clicked.connect(lambda *_args: self.show_guest_inventory_instructions())
        plan_actions.addWidget(guest_help)
        plan_actions.addStretch()
        layout.addLayout(plan_actions)
        drift_actions = QHBoxLayout()
        drift_button = QPushButton("Review package version drift")
        drift_button.setToolTip(
            "Compare an existing Kali setup plan, previously saved version lock, "
            "and a newly supplied guest inventory. No guest operations or file writes."
        )
        drift_button.clicked.connect(lambda *_args: self.review_kali_version_drift())
        drift_actions.addWidget(drift_button)
        drift_note = QLabel("Three local JSON files · self-reported metadata, not attestation")
        drift_note.setObjectName("SubTitle")
        drift_note.setWordWrap(True)
        drift_actions.addWidget(drift_note, 1)
        layout.addLayout(drift_actions)

        controls = QHBoxLayout()
        self.provision_preview_button = QPushButton("Verify ISO + preview VM")
        self.provision_preview_button.setObjectName("Primary")
        self.provision_preview_button.clicked.connect(lambda *_args: self.preview_provision())
        controls.addWidget(self.provision_preview_button)
        kali_actions = QGridLayout()
        kali_actions.setHorizontalSpacing(8)
        kali_actions.setVerticalSpacing(8)
        self.kali_preflight_button = QPushButton("Check Kali VM readiness")
        self.kali_preflight_button.setToolTip(
            "Check a SAVED Kali plan, local ISO hash, both offline VM XML stages, "
            "host RAM, other running VMs and a chosen storage volume. "
            "No guest, disk, VM definition or network is created."
        )
        self.kali_preflight_button.clicked.connect(lambda *_args: self.check_kali_template_readiness())
        kali_actions.addWidget(self.kali_preflight_button, 0, 0)
        registered = QPushButton("Audit installed Kali template VM")
        registered.setToolTip(
            "Read-only inspection of an already manually installed, shut-off "
            "Kali VM against its saved template and separate qcow2 disk. "
            "No guest starts or file changes."
        )
        registered.clicked.connect(lambda *_args: self.audit_registered_kali_template())
        kali_actions.addWidget(registered, 0, 1)
        baseline = QPushButton("Verify Kali cold backup")
        baseline.setToolTip(
            "Read-only binding of a manually installed, shut-off Kali VM and "
            "its independent qcow2 disk to an existing hash-verified cold backup. "
            "Does not make a backup, restore or boot."
        )
        baseline.clicked.connect(lambda *_args: self.verify_kali_cold_baseline())
        kali_actions.addWidget(baseline, 0, 2)
        link_button = QPushButton("Verify Kali recovery copy")
        link_button.setToolTip(
            "Read-only: compare a separate NEW offline recovery staging folder "
            "against the original Kali cold backup and saved template. "
            "Does not restore, define, import or boot any guest."
        )
        link_button.clicked.connect(lambda *_args: self.check_kali_recovery_link())
        kali_actions.addWidget(link_button, 1, 0)
        registered_recovery = QPushButton("Audit registered Kali recovery")
        registered_recovery.setToolTip(
            "Read-only validation of a MANUALLY registered, SHUT-OFF offline Kali "
            "recovery guest. Checks backup→stage→registered VM identity, libvirt "
            "autostart, and disk collisions. Does not start or change guests."
        )
        registered_recovery.clicked.connect(lambda *_args: self.audit_registered_kali_recovery())
        kali_actions.addWidget(registered_recovery, 1, 1)
        runtime_button = QPushButton("Observe running Kali recovery")
        runtime_button.setToolTip(
            "Read-only Fedora/libvirt sVirt and no-NIC metadata check for a benign "
            "recovery VM YOU have already started. Does not start, stop, install "
            "or access a guest. Does NOT hash an active qcow2 disk."
        )
        runtime_button.clicked.connect(lambda *_args: self.observe_running_kali_recovery())
        kali_actions.addWidget(runtime_button, 1, 2)
        label_button = QPushButton("Inspect effective QEMU sVirt label")
        label_button.setToolTip(
            "As an ordinary Fedora user, inspect one ALREADY running benign "
            "Kali QEMU process /proc/PID/attr/current. Confirm guest UUID/name "
            "and compare actual process context to libvirt. Never use sudo, "
            "start a VM, read guest files or hash the writable disk."
        )
        label_button.clicked.connect(lambda *_args: self.check_kali_qemu_process_label())
        kali_actions.addWidget(label_button, 2, 0)
        vm_manager = QPushButton("Open virt-manager")
        vm_manager.clicked.connect(lambda: self.open_program(["virt-manager", "--connect", "qemu:///system"]))
        controls.addWidget(vm_manager)
        layout.addLayout(controls)
        layout.addLayout(kali_actions)
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
        self.provision_template.setEnabled(kind == "pentest")
        if kind == "analysis":
            self.provision_name.setText("nightglass-malware")
        else:
            template_id = self.provision_template.currentData()
            self.provision_name.setText(
                get_template(template_id).default_name if template_id else "nightglass-kali"
            )
        self.provision_result.clear()

    def provision_template_changed(self, *_):
        if self.provision_kind.currentData() != "pentest":
            return
        template_id = self.provision_template.currentData()
        if template_id is None:
            self.provision_name.setText("nightglass-kali")
            self.provision_ram.clear()
            self.provision_cpus.clear()
            self.provision_disk.clear()
        else:
            template = get_template(template_id)
            self.provision_name.setText(template.default_name)
            # Leave RAM/vCPU as 'Auto' so the current machine budget wins;
            # a template's suggested cap is applied by plan_template().
            self.provision_ram.clear()
            self.provision_cpus.clear()
            self.provision_disk.setText(str(template.disk_gib))
        self.provision_result.clear()

    def show_guest_inventory_instructions(self):
        if self.provision_kind.currentData() != "pentest":
            self.provision_result.setPlainText(
                "Kali inventory collection is for manually installed benign pentest VMs only."
            )
            return
        template_id = self.provision_template.currentData()
        if not template_id:
            self.provision_result.setPlainText("Choose a curated Kali toolkit first.")
            return
        self.provision_result.setPlainText(guest_inventory_instructions(template_id))

    def save_kali_setup_plan(self):
        if self.provision_kind.currentData() != "pentest":
            self.error("Setup plans are for independently installed Kali guests, not malware analysis VMs.")
            return
        template_id = self.provision_template.currentData()
        if not template_id:
            self.error("Choose a curated Kali toolkit first.")
            return
        guest = self.provision_name.text().strip()
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save NEW Kali setup plan (not an installer)",
            str(Path.home() / (guest + "-setup-plan.json")),
            "JSON files (*.json)",
        )
        if not filename:
            return
        try:
            plan = build_setup_plan(
                template_id, guest=guest,
                iso_sha256=self.provision_sha.text().strip() or None,
            )
            target = save_setup_plan(plan, Path(filename))
        except (WorkspaceError, ToolError, ValueError, OSError) as exc:
            self.error(str(exc))
            return
        self.provision_result.setPlainText(
            f"Saved NEW private Kali template plan: {target}\n"
            "All package versions are UNKNOWN. Guest installation, disk creation, "
            "network connectivity and dependency auditing were NOT performed."
        )

    def compare_kali_guest_inventory(self):
        plan, _ = QFileDialog.getOpenFileName(
            self, "Select existing Kali setup plan JSON", "", "JSON files (*.json)"
        )
        if not plan:
            return
        inventory, _ = QFileDialog.getOpenFileName(
            self, "Select manually exported guest package inventory JSON", "",
            "JSON files (*.json)"
        )
        if not inventory:
            return
        self.provision_result.setPlainText(
            "Comparing two local JSON files without contacting or running any VM …"
        )
        self.work(
            lambda: compare_inventory_files(Path(plan), Path(inventory)),
            lambda report: self.provision_result.setPlainText(report.describe()),
            lambda message: self.provision_result.setPlainText(
                "GUEST INVENTORY UNVERIFIED — " + message +
                "\nNo software, guest or system settings were modified."
            ),
        )

    def review_kali_version_drift(self):
        if self.provision_kind.currentData() != "pentest":
            self.provision_result.setPlainText(
                "Package drift review applies only to separately provisioned benign Kali VMs."
            )
            return
        paths = []
        for caption in (
            "Select Kali setup plan JSON",
            "Select previously saved Kali package version lock",
            "Select NEW manually obtained guest inventory JSON",
        ):
            selected, _ = QFileDialog.getOpenFileName(
                self, caption, "", "JSON files (*.json)"
            )
            if not selected:
                return
            paths.append(Path(selected))
        self.provision_result.setPlainText(
            "Reviewing only three bounded local JSON files; no VM will be contacted …"
        )
        self.work(
            lambda: compare_version_lock_files(*paths),
            lambda result: self.provision_result.setPlainText(result.describe()),
            lambda message: self.provision_result.setPlainText(
                "KALI VERSION DRIFT UNVERIFIED — " + message +
                "\nNo guest, system configuration or file was modified."
            ),
        )

    def check_kali_template_readiness(self):
        if self.provision_kind.currentData() != "pentest":
            self.provision_result.setPlainText(
                "Kali readiness checks apply only to one selected authorized pentest VM."
            )
            return
        template_id = self.provision_template.currentData()
        if not template_id:
            self.provision_result.setPlainText("Select a curated Kali VM template first.")
            return
        iso = self.provision_iso.text().strip()
        guest = self.provision_name.text().strip()
        sha = self.provision_sha.text().strip().lower()
        if not iso or not sha:
            self.provision_result.setPlainText(
                "Select a local Kali ISO and enter its official SHA-256 digest first."
            )
            return
        manifest, _ = QFileDialog.getOpenFileName(
            self, "Select SAVED Kali setup plan JSON", "", "JSON files (*.json)"
        )
        if not manifest:
            return
        storage = QFileDialog.getExistingDirectory(
            self, "Select existing destination volume for an independent Kali VM disk"
        )
        if not storage:
            return
        self.kali_preflight_button.setEnabled(False)
        self.provision_result.setPlainText(
            "Checking private Kali setup plan, host resources, local ISO hash and "
            "both offline VM XML stages without creating any VM …"
        )
        def check():
            data = load_setup_plan(Path(manifest))
            if data["template_id"] != template_id or data["guest"] != guest:
                raise ToolError(
                    "Saved Kali manifest and selected toolkit/VM name differ; "
                    "never apply one guest's plan to another"
                )
            if data["claimed_installer_iso_sha256"] != sha:
                raise ToolError(
                    "ISO SHA-256 in saved manifest and GUI do not match; "
                    "export a new correctly verified plan"
                )
            return KaliPreflight().inspect(Path(manifest), Path(iso), Path(storage))
        def completed(report):
            self.kali_preflight_button.setEnabled(True)
            self.provision_result.setPlainText(report.describe())
        def failed(message):
            self.kali_preflight_button.setEnabled(True)
            self.provision_result.setPlainText(
                "KALI VM READINESS: BLOCKED / UNVERIFIED\n" + message +
                "\nNo disk, guest, VM definition or configuration was changed."
            )
        self.work(check, completed, failed)

    def audit_registered_kali_template(self):
        if self.provision_kind.currentData() != "pentest":
            self.provision_result.setPlainText(
                "Registered Kali template audits do not apply to malware analysis VMs."
            )
            return
        template_id = self.provision_template.currentData()
        if not template_id:
            self.provision_result.setPlainText("Choose a curated Kali VM profile first.")
            return
        manifest, _ = QFileDialog.getOpenFileName(
            self, "Choose existing Kali template setup plan", "",
            "JSON files (*.json)"
        )
        if not manifest:
            return
        disk, _ = QFileDialog.getOpenFileName(
            self, "Choose exact independent qcow2 disk of a SHUT-OFF Kali VM",
            "", "QEMU disks (*.qcow2)"
        )
        if not disk:
            return
        selected_name = self.provision_name.text().strip()
        self.provision_result.setPlainText(
            "Auditing the registered offline Kali VM, both libvirt definitions, "
            "independent disk and other registered VM disk sources …"
        )
        def check():
            data = load_setup_plan(Path(manifest))
            if data["guest"] != selected_name or data["template_id"] != template_id:
                raise ToolError(
                    "Selected Kali VM identity does not match saved template plan; "
                    "audit cannot be reused between guests"
                )
            return KaliRegistrationInspector().inspect(Path(manifest), Path(disk))
        self.work(
            check,
            lambda result: self.provision_result.setPlainText(result.describe()),
            lambda message: self.provision_result.setPlainText(
                "REGISTERED KALI TEMPLATE: BLOCKED / UNVERIFIED\n" + message +
                "\nNo VM or disk was started, changed or registered."
            ),
        )

    def verify_kali_cold_baseline(self):
        if self.provision_kind.currentData() != "pentest":
            self.provision_result.setPlainText(
                "Cold baseline checks are restricted to separately installed benign Kali guests."
            )
            return
        template_id = self.provision_template.currentData()
        if not template_id:
            self.provision_result.setPlainText("Choose a curated Kali VM profile first.")
            return
        plan_file, _ = QFileDialog.getOpenFileName(
            self, "Choose private Kali VM setup plan", "", "JSON files (*.json)"
        )
        if not plan_file:
            return
        disk_file, _ = QFileDialog.getOpenFileName(
            self, "Choose the registered SHUT-OFF Kali VM disk", "", "QEMU disks (*.qcow2)"
        )
        if not disk_file:
            return
        backup_folder = QFileDialog.getExistingDirectory(
            self, "Choose existing independent Nightglass cold backup folder"
        )
        if not backup_folder:
            return
        expected_guest = self.provision_name.text().strip()
        self.provision_result.setPlainText(
            "Hash-checking an existing cold Kali backup and comparing offline "
            "VM/disk/NVRAM metadata; no guest files will be changed …"
        )
        def run():
            data = load_setup_plan(Path(plan_file))
            if data["guest"] != expected_guest or data["template_id"] != template_id:
                raise ToolError("Cold baseline plan does not match the selected Kali VM/template")
            return KaliColdBaselineInspector().inspect(
                Path(plan_file), Path(disk_file), Path(backup_folder)
            )
        self.work(
            run,
            lambda report: self.provision_result.setPlainText(report.describe()),
            lambda message: self.provision_result.setPlainText(
                "KALI COLD BASELINE: BLOCKED / UNVERIFIED\n" + message +
                "\nNo backup or VM was created, restored, or modified."
            ),
        )

    def check_kali_recovery_link(self):
        if self.provision_kind.currentData() != "pentest":
            self.provision_result.setPlainText(
                "Kali recovery comparison is for separate benign Kali VM templates only."
            )
            return
        template_id = self.provision_template.currentData()
        if not template_id:
            self.provision_result.setPlainText("Choose a curated Kali toolkit first.")
            return
        plan, _ = QFileDialog.getOpenFileName(
            self, "Choose saved original Kali template setup plan", "",
            "JSON files (*.json)"
        )
        if not plan:
            return
        original = QFileDialog.getExistingDirectory(
            self, "Choose ORIGINAL verified Kali cold backup folder"
        )
        if not original:
            return
        staged = QFileDialog.getExistingDirectory(
            self, "Choose NEW already staged offline recovery folder"
        )
        if not staged:
            return
        guest = self.provision_name.text().strip()
        self.provision_result.setPlainText(
            "Verifying original and staged hashes and exact offline XML transformation …"
        )
        def check():
            data = load_setup_plan(Path(plan))
            if data["guest"] != guest or data["template_id"] != template_id:
                raise ToolError("Recovery source plan differs from selected Kali guest and profile")
            return KaliRecoveryLink().inspect(Path(plan), Path(original), Path(staged))
        self.work(
            check,
            lambda report: self.provision_result.setPlainText(report.describe()),
            lambda message: self.provision_result.setPlainText(
                "KALI RECOVERY LINK: BLOCKED / UNVERIFIED\n" + message +
                "\nNo VM, disk, backup or network was modified."
            ),
        )

    def audit_registered_kali_recovery(self):
        if self.provision_kind.currentData() != "pentest":
            self.provision_result.setPlainText(
                "Recovery registration audits apply to separate benign Kali VM templates only."
            )
            return
        template_id = self.provision_template.currentData()
        if not template_id:
            self.provision_result.setPlainText("Choose a curated Kali toolkit first.")
            return
        plan, _ = QFileDialog.getOpenFileName(
            self, "Original curated Kali setup plan", "", "JSON files (*.json)"
        )
        if not plan:
            return
        backup = QFileDialog.getExistingDirectory(
            self, "Choose the ORIGINAL hash-verified Kali cold backup"
        )
        if not backup:
            return
        staged = QFileDialog.getExistingDirectory(
            self, "Choose the separately staged, MANUALLY REGISTERED recovered guest"
        )
        if not staged:
            return
        guest = self.provision_name.text().strip()
        self.provision_result.setPlainText(
            "Checking original Kali plan, backup, offline recovery copy, "
            "registered guest policy and autostart (read-only) …"
        )
        def check():
            data = load_setup_plan(Path(plan))
            if data["guest"] != guest or data["template_id"] != template_id:
                raise ToolError(
                    "Original Kali template/guest differs from selected profile; "
                    "cannot reuse one guest's recovery evidence for another"
                )
            return KaliRecoveryRegistrationInspector().inspect(
                Path(plan), Path(backup), Path(staged)
            )
        self.work(
            check,
            lambda report: self.provision_result.setPlainText(report.describe()),
            lambda message: self.provision_result.setPlainText(
                "KALI REGISTERED RECOVERY: BLOCKED / UNVERIFIED\n" + message +
                "\nNo registered guest or backup was started, restored, or modified."
            ),
        )

    def observe_running_kali_recovery(self):
        if self.provision_kind.currentData() != "pentest":
            self.provision_result.setPlainText(
                "Running recovery observations are for benign, independent Kali pentest guests only."
            )
            return
        template_id = self.provision_template.currentData()
        if not template_id:
            self.provision_result.setPlainText("Choose a curated Kali VM template first.")
            return
        plan, _ = QFileDialog.getOpenFileName(
            self, "Original Kali template setup plan", "", "JSON files (*.json)"
        )
        if not plan:
            return
        backup = QFileDialog.getExistingDirectory(
            self, "Verified original cold backup (inactive files only)"
        )
        if not backup:
            return
        guest, accepted = QInputDialog.getText(
            self, "Manually running benign Kali guest",
            "Enter the NEW recovery VM name already started by the operator:"
        )
        if not accepted or not guest.strip():
            return
        disk, _ = QFileDialog.getOpenFileName(
            self, "Exact live recovery guest qcow2 (metadata only — never hashed)",
            "", "QEMU disk (*.qcow2)"
        )
        if not disk:
            return
        original_guest = self.provision_name.text().strip()
        self.provision_result.setPlainText(
            "Checking host/libvirt runtime metadata without interacting with "
            "the running Kali guest or hashing its writable disk …"
        )
        def check():
            data = load_setup_plan(Path(plan))
            if data["guest"] != original_guest or data["template_id"] != template_id:
                raise ToolError("Selected Kali source guest/template differs from saved setup plan")
            return KaliRunningInspector().inspect(
                Path(plan), Path(backup), guest.strip(), Path(disk)
            )
        self.work(
            check,
            lambda result: self.provision_result.setPlainText(result.describe()),
            lambda msg: self.provision_result.setPlainText(
                "KALI RUNNING-GUEST OBSERVATION: BLOCKED / UNVERIFIED\n" + msg +
                "\nNo VM, guest disk or host network was modified."
            ),
        )

    def check_kali_qemu_process_label(self):
        if self.provision_kind.currentData() != "pentest":
            self.provision_result.setPlainText(
                "QEMU process SELinux inspection is for manually running benign Kali VMs only."
            )
            return
        template_id = self.provision_template.currentData()
        if not template_id:
            self.provision_result.setPlainText("Choose a curated Kali toolkit first.")
            return
        plan, _ = QFileDialog.getOpenFileName(
            self, "Select original curated Kali setup plan", "", "JSON files (*.json)"
        )
        if not plan:
            return
        guest, accepted = QInputDialog.getText(
            self, "Observe an already running benign Kali recovery",
            "NEW manually running recovery guest name (not original guest):"
        )
        if not accepted or not guest.strip():
            return
        source_guest = self.provision_name.text().strip()
        self.provision_result.setPlainText(
            "Checking effective QEMU /proc SELinux process context as an ordinary "
            "Fedora user. Unreadable process metadata will BLOCK; no sudo fallback …"
        )
        def check():
            data = load_setup_plan(Path(plan))
            if data["guest"] != source_guest or data["template_id"] != template_id:
                raise ToolError("QEMU process-label plan differs from selected Kali source guest/profile")
            return KaliProcessLabelInspector().inspect(Path(plan), guest.strip())
        self.work(
            check,
            lambda report: self.provision_result.setPlainText(report.describe()),
            lambda msg: self.provision_result.setPlainText(
                "KALI QEMU PROCESS LABEL: BLOCKED / UNVERIFIED\n" + msg +
                "\nNo root access, VM lifecycle action, guest read or disk hash occurred."
            ),
        )

    def show_kali_template(self):
        if self.provision_kind.currentData() != "pentest":
            self.provision_result.setPlainText(
                "Malware analysis uses its own disconnected VM; Kali pentest "
                "templates must not be attached to it."
            )
            return
        template_id = self.provision_template.currentData()
        self.provision_result.setPlainText(
            get_template(template_id).describe() if template_id else
            "Custom Kali: no predefined tool bundle. The VM is initially "
            "disconnected. Existing checksum and virt-install dry-run checks apply."
        )

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
            kind = self.provision_kind.currentData()
            template_id = self.provision_template.currentData() if kind == "pentest" else None
            planner = (
                (lambda **kw: plan_template(template_id, **kw))
                if template_id else
                (lambda **kw: build_plan(kind, **kw))
            )
            plan = planner(
                iso_path=self.provision_iso.text().strip(),
                expected_sha256=self.provision_sha.text().strip(),
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
            info = "\n\n" + get_template(template_id).describe() if template_id else ""
            self.provision_result.setPlainText(preview.describe() + info)
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
        verify.clicked.connect(lambda *_args: self.verify_backup_folder())
        row.addWidget(verify)
        stage = QPushButton("Recover into NEW folder")
        stage.clicked.connect(lambda *_args: self.stage_backup_folder())
        row.addWidget(stage)
        stage_verify = QPushButton("Verify staged recovery")
        stage_verify.clicked.connect(lambda *_args: self.verify_recovery_folder())
        row.addWidget(stage_verify)
        host_check = QPushButton("Check Fedora import readiness")
        host_check.clicked.connect(lambda *_args: self.preflight_recovery_folder())
        row.addWidget(host_check)
        row.addStretch()
        layout.addLayout(row)
        acceptance_row = QHBoxLayout()
        inspect = QPushButton("Audit registered VM")
        inspect.clicked.connect(lambda *_args: self.inspect_registered_guest())
        acceptance_row.addWidget(inspect)
        handoff = QPushButton("Verify registered handoff")
        handoff.setToolTip(
            "Read-only check of a registered powered-off VM against the disk and "
            "NVRAM paths, identity and disk formats in a verified recovery folder. "
            "Does not start, register or change the VM."
        )
        handoff.clicked.connect(lambda *_args: self.verify_registered_handoff())
        acceptance_row.addWidget(handoff)
        export = QPushButton("Save local audit report")
        export.clicked.connect(lambda *_args: self.export_acceptance_report())
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

    def _build_discovery(self):
        """Read-only first-run recognition, with unknowns kept for user review."""
        page = QScrollArea()
        page.setWidgetResizable(True)
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(4, 5, 4, 10)
        layout.setSpacing(12)

        intro = QLabel(
            "FIRST-RUN SYSTEM RECOGNITION  ·  READ-ONLY\n"
            "Nightglass inspects host resources and local disk layout without "
            "selecting, mounting or modifying a disk. A disk with zero reported "
            "partitions is NOT automatically trusted as empty."
        )
        intro.setWordWrap(True)
        intro.setObjectName("SubTitle")
        layout.addWidget(intro)

        panel = QFrame()
        panel.setObjectName("Panel")
        controls = QVBoxLayout(panel)
        title = QLabel("INSTALLATION INTENT  ·  USER DECISION")
        title.setObjectName("SectionHeading")
        controls.addWidget(title)
        self.discovery_intent = NoWheelComboBox()
        self.discovery_intent.addItem("Not decided — default", "undecided")
        self.discovery_intent.addItem("Freshly format selected target (delete its data)", "format_target")
        self.discovery_intent.addItem("Alongside an existing OS (higher risk)", "coexist")
        self.discovery_intent.currentIndexChanged.connect(
            lambda *_args: self.preview_discovery_intent())
        controls.addWidget(self.discovery_intent)
        # Recorded in the plan only; Fedora's installer applies the encryption.
        self.discovery_encryption = NoWheelComboBox()
        for choice in ENCRYPTION_CHOICES:
            self.discovery_encryption.addItem("Linux disk encryption: " + ENCRYPTION_LABELS[choice], choice)
        self.discovery_encryption.setToolTip(
            "Planned in Fedora's installer ('Encrypt my data'). Verify later with: nightglass encryption-check")
        controls.addWidget(self.discovery_encryption)
        self.discovery_intent_status = QLabel("")
        self.discovery_intent_status.setWordWrap(True)
        self.discovery_intent_status.setObjectName("SubTitle")
        controls.addWidget(self.discovery_intent_status)
        self.discovery_format_warning = QLabel("")
        self.discovery_format_warning.setWordWrap(True)
        self.discovery_format_warning.setObjectName("SubTitle")
        controls.addWidget(self.discovery_format_warning)
        self.discovery_backup_acknowledged = QCheckBox(ACKNOWLEDGMENT)
        self.discovery_backup_acknowledged.setChecked(False)
        self.discovery_backup_acknowledged.setToolTip(
            "Acknowledges the data-loss notice only; NOT evidence of backups, "
            "safe target identity, or permission to format.")
        controls.addWidget(self.discovery_backup_acknowledged)
        target_label = QLabel("OBSERVED INSTALLATION TARGET  ·  PREVIEW ONLY")
        target_label.setObjectName("SectionHeading")
        controls.addWidget(target_label)
        self.discovery_target_combo = NoWheelComboBox()
        self.discovery_target_combo.addItem("No disk selected — scan first", None)
        self.discovery_target_combo.currentIndexChanged.connect(
            lambda *_args: self.discovery_backup_acknowledged.setChecked(False))
        controls.addWidget(self.discovery_target_combo)
        target_help = QLabel(
            "Selecting a disk only previews consequences. This index is not a "
            "permanent hardware identifier. Windows boot/system disks remain "
            "protected. The actual installer would have to verify hardware "
            "identity again immediately before any destructive operation.")
        target_help.setObjectName("SubTitle")
        target_help.setWordWrap(True)
        controls.addWidget(target_help)
        self.discovery_preview_button = QPushButton("Preview proposed disk changes — NO WRITES")
        self.discovery_preview_button.clicked.connect(
            lambda *_args: self.preview_target_plan())
        controls.addWidget(self.discovery_preview_button)
        self.discovery_target_preview = QPlainTextEdit()
        self.discovery_target_preview.setReadOnly(True)
        self.discovery_target_preview.setMinimumHeight(230)
        controls.addWidget(self.discovery_target_preview)
        change_title = QLabel("PROPOSED PARTITION / EFI / BOOT IMPACT  ·  UNKNOWN ITEMS HELD")
        change_title.setObjectName("SectionHeading")
        controls.addWidget(change_title)
        self.discovery_change_button = QPushButton("Review proposed installation impact — NO WRITES")
        self.discovery_change_button.clicked.connect(
            lambda *_args: self.preview_install_changes())
        controls.addWidget(self.discovery_change_button)
        self.discovery_change_review = QPlainTextEdit()
        self.discovery_change_review.setReadOnly(True)
        self.discovery_change_review.setMinimumHeight(340)
        controls.addWidget(self.discovery_change_review)
        proposal_heading = QLabel("USER-SUPPLIED OPERATION PROPOSAL  ·  UNTRUSTED")
        proposal_heading.setObjectName("SectionHeading")
        controls.addWidget(proposal_heading)
        proposal_note = QLabel(
            "Optional: manually open an untrusted proposal JSON from a future installer "
            "or the bundled example. It can be wrong or incomplete. This never "
            "executes operations or proves the target, EFI changes or backups.")
        proposal_note.setObjectName("SubTitle")
        proposal_note.setWordWrap(True)
        controls.addWidget(proposal_note)
        self.discovery_proposal_button = QPushButton(
            "Review local operation proposal JSON — NO WRITES")
        self.discovery_proposal_button.clicked.connect(
            lambda *_args: self.review_proposal_file())
        controls.addWidget(self.discovery_proposal_button)
        self.discovery_proposal_report = QPlainTextEdit()
        self.discovery_proposal_report.setReadOnly(True)
        self.discovery_proposal_report.setMinimumHeight(210)
        self.discovery_proposal_report.setPlainText(
            "NO PROPOSAL SELECTED. Nothing has been read or verified.")
        controls.addWidget(self.discovery_proposal_report)
        self.discovery_folder_names = QCheckBox(
            "Also inspect personal directory NAMES (opt-in; local only, no files read)")
        self.discovery_folder_names.setChecked(False)
        controls.addWidget(self.discovery_folder_names)
        self.discovery_button = QPushButton("Refresh read-only system discovery")
        self.discovery_button.setObjectName("Primary")
        self.discovery_button.clicked.connect(
            lambda *_args: self.begin_system_discovery())
        controls.addWidget(self.discovery_button)
        layout.addWidget(panel)

        self.discovery_status = QLabel(
            "Automatic resource and disk detection is scheduled; unknown facts require your review.")
        self.discovery_status.setObjectName("Badge")
        self.discovery_status.setWordWrap(True)
        layout.addWidget(self.discovery_status)
        self.discovery_output = QPlainTextEdit()
        self.discovery_output.setReadOnly(True)
        self.discovery_output.setMinimumHeight(290)
        self.discovery_output.setPlaceholderText(
            "No storage device is selected or certified. Review recognition results here.")
        layout.addWidget(self.discovery_output)
        warning = QLabel(
            "BACKUP RESPONSIBILITY: During a future OS installation, formatting "
            "the selected drive or partitions will delete data there. Nightglass "
            "will not create or verify your backups. It assumes you have backed "
            "up anything you want to keep yourself before allowing a destructive "
            "installation workflow. This discovery page cannot authorize formatting, "
            "OS installation or VM startup."
        )
        warning.setWordWrap(True)
        warning.setObjectName("SubTitle")
        layout.addWidget(warning)
        layout.addStretch()
        page.setWidget(holder)
        self.stack.addWidget(page)
        self.preview_discovery_intent()
        self.discovery_intent.currentIndexChanged.connect(
            lambda *_args: self.preview_target_plan())
        self.discovery_target_combo.currentIndexChanged.connect(
            lambda *_args: self.preview_target_plan())
        self.discovery_backup_acknowledged.stateChanged.connect(
            lambda *_args: self.preview_target_plan())
        self.discovery_encryption.currentIndexChanged.connect(
            lambda *_args: self.preview_target_plan())
        self.preview_target_plan()

    def preview_discovery_intent(self):
        intent = self.discovery_intent.currentData() or "undecided"
        explanations = {
            "undecided": (
                "UNDECIDED: target identity, current contents, encryption and "
                "boot path remain UNKNOWN. No installation is authorized."
            ),
            "format_target": (
                "PLANNED REFORMAT: a future installer would replace the selected "
                "drive or partitions, deleting existing data. This is the intended "
                "operation, NOT evidence that the disk is empty, safely identified "
                "or approved. You are personally responsible for backups."
            ),
            "coexist": (
                "ALONGSIDE EXISTING OS: partition and EFI/boot changes still risk "
                "data loss or loss of boot access. Your backups are your responsibility; "
                "the future installer must show its exact target and changes."
            ),
        }
        self.discovery_intent_status.setText(explanations.get(intent, explanations["undecided"]))
        self.discovery_format_warning.setText(disclosure_for(intent).warning)
        # An intent change invalidates the old acknowledgment. This checkbox
        # never grants write permission or asserts actual backup completeness.
        self.discovery_backup_acknowledged.setChecked(False)
        self.discovery_backup_acknowledged.setEnabled(intent != "undecided")

    def preview_target_plan(self):
        """No file writes, disk selection persisted, or install credentials."""
        target_index = self.discovery_target_combo.currentData()
        preview = build_target_preview(
            self.discovery_snapshot,
            target_index=target_index if type(target_index) is int else None,
            intent=self.discovery_intent.currentData() or "undecided",
            backup_warning_acknowledged=self.discovery_backup_acknowledged.isChecked(),
            encryption=self.discovery_encryption.currentData() or "undecided",
        )
        self.discovery_target_preview.setPlainText(describe_target_preview(preview))
        self.preview_install_changes(preview)
        return preview

    def preview_install_changes(self, preview=None):
        """Advisory only: never pass a disk index to a write-capable tool."""
        if preview is None:
            target_index = self.discovery_target_combo.currentData()
            preview = build_target_preview(
                self.discovery_snapshot,
                target_index=target_index if type(target_index) is int else None,
                intent=self.discovery_intent.currentData() or "undecided",
                backup_warning_acknowledged=self.discovery_backup_acknowledged.isChecked(),
                encryption=self.discovery_encryption.currentData() or "undecided",
            )
        review = build_change_review(preview)
        self.discovery_change_review.setPlainText(describe_change_review(review))
        return review

    def review_proposal_file(self):
        """Read only a small explicitly chosen local JSON file; never install."""
        selected, _filter = QFileDialog.getOpenFileName(
            self, "Review UNTRUSTED local installer proposal", str(Path.home()),
            "JSON documents (*.json)")
        if not selected:
            return
        self.discovery_proposal_report.setPlainText(
            "Inspecting supplied JSON schema locally. It cannot authorize writes.")
        try:
            report = review_proposal(read_proposal_file(Path(selected)))
        except ProposalError as exc:
            self.discovery_proposal_report.setPlainText(
                "PROPOSAL REJECTED: " + str(exc) +
                "\nNo installer or storage operation was performed.")
            return
        self.discovery_proposal_report.setPlainText(describe_proposal(report))

    def begin_system_discovery(self):
        if getattr(self, "_discovery_scanning", False):
            return
        # Invalidate previous disk indexes before collecting a fresh snapshot.
        # Disk numbers and physical connections may change.
        self.discovery_snapshot = None
        self.discovery_target_combo.clear()
        self.discovery_target_combo.addItem("No disk selected — scan in progress", None)
        self.discovery_backup_acknowledged.setChecked(False)
        self.discovery_target_preview.setPlainText(
            "Previous target selection discarded. A fresh snapshot must be reviewed.")
        self.discovery_change_review.setPlainText(
            "Previous installation-impact plan invalidated. No partition/EFI changes authorized.")
        self.discovery_proposal_report.setPlainText(
            "Hardware refreshed; previous proposal review discarded. Choose a file again.")
        self._discovery_scanning = True
        self.discovery_button.setEnabled(False)
        self.discovery_status.setText("Reading bounded host and storage metadata …")
        names = self.discovery_folder_names.isChecked()

        def finished(report):
            self._discovery_scanning = False
            self.discovery_button.setEnabled(True)
            self.discovery_snapshot = report
            self.discovery_target_combo.clear()
            self.discovery_target_combo.addItem("Choose observed disk to preview — none selected", None)
            if report.get("storage_query") == "OBSERVED":
                for index, disk in enumerate(report.get("disks", [])):
                    if not isinstance(disk, dict):
                        continue
                    label = (
                        str(disk.get("local_id", "UNKNOWN")) +
                        "  ·  approx " + str(disk.get("size_gib_approx")) +
                        " GiB  ·  " + str(disk.get("target_classification", "UNKNOWN"))
                    )
                    self.discovery_target_combo.addItem(label[:140], index)
            self.discovery_backup_acknowledged.setChecked(False)
            self.discovery_status.setText(
                "Observation complete; all disk targets UNVERIFIED. No changes made.")
            self.discovery_output.setPlainText(describe_discovery(report))
            self.preview_target_plan()
            # Folder names are visible only after explicit opt-in, never exported
            # to a file or shared automatically.
            if names:
                folders = []
                for entry in report["personal_folders"]:
                    found = entry.get("directory_names", [])
                    folders.append(
                        entry["category"] + " [" + entry["names_scan"] + "]: "
                        + (", ".join(found) if found else "(none observed)")
                    )
                self.discovery_output.appendPlainText(
                    "\nOpt-in private folder directory names:\n" + "\n".join(folders))
        def failed(message):
            self._discovery_scanning = False
            self.discovery_snapshot = None
            self.discovery_target_combo.clear()
            self.discovery_target_combo.addItem("Detection unavailable — no target", None)
            self.discovery_backup_acknowledged.setChecked(False)
            self.discovery_button.setEnabled(True)
            self.discovery_status.setText(
                "Detection unavailable — UNKNOWN, no disk or install approved.")
            self.discovery_output.setPlainText(
                "Automatic recognition failed safely. Review environment manually. "
                "No change was performed.")
            self.preview_target_plan()
        self.work(lambda: collect_system(include_folder_names=names),
                  finished, failed)

    def goto(self, index: int):
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        self.header_title.setText(["Security workspaces", "Trust boundaries", "System diagnostics", "Machine settings", "Offline VM preparation", "VM backups", "System discovery"][index])
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
