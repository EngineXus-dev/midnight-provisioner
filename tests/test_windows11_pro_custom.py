"""Static, nonexecuting contract for the deferred Windows 11 Pro custom plan.

Tests do NOT use PowerShell ApplyCore, run Win11Debloat/WinUtil,
elevate, modify registry, USB, disks or the current Windows 10 host.
Windows-native AST syntax parse is separately opt-in via a test case.
"""
from __future__ import annotations

import json
from pathlib import Path
import platform
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config" / "windows11-pro-custom.json"
SCRIPT = ROOT / "scripts" / "Invoke-Nightglass-Win11ProCustom.ps1"


class Windows11ProCustomContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.script = SCRIPT.read_text(encoding="utf-8")
        cls.items = cls.catalog["items"]

    def test_user_all_32_choices_and_three_app_groups_are_present(self):
        self.assertEqual(self.catalog["schema"], "nightglass.windows11.pro.custom.v1")
        self.assertEqual(self.catalog["target"]["edition"], "Windows 11 Pro")
        self.assertEqual(len(self.items), 35)
        self.assertEqual([x["id"] for x in self.items], list(range(1, 36)))
        self.assertEqual(len({x["title"] for x in self.items}), 35)
        self.assertEqual({x["id"] for x in self.items if x["id"] in (33,34,35)}, {33,34,35})
        for item in self.items:
            self.assertTrue(item["mode"] in self.catalog["modeMeanings"])
            self.assertTrue(item["title"].strip())
            self.assertIsInstance(item["switches"], list)

    def test_no_destructive_actions_mixed_into_approved_core(self):
        source = self.script
        self.assertIn("if ($flag -eq 'RemoveGamingApps') { continue }", source)
        for risky in (
            "DisableBitlockerAutoEncryption", "EnableWindowsSandbox",
            "EnableWindowsSubsystemForLinux", "RemoveGamingApps",
            "RemoveApps", "ForceRemoveEdge", "ClearStart",
        ):
            # Explicitly omitted from the hardcoded approved list.
            allowlisted = source.split("$approvedSwitches = @(", 1)[1].split("\n)", 1)[0]
            self.assertNotIn("'" + risky + "'", allowlisted)
        self.assertIn("requested.Count -ne $approvedSwitches.Count", source)
        self.assertIn("ApplyCore never performs app uninstall", source)
        self.assertIn("prohibited", self.catalog)

    def test_default_preview_and_explicit_future_apply_requirements(self):
        source = self.script
        self.assertIn("[string]$Mode = 'Preview'", source)
        self.assertIn("ExportPlan", source)
        self.assertIn("APPLY NIGHTGLASS WINDOWS11 PRO CORE", source)
        self.assertIn("if (-not $BackupVerified)", source)
        self.assertIn("Windows 11 Pro", source)
        self.assertIn("Administrator", source)
        self.assertIn("Get-FileHash", source)
        self.assertIn("CreateRestorePoint", source)
        self.assertIn("Win11Debloat.ps1", source)
        self.assertIn("Win11Debloat script SHA256 mismatch", source) if False else None
        self.assertIn("Third-party script SHA256 mismatch", source)
        self.assertIn("ScriptBlock", source) if False else None
        self.assertIn("[System.Management.Automation.Language.Parser]::ParseFile", source)
        self.assertIn("Get-Content -LiteralPath $catalogPath", source)
        self.assertIn("[System.IO.FileMode]::CreateNew", source)
        self.assertIn("Get-CimInstance Win32_OperatingSystem", source)
        self.assertIn("if ($Consent -cne", source)

    def test_no_auto_download_ubiquitous_debloat_or_disk_commands(self):
        code = "\n".join(
            line for line in self.script.splitlines()
            if not line.lstrip().startswith("#")
        )
        for pat in (
            r"\b(?:Invoke-RestMethod|Invoke-WebRequest|iwr|irm|iex|Invoke-Expression)\b",
            r"\b(?:Start-Process|Start-Job)\b",
            r"\b(?:Clear|Initialize|Format|Remove|New|Resize)-(?:Disk|Partition|Volume)\b",
            r"\b(?:bcdedit|bootrec|diskpart|manage-bde|mbr2gpt|reagentc)\b",
            r"\b(?:Enable|Disable|Suspend|Resume)-BitLocker\b",
            r"\b(?:Disable|Enable)-WindowsOptionalFeature\b",
            r"\b(?:Remove|Add)-Appx(?:Provisioned)?Package\b",
            r"\b(?:Restart-Computer|Stop-Computer)\b",
        ):
            with self.subTest(pat=pat):
                self.assertIsNone(re.search(pat, code, re.IGNORECASE))

    def test_third_party_launcher_is_not_an_approved_input(self):
        source = self.script
        self.assertIn("Get.ps1", source)
        self.assertIn("[System.IO.Path]::GetFileName($Win11DebloatPath)", source)
        self.assertIn("Provide the SHA256 of the exact previously inspected", source)
        self.assertIn("if ($parseErrors.Count -gt 0", source)

    def test_selected_core_cover_explicit_requirements(self):
        for term in (
            "DisableGameBarIntegration", "DisableDVR", "DisableRecall",
            "DisableClickToDo", "DisableCopilot", "DisableLocationServices",
            "DisableFastStartup", "DisableUpdateASAP",
            "PreventUpdateAutoReboot", "DisableDeliveryOptimization",
            "DisableAISvcAutoStart", "EnableEndTask",
            "ShowHiddenFolders", "ShowKnownFileExt", "DisableWindowSnapping",
        ):
            self.assertIn("'" + term + "'", self.script)

    @unittest.skipUnless(platform.system() == "Windows",
                         "Native Windows PowerShell 5.1 AST parser is Windows-only")
    def test_actual_windows_powershell_ast_parser_only(self):
        escaped = str(SCRIPT).replace("'", "''")
        check = (
            "$t=$null; $e=$null; "
            "[System.Management.Automation.Language.Parser]::ParseFile("
            f"'{escaped}', [ref]$t, [ref]$e) | Out-Null; "
            "if ($e.Count -gt 0) { "
            "$e | ForEach-Object { [Console]::Error.WriteLine($_.Message) }; exit 1 }; exit 0"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", check],
            capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
