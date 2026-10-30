#!/usr/bin/env python3
"""Optional Kali Xfce theme helper. Preview by default; guest-local apply/undo.

Uses installed Kali themes and xfconf only. No root, downloads, host access,
desktop replacement, wallpaper replacement, security changes or VM integration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

THEMES = ("Kali-Dark", "Kali-Light")
PROPERTIES = (("xsettings", "/Net/ThemeName"), ("xfwm4", "/general/theme"))
FORMAT = "midnight-provisioner.kali-desktop-theme.v1"
THEME_ROOT = Path("/usr/share/themes")
OS_RELEASE = Path("/etc/os-release")
VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_. +()-]{0,127}")


class ThemeError(ValueError):
    pass


def ensure_guest():
    if sys.platform != "linux" or os.geteuid() == 0:
        raise ThemeError("Run inside Kali as the regular desktop user, not root.")
    fields = {}
    for line in OS_RELEASE.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            fields[key] = value.strip('"')
    if fields.get("ID") != "kali":
        raise ThemeError("This helper applies only inside Kali Linux; the Fedora host is not changed.")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower().split(":")
    if "xfce" not in desktop or not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        raise ThemeError("Sign in to the Kali Xfce desktop session first. Other desktops are unchanged.")
    executable = shutil.which("xfconf-query")
    if not executable:
        raise ThemeError("xfconf-query is unavailable; no settings were changed.")
    return executable


def query(executable, channel, prop, value=None):
    args = [executable, "--channel", channel, "--property", prop]
    if value is not None:
        if not isinstance(value, str) or not VALUE.fullmatch(value):
            raise ThemeError("Unsupported theme setting in snapshot.")
        args.extend(["--set", value])
    result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
    if result.returncode:
        raise ThemeError("Xfce could not read or update " + channel + ":" + prop)
    return result.stdout.strip()


def installed(theme):
    folder = THEME_ROOT / theme
    return (folder / "gtk-3.0/gtk.css").is_file() and (folder / "xfwm4/themerc").is_file()


def checked_path(path):
    path = path.expanduser().absolute()
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ThemeError("Use a local snapshot path without symlinks.")
    return path


def save_snapshot(record, destination=None):
    if destination is None:
        folder = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "midnight-provisioner" / "GuestThemeSnapshots"
        checked_path(folder)
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination = folder / (datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8] + ".json")
    destination = checked_path(Path(destination))
    if not destination.parent.is_dir():
        raise ThemeError("The snapshot parent directory must already exist.")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return destination


def apply_theme(theme, destination=None):
    executable = ensure_guest()
    if theme not in THEMES or not installed(theme):
        raise ThemeError("The selected Kali GTK and window-manager theme must already be installed.")
    before = [query(executable, channel, prop) for channel, prop in PROPERTIES]
    if not all(VALUE.fullmatch(value) for value in before):
        raise ThemeError("Existing theme names cannot be safely recorded; no settings were changed.")
    record = {"format": FORMAT, "before": before, "applied": theme}
    snapshot = save_snapshot(record, destination)
    changed = []
    try:
        for index, (channel, prop) in enumerate(PROPERTIES):
            query(executable, channel, prop, theme)
            changed.append(index)
    except (ThemeError, OSError, subprocess.SubprocessError) as exc:
        rollback_failed = False
        for index in reversed(changed):
            try:
                query(executable, *PROPERTIES[index], before[index])
            except (ThemeError, OSError, subprocess.SubprocessError):
                rollback_failed = True
        detail = " Automatic rollback needs manual review." if rollback_failed else " Completed changes were rolled back."
        raise ThemeError("Theme change failed." + detail + " Snapshot: " + str(snapshot)) from exc
    return snapshot


def undo_theme(path):
    executable = ensure_guest()
    path = checked_path(Path(path))
    if not path.is_file() or path.stat().st_size > 4096:
        raise ThemeError("Use a small, regular snapshot JSON file from this helper.")
    record = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(record, dict) or set(record) != {"format", "before", "applied"}
            or record["format"] != FORMAT or record["applied"] not in THEMES
            or not isinstance(record["before"], list) or len(record["before"]) != len(PROPERTIES)
            or not all(isinstance(v, str) and VALUE.fullmatch(v) for v in record["before"])):
        raise ThemeError("Invalid theme snapshot; no settings were changed.")
    current = [query(executable, channel, prop) for channel, prop in PROPERTIES]
    if current != [record["applied"]] * len(PROPERTIES):
        raise ThemeError("Theme settings have changed since Apply; undo will not overwrite those edits.")
    changed = []
    try:
        for index, (channel, prop) in enumerate(PROPERTIES):
            query(executable, channel, prop, record["before"][index])
            changed.append(index)
    except (ThemeError, OSError, subprocess.SubprocessError) as exc:
        for index in reversed(changed):
            try:
                query(executable, *PROPERTIES[index], record["applied"])
            except (ThemeError, OSError, subprocess.SubprocessError):
                raise ThemeError("Undo could not finish or roll back; review the retained snapshot manually.") from exc
        raise ThemeError("Undo failed; completed changes were rolled back. Snapshot retained.") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", choices=THEMES, default="Kali-Dark")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Apply inside this Kali Xfce session, after saving prior settings")
    mode.add_argument("--undo", type=Path, help="Restore a snapshot only if the theme has not changed since Apply")
    parser.add_argument("--snapshot", type=Path, help="Optional NEW snapshot file for Apply")
    args = parser.parse_args(argv)
    if args.snapshot is not None and not args.apply:
        parser.error("--snapshot requires --apply")
    try:
        if args.undo:
            undo_theme(args.undo)
            print("Restored the previous GTK and window-manager theme. Snapshot retained.")
        elif args.apply:
            snapshot = apply_theme(args.theme, args.snapshot)
            print("Applied " + args.theme + " inside this Kali Xfce session.")
            print("Snapshot: " + str(snapshot))
            print('Undo: python3 kali-desktop-theme.py --undo "' + str(snapshot) + '"')
        else:
            print("PREVIEW ONLY — no settings changed.")
            print("Guest desktop: Kali Linux / Xfce / regular user")
            print("GTK theme and window decorations: " + args.theme)
            print("Apply requires the selected theme to be installed and records prior settings for undo.")
            print("Use --apply to apply inside the guest. Icons and wallpaper are left as you chose them.")
        return 0
    except (ThemeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print("Theme action stopped: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
