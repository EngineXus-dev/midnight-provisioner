"""Midnight Provisioner Phase 20 source-only safety contract.

No Windows recovery utility is executed by this Python test. The host observer
is invoked only by an explicitly pinned operator run, after this gate passes.
"""
from __future__ import annotations

from pathlib import Path
import platform
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "windows" / "Read-Midnight-Provisioner-Recovery-Posture.ps1"


class WindowsRecoveryPostureContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="ascii")
        # Strip comments for executable-source policy checks.
        cls.live = re.sub(r"<#[\s\S]*?#>", "", cls.source)
        cls.live = "\n".join(line for line in cls.live.splitlines()
                             if not line.lstrip().startswith("#"))

    def test_exact_readonly_native_commands_and_no_elevation(self):
        for snippet in ("#requires -Version 5.1", "[PlatformID]::Win32NT",
                        "System32\\reagentc.exe", "System32\\powercfg.exe",
                        "-Option '/info'", "-Option '/a'",
                        "-Name HiberbootEnabled", "READ_ONLY_NON_ELEVATED_WINDOWS"):
            self.assertIn(snippet, self.source)
        for bad in ("-Verb RunAs", "Start-Process", "Invoke-Expression",
                    "Invoke-Command", "Set-ExecutionPolicy", "Enable-PSRemoting",
                    "WriteAllBytes", "Format-Volume", "New-Partition"):
            self.assertNotIn(bad, self.live)

    def test_no_storage_firmware_encryption_or_power_mutation(self):
        expressions = (
            r"\b(?:Set|Clear|Initialize|Format|Remove|New|Resize)-(?:Disk|Partition|Volume)\b",
            r"\b(?:Enable|Disable|Suspend|Resume|Lock|Unlock|Clear)-BitLocker\b",
            r"\b(?:bcdedit|bootrec|diskpart|manage-bde|mountvol|mbr2gpt)\b",
            r"\b(?:Set-ItemProperty|New-ItemProperty|Remove-ItemProperty)\b",
            r"\b(?:Set-Content|Out-File|Export-Csv|Start-Transcript|Tee-Object)\b",
            r"\b(?:New-Item|Remove-Item|Move-Item|Copy-Item|Format-Table)\b",
            r"\b(?:powercfg|reagentc)\.exe\s*/(?:hibernate|h|enable|disable|setreimage|boottore)\b",
            r"\b(?:virsh|virt-install|qemu-system|docker|wsl|pip|winget)\b",
        )
        for regex in expressions:
            with self.subTest(pattern=regex):
                self.assertNotRegex(self.live, "(?i)" + regex)
        self.assertIn("Get-ItemProperty -LiteralPath", self.source)

    def test_command_output_is_never_reflected_verbatim(self):
        self.assertIn("if ($joined.Length -gt 32768)", self.source)
        self.assertIn("if ($statusCode -ne 0) { return '' }", self.source)
        self.assertIn("$joined = [string]($lines -join [Environment]::NewLine)", self.source)
        self.assertNotIn("$recoveryRaw |", self.live)
        self.assertNotIn("$powerRaw |", self.live)
        self.assertNotIn("evidence = $recoveryRaw", self.live)
        self.assertNotIn("evidence = $powerRaw", self.live)
        self.assertIn("raw_command_output_in_report = $false", self.source)

    def test_fail_closed_on_unrecognized_or_localized_output(self):
        for token in ("'windows_re' 'UNKNOWN'", "'hibernate_capability' 'UNKNOWN'",
                      "'fast_startup' 'UNKNOWN'", "'windows_re' 'HOLD'",
                      "'fast_startup' 'HOLD'", "'recovery_media' 'UNKNOWN'",
                      "'secure_boot_confirmation' 'UNKNOWN'",
                      "'encryption_key_custody' 'UNKNOWN'"):
            self.assertIn(token, self.source)
        self.assertNotRegex(self.live, r"(?i)\b(?:Read-Host|ShouldProcess)\b")

    def test_no_private_identifiers_or_secrets_captured(self):
        for key in ("KeyProtector", "RecoveryPassword", "Get-BitLockerKeyProtector",
                    ".SerialNumber", ".DeviceID", ".UniqueId", ".MachineGuid",
                    "Win32_Tpm", "Get-ChildItem", "Get-CimInstance",
                    "Get-Disk", "Get-Partition", "Get-Volume"):
            with self.subTest(value=key):
                self.assertNotIn(key, self.live)
        self.assertNotIn("$_ | ConvertTo-Json", self.live)
        self.assertNotIn("$recoveryRaw | ConvertTo-Json", self.live)

    def test_permanent_install_and_backup_false_not_autoproven(self):
        for key in ("windows_recovery_boot_verified", "full_backup_verified",
                    "controlled_restore_verified", "encryption_recovery_key_verified",
                    "ntfs_clean_shutdown_verified", "secure_boot_independently_verified",
                    "official_fedora_iso_provenance_verified",
                    "physical_fedora_isolation_verified", "windows_install_authorized",
                    "fedora_install_authorized", "disk_partition_write_authorized",
                    "vm_start_authorized"):
            with self.subTest(key=key):
                self.assertIn(f"{key} = $false", self.source)
        self.assertIn("status = 'HOLD_MANUAL_RECOVERY_AND_DEPLOYMENT'", self.source)
        self.assertIn("schema = 'midnight-provisioner.windows-recovery-posture.v1'", self.source)

    def test_no_reserved_args_parameter_or_windows_powershell_bom_issue(self):
        self.assertTrue(SCRIPT.read_bytes().isascii())
        self.assertNotRegex(self.live, r"(?i)\bparam\s*\(\s*\[[^\]]+\]\s*\$(?:args|home|host|pid|error)\b")
        self.assertNotRegex(self.live, r"(?i)^\s*\$(?:args|home|host|pid|error)\s*=",)

    @unittest.skipUnless(platform.system() == "Windows",
                         "Native Windows PowerShell 5.1 AST parser required")
    def test_native_powershell_parser_only_no_execution(self):
        path = str(SCRIPT).replace("'", "''")
        command = ("$t=$null;$e=$null;"
                   "[System.Management.Automation.Language.Parser]::ParseFile("
                   f"'{path}',[ref]$t,[ref]$e)|Out-Null;"
                   "if($e.Count){$e|ForEach-Object{"
                   "[Console]::Error.WriteLine($_.Message)};exit 1};exit 0")
        cp = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                             "-ExecutionPolicy", "Bypass", "-Command", command],
                            capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(cp.returncode, 0, cp.stderr + cp.stdout)


if __name__ == "__main__":
    unittest.main()
