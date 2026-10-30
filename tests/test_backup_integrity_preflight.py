"""Offline synthetic verification of Midnight Provisioner read-only backup integrity.

Uses temporary miniature trees only: no user documents, portable disks,
GitHub, Git, privileged operations or OS installers are touched.
"""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import json
import os
import stat
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "backup" / "Inspect-Midnight-Provisioner-Backup.py"
spec = importlib.util.spec_from_file_location("midnight_provisioner_backup_inspector", TOOL)
backup = importlib.util.module_from_spec(spec)
assert spec.loader is not None
# dataclasses with postponed annotations resolve their declaring module
# through sys.modules: register this private synthetic import first.
sys.modules[spec.name] = backup
spec.loader.exec_module(backup)


class BackupIntegrityTests(unittest.TestCase):
    def make_trees(self, parent: Path):
        src, dst = parent / "original", parent / "portable-copy"
        src.mkdir()
        dst.mkdir()
        for folder in (src, dst):
            (folder / ".git").mkdir()
            (folder / ".git" / "config").write_bytes(b"[core]\nrepositoryformatversion=0\n")
            (folder / ".venv").mkdir()
            (folder / ".venv" / "pyvenv.cfg").write_bytes(b"synthetic env\n")
            (folder / ".env").write_bytes(b"LOCAL_FAKE_KEY=NO_REAL_SECRETS\n")
            (folder / "nested").mkdir()
            (folder / "nested" / "data.bin").write_bytes(b"abc\x00xyz")
        return src, dst

    def inspect(self, source, destination, *, verify):
        src = backup.checked_root(source)
        dst = backup.checked_root(destination)
        self.assertTrue(backup.separated(src, dst))
        a = backup.inventory(src, max_files=100, max_bytes=1024**2)
        b = backup.inventory(dst, max_files=100, max_bytes=1024**2)
        result, differences = backup.compare(
            a, b, verify=verify, source_device=src.stat().st_dev,
            backup_device=dst.stat().st_dev)
        return result, differences

    def test_preview_has_zero_file_access_or_writes(self):
        with patch.object(backup, "checked_root", side_effect=AssertionError("filesystem read")), \
             patch.object(backup, "inventory", side_effect=AssertionError("filesystem scan")), \
             patch.object(backup, "write_report_new", side_effect=AssertionError("filesystem write")):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(backup.main([]), 0)
        self.assertIn("PREVIEW ONLY", output.getvalue())
        self.assertIn("No directory enumeration", output.getvalue())

    def test_exact_copies_include_git_env_venv_and_nested_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = self.make_trees(Path(folder))
            result, diffs = self.inspect(src, dst, verify=True)
            self.assertEqual(result["status"], "CONTENT_MATCH")
            self.assertTrue(result["verification_succeeded"])
            self.assertEqual(result["required_files"], 4)
            self.assertTrue(all(result["source_markers_present"].values()))
            self.assertTrue(all(result["backup_markers_present"].values()))
            self.assertEqual(diffs, [])
            self.assertFalse(result["backup_recovery_proven"])
            self.assertFalse(result["external_media_confirmed"])
            self.assertFalse(result["data_copy_performed"])

    def test_identical_size_but_different_bytes_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = self.make_trees(Path(folder))
            (dst / ".env").write_bytes(b"LOCAL_FAKE_KEY=NO_REAL_SECRETZ\n")
            result, differences = self.inspect(src, dst, verify=True)
            self.assertEqual(result["different_file_sizes"], 0)
            self.assertEqual(result["different_file_hashes"], 1)
            self.assertEqual(result["status"], "BACKUP_CONTENT_MISMATCH")
            self.assertFalse(result["verification_succeeded"])
            self.assertIn(".env", differences)

    def test_inspect_never_mistaken_for_content_hash_check(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = self.make_trees(Path(folder))
            (dst / ".env").write_bytes(b"LOCAL_FAKE_KEY=NO_REAL_SECRETZ\n")
            result, _ = self.inspect(src, dst, verify=False)
            self.assertEqual(result["status"], "INVENTORY_ONLY_NOT_CONTENT_VERIFIED")
            self.assertFalse(result["content_hashed"])
            self.assertFalse(result["verification_succeeded"])

    def test_missing_and_extra_files_are_reported_separately(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = self.make_trees(Path(folder))
            (dst / "nested" / "data.bin").unlink()
            (dst / "extra.txt").write_text("old unrelated export", encoding="utf-8")
            result, differences = self.inspect(src, dst, verify=True)
            self.assertEqual(result["missing_files"], 1)
            self.assertEqual(result["extra_backup_files"], 1)
            self.assertFalse(result["verification_succeeded"])
            self.assertIn("nested/data.bin", differences)

    def test_backup_extras_are_not_deleted_and_are_explicitly_marked(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = self.make_trees(Path(folder))
            extra = dst / "older-log.txt"
            extra.write_bytes(b"old")
            result, _ = self.inspect(src, dst, verify=True)
            self.assertEqual(result["status"], "CONTENT_MATCH_EXTRAS_REVIEW")
            self.assertTrue(result["verification_succeeded"])
            self.assertEqual(extra.read_bytes(), b"old")

    def test_same_inode_hardlink_copy_is_not_an_independent_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = self.make_trees(Path(folder))
            original = src / ".env"
            copied = dst / ".env"
            copied.unlink()
            try:
                os.link(original, copied)
            except (OSError, NotImplementedError):
                self.skipTest("Filesystem does not support hardlinks here")
            if original.stat().st_ino == 0 or original.stat().st_ino != copied.stat().st_ino:
                self.skipTest("Filesystem does not report stable hardlink file identity")
            result, diffs = self.inspect(src, dst, verify=True)
            self.assertEqual(result["same_file_identity_count"], 1)
            self.assertEqual(result["status"], "NOT_INDEPENDENT_FILE_COPY")
            self.assertFalse(result["verification_succeeded"])
            self.assertIn(".env", diffs)

    def test_cross_name_hardlink_is_not_an_independent_copy(self):
        # Old check only compared source and backup at the SAME path.
        # A source/first.bin hardlink masquerading as backup/second.bin
        # must fail even though expected contents and sizes match.
        with tempfile.TemporaryDirectory() as folder:
            src, dst = self.make_trees(Path(folder))
            first = src / "first.bin"
            second = src / "second.bin"
            first.write_bytes(b"same data")
            second.write_bytes(b"same data")
            (dst / "first.bin").write_bytes(b"same data")
            alias = dst / "second.bin"
            try:
                os.link(first, alias)
            except (OSError, NotImplementedError):
                self.skipTest("Hardlinks unavailable on synthetic filesystem")
            if first.stat().st_ino == 0 or first.stat().st_ino != alias.stat().st_ino:
                self.skipTest("Filesystem does not report stable hardlink identity")
            result, differences = self.inspect(src, dst, verify=True)
            self.assertEqual(result["different_file_sizes"], 0)
            self.assertEqual(result["different_file_hashes"], 0)
            self.assertEqual(result["same_file_identity_count"], 1)
            self.assertEqual(result["status"], "NOT_INDEPENDENT_FILE_COPY")
            self.assertEqual(result["identity_scope"], "ALL_FILES_IN_SELECTED_SOURCE_ROOT")
            self.assertFalse(result["verification_succeeded"])
            self.assertIn("second.bin", differences)

    def test_extra_backup_file_hardlinked_to_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = self.make_trees(Path(folder))
            original = src / ".env"
            alias = dst / "extra-but-not-independent.env"
            try:
                os.link(original, alias)
            except (OSError, NotImplementedError):
                self.skipTest("Hardlinks unavailable on synthetic filesystem")
            if original.stat().st_ino == 0 or original.stat().st_ino != alias.stat().st_ino:
                self.skipTest("Filesystem does not report stable hardlink identity")
            result, differences = self.inspect(src, dst, verify=True)
            self.assertEqual(result["extra_backup_files"], 1)
            self.assertEqual(result["same_file_identity_count"], 1)
            self.assertEqual(result["status"], "NOT_INDEPENDENT_FILE_COPY")
            self.assertFalse(result["verification_succeeded"])
            self.assertIn(alias.name, differences)

    def test_no_recursive_or_self_comparison(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = root / "source"
            original.mkdir()
            inside = original / "copies"
            inside.mkdir()
            for src, dst in ((original, original), (original, inside),
                             (inside, original)):
                with self.subTest(source=src, backup=dst):
                    with self.assertRaises(backup.BackupError):
                        backup.separated(src.resolve(), dst.resolve())

    def test_symlinked_file_or_folder_blocks_instead_of_escaping(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = self.make_trees(Path(folder))
            link = src / "external-link"
            try:
                link.symlink_to(dst, target_is_directory=True)
            except (OSError, NotImplementedError):
                return  # Windows standard user may not have link privileges.
            with self.assertRaises(backup.BackupError):
                backup.inventory(src, max_files=100, max_bytes=1024**2)
            with self.assertRaises(backup.BackupError):
                backup.checked_root(link)

    def test_windows_reparse_attribute_is_a_hard_block_even_without_symlink_mode(self):
        # Synthetic junction/reparse attributes; real native Windows
        # junction creation and check remain a separate acceptance step.
        fake_dir = SimpleNamespace(st_mode=stat.S_IFDIR,
                                   st_file_attributes=0x400)
        with patch.object(backup.stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400,
                          create=True):
            self.assertTrue(backup.is_link_or_reparse(Path("fake"), fake_dir))

    def test_linked_parent_of_selected_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            real_parent = root / "actual"
            real_parent.mkdir()
            child = real_parent / "project"
            child.mkdir()
            alias = root / "shortcut"
            try:
                alias.symlink_to(real_parent, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Directory symlink creation unavailable")
            # Final component 'project' is NOT itself a symlink.
            self.assertFalse((alias / "project").is_symlink())
            with self.assertRaises(backup.BackupError):
                backup.checked_root(alias / "project")
            self.assertEqual(backup.checked_root(child), child.resolve())

    def test_linked_parent_of_report_is_blocked_without_creating_output(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            real = root / "real"
            real.mkdir()
            alias = root / "linked-parent"
            try:
                alias.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Directory symlink creation unavailable")
            report = alias / "safe-looking.json"
            with self.assertRaises(backup.BackupError):
                backup.write_report_new(report, {"state": "test"},
                                        (root / "source", root / "backup"))
            self.assertFalse((real / "safe-looking.json").exists())

    def test_dotdot_parent_traversal_does_not_skip_link_detection(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            normal = root / "source"
            normal.mkdir()
            unsafe = root / "middle" / ".." / "source"
            with self.assertRaises(backup.BackupError):
                backup.checked_root(unsafe)
            self.assertEqual(backup.checked_root(normal), normal.resolve())

    def test_report_parent_traversal_is_blocked_before_normalization(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            intended = root / "real"
            intended.mkdir()
            wrong = intended / "child"
            wrong.mkdir()
            destination = wrong / ".." / "out.json"
            with self.assertRaises(backup.BackupError):
                backup.write_report_new(destination, {"test": True},
                                        (root / "source", root / "backup"))
            self.assertFalse((intended / "out.json").exists())

    def test_large_file_and_count_limits_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = self.make_trees(Path(folder))
            with self.assertRaises(backup.BackupError):
                backup.inventory(src, max_files=2, max_bytes=1024**2)
            with self.assertRaises(backup.BackupError):
                backup.inventory(src, max_files=100, max_bytes=1)

    def test_empty_directory_bomb_respects_explicit_entry_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "mostly-empty"
            root.mkdir()
            for n in range(12):
                (root / f"empty-{n}").mkdir()
            with self.assertRaises(backup.BackupError):
                backup.inventory(root, max_files=10, max_bytes=1024**2)

    def test_changes_after_inventory_are_not_marked_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = self.make_trees(Path(folder))
            original = backup.inventory(src, max_files=100, max_bytes=1024**2)
            (src / ".env").write_bytes(b"modified after initial snapshot")
            with self.assertRaises(backup.BackupError):
                backup.fingerprint(original.files[".env"])

    def test_report_is_opt_in_exclusive_and_never_written_inside_scanned_data(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = self.make_trees(Path(folder))
            target = Path(folder) / "local-summary.json"
            payload = {"status": "INCOMPLETE", "os_install_authorized": False}
            backup.write_report_new(target, payload, (src.resolve(), dst.resolve()))
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), payload)
            with self.assertRaises(FileExistsError):
                backup.write_report_new(target, {"status": "PASS"}, (src.resolve(), dst.resolve()))
            with self.assertRaises(backup.BackupError):
                backup.write_report_new(src / "new-report.json", payload,
                                        (src.resolve(), dst.resolve()))

    def test_live_cli_verify_requires_explicit_two_existing_directories(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = self.make_trees(Path(folder))
            args = ["--mode", "Verify", "--source", str(src), "--backup", str(dst)]
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(backup.main(args), 0)
            self.assertTrue(json.loads(output.getvalue())["verification_succeeded"])
            (dst / "nested" / "data.bin").unlink()
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(backup.main(args), 1)
            self.assertFalse(json.loads(output.getvalue())["verification_succeeded"])

    def test_no_executable_install_or_data_transfer_code(self):
        code = TOOL.read_text(encoding="utf-8")
        for forbidden in (
            "shutil.copy", "shutil.move", "subprocess.run",
            "requests.get", "urllib.request", "git fetch",
            "docker run", "bcdedit", "diskpart", "Format-Volume",
            "setup.exe", "mountvol", "os.system(", "os.remove(",
            "os.unlink(", "os.replace(", "shutil.rmtree(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)
        self.assertIn("O_EXCL", code)
        self.assertIn("FILE_ATTRIBUTE_REPARSE_POINT", code)
        self.assertIn("content_hashed", code)


if __name__ == "__main__":
    unittest.main()
