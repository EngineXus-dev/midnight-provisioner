"""Static guardrail regression checks for the opt-in Fedora Docker test runner.

These tests do NOT run Docker or imply live Fedora guest security validation.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTAINERFILE = ROOT / "docker" / "Containerfile.fedora-verification"
RUNNER = ROOT / "scripts" / "Run-Nightglass-Fedora-Checks.ps1"
BOOTSTRAP = ROOT / "scripts" / "Start-Nightglass-Fedora-Checks.ps1"


class FedoraDockerRunnerContractTests(unittest.TestCase):
    def test_image_uses_fedora_and_installs_only_test_tools_without_copying_project(self):
        text = CONTAINERFILE.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^FROM fedora:43$")
        for package in ("python3-pyside6", "libvirt-client", "qemu-img", "bash"):
            self.assertIn(package, text)
        self.assertIn("USER 10001:10001", text)
        self.assertIn("QT_QPA_PLATFORM=offscreen", text)
        self.assertIn('ENTRYPOINT ["python3", "-B", "scripts/verify_local.py"]', text)
        self.assertNotRegex(text, r"(?mi)^\s*(?:COPY|ADD)\s")
        self.assertIn("NIGHTGLASS_GUI_SMOKE=0", text)

    def test_bash_sources_keep_lf_line_endings_in_windows_worktrees(self):
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("*.sh text eol=lf", attributes)
        for path in ("setup-nightglass.sh", "fedora-recovery-smoke.sh"):
            with self.subTest(script=path):
                source = (ROOT / "scripts" / path).read_bytes()
                self.assertNotIn(b"\\r\\n", source)

    def test_runtime_is_rootless_no_network_no_vm_devices_and_read_only(self):
        text = RUNNER.read_text(encoding="utf-8")
        begin = text.index("    $runArgs = @(")
        end = text.index("    if ($Focused)", begin)
        run_arguments = text[begin:end]
        for guard in (
            '"--network", "none"',
            '"--read-only"',
            '"--cap-drop", "ALL"',
            '"--security-opt", "no-new-privileges:true"',
            '"--user", "10001:10001"',
            '"--pids-limit", "160"',
            '"--memory", "2048m"',
            '"--tmpfs", "/tmp:rw,nosuid,nodev,size=512m"',
            "target=/workspace,readonly",
        ):
            self.assertIn(guard, run_arguments, guard)
        for forbidden in ('"--privileged"', '"/dev/kvm"', '"/var/run/docker.sock"'):
            self.assertNotIn(forbidden, run_arguments)
        self.assertIn('$runArgs += "--all"', text)

    def test_git_operations_preserve_original_checkout_and_never_force_merge(self):
        runner = RUNNER.read_text(encoding="utf-8")
        bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
        for text in (runner, bootstrap):
            self.assertIn("git -C", text)
            self.assertIn("fetch --no-tags origin", text)
            self.assertIn("chore/offline-integration-verification", text)
            self.assertIsNone(re.search(
                r"(?im)^\s*&\s*git\s+.*\b(?:reset|clean|merge|rebase|push)\b",
                text,
            ))
        self.assertIn("worktree add --detach", runner)
        self.assertIn("Start-Transcript -LiteralPath $logPath -NoClobber", runner)
        self.assertIn("Nightglass-Fedora-Check-", runner)
        self.assertIn("Set-Content -LiteralPath $runner -Encoding UTF8", bootstrap)
        self.assertNotIn("docker run --privileged", runner)

    def test_missing_cached_image_is_normal_first_run(self):
        runner = RUNNER.read_text(encoding="utf-8")
        # PowerShell 5.1 turns Docker's expected "No such image" stderr
        # into a terminating error under ErrorActionPreference=Stop.
        # A tag-list lookup must instead treat cache misses as normal.
        self.assertIn("docker image ls --format", runner)
        self.assertIn("Docker image cache lookup", runner)
        self.assertIn('$cached = @($imageList | Where-Object', runner)
        self.assertNotIn("docker image inspect $imageTag", runner)
        self.assertIn("if ($ForceImageBuild -or -not $cached)", runner)

    def test_runner_does_not_run_guest_vm_commands(self):
        runner = RUNNER.read_text(encoding="utf-8")
        self.assertNotRegex(runner, r"(?im)^\s*&\s*(?:virsh|virt-install|qemu-system)")
        self.assertIn("Assert-ExitCode -Operation \"Fedora container verification\"", runner)


if __name__ == "__main__":
    unittest.main()
