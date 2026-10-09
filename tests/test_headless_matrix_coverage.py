"""No-container synthetic tests for minimum executed-test matrix threshold."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "scripts" / "run_headless_matrix.py"
RELEASE_GATE = ROOT / "scripts" / "Run-Nightglass-Offline-Release-Gate.py"

spec = importlib.util.spec_from_file_location("nightglass_matrix_gate", MATRIX)
matrix = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(matrix)


class MatrixCoverageTests(unittest.TestCase):
    def mock_run(self, *, collected=100, run=100, skips=30,
                 successful=True, expected_failures=0, errors=None):
        suite = MagicMock()
        suite.countTestCases.return_value = collected
        loader = MagicMock()
        loader.discover.return_value = suite
        loader.errors = errors or []
        result = MagicMock()
        result.wasSuccessful.return_value = successful
        result.testsRun = run
        result.skipped = [("fixture", "platform")] * skips
        result.expectedFailures = [("fixture", "known failure")] * expected_failures
        runner = MagicMock()
        runner.run.return_value = result
        with patch.object(matrix.unittest, "TestLoader", return_value=loader), \
             patch.object(matrix.unittest, "TextTestRunner", return_value=runner), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            value = matrix.run_matrix()
        return value, loader, runner

    def test_pass_requires_actual_execution_not_just_collected(self):
        status, loader, runner = self.mock_run()
        self.assertEqual(status, 0)
        loader.discover.assert_called_once()
        runner.run.assert_called_once()

    def test_zero_and_small_collections_are_blocked(self):
        for n in (0, 1, matrix.MIN_COLLECTED-1):
            with self.subTest(collected=n):
                status, _, runner = self.mock_run(collected=n, run=n, skips=0)
                self.assertNotEqual(status, 0)
                runner.run.assert_not_called()

    def test_mostly_skipped_collections_fail(self):
        status, _, _ = self.mock_run(collected=100, run=100,
                                    skips=100-matrix.MIN_EXECUTED+1)
        self.assertEqual(status, 1)

    def test_partial_execution_known_failures_import_errors_fail(self):
        for case in (
            dict(run=95),
            dict(successful=False),
            dict(expected_failures=1),
            dict(errors=["synthetic import error"]),
        ):
            with self.subTest(case=case):
                status, _, _ = self.mock_run(**case)
                self.assertNotEqual(status, 0)

    def test_release_gate_invokes_minimum_matrix_checker_for_each_version(self):
        source = RELEASE_GATE.read_text(encoding="utf-8")
        self.assertIn('"python", "-B", "scripts/run_headless_matrix.py"', source)
        self.assertIn('VERSIONS = ("3.11", "3.12", "3.13")', source)
        self.assertIn('"--network", "none"', source)
        self.assertNotIn('"python", "-B", "-m", "unittest", "discover"', source)

    def test_safe_synthetic_purpose(self):
        code = MATRIX.read_text(encoding="utf-8")
        self.assertGreaterEqual(matrix.MIN_COLLECTED, 50)
        self.assertGreaterEqual(matrix.MIN_EXECUTED, 30)
        for bad in ("subprocess", "git fetch", "docker", "virsh", "setup.exe",
                    "shutil.rmtree", "os.system(", "Invoke-Expression"):
            self.assertNotIn(bad, code)


if __name__ == "__main__":
    unittest.main()
