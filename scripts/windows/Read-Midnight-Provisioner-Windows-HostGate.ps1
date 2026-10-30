#requires -Version 5.1
<#
Midnight Provisioner phase 18: bounded, read-only native Windows host gate.
Outputs sanitized JSON ONLY. No file writes, elevation, Git, network,
disk/EFI/BitLocker mutation, VM launch, installation, or secret collection.
The result NEVER authorizes Fedora/Windows installation or partition work.
#>
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    [Console]::Error.WriteLine('Native Windows is required.')
    exit 2
}

$checks = New-Object 'System.Collections.Generic.List[object]'
function Add-Observation {
    param([string]$Name, [string]$State, [string]$Evidence, [string]$Next)
    if ($State -notin @('OBSERVED', 'REVIEW', 'HOLD', 'UNKNOWN')) {
        throw 'Invalid host-observation status'
    }
    [void]$checks.Add([pscustomobject][ordered]@{
        name = $Name
        state = $State
        evidence = $Evidence
        next = $Next
    })
}

# Emit ONLY enumerated/sanitized facts. Do not print CIM objects, paths,
# hostnames, model/serial, TPM owner data, key protectors or recovery secrets.
$family = 'UNKNOWN'
try {
    $osInfo = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
    $name = [string]$osInfo.Caption
    if ($name -match 'Windows 11') { $family = 'WINDOWS_11' }
    elseif ($name -match 'Windows 10') { $family = 'WINDOWS_10' }
    elseif ($name -match 'Windows') { $family = 'OTHER_WINDOWS' }
} catch {}
if ($family -eq 'WINDOWS_10') {
    Add-Observation 'windows_servicing' 'REVIEW' 'Windows 10 detected; ordinary support ended 2025-10-14' 'Check exact edition, lifecycle and verified security servicing/ESU; do not infer ESU enrollment.'
} elseif ($family -eq 'WINDOWS_11') {
    Add-Observation 'windows_servicing' 'REVIEW' 'Windows 11 detected' 'Verify supported edition, build and current security updates independently.'
} else {
    Add-Observation 'windows_servicing' 'UNKNOWN' 'Windows edition not confirmed' 'Verify a supported Windows installation before dual boot.'
}

try {
    $info = Get-ComputerInfo -Property BiosFirmwareType -ErrorAction Stop
    $firmware = [string]$info.BiosFirmwareType
    if ($firmware -match '^Uefi$') {
        Add-Observation 'firmware' 'OBSERVED' 'UEFI reported by Windows' 'Review actual EFI System Partition and firmware boot entries manually.'
    } elseif ($firmware -match '^Bios$') {
        Add-Observation 'firmware' 'HOLD' 'Legacy BIOS reported' 'Do not apply UEFI/GPT instructions.'
    } else { throw 'No recognized firmware mode' }
} catch {
    Add-Observation 'firmware' 'UNKNOWN' 'Firmware mode unavailable' 'Confirm UEFI using independent native Windows/firmware review.'
}

try {
    $sb = Confirm-SecureBootUEFI -ErrorAction Stop
    if ($sb -eq $true) {
        Add-Observation 'secure_boot' 'OBSERVED' 'Secure Boot enabled' 'Verify Fedora live-media compatibility before planning any change.'
    } else {
        Add-Observation 'secure_boot' 'REVIEW' 'Secure Boot not enabled' 'Review boot-chain security; this tool does not enable/disable firmware settings.'
    }
} catch {
    Add-Observation 'secure_boot' 'UNKNOWN' 'Secure Boot query unavailable' 'Verify in firmware manually; never assume disabled/enabled.'
}

try {
    $fast = Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name HiberbootEnabled -ErrorAction Stop
    if ($fast.HiberbootEnabled -eq 0) {
        Add-Observation 'fast_startup' 'OBSERVED' 'Fast Startup flag disabled' 'Independently confirm Windows is fully shut down and NTFS is not hibernated.'
    } elseif ($fast.HiberbootEnabled -eq 1) {
        Add-Observation 'fast_startup' 'HOLD' 'Fast Startup flag enabled' 'Do not mount Windows NTFS read-write from Linux until a safe shutdown plan is reviewed.'
    } else { throw 'Unknown registry value' }
} catch {
    Add-Observation 'fast_startup' 'UNKNOWN' 'Fast Startup flag unavailable' 'Confirm complete shutdown behavior before Linux NTFS access.'
}

# Never access .KeyProtector, RecoveryPassword, TPM owner auth or serials.
if (Get-Command -Name Get-BitLockerVolume -ErrorAction SilentlyContinue) {
    try {
        $volume = Get-BitLockerVolume -MountPoint $env:SystemDrive -ErrorAction Stop
        $protection = [string]$volume.ProtectionStatus
        if ($protection -eq 'On') {
            Add-Observation 'volume_encryption' 'REVIEW' 'OS volume BitLocker protection On' 'Verify the recovery key is stored securely OFFLINE; never paste it into Midnight Provisioner logs.'
        } elseif ($protection -eq 'Off') {
            Add-Observation 'volume_encryption' 'REVIEW' 'OS volume BitLocker protection Off (advisory)' 'Check actual device-encryption state and recovery options independently.'
        } else { throw 'Unknown protection state' }
    } catch {
        Add-Observation 'volume_encryption' 'UNKNOWN' 'OS encryption state unavailable' 'Verify BitLocker/device-encryption state and recovery key custody offline.'
    }
} else {
    Add-Observation 'volume_encryption' 'UNKNOWN' 'BitLocker query not available' 'Verify device encryption and recovery key custody offline.'
}

