"""Offscreen Qt integration tests: real PySide6 widgets, NO libvirt or OS writes.

These tests are opt-in because headless unit runners need not install Qt.
GitHub Actions runs them in a separate job with a temporary HOME/config and
QT_QPA_PLATFORM=offscreen. No guest is imported, registered or launched.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(
    os.environ.get("NIGHTGLASS_GUI_SMOKE") == "1",
    "Separate Qt CI job only; PySide6 intentionally not required for unit tests",
)
class OffscreenMainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from nightglass.theme import apply_theme
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def setUp(self):
        import nightglass.ui as ui

        self.ui = ui
        self.temp = tempfile.TemporaryDirectory(prefix="ng-gui-test-")
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "config"
        self.home = Path(self.temp.name) / "home"
        self.config.mkdir()
        self.home.mkdir()
        self.env = patch.dict(os.environ, {
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_DATA_HOME": str(Path(self.temp.name) / "data"),
            "HOME": str(self.home),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        # Initial refresh would otherwise query the developer's real libvirt.
        with patch.object(ui.MainWindow, "refresh", return_value=None):
            self.window = ui.MainWindow()
        self.addCleanup(self.window.close)
        self.assertFalse(self.window._busy)

    def test_casual_dark_palette_and_active_navigation(self):
        from PySide6.QtGui import QPalette
        from nightglass.theme import COLORS, THEME_NAME
        self.assertIn("Dark", THEME_NAME)
        self.assertEqual(
            self.app.palette().color(QPalette.ColorRole.Window).name(),
            COLORS["window"],
        )
        from PySide6.QtWidgets import QFrame, QLabel
        stylesheet = self.app.styleSheet()
        self.assertIn("QFrame#Sidebar QPushButton:checked", stylesheet)
        self.assertIn(COLORS["neon_pink"], stylesheet)
        self.assertIn(COLORS["neon_purple"], stylesheet)
        # Primary and neutral text are lavender-tinted, never glare-white.
        for token in ("text", "text_strong", "text_muted"):
            channel = COLORS[token]
            self.assertEqual(len(channel), 7)
            self.assertGreater(int(channel[5:7], 16), int(channel[3:5], 16))
        self.assertIn(COLORS["text"], stylesheet)
        self.assertIn("QFrame#AccentRail", stylesheet)
        self.assertIn("border-left: 3px solid", stylesheet)
        self.assertEqual(
            len(self.window.findChildren(QFrame, "AccentRail")), 1
        )
        tagline = self.window.findChildren(QLabel, "Tagline")
        self.assertEqual(len(tagline), 1)
        self.assertIn("RESTORE", tagline[0].text())
        self.assertEqual(len(self.window.nav_buttons), 6)
        self.assertTrue(self.window.nav_buttons[0].isChecked())
        self.window.goto(3)
        self.assertTrue(self.window.nav_buttons[3].isChecked())
        self.assertFalse(self.window.nav_buttons[0].isChecked())
        self.window.goto(5)
        self.assertTrue(self.window.nav_buttons[5].isChecked())

    def test_real_qt_pages_and_workspace_cards_construct(self):
        self.assertEqual(self.window.stack.count(), 6)
        self.assertEqual(len(self.window.cards), 4)
        self.assertIn("Nightglass", self.window.windowTitle())
        for index in (0, 1, 3, 4, 5):
            with self.subTest(page=index):
                self.window.goto(index)
                self.assertEqual(self.window.stack.currentIndex(), index)
        with patch.object(self.window, "check_host", return_value=None) as doctor:
            self.window.goto(2)
            doctor.assert_called_once()
        self.assertEqual(self.window.stack.currentIndex(), 2)

    def test_preset_controls_are_safe_and_saved_only_to_temp_home(self):
        import nightglass.portability as portability

        options = [
            self.window.profile_combo.itemData(i)
            for i in range(self.window.profile_combo.count())
        ]
        self.assertEqual(options, ["auto", "compact", "balanced", "performance"])
        compact = self.window.profile_combo.findData("compact")
        self.window.profile_combo.setCurrentIndex(compact)
        self.window.ram_override.setText("2.25")
        self.window.vm_override.setText("1")
        self.window.cpu_override.setText("2")
        prefs = self.window.machine_preferences_from_form()
        self.assertEqual(prefs.preset, "compact")
        self.assertEqual(prefs.guest_ram_cap_gib, 2.25)
        self.assertEqual(prefs.active_vm_cap, 1)
        self.assertEqual(prefs.vcpu_cap, 2)

        with patch.object(self.window, "inform"), patch.object(self.window, "refresh"):
            self.window.save_machine_profile()
        saved = portability.load_machine_preferences(self.config / "nightglass" / "machine.json")
        self.assertEqual(saved, prefs)
        self.assertEqual(
            (self.config / "nightglass" / "machine.json").stat().st_mode & 0o777, 0o600
        )

    def test_provisioning_ui_never_creates_guest_for_missing_iso(self):
        with patch.object(self.window, "error") as error, \
             patch.object(self.window, "work") as background:
            self.window.prepare_space("analysis")
            self.assertEqual(self.window.stack.currentIndex(), 4)
            self.assertEqual(self.window.provision_kind.currentData(), "analysis")
            self.assertEqual(self.window.provision_name.text(), "nightglass-malware")
            self.window.preview_provision()
        error.assert_called_once()
        background.assert_not_called()

    def test_analysis_profile_cannot_save_running_memory(self):
        with patch.object(self.window, "error") as error, \
             patch.object(self.window, "work") as background:
            self.window.save_space("analysis")
        error.assert_called_once()
        background.assert_not_called()

    def test_new_backup_and_registered_audit_controls_exist(self):
        from PySide6.QtWidgets import QPushButton
        self.window.goto(5)
        labels = {
            button.text()
            for button in self.window.stack.currentWidget().findChildren(QPushButton)
        }
        self.assertTrue({
            "Verify saved backup",
            "Recover into NEW folder",
            "Verify staged recovery",
            "Check Fedora import readiness",
            "Audit registered VM",
            "Save local audit report",
        }.issubset(labels))

    def test_resource_monitor_starts_only_after_user_request(self):
        from types import SimpleNamespace
        with patch.object(self.window, "check_host"):
            self.window.goto(2)
        self.assertFalse(self.window._resource_monitor_enabled)
        self.assertFalse(self.window._resource_monitor_busy)
        self.assertEqual(self.window.resource_timer.interval(), 20000)
        with patch.object(self.window, "work") as background:
            self.window.refresh_resources()
            background.assert_not_called()
            self.window.refresh_resources(activate=True)
            background.assert_called_once()
            self.assertTrue(self.window._resource_monitor_busy)
            # User clicks a second time before completion: no overlapping worker.
            self.window.refresh_resources(activate=True)
            background.assert_called_once()
            task, success, failure = background.call_args.args
            snap = SimpleNamespace(
                level="CAUTION", active_vms=("external-guest",),
                describe=lambda: "Externally launched VM: external-guest"
            )
            success(snap)
        self.assertFalse(self.window._resource_monitor_busy)
        self.assertIn("CAUTION", self.window.resource_status.text())
        self.assertIn("external-guest", self.window.resource_details.toPlainText())
        with patch.object(self.window, "work") as background:
            self.window.refresh_resources()
            background.assert_called_once()
            _task, _success, failure = background.call_args.args
            failure("Permission denied by libvirt")
        self.assertFalse(self.window._resource_monitor_busy)
        self.assertIn("UNKNOWN", self.window.resource_status.text())
        self.assertIn("Permission denied", self.window.resource_details.toPlainText())

    def test_read_only_fedora_host_posture_action(self):
        from PySide6.QtWidgets import QPushButton
        from nightglass.host_posture import HostPosture, PostureCheck
        self.window.goto(2)
        controls = {button.text() for button in self.window.stack.currentWidget().findChildren(QPushButton)}
        self.assertIn("Audit Fedora host security", controls)
        with patch.object(self.window, "work") as background:
            self.window.check_host_security()
            background.assert_called_once()
            function, success, failure = background.call_args.args
            # The requested job has not executed on any real host.
            self.assertIs(function, self.ui.inspect_host_posture)
            report = HostPosture((
                PostureCheck("SELinux", "WARN", "Permissive"),
                PostureCheck("firewalld", "INFO", "Not proof of filtering"),
            ))
            success(report)
            self.assertIn("attention required", self.window.posture_summary.text())
            self.assertIn("SELinux", self.window.diagnostics.toPlainText())
            self.assertIn("READ-ONLY", self.window.diagnostics.toPlainText())
        with patch.object(self.window, "work") as background:
            self.window.check_host_security()
            _, _, failure = background.call_args.args
            failure("Permission denied")
        self.assertIn("UNKNOWN", self.window.posture_summary.text())
        self.assertIn("No configuration was changed", self.window.diagnostics.toPlainText())

    def test_actual_offscreen_ui_renders_without_real_display(self):
        self.window.resize(1150, 760)
        self.window.show()
        self.app.processEvents()
        shot = self.window.grab()
        self.assertFalse(shot.isNull())
        self.assertGreaterEqual(shot.width(), 880)
        self.assertGreaterEqual(shot.height(), 610)
        # Verify theme is dark at window edges; this catches accidental
        # inheritance of Qt's bright native palette or a lost stylesheet.
        image = shot.toImage()
        for x, y in ((0, 0), (shot.width() - 2, 2), (2, shot.height() - 2)):
            rgb = image.pixelColor(x, y)
            self.assertLess(max(rgb.red(), rgb.green(), rgb.blue()), 90)
        path = os.environ.get("NIGHTGLASS_GUI_PREVIEW")
        if path:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            self.assertTrue(shot.save(str(target), "PNG"), "Qt offscreen screenshot failed")
            self.assertGreater(target.stat().st_size, 2048)
            # Inspect three materially different views, without loading guest
            # images, accessing libvirt, or touching the developer's settings.
            for page, suffix in ((3, "machine"), (5, "recovery")):
                self.window.goto(page)
                self.app.processEvents()
                other = target.with_name(target.stem + "-" + suffix + ".png")
                self.assertTrue(self.window.grab().save(str(other), "PNG"))
                self.assertGreater(other.stat().st_size, 2048)


if __name__ == "__main__":
    unittest.main()
