"""Static safety contract for the Windows dual-boot inventory tool.

No Windows storage, firmware, encryption or system commands are invoked.
The actual PowerShell parser and Windows cmdlet calls must be tested on
Windows before treating this as a validated native hardware report.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "scripts" / "Review-Windows-DualBoot.ps1"


class WindowsDualBootReviewSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = REVIEW.read_text(encoding="utf-8")

    def test_readonly_queries_include_key_dualboot_risks(self):
        for item in (
            "Win32_OperatingSystem",
            "Win32_ComputerSystem",
            "Win32_Processor",
            "Get-ComputerInfo",
            "Confirm-SecureBootUEFI",
            "HiberbootEnabled",
            "Get-BitLockerVolume",
            "ProtectionStatus",
            "VolumeStatus",
            "Get-Disk",
            "Get-Partition",
            "Get-Volume",
            "PartitionStyle",
            "SizeRemaining",
            "VirtualizationFirmwareEnabled",
            "SecondLevelAddressTranslationExtensions",
        ):
            with self.subTest(item=item):
                self.assertIn(item, self.source)

    def test_never_uses_write_commands_or_boot_encryption_mutations(self):
        code_lines = "\n".join(
            line for line in self.source.splitlines()
            if not line.lstrip().startswith("#")
        )
        for forbidden in (
            r"\b(?:Set|Clear|Initialize|Format|Remove|New|Resize)-(?:Disk|Partition|Volume)\b",
            r"\b(?:Enable|Disable|Suspend|Resume|Lock|Unlock|Clear)-BitLocker\b",
            r"\b(?:Set|Repair)-(?:Computer|SecureBoot|Disk)\b",
            r"\b(?:bcdedit|bootrec|diskpart|manage-bde|mountvol|reagentc|mbr2gpt)\b",
            r"\b(?:Start|Stop|Restart)-Computer\b",
            r"\b(?:Invoke-Expression|Invoke-Command|Start-Process|iex)\b",
            r"\b(?:Set-Content|Add-Content|Out-File|Export-Clixml|Start-Transcript)\b",
            r"\b(?:Remove-Item|New-Item|Move-Item|Copy-Item)\b",
        ):
            with self.subTest(pattern=forbidden):
                self.assertNotRegex(code_lines, r"(?i)" + forbidden)

    def test_never_reads_bitlocker_key_material(self):
        for key in (
            "KeyProtector",
            "RecoveryPassword",
            "Get-BitLockerKeyProtector",
            "PasswordProtector",
        ):
            # The words may appear in warnings/comments, but never as
            # an object property access or command invocation.
            self.assertNotRegex(self.source,
                                r"(?i)\." + re.escape(key) + r"\b")
        self.assertIn("Never enumerate", self.source)
        self.assertIn("Do NOT paste a BitLocker recovery key", self.source)

    def test_no_automatic_install_approval_or_disk_selection(self):
        self.assertIn("NO INSTALL/SHRINK/FORMAT/EFI/BOOTLOADER CHANGES AUTHORIZED.", self.source)
        self.assertIn("Filesystem free space is NOT unallocated", self.source)
        self.assertIn("full Windows/disk backup", self.source)
        self.assertIn("Recovery", self.source)
        self.assertIn("live USB", self.source)
        self.assertIn("PENDING", self.source)
        self.assertNotIn("Read-Host", self.source)
        self.assertNotIn("ShouldProcess", self.source)

    def test_os_drive_normalization_never_uses_ambiguous_trimend(self):
        # The target must be derived from the Windows SystemDrive letter,
        # never an arbitrary disk/partition number or a write operation.
        self.assertIn("$osLetter = [string]$env:SystemDrive", self.source)
        self.assertIn("$osLetter = $osLetter.Substring(0, 1)", self.source)
        self.assertIn("Get-Partition -DriveLetter $osLetter", self.source)
        self.assertNotIn(".TrimEnd(", self.source)

    def test_checks_native_windows_and_no_reboot_or_secret_report(self):
        self.assertIn("PlatformID]::Win32NT", self.source)
        self.assertIn("Get-CimInstance", self.source)
        self.assertIn("Get-Disk -ErrorAction Stop", self.source)
        self.assertIn("created no report files", self.source)
        self.assertNotIn('Start-Transcript', self.source)
        self.assertNotIn("System.Management.Automation.PSCredential", self.source)


if __name__ == "__main__":
    unittest.main()
