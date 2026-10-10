"""Phase24 data-loss notice: required wording, intent mapping, fail-closed state."""
from __future__ import annotations

import unittest
from pathlib import Path

from nightglass.install_disclosure import (
    ACKNOWLEDGMENT, FORMAT_TARGET, COEXIST, UNDECIDED, disclosure_for,
)
from nightglass.system_discovery import collect_system, describe


class FormatWarningTests(unittest.TestCase):
    def test_format_selected_drive_warns_of_destruction_and_user_backups(self):
        disclosure = disclosure_for(FORMAT_TARGET)
        warning = disclosure.warning.lower()
        for term in ("format", "deleted", "operating systems", "documents",
                     "before installation", "responsible", "backing",
                     "nightglass does not", "stop"):
            with self.subTest(term=term):
                self.assertIn(term, warning)
        self.assertIn("formatting can permanently delete", ACKNOWLEDGMENT.lower())

    def test_coexist_warning_addresses_efi_and_user_backups(self):
        warning = disclosure_for(COEXIST).warning.lower()
        self.assertIn("efi", warning)
        self.assertIn("boot", warning)
        self.assertIn("backup", warning)
        self.assertIn("does not create or verify", warning)

    def test_unselected_default_warns_but_never_approves(self):
        state = disclosure_for(UNDECIDED)
        self.assertIn("no target drive has been chosen", state.warning.lower())
        self.assertFalse(state.installation_authorized)
        self.assertFalse(state.target_selected)

    def test_bad_intent_fails_closed(self):
        for value in ("blank", "wipe_all_without_warning", "", "FORMAT"):
            with self.subTest(intent=value), self.assertRaises(ValueError):
                disclosure_for(value)

    def test_acks_are_not_backup_proof_or_disk_authorization(self):
        for intent in (UNDECIDED, FORMAT_TARGET, COEXIST):
            with self.subTest(intent=intent):
                state = disclosure_for(intent)
                self.assertTrue(state.requires_user_warning)
                self.assertFalse(state.installer_creates_backup)
                self.assertFalse(state.installer_verifies_backup)
                self.assertTrue(state.backups_presumed_user_responsibility)
                self.assertTrue(state.acknowledgment_is_not_backup_evidence)
                self.assertFalse(state.target_selected)
                self.assertFalse(state.target_safe_to_format)
                self.assertFalse(state.target_format_authorized)
                self.assertFalse(state.existing_os_safe)
                self.assertFalse(state.disk_write_authorized)
                self.assertFalse(state.installation_authorized)

    def test_discovery_report_carries_caution_but_never_marks_backup_complete(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            s = collect_system(system="Windows", run_live=False,
                storage_data={"disks":[{"Number":1,"Size":500*1024**3,
                                         "IsBoot":False,"IsSystem":False}],
                              "partitions":[]}, home=Path(tmp))
        self.assertEqual(s["backup_responsibility"],
                         "USER_MUST_BACK_UP_DATA_BEFORE_FORMAT")
        self.assertTrue(s["format_warning_required"])
        self.assertFalse(s["format_warning_accepted"])
        self.assertFalse(s["installer_creates_or_verifies_backups"])
        self.assertEqual(s["backup_of_empty_target_required"],
                         "NOT_EVALUATED_TARGET_MAY_CONTAIN_DATA")
        self.assertFalse(s["installation_authorized"])
        self.assertFalse(s["partition_write_authorized"])
        self.assertEqual(s["disks"][0]["target_classification"],
                         "UNVERIFIED_NOT_EMPTY_PROVEN")
        self.assertIn("back up anything", describe(s).lower())
        self.assertIn("responsible", s["format_warning"].lower())

    def test_warning_does_not_perform_device_mutations_or_backup_operations(self):
        import nightglass.install_disclosure as m
        source = Path(m.__file__).read_text(encoding="utf-8")
        for token in ("import subprocess", "os.system", "shutil.copy",
                      "wipefs", "mkfs", "Format-Volume", "Clear-Disk",
                      "os.remove", ".write_bytes", ".write_text"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_discovery_no_longer_claims_new_target_must_be_blank(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            s = collect_system(system="Linux", run_live=False,
                               storage_data={"blockdevices":[]}, home=Path(tmp))
        next_steps = "\n".join(s["next_steps"]).lower()
        self.assertIn("format", next_steps)
        self.assertIn("back up", next_steps)
        self.assertNotIn("dedicated blank drive", next_steps)
        self.assertEqual(s["setup_intent"], "UNDECIDED")


if __name__ == "__main__":
    unittest.main()
