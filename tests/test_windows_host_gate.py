"""Phase 18 Windows host observation safety contract (NO hardware queries).

The actual report must be run on native Windows; these static tests ensure
a future edit cannot quietly add installers, disk operations or approval flags.
"""
from __future__ import annotations

from pathlib import Path
import platform
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "scripts" / "Read-Nightglass-Windows-HostGate.ps1"


class WindowsHostGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = REVIEW.read_text(encoding="utf-8")
        # Ignore comments, while still inspecting active PowerShell source.
        cls.code = re.sub(r"<#[\s\S]*?#>", "", cls.script)
        cls.code = "\n".join(line for line in cls.code.splitlines()
                             if not line.lstrip().startswith("#"))

    def test_review_is_explicitly_native_windows_and_read_only(self):
        for fragment in ("#requires -Version 5.1",
                         "[PlatformID]::Win32NT", "Get-CimInstance",
                         "Win32_OperatingSystem", "Get-ComputerInfo",
                         "Confirm-SecureBootUEFI", "HiberbootEnabled",
                         "Get-BitLockerVolume", "Get-Partition",
                         "Get-Disk", "Win32_Processor",
                         "VirtualizationFirmwareEnabled"):
            self.assertIn(fragment, self.script)

    def test_never_operates_on_disks_boot_media_or_vm(self):
        for pattern in (
            r"(?i)\b(?:Set|Clear|Initialize|Format|Remove|New|Resize)-(?:Disk|Partition|Volume)\b",
            r"(?i)\b(?:Enable|Disable|Suspend|Resume|Lock|Unlock|Clear)-BitLocker\b",
            r"(?i)\b(?:bcdedit|bootrec|diskpart|manage-bde|mountvol|reagentc|mbr2gpt)\b",
            r"(?i)\b(?:virsh|virt-install|qemu-system|docker|wsl|Invoke-WebRequest|Invoke-RestMethod)\b",
            r"(?i)\b(?:Start|Stop|Restart)-Computer\b",
            r"(?i)\b(?:Start-Process|Invoke-Expression|Invoke-Command|iex)\b",
            r"(?i)\b(?:Set-Content|Add-Content|Out-File|Export-Csv|Start-Transcript|Tee-Object)\b",
            r"(?i)\b(?:Remove-Item|New-Item|Move-Item|Copy-Item|WriteAllText|CreateNew)\b",
            r"(?i)\b(?:git|pip|dnf|choco|winget)\s+(?:install|pull|merge|reset|push|clean)\b",
        ):
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.code, pattern)

    def test_never_collects_sensitive_unique_host_identifiers(self):
        # Never emit raw CIM objects, device IDs, keys, hostnames or paths.
        for pattern in (
            r"(?i)\.KeyProtector\b",
            r"(?i)\.RecoveryPassword\b",
            r"(?i)\.SerialNumber\b",
            r"(?i)\.DeviceID\b",
            r"(?i)\.UniqueId\b",
            r"(?i)\.MachineGuid\b",
            r"(?i)\bGet-LocalUser\b",
            r"(?i)\bGet-ChildItem\b",
            r"(?i)\bFormat-List\s+\*",
        ):
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.code, pattern)
        for name in ("KeyProtector", "RecoveryPassword", "Get-BitLockerKeyProtector"):
            self.assertNotIn(f".{name}", self.script)
        self.assertIn("contains_serials_secrets_or_raw_disk_paths = $false", self.script)

    def test_installation_and_backup_cannot_be_certified(self):
        for field in ("full_backup_verified", "restore_verified",
                      "bitlocker_recovery_key_verified",
                      "windows_install_authorized",
                      "fedora_install_authorized",
                      "disk_partition_write_authorized",
                      "real_fedora_host_isolation_verified"):
            with self.subTest(field=field):
                self.assertIn(f"{field} = $false", self.script)
        self.assertIn("HOLD_MANUAL_DEPLOYMENT_APPROVAL", self.script)
        self.assertIn("manual_requirements = $manual", self.script)
        self.assertIn("schema = 'nightglass.windows-host-observation.v1'", self.script)

    def test_unknown_and_failure_states_fail_closed(self):
        self.assertIn("@('OBSERVED', 'REVIEW', 'HOLD', 'UNKNOWN')", self.script)
        self.assertIn("if ($disk.Count -ne 1)", self.script)
        self.assertIn("if ($partition.Count -ne 1)", self.script)
        for check in ("windows_servicing", "firmware", "secure_boot",
                      "fast_startup", "volume_encryption", "ram_budget",
                      "virtualization_firmware", "os_disk_layout", "partition_map"):
            with self.subTest(check=check):
                self.assertIn(f"'{check}'", self.script)
        self.assertIn("Get-Disk -Number $partition[0].DiskNumber", self.script)
        self.assertNotIn("Get-Disk |", self.script)

    def test_windows10_extended_support_is_never_guessed(self):
        self.assertIn("2025-10-14", self.script)
        self.assertIn("Check exact edition, lifecycle and verified security servicing/ESU", self.script)
        self.assertIn("do not infer ESU enrollment", self.script)

    def test_source_is_ascii_to_parse_under_windows_powershell_51(self):
        self.assertTrue(REVIEW.read_bytes().isascii())

    @unittest.skipUnless(platform.system() == "Windows",
                         "Native PowerShell 5.1 parser requires Windows")
    def test_native_windows_powershell_ast_parse_without_execution(self):
        escaped = str(REVIEW).replace("'", "''")
        script = ("$tokens=$null;$errors=$null;"
                  "[System.Management.Automation.Language.Parser]::ParseFile("
                  f"'{escaped}',[ref]$tokens,[ref]$errors)|Out-Null;"
                  "if($errors.Count){$errors|ForEach-Object{"
                  "[Console]::Error.WriteLine($_.Message)};exit 1};exit 0")
        result = subprocess.run(["powershell.exe", "-NoProfile",
                                 "-NonInteractive", "-Command", script],
                                capture_output=True, text=True, check=False, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
