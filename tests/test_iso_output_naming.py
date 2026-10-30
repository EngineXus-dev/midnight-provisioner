"""Output collisions must preserve artifacts and stop before build work."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/iso/Fedora/Build-Midnight-Provisioner-Iso.ps1"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "PowerShell is required for the Windows wrapper")
class WindowsOutputNamingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="iso naming ")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.iso = self.directory / "Fedora-Everything-netinst-x86_64-44-1.7.iso"
        self.iso.write_bytes(b"input fixture")
        self.output = self.directory / "output"
        self.output.mkdir()
        self.default = self.output / ("Midnight-Provisioner-Installer-" + self.iso.name)
        self.capture = self.directory / "docker-arguments.json"

    def invoke(self, name=None):
        def quote(value):
            return "'" + str(value).replace("'", "''") + "'"
        command = (
            "$ErrorActionPreference='Stop'; "
            "function global:docker { "
            "ConvertTo-Json -InputObject @($args) -Compress | "
            "Set-Content -LiteralPath " + quote(self.capture) + "; "
            "$global:LASTEXITCODE=0 }; "
            "& " + quote(BUILDER) + " -IsoPath " + quote(self.iso) +
            " -Sha256 " + quote("a" * 64) + " -OutputDir " + quote(self.output)
        )
        if name is not None:
            command += " -OutputName " + quote(name)
        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        return subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")

    def test_default_rerun_preserves_iso_and_checksum(self):
        self.default.write_bytes(b"previous ISO")
        sidecar = Path(str(self.default) + ".sha256")
        sidecar.write_bytes(b"previous checksum")
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.capture.read_text(encoding="utf-8-sig"))
        self.assertRegex(args[-1], r"-rebuild-\d{8}-\d{6}(?:-\d+)?\.iso$")
        self.assertNotEqual(args[-1], self.default.name)
        self.assertIn('--name "$4"', args[args.index("-c") + 1])
        self.assertEqual(self.default.read_bytes(), b"previous ISO")
        self.assertEqual(sidecar.read_bytes(), b"previous checksum")

    def test_unused_default_keeps_standard_name(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.capture.read_text(encoding="utf-8-sig"))[-1], self.default.name)

    def test_explicit_iso_or_orphaned_checksum_collision_never_starts_docker(self):
        for suffix in ("", ".sha256"):
            with self.subTest(suffix=suffix):
                artifact = self.output / ("Chosen.iso" + suffix)
                artifact.write_bytes(b"keep")
                result = self.invoke("Chosen.iso")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Refusing to overwrite", result.stderr)
                self.assertFalse(self.capture.exists())
                self.assertEqual(artifact.read_bytes(), b"keep")
                artifact.unlink()

    def test_directory_in_explicit_name_is_rejected(self):
        result = self.invoke("../Chosen.iso")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.capture.exists())


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "POSIX bash required")
class LinuxOutputNamingTests(unittest.TestCase):
    def test_explicit_checksum_collision_precedes_dependency_or_hash_work(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            iso = path / "Fedora-netinst.iso"
            iso.write_bytes(b"input fixture")
            sidecar = path / "Chosen.iso.sha256"
            sidecar.write_bytes(b"keep")
            result = subprocess.run(["bash", str(ROOT / "scripts/iso/Fedora/build-midnight-provisioner-iso.sh"),
                                     "--iso", str(iso), "--sha256", "a" * 64,
                                     "--output", str(path), "--name", "Chosen.iso"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Refusing to overwrite", result.stderr)
            self.assertNotIn("Verifying", result.stdout)
            self.assertEqual(sidecar.read_bytes(), b"keep")
