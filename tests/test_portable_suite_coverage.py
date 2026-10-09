"""Zero-write synthetic regressions for Windows-portable test completeness."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_portable_suite.py"
spec = importlib.util.spec_from_file_location("nightglass_portable_suite_test", RUNNER)
portable = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(portable)


class PortableSuiteCoverageTests(unittest.TestCase):
    def simulate(self, *, discovered=4, ran=4, skips=0,
                 passed=True, expected_failures=0, errors=()):
        suite = MagicMock()
        suite.countTestCases.return_value = discovered
        loader = MagicMock()
        loader.discover.return_value = suite
        loader.errors = list(errors)
        result = MagicMock()
        result.testsRun = ran
        result.skipped = [("case", "reason")] * skips
        result.expectedFailures = [("case", "reason")] * expected_failures
        result.wasSuccessful.return_value = passed
        runner = MagicMock()
        runner.run.return_value = result
        with patch.dict(sys.modules, {"verify_local": SimpleNamespace(
                    WINDOWS_PORTABLE_SUITES=("test_candidate_branch_contract.py",))}), \
             patch.object(portable.unittest, "TestLoader", return_value=loader), \
             patch.object(portable.unittest, "TextTestRunner", return_value=runner), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            value = portable.run_pattern("test_candidate_branch_contract.py")
        return value, loader, runner

    def test_real_executed_tests_pass(self):
        outcome, loader, runner = self.simulate()
        self.assertEqual(outcome, 0)
        loader.discover.assert_called_once()
        runner.run.assert_called_once()

    def test_zero_discovery_blocks(self):
        outcome, _, runner = self.simulate(discovered=0, ran=0)
        self.assertEqual(outcome, 1)
        runner.run.assert_not_called()

    def test_all_skipped_blocks_even_if_unittest_reports_success(self):
        outcome, _, _ = self.simulate(discovered=4, ran=4, skips=4)
        self.assertEqual(outcome, 1)

    def test_partial_skips_are_disclosed_but_real_execution_required(self):
        outcome, _, _ = self.simulate(discovered=4, ran=4, skips=3)
        self.assertEqual(outcome, 0)

    def test_failure_import_error_expected_failure_and_partial_run_block(self):
        for case in (
            {"passed": False}, {"errors": ("synthetic failed import",)},
            {"expected_failures": 1}, {"ran": 3},
        ):
            with self.subTest(case=case):
                outcome, _, _ = self.simulate(**case)
                self.assertEqual(outcome, 1)

    def test_unknown_suite_pattern_fails_without_importing(self):
        with patch.dict(sys.modules, {"verify_local": SimpleNamespace(
                    WINDOWS_PORTABLE_SUITES=("test_candidate_branch_contract.py",))}), \
             patch.object(portable.unittest, "TestLoader",
                          side_effect=AssertionError("Should not load unknown tests")):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(portable.run_pattern("bad_pattern.py"), 2)

    def test_no_shell_docker_git_or_file_mutation(self):
        source = RUNNER.read_text(encoding="utf-8")
        for term in ("subprocess.run", "shell=True", "git fetch", "git merge",
                     "docker run", "shutil.rmtree", "os.system(",
                     "open(path, 'w'", "setup.exe", "Format-Volume"):
            with self.subTest(term=term):
                self.assertNotIn(term, source)
        self.assertIn("executed = result.testsRun - len(result.skipped)", source)
        self.assertIn("result.testsRun != collected", source)


if __name__ == "__main__":
    unittest.main()
