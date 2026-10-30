"""Static contract for optional Windows 11 Lite build and preference preview.

Does not execute PowerShell/NTLite or change Windows/USB/ISO files.
Native Windows PowerShell parser, Apply, and Undo still require
separate host acceptance before any production use.
"""
from pathlib import Path
import platform
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "windows" / "Set-Midnight-Provisioner-Windows11-Preferences.ps1"
PROFILE = ROOT / "docs" / "WINDOWS11_LITE_IMAGE_PROFILE.md"


class SafeWindowsLiteProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.guide = PROFILE.read_text(encoding="utf-8")

    def test_only_preapproved_hkcu_user_preferences(self):
        source = self.source
        names = (
            "HideFileExt", "TaskbarDa", "ShowTaskViewButton",
            "SoftLandingEnabled", "SystemPaneSuggestionsEnabled",
            "SubscribedContent-338388Enabled", "AppsUseLightTheme",
            "SystemUsesLightTheme",
        )
        for name in names:
            self.assertIn("Name='" + name + "'", source)
        self.assertEqual(source.count("[pscustomobject]@{ Path='HKCU:"), len(names))
        self.assertNotIn("HKLM:", source)
        self.assertNotIn("HKCR:", source)
        self.assertNotIn("HKU:", source)

    def test_preview_is_default_and_changes_require_literal_consent(self):
        self.assertIn("[string]$Mode = 'Preview'", self.source)
        self.assertIn("if ($Mode -eq 'Preview')", self.source)
        self.assertIn("PREVIEW ONLY: no file or registry writes.", self.source)
        self.assertIn("-cne 'APPLY MIDNIGHT_PROVISIONER USER PREFERENCES'", self.source)
        self.assertIn("-cne 'UNDO MIDNIGHT_PROVISIONER USER PREFERENCES'", self.source)
        self.assertIn("Assert-Windows11", self.source)
        self.assertIn("Windows 11 not detected.", self.source)
        self.assertIn("CreateNew", self.source)
        self.assertIn("PreferenceSnapshots", self.source)

    def test_undo_does_not_target_arbitrary_registry_keys(self):
        for text in (
            "Snapshot key count does not match the safe allowlist.",
            "Snapshot does not match the fixed safe preference allowlist.",
            "modified since Apply",
            "Unrecognized snapshot version.",
            "Remove-ItemProperty -Path $item.Path -Name $item.Name",
        ):
            self.assertIn(text, self.source)

    def test_no_services_remote_scripts_security_or_boot_mutations(self):
        source = "\n".join(
            line for line in self.source.splitlines()
            if not line.lstrip().startswith("#")
        )
        for bad in (
            r"\b(?:iwr|irm|Invoke-WebRequest|Invoke-RestMethod|iex|Invoke-Expression)\b",
            r"\b(?:Start|Stop|Set|Remove)-Service\b",
            r"\b(?:Disable|Enable)-Windows(?:Optional)?Feature\b",
            r"\b(?:Remove|Add)-Appx(?:Provisioned)?Package\b",
            r"\b(?:Clear|Initialize|Format|Remove|New|Resize)-(?:Disk|Partition|Volume)\b",
            r"\b(?:bcdedit|bootrec|diskpart|manage-bde|reagentc|mountvol)\b",
            r"\b(?:Enable|Disable|Suspend|Resume)-BitLocker\b",
            r"\b(?:Set-MpPreference|Remove-MpPreference|netsh|Set-NetFirewallProfile)\b",
            r"\b(?:Restart-Computer|Stop-Computer|Start-Process)\b",
            r"\b(?:DISM|sfc|setup\.exe|rufus|ventoy)\b",
        ):
            with self.subTest(pattern=bad):
                self.assertNotRegex(source, re.compile(bad, re.IGNORECASE))

    def test_guide_respects_reported_pro_key_and_windows_security(self):
        for text in (
            "Windows 11 26H2",
            "Windows 10 Home",
            "Edition decision updated",
            "Windows Pro\nactivation key",
            "Windows 10 Home",
            "Microsoft Defender",
            "Windows Update",
            "Windows Recovery Environment",
            "WSL2",
            "WebView2",
            "TPM",
            "install.esd",
            "Home digital entitlement",
            "3 GB",
            "NOT Midnight Provisioner acceptance targets",
            "does NOT authorise",
        ):
            self.assertIn(text.casefold(), self.guide.casefold())

    @unittest.skipUnless(platform.system() == "Windows",
                         "Real Windows PowerShell 5.1 AST is Windows-only")
    def test_real_windows_powershell_parse_only(self):
        p = str(SCRIPT).replace("'", "''")
        cmd = (
            "$tokens=$null; $errors=$null; "
            "[System.Management.Automation.Language.Parser]::ParseFile("
            f"'{p}', [ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors.Count -ne 0) { "
            "$errors | ForEach-Object { [Console]::Error.WriteLine($_.Message) }; exit 1 }; exit 0"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", cmd],
            capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
