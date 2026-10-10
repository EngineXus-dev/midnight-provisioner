"""Isolated-process tests for exact Windows QEMU/SELinux fixture coverage."""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "testing" / "run_windows_qemu_subset.py"
EXPECTED = ("test_one", "test_two", "test_three")


class QemuSubsetRunnerCoverageTests(unittest.TestCase):
    def make_fixture(self, *, missing=None, skip=None, duplicate=None, import_error=False):
        tmp = tempfile.TemporaryDirectory(prefix="ng-qemu-tests-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for folder in ("scripts", "tests", "nightglass"):
            (root / folder).mkdir()
        (root / "scripts" / "testing").mkdir()
        shutil.copyfile(SCRIPT, root / "scripts" / "testing" / SCRIPT.name)
        (root / "scripts" / "testing" / "verify_local.py").write_text(
            "WINDOWS_QEMU_CASES = " + repr(EXPECTED) + "\n", encoding="utf-8")
        (root / "nightglass" / "__init__.py").write_text(
            "SYNTHETIC_VALUE = 7\n", encoding="utf-8")
        src = ["import unittest", "from nightglass import SYNTHETIC_VALUE",
               "class SyntheticQemuCases(unittest.TestCase):"]
        for case in EXPECTED:
            if case == missing:
                continue
            if case == skip:
                src.append('    @unittest.skip("simulated unavailable case")')
            src.append(f"    def {case}(self): self.assertEqual(SYNTHETIC_VALUE, 7)")
        if duplicate:
            src += ["class DuplicateCase(unittest.TestCase):",
                    f"    def {duplicate}(self): self.assertTrue(True)"]
        # The extra case is intentionally NOT on the allowlist and would fail.
        src += ["class DeliberatelyExcluded(unittest.TestCase):",
                "    def test_excluded(self): self.fail('should not run')"]
        if import_error:
            src.insert(1, "import missing_nightglass_synthetic_dependency")
        (root / "tests" / "test_kali_process_label.py").write_text(
            "\n".join(src) + "\n", encoding="utf-8")
        return root

    def invoke(self, root):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONNOUSERSITE"] = "1"
        return subprocess.run(
            [sys.executable, "-B", "scripts/testing/run_windows_qemu_subset.py"],
            cwd=root, env=env, text=True, capture_output=True, timeout=20,
            check=False,
        )

    def test_exact_cases_execute_and_unlisted_case_is_not_run(self):
        p = self.invoke(self.make_fixture())
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("All 3 explicitly selected", p.stdout)

    def test_missing_named_case_blocks(self):
        p = self.invoke(self.make_fixture(missing="test_two"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("test_two", p.stderr)

    def test_skipped_named_case_blocks(self):
        p = self.invoke(self.make_fixture(skip="test_one"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("skipped=1", p.stderr)

    def test_duplicate_named_case_blocks(self):
        p = self.invoke(self.make_fixture(duplicate="test_three"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("duplicates", p.stderr)

    def test_import_failure_blocks(self):
        p = self.invoke(self.make_fixture(import_error=True))
        self.assertEqual(p.returncode, 1)
        self.assertIn("discovery or module import failed", p.stderr)

    def test_missing_test_file_blocks(self):
        root = self.make_fixture()
        (root / "tests" / "test_kali_process_label.py").unlink()
        p = self.invoke(root)
        self.assertEqual(p.returncode, 2)
        self.assertIn("Missing, linked", p.stderr)

    def test_runner_is_exact_subset_and_never_operates_on_a_real_guest(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("WINDOWS_QEMU_CASES", source)
        self.assertIn("case._testMethodName", source)
        self.assertIn("run.skipped", source)
        for term in ("subprocess.run", "docker run", "virsh start", "git fetch",
                     "shell=True", "os.system(", "shutil.rmtree("):
            self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