try {
    $machine = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
    $ram = [double]$machine.TotalPhysicalMemory
    if ($ram -le 0) { throw 'Invalid RAM count' }
    if ($ram -lt 7GB) {
        Add-Observation 'ram_budget' 'HOLD' 'Less than 7 GiB RAM reported' 'Review whether Fedora desktop and one small guest can safely fit.'
    } elseif ($ram -lt 12GB) {
        Add-Observation 'ram_budget' 'REVIEW' '7-12 GiB RAM range' 'Plan one small VM at a time and verify Linux memory headroom.'
    } else {
        Add-Observation 'ram_budget' 'OBSERVED' 'At least 12 GiB RAM reported' 'Still validate active guest limits on Fedora.'
    }
} catch {
    Add-Observation 'ram_budget' 'UNKNOWN' 'Installed RAM unavailable' 'Measure memory before choosing VM presets.'
}

try {
    $processors = @(Get-CimInstance -ClassName Win32_Processor -ErrorAction Stop)
    if ($processors.Count -eq 0) { throw 'No processors' }
    $vals = @($processors | ForEach-Object { $_.VirtualizationFirmwareEnabled } | Select-Object -Unique)
    if ($vals.Count -eq 1 -and $vals[0] -eq $true) {
        Add-Observation 'virtualization_firmware' 'OBSERVED' 'Virtualization firmware flag True' 'A native Fedora /dev/kvm permissions test is still required.'
    } elseif ($vals.Count -eq 1 -and $vals[0] -eq $false) {
        Add-Observation 'virtualization_firmware' 'HOLD' 'Virtualization firmware flag False' 'Review firmware CPU virtualization settings manually; no setting is changed.'
    } else { throw 'Ambiguous virtualization flag' }
} catch {
    Add-Observation 'virtualization_firmware' 'UNKNOWN' 'Virtualization firmware flag unavailable' 'Test KVM only after Fedora host setup.'
}

# Read the CURRENT Windows OS volume and its disk. Never infer an install
# target from a disk number, free-space amount, or USB bus class.
try {
    $drive = [string]$env:SystemDrive
    if ($drive -notmatch '^[A-Za-z]:$') { throw 'Unrecognized Windows system drive' }
    $partition = @(Get-Partition -DriveLetter $drive.Substring(0,1) -ErrorAction Stop)
    if ($partition.Count -ne 1) { throw 'Ambiguous OS partition' }
    $disk = @(Get-Disk -Number $partition[0].DiskNumber -ErrorAction Stop)
    if ($disk.Count -ne 1) { throw 'Ambiguous OS disk' }
    if ([string]$disk[0].PartitionStyle -eq 'GPT') {
        Add-Observation 'os_disk_layout' 'REVIEW' 'Windows OS disk reports GPT' 'Independently confirm EFI and recovery partitions and any separate boot disk.'
    } else {
        Add-Observation 'os_disk_layout' 'HOLD' 'Windows OS disk does not report GPT' 'Do not follow UEFI/GPT installation instructions.'
    }
    $parts = @(Get-Partition -DiskNumber $partition[0].DiskNumber -ErrorAction Stop)
    if ($parts.Count -eq 0) { throw 'No partition inventory' }
    # A count alone is not proof that an EFI or recovery partition is correct.
    Add-Observation 'partition_map' 'REVIEW' 'Windows OS disk partition inventory readable' 'Review EFI, Recovery, Windows, OEM and any other disks independently; no target chosen.'
} catch {
    Add-Observation 'os_disk_layout' 'UNKNOWN' 'Windows OS disk layout unavailable' 'Use a trusted Windows administrator for read-only partition review.'
    Add-Observation 'partition_map' 'UNKNOWN' 'Partition inventory incomplete' 'Do not select an installation target.'
}

# Human confirmations cannot be inferred from any Windows query.
$manual = @(
    'Verified independent full-system and data backups on separate media',
    'Performed a controlled test restore of essential files',
    'Stored Windows recovery key and installation/recovery media offline',
    'Reviewed physical disk, EFI and Recovery partition layout',
    'Verified supported Windows security servicing independently',
    'Verified authentic Fedora KDE ISO checksum and live USB hardware compatibility',
    'Reviewed Fedora partition plan with Windows volumes preserved',
    'Reserved actual guest isolation, network-denial and cold-restore tests for Fedora'
)
$unknowns = @($checks | Where-Object { $_.state -eq 'UNKNOWN' }).Count
$holds = @($checks | Where-Object { $_.state -eq 'HOLD' }).Count
$result = [ordered]@{
    schema = 'midnight-provisioner.windows-host-observation.v1'
    mode = 'READ_ONLY_NATIVE_WINDOWS'
    observed_os_family = $family
    status = 'HOLD_MANUAL_DEPLOYMENT_APPROVAL'
    hold_checks = $holds
    unknown_checks = $unknowns
    observations = @($checks.ToArray())
    manual_requirements = $manual
    full_backup_verified = $false
    restore_verified = $false
    bitlocker_recovery_key_verified = $false
    windows_install_authorized = $false
    fedora_install_authorized = $false
    disk_partition_write_authorized = $false
    real_fedora_host_isolation_verified = $false
    contains_serials_secrets_or_raw_disk_paths = $false
}
$result | ConvertTo-Json -Depth 6
