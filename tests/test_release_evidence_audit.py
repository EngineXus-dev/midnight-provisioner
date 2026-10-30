"""No network, Git or Docker: check tamper resistance of local release evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUDITOR = ROOT / "scripts" / "release" / "Audit-Midnight-Provisioner-Release-Evidence.py"
spec = importlib.util.spec_from_file_location("midnight_provisioner_release_evidence_test_module", AUDITOR)
audit_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit_module)

COMMIT = "c" * 40
LOG = b"midnight-provisioner local synthetic test log\n"


def valid_report():
    return {
        "format": audit_module.SCHEMA,
        "branch": audit_module.BRANCH,
        "tested_commit": COMMIT,
        "checks": {key: "PASS" for key in audit_module.CHECKS},
        "test_gate_passed": True,
        "execution_error": None,
        "original_main_before": "a" * 40,
        "original_main_after": "a" * 40,
        "local_log_sha256": hashlib.sha256(LOG).hexdigest(),
        "physical_fedora_kvm_svirt_network_restore": "NOT_TESTED",
        "windows11_clean_install_usb_formatter": "NOT_RUN",
        "github_pr_merge_or_actions": "NOT_PERFORMED",
        "deployment_approved": False,
        "release_attested": False,
        "report_authentication": "LOCAL_UNAUTHENTICATED",
    }


class LocalReleaseEvidenceTests(unittest.TestCase):
    def test_valid_report_means_synthetic_only(self):
        report = valid_report()
        self.assertEqual(audit_module.audit(
            report, expected_commit=COMMIT, log_bytes=LOG), [])
        self.assertFalse(report["deployment_approved"])
        self.assertFalse(report["release_attested"])

    def test_every_missing_or_blocked_stage_rejected(self):
        for stage in audit_module.CHECKS:
            for value in ("FAIL", "BLOCKED", "NOT_RUN", 123):
                with self.subTest(stage=stage, value=value):
                    r = valid_report()
                    r["checks"][stage] = value
                    self.assertTrue(audit_module.audit(
                        r, expected_commit=COMMIT, log_bytes=LOG))

    def test_report_cannot_fake_pass_or_physical_acceptance(self):
        mutations = (
            ("test_gate_passed", "true"),
            ("test_gate_passed", 1),
            ("original_main_after", "b" * 40),
            ("release_attested", True),
            ("deployment_approved", True),
            ("physical_fedora_kvm_svirt_network_restore", "PASS"),
            ("windows11_clean_install_usb_formatter", "PASS"),
            ("github_pr_merge_or_actions", "MERGED"),
            ("report_authentication", "SIGNED"),
            ("execution_error", "TimeoutError"),
            ("branch", "main"),
            ("format", "midnight-provisioner-offline-rc-gate-v1"),
            ("local_log_sha256", "0" * 64),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                r = valid_report()
                r[field] = value
                self.assertTrue(audit_module.audit(
                    r, expected_commit=COMMIT, log_bytes=LOG))

    def test_exact_sha_and_log_binding_required(self):
        self.assertTrue(audit_module.audit(
            valid_report(), expected_commit="d" * 40, log_bytes=LOG))
        self.assertTrue(audit_module.audit(
            valid_report(), expected_commit=COMMIT, log_bytes=b"tampered"))
        self.assertTrue(audit_module.audit(
            valid_report(), expected_commit=COMMIT, log_bytes=None))
        with self.assertRaises(audit_module.EvidenceError):
            audit_module.audit(valid_report(), expected_commit="short", log_bytes=LOG)

    def test_extraneous_or_missing_check_rejected(self):
        for change in ("missing", "extra"):
            r = valid_report()
            if change == "missing":
                del r["checks"][audit_module.CHECKS[0]]
            else:
                r["checks"]["hardware_kvm"] = "PASS"
            self.assertTrue(audit_module.audit(r, expected_commit=COMMIT, log_bytes=LOG))

    def test_reject_json_duplicate_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / "bad.json"
            f.write_text('{"format": "ok", "format": "different"}', encoding="utf-8")
            with self.assertRaises(audit_module.EvidenceError):
                audit_module.read_report(f)

    def test_reject_nonstandard_nan_infinity_even_in_extra_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            for token in ("NaN", "Infinity", "-Infinity"):
                path = Path(folder) / "nonstandard.json"
                path.write_text('{"test_gate_passed": ' + token + '}',
                                encoding="utf-8")
                with self.subTest(token=token):
                    with self.assertRaises(audit_module.EvidenceError):
                        audit_module.read_report(path)

    def test_file_cannot_be_overlarge_or_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "huge.json"
            p.write_bytes(b"x" * (audit_module.MAX_REPORT_BYTES + 1))
            with self.assertRaises(audit_module.EvidenceError):
                audit_module.read_report(p)
            with self.assertRaises(audit_module.EvidenceError):
                audit_module.read_report(Path(folder))
            alias = Path(folder) / "alias.json"
            try:
                alias.symlink_to(p)
            except (OSError, NotImplementedError):
                return  # Standard Windows user may not have symlink privileges.
            with self.assertRaises(audit_module.EvidenceError):
                audit_module.read_report(alias)

    def test_cli_checks_report_and_real_local_log(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rp, lp = root / "report.json", root / "run.log"
            rp.write_text(json.dumps(valid_report()), encoding="utf-8")
            lp.write_bytes(LOG)
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(audit_module.main([
                    "--report", str(rp), "--log", str(lp),
                    "--expected-commit", COMMIT]), 0)
            self.assertIn("SYNTHETIC LOCAL REPORT CONSISTENT", output.getvalue())
            self.assertIn("NOT DEPLOYMENT READY", output.getvalue())
            lp.write_bytes(b"tamper")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(audit_module.main([
                    "--report", str(rp), "--log", str(lp),
                    "--expected-commit", COMMIT]), 1)

    def test_no_destructive_commands_or_persistence(self):
        source = AUDITOR.read_text(encoding="utf-8")
        for word in ("docker run", "git checkout", "git reset", "git clean",
                     "diskpart", "format-volume", "powershell.exe",
                     "shutil.rmtree", "Start-Process", "setup.exe"):
            with self.subTest(word=word):
                self.assertNotIn(word, source)
        self.assertIn("LOCAL_UNAUTHENTICATED", source)
        self.assertIn("MAX_LOG_BYTES", source)


if __name__ == "__main__":
    unittest.main()
