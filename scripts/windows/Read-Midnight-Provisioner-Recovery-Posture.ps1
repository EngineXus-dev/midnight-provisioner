#requires -Version 5.1
<#
Midnight Provisioner Phase 20. NO installation or authorization.
Observe only these documented read-only Windows commands:
  %SystemRoot%\System32\reagentc.exe /info
  %SystemRoot%\System32\powercfg.exe /a
and the Fast Startup registry flag. Discard raw command output and
publish only sanitized, bounded status labels. Neither command elevates.
Nothing is backed up, restored, mounted, encrypted or modified.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    [Console]::Error.WriteLine('Midnight Provisioner Phase 20 requires native Windows.')
    exit 2
}

$observations = New-Object 'System.Collections.Generic.List[object]'
function Add-Observation {
    param([string]$Name, [string]$State, [string]$Detail, [string]$Next)
    if ($State -notin @('OBSERVED', 'REVIEW', 'HOLD', 'UNKNOWN')) {
        throw 'Invalid Phase20 observation status'
    }
    [void]$observations.Add([pscustomobject][ordered]@{
        name = $Name
        state = $State
        evidence = $Detail
        next = $Next
    })
}

function Invoke-BoundedRead {
    param([string]$Executable, [string]$Option)
    # No user-controlled shell command, expansion, mutation or subprocess
    # arguments. Only fixed system executable and one read-only switch.
    try {
        if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
            return ''
        }
        $lines = @(& $Executable $Option 2>$null)
        $statusCode = [int]$LASTEXITCODE
        if ($statusCode -ne 0) { return '' }
        $joined = [string]($lines -join [Environment]::NewLine)
        if ($joined.Length -gt 32768) { return '' }
        return $joined
    } catch {
        return ''
    }
}

# Never display Windows RE locations, BCD identifiers or other fields.
# Recognize exact English status only; localized text remains UNKNOWN.
$systemRootPath = [string]$env:SystemRoot
if (-not $systemRootPath) { $systemRootPath = [string]$env:windir }
$reagent = if ($systemRootPath) {
    Join-Path $systemRootPath 'System32\reagentc.exe'
} else { '' }
$power = if ($systemRootPath) {
    Join-Path $systemRootPath 'System32\powercfg.exe'
} else { '' }
$recoveryRaw = if ($reagent) { Invoke-BoundedRead -Executable $reagent -Option '/info' } else { '' }
if ($recoveryRaw -match '(?im)^\s*Windows RE status\s*:\s*Enabled\s*$') {
    Add-Observation 'windows_re' 'REVIEW' 'Windows RE reported enabled (not boot-tested)' 'Verify recovery media and actual recovery boot separately.'
} elseif ($recoveryRaw -match '(?im)^\s*Windows RE status\s*:\s*Disabled\s*$') {
    Add-Observation 'windows_re' 'HOLD' 'Windows RE reported disabled' 'Review recovery options before any dual-boot change; this tool cannot enable Windows RE.'
} else {
    Add-Observation 'windows_re' 'UNKNOWN' 'Windows RE query unavailable or unrecognized' 'Confirm Windows recovery environment using a trusted manual Windows review.'
}

# A disabled Fast Startup flag does not prove the NTFS filesystem
# is currently cleanly shut down.
try {
    $fastKey = Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name HiberbootEnabled -ErrorAction Stop
    if ($fastKey.HiberbootEnabled -eq 1) {
        Add-Observation 'fast_startup' 'HOLD' 'Fast Startup registry flag enabled' 'Review disabling Fast Startup and a clean shutdown BEFORE Linux read-write NTFS access.'
    } elseif ($fastKey.HiberbootEnabled -eq 0) {
        Add-Observation 'fast_startup' 'REVIEW' 'Fast Startup registry flag disabled' 'Separately verify a clean shutdown; registry value is not an NTFS state proof.'
    } else {
        Add-Observation 'fast_startup' 'UNKNOWN' 'Fast Startup registry flag unrecognized' 'Review shutdown and hibernation state manually.'
    }
} catch {
    Add-Observation 'fast_startup' 'UNKNOWN' 'Fast Startup registry query unavailable' 'Review shutdown and hibernation state manually.'
}

# powercfg /a reports available sleep states, not actual current NTFS state.
# Localized or ambiguous output MUST remain UNKNOWN.
$powerRaw = if ($power) { Invoke-BoundedRead -Executable $power -Option '/a' } else { '' }
if ($powerRaw -match '(?is)The following sleep states are available on this system\s*:\s*(.*?)(?:The following sleep states are not available|$)') {
    $availableSection = [string]$Matches[1]
    if ($availableSection -match '(?im)^\s*Hibernate\s*$') {
        Add-Observation 'hibernate_capability' 'REVIEW' 'Hibernate is reported available' 'Available sleep states do not establish NTFS safety or actual power state.'
    } else {
        Add-Observation 'hibernate_capability' 'UNKNOWN' 'Hibernate availability not confirmed' 'Review hibernation state manually; powercfg output is advisory only.'
    }
} else {
    Add-Observation 'hibernate_capability' 'UNKNOWN' 'Sleep-state query unavailable or unrecognized' 'Do not infer NTFS shutdown safety.'
}

# These are manual evidence gates, NOT inferred from registry values.
Add-Observation 'recovery_media' 'UNKNOWN' 'Recovery media possession not observed' 'Keep Windows recovery and BitLocker recovery material offline; never upload secrets.'
Add-Observation 'backup_restoration' 'UNKNOWN' 'Independent backup and restore drill not observed' 'Verify external copies and a non-destructive restoration independently.'
Add-Observation 'secure_boot_confirmation' 'UNKNOWN' 'Secure Boot not elevated or firmware-confirmed' 'Confirm manually in msinfo32 or firmware; Confirm-SecureBootUEFI requires administrator privilege.'
Add-Observation 'encryption_key_custody' 'UNKNOWN' 'Encryption key custody not observed' 'Verify access to recovery credentials privately; do not paste recovery keys.'

$holdCount = @($observations | Where-Object { $_.state -eq 'HOLD' }).Count
$unknownCount = @($observations | Where-Object { $_.state -eq 'UNKNOWN' }).Count
$report = [ordered]@{
    schema = 'midnight-provisioner.windows-recovery-posture.v1'
    mode = 'READ_ONLY_NON_ELEVATED_WINDOWS'
    status = 'HOLD_MANUAL_RECOVERY_AND_DEPLOYMENT'
    observations = @($observations.ToArray())
    hold_checks = $holdCount
    unknown_checks = $unknownCount
    windows_recovery_boot_verified = $false
    full_backup_verified = $false
    controlled_restore_verified = $false
    encryption_recovery_key_verified = $false
    ntfs_clean_shutdown_verified = $false
    secure_boot_independently_verified = $false
    official_fedora_iso_provenance_verified = $false
    physical_fedora_isolation_verified = $false
    windows_install_authorized = $false
    fedora_install_authorized = $false
    disk_partition_write_authorized = $false
    vm_start_authorized = $false
    raw_command_output_in_report = $false
}
$report | ConvertTo-Json -Depth 5
