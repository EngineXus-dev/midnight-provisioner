"""Safety contracts for the opt-in Windows offline verification launcher.

No git fetch, Docker calls, PowerShell execution or Windows host changes occur
from these static tests. Native PS5.1 AST parser runs only on Windows.
"""
from __future__ import annotations

from pathlib import Path
import platform
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "testing" / "Invoke-Nightglass-OfflineChecks.ps1"
GATE = ROOT / "scripts" / "testing" / "Run-Nightglass-Offline-Release-Gate.py"


class WindowsOneCommandOfflineChecksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = LAUNCHER.read_text(encoding="utf-8")
        cls.gate_source = GATE.read_text(encoding="utf-8")

    def test_preview_default_does_not_enter_git_preflight(self):
        s = self.source
        self.assertIn("#requires -Version 5.1", s)
        self.assertIn("[switch]$FetchRefs", s)
        self.assertIn("[switch]$AuditStack", s)
        self.assertIn("[switch]$RunDockerGate", s)
        self.assertIn("if (-not ($FetchRefs -or $AuditStack -or $RunDockerGate))", s)
        self.assertIn("PLAN ONLY: no Git calls, filesystem writes", s)
        self.assertLess(s.index("if (-not ($FetchRefs"),
                        s.index("$git = Get-Command"))
        self.assertLess(s.index("if (-not ($FetchRefs"),
                        s.index("$rootText = @(& $gitExe"))

    def test_docker_requires_explicit_literal_consent(self):
        s = self.source
        self.assertIn("RUN NIGHTGLASS OFFLINE TESTS", s)
        self.assertIn("-cne $requiredConsent", s)
        self.assertIn("($PullPythonImages -or $BuildFedoraImage) -and -not $RunDockerGate", s)
        self.assertIn("Docker image pull/build options require", s)
        self.assertIn("only when ready", s)

    def test_no_original_tree_file_writes_or_checkout(self):
        s = self.source
        self.assertIn("$temp = Join-Path $env:TEMP", s)
        self.assertIn("New-Item -ItemType Directory -Path $temp", s)
        self.assertIn("Set-Content -LiteralPath $destination -Encoding UTF8", s)
        self.assertIn("if ($LASTEXITCODE -ne 0 -or $lines.Count -eq 0)", s)
        self.assertIn("Refusing to overwrite", s)
        self.assertIn("$sha + ':' + $ScriptPath", s)
        self.assertIn("refs/remotes/origin/", s)
        executable = "\n".join(
            line for line in s.splitlines()
            if not line.lstrip().startswith("#")
        )
        for banned in (
            "reset --hard", "git clean -fd", "git checkout", "git pull",
            "Set-ItemProperty", "Remove-Item", "Remove-ItemProperty",
            "Start-Process", "Invoke-RestMethod", "Invoke-WebRequest",
            "Format-Volume", "Initialize-Disk", "Clear-Disk", "bcdedit",
            "manage-bde", "Enable-WindowsOptionalFeature",
        ):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, executable)

    def test_sha_pin_passed_to_test_runner(self):
        s = self.source
        self.assertIn("--expected-commit', $sha", s)
        self.assertIn("--expected-candidate-sha $sha", s)
        self.assertIn("git", s.lower())
        self.assertIn("ExpectedCommit", s)
        self.assertIn("Candidate branch changed", s)
        self.assertIn("Cannot retrieve audited script from pinned Git object", s)
        self.assertIn("expected_sha: str | None = None", self.gate_source)
        self.assertIn("Fetched branch has advanced since approved SHA", self.gate_source)
        self.assertIn("expected_sha=expected_sha", self.gate_source)

    @unittest.skipUnless(platform.system() == "Windows",
                         "Windows PowerShell AST parser is Windows-only")
    def test_native_windows_powershell_51_ast_only(self):
        escaped = str(LAUNCHER).replace("'", "''")
        script = (
            "$a=$null;$e=$null;"
            "[System.Management.Automation.Language.Parser]::ParseFile("
            f"'{escaped}',[ref]$a,[ref]$e)|Out-Null;"
            "if($e.Count){$e|ForEach-Object{[Console]::Error.WriteLine($_.Message)};exit 1};exit 0"
        )
        p = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            text=True, capture_output=True, timeout=20, check=False,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
