#!/usr/bin/env python3
"""Install application-menu and desktop launchers for the current Linux user."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def data_home():
    value = os.environ.get("XDG_DATA_HOME", "")
    return Path(value) if value.startswith("/") else Path.home() / ".local/share"


def desktop_dir():
    try:
        result = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=10, check=True)
        path = Path(result.stdout.strip())
        if path.is_absolute():
            return None if path == Path.home() else path
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home() / "Desktop"


def exec_arg(value):
    if any(c in value for c in "\n\r\0="):
        raise ValueError("Unsupported character in launcher command")
    value = value.replace("%", "%%")
    for char in ("\\", '"', chr(96), "$"):
        value = value.replace(char, "\\" + char)
    return '"' + value.replace("\\", "\\\\") + '"'


def write_launcher(path, content, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Refusing a symlinked launcher: " + str(path))
    fd, name = tempfile.mkstemp(prefix=".midnight-launcher-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def install(command, applications=None, desktop=None):
    text = (
        "[Desktop Entry]\nType=Application\nName=Midnight Provisioner\n"
        "Comment=Manage local workspaces and virtual machines\n"
        "Exec=" + exec_arg(str(command)) + " gui\n"
        "Icon=security-high\nTerminal=false\nCategories=System;Utility;\n"
    )
    for directory, mode in ((applications, 0o644), (desktop, 0o755)):
        if directory is not None:
            write_launcher(directory / "midnight-provisioner.desktop", text, mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", required=True, type=Path)
    parser.add_argument("--applications-dir", type=Path)
    parser.add_argument("--desktop-only", action="store_true")
    parser.add_argument("--no-desktop", action="store_true")
    parser.add_argument("--first-login", action="store_true")
    args = parser.parse_args()
    if not args.command.is_absolute() or not args.command.is_file() or not os.access(args.command, os.X_OK):
        parser.error("--command must name an installed executable by absolute path")
    stamp = data_home() / "midnight-provisioner/desktop-shortcut-installed"
    if args.first_login and stamp.exists():
        return
    applications = None if args.desktop_only else (args.applications_dir or data_home() / "applications")
    desktop = None if args.no_desktop else desktop_dir()
    install(args.command, applications, desktop)
    if args.first_login:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.touch()
    print("Midnight Provisioner launchers installed.")


if __name__ == "__main__":
    main()
