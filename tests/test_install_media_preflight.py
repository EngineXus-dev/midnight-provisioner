"""Offline synthetic, non-destructive installer-media planning regression tests."""
from __future__ import annotations

import hashlib
import importlib.util
import io
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "windows" / "Plan-Nightglass-InstallMedia.py"
spec = importlib.util.spec_from_file_location("nightglass_media_preflight", SCRIPT)
media = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(media)


class OfflineWindowsMediaPlannerTests(unittest.TestCase):
    def test_plan_only_default_does_not_touch_usb_or_file_system(self):
        with patch.object(media, "iso_info", side_effect=AssertionError("unexpected ISO access")), \
             patch.object(media, "create_report", side_effect=AssertionError("unexpected write")):
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(media.main([]), 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["activation_timing"], "activate_later")
        self.assertEqual(report["media_fit"], "NOT_CHECKED")
        self.assertFalse(report["key_recorded"])
        self.assertFalse(report["install_authorized"])
        self.assertFalse(report["usb_format_authorized"])
        self.assertIn("EXCLUDED", report["portable_backup_drive"])
        self.assertIn("I don't have a product key", report["activation_instruction"])
        self.assertIn("Windows 11 PRO edition", report["activation_instruction"])

    def test_explicit_activate_at_setup_also_supported_without_any_key(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(media.main(["--activation", "activate_during_setup"]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["activation_timing"], "activate_during_setup")
        self.assertFalse(result["key_recorded"])
        self.assertIn("genuine Microsoft", result["activation_instruction"])

    def test_uses_real_declared_usable_capacity_and_one_gib_reserve(self):
        win = {"bytes": 8_000_000_000, "sha256": "NOT_COMPUTED"}
        fedora = {"bytes": 3_100_000_000, "sha256": "NOT_COMPUTED"}
        needed = win["bytes"] + fedora["bytes"] + media.RESERVE
        low = media.make_plan(activation="activate_later", windows=win,
                              fedora=fedora, usb_bytes=needed-1)
        fit = media.make_plan(activation="activate_later", windows=win,
                              fedora=fedora, usb_bytes=needed)
        unknown = media.make_plan(activation="activate_later", windows=win, fedora=fedora)
        self.assertEqual(low["media_fit"], "INSUFFICIENT_USABLE_USB_CAPACITY")
        self.assertEqual(fit["media_fit"], "SIZE_ESTIMATE_FITS_NOT_BOOT_VERIFIED")
        self.assertEqual(unknown["media_fit"], "UNKNOWN_ACTUAL_USB_CAPACITY")
        self.assertEqual(fit["source_authenticity"],
                         "NOT_ATTESTED; manually verify official publisher")
        self.assertFalse(fit["usb_format_authorized"])
        self.assertEqual(media.parse_capacity("16000000000"), 16_000_000_000)
        for bad in ("0", "-1", "16GB", "1.5", " 16000000000", "99999999999999999"):
            with self.subTest(bad=bad):
                with self.assertRaises(media.PreflightError):
                    media.parse_capacity(bad)

    def test_check_two_iso_source_files_only_with_optional_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            w = Path(folder) / "windows.iso"
            f = Path(folder) / "fedora.iso"
            w.write_bytes(b"W" * 100)
            f.write_bytes(b"F" * 40)
            a = media.iso_info(w, 20, hash_file=False)
            b = media.iso_info(f, 20, hash_file=True)
            self.assertEqual(a["sha256"], "NOT_COMPUTED")
            self.assertEqual(b["sha256"], hashlib.sha256(b"F" * 40).hexdigest())
            self.assertEqual(a["bytes"], 100)
            with self.assertRaises(media.PreflightError):
                media.iso_info(f, 50, hash_file=True)
            with self.assertRaises(media.PreflightError):
                media.iso_info(Path(folder) / "whatever.txt", 1, hash_file=True)

    def test_report_created_only_explicitly_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "report.json"
            data = media.make_plan(activation="activate_later")
            media.create_report(target, data)
            self.assertEqual(json.loads(target.read_text()), data)
            with self.assertRaises(FileExistsError):
                media.create_report(target, {"x": 1})
            self.assertEqual(json.loads(target.read_text()), data)

    def test_invalid_use_never_gets_pass(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                media.main(["--check-files"])
            with self.assertRaises(SystemExit):
                media.main(["--windows-iso", "Windows.iso"])
            with self.assertRaises(SystemExit):
                media.main(["--report", "report.json"])
            self.assertEqual(media.main(["--check-files",
                                         "--windows-iso", "none.iso",
                                         "--fedora-iso", "missing.iso"]), 2)
        self.assertFalse(media.make_plan(activation="activate_later")["install_authorized"])

    def test_script_has_no_host_disk_writer_or_product_key_handling(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "subprocess.run(", "os.system(", "shutil.rmtree(",
            "diskpart", "format-volume", "bcdedit", "slmgr", "manage-bde",
            "Clear-Disk", "Initialize-Disk", "Ventoy2Disk", "rufus.exe",
            "win11setup.exe", "Get-BitLockerVolume", "winutil",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIn("stat.S_ISREG", source)
        self.assertIn("O_EXCL", source)


if __name__ == "__main__":
    unittest.main()
