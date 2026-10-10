"""Offline synthetic tests for Phase 19. Never inspects actual disks or backup media."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "windows" / "Build-Nightglass-Phase19-Preflight.py"
spec = importlib.util.spec_from_file_location("nightglass_phase19_preflight", SCRIPT)
tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(tool)

NAMES = (
    "windows_servicing", "firmware", "secure_boot", "fast_startup",
    "volume_encryption", "ram_budget", "virtualization_firmware",
    "os_disk_layout", "partition_map",
)


def host_report():
    result = {
        "schema": tool.HOST_SCHEMA,
        "mode": "READ_ONLY_NATIVE_WINDOWS",
        "status": "HOLD_MANUAL_DEPLOYMENT_APPROVAL",
        "observed_os_family": "WINDOWS_10",
        "observations": [
            {"name": name, "state": ("HOLD" if name == "fast_startup" else
                                     "UNKNOWN" if name in ("secure_boot", "volume_encryption")
                                     else "REVIEW"),
             "evidence": "Synthetic marker", "next": "Manual check"}
            for name in NAMES
        ],
        "hold_checks": 1,
        "unknown_checks": 2,
        "manual_requirements": ["Independent human check"] * 8,
    }
    for key in ("full_backup_verified", "restore_verified",
                "bitlocker_recovery_key_verified", "windows_install_authorized",
                "fedora_install_authorized", "disk_partition_write_authorized",
                "real_fedora_host_isolation_verified",
                "contains_serials_secrets_or_raw_disk_paths"):
        result[key] = False
    return result


class Phase19PreinstallTests(unittest.TestCase):
    def test_synthetic_phase18_report_is_accepted_without_approving_deployment(self):
        result = tool.assess(host_report())
        self.assertEqual(result["schema"], tool.SCHEMA)
        self.assertEqual(result["status"], "HOLD_MANUAL_AND_PHYSICAL_ACCEPTANCE")
        self.assertEqual(result["host_hold_count"], 1)
        self.assertEqual(result["host_unknown_count"], 2)
        self.assertGreaterEqual(result["pending_independent_checks"], 11)
        for key in ("backup_proven", "recovery_proven",
                    "windows_security_servicing_proven",
                    "physical_fedora_host_security_proven",
                    "fedora_live_usb_safety_proven",
                    "windows_install_authorized", "fedora_install_authorized",
                    "disk_write_authorized", "vm_start_authorized"):
            with self.subTest(key=key):
                self.assertIs(result[key], False)

    def test_duplicate_or_missing_host_checks_fail_closed(self):
        for mutate in ("remove", "duplicate", "unknown_name", "unsafe_state"):
            payload = host_report()
            if mutate == "remove":
                payload["observations"].pop()
            elif mutate == "duplicate":
                payload["observations"][1]["name"] = payload["observations"][0]["name"]
            elif mutate == "unknown_name":
                payload["observations"][0]["name"] = "invented"
            else:
                payload["observations"][0]["state"] = "PASS"
            with self.subTest(mutate=mutate), self.assertRaises(tool.GateError):
                tool.validate_host(payload)

    def test_missing_or_truthy_proof_flags_fail_closed(self):
        for field in ("full_backup_verified", "restore_verified", "fedora_install_authorized",
                      "disk_partition_write_authorized", "real_fedora_host_isolation_verified",
                      "contains_serials_secrets_or_raw_disk_paths"):
            payload = host_report()
            payload[field] = True
            with self.subTest(field=field), self.assertRaises(tool.GateError):
                tool.validate_host(payload)
            del payload[field]
            with self.subTest(missing=field), self.assertRaises(tool.GateError):
                tool.validate_host(payload)

    def test_inconsistent_count_and_schema_fail_closed(self):
        for key, value in (
            ("hold_checks", 0), ("unknown_checks", 9),
            ("schema", "nightglass.fake.v1"),
            ("mode", "WRITE_DISKS"),
            ("status", "INSTALL_APPROVED"),
            ("observed_os_family", "WINDOWS_13"),
        ):
            payload = host_report()
            payload[key] = value
            with self.subTest(key=key), self.assertRaises(tool.GateError):
                tool.validate_host(payload)

    def test_duplicate_json_keys_and_nonfinite_values_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            report = Path(scratch) / "host.json"
            for invalid in ('{"schema":1,"schema":2}', '{"value":NaN}'):
                report.write_text(invalid, encoding="utf-8")
                with self.subTest(invalid=invalid), self.assertRaises(tool.GateError):
                    tool.read_host_report(report)

    def test_synthetic_host_json_roundtrip_and_absent_manual_evidence(self):
        with tempfile.TemporaryDirectory() as scratch:
            report = Path(scratch) / "host.json"
            report.write_text(json.dumps(host_report()), encoding="utf-8")
            before = report.read_bytes()
            with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
                code = tool.main(["--host-report", str(report)])
            self.assertEqual(code, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "HOLD_MANUAL_AND_PHYSICAL_ACCEPTANCE")
            self.assertEqual(result["iso_verification"]["status"], "NOT_SUPPLIED")
            self.assertEqual(report.read_bytes(), before)
            self.assertNotIn(str(report), out.getvalue())

    def test_manifest_symlink_and_parent_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            directory = Path(scratch)
            report = directory / "host.json"
            report.write_text(json.dumps(host_report()), encoding="utf-8")
            target = directory / "alias.json"
            try:
                target.symlink_to(report)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink creation unavailable on this Windows host")
            with self.assertRaises(tool.GateError):
                tool.read_host_report(target)
            with self.assertRaises(tool.GateError):
                tool.read_host_report(directory / ".." / directory.name / report.name)

    def test_oversized_report_rejected_before_json_parsing(self):
        with tempfile.TemporaryDirectory() as scratch:
            report = Path(scratch) / "host.json"
            report.write_bytes(b"A" * (tool.MAX_REPORT_BYTES + 1))
            with self.assertRaises(tool.GateError):
                tool.read_host_report(report)

    def test_iso_argument_pair_requires_explicit_hash(self):
        with self.assertRaises(tool.GateError):
            tool.verify_iso(Path("/tmp/fixture.iso"), None)
        with self.assertRaises(tool.GateError):
            tool.verify_iso(None, "f" * 64)
        with self.assertRaises(tool.GateError):
            tool.verify_iso(Path("/tmp/fixture.iso"), "unsafe")

    def test_iso_hashing_reads_bytes_without_modifying_fixture(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "synthetic.iso"
            fake = b"benign miniature synthetic ISO placeholder"
            path.write_bytes(fake)
            digest = hashlib.sha256(fake).hexdigest()
            with patch.object(tool, "MIN_ISO_BYTES", 1):
                matches = tool.verify_iso(path, digest)
                mismatches = tool.verify_iso(path, "0" * 64)
            self.assertTrue(matches["sha256_matches_operator_digest"])
            self.assertEqual(matches["status"], "HASH_MATCHES_OPERATOR_INPUT")
            self.assertIs(matches["official_fedora_provenance_verified"], False)
            self.assertEqual(mismatches["status"], "HASH_MISMATCH_BLOCKED")
            self.assertEqual(path.read_bytes(), fake)

    def test_iso_match_does_not_approve_live_usb_or_install(self):
        iso = {"status": "HASH_MATCHES_OPERATOR_INPUT",
               "sha256_matches_operator_digest": True,
               "official_fedora_provenance_verified": False}
        assessment = tool.assess(host_report(), iso)
        self.assertFalse(assessment["fedora_install_authorized"])
        self.assertFalse(assessment["fedora_live_usb_safety_proven"])
        self.assertFalse(assessment["physical_fedora_host_security_proven"])
        self.assertIn("fedora_iso_provenance",
                      [item["id"] for item in assessment["blockers"]])

    def test_untrusted_iso_provenance_claim_is_blocked(self):
        with self.assertRaises(tool.GateError):
            tool.assess(host_report(), {"status": "FAKE", "sha256_matches_operator_digest": True,
                                        "official_fedora_provenance_verified": True})

    def test_no_network_or_unsafe_operations_in_preflight_source(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("subprocess.", "requests.", "urllib.request", "socket.",
                          "os.system", "shutil.copy", "os.remove", "os.unlink",
                          "os.replace", "os.rename", "os.chmod", "os.chown",
                          "open(", "write_text(", "write_bytes("):
            with self.subTest(fragment=forbidden):
                # open is allowed only as os.open(..., O_RDONLY), which is
                # separately checked below.
                if forbidden == "open(":
                    self.assertNotIn("path.open(", source)
                else:
                    self.assertNotIn(forbidden, source)
        self.assertIn("os.O_RDONLY", source)
        self.assertIn("O_NOFOLLOW", source)
        self.assertIn("HOLD_MANUAL_AND_PHYSICAL_ACCEPTANCE", source)


if __name__ == "__main__":
    unittest.main()
