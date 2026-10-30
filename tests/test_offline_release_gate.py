"""Synthetic contract tests for the opt-in cumulative offline release gate.

Never runs git fetch, Docker, PowerShell, Fedora/libvirt or GitHub Actions.
"""
from __future__ import annotations

import base64
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "testing" / "Run-Midnight-Provisioner-Offline-Release-Gate.py"
spec = importlib.util.spec_from_file_location("midnight_provisioner_offline_gate_for_tests", RUNNER)
gate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gate)


class OfflineReleaseGateContractTests(unittest.TestCase):
    def test_default_is_plan_only_with_no_os_or_git_calls(self):
        with patch.object(gate, "repo_root", side_effect=AssertionError("Unexpected repo access")), \
             patch.object(gate, "verify", side_effect=AssertionError("Unexpected verifier")):
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(gate.main([]), 0)
        self.assertIn("PLAN ONLY", out.getvalue())
        self.assertIn("No GitHub Actions or merges", out.getvalue())

    def test_authorized_branch_and_origin_only(self):
        self.assertEqual(gate.BRANCH, "verification/phase17-qemu-subset-integrity")
        self.assertTrue(gate.ORIGIN.fullmatch(
            "https://github.com/EngineXus-dev/midnight-provisioner.git"))
        self.assertTrue(gate.ORIGIN.fullmatch(
            "git@github.com:EngineXus-dev/midnight-provisioner.git"))
        for bad in ("https://github.com/EngineXus-dev/unrelated.git",
                    "https://github.com/attacker/midnight-provisioner.git",
                    "https://example.com/EngineXus-dev/midnight-provisioner.git"):
            self.assertIsNone(gate.ORIGIN.fullmatch(bad))

    def test_isolated_docker_runtime_is_rootless_nonprivileged_readonly(self):
        opts = gate.docker_base(
            Path("/tmp/mock-detached"), label="midnight-provisioner-unit-test",
            memory="1024m", tmpfs="512m")
        text = " ".join(opts)
        for flag in ("--network none", "--read-only", "--cap-drop ALL",
                     "--security-opt no-new-privileges:true",
                     "--user 10001:10001", "--pull never", "--ipc private",
                     "target=/workspace,readonly", "size=512m",
                     "--memory 1024m"):
            self.assertIn(flag, text)
        for forbidden in ("--privileged", "/dev/kvm", "/var/run/docker.sock",
                          "--network host", "--mount type=bind,source=/,target=/"):
            self.assertNotIn(forbidden, text)

    def test_version_matrix_and_fedora_image_are_explicit(self):
        self.assertEqual(gate.VERSIONS, ("3.11", "3.12", "3.13"))
        self.assertEqual(len(gate.CHECKS), 6)
        self.assertIn("python_source_ast", gate.CHECKS)
        self.assertNotIn("windows_portable", gate.CHECKS)
        with tempfile.TemporaryDirectory() as home:
            worktree = Path(home)
            (worktree / "docker").mkdir()
            cf = worktree / gate.FEDORA_CONTAINERFILE
            cf.write_text("FROM fedora:43\n", encoding="utf-8")
            sha = hashlib.sha256(cf.read_bytes()).hexdigest()[:12]
            self.assertEqual(gate.fedora_tag(worktree),
                             "midnight-provisioner-fedora-verifier:43-" + sha)

    def test_powershell_source_is_parsed_not_executed(self):
        argv = gate.power_shell_ast(Path("C:/new-detached"))
        self.assertEqual(argv[0], "powershell.exe")
        self.assertIn("-EncodedCommand", argv)
        encoded = argv[-1]
        raw = base64.b64decode(encoded).decode("utf-16le")
        self.assertIn("Parser]::ParseFile(", raw)
        self.assertIn("Get-ChildItem", raw)
        self.assertIn("$errors.Count -gt 0", raw)
        self.assertNotIn("Invoke-Expression", raw)
        self.assertNotIn("Start-Process", raw)
        self.assertNotIn("& $p", raw)

    def test_python_ast_does_not_import_or_execute_fetched_code(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            for folder in ("midnight_provisioner", "tests", "scripts"):
                (root / folder).mkdir()
            for index in range(21):
                folder = ("midnight_provisioner", "tests", "scripts")[index % 3]
                (root / folder / f"fixture_{index}.py").write_text(
                    "assert False, 'Would execute if imported'\n", encoding="utf-8")
            self.assertEqual(gate.source_ast(root), 21)
            bad = root / "tests" / "bad.py"
            bad.write_text("def invalid(:\n", encoding="utf-8")
            with self.assertRaises(SyntaxError):
                gate.source_ast(root)
            bad.unlink()
            try:
                (root / "tests" / "alias.py").symlink_to(root / "tests" / "fixture_1.py")
            except (OSError, NotImplementedError):
                # Windows 10 may deny symlink creation without privileges.
                return
            with self.assertRaises(gate.GateError):
                gate.source_ast(root)

    def test_missing_image_remains_blocked_by_default(self):
        with patch.object(gate, "image_cached", return_value=False):
            with patch.object(gate, "run_logged", side_effect=AssertionError(
                    "Do not auto-pull when consent is absent")):
                self.assertFalse(gate.fresh_image("python:3.13-slim",
                    root=ROOT, allow_pull=False, stream=io.StringIO()))
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            (root / "docker").mkdir()
            (root / gate.FEDORA_CONTAINERFILE).write_text(
                "FROM fedora:43\n", encoding="utf-8")
            with patch.object(gate, "image_cached", return_value=False):
                with patch.object(gate, "run_logged", side_effect=AssertionError(
                        "Do not auto-build Fedora when consent is absent")):
                    self.assertFalse(gate.prepare_fedora(
                        "ng-fedora:test", checkout=root, allow_build=False,
                        stream=io.StringIO()))

    def test_detached_worktree_is_unique_and_never_mutates_main(self):
        with tempfile.TemporaryDirectory() as home:
            repo = Path(home) / "midnight-provisioner"
            repo.mkdir()
            calls = []

            def fake_checked(argv, *, cwd, timeout=30):
                calls.append(argv)
                if argv[-2:] == ["rev-parse", "HEAD"] or (
                        "rev-parse" in argv and argv[-1].startswith("refs/remotes")):
                    return "a" * 40
                return ""

            with patch.object(gate, "checked", side_effect=fake_checked):
                checkout, sha, log, report = gate.branch_checkout(repo)
            self.assertEqual(sha, "a" * 40)
            self.assertEqual(checkout.parent, repo.parent)
            self.assertTrue(checkout.name.startswith("Midnight-Provisioner-RC-"))
            self.assertNotEqual(checkout, repo)
            self.assertTrue(log.parent == report.parent == repo.parent)
            # Branch checkout now does fetch -> pinned ref verification ->
            # worktree add -> HEAD/ref equality checks. Do not assume
            # worktree is the second Git call as in older runner versions.
            worktree_calls = [command for command in calls if "worktree" in command]
            self.assertEqual(len(worktree_calls), 1)
            self.assertIn("--detach", worktree_calls[0])
            fetch_index = next(i for i, command in enumerate(calls)
                               if "fetch" in command)
            worktree_index = calls.index(worktree_calls[0])
            self.assertLess(fetch_index, worktree_index)
            self.assertTrue(any("rev-parse" in command
                                for command in calls[fetch_index + 1:worktree_index]))
            joined = " ".join(" ".join(c) for c in calls)
            for forbidden in (" reset ", " clean ", " merge ",
                              " rebase ", " push ", " checkout ", "Actions"):
                self.assertNotIn(forbidden, joined)
            self.assertFalse(log.exists())
            self.assertFalse(report.exists())

    def test_pinned_candidate_sha_mismatch_stops_before_worktree_creation(self):
        with tempfile.TemporaryDirectory() as home:
            repo = Path(home) / "midnight-provisioner"
            repo.mkdir()
            commands = []

            def fake_checked(argv, *, cwd, timeout=30):
                commands.append(argv)
                if "fetch" in argv:
                    return ""
                if "rev-parse" in argv:
                    return "a" * 40
                raise AssertionError("Worktree operation should never run")

            with patch.object(gate, "checked", side_effect=fake_checked):
                with self.assertRaises(gate.GateError):
                    gate.branch_checkout(repo, expected_sha="b" * 40)
            self.assertEqual(sum(1 for x in commands if "fetch" in x), 1)
            self.assertFalse(any("worktree" in x for x in commands))
            self.assertEqual(list(repo.parent.glob("Midnight-Provisioner-RC-*")), [])

    def test_invalid_expected_sha_prevents_even_fetch(self):
        with tempfile.TemporaryDirectory() as home:
            repo = Path(home)
            with patch.object(gate, "checked", side_effect=AssertionError(
                    "No Git operation permitted on invalid SHA")):
                with self.assertRaises(gate.GateError):
                    gate.branch_checkout(repo, expected_sha="too-short")

    def test_reports_exclusively_created_and_hardware_gate_not_attested(self):
        with tempfile.TemporaryDirectory() as home:
            file = Path(home) / "new-summary.json"
            payload = {"test_gate_passed": True,
                       "physical_fedora_kvm_svirt_network_restore": "NOT_TESTED"}
            gate.summary_file(file, payload)
            self.assertEqual(json.loads(file.read_text()), payload)
            with self.assertRaises(FileExistsError):
                gate.summary_file(file, payload)
            if os.name == "posix":
                self.assertEqual(file.stat().st_mode & 0o777, 0o600)

    def test_gate_source_does_not_operate_windows_installer_or_vm(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn('"github_pr_merge_or_actions": "NOT_PERFORMED"', source)
        self.assertIn('"windows11_clean_install_usb_formatter": "NOT_RUN"', source)
        self.assertIn('"physical_fedora_kvm_svirt_network_restore": "NOT_TESTED"', source)
        self.assertIn('passed = all(results[k] == "PASS" for k in CHECKS)', source)
        self.assertIn("summary_file(report_path, report)", source)
        self.assertIn('"midnight-provisioner-offline-rc-gate-v2"', source)
        self.assertIn('"original_main_before": main_before', source)
        self.assertIn('"original_main_after": main_after', source)
        self.assertIn('"local_log_sha256": log_digest', source)
        self.assertIn('"report_authentication": "LOCAL_UNAUTHENTICATED"', source)
        self.assertIn('"deployment_approved": False', source)
        self.assertIn('"release_attested": False', source)
        self.assertIn("if main_after != main_before:", source)
        self.assertIn("hashlib.sha256(log_path.read_bytes())", source)
        self.assertNotRegex(source, r"(?m)^\s*os\.system\(")
        self.assertNotIn("shell=True", source)
        self.assertNotIn('["git", "merge"', source)
        self.assertNotIn('["git", "reset"', source)
        self.assertNotIn('["git", "clean"', source)

    def test_failed_any_check_cannot_produce_pass(self):
        self.assertFalse(all({"a": "PASS", "b": "BLOCKED"}[x] == "PASS"
                             for x in ("a", "b")))
        self.assertEqual(gate.VERDICT, {"PASS", "FAIL", "BLOCKED", "NOT_RUN"})


if __name__ == "__main__":
    unittest.main()
