#requires -Version 5.1
<#
Midnight Provisioner Phase 21: bounded WinRE query diagnosis; ALWAYS deployment-HOLD.
Runs only the built-in read-only reagentc.exe /info command. Never publishes
raw output, BCD data, image paths, usernames, volume IDs or recovery keys.
Does not request elevation, change power/BitLocker/WinRE/boot, or write files.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    [Console]::Error.WriteLine('Phase 21 requires native Windows.')
    exit 2
}

# This is an advisory check of the existing process token, NOT elevation.
$token = 'UNKNOWN'
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $token = 'ADMINISTRATOR_TOKEN'
    } else {
        $token = 'STANDARD_TOKEN'
    }
} catch { $token = 'UNKNOWN' }

function Invoke-ReagentcInfo {
    $root = [string][Environment]::SystemDirectory
    if ([string]::IsNullOrWhiteSpace($root)) {
        return @{ reason = 'OS_ROOT_UNAVAILABLE'; result = ''; status = 'UNKNOWN' }
    }
    # The program and its single read-only switch are fixed in this source.
    $tool = Join-Path $root 'reagentc.exe'
    if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
        return @{ reason = 'UTILITY_MISSING'; result = ''; status = 'UNKNOWN' }
    }
    $output = ''
    try {
        $lines = @(& $tool '/info' 2>$null)
        $code = [int]$LASTEXITCODE
        if ($code -ne 0) {
            return @{ reason = 'UTILITY_NONZERO_EXIT'; result = ''; status = 'UNKNOWN' }
        }
        $output = [string]($lines -join [Environment]::NewLine)
    } catch {
        return @{ reason = 'UTILITY_INVOCATION_ERROR'; result = ''; status = 'UNKNOWN' }
    }
    if ($output.Length -gt 32768) {
        return @{ reason = 'UTILITY_OUTPUT_TOO_LARGE'; result = ''; status = 'UNKNOWN' }
    }
    if ([string]::IsNullOrWhiteSpace($output)) {
        return @{ reason = 'UTILITY_OUTPUT_EMPTY'; result = ''; status = 'UNKNOWN' }
    }
    # Only known unambiguous English WinRE status lines are recognized.
    # Raw output may contain private device/recovery paths: never emit it.
    $enabled = [regex]::Matches($output, '(?im)^\s*Windows RE status\s*:\s*Enabled\s*$').Count
    $disabled = [regex]::Matches($output, '(?im)^\s*Windows RE status\s*:\s*Disabled\s*$').Count
    if ($enabled -eq 1 -and $disabled -eq 0) {
        return @{ reason = 'STATUS_ENGLISH_ENABLED'; result = 'REPORTED_ENABLED'; status = 'REVIEW' }
    }
    if ($disabled -eq 1 -and $enabled -eq 0) {
        return @{ reason = 'STATUS_ENGLISH_DISABLED'; result = 'REPORTED_DISABLED'; status = 'HOLD' }
    }
    return @{ reason = 'UTILITY_OUTPUT_UNRECOGNIZED'; result = ''; status = 'UNKNOWN' }
}

$observed = Invoke-ReagentcInfo
# Output only allowlisted enums. No raw command output or exit code/path/IDs.
$permittedReasons = @('OS_ROOT_UNAVAILABLE','UTILITY_MISSING',
    'UTILITY_NONZERO_EXIT','UTILITY_INVOCATION_ERROR','UTILITY_OUTPUT_TOO_LARGE',
    'UTILITY_OUTPUT_EMPTY','UTILITY_OUTPUT_UNRECOGNIZED',
    'STATUS_ENGLISH_ENABLED','STATUS_ENGLISH_DISABLED')
if ($observed.reason -notin $permittedReasons -or
    $observed.status -notin @('UNKNOWN','REVIEW','HOLD') -or
    $observed.result -notin @('','REPORTED_ENABLED','REPORTED_DISABLED')) {
    throw 'Unexpected WinRE diagnostic state; no report may be trusted.'
}
$hint = switch ([string]$observed.reason) {
    'UTILITY_MISSING' { 'Verify the Windows installation and REAgentC availability manually.' }
    'OS_ROOT_UNAVAILABLE' { 'Windows system directory unavailable; verify OS state manually.' }
    'UTILITY_NONZERO_EXIT' { 'The read-only WinRE query returned a nonzero result; review locally with an authorized Windows administrator.' }
    'UTILITY_INVOCATION_ERROR' { 'The read-only WinRE query failed; review locally with an authorized Windows administrator.' }
    'UTILITY_OUTPUT_TOO_LARGE' { 'WinRE output exceeded the safe parser bound; manual review needed.' }
    'UTILITY_OUTPUT_EMPTY' { 'WinRE returned no status; manual review needed.' }
    'UTILITY_OUTPUT_UNRECOGNIZED' { 'Output may be localized or malformed; verify status privately using an authorized Windows review.' }
    'STATUS_ENGLISH_ENABLED' { 'WinRE reports enabled, but recovery boot, image integrity and restore remain untested.' }
    'STATUS_ENGLISH_DISABLED' { 'WinRE reports disabled; do not change recovery settings without an independent recovery plan.' }
    default { 'WinRE cannot be certified.' }
}
$report = [ordered]@{
    schema = 'midnight-provisioner.winre-triage.v1'
    mode = 'NATIVE_WINDOWS_READ_ONLY_NO_ELEVATION'
    status = 'HOLD_INDEPENDENT_RECOVERY_EVIDENCE'
    winre_state = [string]$observed.status
    winre_result = [string]$observed.result
    diagnostic_reason = [string]$observed.reason
    process_token_class = $token
    next_step = $hint
    raw_reagentc_output_in_report = $false
    windows_recovery_boot_proven = $false
    recovery_media_proven = $false
    backup_independence_proven = $false
    restoration_proven = $false
    bitlocker_recovery_key_proven = $false
    ntfs_clean_shutdown_proven = $false
    secure_boot_proven = $false
    official_fedora_iso_provenance_proven = $false
    real_fedora_isolation_proven = $false
    windows_install_authorized = $false
    fedora_install_authorized = $false
    disk_write_authorized = $false
    vm_start_authorized = $false
}
$report | ConvertTo-Json -Depth 4
