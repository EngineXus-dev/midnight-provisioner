#!/usr/bin/env python3
"""Require every exact Windows-safe QEMU/SELinux synthetic case to run.

Read-only local unit tests only; no guest processes, virsh, Docker or Git.
The test file and expected names are fixed by verify_local, not user input.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEST_FILE = "test_kali_process_label.py"


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def run_exact_cases(*, root: Path = ROOT) -> int:
    """Return success only when every allowlisted QEMU synthetic test executes."""
    from verify_local import WINDOWS_QEMU_CASES

    root = root.resolve()
    test_folder = root / "tests"
    source = test_folder / TEST_FILE
    if (Path.cwd().resolve() != root or test_folder.is_symlink()
            or not test_folder.is_dir() or source.is_symlink()
            or not source.is_file()):
        print("[BLOCKED] Missing, linked, or wrong-checkout QEMU test file", file=sys.stderr)
        return 2
    expected = tuple(WINDOWS_QEMU_CASES)
    if (not expected or len(set(expected)) != len(expected)
            or any(not isinstance(n, str) or not n.startswith("test_")
                   for n in expected)):
        print("[BLOCKED] Invalid or duplicated QEMU case allowlist", file=sys.stderr)
        return 2
    if str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))
    loader = unittest.TestLoader()
    suite = loader.discover(str(test_folder), pattern=TEST_FILE)
    found = list(flatten(suite))
    if loader.errors or not found:
        print("[BLOCKED] QEMU test discovery or module import failed", file=sys.stderr)
        return 1
    selected = [case for case in found if case._testMethodName in expected]
    counts = Counter(case._testMethodName for case in selected)
    if set(counts) != set(expected) or any(count != 1 for count in counts.values()):
        missing = sorted(set(expected) - set(counts))
        duplicated = sorted(k for k, value in counts.items() if value != 1)
        print(f"[BLOCKED] QEMU selected case inventory mismatch: "
              f"missing={missing}, duplicates={duplicated}", file=sys.stderr)
        return 1
    run = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(selected))
    if (not run.wasSuccessful() or run.skipped or run.expectedFailures
            or run.testsRun != len(expected)):
        print(f"[FAIL] QEMU selection: expected={len(expected)}, "
              f"run={run.testsRun}, skipped={len(run.skipped)}", file=sys.stderr)
        return 1
    print(f"[PASS] All {len(expected)} explicitly selected QEMU cases executed; "
          "none skipped", flush=True)
    return 0


def main() -> int:
    return run_exact_cases()


if __name__ == "__main__":
    raise SystemExit(main())
