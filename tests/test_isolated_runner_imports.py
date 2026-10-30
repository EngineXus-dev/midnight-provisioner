"""Actual subprocess checks for the scripts/ versus project-root import gap.

Makes ONLY disposable temp project trees; never starts VMs, Docker, Git or
PowerShell, and never edits a user checkout. Runs actual three GitHub
runner scripts under the same 'python -B scripts/...' invocation as release.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNERS = (
    "run_portable_suite.py",
    "run_headless_matrix.py",
    "run_required_suite.py",
)


class IsolatedRunnerImportTests(unittest.TestCase):
    def fixture(self):
        tmp = tempfile.TemporaryDirectory(prefix="midnight-provisioner-runner-import-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name in ("scripts", "tests", "midnight_provisioner"):
            (root / name).mkdir()
        (root / "scripts" / "testing").mkdir()
        (root / "midnight_provisioner" / "__init__.py").write_text(
            "SYNTHETIC_SENTINEL = 31415\n", encoding="utf-8")
        for name in RUNNERS:
            shutil.copyfile(ROOT / "scripts" / "testing" / name, root / "scripts" / "testing" / name)
        (root / "scripts" / "testing" / "verify_local.py").write_text(
            'WINDOWS_PORTABLE_SUITES = ("test_synthetic_fixture.py",)\n',
            encoding="utf-8")
        for name, n in (
            ("test_synthetic_fixture.py", 65),
            ("test_gui_smoke.py", 5),
            ("test_native_tools.py", 5),
        ):
            code = [
                "import unittest",
                "from midnight_provisioner import SYNTHETIC_SENTINEL",
                "class SyntheticMidnightProvisionerFixture(unittest.TestCase):",
            ]
            for i in range(n):
                code.append(
                    f"    def test_{i:03d}(self): "
                    "self.assertEqual(SYNTHETIC_SENTINEL, 31415)")
            (root / "tests" / name).write_text(
                "\n".join(code) + "\n", encoding="utf-8")
        return root

    def run_cli(self, root: Path, *args: str):
        env = os.environ.copy()
        # A developer's PYTHONPATH must not accidentally hide the broken
        # source-root import by making 'midnight-provisioner' globally importable.
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, "-B", *args],
            cwd=root, env=env, capture_output=True, text=True,
            check=False, timeout=35,
        )

    def test_portable_runner_imports_real_project_package(self):
        root = self.fixture()
        result = self.run_cli(
            root, "scripts/testing/run_portable_suite.py", "--pattern",
            "test_synthetic_fixture.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("65 executed", result.stdout)

    def test_matrix_runner_imports_project_and_executes_enough_tests(self):
        root = self.fixture()
        result = self.run_cli(root, "scripts/testing/run_headless_matrix.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("75 executed", result.stdout)

    def test_required_gui_imports_project_in_script_mode(self):
        root = self.fixture()
        result = self.run_cli(
            root, "scripts/testing/run_required_suite.py", "--check", "gui")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("5 actual tests", result.stdout)

    def test_required_native_imports_project_in_script_mode(self):
        root = self.fixture()
        result = self.run_cli(
            root, "scripts/testing/run_required_suite.py", "--check", "native")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("5 actual tests", result.stdout)

    def test_missing_project_package_fails_closed(self):
        root = self.fixture()
        (root / "midnight_provisioner" / "__init__.py").unlink()
        for command in (
            ("scripts/testing/run_portable_suite.py", "--pattern", "test_synthetic_fixture.py"),
            ("scripts/testing/run_headless_matrix.py",),
            ("scripts/testing/run_required_suite.py", "--check", "gui"),
        ):
            with self.subTest(command=command):
                result = self.run_cli(root, *command)
                self.assertNotEqual(result.returncode, 0)

    def test_actual_runner_sources_repair_root_import_gap(self):
        for name in RUNNERS:
            with self.subTest(name=name):
                source = (ROOT / "scripts" / "testing" / name).read_text(encoding="utf-8")
                self.assertIn("sys.path.insert(0, str(", source)
                self.assertIn("unittest.TestLoader()", source)


if __name__ == "__main__":
    unittest.main()
