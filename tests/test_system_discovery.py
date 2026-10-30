"""Midnight Provisioner integrated system discovery: pure synthetic safety tests."""
from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest

from midnight_provisioner.install_target_preview import build_target_preview
from unittest.mock import patch

from midnight_provisioner import system_discovery as discovery


def _disk(name="nvme0n1", children=None):
    out = {"name": name, "type": "disk", "size": 500 * 1024**3,
           "rm": False, "ro": False, "tran": "nvme", "mountpoints": [None]}
    if children is not None:
        out["children"] = children
    return out


class FirstRunRecognitionTests(unittest.TestCase):
    def test_no_storage_never_means_no_disk_or_empty_disk(self):
        with tempfile.TemporaryDirectory() as temp:
            s = discovery.collect_system(system="Linux", run_live=False,
                                         storage_data=None, home=Path(temp))
        self.assertEqual(s["storage_query"], "UNKNOWN")
        self.assertEqual(s["disks"], [])
        self.assertEqual(s["status"], "HOLD_USER_REVIEW_ALL_UNKNOWN_DETAILS")
        self.assertFalse(s["installation_authorized"])
        self.assertFalse(s["blank_drive_independently_verified"])

    def test_linux_system_mount_is_protected(self):
        raw = {"blockdevices": [_disk(children=[
            {"name": "nvme0n1p1", "type": "part", "mountpoints": ["/"]}])]}
        scan = discovery.linux_storage(raw)
        self.assertEqual(scan[0]["target_classification"], "PROTECTED_IN_USE")
        self.assertEqual(scan[0]["system_use_evidence"], "MOUNTED_PARTITION_FOUND")

    def test_linux_no_partitions_cannot_be_called_blank(self):
        scan = discovery.linux_storage({"blockdevices": [_disk()]})
        self.assertEqual(scan[0]["target_classification"], "UNVERIFIED_NOT_EMPTY_PROVEN")
        self.assertIsNone(scan[0]["partition_count_observed"])

    def test_windows_boot_disk_protected_and_second_disk_unknown(self):
        raw = {"disks": [
            {"Number": 0, "IsBoot": True, "IsSystem": True,
             "Size": 256 * 1024**3, "BusType": "SATA", "IsReadOnly": False},
            {"Number": 1, "IsBoot": False, "IsSystem": False,
             "Size": 1024**4, "BusType": "USB", "IsReadOnly": False},
        ], "partitions": [
            {"DiskNumber": 0, "DriveLetter": "C"},
        ]}
        scan = discovery.windows_storage(raw)
        self.assertEqual(scan[0]["target_classification"], "PROTECTED_IN_USE")
        self.assertEqual(scan[1]["target_classification"], "UNVERIFIED_NOT_EMPTY_PROVEN")
        self.assertEqual(scan[1]["partition_count_observed"], 0)
        self.assertIsNone(scan[1]["removable"])

    def test_windows_unreadable_boot_status_is_not_selectable(self):
        for missing in ("IsBoot", "IsSystem"):
            disk = {"Number": 1, "IsBoot": False, "IsSystem": False, "Size": 1024**4}
            del disk[missing]
            with self.subTest(missing=missing):
                scan = discovery.windows_storage({"disks": [disk], "partitions": []})
                self.assertEqual(scan[0]["target_classification"], "UNKNOWN")
                preview = build_target_preview(
                    {"schema": "midnight-provisioner.system-discovery.v1", "read_only": True,
                     "status": "HOLD_USER_REVIEW_ALL_UNKNOWN_DETAILS",
                     "installation_authorized": False, "partition_write_authorized": False,
                     "install_target_confirmed": False, "storage_query": "OBSERVED",
                     "disks": scan}, target_index=0)
                self.assertEqual(preview.target_observed_label, "NOT_SELECTED")

    def test_missing_partition_query_does_not_forge_zero_partitions(self):
        # One completed Get-Partition query may legitimately return [].
        # If its JSON property is missing, that is a failed/incomplete
        # inspection: do not manufacture an empty disk inventory.
        without_partitions = {"disks": [
            {"Number": 2, "Size": 512 * 1024**3, "IsBoot": False,
             "IsSystem": False, "BusType": "SATA"}
        ]}
        self.assertEqual(discovery.windows_storage(without_partitions), [])
        self.assertEqual(discovery.windows_storage({
            **without_partitions, "partitions": []
        })[0]["partition_count_observed"], 0)
        self.assertEqual(discovery.windows_storage({
            **without_partitions, "partitions": []
        })[0]["target_classification"], "UNVERIFIED_NOT_EMPTY_PROVEN")

    def test_storage_query_rejects_invalid_types_and_oversized_array(self):
        self.assertEqual(discovery.linux_storage(None), [])
        self.assertEqual(discovery.windows_storage({"disks": "not-array", "partitions": []}), [])
        self.assertEqual(discovery.linux_storage(
            {"blockdevices": [_disk(str(i)) for i in range(35)]}), [])
        self.assertIsNone(discovery._safe_size(True))
        self.assertIsNone(discovery._safe_size(-1))
        self.assertIsNone(discovery._bool("1"))

    def test_fixed_command_no_shell_and_bounded_output(self):
        ok = type("Completed", (), {"returncode": 0, "stdout": b'{"blockdevices":[]}'})()
        with patch.object(discovery.subprocess, "run", return_value=ok) as run:
            parsed = discovery._run_fixed(discovery.LINUX_QUERY)
        self.assertEqual(parsed, {"blockdevices": []})
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(run.call_args.kwargs["timeout"], 7)
        too_large = type("Completed", (), {"returncode": 0, "stdout": b"x"*65537})()
        with patch.object(discovery.subprocess, "run", return_value=too_large):
            self.assertIsNone(discovery._run_fixed(discovery.LINUX_QUERY))

    def test_folder_names_not_read_without_consent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "Documents"
            folder.mkdir()
            (folder / "SomePrivateProject").mkdir()
            with patch.object(discovery.os, "scandir", side_effect=AssertionError("Cannot inspect names")):
                data = discovery.folder_summary(include_names=False, home=root)
        self.assertEqual(data[1]["category"], "Documents")
        self.assertTrue(data[1]["exists"])
        self.assertEqual(data[1]["names_scan"], "NOT_REQUESTED")
        self.assertNotIn("directory_names", data[1])

    def test_optin_directory_names_only_and_excludes_special_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "Documents"
            folder.mkdir()
            (folder / "ReviewedProject").mkdir()
            (folder / ".ssh").mkdir()
            (folder / "passwords.txt").write_text("do-not-read")
            result = discovery.folder_summary(include_names=True, home=root)
        entries = result[1]["directory_names"]
        self.assertIn("ReviewedProject", entries)
        self.assertNotIn(".ssh", entries)
        self.assertNotIn("passwords.txt", entries)

    def test_not_follow_symlink_personal_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            external = root / "Elsewhere"
            external.mkdir()
            try:
                (root / "Documents").symlink_to(external, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Host does not permit synthetic symlink creation")
            found = discovery.folder_summary(include_names=True, home=root)
        self.assertFalse(found[1]["exists"])
        self.assertNotIn("directory_names", found[1])

    def test_blank_drive_intent_can_never_authorize_in_install_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            result = discovery.collect_system(system="Windows",
                storage_data={"disks": [{"Number": 1, "Size": 1000*1024**3,
                                        "IsSystem": False, "IsBoot": False,
                                        "BusType": "USB"}], "partitions": []},
                run_live=False, home=Path(temp))
        self.assertEqual(result["setup_intent"], "UNDECIDED")
        self.assertFalse(result["install_target_confirmed"])
        self.assertEqual(result["storage_query"], "OBSERVED")
        for key in ("installation_authorized", "partition_write_authorized",
                    "usb_format_authorized", "firmware_change_authorized",
                    "vm_start_authorized", "other_drive_backup_scope_assessed"):
            with self.subTest(key=key):
                self.assertIs(result[key], False)

    def test_cli_command_only_reports_safe_local_observations(self):
        from midnight_provisioner.cli import main
        with tempfile.TemporaryDirectory() as temp:
            sample = discovery.collect_system(system="Linux", run_live=False,
                                              storage_data={"blockdevices": []},
                                              home=Path(temp))
        with patch("midnight_provisioner.system_discovery.collect_system", return_value=sample), \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            result = main(["discover", "--json"])
        self.assertEqual(result, 0)
        written = json.loads(output.getvalue())
        self.assertEqual(written["status"], "HOLD_USER_REVIEW_ALL_UNKNOWN_DETAILS")

    def test_no_high_risk_side_effects(self):
        source = Path(discovery.__file__).read_text(encoding="utf-8")
        for text in ("shell=True", "subprocess.Popen(", "os.system(", "os.remove(",
                     "os.unlink(", "shutil.copy", "os.replace(", ".write_bytes(",
                     "open('wb'", "os.O_WRONLY", "mkfs.", "wipefs", "diskpart",
                     "Set-Disk", "Clear-Disk", "Format-Volume", "mount -o"):
            with self.subTest(text=text):
                self.assertNotIn(text, source)
        self.assertIn('"installation_authorized": False', source)


if __name__ == "__main__":
    unittest.main()
