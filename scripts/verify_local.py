#!/usr/bin/env python3
"""Nightglass offline verification: local-only, no sudo/pip/GitHub Actions/VMs.

Run from a checkout: python -B scripts/verify_local.py
For Qt opt-in: python -B scripts/verify_local.py --gui
For real native fixture tools (NO guests): python -B scripts/verify_local.py --native
The script runs the repository's existing tests; it never downloads dependencies,
starts VMs, connects to GitHub, changes host security settings, or edits files.
"""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "build", "dist", "__pycache__", ".tox"}
SUBPROCESS_ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}


def python_sources():
    for directory in ("nightglass", "tests", "scripts"):
        folder = ROOT / directory
        if not folder.is_dir():
            raise RuntimeError(f"Required project folder missing: {directory}")
        for item in folder.rglob("*.py"):
            if not any(part in SKIP_DIRS for part in item.relative_to(ROOT).parts):
                yield item


def check_syntax() -> int:
    checked = 0
    for item in python_sources():
        try:
            with item.open("r", encoding="utf-8") as source:
                ast.parse(source.read(), filename=str(item))
        except (OSError, UnicodeError, SyntaxError) as exc:
            print(f"[FAIL] Python syntax: {item.relative_to(ROOT)}: {exc}", file=sys.stderr)
            return 1
        checked += 1
    print(f"[PASS] Parsed {checked} Python sources without creating .pyc files", flush=True)
    return 0


def run_command(title: str, argv: list[str], *, extra_env=None, dry_run=False) -> int:
    print(f"\n[CHECK] {title}\n        {' '.join(argv)}", flush=True)
    if dry_run:
        return 0
    environment = SUBPROCESS_ENV.copy()
    if extra_env:
        environment.update(extra_env)
    try:
        result = subprocess.run(
            argv, cwd=ROOT, env=environment, shell=False, check=False,
        )
    except OSError as exc:
        print(f"[FAIL] {title}: {exc}", file=sys.stderr)
        return 1
    print(("[PASS] " if result.returncode == 0 else "[FAIL] ") + title, flush=True)
    return 0 if result.returncode == 0 else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Nightglass offline local source/tests check; never invokes sudo, pip, VMs or GitHub"
    )
    parser.add_argument(
        "--gui", action="store_true", help="Additionally exercise actual PySide6 offscreen GUI"
    )
    parser.add_argument(
        "--native", action="store_true",
        help="Additionally exercise native libvirt/QEMU fixtures WITHOUT running VMs",
    )
    parser.add_argument(
        "--all", action="store_true", help="Equivalent to --gui --native"
    )
    parser.add_argument(
        "--focused", action="store_true",
        help="Only run recent Kali sVirt/VM tests (quick troubleshooting, not full verification)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Describe the checks only; does not execute tests",
    )
    args = parser.parse_args(argv)
    if args.all:
        args.gui = args.native = True

    print("Nightglass OFFLINE integration verification")
    print(f"Checkout: {ROOT}")
    print("No GitHub Actions, VM launches, sudo, pip install or network requests are initiated.")
    print("GitHub status checks will NOT be updated by this local test run.")
    failed = False

    if args.dry_run:
        print("[DRY RUN] Would parse local Python source and run selected checks")
    else:
        failed |= bool(check_syntax())

    bash = shutil.which("bash")
    if bash:
        scripts = [
            str(ROOT / "scripts" / "setup-nightglass.sh"),
            str(ROOT / "scripts" / "fedora-recovery-smoke.sh"),
        ]
        if all(Path(script).is_file() for script in scripts):
            failed |= bool(run_command("Bash syntax only (no commands run)", [
                bash, "-n", *scripts,
            ], dry_run=args.dry_run))

    if args.focused:
        for pattern in (
            "test_kali_process_label.py",
            "test_kali_running.py",
            "test_kali_recovery_registration.py",
            "test_kali_recovery_link.py",
        ):
            failed |= bool(run_command(f"Unit tests: {pattern}", [
                sys.executable, "-B", "-m", "unittest", "discover",
                "-s", "tests", "-p", pattern, "-v",
            ], dry_run=args.dry_run))
    else:
        failed |= bool(run_command("Python unittest suite (no VMs)", [
            sys.executable, "-B", "-m", "unittest", "discover",
            "-s", "tests", "-v",
        ], dry_run=args.dry_run))

    if args.gui:
        # Explicitly fail if Qt is unavailable; do not claim a skipped suite passed.
        failed |= bool(run_command("PySide6 offscreen GUI smoke", [
            sys.executable, "-B", "-m", "unittest", "discover",
            "-s", "tests", "-p", "test_gui_smoke.py", "-v",
        ], extra_env={
            "QT_QPA_PLATFORM": "offscreen",
            "NIGHTGLASS_GUI_SMOKE": "1",
        }, dry_run=args.dry_run))
    if args.native:
        # Never run host commands beyond fixed read-only fixture validators.
        missing = [name for name in ("virt-xml-validate", "qemu-img")
                   if not shutil.which(name)]
        if missing and not args.dry_run:
            print("[FAIL] Native fixtures unavailable: " + ", ".join(missing),
                  file=sys.stderr)
            print("Do not enable libvirt guests or use sudo to make this test pass.")
            failed = True
        else:
            failed |= bool(run_command("Native QEMU/libvirt fixture checks (NO VMs)", [
                sys.executable, "-B", "-m", "unittest", "discover",
                "-s", "tests", "-p", "test_native_tools.py", "-v",
            ], dry_run=args.dry_run))
    if failed:
        print("\nRESULT: FAILED or INCOMPLETE. Keep integration PRs as drafts.", file=sys.stderr)
        return 1
    print("\nRESULT: " + (
        "DRY RUN ONLY (not tested)" if args.dry_run else
        "Selected LOCAL checks passed; Fedora hardware acceptance still pending."
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
