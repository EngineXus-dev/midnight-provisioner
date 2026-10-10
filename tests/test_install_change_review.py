"""Phase26 source-only installation change-review regressions."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from nightglass.system_discovery import collect_system
from nightglass.install_target_preview import build_target_preview
from nightglass.install_change_review import build_change_review, review_from_discovery, describe_change_review


def snapshot():
    with TemporaryDirectory() as home:
        return collect_system(system="Windows", run_live=False, home=Path(home),
            storage_data={"disks": [
                {"Number": 0, "Size": 500*1024**3, "IsBoot": True, "IsSystem": True, "BusType": "NVMe"},
                {"Number": 1, "Size": 1800*1024**3, "IsBoot": False, "IsSystem": False, "BusType": "USB"}],
                "partitions": [{"DiskNumber": 0}, {"DiskNumber": 1}, {"DiskNumber": 1}]})


class Phase26ChangeReviewTests(unittest.TestCase):
    def test_default_never_picks_device(self):
        r = review_from_discovery(snapshot())
        self.assertEqual(r.observed_target, "NOT_SELECTED")
        self.assertFalse(r.write_manifest_complete)
        self.assertFalse(r.disk_write_authorized)

    def test_full_format_is_intended_not_an_executed_partition_change(self):
        r = review_from_discovery(snapshot(), target_index=1, intent="format_target")
        self.assertEqual(r.observed_partition_count, 2)
        self.assertEqual(r.impacts[0].state, "INTENDED_EFFECT_NOT_VERIFIED")
        self.assertFalse(r.exact_new_partition_layout_known)
        self.assertFalse(r.disk_write_authorized)

    def test_coexist_does_not_assume_preservation(self):
        r = review_from_discovery(snapshot(), target_index=1, intent="coexist")
        self.assertEqual(r.impacts[0].state, "UNKNOWN_REQUIRES_INSTALLER")
        self.assertFalse(r.windows_boot_impact_known)

    def test_protected_system_disk_stays_blocked(self):
        r = review_from_discovery(snapshot(), target_index=0, intent="format_target",
                                  backup_warning_acknowledged=True)
        self.assertEqual(r.target_classification, "PROTECTED_IN_USE")
        self.assertIn("PROTECTED HOST DISK", " ".join(r.blockers))
        self.assertFalse(r.disk_write_authorized)

    def test_all_efi_and_other_drive_impacts_marked_unknown(self):
        r = review_from_discovery(snapshot(), target_index=1, intent="format_target")
        states = {x.component: x.state for x in r.impacts}
        for key in ("EFI_SYSTEM_PARTITION", "WINDOWS_BOOT_AND_RECOVERY",
                    "OTHER_PHYSICAL_DRIVES", "INSTALLER_MEDIA_AND_BOOT"):
            self.assertEqual(states[key], "UNKNOWN_REQUIRES_INSTALLER")

    def test_zero_partitions_not_verified_blank(self):
        d = snapshot()
        d["disks"][1]["partition_count_observed"] = 0
        r = review_from_discovery(d, target_index=1, intent="format_target")
        self.assertEqual(r.observed_partition_count, 0)
        self.assertFalse(r.target_identity_independently_verified)

    def test_user_backup_acknowledgment_never_proves_backup(self):
        r = review_from_discovery(snapshot(), target_index=1, intent="format_target",
                                  backup_warning_acknowledged=True)
        self.assertTrue(r.user_backup_warning_acknowledged)
        self.assertFalse(r.backups_certified_by_nightglass)
        self.assertFalse(r.destructive_consent_obtained)

    def test_forged_authorized_preview_rejected(self):
        p = build_target_preview(snapshot(), target_index=1, intent="format_target")
        with self.assertRaises(ValueError):
            build_change_review(replace(p, disk_write_authorized=True))

    def test_unknown_snapshot_no_disk_selected(self):
        r = review_from_discovery(None, target_index=0, intent="format_target")
        self.assertEqual(r.observed_target, "NOT_SELECTED")
        self.assertFalse(r.os_install_authorized)

    def test_describe_warns_no_exact_writes_and_user_backup(self):
        text = describe_change_review(review_from_discovery(snapshot()))
        self.assertIn("EXACT PARTITION CHANGES: UNKNOWN", text)
        self.assertIn("USER RESPONSIBILITY", text)
        self.assertIn("NO PHYSICAL DISK WRITES", text)


if __name__ == "__main__":
    unittest.main()
