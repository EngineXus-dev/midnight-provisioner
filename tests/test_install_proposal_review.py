"""Phase27 strict untrusted proposal reader and fail-closed no-write review."""
from __future__ import annotations

from dataclasses import asdict
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from nightglass.install_proposal_review import (
    SCHEMA, STATUS, ProposalError, parse_proposal, read_proposal_file,
    review_proposal, describe_proposal,
)


def proposal():
    return {
        "schema": SCHEMA,
        "source": "unverified_user_supplied",
        "intent": "format_target",
        "target_ref": "target_a",
        "devices": [
            {"ref": "target_a", "role": "target", "partition_count": 2},
            {"ref": "other_b", "role": "other", "partition_count": None},
        ],
        "operations": [
            {"action": "delete_partition", "device_ref": "target_a",
             "partition_ref": "old_part"},
            {"action": "create_partition", "device_ref": "target_a",
             "partition_ref": None},
            {"action": "write_bootloader", "device_ref": "other_b",
             "partition_ref": None},
        ],
    }


class ProposalReviewTests(unittest.TestCase):
    def test_valid_untrusted_plan_still_holds(self):
        report = review_proposal(proposal())
        self.assertEqual(report.status, STATUS)
        self.assertEqual(report.declared_device_count, 2)
        self.assertEqual(report.declared_operation_count, 3)
        self.assertFalse(report.physical_device_identity_verified)
        self.assertFalse(report.disk_write_authorized)
        self.assertFalse(report.os_install_authorized)

    def test_detects_other_disk_boot_changes_without_approving(self):
        report = review_proposal(proposal())
        self.assertTrue(report.other_drive_changes_claimed)
        self.assertTrue(report.boot_or_firmware_changes_claimed)
        self.assertTrue(report.impacts[-1].outside_declared_target)
        self.assertIn("OTHER DRIVE", " ".join(report.blockers))
        self.assertFalse(report.os_install_authorized)

    def test_claimed_no_other_disk_changes_is_not_proof(self):
        d = proposal()
        d["operations"] = d["operations"][:2]
        r = review_proposal(d)
        self.assertFalse(r.other_drive_changes_claimed)
        self.assertIn("does NOT prove", " ".join(r.blockers))
        self.assertFalse(r.all_connected_disks_accounted_for)

    def test_user_backups_not_certified_even_when_plan_parses(self):
        d = proposal()
        r = review_proposal(d)
        self.assertFalse(r.user_backups_verified_by_nightglass)
        self.assertFalse(r.independent_destructive_consent)
        self.assertFalse(r.official_installer_origin_verified)

    def test_unknown_actions_and_device_refs_fail_closed(self):
        for operation in (
            {"action":"automatic_erase_all","device_ref":"target_a","partition_ref":None},
            {"action":"format_partition","device_ref":"unknown","partition_ref":"part"},
            {"action":"delete_partition","device_ref":"target_a","partition_ref":None},
            {"action":"write_bootloader","device_ref":"target_a","partition_ref":"somepart"},
        ):
            with self.subTest(operation=operation), self.assertRaises(ProposalError):
                d = proposal()
                d["operations"] = [operation]
                review_proposal(d)

    def test_unhashable_operation_input_is_cleanly_rejected(self):
        for bad in ([], {}, ["delete_partition"], {"op": "delete_partition"}):
            with self.subTest(bad=repr(bad)), self.assertRaises(ProposalError):
                d = proposal()
                d["operations"][0]["action"] = bad
                review_proposal(d)

    def test_duplicate_operations_and_duplicate_device_names_rejected(self):
        d = proposal()
        d["operations"].append(d["operations"][0].copy())
        with self.assertRaises(ProposalError):
            review_proposal(d)
        d = proposal()
        d["devices"].append(d["devices"][0].copy())
        with self.assertRaises(ProposalError):
            review_proposal(d)

    def test_duplicate_json_properties_rejected(self):
        src = json.dumps(proposal())
        src = src.replace('"schema": ', '"schema": "x", "schema": ', 1)
        with self.assertRaises(ProposalError):
            parse_proposal(src)

    def test_malformed_oversized_and_nan_rejected(self):
        for data in ('{', '{"oops":NaN}', "x" * 70000, "[]"):
            with self.subTest(length=len(data)), self.assertRaises(ProposalError):
                parse_proposal(data)

    def test_missing_target_or_bad_role_rejected(self):
        for edit in ("missing", "wrong_role", "duplicate_target"):
            d = proposal()
            if edit == "missing":
                d["target_ref"] = "not_declared"
            if edit == "wrong_role":
                d["devices"][0]["role"] = "other"
            if edit == "duplicate_target":
                d["devices"][1]["role"] = "target"
            with self.subTest(edit=edit), self.assertRaises(ProposalError):
                review_proposal(d)

    def test_rejects_unexpected_keys_and_actual_disk_paths(self):
        d = proposal()
        d["devices"][0]["path"] = "opaque-data-not-a-path"
        with self.assertRaises(ProposalError):
            review_proposal(d)
        d = proposal()
        d["devices"][0]["ref"] = "/dev/sdx"
        with self.assertRaises(ProposalError):
            review_proposal(d)

    def test_file_reader_only_reads_explicit_local_json(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposal.json"
            path.write_text(json.dumps(proposal()), encoding="utf8")
            d = read_proposal_file(path)
            self.assertEqual(d["target_ref"], "target_a")
            self.assertEqual(review_proposal(d).status, STATUS)

    def test_symlinked_file_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "real.json"
            path.write_text(json.dumps(proposal()), encoding="utf8")
            link = root / "linked.json"
            try:
                link.symlink_to(path)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink fixtures unavailable on this host")
            with self.assertRaises(ProposalError):
                read_proposal_file(link)

    def test_report_only_shows_bounded_tokens_not_file_paths(self):
        report = describe_proposal(review_proposal(proposal()))
        self.assertIn("UNTRUSTED", report)
        self.assertIn("OTHER-DRIVE", report)
        self.assertIn("No disk writes", report)
        self.assertNotIn("/dev/", report)

    def test_cli_reads_explicit_file_but_never_authorizes(self):
        from nightglass.cli import main
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposal.json"
            path.write_text(json.dumps(proposal()), encoding="utf8")
            with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                result = main(["proposal-review", "--file", str(path), "--json"])
            self.assertEqual(result, 0)
            doc = json.loads(stdout.getvalue())
            self.assertEqual(doc["status"], STATUS)
            self.assertFalse(doc["disk_write_authorized"])
            self.assertFalse(doc["os_install_authorized"])

    def test_bad_file_returns_error_without_report(self):
        from nightglass.cli import main
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            path.write_text("{}", encoding="utf8")
            with patch("sys.stderr", new_callable=io.StringIO) as stderr:
                result = main(["proposal-review", "--file", str(path)])
            self.assertEqual(result, 2)
            self.assertIn("rejected", stderr.getvalue().lower())

    def test_all_authorization_flags_always_false(self):
        for mode in ("format_target", "coexist"):
            d = proposal()
            d["intent"] = mode
            report = asdict(review_proposal(d))
            for field in ("completeness_independently_verified",
                          "physical_device_identity_verified",
                          "actual_partition_geometry_verified",
                          "all_connected_disks_accounted_for",
                          "official_installer_origin_verified",
                          "user_backups_verified_by_nightglass",
                          "independent_destructive_consent", "disk_write_authorized",
                          "os_install_authorized"):
                with self.subTest(mode=mode, field=field):
                    self.assertIs(report[field], False)

    def test_no_executors_in_parser_module(self):
        import nightglass.install_proposal_review as mod
        source = Path(mod.__file__).read_text(encoding="utf-8")
        for token in ("subprocess.run(", "subprocess.Popen(", "os.system(",
                      ".write_bytes(", ".write_text(", "shutil.copy",
                      "Format-Volume", "Clear-Disk"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
