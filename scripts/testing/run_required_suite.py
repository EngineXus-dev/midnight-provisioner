#!/usr/bin/env python3
"""Fail-closed Nightglass opt-in GUI/native fixture test runner.

Only two curated suites are allowed. Unlike plain unittest discovery,
a missing, skipped or zero-test GUI/native suite is a FAILURE, never PASS.
Runs only inside the explicitly requested verification environment;
never launches a guest, downloads tools or changes host configuration.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_SUITES = {
    "gui": ("test_gui_smoke.py", 5),
    "native": ("test_native_tools.py", 5),
}


def run_required(check: str) -> int:
    """Return 0 only if the required suite really executed and passed."""
    if check not in REQUIRED_SUITES:
        raise ValueError("Unknown required integration test group")
    filename, minimum = REQUIRED_SUITES[check]
    source = ROOT / "tests" / filename
    if source.is_symlink() or not source.is_file():
        print("[BLOCKED] Required test file missing or linked", file=sys.stderr)
        return 2
    if Path.cwd().resolve() != ROOT:
        print("[BLOCKED] Must run from the isolated project root", file=sys.stderr)
        return 2
    # Direct execution from scripts/ does not implicitly add the
    # repository root needed for 'import nightglass' in GUI/native tests.
    # Place the pinned checkout first, even when an inherited PYTHONPATH
    # already lists it after another potentially conflicting package root.
    if str(ROOT) in sys.path:
        sys.path.remove(str(ROOT))
    sys.path.insert(0, str(ROOT))
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), pattern=filename)
    collected = suite.countTestCases()
    if loader.errors or collected < minimum:
        print(f"[BLOCKED] {check}: collected {collected}, required at least {minimum}",
              file=sys.stderr)
        for issue in loader.errors:
            print("[BLOCKED] Test import failed:", issue[:200], file=sys.stderr)
        return 1
    print(f"[CHECK] Required {check} suite collected {collected} tests", flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if (not result.wasSuccessful() or result.skipped or result.expectedFailures
            or result.testsRun != collected or result.testsRun < minimum):
        print(f"[FAIL] {check}: run={result.testsRun}, skipped={len(result.skipped)}, "
              f"expected_failures={len(result.expectedFailures)}, "
              f"collected={collected}", file=sys.stderr)
        return 1
    print(f"[PASS] {check}: {result.testsRun} actual tests; zero skips", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Require actual Nightglass Qt/native tests")
    parser.add_argument("--check", choices=sorted(REQUIRED_SUITES), required=True)
    args = parser.parse_args(argv)
    return run_required(args.check)


if __name__ == "__main__":
    raise SystemExit(main())
