"""Synthetic contract tests: required GUI/native fixture suites cannot silently skip.

Never invokes GUI, QEMU, virsh, Docker or installation utilities.
"""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "run_required_suite.py"
VERIFY = ROOT / "scripts" / "verify_local.py"

spec = importlib.util.spec_from_file_location("ng_required_tests", TOOL)
required = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(required)


class RequiredIntegrationSuitesTests(unittest.TestCase):
    def test_only_curated_gui_and_native_suite_names(self):
        self.assertEqual(required.REQUIRED_SUITES, {
            "gui": ("test_gui_smoke.py", 5),
            "native": ("test_native_tools.py", 5),
        })
        with self.assertRaises(ValueError):
            required.run_required("untrusted_tests")

    def invoke_fake(self, *, check="gui", discovered=8, executed=8,
                    skipped=0, expected_failures=0, successful=True, errors=None):
        suite = MagicMock()
        suite.countTestCases.return_value = discovered
        loader = MagicMock()
        loader.discover.return_value = suite
        loader.errors = errors or []
        result = MagicMock()
        result.wasSuccessful.return_value = successful
        result.skipped = [("case", "reason")] * skipped
        result.expectedFailures = [("case", "failure")] * expected_failures
        result.testsRun = executed
        runner = MagicMock()
        runner.run.return_value = result

        with patch.object(required.unittest, "TestLoader", return_value=loader), \
             patch.object(required.unittest, "TextTestRunner", return_value=runner), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            outcome = required.run_required(check)
        return outcome, loader, runner

    def test_actual_success_requires_at_least_five_tests_and_zero_skips(self):
        outcome, loader, runner = self.invoke_fake()
        self.assertEqual(outcome, 0)
        loader.discover.assert_called_once()
        runner.run.assert_called_once()

    def test_zero_or_incomplete_collection_is_a_failure(self):
        for count in (0, 1, 4):
            with self.subTest(collected=count):
                result, _, runner = self.invoke_fake(discovered=count, executed=count)
                self.assertNotEqual(result, 0)
                runner.run.assert_not_called()

    def test_skipped_failing_expected_failure_and_unrun_are_blockers(self):
        cases = (
            {"skipped": 1},
            {"successful": False},
            {"expected_failures": 1},
            {"executed": 7},
            {"errors": ["synthetic import failure"]},
        )
        for case in cases:
            with self.subTest(case=case):
                result, _, _ = self.invoke_fake(**case)
                self.assertNotEqual(result, 0)

    def test_verification_all_uses_explicit_non_skipping_runner(self):
        code = VERIFY.read_text(encoding="utf-8")
        self.assertIn('"scripts/run_required_suite.py", "--check", "gui"', code)
        self.assertIn('"--check", "native"', code)
        self.assertIn("Full Linux verification requires Bash syntax validation.", code)
        self.assertIn("if args.all:", code)
        self.assertIn('"NIGHTGLASS_GUI_SMOKE": "1"', code)

    def test_no_dangerous_operations_in_required_test_runner(self):
        code = TOOL.read_text(encoding="utf-8")
        for forbidden in ("git fetch", "git merge", "docker run",
                          "virsh start", "qemu-system", "Invoke-Expression",
                          "subprocess.run", "shutil.rmtree", "os.system("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)
        self.assertIn("result.skipped", code)
        self.assertIn("result.testsRun != collected", code)


if __name__ == "__main__":
    unittest.main()
