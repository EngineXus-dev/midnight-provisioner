"""Phase25: no-writes, explicit-user-selected target preview contract."""
from __future__ import annotations

import dataclasses
from pathlib import Path
import tempfile
import unittest

from midnight_provisioner.install_disclosure import FORMAT_TARGET, COEXIST, UNDECIDED
from midnight_provisioner.install_target_preview import (
    SCHEMA, build_target_preview, describe_target_preview,
)
from midnight_provisioner.system_discovery import collect_system


def observation():
    with tempfile.TemporaryDirectory() as root:
        return collect_system(
            system="Windows", run_live=False,
            storage_data={
                "memory_bytes": 8 * 1024**3,
                "disks": [
                    {"Number": 0, "IsBoot": True, "IsSystem": True, "BusType": "NVMe",
                     "IsReadOnly": False, "Size": 466 * 1024**3},
                    {"Number": 1, "IsBoot": False, "IsSystem": False, "BusType": "USB",
                     "IsReadOnly": False, "Size": 1863 * 1024**3},
                ],
                "partitions": [
                    {"DiskNumber": 0}, {"DiskNumber": 0},
                    {"DiskNumber": 0}, {"DiskNumber": 0},
                    {"DiskNumber": 1}, {"DiskNumber": 1},
                ],
            },
            home=Path(root),
        )


