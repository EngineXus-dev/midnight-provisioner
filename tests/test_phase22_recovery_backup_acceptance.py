"""Phase22 strictly offline synthetic evidence contract. No hardware/disk scans."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Review-Nightglass-Recovery-Backup.py"
spec = importlib.util.spec_from_file_location("nightglass_phase22_review", SCRIPT)
tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(tool)


def winre(reason="UTILITY_INVOCATION_ERROR"):
    row = {
        "schema": tool.WINRE_SCHEMA,
        "mode": "NATIVE_WINDOWS_READ_ONLY_NO_ELEVATION",
        "status": "HOLD_INDEPENDENT_RECOVERY_EVIDENCE",
        "raw_reagentc_output_in_report": False,
        "process_token_class": "STANDARD_TOKEN",
        "diagnostic_reason": reason,
        "winre_state": "UNKNOWN",
        "winre_result": "",
    }
    if reason == "STATUS_ENGLISH_ENABLED":
        row["winre_state"], row["winre_result"] = "REVIEW", "REPORTED_ENABLED"
    if reason == "STATUS_ENGLISH_DISABLED":
        row["winre_state"], row["winre_result"] = "HOLD", "REPORTED_DISABLED"
    row.update({name: False for name in tool.FLAGS})
    return row


def backup(matched=True, extras=0):
    return {
        "schema": tool.BACKUP_SCHEMA,
        "mode": "Verify",
        "status": ("CONTENT_MATCH_EXTRAS_REVIEW" if extras and matched else
                   "CONTENT_MATCH" if matched else "INCOMPLETE"),
        "source_identity_scope": "ALL_SELECTED_SOURCE_ROOTS",
        "entry_count": 1,
        "entries": [{"id": "projects", "verification_succeeded": matched}],
        "all_selected_content_matched": matched,
        "additional_backup_files_to_review": extras,
        **{name: False for name in tool.BACKUP_FALSE},
    }


class RecoveryBackupAcceptanceTests(unittest.TestCase):
    def test_preview_does_not_read_any_files(self):
        with redirect_stdout(io.StringIO()) as out:
            code = tool.main([])
        self.assertEqual(code, 0)
        self.assertIn("no files or hardware accessed", out.getvalue())

    def test_unambiguous_winre_enabled_is_not_recovery_proof(self):
        for reason in ("UTILITY_INVOCATION_ERROR",
                       "STATUS_ENGLISH_ENABLED", "STATUS_ENGLISH_DISABLED"):
            with self.subTest(reason=reason):
                assessment = tool.assess(winre(reason))
                self.assertEqual(assessment["status"], "HOLD_RECOVERY_BACKUP_AND_PHYSICAL_ACCEPTANCE")
                self.assertFalse(assessment["windows_recovery_boot_proven"])
                self.assertFalse(assessment["fedora_install_authorized"])
                self.assertFalse(assessment["backup_set"]["selected_folder_copies_match"])

    def test_corrupt_winre_assertions_or_status_rejected(self):
        for field, value in (
            ("windows_install_authorized", True),
            ("restoration_proven", True),
            ("raw_reagentc_output_in_report", True),
            ("status", "INSTALL_ALLOWED"),
            ("schema", "made.up.v1"),
            ("process_token_class", "root"),
            ("diagnostic_reason", "REBOOT_APPROVED"),
        ):
            doc = winre()
            doc[field] = value
            with self.subTest(field=field), self.assertRaises(tool.EvidenceError):
                tool.validate_winre(doc)
        doc = winre()
        del doc["backup_independence_proven"]
        with self.assertRaises(tool.EvidenceError):
            tool.validate_winre(doc)

    def test_winre_reason_state_mismatch_rejected(self):
        doc = winre("STATUS_ENGLISH_ENABLED")
        doc["winre_state"] = "UNKNOWN"
        with self.assertRaises(tool.EvidenceError):
            tool.validate_winre(doc)

    def test_selected_folder_hash_pass_does_not_prove_restore(self):
        result = tool.assess(winre(), backup())
        self.assertTrue(result["backup_set"]["selected_folder_copies_match"])
        self.assertEqual(result["backup_set"]["selected_group_count"], 1)
        for field in ("full_machine_backup_proven", "controlled_restore_proven",
                      "bitlocker_key_custody_proven", "clean_ntfs_shutdown_proven",
                      "fedora_install_authorized", "disk_write_authorized",
                      "vm_start_authorized"):
            with self.subTest(field=field):
                self.assertFalse(result[field])

    def test_incomplete_backup_remains_incomplete(self):
        result = tool.assess(winre(), backup(matched=False))
        self.assertFalse(result["backup_set"]["selected_folder_copies_match"])
        self.assertFalse(result["controlled_restore_proven"])

    def test_extras_are_counted_and_reviewed_without_delete(self):
        result = tool.assess(winre(), backup(extras=2))
        self.assertEqual(result["backup_set"]["extra_backup_files_to_review"], 2)
        self.assertFalse(result["full_machine_backup_proven"])

    def test_forged_full_machine_backup_or_other_claim_rejected(self):
        for field in tool.BACKUP_FALSE:
            with self.subTest(field=field):
                doc = backup()
                doc[field] = True
                with self.assertRaises(tool.EvidenceError):
                    tool.validate_backup(doc)
                del doc[field]
                with self.assertRaises(tool.EvidenceError):
                    tool.validate_backup(doc)

    def test_backup_status_or_group_results_mismatch_rejected(self):
        for field, value in (
            ("status", "INVENTORY_ONLY_NOT_CONTENT_VERIFIED"),
            ("mode", "Inspect"),
            ("all_selected_content_matched", False),
            ("additional_backup_files_to_review", -1),
        ):
            doc = backup()
            doc[field] = value
            with self.subTest(field=field), self.assertRaises(tool.EvidenceError):
                tool.validate_backup(doc)
        doc = backup()
        doc["entries"][0]["source"] = "C:\\private\\source"
        with self.assertRaises(tool.EvidenceError):
            tool.validate_backup(doc)

    def test_unauthorized_json_duplicate_nonfinite_and_oversize_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "test.json"
            for payload in (b'{"schema":1,"schema":2}', b'{"a":NaN}',
                            b"x" * (tool.MAX_JSON + 1)):
                src.write_bytes(payload)
                with self.subTest(payload=payload[:20]), self.assertRaises(tool.EvidenceError):
                    tool.read_json(src)

    def test_symlink_rejected_or_explicitly_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source = directory / "real.json"
            source.write_text(json.dumps(winre()), encoding="utf-8")
            alias = directory / "alias.json"
            try:
                alias.symlink_to(source)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink fixture requires host permission")
            with self.assertRaises(tool.EvidenceError):
                tool.read_json(alias)

    def test_valid_file_roundtrip_has_no_file_paths_or_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "winre.json"
            dst = Path(tmp) / "backup.json"
            src.write_text(json.dumps(winre()), encoding="utf-8")
            dst.write_text(json.dumps(backup()), encoding="utf-8")
            before = src.read_bytes(), dst.read_bytes()
            with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
                code = tool.main(["--mode", "Assess", "--winre-report", str(src),
                                  "--backup-report", str(dst)])
            self.assertEqual(code, 0)
            data = json.loads(out.getvalue())
            self.assertEqual(data["status"], "HOLD_RECOVERY_BACKUP_AND_PHYSICAL_ACCEPTANCE")
            self.assertTrue(data["backup_evidence_supplied"])
            self.assertNotIn(str(src), out.getvalue())
            self.assertNotIn(str(dst), out.getvalue())
            self.assertEqual(before, (src.read_bytes(), dst.read_bytes()))

    def test_source_has_no_mutating_disk_recovery_or_network_operations(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("subprocess.", "requests.", "urllib.request",
                          "socket.", "os.system(", "shutil.", "os.remove(",
                          "os.unlink(", "os.replace(", "os.rename(",
                          ".write_text(", ".write_bytes(", "os.O_WRONLY",
                          "os.O_RDWR", "DeleteFile", "CreateFileW"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIn("os.O_RDONLY", source)
        self.assertIn("HOLD_RECOVERY_BACKUP_AND_PHYSICAL_ACCEPTANCE", source)


if __name__ == "__main__":
    unittest.main()
