#requires -Version 5.1
<#
.SYNOPSIS
  Nightglass Windows-to-Fedora deployment observation. READ ONLY.
.DESCRIPTION
  Displays sanitized hardware/boot/disk/BitLocker/Fast-Startup state and
  clearly separates observed facts from human backup/install approvals.
  Does NOT require administrator privileges or create reports by default.
  Does NOT change any partition, boot entry, firmware setting, BitLocker
  protection, encryption, hibernation setting, recovery key or VM.
.NOTES
  Manual physical-disk review, independent backups and Windows recovery
  are mandatory before any later Fedora USB installation.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    Write-Error 'This read-only hardware inspection requires native Windows, not Linux/WSL/containers.'
    exit 2
}

function Say {
    param([string]$Label, [string]$Value)
    Write-Host ("{0,-31} {1}" -f $Label, $Value)
}
function Gib {
    param([object]$Bytes)
    if ($null -eq $Bytes) { return 'UNKNOWN' }
    return ("{0:N1} GiB" -f ([double]$Bytes / 1GB))
}
function Unknown {
    param([string]$What)
    Say $What 'UNKNOWN — manual verification required'
}
function BootMode {
    try {
        $value = Get-ComputerInfo -Property BiosFirmwareType -ErrorAction Stop
        $mode = [string]$value.BiosFirmwareType
        if ($mode -match '^(Uefi|BIOS)$') { return $mode }
    } catch {}
    return 'UNKNOWN'
}

Write-Host 'NIGHTGLASS — WINDOWS 10/11 + FEDORA READINESS OBSERVATION' -ForegroundColor Cyan
Write-Host 'QUERY ONLY: no sudo/admin, partition changes, bootloader edits, BitLocker/TPM changes or output files.'
Write-Host 'This script cannot authorize a Windows upgrade or Fedora installation: backup/keys/eligibility/live-USB review remain mandatory.'
Write-Host ''

$windows = $null
try {
    $windows = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
    Say 'Windows version' ("{0} | {1}" -f $windows.Caption, $windows.Version)
} catch { Unknown 'Windows version' }
if ($null -eq $windows) {
    Write-Host 'Operating system identity could not be confirmed; deployment remains on HOLD.'
}

$computer = $null
try {
    $computer = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
    Say 'Installed RAM' (Gib $computer.TotalPhysicalMemory)
    if ([double]$computer.TotalPhysicalMemory -lt 11GB) {
        Say 'Virtualization guidance' 'LOW MEMORY: plan ONE small VM at a time; no concurrent labs'
    } else {
        Say 'Virtualization guidance' 'RAM budget must still be verified on Fedora'
    }
} catch { Unknown 'Installed RAM' }