class TargetPreviewTests(unittest.TestCase):
    def test_initial_state_no_disk_preselected(self):
        plan = build_target_preview(observation())
        self.assertEqual(plan.schema, SCHEMA)
        self.assertEqual(plan.status, "HOLD_PREVIEW_ONLY_NO_INSTALLER_OR_DISK_WRITES")
        self.assertEqual(plan.target_observed_label, "NOT_SELECTED")
        self.assertEqual(plan.proposed_scope, "NONE")
        self.assertFalse(plan.disk_write_authorized)

    def test_format_target_reports_all_data_will_be_erased(self):
        plan = build_target_preview(
            observation(), target_index=1, intent=FORMAT_TARGET,
        )
        self.assertEqual(plan.target_observed_label, "Disk 1")
        self.assertEqual(plan.target_partitions_observed, 2)
        self.assertEqual(plan.target_size_gib_approx, 1863)
        self.assertEqual(plan.proposed_scope, "ENTIRE_SELECTED_DISK")
        self.assertIn("delete", plan.warning.lower())
        self.assertIn("yourself", plan.warning.lower())
        self.assertIn("may contain valuable data", " ".join(plan.unresolved).lower())
        self.assertFalse(plan.chosen_disk_identity_verified)
        self.assertFalse(plan.disk_write_authorized)

    def test_windows_boot_device_is_protected_even_if_explicitly_selected(self):
        plan = build_target_preview(
            observation(), target_index=0, intent=FORMAT_TARGET,
            backup_warning_acknowledged=True,
        )
        self.assertEqual(plan.target_classification, "PROTECTED_IN_USE")
        self.assertIn("must NOT", " ".join(plan.unresolved))
        self.assertFalse(plan.independent_install_authorization)
        self.assertFalse(plan.os_install_authorized)

    def test_coexist_changes_scope_but_never_edits_any_partition(self):
        plan = build_target_preview(
            observation(), target_index=1, intent=COEXIST,
            backup_warning_acknowledged=True,
        )
        self.assertEqual(plan.proposed_scope, "PARTITION_CHANGES_NOT_YET_SPECIFIED")
        self.assertIn("EFI", plan.warning)
        self.assertFalse(plan.complete_writes_list_known)
        self.assertFalse(plan.boot_and_efi_impact_verified)

    def test_acknowledgment_is_not_a_backup_or_authorization(self):
        plan = build_target_preview(
            observation(), target_index=1, intent=FORMAT_TARGET,
            backup_warning_acknowledged=True,
        )
        self.assertTrue(plan.user_backup_warning_acknowledged)
        self.assertFalse(plan.user_backups_proven_by_midnight_provisioner)
        for field in (
            "target_selected", "target_safe_to_format", "target_format_authorized",
        ):
            self.assertNotIn(field, dataclasses.asdict(plan))
        self.assertFalse(plan.independent_install_authorization)
        self.assertFalse(plan.disk_write_authorized)
        self.assertFalse(plan.os_install_authorized)

    def test_unavailable_evidence_does_not_become_empty_disk(self):
        report = observation()
        report["storage_query"] = "UNKNOWN"
        plan = build_target_preview(report, target_index=1, intent=FORMAT_TARGET)
        self.assertEqual(plan.target_observed_label, "NOT_SELECTED")
        self.assertIn("did not produce", " ".join(plan.unresolved))
        self.assertFalse(plan.disk_write_authorized)

    def test_original_report_can_never_grant_install_even_if_forged(self):
        report = observation()
        report["installation_authorized"] = True
        plan = build_target_preview(report, target_index=1, intent=FORMAT_TARGET)
        self.assertEqual(plan.target_observed_label, "NOT_SELECTED")
        self.assertFalse(plan.disk_write_authorized)

    def test_disallows_invalid_indices_or_boolean_indices(self):
        for i in (True, -1, 2, 9000, "1", None):
            with self.subTest(index=i):
                plan = build_target_preview(
                    observation(), target_index=i, intent=FORMAT_TARGET,
                )
                self.assertEqual(plan.target_observed_label, "NOT_SELECTED")
                self.assertFalse(plan.os_install_authorized)

    def test_malformed_local_disk_name_does_not_prove_identity(self):
        report = observation()
        report["disks"][1]["local_id"] = "../../dev/sda"
        plan = build_target_preview(report, target_index=1, intent=FORMAT_TARGET)
        self.assertEqual(plan.target_observed_label, "NOT_SELECTED")
        self.assertFalse(plan.chosen_disk_identity_verified)

    def test_non_boolean_acknowledgment_rejected(self):
        with self.assertRaises(ValueError):
            build_target_preview(observation(), backup_warning_acknowledged=1)

    def test_unknown_intent_rejected(self):
        for mode in ("wipe-all", "blank", "", "auto"):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                build_target_preview(observation(), intent=mode)

    def test_preview_is_immutable(self):
        plan = build_target_preview(observation())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            plan.disk_write_authorized = True

    def test_preview_text_explicitly_no_writes(self):
        text = describe_target_preview(build_target_preview(
            observation(), target_index=1, intent=FORMAT_TARGET,
        ))
        self.assertIn("NO_INSTALLER_OR_DISK_WRITES", text)
        self.assertIn("NOT INDEPENDENTLY VERIFIED", text)
        self.assertIn("No physical disk operation", text)
        self.assertNotIn("serial number", text.lower())

    def test_missing_snapshot_does_not_raise_or_pick_device(self):
        plan = build_target_preview(None, target_index=0, intent=FORMAT_TARGET)
        self.assertEqual(plan.target_observed_label, "NOT_SELECTED")
        self.assertFalse(plan.disk_write_authorized)

    def test_cli_risk_preview_uses_readonly_discovery_and_own_backup_warning(self):
        from midnight_provisioner.cli import main
        from unittest.mock import patch
        import io
        import json
        sample = observation()
        with patch("midnight_provisioner.system_discovery.collect_system",
                   return_value=sample) as scan, \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            code = main([
                "install-preview", "--intent", "format_target",
                "--disk-index", "1", "--ack-warning", "--json",
            ])
        self.assertEqual(code, 0)
        scan.assert_called_once_with(include_folder_names=False)
        doc = json.loads(out.getvalue())
        self.assertEqual(doc["target_observed_label"], "Disk 1")
        self.assertTrue(doc["user_backup_warning_acknowledged"])
        self.assertFalse(doc["disk_write_authorized"])
        self.assertFalse(doc["os_install_authorized"])
        self.assertIn("does not make or verify", doc["warning"])

    def test_source_has_no_install_format_or_writes(self):
        import midnight_provisioner.install_target_preview as m
        source = Path(m.__file__).read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.system(", "shutil.", "os.open(", "open(",
                          "os.unlink(", "os.remove(", ".write_text(", ".write_bytes(",
                          "wipefs", "mkfs", "Format-Volume", "Clear-Disk",
                          "diskpart", "shutil.rmtree"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIn("disk_write_authorized=False", source)


if __name__ == "__main__":
    unittest.main()
