"""Windows PowerShell 5.1 forward-compatibility tripwires.

Never executes a source PowerShell file. Native checks only parse AST syntax.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import platform
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCANNER = SCRIPTS / "check_powershell_guardrails.py"
CHECKED = SCRIPTS / "Run-Nightglass-GUI-Smoke.ps1"
ARCHIVER = SCRIPTS / "Archive-Nightglass-TestResults.ps1"

spec = importlib.util.spec_from_file_location("nightglass_ps_guardrails", SCANNER)
scanner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(scanner)


class PowerShellGuardrailTests(unittest.TestCase):
    def test_automatic_variables_cannot_be_accidentally_assigned(self):
        for case in ("$home = 'temp'", "$HOME = 'temp'",
                     "$Host += 'x'", "$PID++", "foreach ($Pwd in 1..3) {}",
                     "Set-Variable -Name HOME -Value x", "[string]$HOME = 'x'"):
            with self.subTest(case=case):
                self.assertTrue(scanner.candidates(case), case)
        for good in ("$testHome = 'temp'", "$env:HOME = 'temp'",
                     "$HomeDirectory = 'temp'", "# $HOME = 'comment'",
                     "Write-Output $HOME", 'Write-Host "$HOME"'):
            with self.subTest(good=good):
                self.assertEqual(scanner.candidates(good), [], good)

    def test_repo_scripts_avoid_reserved_local_variables(self):
        paths = sorted(SCRIPTS.rglob("*.ps1"))
        self.assertTrue(paths)
        self.assertEqual(scanner.scan(paths), [])

    def test_gui_runner_never_silently_skips_or_installs(self):
        source = CHECKED.read_text(encoding="utf-8")
        for token in ("QT_QPA_PLATFORM", "offscreen", "NIGHTGLASS_GUI_SMOKE",
                      "ExpectedSha", "TimeoutSeconds", "FAILED_NO_EXECUTED_GUI_TESTS",
                      "Archive-Nightglass-TestResults.ps1", "worktree add --detach",
                      "throw 'GUI smoke failed or produced no executed tests'"):
            self.assertIn(token, source)
        for forbidden in ("docker run", "virsh start", "virt-install",
                          "Start-Process setup.exe", "git reset --hard", "git clean -fd"):
            self.assertNotIn(forbidden, source)

    def test_archive_retains_original_zip_and_hashes(self):
        source = ARCHIVER.read_text(encoding="utf-8")
        for token in ("SHA256", "Get-FileHash", "manifest.txt", "summary.csv",
                      "New-Item -ItemType Directory", "original-results.zip"):
            self.assertIn(token, source)

    @unittest.skipUnless(platform.system() == "Windows",
                         "Native Windows PowerShell 5.1 AST parser is Windows-only")
    def test_native_windows_powershell_parse_all_repo_scripts(self):
        for script in sorted(SCRIPTS.rglob("*.ps1")):
            with self.subTest(script=str(script.relative_to(ROOT))):
                escaped = str(script).replace("'", "''")
                command = (
                    "$tokens=$null;$errors=$null;"
                    "[System.Management.Automation.Language.Parser]::ParseFile("
                    f"'{escaped}',[ref]$tokens,[ref]$errors)|Out-Null;"
                    "if($errors.Count){$errors|ForEach-Object{[Console]::Error.WriteLine($_.Message)};exit 1};exit 0"
                )
                result = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                    capture_output=True, text=True, check=False, timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
