#!/usr/bin/env python3
"""Fail-closed Python compatibility matrix test runner.

This executes only synthetic project unittests in the *already isolated*
Python Docker container. Qt/native suites may legitimately skip in slim
images and run separately as REQUIRED Fedora fixture checks.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
MIN_COLLECTED = 60
MIN_EXECUTED = 40


def run_matrix() -> int:
    source = ROOT / "tests"
    if (Path.cwd().resolve() != ROOT or source.is_symlink()
            or not source.is_dir()):
        print("[BLOCKED] Must run in isolated Nightglass source tree", file=sys.stderr)
        return 2
    # Python invoked via 'scripts/testing/run_headless_matrix.py' otherwise
    # has scripts/ and tests/ but NOT the checkout root on sys.path.
    # The synthetic modules legitimately import nightglass.
    # Place the pinned checkout first, even when an inherited PYTHONPATH
    # already lists it after another potentially conflicting package root.
    if str(ROOT) in sys.path:
        sys.path.remove(str(ROOT))
    sys.path.insert(0, str(ROOT))
    loader = unittest.TestLoader()
    suite = loader.discover(str(source), pattern="test*.py")
    collected = suite.countTestCases()
    if loader.errors or collected < MIN_COLLECTED:
        print(f"[BLOCKED] Only collected {collected} tests; minimum {MIN_COLLECTED}",
              file=sys.stderr)
        return 1
    print(f"[CHECK] Python matrix collected {collected} test cases", flush=True)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    actually_executed = result.testsRun - len(result.skipped)
    if (not result.wasSuccessful() or result.expectedFailures
            or result.testsRun != collected or actually_executed < MIN_EXECUTED):
        print(f"[FAIL] Python matrix: collected={collected}, run={result.testsRun}, "
              f"executed={actually_executed}, skipped={len(result.skipped)}, "
              f"expectedFailures={len(result.expectedFailures)}",
              file=sys.stderr)
        return 1
    print(f"[PASS] Python matrix: {actually_executed} executed, "
          f"{len(result.skipped)} platform/optional skips (NOT CERTIFIED by this matrix)",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_matrix())
