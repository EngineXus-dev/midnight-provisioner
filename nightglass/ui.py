"""Compact cyberpunk-inspired KDE controller. Only opt-in, guarded actions mutate VMs."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import replace
from functools import partial
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea, QStackedWidget,
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

STYLE = """
QWidget { background: #0b0e13; color: #dce5e9; font-family: 'Noto Sans', 'DejaVu Sans', sans-serif; font-size: 12px; }
QMainWindow { background: #0b0e13; }
QFrame#Sidebar { background: #10151c; border-right: 1px solid #253038; }
QFrame#WorkspaceCard { background: #121a22; border: 1px solid #293944; border-radius: 16px; }
QFrame#WorkspaceCard:hover { border-color: #3b6472; }
QFrame#Panel { background: #121a22; border: 1px solid #293944; border-radius: 14px; }
QPushButton { background: #1a2833; color: #d6e8ed; border: 1px solid #33505d; padding: 9px 12px; border-radius: 8px; }
QPushButton:hover { border-color: #57d5ce; background: #223642; }
QPushButton:disabled { color: #61717a; background: #141b22; border-color: #222c32; }
QPushButton#Primary { color: #091718; background: #5bd9cf; border: none; font-weight: 700; }
QPushButton#Primary:hover { background: #83efe6; }
QPushButton#Danger { color: #f5b8b5; border-color: #6c3c48; }
QLabel#Title { color: #f2f7f8; font-size: 24px; font-weight: 750; }
QLabel#Brand { color: #68e0d8; font-size: 23px; font-weight: 800; letter-spacing: 2px; }
QLabel#SubTitle { color: #88a3b0; font-size: 12px; }
QLabel#CardTitle { color: #f1fafb; font-size: 16px; font-weight: 700; }
QLabel#Badge { background: #18323b; border: 1px solid #315563; color: #8ce5df; padding: 4px 8px; border-radius: 7px; }
QPlainTextEdit { background: #101820; color: #bed5db; border: 1px solid #334952; border-radius: 9px; padding: 8px; font-family: 'Monospace'; }
QComboBox { background: #1a2833; color: #dce5e9; padding: 8px; border: 1px solid #34505d; border-radius: 8px; }
QScrollArea { border: none; }
QScrollBar:vertical { background: #11191f; width: 10px; }
QScrollBar::handle:vertical { background: #34454d; border-radius: 4px; }
"""


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
        self.state.setStyleSheet("color: #8daab5")
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
            outer.addLayout(more)
        else:
            self.save = self.viewer = None

    def update_status(self, status: str, explanation: str, can_start: bool, running: bool):
        self.state.setText("● " + status)
        self.state.setStyleSheet("color: " + ("#72ddb8" if running else ("#e0b27e" if not can_start else "#a2c5d2")))
        self.policy.setText(explanation[:220])
        self.launch.setEnabled((can_start and not running) if self.space.kind == "vm" else can_start)
        if self.stop:
            self.stop.setEnabled(running)
        if self.viewer:
            self.viewer.setEnabled(running)
        if self.save:
            self.save.setEnabled(running and self.space.policy != "isolated")


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
        self._build()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(30000)
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
        slogan.setStyleSheet("color: #67818e; font-size: 9px; letter-spacing: 0.7px")
        side.addWidget(slogan)
        side.addSpacing(26)
        self.stack = QStackedWidget()
        nav = [("▦  Workspaces", 0), ("◇  Security model", 1), ("✦  Diagnostics", 2), ("⚙  Machine settings", 3)]
        for label, index in nav:
            button = QPushButton(label)
            button.setMinimumHeight(43)
            button.clicked.connect(partial(self.goto, index))
            side.addWidget(button)
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
        footer.setStyleSheet("color: #607681; font-size: 10px")
        footer.setWordWrap(True)
        right.addWidget(footer)
        main.addWidget(pages, 1)
        self._build_workspaces()
        self._build_security()
        self._build_diagnostics()
        self._build_machine()

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
            head.setStyleSheet("color: #70d9d1; font-weight: 700; letter-spacing: 1px")
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
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setPlaceholderText("Select 'Run checks' to inspect host readiness")
        layout.addWidget(self.diagnostics, 1)
        run = QPushButton("Run checks")
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
        title.setStyleSheet("color: #70d9d1; font-weight: 700")
        inner.addWidget(title)
        self.profile_combo = QComboBox()
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
        head.setStyleSheet("color: #70d9d1; font-weight: 700")
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

    def preview_machine_profile(self, *_):
        mode = self.profile_combo.currentData() or "auto"
        prefs = MachinePreferences(preset=mode)
        self.profile_summary.setText(
            current_budget(prefs).explain() +
            "\nLimits apply to future VM starts through Nightglass; existing VM RAM allocations aren't rewritten."
        )

    def save_machine_profile(self):
        mode = self.profile_combo.currentData() or "auto"
        try:
            prefs = MachinePreferences(
                preset=mode,
                automatic_update_checks=self.update_opt_in.isChecked(),
            )
            save_machine_preferences(prefs)
        except (WorkspaceError, OSError) as exc:
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

    def goto(self, index: int):
        self.stack.setCurrentIndex(index)
        self.header_title.setText(["Security workspaces", "Trust boundaries", "System diagnostics", "Machine settings"][index])
        if index == 2:
            self.check_host()

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
    app.setStyleSheet(STYLE)
    try:
        window = MainWindow()
    except (WorkspaceError, OSError) as exc:
        print(f"Unable to load configuration: {exc}")
        return 2
    window.show()
    return app.exec()
