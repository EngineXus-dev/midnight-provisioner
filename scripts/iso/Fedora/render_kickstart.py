#!/usr/bin/env python3
"""Render the Nightglass installer kickstart with an embedded, checksummed source payload.

The payload is `git archive` of a commit: committed, tracked files only, so a
local .env, .venv or uncommitted change can never end up on the ISO.
Writes one NEW file; never touches disks or ISOs.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TEMPLATE = HERE / "nightglass.ks.in"
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
# Kickstart commands that would select, wipe or lay out disks. The template must
# leave storage to the person installing.
STORAGE_COMMANDS = frozenset({
    "autopart", "bootloader", "btrfs", "clearpart", "ignoredisk", "logvol", "mount",
    "part", "partition", "raid", "reqpart", "volgroup", "zerombr", "zfcp", "iscsi",
})


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), *args],
        check=True, capture_output=True, timeout=120,
    ).stdout


def build_payload(ref: str = "HEAD") -> tuple[bytes, str]:
    commit = _git("rev-parse", "--verify", ref + "^{commit}").decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Unexpected commit id")
    return _git("archive", "--format=tar.gz", commit), commit


def storage_commands(kickstart: str) -> list[str]:
    """Top-level (non-%section) storage commands present in a kickstart."""
    found, depth = [], 0
    for line in kickstart.splitlines():
        word = line.strip().split(" ", 1)[0]
        if word.startswith("%"):
            depth = 0 if word == "%end" else 1
            continue
        if depth == 0 and word in STORAGE_COMMANDS:
            found.append(word)
    return found


def render(template: str, payload: bytes, commit: str) -> str:
    if not payload or len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("Source payload is empty or larger than 16 MiB")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Commit must be a full SHA-1")
    # A CRLF checkout (Windows) would break the installer's %post shell script.
    text = (template.replace("\r\n", "\n").replace("@COMMIT@", commit)
            .replace("@SHA256@", hashlib.sha256(payload).hexdigest())
            .replace("@PAYLOAD@", base64.encodebytes(payload).decode("ascii").rstrip("\n")))
    leftover = re.findall(r"@[A-Z0-9_]+@", text)
    if leftover:
        raise ValueError("Unrendered placeholders: " + ", ".join(sorted(set(leftover))))
    if storage_commands(text):
        raise ValueError("Kickstart must not configure storage: " + ", ".join(storage_commands(text)))
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="NEW kickstart file to create")
    parser.add_argument("--ref", default="HEAD", help="Git commit to package (default HEAD)")
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        print("Refusing to overwrite " + str(args.output), file=sys.stderr)
        return 2
    try:
        payload, commit = build_payload(args.ref)
        text = render(TEMPLATE.read_text(encoding="utf-8"), payload, commit)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("Kickstart not created: " + str(exc), file=sys.stderr)
        return 2
    dirty = _git("status", "--porcelain", "--untracked-files=no").strip()
    if dirty and args.ref == "HEAD":
        print("NOTE: uncommitted changes are NOT included; only commit " + commit[:12] + " is.", file=sys.stderr)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(text)
    print(f"Kickstart {args.output} embeds Nightglass {commit[:12]} ({len(payload):,} bytes compressed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
