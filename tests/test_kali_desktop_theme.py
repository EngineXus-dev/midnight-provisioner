"""Theme helper preview, rollback, undo, and platform boundaries without desktop I/O."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/kali/kali-desktop-theme.py"
spec = importlib.util.spec_from_file_location("kali_desktop_theme", SOURCE)
theme = importlib.util.module_from_spec(spec)
spec.loader.exec_module(theme)


class GuestThemeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.snapshot = Path(self.temp.name) / "previous.json"
        self.values = dict.fromkeys(theme.PROPERTIES, "Adwaita")
        self.writes = []

    def query(self, executable, channel, prop, value=None):
        key = (channel, prop)
        if value is not None:
            self.values[key] = value
            self.writes.append((key, value))
        return self.values[key]

    def test_default_preview_does_not_inspect_or_change_a_desktop(self):
        with patch.object(theme, "ensure_guest") as guard, patch.object(theme.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(theme.main([]), 0)
        self.assertIn("PREVIEW ONLY", output.getvalue())
        guard.assert_not_called()
        run.assert_not_called()

    def test_apply_records_prior_settings_and_undo_restores_them(self):
        with patch.object(theme, "ensure_guest", return_value="xfconf-query"), patch.object(theme, "installed", return_value=True), patch.object(theme, "query", side_effect=self.query):
            self.assertEqual(theme.apply_theme("Kali-Dark", self.snapshot), self.snapshot)
            self.assertTrue(all(v == "Kali-Dark" for v in self.values.values()))
            self.assertEqual(json.loads(self.snapshot.read_text())["before"], ["Adwaita", "Adwaita"])
            theme.undo_theme(self.snapshot)
            self.assertTrue(all(v == "Adwaita" for v in self.values.values()))
            self.assertTrue(self.snapshot.exists())

    def test_existing_snapshot_is_never_overwritten_or_settings_changed(self):
        self.snapshot.write_text("keep")
        with patch.object(theme, "ensure_guest", return_value="xfconf-query"), patch.object(theme, "installed", return_value=True), patch.object(theme, "query", side_effect=self.query):
            with self.assertRaises(FileExistsError):
                theme.apply_theme("Kali-Dark", self.snapshot)
        self.assertFalse(self.writes)
        self.assertEqual(self.snapshot.read_text(), "keep")

    def test_undo_refuses_to_replace_later_user_changes(self):
        with patch.object(theme, "ensure_guest", return_value="xfconf-query"), patch.object(theme, "installed", return_value=True), patch.object(theme, "query", side_effect=self.query):
            theme.apply_theme("Kali-Dark", self.snapshot)
            self.values[theme.PROPERTIES[0]] = "CustomTheme"
            self.writes.clear()
            with self.assertRaisesRegex(theme.ThemeError, "changed since Apply"):
                theme.undo_theme(self.snapshot)
        self.assertFalse(self.writes)

    def test_partial_apply_rolls_back_and_keeps_snapshot(self):
        def failing(executable, channel, prop, value=None):
            if channel == "xfwm4" and value == "Kali-Dark":
                raise theme.ThemeError("simulated write failure")
            return self.query(executable, channel, prop, value)
        with patch.object(theme, "ensure_guest", return_value="xfconf-query"), patch.object(theme, "installed", return_value=True), patch.object(theme, "query", side_effect=failing):
            with self.assertRaisesRegex(theme.ThemeError, "rolled back"):
                theme.apply_theme("Kali-Dark", self.snapshot)
        self.assertTrue(all(v == "Adwaita" for v in self.values.values()))
        self.assertTrue(self.snapshot.exists())

    def test_missing_installed_theme_does_not_write_settings_or_snapshot(self):
        with patch.object(theme, "ensure_guest", return_value="xfconf-query"), patch.object(theme, "installed", return_value=False), patch.object(theme, "query") as query:
            with self.assertRaises(theme.ThemeError):
                theme.apply_theme("Kali-Dark", self.snapshot)
        query.assert_not_called()
        self.assertFalse(self.snapshot.exists())

    def test_non_kali_platform_is_rejected_before_any_xfconf_command(self):
        with patch.object(theme.sys, "platform", "win32"), patch.object(theme.subprocess, "run") as run:
            with self.assertRaises(theme.ThemeError):
                theme.ensure_guest()
        run.assert_not_called()

    def test_snapshot_cannot_inject_commands_or_unknown_properties(self):
        self.snapshot.write_text(json.dumps({"format": theme.FORMAT, "before": ["$(touch bad)", "Adwaita"], "applied": "Kali-Dark"}))
        with patch.object(theme, "ensure_guest", return_value="xfconf-query"), patch.object(theme, "query") as query:
            with self.assertRaises(theme.ThemeError):
                theme.undo_theme(self.snapshot)
        query.assert_not_called()
