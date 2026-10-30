"""Dedicated Kali workspace view; delegates operations to the existing controller."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from .kali_setup import load_setup_plan, save_version_lock
from .kali_templates import get_template, list_templates
from .portability import load_machine_preferences, save_machine_preferences
from .runner import ToolError

STUDIO_THEMES = {
    "crimson": ("Crimson eclipse", "#f16a7e", "#321923"),
    "violet": ("Ultraviolet", "#b396ff", "#251d39"),
    "venom": ("Venom", "#86d9ad", "#162d25"),
}


class StudioTabs(QTabWidget):
    """Size the current workflow instead of reserving the full catalog height."""

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        page = self.currentWidget()
        if page is not None and page.layout() is not None:
            layout = page.layout()
            height = layout.totalHeightForWidth(max(200, self.width()))
            if height < 0:
                height = layout.sizeHint().height()
            return QSize(size.width(), height + self.tabBar().sizeHint().height() + 8)
        return size

    def sizeHint(self):
        return self.minimumSizeHint()


class KaliStudio(QScrollArea):
    """A dark, tabbed front end to the same validated Kali actions and form state."""

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setObjectName("KaliStudio")
        self.setWidgetResizable(True)
        self.profile_buttons = {}
        self.action_buttons = {}
        self.holder = QWidget()
        self.holder.setObjectName("StudioSurface")
        self.setWidget(self.holder)
        layout = QVBoxLayout(self.holder)
        layout.setContentsMargins(4, 0, 4, 12)
        layout.setSpacing(15)

        hero = QFrame()
        hero.setObjectName("StudioHero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        heading = QVBoxLayout()
        heading.setSpacing(5)
        heading.addWidget(self.label("MIDNIGHT  /  SECURITY LAB", "StudioKicker"))
        heading.addWidget(self.label("KALI STUDIO", "StudioTitle"))
        heading.addWidget(self.label("Small toolkits. Separate guests. A deliberate workflow.", "StudioMuted"))
        hero_layout.addLayout(heading, 1)
        seal = self.label("07\nTOOLKITS", "StudioSeal")
        seal.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(seal)
        layout.addWidget(hero)

        context = QHBoxLayout()
        self.selection = self.label("Choose a toolkit", "StudioSelection")
        context.addWidget(self.selection, 1)
        context.addWidget(self.label("OFFLINE FIRST", "StudioBadge"))
        layout.addLayout(context)

        self.tabs = StudioTabs()
        self.tabs.setObjectName("StudioTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(lambda _index: self.tabs.updateGeometry())
        layout.addWidget(self.tabs)
        self._build_catalog()
        self._build_setup()
        self._build_packages()
        self._build_recovery()
        self._build_runtime()
        self._build_appearance()

        output_heading = QHBoxLayout()
        output_heading.addWidget(self.label("ACTIVITY & RESULTS", "StudioKicker"), 1)
        clear = QPushButton("Clear")
        clear.clicked.connect(controller.provision_result.clear)
        output_heading.addWidget(clear)
        layout.addLayout(output_heading)
        self.result = QPlainTextEdit()
        self.result.setObjectName("StudioOutput")
        self.result.setReadOnly(True)
        self.result.setMinimumHeight(135)
        self.result.setMaximumHeight(210)
        self.result.setPlaceholderText("Choose a toolkit to begin. Checks and saved-plan results appear here.")
        self.result.setAccessibleName("Kali Studio activity and results")
        layout.addWidget(self.result)
        layout.addStretch()
        controller.provision_result.textChanged.connect(lambda *_: self.sync_result())
        controller.provision_template.currentIndexChanged.connect(lambda *_: self.sync_profile())
        controller.provision_name.textChanged.connect(lambda *_: self.sync_selection())
        self.sync_profile()
        self.sync_result()
        self.set_theme(load_machine_preferences().kali_studio_theme)

    @staticmethod
    def label(text, name):
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    def section(self, title, description):
        widget = QWidget()
        widget.setObjectName("StudioSection")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 18, 0, 4)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.label(title, "StudioHeading"))
        layout.addWidget(self.label(description, "StudioMuted"))
        self.tabs.addTab(widget, title)
        return layout

    def action(self, text, method, layout, *, primary=False):
        button = QPushButton(text)
        button.setObjectName("StudioPrimary" if primary else "StudioAction")
        button.setMinimumHeight(32)
        button.clicked.connect(lambda _checked=False: self.invoke(method))
        self.action_buttons[method] = button
        layout.addWidget(button)
        return button

    def invoke(self, method):
        self.controller.provision_kind.setCurrentIndex(
            self.controller.provision_kind.findData("pentest")
        )
        if method in {"verify_setup_plan", "save_package_snapshot"}:
            getattr(self, method)()
        else:
            getattr(self.controller, method)()

    def _build_catalog(self):
        layout = self.section("Toolkits", "Choose a focus. Each toolkit gets its own guest and independent disk.")
        grid = QGridLayout()
        grid.setSpacing(10)
        for index, template in enumerate(list_templates()):
            button = QPushButton()
            button.setCheckable(True)
            button.setObjectName("ToolkitCard")
            button.setAccessibleName(template.name)
            role = "WHITE HAT" if template.category == "white-hat" else "RED TEAM"
            button.setText(
                f"{role}  /  {template.identifier}\n{template.name.replace('&', '&&')}\n"
                f"{len(template.packages)} tools  ·  {template.ram_mib / 1024:g} GiB  ·  {template.vcpus} vCPU"
            )
            button.setToolTip(template.purpose + "\n" + ", ".join(template.packages))
            button.setMinimumHeight(104)
            button.clicked.connect(lambda _checked=False, key=template.identifier: self.select_profile(key))
            grid.addWidget(button, index // 2, index % 2)
            self.profile_buttons[template.identifier] = button
        custom = QPushButton("CUSTOM KALI\nYour own package selection\nSeparate guest · no predefined bundle")
        custom.setObjectName("ToolkitCard")
        custom.setCheckable(True)
        custom.setMinimumHeight(104)
        custom.clicked.connect(lambda: self.select_profile(None))
        grid.addWidget(custom, 3, 1)
        self.profile_buttons[None] = custom
        layout.addLayout(grid)
        self.packages = self.label("", "StudioPackages")
        layout.addWidget(self.packages)
        proceed = QPushButton("Configure selected toolkit  →")
        proceed.setObjectName("StudioPrimary")
        proceed.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        layout.addWidget(proceed)

    def linked_field(self, name, placeholder, *, numeric=None):
        original = getattr(self.controller, name)
        field = QLineEdit(original.text())
        field.setPlaceholderText(placeholder)
        field.setAccessibleName(placeholder)
        if numeric:
            field.setValidator(QIntValidator(*numeric, field))
        # setText does not emit textChanged when the text is unchanged.
        original.textChanged.connect(field.setText)
        field.textChanged.connect(original.setText)
        setattr(self, name, field)
        return field

    def _build_setup(self):
        layout = self.section("Setup", "Choose a local installer, save a plan, then check readiness before installing in virt-manager.")
        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        for row, (caption, name, placeholder) in enumerate((
            ("Guest identity", "provision_name", "Unique Kali VM name"),
            ("Installer ISO", "provision_iso", "Local Kali installer .iso"),
            ("Publisher SHA-256", "provision_sha", "Verified 64-character publisher checksum"),
        )):
            form.addWidget(self.label(caption, "StudioMuted"), row, 0)
            field = self.linked_field(name, placeholder)
            form.addWidget(field, row, 1)
            if name == "provision_iso":
                browse = QPushButton("Browse")
                browse.clicked.connect(lambda: self.controller.choose_provision_iso())
                form.addWidget(browse, row, 2)
        layout.addLayout(form)
        resources = QHBoxLayout()
        for caption, name, limit in (
            ("RAM / MiB", "provision_ram", (1024, 131072)),
            ("vCPU", "provision_cpus", (1, 128)),
            ("Disk / GiB", "provision_disk", (20, 256)),
        ):
            box = QVBoxLayout()
            box.addWidget(self.label(caption, "StudioKicker"))
            box.addWidget(self.linked_field(name, "Auto", numeric=limit))
            resources.addLayout(box)
        layout.addLayout(resources)
        layout.addWidget(self.label("Auto allocations follow the selected toolkit and your machine's resource limits.", "StudioMuted"))
        buttons = QGridLayout()
        actions = [
            ("Save private Kali setup plan", "save_kali_setup_plan"),
            ("Verify saved setup plan", "verify_setup_plan"),
            ("Verify ISO + preview VM", "preview_provision"),
            ("Check Kali VM readiness", "check_kali_template_readiness"),
        ]
        for index, (text, method) in enumerate(actions):
            box = QVBoxLayout()
            self.action(text, method, box, primary=index == 2)
            buttons.addLayout(box, index // 2, index % 2)
        layout.addLayout(buttons)
        manager = QPushButton("Open virt-manager for installation  ↗")
        manager.clicked.connect(lambda: self.controller.open_program(["virt-manager", "--connect", "qemu:///system"]))
        layout.addWidget(manager)
        layout.addWidget(self.label("The preview checks files and proposed XML. Actual VM installation stays in virt-manager.", "StudioMuted"))

    def _build_packages(self):
        layout = self.section("Packages", "Collect versions inside the guest, compare them locally, and keep a private version snapshot.")
        self.action("View toolkit details", "show_kali_template", layout)
        self.action("Guest inventory instructions", "show_guest_inventory_instructions", layout)
        self.action("Compare guest inventory", "compare_kali_guest_inventory", layout)
        self.action("Save package version snapshot", "save_package_snapshot", layout)
        self.action("Review package version drift", "review_kali_version_drift", layout)
        layout.addWidget(self.label("Inventory comes from the guest-side helper. These controls do not run apt or transfer files into a VM.", "StudioMuted"))

    def _build_recovery(self):
        layout = self.section("Recovery", "Follow the chain from the installed guest to its cold backup and independent recovery copy.")
        for text, method in (
            ("Audit installed Kali template VM", "audit_registered_kali_template"),
            ("Verify Kali cold backup", "verify_kali_cold_baseline"),
            ("Verify Kali recovery copy", "check_kali_recovery_link"),
            ("Audit registered Kali recovery", "audit_registered_kali_recovery"),
        ):
            self.action(text, method, layout)
        backup = QPushButton("Open backup & recovery tools  →")
        backup.clicked.connect(lambda: self.controller.goto(5))
        layout.addWidget(backup)

    def _build_runtime(self):
        layout = self.section("Runtime", "Inspect a benign recovery guest you have already started, without launching or contacting it.")
        self.action("Observe running Kali recovery", "observe_running_kali_recovery", layout)
        self.action("Inspect effective QEMU sVirt label", "check_kali_qemu_process_label", layout)
        layout.addWidget(self.label("Results are observations of libvirt and process metadata, not a certificate of network isolation.", "StudioMuted"))

    def _build_appearance(self):
        layout = self.section("Appearance", "Choose your studio accent and optionally theme the desktop inside a Kali Xfce guest.")
        layout.addWidget(self.label("STUDIO ACCENT", "StudioKicker"))
        self.theme_combo = QComboBox()
        for key, (name, _accent, _surface) in STUDIO_THEMES.items():
            self.theme_combo.addItem(name, key)
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(load_machine_preferences().kali_studio_theme))
        self.theme_combo.currentIndexChanged.connect(lambda *_: self.change_theme())
        layout.addWidget(self.theme_combo)
        self.appearance_status = self.label("Saved on this machine. All accents use an obsidian background.", "StudioMuted")
        layout.addWidget(self.appearance_status)
        layout.addWidget(self.label("KALI GUEST DESKTOP", "StudioKicker"))
        self.guest_theme = QComboBox()
        self.guest_theme.addItem("Kali Dark", "Kali-Dark")
        self.guest_theme.addItem("Kali Light", "Kali-Light")
        layout.addWidget(self.guest_theme)
        show = QPushButton("Show guest theme instructions")
        show.clicked.connect(lambda *_: self.guest_theme_instructions())
        layout.addWidget(show)
        layout.addWidget(self.label("The optional helper runs inside Kali Xfce, previews first, and saves the previous settings for undo. No theme is pushed from the host.", "StudioMuted"))

    def enter(self):
        self.controller.provision_kind.setCurrentIndex(self.controller.provision_kind.findData("pentest"))
        self.sync_profile()

    def select_profile(self, identifier):
        self.enter()
        self.controller.provision_template.setCurrentIndex(self.controller.provision_template.findData(identifier))
        self.sync_profile()

    def sync_profile(self, *_):
        identifier = self.controller.provision_template.currentData()
        for key, button in self.profile_buttons.items():
            button.setChecked(key == identifier)
        if identifier:
            template = get_template(identifier)
            self.packages.setText("SELECTED PACKAGES  /  " + "  ·  ".join(template.packages))
        else:
            self.packages.setText("CUSTOM KALI  /  No predefined package bundle")
        self.sync_selection()

    def sync_selection(self, *_):
        identifier = self.controller.provision_template.currentData()
        name = get_template(identifier).name if identifier else "Custom Kali"
        self.selection.setText(name + "  /  " + self.controller.provision_name.text())

    def sync_result(self):
        self.result.setPlainText(self.controller.provision_result.toPlainText())
        for method, source in (("preview_provision", "provision_preview_button"),
                               ("check_kali_template_readiness", "kali_preflight_button")):
            self.action_buttons[method].setEnabled(getattr(self.controller, source).isEnabled())

    def change_theme(self, *_):
        key = self.theme_combo.currentData()
        try:
            save_machine_preferences(replace(load_machine_preferences(), kali_studio_theme=key))
        except (OSError, ValueError) as exc:
            self.appearance_status.setText("Could not save appearance: " + str(exc))
            return
        self.set_theme(key)
        self.appearance_status.setText("Saved: " + STUDIO_THEMES[key][0])

    def set_theme(self, key):
        _name, accent, selected = STUDIO_THEMES[key]
        self.setStyleSheet("""
            QWidget#StudioSurface, QWidget#StudioSection { background: #0b0b11; }
            QFrame#StudioHero { background: #111119; border: 1px solid #2b2633; border-left: 3px solid ACCENT; border-radius: 12px; }
            QLabel#StudioTitle { color: #eee6ee; font-size: 32px; font-weight: 800; letter-spacing: 3px; }
            QLabel#StudioKicker { color: ACCENT; font-size: 10px; font-weight: 650; letter-spacing: 1.5px; }
            QLabel#StudioMuted { color: #a7a0b3; font-size: 12px; }
            QLabel#StudioHeading { color: #e9dfed; font-size: 17px; font-weight: 700; }
            QLabel#StudioSelection { color: #cfc3d5; font-size: 12px; }
            QLabel#StudioSeal { color: ACCENT; font-size: 19px; font-weight: 750; padding: 10px; }
            QLabel#StudioBadge { color: ACCENT; background: SELECTED; border: 1px solid ACCENT; border-radius: 5px; padding: 5px 8px; font-size: 10px; }
            QLabel#StudioPackages { color: #bdb2c6; background: #14131c; padding: 12px; border-radius: 8px; font-size: 11px; }
            QPushButton#ToolkitCard { text-align: left; color: #a9a1b8; background: #12121b; border: 1px solid #2b2736; border-radius: 10px; padding: 15px; font-size: 12px; }
            QPushButton#ToolkitCard:hover { background: #1b1722; border-color: ACCENT; }
            QPushButton#ToolkitCard:checked { color: #f2e8ee; background: SELECTED; border: 1px solid ACCENT; border-left: 3px solid ACCENT; }
            QPushButton#StudioPrimary { background: SELECTED; color: #f2e8ef; border: 1px solid ACCENT; font-weight: 650; padding: 10px 14px; }
            QPushButton#StudioPrimary:hover { color: ACCENT; background: #221b2b; }
            QPushButton#StudioAction { text-align: left; padding: 11px 15px; background: #15141e; border-color: #332d40; }
            QPushButton#StudioAction:hover { border-color: ACCENT; color: ACCENT; }
            QPushButton#StudioPrimary:disabled, QPushButton#StudioAction:disabled { color: #756d81; background: #111117; border-color: #26212e; }
            QTabWidget#StudioTabs::pane { border: none; }
            QTabBar { qproperty-drawBase: 0; }
            QTabBar::tab { background: #111019; color: #a59bb1; padding: 10px 12px; border-bottom: 2px solid #282331; }
            QTabBar::tab:selected { color: ACCENT; background: #1b1722; border-bottom: 2px solid ACCENT; }
            QTabBar::tab:hover { color: #eee6ef; }
            QPlainTextEdit#StudioOutput { background: #09090f; color: #c9bbd1; border: 1px solid #30283b; }
        """.replace("ACCENT", accent).replace("SELECTED", selected))

    def verify_setup_plan(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Verify private Kali setup plan", "", "JSON files (*.json)")
        if not filename:
            return
        try:
            plan = load_setup_plan(Path(filename))
            if plan["template_id"] != self.controller.provision_template.currentData() or plan["guest"] != self.controller.provision_name.text().strip():
                raise ValueError("The plan belongs to a different toolkit or guest. Select its matching profile and guest name.")
            self.controller.provision_result.setPlainText("Setup plan verified against the current catalog: " + plan["guest"])
        except (OSError, ValueError, ToolError) as exc:
            self.controller.provision_result.setPlainText("Setup plan could not be verified: " + str(exc))

    def save_package_snapshot(self):
        paths = []
        for caption in ("Choose private Kali setup plan", "Choose guest package inventory"):
            filename, _ = QFileDialog.getOpenFileName(self, caption, "", "JSON files (*.json)")
            if not filename:
                return
            paths.append(Path(filename))
        destination, _ = QFileDialog.getSaveFileName(self, "Save NEW private package version snapshot", "", "JSON files (*.json)")
        if not destination:
            return
        template = self.controller.provision_template.currentData()
        guest = self.controller.provision_name.text().strip()
        def save():
            plan = load_setup_plan(paths[0])
            if plan["template_id"] != template or plan["guest"] != guest:
                raise ToolError("Choose the plan matching the selected toolkit and guest.")
            return save_version_lock(*paths, Path(destination))
        self.controller.work(
            save,
            lambda saved: self.controller.provision_result.setPlainText("Saved guest-reported package version snapshot: " + str(saved)),
            lambda message: self.controller.provision_result.setPlainText("Version snapshot not saved: " + message),
        )

    def guest_theme_instructions(self):
        name = self.guest_theme.currentData()
        self.controller.provision_result.setPlainText(
            "INSIDE THE KALI XFCE GUEST\n\n"
            "Transfer the reviewed scripts/kali/kali-desktop-theme.py helper yourself.\n"
            "Run as the guest's regular desktop user:\n\n"
            f"  python3 kali-desktop-theme.py --theme {name}\n"
            f"  python3 kali-desktop-theme.py --theme {name} --apply\n\n"
            "The first command previews. Apply saves the previous theme settings and prints an undo command.\n"
            "No packages are downloaded; the selected Kali theme must already be installed.\n"
            "You can also use Kali Settings → Appearance and Window Manager → Style."
        )
