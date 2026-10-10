# Windows 10 preflight - read-only. No partition/BCD/BitLocker changes.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Continue'
Write-Host '== NIGHTGLASS Windows Host Preflight (READ ONLY) ==' -ForegroundColor Cyan
Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,OSArchitecture | Format-List
Get-CimInstance Win32_Processor | Select-Object Name,NumberOfLogicalProcessors,VMMonitorModeExtensions,VirtualizationFirmwareEnabled,SecondLevelAddressTranslationExtensions | Format-List
Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,TotalPhysicalMemory,HypervisorPresent | Format-List
Write-Host '== Disk layout (do not modify until backed up) ==' -ForegroundColor Yellow
Get-Disk | Select-Object Number,FriendlyName,PartitionStyle,Size,HealthStatus | Format-Table -AutoSize
Get-Partition | Select-Object DiskNumber,PartitionNumber,DriveLetter,Size,Type | Format-Table -AutoSize
Write-Host '== Firmware / encryption context ==' -ForegroundColor Yellow
try { Get-ComputerInfo -Property BiosFirmwareType | Format-List } catch { Write-Host 'Firmware type unavailable' }
if (Get-Command Get-BitLockerVolume -ErrorAction SilentlyContinue) {
    try { Get-BitLockerVolume | Select-Object MountPoint,ProtectionStatus,VolumeStatus | Format-Table -AutoSize }
    catch { Write-Host 'BitLocker inspection requires additional permissions.' }
}
Write-Host 'No disk, firmware, boot or encryption settings were changed.' -ForegroundColor Green
