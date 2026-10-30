"""Tests: one installation, hardware-clamped preferences and cautious updates."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from midnight_provisioner.portability import (
    MachinePreferences, budget_for, load_machine_preferences, save_machine_preferences,
)
from midnight_provisioner.models import WorkspaceError
from midnight_provisioner.runner import ToolError
from midnight_provisioner.updates import SourceUpdater


class MachineBudgetTests(unittest.TestCase):
    def test_auto_adjusts_to_real_machine_size(self):
        for ram, expect_max in ((7.7, 1), (8.0, 1), (16.0, 2), (24.0, 3), (32.0, 3)):
            with self.subTest(ram=ram):
                budget = budget_for(ram, 8)
                self.assertEqual(budget.active_vm_cap, expect_max)
                reserve = 4 if ram < 11 else 6 if ram < 20 else 8
                self.assertLessEqual(budget.guest_ram_cap_gib * budget.active_vm_cap, ram - reserve + 0.1)
                self.assertLessEqual(budget.vcpu_cap, 7)

    def test_low_ram_profile_cannot_turn_into_high_ram(self):
        p = MachinePreferences(
            preset="performance", guest_ram_cap_gib=128, active_vm_cap=128, vcpu_cap=128,
        )
        b = budget_for(7.7, 6, p)
        self.assertEqual(b.active_vm_cap, 1)
        self.assertLessEqual(b.guest_ram_cap_gib, 3.5)
        self.assertLessEqual(b.vcpu_cap, 5)

    def test_compact_is_one_vm_even_on_large_host(self):
        b = budget_for(32, 12, MachinePreferences(preset="compact"))
        self.assertEqual(b.active_vm_cap, 1)
        self.assertLessEqual(b.guest_ram_cap_gib, 2.5)

    def test_unknown_ram_fails_conservatively(self):
        budget = budget_for(None, None)
        self.assertEqual(budget.active_vm_cap, 1)
        self.assertLessEqual(budget.guest_ram_cap_gib, 2)
        self.assertEqual(budget.vcpu_cap, 1)

    def test_invalid_overrides_rejected(self):
        for invalid in (
            {"preset": "administrator"},
            {"guest_ram_cap_gib": -1},
            {"guest_ram_cap_gib": True},
            {"active_vm_cap": 0},
            {"vcpu_cap": 3.5},
            {"automatic_update_checks": "yes"},
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(WorkspaceError):
                    MachinePreferences(**invalid)

    def test_machine_prefs_roundtrip_and_file_mode(self):
        with tempfile.TemporaryDirectory() as root:
            filename = Path(root) / "machine.json"
            original = MachinePreferences(
                preset="balanced", guest_ram_cap_gib=4.0, active_vm_cap=2, vcpu_cap=3,
                automatic_update_checks=True,
            )
            if os.name == "nt":
                # Native Windows has no fchmod; test serialization while
                # retaining the POSIX permissions call in production.
                with patch("midnight_provisioner.portability.os.fchmod", create=True):
                    save_machine_preferences(original, filename)
            else:
                save_machine_preferences(original, filename)
            self.assertEqual(load_machine_preferences(filename), original)
            if os.name != "nt":
                self.assertEqual(filename.stat().st_mode & 0o777, 0o600)
            self.assertEqual((Path(root) / "machine.json").exists(), True)

    def test_machine_prefs_refuse_symlink(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "source.json"
            source.write_text("{}")
            dest = Path(root) / "machine.json"
            try:
                dest.symlink_to(source)
            except (OSError, NotImplementedError):
                self.skipTest("Creating test symlinks requires unavailable OS privileges")
            with self.assertRaises(WorkspaceError):
                save_machine_preferences(MachinePreferences(), dest)
            with self.assertRaises(WorkspaceError):
                load_machine_preferences(dest)

    def test_single_setup_script_replaces_ram_specific_installs(self):
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        self.assertTrue((scripts / "install" / "setup-midnight-provisioner.sh").exists())
        self.assertFalse((scripts / "Setup-8GB.sh").exists())
        self.assertFalse((scripts / "Setup-32GB.sh").exists())


class FakeSourceUpdater(SourceUpdater):
    def __init__(self, root: Path):
        super().__init__(root)
        self.calls = []
        self.responses = {
            ("rev-parse", "--show-toplevel"): str(root),
            ("remote", "get-url", "origin"): "https://github.com/EngineXus-dev/midnight-provisioner.git",
            ("symbolic-ref", "--quiet", "--short", "HEAD"): "main",
            ("status", "--porcelain", "--untracked-files=normal"): "",
            ("fetch", "--no-tags", "origin", "main"): "",
            ("rev-list", "--left-right", "--count", "HEAD...refs/remotes/origin/main"): "0 1",
            ("rev-parse", "HEAD"): "a" * 40,
            ("rev-parse", "refs/remotes/origin/main"): "b" * 40,
            ("merge", "--ff-only", "--no-edit", "b" * 40): "",
        }

    def _git(self, *args, timeout=35):
        self.calls.append(args)
        if args not in self.responses:
            raise AssertionError(f"Unexpected Git command: {args}")
        return self.responses[args]


class SafeUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        (self.root / "pyproject.toml").write_text("[project]\nname='midnight-provisioner'\n")
        self.updater = FakeSourceUpdater(self.root)

    def test_update_needs_explicit_consent(self):
        with self.assertRaisesRegex(ToolError, "confirmation"):
            self.updater.apply()
        self.assertFalse(self.updater.calls)

    def test_updates_are_fast_forward_only(self):
        result = self.updater.apply(confirmed=True)
        self.assertIn("Updated", result)
        self.assertIn(("merge", "--ff-only", "--no-edit", "b" * 40), self.updater.calls)

    def test_dirty_checkout_stops_before_fetch(self):
        self.updater.responses[("status", "--porcelain", "--untracked-files=normal")] = "?? .env"
        with self.assertRaisesRegex(ToolError, "Local source changes"):
            self.updater.apply(confirmed=True)
        self.assertFalse(any(call[0] == "fetch" for call in self.updater.calls))

    def test_wrong_branch_blocks_update(self):
        self.updater.responses[("symbolic-ref", "--quiet", "--short", "HEAD")] = "feat/foo"
        with self.assertRaisesRegex(ToolError, "only run on main"):
            self.updater.check()
        self.assertFalse(any(call[0] == "fetch" for call in self.updater.calls))

    def test_unrecognized_origin_blocks_update(self):
        self.updater.responses[("remote", "get-url", "origin")] = "https://example.org/fork.git"
        with self.assertRaisesRegex(ToolError, "Origin does not match"):
            self.updater.check()
        self.assertFalse(any(call[0] == "fetch" for call in self.updater.calls))

    def test_divergent_history_blocks_merge(self):
        self.updater.responses[("rev-list", "--left-right", "--count", "HEAD...refs/remotes/origin/main")] = "2 3"
        with self.assertRaisesRegex(ToolError, "diverged"):
            self.updater.apply(confirmed=True)
        self.assertFalse(any(call[0] == "merge" for call in self.updater.calls))


if __name__ == "__main__":
    unittest.main()
