#!/usr/bin/env python3
"""Nightglass official-ISO and activation-timing planning gate.

DEFAULT: plan only. No downloads, USB/disk enumeration, formatting, flashing,
partitioning, installer invocation, registry, key handling, or destructive APIs.
The optional --check-files action reads two explicitly supplied regular ISOs,
and estimates fit only against a user-provided *usable* USB byte capacity.
A fit estimate is never media authenticity or boot/security validation.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

RESERVE = 1024 * 1024 * 1024   # 1 GiB for bootloader/file-system room
MIN_WIN = 1024 * 1024 * 1024   # Don't accept a tiny disguised ISO fixture
MIN_FEDORA = 512 * 1024 * 1024
MODES = ("activate_later", "activate_during_setup")
SCHEMA = "nightglass.windows11.pro.media-preflight.v1"
HEX256 = re.compile(r"[0-9a-fA-F]{64}\Z")


class PreflightError(ValueError):
    """A failure never authorizes formatting or installation."""


def mode_text(choice: str) -> str:
    if choice not in MODES:
        raise PreflightError("Unsupported activation timing")
    if choice == "activate_later":
        return ("At genuine Microsoft setup, select 'I don't have a product key' "
                "if offered; confirm Windows 11 PRO edition. After setup use "
                "Settings > System > Activation > Change product key.")
    return ("Enter a valid Windows 11 Pro key privately in genuine Microsoft "
            "Setup when ready. Nightglass never asks for or stores keys.")


def iso_info(path: Path, minimum: int, *, hash_file: bool) -> dict:
    if path.suffix.lower() != ".iso":
        raise PreflightError("Source file must have .iso extension")
    # No path text in errors/reports; USB/drive names can reveal identity.
    if path.is_symlink():
        raise PreflightError("Symlinked ISO is unsupported")
    try:
        before = path.lstat()
    except OSError as exc:
        raise PreflightError("ISO source unreadable") from exc
    if not stat.S_ISREG(before.st_mode):
        raise PreflightError("ISO source is not a regular file")
    if before.st_size < minimum:
        raise PreflightError("ISO source is implausibly small")
    payload = {"bytes": int(before.st_size), "sha256": "NOT_COMPUTED"}
    if hash_file:
        digest = hashlib.sha256()
        # O_NOFOLLOW is used on platforms supporting it; recheck file id
        # to narrow symlink swaps and mid-hash file replacement.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise PreflightError("Opened ISO is not regular")
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                    before.st_dev, before.st_ino, before.st_size):
                raise PreflightError("ISO was changed before hashing")
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            after_open = os.fstat(stream.fileno())
        after = path.lstat()
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise PreflightError("ISO was modified during inspection")
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
                after_open.st_dev, after_open.st_ino, after_open.st_size):
            raise PreflightError("ISO was changed while hashing")
        payload["sha256"] = digest.hexdigest()
    return payload


def parse_capacity(value: str) -> int:
    # Exact observed usable bytes, not marketing label "16GB".
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise PreflightError("Usable USB bytes must be a positive integer")
    capacity = int(value)
    if capacity > 10**14:
        raise PreflightError("USB capacity value implausibly large")
    return capacity


def make_plan(*, activation: str, windows: dict | None = None,
              fedora: dict | None = None, usb_bytes: int | None = None) -> dict:
    result = {
        "schema": SCHEMA,
        "edition": "Windows 11 Pro (user reports owning a Pro key)",
        "activation_timing": activation,
        "activation_instruction": mode_text(activation),
        "key_recorded": False,
        "install_authorized": False,
        "usb_format_authorized": False,
        "windows_installed": False,
        "fedora_installed": False,
        "portable_backup_drive": "EXCLUDED_FROM_INSTALL_AND_USB_FORMAT",
        "source_authenticity": "NOT_ATTESTED; manually verify official publisher",
        "secure_boot_test": "NOT_PERFORMED",
        "data_backup_verified": False,
        "media_fit": "NOT_CHECKED",
        "minimum_free_headroom_bytes": RESERVE,
    }
    if (windows is None) != (fedora is None):
        raise PreflightError("Both ISO sources must be inspected together")
    if windows is not None:
        result["iso_files"] = {"windows11_pro": windows, "fedora_kde": fedora}
        result["combined_iso_bytes"] = windows["bytes"] + fedora["bytes"]
        if usb_bytes is None:
            result["media_fit"] = "UNKNOWN_ACTUAL_USB_CAPACITY"
        else:
            result["declared_usable_usb_bytes"] = usb_bytes
            needed = result["combined_iso_bytes"] + RESERVE
            result["media_fit"] = (
                "SIZE_ESTIMATE_FITS_NOT_BOOT_VERIFIED"
                if needed <= usb_bytes else "INSUFFICIENT_USABLE_USB_CAPACITY"
            )
    return result


def create_report(path: Path, data: dict) -> None:
    """Exclusive create. No existing file or symlink is overwritten."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True, indent=2)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nightglass non-destructive Windows/Fedora media planning")
    parser.add_argument("--activation", choices=MODES, default="activate_later",
                        help="Future Pro key entry: default activate later")
    parser.add_argument("--check-files", action="store_true",
                        help="Read two explicitly supplied local ISO files")
    parser.add_argument("--windows-iso", type=Path)
    parser.add_argument("--fedora-iso", type=Path)
    parser.add_argument("--usable-usb-bytes", type=str,
                        help="ACTUAL usable bytes measured from the separate 16GB stick, not marketing label")
    parser.add_argument("--sha256", action="store_true",
                        help="Optionally calculate SHA256 of each ISO, no publisher authentication")
    parser.add_argument("--report", type=Path, help="Optional NEW status JSON path, never overwrite")
    args = parser.parse_args(argv)
    if not args.check_files and any((
            args.windows_iso, args.fedora_iso, args.usable_usb_bytes, args.sha256)):
        parser.error("ISO inspection options require --check-files")
    if args.check_files and (args.windows_iso is None or args.fedora_iso is None):
        parser.error("--check-files requires BOTH --windows-iso and --fedora-iso")
    if not args.check_files and args.report:
        parser.error("--report is for explicit --check-files only; default preview never writes")
    try:
        usb_bytes = (parse_capacity(args.usable_usb_bytes)
                     if args.usable_usb_bytes is not None else None)
        windows = fedora = None
        if args.check_files:
            w = args.windows_iso
            f = args.fedora_iso
            if w == f or (w.exists() and f.exists() and w.samefile(f)):
                raise PreflightError("Two different ISO files are required")
            windows = iso_info(w, MIN_WIN, hash_file=args.sha256)
            fedora = iso_info(f, MIN_FEDORA, hash_file=args.sha256)
        plan = make_plan(activation=args.activation, windows=windows, fedora=fedora,
                         usb_bytes=usb_bytes)
        print(json.dumps(plan, sort_keys=True, indent=2))
        if args.report:
            create_report(args.report, plan)
        if plan["media_fit"] == "INSUFFICIENT_USABLE_USB_CAPACITY":
            print("HOLD: ISO files do not fit declared usable space plus reserve.", file=sys.stderr)
            return 1
        return 0
    except (PreflightError, OSError) as exc:
        print("HOLD: " + type(exc).__name__ + "; no installation or USB actions.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