try {
    $cpu = @(Get-CimInstance -ClassName Win32_Processor -ErrorAction Stop)
    if ($cpu.Count -gt 0) {
        $logicalCores = ($cpu | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
        Say 'Logical CPU cores' ([string]$logicalCores)
        # The CPU model is for a human check against Microsoft's current supported list.
        # It is not sufficient to certify Windows 11 eligibility.
        Say 'CPU model (advisory)' ([string]$cpu[0].Name)
        foreach ($prop in @('VMMonitorModeExtensions', 'VirtualizationFirmwareEnabled',
                             'SecondLevelAddressTranslationExtensions')) {
            $vals = @($cpu | ForEach-Object { $_.$prop } | Select-Object -Unique)
            $result = if ($vals.Count -eq 1 -and $null -ne $vals[0]) { [string]$vals[0] } else { 'UNKNOWN' }
            Say ("CPU " + $prop) $result
        }
        Write-Host 'CPU capability flags are advisory, NOT proof that Fedora /dev/kvm will work.'
    } else { Unknown 'CPU capabilities' }
} catch { Unknown 'CPU capabilities' }

$firmware = BootMode
Say 'Windows boot firmware' $firmware
if ($firmware -ne 'Uefi') {
    Write-Host 'HOLD: UEFI was not confirmed. Do NOT assume GPT/UEFI partition instructions apply.'
}
try {
    $secure = Confirm-SecureBootUEFI -ErrorAction Stop
    Say 'Secure Boot observed' ([string][bool]$secure)
} catch { Unknown 'Secure Boot observed' }
Write-Host 'Secure Boot status often requires an elevated query; this reviewer will not elevate.'

# Windows 11 upgrade prerequisite: TPM 2.0. Do not print the full Get-Tpm
# object; it can contain TPM ownership/authorization-related properties.
# We read and display only non-secret presence/readiness/version fields.
$tpmPresent = 'UNKNOWN'
$tpmReady = 'UNKNOWN'
$tpmSpec = 'UNKNOWN'
if (Get-Command -Name Get-Tpm -ErrorAction SilentlyContinue) {
    try {
        $tpm = Get-Tpm -ErrorAction Stop
        if ($null -ne $tpm.TpmPresent) { $tpmPresent = [string][bool]$tpm.TpmPresent }
        if ($null -ne $tpm.TpmReady) { $tpmReady = [string][bool]$tpm.TpmReady }
    } catch {}
}
try {
    $tpmCim = Get-CimInstance -Namespace 'root\CIMV2\Security\MicrosoftTpm' -ClassName Win32_Tpm -ErrorAction Stop
    $rawSpec = [string]$tpmCim.SpecVersion
    # Return only a bounded spec marker; never dump a complete CIM object.
    if ($rawSpec -match '(^|[,; ])2\.0([,; ]|$)') { $tpmSpec = '2.0 reported' }
    elseif ($rawSpec -match '(^|[,; ])1\.2([,; ]|$)') { $tpmSpec = '1.2 reported' }
} catch {}
Say 'TPM present (advisory)' $tpmPresent
Say 'TPM ready (advisory)' $tpmReady
Say 'TPM spec (advisory)' $tpmSpec
Write-Host 'Windows 11 eligibility is NOT established: confirm using official PC Health Check / Windows Update.'
Write-Host 'Windows upgrade MUST remain separate from Fedora partition/EFI work.'

$fastStartup = 'UNKNOWN'
try {
    $key = Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name HiberbootEnabled -ErrorAction Stop
    if ($key.HiberbootEnabled -eq 1) { $fastStartup = 'ENABLED' }
    elseif ($key.HiberbootEnabled -eq 0) { $fastStartup = 'DISABLED' }
} catch {}
Say 'Fast Startup registry flag' $fastStartup
if ($fastStartup -ne 'DISABLED') {
    Write-Host 'REVIEW: verify a full Windows shutdown before Linux NTFS access; never write a hibernated NTFS volume.'
}

$encryption = 'UNKNOWN'
if (Get-Command -Name Get-BitLockerVolume -ErrorAction SilentlyContinue) {
    try {
        # Only the protection/encryption STATE is read. Never enumerate
        # KeyProtector, RecoveryPassword, numerical protectors or key files.
        $osBitLocker = Get-BitLockerVolume -MountPoint $env:SystemDrive -ErrorAction Stop
        $encryption = ("Protection={0}; Volume={1}" -f $osBitLocker.ProtectionStatus,
                                                      $osBitLocker.VolumeStatus)
    } catch {}
}
Say 'OS volume encryption state' $encryption
Write-Host 'Do NOT paste a BitLocker recovery key in logs or GitHub.'
Write-Host 'HOLD: verify recovery key possession offline BEFORE any future firmware/boot change.'

$allDisks = @()
try {
    $allDisks = @(Get-Disk -ErrorAction Stop)
    Write-Host ''
    Write-Host 'DISK INVENTORY (number/size/style only; not a target selection)' -ForegroundColor Yellow
    if ($allDisks.Count -eq 0) { Unknown 'Disk inventory' }
    foreach ($disk in $allDisks) {
        Say ("Disk " + [string]$disk.Number) ("Size={0}; Style={1}; Bus={2}; Health={3}" -f
            (Gib $disk.Size), $disk.PartitionStyle, $disk.BusType, $disk.HealthStatus)
    }
} catch { Unknown 'Disk inventory' }

$osLetter = [string]$env:SystemDrive
if ($osLetter.Length -ge 2 -and $osLetter[1] -eq ':') {
    $osLetter = $osLetter.Substring(0, 1)
} else {
    $osLetter = ''
}
$osPartition = $null
if ($osLetter -match '^[A-Za-z]$') {
    try {
        $osPartition = Get-Partition -DriveLetter $osLetter -ErrorAction Stop
    } catch { Unknown 'OS partition identification' }
} else { Unknown 'OS drive letter' }

if ($null -ne $osPartition) {
    $targetDisk = @($allDisks | Where-Object { $_.Number -eq $osPartition.DiskNumber })
    Say 'Windows OS disk number' ([string]$osPartition.DiskNumber)
    Say 'Windows OS partition size' (Gib $osPartition.Size)
    if ($targetDisk.Count -eq 1) {
        Say 'Windows OS disk style' ([string]$targetDisk[0].PartitionStyle)
        if ($targetDisk[0].PartitionStyle -ne 'GPT') {
            Write-Host 'HOLD: Windows OS disk is not confirmed GPT. Do not attempt UEFI installation plan.'
        }
    } else { Unknown 'Windows OS disk style' }
    Write-Host ''
    Write-Host 'PARTITIONS ON WINDOWS OS DISK (DO NOT DELETE OR FORMAT)' -ForegroundColor Yellow
    try {
        $parts = @(Get-Partition -DiskNumber $osPartition.DiskNumber -ErrorAction Stop)
        foreach ($part in $parts) {
            Say ("Partition " + [string]$part.PartitionNumber) ("Size={0}; Type={1}; Drive={2}" -f
                (Gib $part.Size), $part.Type,
                $(if ($null -eq $part.DriveLetter) { '-' } else { [string]$part.DriveLetter }))
        }
    } catch { Unknown 'Windows OS disk partitions' }
    try {
        $volume = Get-Volume -DriveLetter $osLetter -ErrorAction Stop
        Say 'Free space INSIDE OS volume' (Gib $volume.SizeRemaining)
        Write-Host 'Filesystem free space is NOT unallocated partition space. No shrink recommendation is made.'
    } catch { Unknown 'OS filesystem available space' }
}

Write-Host ''
Write-Host 'OTHER DISKS: READ-ONLY PARTITION SUMMARY (NOT INSTALL TARGETS)' -ForegroundColor Yellow
if ($null -ne $osPartition) {
    foreach ($disk in $allDisks) {
        if ($disk.Number -eq $osPartition.DiskNumber) { continue }
        Write-Host ("Disk {0} ({1} bus); do not format based on size or bus type." -f
            $disk.Number, $disk.BusType)
        try {
            $extras = @(Get-Partition -DiskNumber $disk.Number -ErrorAction Stop)
            if ($extras.Count -eq 0) { Write-Host '  No partitions reported (NOT proof of an unused disk).' }
            foreach ($part in $extras) {
                Say ("  Partition " + [string]$part.PartitionNumber) ("Size={0}; Type={1}; Drive={2}" -f
                    (Gib $part.Size), $part.Type,
                    $(if ($null -eq $part.DriveLetter) { '-' } else { [string]$part.DriveLetter }))
            }
        } catch { Unknown ("Disk " + [string]$disk.Number + " partition inventory") }
    }
} else {
    Write-Host 'Windows OS partition cannot be identified. Do not choose an installation disk.'
}
Write-Host ''

Write-Host 'DEPLOYMENT CHECKPOINTS — ALL REQUIRE EXPLICIT HUMAN REVIEW' -ForegroundColor Yellow
Write-Host '[PENDING] Independently tested full Windows/disk backup on disconnected media'
Write-Host '[PENDING] Windows recovery USB tested and BitLocker/device-encryption recovery key stored offline'
Write-Host '[PENDING] OEM/firmware boot menu identified; disk/ESP/Recovery partition layout independently reviewed'
Write-Host '[PENDING] If upgrading Windows first: official PC Health Check eligible; full backup/recovery; Windows 11 boots and drivers verified'
Write-Host '[PENDING] Genuine Fedora KDE installer ISO checksum/source verified; live USB hardware trial'
Write-Host '[PENDING] Target SSD and installer changes reviewed by a human, with Windows partitions preserved'
Write-Host '[PENDING] Post-install BOTH Windows and Fedora boot and restore-path verification'
Write-Host 'NO INSTALL/SHRINK/FORMAT/EFI/BOOTLOADER CHANGES AUTHORIZED.'
Write-Host 'The script made no intentional system changes and created no report files.' -ForegroundColor Green
