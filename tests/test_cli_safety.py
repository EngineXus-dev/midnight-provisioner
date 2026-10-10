"""CLI guardrails: root refusal for writers, cancellable prompts, kept caps."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nightglass.cli import main
from nightglass.portability import MachinePreferences, load_machine_preferences, save_machine_preferences


class CliSafetyTests(unittest.TestCase):
    def run_cli(self, argv, euid=1000):
        out, err = StringIO(), StringIO()
        with patch("nightglass.cli.os.geteuid", return_value=euid, create=True), redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_root_is_refused_for_writing_commands_only(self):
        with patch("nightglass.cli.save_machine_preferences") as save, \
             patch("nightglass.cli.SourceUpdater") as updater:
            for argv in (["profile", "apply", "auto", "--yes"], ["update", "check"],
                         ["update", "checks", "on"], ["gui"],
                         ["templates", "export", "recon", "/tmp/x.json"]):
                with self.subTest(argv=argv):
                    code, _, err = self.run_cli(argv, euid=0)
                    self.assertEqual(code, 2)
                    self.assertIn("never as root", err)
            save.assert_not_called()
            updater.assert_not_called()
        code, out, _ = self.run_cli(["profile", "show"], euid=0)
        self.assertEqual(code, 0)
        self.assertIn("Profile:", out)

    def test_eof_or_ctrl_c_at_confirmation_cancels(self):
        for error in (EOFError, KeyboardInterrupt):
            with self.subTest(error=error), \
                 patch("nightglass.cli.save_machine_preferences") as save, \
                 patch("nightglass.cli.sys.stdin.isatty", return_value=True), \
                 patch("builtins.input", side_effect=error):
                code, out, _ = self.run_cli(["profile", "apply", "compact"])
                self.assertEqual(code, 1)
                self.assertIn("Cancelled", out)
                save.assert_not_called()

    def test_profile_apply_keeps_user_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "machine.json"
            save_machine_preferences(MachinePreferences(preset="auto", guest_ram_cap_gib=2.0, vcpu_cap=1), path)
            with patch("nightglass.cli.load_machine_preferences", lambda: load_machine_preferences(path)), \
                 patch("nightglass.cli.save_machine_preferences", lambda prefs: save_machine_preferences(prefs, path)):
                code, out, _ = self.run_cli(["profile", "apply", "performance", "--yes"])
            self.assertEqual(code, 0)
            saved = load_machine_preferences(path)
            self.assertEqual((saved.preset, saved.guest_ram_cap_gib, saved.vcpu_cap), ("performance", 2.0, 1))
            self.assertIn("caps are kept", out)

    def test_os_error_is_reported_without_traceback(self):
        with patch("nightglass.cli.save_machine_preferences", side_effect=PermissionError("denied")):
            code, _, err = self.run_cli(["update", "checks", "on"])
        self.assertEqual(code, 2)
        self.assertIn("denied", err)

    def test_hostile_proposal_numbers_are_rejected_not_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "proposal.json"
            path.write_text('{"schema": ' + "9" * 5000 + "}", encoding="utf-8")
            code, _, err = self.run_cli(["proposal-review", "--file", str(path)])
        self.assertEqual(code, 2)
        self.assertIn("proposal rejected", err)

    def test_deeply_nested_guest_json_is_a_tool_error(self):
        from nightglass.kali_setup import _read_bounded_json
        from nightglass.runner import ToolError
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inventory.json"
            path.write_text("[" * 50000 + "]" * 50000, encoding="utf-8")
            with self.assertRaises(ToolError):
                _read_bounded_json(path)


if __name__ == "__main__":
    unittest.main()
