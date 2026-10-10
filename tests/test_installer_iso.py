"""Dual-boot installer ISO: kickstart safety, payload integrity and build-script contracts."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ISO = ROOT / "scripts" / "iso" / "Fedora"
spec = importlib.util.spec_from_file_location("nightglass_render_kickstart", ISO / "render_kickstart.py")
rk = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(rk)

COMMIT = "a" * 40


def sample_payload() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        data = b"print('nightglass')\n"
        info = tarfile.TarInfo("nightglass/cli.py")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def rendered(payload: bytes | None = None) -> str:
    return rk.render(rk.TEMPLATE.read_text(encoding="utf-8"), payload or sample_payload(), COMMIT)


def embedded_payload(kickstart: str) -> tuple[bytes, str]:
    body = kickstart.split("<<'NIGHTGLASS_PAYLOAD'\n", 1)[1].split("\nNIGHTGLASS_PAYLOAD\n", 1)[0]
    digest = re.search(r'echo "([0-9a-f]{64})  \$payload" \| sha256sum -c -', kickstart).group(1)
    return base64.b64decode(body), digest


class KickstartSafetyTests(unittest.TestCase):
    def test_template_never_configures_storage(self):
        self.assertEqual(rk.storage_commands(rk.TEMPLATE.read_text(encoding="utf-8")), [])
        self.assertEqual(rk.storage_commands(rendered()), [])

    def test_storage_commands_are_detected_and_refused(self):
        for line in ("clearpart --all --initlabel", "autopart --encrypted", "zerombr",
                     "ignoredisk --only-use=sda", "part / --size=1"):
            with self.subTest(line=line):
                hostile = rk.TEMPLATE.read_text(encoding="utf-8").replace("graphical\n", "graphical\n" + line + "\n")
                self.assertTrue(rk.storage_commands(hostile))
                with self.assertRaises(ValueError):
                    rk.render(hostile, sample_payload(), COMMIT)
        # Words inside %post are shell, not kickstart commands.
        self.assertEqual(rk.storage_commands("%post\npart of a sentence\n%end\n"), [])

    def test_payload_round_trips_with_matching_checksum(self):
        payload = sample_payload()
        decoded, digest = embedded_payload(rendered(payload))
        self.assertEqual(decoded, payload)
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
        self.assertIn(COMMIT, rendered(payload))

    def test_crlf_template_and_bad_inputs(self):
        crlf = rk.TEMPLATE.read_text(encoding="utf-8").replace("\n", "\r\n")
        self.assertNotIn("\r", rk.render(crlf, sample_payload(), COMMIT))
        with self.assertRaises(ValueError):
            rk.render(rk.TEMPLATE.read_text(encoding="utf-8"), b"", COMMIT)
        with self.assertRaises(ValueError):
            rk.render(rk.TEMPLATE.read_text(encoding="utf-8"), sample_payload(), "HEAD")
        with self.assertRaises(ValueError):
            rk.render("@SURPRISE@", sample_payload(), COMMIT)

    def test_post_installs_read_only_copy_and_no_vm_or_network_setup(self):
        text = rk.TEMPLATE.read_text(encoding="utf-8")
        for token in ("%post --erroronfail", "sha256sum -c -", "chown -R root:root /opt/nightglass",
                      "go-w", "python3-pyside6", "@^kde-desktop-environment", "selinux --enforcing"):
            self.assertIn(token, text)
        for forbidden in ("virsh", "net-define", "net-start", "pip install", "curl ", "wget ", "rootpw"):
            self.assertNotIn(forbidden, text)

    @unittest.skipUnless(importlib.util.find_spec("pykickstart"), "pykickstart not installed")
    def test_fedora_kickstart_validator_accepts_it(self):
        from pykickstart.parser import KickstartParser
        from pykickstart.version import makeVersion
        for version in ("F43", "F44"):
            with self.subTest(version=version):
                KickstartParser(makeVersion(version)).readKickstartFromString(rendered())

    @unittest.skipUnless(os.name == "posix" and shutil.which("sha256sum") and shutil.which("base64"),
                         "POSIX shell with base64 and sha256sum (Windows 'bash' may be the WSL launcher)")
    def test_post_refuses_a_tampered_payload_before_installing(self):
        text = rendered()
        post = text.split("%post --erroronfail --log=/root/nightglass-install.log\n", 1)[1]
        check_only = post.split("rm -rf /opt/nightglass", 1)[0]  # decode + checksum, no system writes
        self.assertEqual(subprocess.run(["bash", "-c", check_only], capture_output=True).returncode, 0)
        marker = "<<'NIGHTGLASS_PAYLOAD'\n"
        i = check_only.index(marker) + len(marker) + 20
        tampered = check_only[:i] + ("B" if check_only[i] != "B" else "C") + check_only[i + 1:]
        self.assertNotEqual(subprocess.run(["bash", "-c", tampered], capture_output=True).returncode, 0)

    @unittest.skipUnless((ROOT / ".git").exists() and shutil.which("git"), "needs a git checkout")
    def test_git_payload_contains_code_but_no_local_secrets(self):
        payload, commit = rk.build_payload("HEAD")
        self.assertRegex(commit, r"^[0-9a-f]{40}$")
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            names = archive.getnames()
        self.assertIn("nightglass/cli.py", names)
        self.assertFalse([n for n in names if n.startswith((".venv", ".env")) or "/.env" in n])


class BuildScriptContractTests(unittest.TestCase):
    def test_build_script_verifies_and_never_writes_devices(self):
        text = (ISO / "build-nightglass-iso.sh").read_text(encoding="utf-8")
        self.assertLess(text.index("SHA-256 MISMATCH"), text.index("mkksiso --ks"))
        self.assertLess(text.index("gpgv --keyring"), text.index("mkksiso --ks"))
        self.assertIn('--output "$work/CHECKSUM.verified"', text)  # hash read from signed text only
        for token in ("Refusing to overwrite", "Live ISOs cannot", "render_kickstart.py", "ksvalidator"):
            self.assertIn(token, text)
        for forbidden in (" dd ", "wipefs", "mkfs", "parted", "sgdisk", "fdisk", "/dev/sd", "/dev/nvme"):
            self.assertNotIn(forbidden, text)

    def test_windows_wrapper_passes_values_as_arguments(self):
        text = (ISO / "Build-Nightglass-Iso.ps1").read_text(encoding="utf-8")
        self.assertIn('--iso "/in/$1" "${verify[@]}"', text)
        self.assertIn("bash -c $inner nightglass $isoName $checksumName", text)
        self.assertIn("'-'", text)  # placeholder: Windows PowerShell 5.1 drops empty native arguments
        self.assertIn("':/src:ro'", text)
        for forbidden in ("Invoke-Expression", "Format-Volume", "Clear-Disk", "diskpart"):
            self.assertNotIn(forbidden, text)

    def test_windows_iso_trim_only_exports_one_edition(self):
        text = (ROOT / "scripts" / "iso" / "Windows11" / "Optimize-Windows11Iso.ps1").read_text(encoding="utf-8")
        for token in ("#requires -RunAsAdministrator", "-Access ReadOnly", "/Export-Image", "/CheckIntegrity",
                      "Refusing to overwrite", "Dismount-DiskImage", "etfsboot.com", "efisys.bin",
                      "exactly the chosen edition"):
            self.assertIn(token, text)
        # A trim, not a debloat: no component, package, feature or app removal; no disk writes.
        for forbidden in ("/Remove-", "/Disable-Feature", "Remove-AppxProvisionedPackage", "Remove-WindowsPackage",
                          "Disable-WindowsOptionalFeature", "Format-Volume", "Clear-Disk", "diskpart", "Invoke-Expression"):
            self.assertNotIn(forbidden, text)

    def test_line_endings_are_pinned_for_windows_checkouts(self):
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("*.ks.in text eol=lf", attributes)
        self.assertIn("*.sh text eol=lf", attributes)


if __name__ == "__main__":
    unittest.main()
