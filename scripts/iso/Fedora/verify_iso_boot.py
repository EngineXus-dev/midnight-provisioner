#!/usr/bin/env python3
"""Read back Fedora ISO boot arguments, including the embedded USB EFI image."""
from __future__ import annotations

import argparse
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile


def verify_config(text: str, expected: list[str], source: str) -> int:
    """Require the workaround and kickstart on every GRUB kernel boot line."""
    count = 0
    for number, line in enumerate(text.splitlines(), 1):
        words = shlex.split(line, comments=True)
        if not words or words[0] not in {"linux", "linuxefi", "linux16"}:
            continue
        count += 1
        args = words[2:]
        for argument in expected:
            key = argument.split("=", 1)[0]
            values = [a for a in args if a.split("=", 1)[0] == key]
            if values != [argument]:
                raise ValueError(f"{source}:{number}: expected exactly {argument}, got {values}")
        if not any(a.startswith("inst.ks=") for a in args):
            raise ValueError(f"{source}:{number}: missing inst.ks boot argument")
    if not count:
        raise ValueError(f"{source}: no kernel boot entries found")
    return count


def run(*args: str) -> None:
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError(f"{args[0]} failed: {result.stderr.strip() or result.stdout.strip()}")


def verify_iso(iso: Path, cmdline: str) -> None:
    expected = shlex.split(cmdline)
    if not expected:
        raise ValueError("Expected boot arguments must not be empty")
    with tempfile.TemporaryDirectory(prefix="midnight-provisioner-boot-check-") as directory:
        work = Path(directory)
        configs = [
            ("/boot/grub2/grub.cfg", work / "bios.cfg"),
            ("/EFI/BOOT/grub.cfg", work / "uefi.cfg"),
        ]
        command = ["xorriso", "-osirrox", "on", "-indev", str(iso.resolve())]
        for source, destination in configs:
            command.extend(["-extract", source, str(destination)])
        command.extend(["-extract_boot_images", str(work / "boot-images")])
        run(*command)
        for source, destination in configs:
            count = verify_config(destination.read_text(encoding="utf-8"), expected, source)
            print(f"Verified {source}: {count} kernel entries")

        # Fedora can store the EFI FAT image in an appended partition rather
        # than /images/efiboot.img. xorriso finds it through the boot catalog.
        boot_images = work / "boot-images"
        images = sorted(set(boot_images.glob("*uefi*.img")) | set(boot_images.glob("gpt*_efi.img")))
        if not images:
            raise ValueError("No embedded EFI boot image extracted; USB boot is unverified")
        for index, image in enumerate(images):
            destination = work / f"embedded-efi-{index}.cfg"
            run("mcopy", "-i", str(image), "::/EFI/BOOT/grub.cfg", str(destination))
            source = f"{image.name}:/EFI/BOOT/grub.cfg"
            count = verify_config(destination.read_text(encoding="utf-8"), expected, source)
            print(f"Verified {source}: {count} kernel entries")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--cmdline", required=True)
    args = parser.parse_args()
    try:
        verify_iso(args.iso, args.cmdline)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ISO boot verification FAILED: {exc}", file=sys.stderr)
        return 1
    print("ISO boot verification PASS (ISO GRUB configs and embedded EFI image)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
