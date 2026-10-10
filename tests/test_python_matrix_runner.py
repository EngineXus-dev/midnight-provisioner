"""Static opt-in PowerShell Python-matrix safety regression tests.

No Docker daemon, GitHub Actions or VM operations are invoked here.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "Run-Nightglass-Python-Matrix.ps1"


class PythonMatrixRunnerTests(unittest.TestCase):
    def test_exact_interpreters_are_requested_and_results_are_checked(self):
        text = RUNNER.read_text(encoding="utf-8")
        for version in ("3.11", "3.12", "3.13"):
            self.assertIn(f'"{version}"', text)
        self.assertIn("Assert-Exit \"Python $version synthetic tests\"", text)
        self.assertIn("python", text)
        self.assertIn("unittest", text)

    def test_runtime_is_unprivileged_offline_and_readonly(self):
        text = RUNNER.read_text(encoding="utf-8")
        for required in (
            '"--network", "none"',
            '"--read-only"',
            '"--cap-drop", "ALL"',
            '"--security-opt", "no-new-privileges:true"',
            '"--user", "10001:10001"',
            '"--pull", "never"',
            'target=/workspace,readonly',
            '"--memory", "1024m"',
            '"--tmpfs", "/tmp:rw,nosuid,nodev,size=512m"',
        ):
            self.assertIn(required, text)
        for forbidden in ('"--privileged"', '"/dev/kvm"', '"/var/run/docker.sock"'):
            self.assertNotIn(forbidden, text)

    def test_temporary_space_exceeds_backup_recovery_safety_reserve(self):
        # The application intentionally reserves 256 MiB beyond the real
        # backup/recovery fixture payload; a 256m tmpfs is insufficient.
        runner = RUNNER.read_text(encoding="utf-8")
        found = re.search(r'--tmpfs", "/tmp:rw,nosuid,nodev,size=(\d+)m"', runner)
        self.assertIsNotNone(found)
        capacity_mib = int(found.group(1))
        self.assertGreater(capacity_mib, 256)
        self.assertLessEqual(capacity_mib, 768)  # Keep workstation usage low.
        for module in ("backups.py", "recovery.py"):
            content = (ROOT / "nightglass" / module).read_text(encoding="utf-8")
            self.assertIn("256 * 1024 * 1024", content)

    def test_checkout_is_unique_detached_branch_only_and_no_history_rewrite(self):
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("verification/fedora-host-acceptance-preflight", text)
        self.assertIn("worktree add --detach", text)
        self.assertIn("Nightglass-Python-Matrix-", text)
        self.assertIn("Start-Transcript -LiteralPath $logPath -NoClobber", text)
        self.assertIn("EngineXus-dev/nightglass-workspaces", text)
        self.assertIsNone(re.search(
            r"(?im)^\s*&\s*git\s+.*\b(?:clean|reset|merge|rebase|push)\b",
            text
        ))

    def test_only_synthetic_tests_are_claimed(self):
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("GUI/native fixtures NOT run", text)
        self.assertIn("acceptance remains PENDING", text)
        self.assertIn("No merges, resets, git clean, force-push", text)


if __name__ == "__main__":
    unittest.main()
