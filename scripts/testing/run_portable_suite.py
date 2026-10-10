#!/usr/bin/env python3
"""Fail-closed Nightglass Windows-portable unittest subset runner.

A plain unittest discover returns exit 0 for zero collected tests or all
skipped tests. This runner rejects both. No Git/network/Docker/host writes;
only the selected, already-allowlisted synthetic test module is executed.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


def run_pattern(pattern: str, *, root: Path = ROOT) -> int:
    """One actual executed passing case is mandatory; skipped cases disclosed."""
    from verify_local import WINDOWS_PORTABLE_SUITES

    if pattern not in WINDOWS_PORTABLE_SUITES or not pattern.startswith("test_"):
        print("[BLOCKED] Test pattern not on Windows-portable allowlist", file=sys.stderr)
        return 2
    root = root.resolve()
    tests = root / "tests"
    source = tests / pattern
    if (Path.cwd().resolve() != root or tests.is_symlink() or not tests.is_dir()
            or source.is_symlink() or not source.is_file()):
        print("[BLOCKED] Missing, linked, or wrong-checkout test suite", file=sys.stderr)
        return 2
    # Executing 'python scripts/testing/run_portable_suite.py' sets sys.path[0]
    # to scripts/, NOT to the project root. Discovery adds tests/ only;
    # it does not make 'import nightglass' available. Add the trusted
    # checked-out root explicitly before loading test modules.
    # Place the pinned checkout first, even when an inherited PYTHONPATH
    # already lists it after another potentially conflicting package root.
    if str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))
    loader = unittest.TestLoader()
    suite = loader.discover(str(tests), pattern=pattern)
    collected = suite.countTestCases()
    if loader.errors or collected < 1:
        print(f"[BLOCKED] {pattern}: discovery errors or zero cases", file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    executed = result.testsRun - len(result.skipped)
    if (not result.wasSuccessful() or result.expectedFailures
            or result.testsRun != collected or executed < 1):
        print(f"[FAIL] {pattern}: collected={collected}, run={result.testsRun}, "
              f"executed={executed}, skipped={len(result.skipped)}",
              file=sys.stderr)
        return 1
    print(f"[PASS] {pattern}: {executed} executed; "
          f"{len(result.skipped)} platform-specific skipped (not verified)", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Require actual Nightglass Windows-portable tests")
    parser.add_argument("--pattern", required=True)
    args = parser.parse_args(argv)
    return run_pattern(args.pattern)


if __name__ == "__main__":
    raise SystemExit(main())
