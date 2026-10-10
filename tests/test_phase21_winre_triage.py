"""Static Phase21 read-only WinRE diagnostics; no native Windows queries."""
from __future__ import annotations
from pathlib import Path
import platform
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "windows" / "Read-Nightglass-WinRE-Triage.ps1"

class WinREContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="ascii")
        cls.live = re.sub(r"<#[\s\S]*?#>", "", cls.source)
        cls.live = "\n".join(x for x in cls.live.splitlines()
                             if not x.lstrip().startswith("#"))

    def test_native_windows_51_only(self):
        self.assertIn("#requires -Version 5.1", self.source)
        self.assertIn("[PlatformID]::Win32NT", self.source)
        self.assertTrue(SCRIPT.read_bytes().isascii())

    def test_exact_read_only_query_and_bound(self):
        for marker in ("[Environment]::SystemDirectory", "Join-Path $root 'reagentc.exe'",
                       "$tool '/info'", "32768", "UTILITY_MISSING", "$LASTEXITCODE"):
            self.assertIn(marker, self.source)
        self.assertNotIn("$tool '/enable'", self.live)
        self.assertNotIn("$tool '/disable'", self.live)

    def test_diagnostic_reason_codes_are_bounded_and_explicit(self):
        for reason in ("OS_ROOT_UNAVAILABLE","UTILITY_MISSING","UTILITY_NONZERO_EXIT",
                       "UTILITY_INVOCATION_ERROR","UTILITY_OUTPUT_TOO_LARGE",
                       "UTILITY_OUTPUT_EMPTY","UTILITY_OUTPUT_UNRECOGNIZED",
                       "STATUS_ENGLISH_ENABLED","STATUS_ENGLISH_DISABLED"):
            with self.subTest(reason=reason):
                self.assertIn("'" + reason + "'", self.source)
        self.assertIn("HOLD_INDEPENDENT_RECOVERY_EVIDENCE", self.source)
        self.assertIn("process_token_class = $token", self.source)

    def test_never_emit_sensitive_raw_winre_output(self):
        for bad in ("$output | ConvertTo-Json", "$lines | ConvertTo-Json",
                    "raw_reagentc_output_in_report = $true",
                    "reagentc_output = $output", "Write-Host $output"):
            self.assertNotIn(bad, self.live)
        self.assertIn("raw_reagentc_output_in_report = $false", self.source)
        self.assertIn("next_step = $hint", self.source)

    def test_never_change_windows_disk_boot_encryption_or_reboot(self):
        expressions = (
            r"\b(?:Set|Clear|Initialize|Format|Remove|New|Resize)-(?:Disk|Partition|Volume)\b",
            r"\b(?:Enable|Disable|Suspend|Resume|Lock|Unlock|Clear)-BitLocker\b",
            r"\b(?:bcdedit|bootrec|diskpart|manage-bde|mbr2gpt)\b",
            r"\b(?:Set-ItemProperty|New-ItemProperty|Remove-ItemProperty)\b",
            r"\b(?:Set-Content|Out-File|Start-Transcript|Tee-Object|Copy-Item|Remove-Item)\b",
            r"\b(?:Start-Process|Invoke-Expression|Invoke-Command|Restart-Computer)\b",
            r"\b(?:virsh|qemu-system|docker|winget|pip)\b",
        )
        for pattern in expressions:
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.live, "(?i)" + pattern)

    def test_all_install_and_recovery_evidence_flags_false(self):
        flags = ("windows_recovery_boot_proven","recovery_media_proven",
                 "backup_independence_proven","restoration_proven",
                 "bitlocker_recovery_key_proven","ntfs_clean_shutdown_proven",
                 "secure_boot_proven","official_fedora_iso_provenance_proven",
                 "real_fedora_isolation_proven","windows_install_authorized",
                 "fedora_install_authorized","disk_write_authorized","vm_start_authorized")
        for name in flags:
            with self.subTest(name=name):
                self.assertIn(name + " = $false", self.source)
        self.assertIn("schema = 'nightglass.winre-triage.v1'", self.source)

    def test_status_parser_fails_closed_and_rejects_ambiguity(self):
        for fragment in ("$enabled -eq 1 -and $disabled -eq 0",
                         "$disabled -eq 1 -and $enabled -eq 0",
                         "UTILITY_OUTPUT_UNRECOGNIZED",
                         "$observed.status -notin @('UNKNOWN','REVIEW','HOLD')"):
            self.assertIn(fragment, self.source)

    @unittest.skipUnless(platform.system() == "Windows", "Native Windows PowerShell 5.1 AST required")
    def test_native_powershell_parse_only(self):
        path = str(SCRIPT).replace("'", "''")
        command = ("$t=$null;$e=$null;"
                   "[System.Management.Automation.Language.Parser]::ParseFile("
                   f"'{path}',[ref]$t,[ref]$e)|Out-Null;"
                   "if($e.Count){$e|ForEach-Object{"
                   "[Console]::Error.WriteLine($_.Message)};exit 1};exit 0")
        cp = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                             "-ExecutionPolicy","Bypass","-Command",command],
                            capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)

if __name__ == "__main__":
    unittest.main()
