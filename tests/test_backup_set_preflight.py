"""Offline synthetic tests for a multi-location pre-reinstall backup catalog.

All file data is fake and created within disposable temporary directories.
No real personal files, USB, Git, Docker, installer, or network access.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Verify-Nightglass-BackupSet.py"
spec = importlib.util.spec_from_file_location("nightglass_backup_set_test", SCRIPT)
settool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(settool)


class BackupSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = settool.checker_module()

    def fixture(self, directory: Path):
        roots = {}
        for label in ("nightglass", "personal"):
            original = directory / (label + "-source")
            backup = directory / (label + "-portable-copy")
            original.mkdir()
            backup.mkdir()
            (original / ".env").write_text("FAKE_TEST_SECRET=none", encoding="utf-8")
            (backup / ".env").write_text("FAKE_TEST_SECRET=none", encoding="utf-8")
            (original / "nested").mkdir()
            (backup / "nested").mkdir()
            (original / "nested" / "readme.txt").write_text("hello", encoding="utf-8")
            (backup / "nested" / "readme.txt").write_text("hello", encoding="utf-8")
            roots[label] = (original, backup)
        return roots

    def manifest(self, directory: Path, roots: dict):
        payload = {"version": 1, "entries": [
            {"id": name, "source": str(src), "backup": str(dst)}
            for name, (src, dst) in roots.items()
        ]}
        path = directory / "private.backup-set.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_preview_does_not_import_checker_or_read_files(self):
        with patch.object(settool, "checker_module",
                          side_effect=AssertionError("Preview may not access files")):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(settool.main([]), 0)
        self.assertIn("PREVIEW ONLY", output.getvalue())

    def test_two_independent_roots_both_sha256_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            path = self.manifest(home, self.fixture(home))
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(settool.main([
                    "--mode", "Verify", "--manifest", str(path)]), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "CONTENT_MATCH")
            self.assertEqual(result["entry_count"], 2)
            self.assertTrue(result["all_selected_content_matched"])
            self.assertTrue(all(row["content_hashed"] for row in result["entries"]))
            self.assertTrue(all(row["source_markers_present"][".env"]
                                for row in result["entries"]))
            self.assertFalse(result["restore_drill_performed"])
            self.assertFalse(result["restore_proven"])
            self.assertFalse(result["full_machine_backup_completeness_proven"])
            self.assertFalse(result["windows_install_authorized"])

    def test_single_changed_same_size_file_blocks_entire_set(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            roots = self.fixture(home)
            path = self.manifest(home, roots)
            (roots["personal"][1] / ".env").write_text(
                "FAKE_TEST_SECRET=nope", encoding="utf-8")
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(settool.main([
                    "--mode", "Verify", "--manifest", str(path)]), 1)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertFalse(result["all_selected_content_matched"])
            row = {x["id"]: x for x in result["entries"]}
            self.assertEqual(row["nightglass"]["different_file_hashes"], 0)
            self.assertEqual(row["personal"]["different_file_hashes"], 1)

    def test_missing_copy_blocks_and_isolated_extras_never_deleted(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            roots = self.fixture(home)
            p = self.manifest(home, roots)
            (roots["personal"][1] / "nested" / "readme.txt").unlink()
            extra = roots["nightglass"][1] / "older-file.bin"
            extra.write_bytes(b"DO_NOT_DELETE")
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(settool.main(["--mode", "Verify", "--manifest", str(p)]), 1)
            report = json.loads(output.getvalue())
            self.assertEqual(report["status"], "INCOMPLETE")
            self.assertEqual(report["additional_backup_files_to_review"], 1)
            self.assertEqual(extra.read_bytes(), b"DO_NOT_DELETE")

    def test_inspect_does_not_claim_content_matching(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            roots = self.fixture(home)
            p = self.manifest(home, roots)
            (roots["personal"][1] / ".env").write_text(
                "FAKE_TEST_SECRET=nope", encoding="utf-8")
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(settool.main(["--mode", "Inspect", "--manifest", str(p)]), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "INVENTORY_ONLY_NOT_CONTENT_VERIFIED")
            self.assertFalse(result["all_selected_content_matched"])
            self.assertFalse(result["entries"][0]["content_hashed"])

    def test_one_empty_source_blocks_vacuous_success(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            roots = self.fixture(home)
            empty, dst = roots["personal"]
            (empty / ".env").unlink()
            (empty / "nested" / "readme.txt").unlink()
            p = self.manifest(home, roots)
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(settool.main([
                    "--mode", "Verify", "--manifest", str(p)]), 2)

    def test_empty_manifest_and_oversized_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            p = home / "private.json"
            for payload in ("", '{"version": 1, "entries": []}',
                            '{"version": 1, "version": 1, "entries": []}',
                            '{"version": 1, "entries": null}',
                            "x" * (settool.MAX_MANIFEST_BYTES + 1)):
                p.write_text(payload, encoding="utf-8")
                with self.subTest(payload_length=len(payload)):
                    with self.assertRaises(settool.SetError):
                        settool.read_manifest(p, self.base)

    def test_nonabsolute_paths_rejected_before_source_read(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            roots = self.fixture(home)
            p = self.manifest(home, roots)
            data = json.loads(p.read_text())
            data["entries"][0]["backup"] = "../relative"
            p.write_text(json.dumps(data))
            with self.assertRaises(settool.SetError):
                settool.read_manifest(p, self.base)

    def test_overlapping_or_repeated_source_roots_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            roots = self.fixture(home)
            p = self.manifest(home, roots)
            data = json.loads(p.read_text())
            data["entries"][1]["source"] = data["entries"][0]["source"]
            p.write_text(json.dumps(data))
            with self.assertRaises(settool.SetError):
                settool.read_manifest(p, self.base)

    def test_duplicate_or_sensitive_labels_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            roots = self.fixture(home)
            p = self.manifest(home, roots)
            data = json.loads(p.read_text())
            for value in ("nightglass", "C:/private", "MY EMAIL", "", "a" * 60):
                data["entries"][1]["id"] = value
                p.write_text(json.dumps(data))
                with self.subTest(label=value):
                    with self.assertRaises(settool.SetError):
                        settool.read_manifest(p, self.base)

    def test_symlinked_manifest_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            roots = self.fixture(home)
            p = self.manifest(home, roots)
            link = home / "pointer.json"
            try:
                link.symlink_to(p)
            except (OSError, NotImplementedError):
                return
            with self.assertRaises(settool.SetError):
                settool.read_manifest(link, self.base)

    def test_exclusive_report_is_outside_every_selected_root(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            roots = self.fixture(home)
            p = self.manifest(home, roots)
            out = home / "new-summary.json"
            args = ["--mode", "Verify", "--manifest", str(p),
                    "--report", str(out)]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(settool.main(args), 0)
            result = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(result["all_selected_content_matched"])
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(settool.main(args), 2)
            self.assertTrue(result["all_selected_content_matched"])
            inside = roots["personal"][0] / "report.json"
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(settool.main([
                    "--mode", "Verify", "--manifest", str(p),
                    "--report", str(inside)]), 2)
            self.assertFalse(inside.exists())

    def test_cli_omits_absolute_paths_and_user_file_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            roots = self.fixture(home)
            p = self.manifest(home, roots)
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(settool.main([
                    "--mode", "Verify", "--manifest", str(p)]), 0)
            printed = stdout.getvalue()
            self.assertNotIn(str(home), printed)
            self.assertNotIn("FAKE_TEST_SECRET", printed)
            self.assertNotIn("private.backup-set", printed)

    def test_no_network_copy_restore_install_or_git_operations(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "subprocess.run", "git fetch", "docker run", "shutil.copy",
            "shutil.move", "shutil.rmtree", "os.system(",
            "os.replace(", "os.unlink(", "Format-Volume", "diskpart",
            "Ventoy2Disk", "setup.exe", "manage-bde",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("module.inventory(", source)
        self.assertIn("module.compare(", source)
        self.assertIn("full_machine_backup_completeness_proven", source)


if __name__ == "__main__":
    unittest.main()
