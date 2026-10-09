#!/usr/bin/env python3
"""Nightglass read-only local CI alternative.

No sudo, guest launch, package install, network request, GitHub Actions job,
source-tree deletion or overwrite. Tests use unittest's existing temp fixtures.

Windows checks are deliberately PARTIAL: POSIX mode bits, symlinks,
SELinux, /proc and libvirt acceptance require a real Linux/Fedora runner.
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
SUBPROCESS_ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTHONFAULTHANDLER": "1"}

# Allowlisted synthetic suites whose behavior is independent of Windows
# filesystem mode bits, Windows symlink privileges and POSIX OS APIs.
# All other tests remain PENDING real Linux execution, not PASS or SKIPPED
# as if their security guarantees had been tested on Windows.
WINDOWS_PORTABLE_SUITES = (
    "test_launch_parity.py",
    "test_managed_state.py",
    "test_resources.py",
    "test_svirt_policy.py",
    "test_kali_templates.py",
    "test_fedora_docker_runner.py",
    "test_host_acceptance.py",
    "test_python_matrix_runner.py",
    "test_windows_dualboot_review.py",
    "test_windows11_lite_profile.py",
    "test_windows11_pro_custom.py",
    "test_offline_release_gate.py",
)

# Cross-platform synthetic /proc process checks only: excludes the strict
# POSIX chmod-0600 test, but never changes/relaxes real Fedora checks.
WINDOWS_QEMU_CASES = (
    "test_cli_observer_never_autostarts_vm_or_requests_root",
    "test_different_guest_uuid_or_name_never_matches",
    "test_different_original_vm_name_is_rejected_before_proc_reads",
    "test_duplicate_matching_process_is_ambiguous_and_refused",
    "test_invalid_or_changed_libvirt_xml_blocks",
    "test_linux_proc_stat_starttime_field_22_fixture_is_exact",
    "test_missing_process_and_unreadable_other_process",
    "test_one_unique_qemu_and_actual_label_produce_non_attestation_pass",
    "test_process_disappears_during_recheck",
    "test_qemu_process_start_time_change_fails_closed",
    "test_running_vm_stops_during_recheck",
    "test_runtime_failure_prevents_proc_enumeration",
    "test_user_cannot_read_matching_process_label",
    "test_wrong_actual_selinux_label_is_blocked",
)

LINUX_FOCUSED_SUITES = (
    "test_kali_process_label.py",
    "test_kali_running.py",
    "test_kali_recovery_registration.py",
    "test_kali_recovery_link.py",
)


def python_sources():
    for directory in ("nightglass", "tests", "scripts"):
        folder = ROOT / directory
        if not folder.is_dir():
            raise RuntimeError(f"Required project folder missing: {directory}")
        for item in folder.rglob("*.py"):
            if not any(part in SKIP_DIRS for part in item.relative_to(ROOT).parts):
                yield item


def check_syntax() -> int:
    count = 0
    try:
        for item in python_sources():
            with item.open("r", encoding="utf-8") as source:
                ast.parse(source.read(), filename=str(item))
            count += 1
    except (OSError, UnicodeError, SyntaxError, RuntimeError) as exc:
        print(f"[FAIL] Python source syntax: {exc}", file=sys.stderr)
        return 1
    print(f"[PASS] Parsed {count} Python source files, no pyc files generated", flush=True)
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
    if result.returncode != 0:
        print(f"[DIAGNOSTIC] {title}: subprocess exit code {result.returncode}", flush=True)
        if result.returncode < 0 and sys.platform.startswith("linux"):
            import signal
            try:
                print(f"[DIAGNOSTIC] Terminated by {signal.Signals(-result.returncode).name}", flush=True)
            except ValueError:
                print("[DIAGNOSTIC] Terminated by unknown signal", flush=True)
    print(("[PASS] " if result.returncode == 0 else "[FAIL] ") + title, flush=True)
    return 0 if result.returncode == 0 else 1


def unit_args(pattern: str, *, matches=()) -> list[str]:
    args = [
        sys.executable, "-B", "-m", "unittest", "discover",
        "-s", "tests", "-p", pattern, "-v",
    ]
    for match in matches:
        args.extend(("-k", match))
    return args


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline Nightglass checks (Windows subset or Linux full suite)"
    )
    parser.add_argument("--focused", action="store_true",
                        help="Focus latest Kali recovery/sVirt synthetic tests")
    parser.add_argument("--gui", action="store_true",
                        help="Also run PySide6 offscreen GUI smoke (must already be installed)")
    parser.add_argument("--native", action="store_true",
                        help="Also run native libvirt/QEMU fixtures on a Linux host")
    parser.add_argument("--all", action="store_true", help="Also request --gui --native")
    parser.add_argument("--full", action="store_true",
                        help="Force full unit discovery on Windows; expected POSIX-specific failures")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show commands without executing tests")
    args = parser.parse_args(argv)
    if args.all:
        args.gui = args.native = True

    windows = sys.platform == "win32"
    linux = sys.platform.startswith("linux")
    print("Nightglass OFFLINE integration verification", flush=True)
    print("Checkout: " + str(ROOT), flush=True)
    print(f"Platform: {sys.platform} | Python: {sys.version.split()[0]}", flush=True)
    print("No GitHub Actions, sudo, pip, guest starts or network actions.", flush=True)
    print("This run does NOT update GitHub check status.", flush=True)

    if windows:
        print(
            "\n[PLATFORM LIMITATION] Fedora/Linux is Nightglass's target platform.\n"
            "Windows cannot validate SELinux, libvirt, /proc runtime behavior,\n"
            "POSIX chmod 0600, Linux symlinks or Linux filesystem paths.\n"
            "Those security tests remain NOT RUN / PENDING FEDORA acceptance.\n"
            "Do NOT enable Windows Developer Mode, sudo/WSL or VM services\n"
            "to make this verification suite green.",
            flush=True,
        )
    if not linux and not windows:
        print("[LIMIT] Non-Linux host cannot certify Nightglass's Fedora security model.")

    failed = False
    if not args.dry_run:
        failed |= bool(check_syntax())
    else:
        print("[DRY RUN] Source syntax would be parsed; no files or tests touched.")

    # Windows has bash.exe as the WSL launcher even without any installed
    # distro. Never attempt invoking it: this caused the previous false FAIL.
    if linux:
        bash = shutil.which("bash")
        scripts = [
            str(ROOT / "scripts" / "setup-nightglass.sh"),
            str(ROOT / "scripts" / "fedora-recovery-smoke.sh"),
            str(ROOT / "scripts" / "fedora-host-acceptance.sh"),
        ]
        if bash and all(Path(script).is_file() for script in scripts):
            failed |= bool(run_command(
                "Bash syntax only (nothing executed)",
                [bash, "-n", *scripts], dry_run=args.dry_run,
            ))
        else:
            print("[NOT RUN] Bash script syntax (missing bash or scripts).", flush=True)
    else:
        print("[NOT RUN] Bash script validation (requires native Linux bash).", flush=True)

    if windows and not args.full:
        if not args.focused:
            for pattern in WINDOWS_PORTABLE_SUITES:
                failed |= bool(run_command(
                    f"Windows-portable synthetic tests: {pattern}",
                    unit_args(pattern), dry_run=args.dry_run,
                ))
        failed |= bool(run_command(
            "Synthetic QEMU /proc cases (Windows-compatible subset)",
            unit_args("test_kali_process_label.py", matches=WINDOWS_QEMU_CASES),
            dry_run=args.dry_run,
        ))
        print(
            "[NOT RUN] Linux/Fedora-only suites: POSIX permissions, symlinks,"
            " host SELinux, lab-network, native VM recovery and active QEMU checks.",
            flush=True,
        )
    elif args.focused:
        for pattern in LINUX_FOCUSED_SUITES:
            failed |= bool(run_command(
                f"Focused Kali regression tests: {pattern}",
                unit_args(pattern), dry_run=args.dry_run,
            ))
    else:
        if windows:
            print(
                "[CAUTION] --full explicitly forced Linux-specific test"
                " discovery on Windows; such failures do not establish Fedora defects.",
                flush=True,
            )
        failed |= bool(run_command(
            "Full Python unittest suite (no VMs)",
            unit_args("test*.py"), dry_run=args.dry_run,
        ))

    if args.gui:
        failed |= bool(run_command(
            "Opt-in PySide6 offscreen GUI smoke",
            unit_args("test_gui_smoke.py"),
            extra_env={
                "QT_QPA_PLATFORM": "offscreen",
                "NIGHTGLASS_GUI_SMOKE": "1",
            },
            dry_run=args.dry_run,
        ))
    else:
        print("[NOT RUN] PySide6 GUI smoke (use --gui with PySide6 installed).")

    if args.native:
        if not linux:
            print(
                "[NOT RUN] Native QEMU/libvirt fixtures require Fedora/Linux,"
                " even when a Windows qemu-img happens to exist."
            )
            failed = True  # Explicitly requested unavailable check is not PASS.
        else:
            missing = [x for x in ("virt-xml-validate", "qemu-img")
                       if not shutil.which(x)]
            if missing and not args.dry_run:
                print("[NOT RUN] Native QEMU/libvirt utilities missing: "
                      + ", ".join(missing))
                failed = True
            else:
                failed |= bool(run_command(
                    "Native libvirt/QEMU fixtures (NO VMs)",
                    unit_args("test_native_tools.py"), dry_run=args.dry_run,
                ))
    else:
        print("[NOT RUN] Native libvirt/QEMU fixtures (use --native on Fedora).")

    if failed:
        print("\nRESULT: TEST FAILURE or REQUESTED CHECK UNAVAILABLE.", file=sys.stderr)
        print("No merges or host/guest changes were performed.", file=sys.stderr)
        return 1
    if args.dry_run:
        print("\nRESULT: DRY RUN ONLY — NO TESTS EXECUTED.")
    elif windows and not args.full:
        print(
            "\nRESULT: WINDOWS-PORTABLE SUBSET PASSED ONLY.\n"
            "Fedora/Linux security tests, native fixtures and live VM"
            " acceptance remain UNVERIFIED."
        )
    elif linux:
        print(
            "\nRESULT: Selected local Linux checks passed.\n"
            "Real Fedora/KVM live isolation, physical VM boot and cold restore"
            " acceptance still require independent testing."
        )
    else:
        print("\nRESULT: Selected local checks passed; Fedora/Linux unverified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
