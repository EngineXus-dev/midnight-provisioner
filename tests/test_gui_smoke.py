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
    os.environ.get("MIDNIGHT_PROVISIONER_GUI_SMOKE") == "1",
    "Separate Qt CI job only; PySide6 intentionally not required for unit tests",
)
class OffscreenMainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # POSIX descriptor modes are not supported on native Windows. Mock
        # this Linux-only syscall for synthetic Qt tests; never change
        # production permission enforcement or Linux-mode assertions.
        if os.name == "nt":
            fd_patch = patch("midnight_provisioner.settings.os.fchmod", create=True)
            fd_patch.start()
            cls.addClassCleanup(fd_patch.stop)
        from PySide6.QtWidgets import QApplication
        from midnight_provisioner.theme import apply_theme
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def setUp(self):
        import midnight_provisioner.ui as ui

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
        from midnight_provisioner.theme import COLORS, THEME_NAME
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
        self.assertEqual(len(self.window.nav_buttons), 7)
        self.assertTrue(self.window.nav_buttons[0].isChecked())
        self.window.goto(3)
        self.assertTrue(self.window.nav_buttons[3].isChecked())
        self.assertFalse(self.window.nav_buttons[0].isChecked())
        self.window.goto(5)
        self.assertTrue(self.window.nav_buttons[5].isChecked())

    def test_real_qt_pages_and_workspace_cards_construct(self):
        self.assertEqual(self.window.stack.count(), 7)
        self.assertEqual(len(self.window.cards), 4)
        self.assertIn("Midnight Provisioner", self.window.windowTitle())
        for index in (0, 1, 3, 4, 5):
            with self.subTest(page=index):
                self.window.goto(index)
                self.assertEqual(self.window.stack.currentIndex(), index)
        with patch.object(self.window, "check_host", return_value=None) as doctor:
            self.window.goto(2)
            doctor.assert_called_once()
        self.assertEqual(self.window.stack.currentIndex(), 2)

    def test_system_discovery_page_is_never_an_installer_or_silent_file_scan(self):
        from midnight_provisioner.system_discovery import collect_system
        from PySide6.QtWidgets import QPlainTextEdit
        self.window.goto(6)
        self.assertEqual(self.window.stack.currentIndex(), 6)
        self.assertEqual(self.window.discovery_intent.currentData(), "undecided")
        self.assertFalse(self.window.discovery_folder_names.isChecked())
        self.assertIn("UNKNOWN", self.window.discovery_intent_status.text())
        self.window.discovery_intent.setCurrentIndex(
            self.window.discovery_intent.findData("format_target")
        )
        self.assertIn("deleting existing data", self.window.discovery_intent_status.text().lower())
        self.assertIn("data loss warning", self.window.discovery_format_warning.text().lower())
        self.assertIn("responsible", self.window.discovery_format_warning.text().lower())
        self.assertFalse(self.window.discovery_backup_acknowledged.isChecked())
        self.assertTrue(self.window.discovery_backup_acknowledged.isEnabled())
        self.window.discovery_backup_acknowledged.setChecked(True)
        self.window.discovery_intent.setCurrentIndex(
            self.window.discovery_intent.findData("coexist")
        )
        self.assertFalse(self.window.discovery_backup_acknowledged.isChecked())
        self.assertIn("partition change warning", self.window.discovery_format_warning.text().lower())
        self.window.discovery_intent.setCurrentIndex(
            self.window.discovery_intent.findData("undecided")
        )
        self.assertFalse(self.window.discovery_backup_acknowledged.isEnabled())
        self.assertTrue(self.window.discovery_output.isReadOnly())
        sample = collect_system(
            system="Linux", storage_data={"blockdevices": []},
            run_live=False, home=Path(self.temp.name)
        )
        with patch.object(self.ui, "collect_system", return_value=sample), \
             patch.object(self.window, "work") as work:
            self.window.begin_system_discovery()
            task, done, error = work.call_args.args
            result = task()
            self.assertFalse(result["folder_names_opted_in"])
            self.assertFalse(result["installation_authorized"])
            done(result)
        self.assertIn("NO TRUSTED DISK INVENTORY", self.window.discovery_output.toPlainText())
        self.assertTrue(self.window.discovery_button.isEnabled())
        self.assertIn("UNVERIFIED", self.window.discovery_status.text())

    def test_target_install_plan_never_auto_selects_or_authorizes_disk(self):
        from midnight_provisioner.system_discovery import collect_system
        sample = collect_system(
            system="Windows", run_live=False,
            home=Path(self.temp.name), storage_data={
                "disks": [
                    {"Number": 0, "Size": 466 * 1024**3, "BusType": "NVMe",
                     "IsBoot": True, "IsSystem": True},
                    {"Number": 1, "Size": 1863 * 1024**3, "BusType": "USB",
                     "IsBoot": False, "IsSystem": False},
                ],
                "partitions": [
                    {"DiskNumber": 0}, {"DiskNumber": 0},
                    {"DiskNumber": 1}, {"DiskNumber": 1},
                ],
            },
        )
        self.window.goto(6)
        self.window.discovery_intent.setCurrentIndex(
            self.window.discovery_intent.findData("format_target")
        )
        with patch.object(self.ui, "collect_system", return_value=sample), \
             patch.object(self.window, "work") as work:
            self.window.begin_system_discovery()
            task, done, _failed = work.call_args.args
            done(task())
        self.assertIsNone(self.window.discovery_target_combo.currentData())
        self.assertEqual(self.window.discovery_target_combo.count(), 3)
        self.assertIn("NOT_SELECTED", self.window.discovery_target_preview.toPlainText())

        self.window.discovery_target_combo.setCurrentIndex(2)
        preview = self.window.preview_target_plan()
        self.assertEqual(preview.target_observed_label, "Disk 1")
        self.assertEqual(preview.target_partitions_observed, 2)
        self.assertIn("ENTIRE_SELECTED_DISK", self.window.discovery_target_preview.toPlainText())
        self.assertFalse(preview.disk_write_authorized)

        self.window.discovery_backup_acknowledged.setChecked(True)
        preview = self.window.preview_target_plan()
        self.assertTrue(preview.user_backup_warning_acknowledged)
        self.assertFalse(preview.user_backups_proven_by_midnight_provisioner)
        self.assertFalse(preview.os_install_authorized)

        self.window.discovery_target_combo.setCurrentIndex(1)
        preview = self.window.preview_target_plan()
        self.assertFalse(self.window.discovery_backup_acknowledged.isChecked())
        self.assertEqual(preview.target_classification, "PROTECTED_IN_USE")
        self.assertFalse(preview.disk_write_authorized)

        with patch.object(self.window, "work") as work:
            self.window.begin_system_discovery()
            self.assertIsNone(self.window.discovery_snapshot)
            self.assertIsNone(self.window.discovery_target_combo.currentData())
            self.assertFalse(self.window.discovery_backup_acknowledged.isChecked())
            self.assertIn("discarded", self.window.discovery_target_preview.toPlainText())

    def test_change_review_qt_displays_unknown_partitions_and_no_writes(self):
        from midnight_provisioner.system_discovery import collect_system
        sample = collect_system(
            system="Windows", run_live=False, home=Path(self.temp.name),
            storage_data={
                "disks": [
                    {"Number": 0, "Size": 466 * 1024**3, "BusType": "NVMe",
                     "IsBoot": True, "IsSystem": True},
                    {"Number": 1, "Size": 1863 * 1024**3, "BusType": "USB",
                     "IsBoot": False, "IsSystem": False}],
                "partitions": [{"DiskNumber": 0}, {"DiskNumber": 1},
                               {"DiskNumber": 1}],
            },
        )
        self.window.goto(6)
        self.window.discovery_intent.setCurrentIndex(
            self.window.discovery_intent.findData("format_target"))
        with patch.object(self.ui, "collect_system", return_value=sample), \
             patch.object(self.window, "work") as background:
            self.window.begin_system_discovery()
            job, completed, _failed = background.call_args.args
            completed(job())
        self.assertTrue(self.window.discovery_change_review.isReadOnly())
        self.assertIn("NO TARGET SELECTED",
                      self.window.discovery_change_review.toPlainText())
        self.window.discovery_target_combo.setCurrentIndex(2)
        review = self.window.preview_install_changes()
        self.assertEqual(review.observed_target, "Disk 1")
        self.assertFalse(review.exact_new_partition_layout_known)
        self.assertFalse(review.disk_write_authorized)
        self.assertIn("EFI_SYSTEM_PARTITION",
                      self.window.discovery_change_review.toPlainText())
        self.window.discovery_backup_acknowledged.setChecked(True)
        self.assertFalse(self.window.preview_install_changes().os_install_authorized)
        with patch.object(self.window, "work"):
            self.window.begin_system_discovery()
            self.assertIsNone(self.window.discovery_snapshot)
            self.assertIn("invalidated",
                          self.window.discovery_change_review.toPlainText())

    def test_local_untrusted_proposal_review_never_executes_or_persists(self):
        import json
        import midnight_provisioner.install_proposal_review as proposal_module
        path = Path(self.temp.name) / "untrusted-proposal.json"
        path.write_text(json.dumps({
            "schema": proposal_module.SCHEMA,
            "source": "unverified_user_supplied",
            "intent": "format_target",
            "target_ref": "target_a",
            "devices": [
                {"ref": "target_a", "role": "target", "partition_count": 2},
                {"ref": "other_b", "role": "other", "partition_count": None},
            ],
            "operations": [{
                "action": "write_bootloader",
                "device_ref": "other_b",
                "partition_ref": None,
            }],
        }), encoding="utf-8")
        self.window.goto(6)
        with patch.object(self.ui.QFileDialog, "getOpenFileName",
                          return_value=(str(path), "JSON documents (*.json)")):
            self.window.review_proposal_file()
        text = self.window.discovery_proposal_report.toPlainText()
        self.assertIn("UNTRUSTED", text)
        self.assertIn("OTHER-DRIVE", text)
        self.assertIn("No disk writes", text)
        self.assertTrue(self.window.discovery_proposal_report.isReadOnly())
        # A scan invalidates old plan views, even if the user supplied a file.
        with patch.object(self.window, "work"):
            self.window.begin_system_discovery()
            self.assertIn("discarded",
                self.window.discovery_proposal_report.toPlainText())

    def test_preset_controls_are_safe_and_saved_only_to_temp_home(self):
        import midnight_provisioner.portability as portability

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
        saved = portability.load_machine_preferences(self.config / "midnight-provisioner" / "machine.json")
        self.assertEqual(saved, prefs)
        if os.name != "nt":
            self.assertEqual(
                (self.config / "midnight-provisioner" / "machine.json").stat().st_mode & 0o777, 0o600
            )

    def test_provisioning_ui_never_creates_guest_for_missing_iso(self):
        with patch.object(self.window, "error") as error, \
             patch.object(self.window, "work") as background:
            self.window.prepare_space("analysis")
            self.assertEqual(self.window.stack.currentIndex(), 4)
            self.assertEqual(self.window.provision_kind.currentData(), "analysis")
            self.assertEqual(self.window.provision_name.text(), "midnight-provisioner-malware")
            self.window.preview_provision()
        error.assert_called_once()
        background.assert_not_called()

    def test_kali_templates_are_independent_and_not_installed_by_gui(self):
        from midnight_provisioner.kali_templates import get_template, list_templates
        with patch.object(self.window, "work") as background:
            self.window.prepare_space("pentest")
            self.assertEqual(self.window.stack.currentIndex(), 4)
            self.assertTrue(self.window.provision_template.isEnabled())
            self.assertEqual(self.window.provision_template.count(), len(list_templates()) + 1)
            entry = self.window.provision_template.findData("web-audit")
            self.assertGreater(entry, 0)
            self.window.provision_template.setCurrentIndex(entry)
            self.assertEqual(
                self.window.provision_name.text(), get_template("web-audit").default_name,
            )
            self.assertEqual(self.window.provision_disk.text(), "48")
            self.window.show_kali_template()
            output = self.window.provision_result.toPlainText()
            self.assertIn("Web Application Assessment", output)
            self.assertIn("DISCONNECTED", output)
            self.assertIn("sudo apt install", output)
            background.assert_not_called()
            self.window.prepare_space("analysis")
            self.assertFalse(self.window.provision_template.isEnabled())
            self.assertEqual(self.window.provision_name.text(), "midnight-provisioner-malware")
            self.window.show_kali_template()
            self.assertIn("must not be attached", self.window.provision_result.toPlainText())
            background.assert_not_called()

    def test_new_kali_setup_plan_is_private_and_guest_inventory_is_read_only(self):
        import json
        from midnight_provisioner.kali_setup import INVENTORY_FORMAT, load_setup_plan
        from PySide6.QtWidgets import QPushButton
        self.window.prepare_space("pentest")
        page = self.window.stack.currentWidget()
        controls = {button.text() for button in page.findChildren(QPushButton)}
        self.assertIn("Save private Kali setup plan", controls)
        self.assertIn("Compare guest inventory", controls)
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("recon")
        )
        output = Path(self.temp.name) / "kali-setup.json"
        with patch.object(self.ui.QFileDialog, "getSaveFileName", return_value=(str(output), "JSON")), \
             patch.object(self.window, "work") as background:
            self.window.save_kali_setup_plan()
            background.assert_not_called()
        plan = load_setup_plan(output)
        self.assertEqual(plan["template_id"], "recon")
        self.assertEqual(plan["status"], "PLANNED_ONLY")
        if os.name != "nt":
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        inventory = Path(self.temp.name) / "manual-inventory.json"
        inventory.write_text(json.dumps({
            "format": INVENTORY_FORMAT,
            "version": 1,
            "guest": plan["guest"],
            "kali_release": "kali-rolling",
            "packages": [
                {"name": name, "installed_version": None, "candidate_version": "1.0"}
                for name in plan["packages"]
            ],
            "dpkg_audit_clean": None,
        }))
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName",
            side_effect=[(str(output), "JSON"), (str(inventory), "JSON")],
        ), patch.object(self.window, "work") as background:
            self.window.compare_kali_guest_inventory()
            background.assert_called_once()
            command, received, failed = background.call_args.args
            self.assertIn("compare_inventory_files", command.__code__.co_names)
            received(command())
        self.assertIn("INCOMPLETE", self.window.provision_result.toPlainText())
        self.assertIn("NOT authenticated", self.window.provision_result.toPlainText())
        # Any attempt to overwrite a local setup record must be rejected.
        with patch.object(self.ui.QFileDialog, "getSaveFileName", return_value=(str(output), "JSON")), \
             patch.object(self.window, "error") as error:
            self.window.save_kali_setup_plan()
            error.assert_called_once()
        self.window.prepare_space("analysis")
        with patch.object(self.window, "error") as error, \
             patch.object(self.ui.QFileDialog, "getSaveFileName") as dialog:
            self.window.save_kali_setup_plan()
            error.assert_called_once()
            dialog.assert_not_called()

    def test_guest_inventory_instructions_are_read_only_and_guest_scoped(self):
        from PySide6.QtWidgets import QPushButton
        self.window.prepare_space("pentest")
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("recon")
        )
        controls = {
            button.text()
            for button in self.window.stack.currentWidget().findChildren(QPushButton)
        }
        self.assertIn("Guest inventory instructions", controls)
        with patch.object(self.window, "work") as worker, \
             patch.object(self.ui.subprocess, "run") as commands:
            self.window.show_guest_inventory_instructions()
            worker.assert_not_called()
            commands.assert_not_called()
        output = self.window.provision_result.toPlainText()
        self.assertIn("python3 kali-guest-inventory.py --plan", output)
        self.assertIn("NOT authenticated", output)
        self.assertIn("does NOT provide host/guest file sharing", output)
        self.assertIn("midnight-provisioner-kali-recon", output)
        self.window.prepare_space("analysis")
        self.window.show_guest_inventory_instructions()
        self.assertIn("benign pentest VMs only", self.window.provision_result.toPlainText())

    def test_kali_version_drift_three_local_files_and_cancel_no_vm_io(self):
        from types import SimpleNamespace
        from PySide6.QtWidgets import QPushButton
        self.window.prepare_space("pentest")
        controls = {
            button.text()
            for button in self.window.stack.currentWidget().findChildren(QPushButton)
        }
        self.assertIn("Review package version drift", controls)
        names = (
            "/tmp/plan-v1.json", "/tmp/baseline-lock.json", "/tmp/current-report.json"
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName",
            side_effect=[(name, "JSON") for name in names],
        ) as picker, patch.object(self.window, "work") as worker:
            self.window.review_kali_version_drift()
            self.assertEqual(picker.call_count, 3)
            worker.assert_called_once()
            task, success, failure = worker.call_args.args
            self.assertIn("compare_version_lock_files", task.__code__.co_names)
            result = SimpleNamespace(
                unchanged=False,
                describe=lambda: (
                    "KALI GUEST PACKAGE DRIFT: DRIFT / UNVERIFIED — REVIEW REQUIRED"
                ),
            )
            success(result)
            self.assertIn("REVIEW REQUIRED", self.window.provision_result.toPlainText())
            failure("unrecognized inventory")
            self.assertIn("UNVERIFIED", self.window.provision_result.toPlainText())
            self.assertIn("No guest", self.window.provision_result.toPlainText())
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName",
            side_effect=[(names[0], "JSON"), ("", "")],
        ), patch.object(self.window, "work") as worker:
            self.window.review_kali_version_drift()
            worker.assert_not_called()
        self.window.prepare_space("analysis")
        with patch.object(self.ui.QFileDialog, "getOpenFileName") as picker:
            self.window.review_kali_version_drift()
            picker.assert_not_called()
        self.assertIn("benign Kali VMs", self.window.provision_result.toPlainText())

    def test_kali_vm_readiness_gui_uses_bound_setup_manifest_and_is_cancelable(self):
        from types import SimpleNamespace
        from PySide6.QtWidgets import QPushButton
        from midnight_provisioner.kali_setup import build_setup_plan, save_setup_plan
        self.window.prepare_space("pentest")
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("recon")
        )
        controls = {
            button.text()
            for button in self.window.stack.currentWidget().findChildren(QPushButton)
        }
        self.assertIn("Check Kali VM readiness", controls)
        digest = "a" * 64
        self.window.provision_sha.setText(digest)
        self.window.provision_iso.setText("/tmp/synthetic-kali.iso")
        manifest = Path(self.temp.name) / "recon-manifest.json"
        save_setup_plan(build_setup_plan("recon", iso_sha256=digest), manifest)
        fake_result = SimpleNamespace(
            ok=True, describe=lambda: "KALI TEMPLATE PREFLIGHT: DRY-RUN PASSED — MANUAL REVIEW ONLY"
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName",
            return_value=(str(manifest), "JSON"),
        ), patch.object(
            self.ui.QFileDialog, "getExistingDirectory",
            return_value=self.temp.name,
        ), patch.object(self.ui, "KaliPreflight") as preflight, \
             patch.object(self.window, "work") as worker:
            preflight.return_value.inspect.return_value = fake_result
            self.window.check_kali_template_readiness()
            worker.assert_called_once()
            self.assertFalse(self.window.kali_preflight_button.isEnabled())
            task, completed, failed = worker.call_args.args
            self.assertIs(task(), fake_result)
            preflight.return_value.inspect.assert_called_once_with(
                manifest, Path("/tmp/synthetic-kali.iso"), Path(self.temp.name)
            )
            completed(fake_result)
            self.assertTrue(self.window.kali_preflight_button.isEnabled())
            self.assertIn("MANUAL REVIEW", self.window.provision_result.toPlainText())
        # Rebind the UI to another profile but use the old saved manifest:
        # inspection must fail before reading an ISO or touching libvirt.
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("web-audit")
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName",
            return_value=(str(manifest), "JSON"),
        ), patch.object(
            self.ui.QFileDialog, "getExistingDirectory",
            return_value=self.temp.name,
        ), patch.object(self.ui, "KaliPreflight") as preflight, \
             patch.object(self.window, "work") as worker:
            self.window.check_kali_template_readiness()
            task, completed, failed = worker.call_args.args
            with self.assertRaisesRegex(Exception, "differ"):
                task()
            preflight.assert_not_called()
            failed("manifest mismatch")
            self.assertTrue(self.window.kali_preflight_button.isEnabled())
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("recon")
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName", return_value=("", "")
        ), patch.object(self.window, "work") as worker:
            self.window.check_kali_template_readiness()
            worker.assert_not_called()
        self.window.prepare_space("analysis")
        with patch.object(self.ui.QFileDialog, "getOpenFileName") as dialog:
            self.window.check_kali_template_readiness()
            dialog.assert_not_called()

    def test_registered_kali_template_audit_is_explicit_and_guest_bound(self):
        from types import SimpleNamespace
        from PySide6.QtWidgets import QPushButton
        from midnight_provisioner.kali_setup import build_setup_plan, save_setup_plan
        self.window.prepare_space("pentest")
        entry = self.window.provision_template.findData("recon")
        self.window.provision_template.setCurrentIndex(entry)
        labels = {
            button.text()
            for button in self.window.stack.currentWidget().findChildren(QPushButton)
        }
        self.assertIn("Audit installed Kali template VM", labels)
        plan = Path(self.temp.name) / "template-plan.json"
        save_setup_plan(build_setup_plan("recon"), plan)
        disk = Path(self.temp.name) / "own-recon.qcow2"
        disk.write_bytes(b"synthetic-disk-not-touched")
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName",
            side_effect=[(str(plan), "JSON"), (str(disk), "QEMU")],
        ), patch.object(self.ui, "KaliRegistrationInspector") as inspector, \
             patch.object(self.window, "work") as worker:
            report = SimpleNamespace(
                ok=True,
                describe=lambda: "KALI REGISTERED TEMPLATE: PASS (CONFIGURATION ONLY)"
            )
            inspector.return_value.inspect.return_value = report
            self.window.audit_registered_kali_template()
            worker.assert_called_once()
            check, completed, failed = worker.call_args.args
            self.assertIs(check(), report)
            inspector.return_value.inspect.assert_called_once_with(plan, disk)
            completed(report)
            self.assertIn("CONFIGURATION ONLY", self.window.provision_result.toPlainText())
        self.assertEqual(disk.read_bytes(), b"synthetic-disk-not-touched")
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("web-audit")
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName",
            side_effect=[(str(plan), "JSON"), (str(disk), "QEMU")],
        ), patch.object(self.ui, "KaliRegistrationInspector") as inspector, \
             patch.object(self.window, "work") as worker:
            self.window.audit_registered_kali_template()
            check, completed, failed = worker.call_args.args
            with self.assertRaisesRegex(Exception, "identity does not match"):
                check()
            inspector.assert_not_called()
            failed("mismatched Kali profile")
        self.assertIn("BLOCKED", self.window.provision_result.toPlainText())
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName", return_value=("", "")
        ), patch.object(self.window, "work") as worker:
            self.window.audit_registered_kali_template()
            worker.assert_not_called()
        self.window.prepare_space("analysis")
        with patch.object(self.ui.QFileDialog, "getOpenFileName") as picker:
            self.window.audit_registered_kali_template()
            picker.assert_not_called()
        self.assertIn("do not apply", self.window.provision_result.toPlainText())

    def test_kali_cold_baseline_gui_requires_matching_profile_and_can_cancel(self):
        from types import SimpleNamespace
        from PySide6.QtWidgets import QPushButton
        from midnight_provisioner.kali_setup import build_setup_plan, save_setup_plan
        self.window.prepare_space("pentest")
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("recon")
        )
        labels = {
            widget.text() for widget in
            self.window.stack.currentWidget().findChildren(QPushButton)
        }
        self.assertIn("Verify Kali cold backup", labels)
        plan = Path(self.temp.name) / "recon-plan.json"
        save_setup_plan(build_setup_plan("recon"), plan)
        disk = Path(self.temp.name) / "unchanged-recon.qcow2"
        disk.write_bytes(b"synthetic-not-changed")
        report = SimpleNamespace(
            ok=True, describe=lambda: (
                "KALI COLD BASELINE: HASHES/DEFINITIONS MATCH (NOT RESTORE-PROVEN)"
            ),
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName",
            side_effect=[(str(plan), "JSON"), (str(disk), "QEMU")],
        ), patch.object(
            self.ui.QFileDialog, "getExistingDirectory",
            return_value=self.temp.name,
        ), patch.object(self.ui, "KaliColdBaselineInspector") as inspector, \
             patch.object(self.window, "work") as worker:
            inspector.return_value.inspect.return_value = report
            self.window.verify_kali_cold_baseline()
            worker.assert_called_once()
            task, success, failure = worker.call_args.args
            self.assertIs(task(), report)
            inspector.return_value.inspect.assert_called_once_with(
                plan, disk, Path(self.temp.name),
            )
            success(report)
            self.assertIn("NOT RESTORE-PROVEN", self.window.provision_result.toPlainText())
        self.assertEqual(disk.read_bytes(), b"synthetic-not-changed")
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("web-audit")
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName",
            side_effect=[(str(plan), "JSON"), (str(disk), "QEMU")],
        ), patch.object(
            self.ui.QFileDialog, "getExistingDirectory",
            return_value=self.temp.name,
        ), patch.object(self.ui, "KaliColdBaselineInspector") as inspector, \
             patch.object(self.window, "work") as worker:
            self.window.verify_kali_cold_baseline()
            task, success, failure = worker.call_args.args
            with self.assertRaisesRegex(Exception, "does not match"):
                task()
            inspector.assert_not_called()
            failure("mismatch")
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName", return_value=("", "")
        ), patch.object(self.window, "work") as worker:
            self.window.verify_kali_cold_baseline()
            worker.assert_not_called()
        self.window.prepare_space("analysis")
        with patch.object(self.ui.QFileDialog, "getOpenFileName") as picker:
            self.window.verify_kali_cold_baseline()
            picker.assert_not_called()

    def test_kali_recovery_copy_gui_binds_source_template_and_allows_cancellation(self):
        from types import SimpleNamespace
        from PySide6.QtWidgets import QPushButton
        from midnight_provisioner.kali_setup import build_setup_plan, save_setup_plan
        self.window.prepare_space("pentest")
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("recon")
        )
        labels = {
            control.text()
            for control in self.window.stack.currentWidget().findChildren(QPushButton)
        }
        self.assertIn("Verify Kali recovery copy", labels)
        plan = Path(self.temp.name) / "selected-kali.json"
        save_setup_plan(build_setup_plan("recon"), plan)
        src = Path(self.temp.name) / "original-backup"
        stage = Path(self.temp.name) / "staged-copy"
        src.mkdir()
        stage.mkdir()
        result = SimpleNamespace(
            ok=True,
            describe=lambda: (
                "KALI RECOVERY LINK: MATCHED (FILES/XML ONLY — NOT RESTORE-PROVEN)"
            ),
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName", return_value=(str(plan), "JSON"),
        ), patch.object(
            self.ui.QFileDialog, "getExistingDirectory",
            side_effect=[str(src), str(stage)],
        ), patch.object(self.ui, "KaliRecoveryLink") as checker, \
             patch.object(self.window, "work") as worker:
            checker.return_value.inspect.return_value = result
            self.window.check_kali_recovery_link()
            worker.assert_called_once()
            task, success, failure = worker.call_args.args
            self.assertIs(task(), result)
            checker.return_value.inspect.assert_called_once_with(plan, src, stage)
            success(result)
            self.assertIn("NOT RESTORE-PROVEN", self.window.provision_result.toPlainText())
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("web-audit")
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName", return_value=(str(plan), "JSON"),
        ), patch.object(
            self.ui.QFileDialog, "getExistingDirectory",
            side_effect=[str(src), str(stage)],
        ), patch.object(self.ui, "KaliRecoveryLink") as checker, \
             patch.object(self.window, "work") as worker:
            self.window.check_kali_recovery_link()
            task, success, failure = worker.call_args.args
            with self.assertRaisesRegex(Exception, "differs from selected"):
                task()
            checker.assert_not_called()
            failure("profile mismatch")
        self.assertIn("BLOCKED", self.window.provision_result.toPlainText())
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName", return_value=("", ""),
        ), patch.object(self.window, "work") as worker:
            self.window.check_kali_recovery_link()
            worker.assert_not_called()
        self.window.prepare_space("analysis")
        with patch.object(self.ui.QFileDialog, "getOpenFileName") as dialog:
            self.window.check_kali_recovery_link()
            dialog.assert_not_called()

    def test_kali_registered_recovery_gui_is_read_only_bound_and_cancelable(self):
        from types import SimpleNamespace
        from PySide6.QtWidgets import QPushButton
        from midnight_provisioner.kali_setup import build_setup_plan, save_setup_plan
        self.window.prepare_space("pentest")
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("recon")
        )
        controls = {
            btn.text() for btn in
            self.window.stack.currentWidget().findChildren(QPushButton)
        }
        self.assertIn("Audit registered Kali recovery", controls)
        plan = Path(self.temp.name) / "recon-plan.json"
        save_setup_plan(build_setup_plan("recon"), plan)
        backup = Path(self.temp.name) / "cold-backup"
        stage = Path(self.temp.name) / "recovery-stage"
        backup.mkdir()
        stage.mkdir()
        report = SimpleNamespace(
            ok=True, describe=lambda:
            "KALI REGISTERED RECOVERY: PASS (METADATA ONLY — NOT BOOT/RESTORE-PROVEN)"
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName", return_value=(str(plan), "JSON"),
        ), patch.object(
            self.ui.QFileDialog, "getExistingDirectory",
            side_effect=[str(backup), str(stage)],
        ), patch.object(self.ui, "KaliRecoveryRegistrationInspector") as checker, \
             patch.object(self.window, "work") as worker:
            checker.return_value.inspect.return_value = report
            self.window.audit_registered_kali_recovery()
            worker.assert_called_once()
            task, success, failure = worker.call_args.args
            self.assertIs(task(), report)
            checker.return_value.inspect.assert_called_once_with(plan, backup, stage)
            success(report)
            self.assertIn("NOT BOOT/RESTORE-PROVEN",
                          self.window.provision_result.toPlainText())
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("web-audit")
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName", return_value=(str(plan), "JSON"),
        ), patch.object(
            self.ui.QFileDialog, "getExistingDirectory",
            side_effect=[str(backup), str(stage)],
        ), patch.object(self.ui, "KaliRecoveryRegistrationInspector") as checker, \
             patch.object(self.window, "work") as worker:
            self.window.audit_registered_kali_recovery()
            task, success, failure = worker.call_args.args
            with self.assertRaisesRegex(Exception, "differs from selected profile"):
                task()
            checker.assert_not_called()
            failure("Kali setup plan/profile mismatch")
        self.assertIn("BLOCKED", self.window.provision_result.toPlainText())
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName", return_value=("", ""),
        ), patch.object(self.window, "work") as worker:
            self.window.audit_registered_kali_recovery()
            worker.assert_not_called()
        self.window.prepare_space("analysis")
        with patch.object(self.ui.QFileDialog, "getOpenFileName") as dialog:
            self.window.audit_registered_kali_recovery()
            dialog.assert_not_called()

    def test_running_kali_recovery_gui_is_explicit_guest_bound_and_cancelable(self):
        from types import SimpleNamespace
        from PySide6.QtWidgets import QPushButton
        from midnight_provisioner.kali_setup import build_setup_plan, save_setup_plan
        self.window.prepare_space("pentest")
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("recon")
        )
        labels = {
            button.text() for button in
            self.window.stack.currentWidget().findChildren(QPushButton)
        }
        self.assertIn("Observe running Kali recovery", labels)
        original = Path(self.temp.name) / "original-setup.json"
        save_setup_plan(build_setup_plan("recon"), original)
        backup = Path(self.temp.name) / "cold-backup"
        backup.mkdir()
        disk = Path(self.temp.name) / "running-recovered.qcow2"
        disk.write_bytes(b"synthetic-never-hashed")
        recovered = "midnight-provisioner-kali-recon-rehearsal"
        result = SimpleNamespace(
            ok=True, describe=lambda:
            "KALI RUNNING-GUEST OBSERVATION: PASS (LIBVIRT/SELINUX METADATA ONLY)"
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName",
            side_effect=[(str(original), "JSON"), (str(disk), "QEMU")],
        ), patch.object(
            self.ui.QFileDialog, "getExistingDirectory", return_value=str(backup),
        ), patch.object(
            self.ui.QInputDialog, "getText", return_value=(recovered, True)
        ), patch.object(
            self.ui, "KaliRunningInspector"
        ) as checker, patch.object(self.window, "work") as worker:
            checker.return_value.inspect.return_value = result
            self.window.observe_running_kali_recovery()
            worker.assert_called_once()
            task, success, failure = worker.call_args.args
            self.assertIs(task(), result)
            checker.return_value.inspect.assert_called_once_with(
                original, backup, recovered, disk
            )
            success(result)
            self.assertIn("METADATA ONLY", self.window.provision_result.toPlainText())
        self.assertEqual(disk.read_bytes(), b"synthetic-never-hashed")
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("web-audit")
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName",
            side_effect=[(str(original), "JSON"), (str(disk), "QEMU")],
        ), patch.object(
            self.ui.QFileDialog, "getExistingDirectory", return_value=str(backup),
        ), patch.object(
            self.ui.QInputDialog, "getText", return_value=(recovered, True)
        ), patch.object(
            self.ui, "KaliRunningInspector"
        ) as checker, patch.object(self.window, "work") as worker:
            self.window.observe_running_kali_recovery()
            task, success, failure = worker.call_args.args
            with self.assertRaisesRegex(Exception, "differs from saved setup plan"):
                task()
            checker.assert_not_called()
            failure("wrong original template")
            self.assertIn("BLOCKED", self.window.provision_result.toPlainText())
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName", return_value=("", ""),
        ), patch.object(self.window, "work") as worker:
            self.window.observe_running_kali_recovery()
            worker.assert_not_called()
        self.window.prepare_space("analysis")
        with patch.object(self.ui.QFileDialog, "getOpenFileName") as picker:
            self.window.observe_running_kali_recovery()
            picker.assert_not_called()

    def test_qemu_process_label_button_and_compact_kali_grid_are_read_only(self):
        from types import SimpleNamespace
        from PySide6.QtWidgets import QPushButton, QGridLayout
        from midnight_provisioner.kali_setup import build_setup_plan, save_setup_plan
        self.window.prepare_space("pentest")
        page = self.window.stack.currentWidget()
        buttons = {b.text(): b for b in page.findChildren(QPushButton)}
        self.assertIn("Inspect effective QEMU sVirt label", buttons)
        self.assertIn("Verify Kali cold backup", buttons)
        self.assertIn("Observe running Kali recovery", buttons)
        # Kali actions used to be one ultra-wide row; now a 3-column grid.
        self.assertTrue(any(
            isinstance(layout, QGridLayout) and layout.count() >= 7
            for layout in page.findChildren(QGridLayout)
        ))
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("recon")
        )
        plan = Path(self.temp.name) / "private-qemu-plan.json"
        save_setup_plan(build_setup_plan("recon"), plan)
        recovered = "midnight-provisioner-kali-recon-rehearsal"
        report = SimpleNamespace(
            ok=True,
            describe=lambda: "KALI QEMU PROCESS LABEL: MATCHED (READ-ONLY /PROC OBSERVATION)",
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName",
            return_value=(str(plan), "JSON"),
        ), patch.object(
            self.ui.QInputDialog, "getText", return_value=(recovered, True)
        ), patch.object(self.ui, "KaliProcessLabelInspector") as inspector, \
             patch.object(self.window, "work") as worker:
            inspector.return_value.inspect.return_value = report
            self.window.check_kali_qemu_process_label()
            worker.assert_called_once()
            task, success, failure = worker.call_args.args
            self.assertIs(task(), report)
            inspector.return_value.inspect.assert_called_once_with(plan, recovered)
            success(report)
            self.assertIn("READ-ONLY /PROC", self.window.provision_result.toPlainText())
        self.window.provision_template.setCurrentIndex(
            self.window.provision_template.findData("web-audit")
        )
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName",
            return_value=(str(plan), "JSON"),
        ), patch.object(
            self.ui.QInputDialog, "getText", return_value=(recovered, True)
        ), patch.object(self.ui, "KaliProcessLabelInspector") as inspector, \
             patch.object(self.window, "work") as worker:
            self.window.check_kali_qemu_process_label()
            task, success, failure = worker.call_args.args
            with self.assertRaisesRegex(Exception, "differs from selected Kali source"):
                task()
            inspector.assert_not_called()
            failure("wrong profile")
            self.assertIn("BLOCKED", self.window.provision_result.toPlainText())
        with patch.object(
            self.ui.QFileDialog, "getOpenFileName", return_value=("", "")
        ), patch.object(self.window, "work") as worker:
            self.window.check_kali_qemu_process_label()
            worker.assert_not_called()
        self.window.prepare_space("analysis")
        with patch.object(self.ui.QFileDialog, "getOpenFileName") as picker:
            self.window.check_kali_qemu_process_label()
            picker.assert_not_called()
        self.assertIn("benign Kali", self.window.provision_result.toPlainText())

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
            "Verify registered handoff",
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

    def test_registered_recovery_handoff_gui_is_read_only(self):
        from types import SimpleNamespace
        from midnight_provisioner.handoff import RecoveryHandoff
        with patch.object(self.ui.QFileDialog, "getExistingDirectory", return_value="/tmp/synthetic-stage"), \
             patch.object(self.window, "work") as worker:
            self.window.verify_registered_handoff()
            worker.assert_called_once()
            function, success, failure = worker.call_args.args
            self.assertIn("RecoveryHandoff", function.__code__.co_names)
            report = SimpleNamespace(
                guest="midnight-provisioner-new-guest",
                ok=True,
                describe=lambda: "REGISTERED RECOVERY HANDOFF: PASS (METADATA ONLY)",
            )
            success(report)
            self.assertIs(self.window.last_acceptance, report)
            self.assertIn("METADATA ONLY", self.window.recovery_log.toPlainText())
        with patch.object(self.ui.QFileDialog, "getExistingDirectory", return_value=""), \
             patch.object(self.window, "work") as worker:
            self.window.verify_registered_handoff()
            worker.assert_not_called()

    def test_diagnostics_buttons_dispatch_without_native_slot_registration(self):
        # Exercise Qt's real clicked signal, but mock all host actions.
        from PySide6.QtWidgets import QPushButton
        buttons = {
            item.text(): item
            for item in self.window.stack.widget(2).findChildren(QPushButton)
        }
        with patch.object(self.window, "work") as background:
            buttons["Audit Fedora host security"].click()
            background.assert_called_once()
        with patch.object(self.window, "refresh_resources") as monitor:
            buttons["Refresh resource monitor"].click()
            monitor.assert_called_once_with(activate=True)

    def test_read_only_fedora_host_posture_action(self):
        from PySide6.QtWidgets import QPushButton
        from midnight_provisioner.host_posture import HostPosture, PostureCheck
        with patch.object(self.window, "check_host"):
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

    def test_running_guest_svirt_observation_requires_user_and_never_starts_vm(self):
        from types import SimpleNamespace
        from PySide6.QtWidgets import QPushButton
        with patch.object(self.window, "check_host"):
            self.window.goto(2)
        from PySide6.QtWidgets import QScrollArea
        self.assertIsInstance(self.window.stack.currentWidget(), QScrollArea)
        labels = {
            button.text()
            for button in self.window.stack.currentWidget().findChildren(QPushButton)
        }
        self.assertIn("Observe running VM sVirt labels", labels)
        self.assertIn("Save local runtime observation", labels)
        with patch.object(self.ui.QInputDialog, "getText", return_value=("safevm", True)), \
             patch.object(self.ui.QInputDialog, "getItem", return_value=("isolated", True)), \
             patch.object(self.window, "work") as worker:
            self.window.observe_guest_runtime_labels()
            worker.assert_called_once()
            task, success, failure = worker.call_args.args
            self.assertIn("RuntimeLabelInspector", task.__code__.co_names)
            observation = SimpleNamespace(
                guest="safevm",
                policy="isolated",
                ok=True,
                describe=lambda: "RUNTIME SVIRT OBSERVATION: PASS (METADATA ONLY)",
            )
            success(observation)
        self.assertIs(self.window.last_acceptance, observation)
        self.assertIn("METADATA ONLY", self.window.diagnostics.toPlainText())
        with patch.object(self.ui.QInputDialog, "getText", return_value=("safevm", False)), \
             patch.object(self.window, "work") as worker:
            self.window.observe_guest_runtime_labels()
            worker.assert_not_called()

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
        path = os.environ.get("MIDNIGHT_PROVISIONER_GUI_PREVIEW")
        if path:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            self.assertTrue(shot.save(str(target), "PNG"), "Qt offscreen screenshot failed")
            self.assertGreater(target.stat().st_size, 2048)
            # Inspect three materially different views, without loading guest
            # images, accessing libvirt, or touching the developer's settings.
            for page, suffix in ((3, "machine"), (5, "recovery"), (2, "diagnostics")):
                with patch.object(self.window, "check_host"):
                    self.window.goto(page)
                self.app.processEvents()
                other = target.with_name(target.stem + "-" + suffix + ".png")
                self.assertTrue(self.window.grab().save(str(other), "PNG"))
                self.assertGreater(other.stat().st_size, 2048)


if __name__ == "__main__":
    unittest.main()
