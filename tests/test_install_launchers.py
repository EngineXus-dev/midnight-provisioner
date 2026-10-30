import importlib.util
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("launchers", ROOT / "scripts/install/install_launchers.py")
launchers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launchers)


class LauncherTests(unittest.TestCase):
    def test_menu_and_desktop_point_to_correct_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            executable = base / "data with spaces" / "midnight-provisioner"
            launchers.install(executable, base / "applications", base / "Localized Desktop")
            menu = base / "applications/midnight-provisioner.desktop"
            desktop = base / "Localized Desktop/midnight-provisioner.desktop"
            self.assertEqual(menu.read_bytes(), desktop.read_bytes())
            self.assertIn('Exec="' + str(executable) + '" gui', menu.read_text())
            if os.name == "posix":
                self.assertEqual(desktop.stat().st_mode & 0o777, 0o755)
                self.assertEqual(menu.stat().st_mode & 0o777, 0o644)

    def test_exec_escapes_field_codes_and_special_characters(self):
        result = launchers.exec_arg('/tmp/a $b%f"c\\d')
        self.assertIn("%%f", result)
        self.assertIn("\\\\$", result)
        self.assertIn("\\\\\\\\", result)
        for value in ("/tmp/a\nb", "/tmp/a=b"):
            with self.assertRaises(ValueError):
                launchers.exec_arg(value)

    def test_first_login_is_idempotent_and_respects_desktop_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            # The test container's /tmp can be mounted noexec. Use a real
            # installed executable; this test exercises first-login state,
            # not permissions on an invented console-script fixture.
            executable = Path(sys.executable)
            arguments = ["install_launchers.py", "--command", str(executable),
                         "--desktop-only", "--first-login"]
            with patch.dict(os.environ, {"XDG_DATA_HOME": str(base / "data")}), \
                 patch.object(launchers, "desktop_dir", return_value=base / "Bureau"), \
                 patch("sys.argv", arguments):
                launchers.main()
                shortcut = base / "Bureau/midnight-provisioner.desktop"
                self.assertTrue(shortcut.exists())
                shortcut.unlink()
                launchers.main()
                self.assertFalse(shortcut.exists())

    def test_disabled_desktop_does_not_create_home_shortcut(self):
        result = type("Result", (), {"stdout": str(Path.home()) + "\n"})()
        with patch.object(launchers.subprocess, "run", return_value=result):
            self.assertIsNone(launchers.desktop_dir())
