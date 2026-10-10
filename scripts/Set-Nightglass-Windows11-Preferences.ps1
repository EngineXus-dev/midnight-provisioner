#requires -Version 5.1
<#
  Nightglass optional post-clean-install Windows 11 USER PREFERENCE tweak.
  Default PREVIEW. No elevation, network calls, app removal, services,
  packages, debloat binaries, Windows Update/Defender/TPM/BitLocker changes,
  partitioning, bootloader edits, reboots, or ISO/USB operations.
  Apply creates an exclusive private snapshot before changing HKCU DWORDs.
  Undo validates the snapshot against an internal fixed allowlist and refuses
  to overwrite a preference that a user subsequently changed.
  Not tested on Windows 11 hardware yet; run parser and tests first.
#>
[CmdletBinding()]
param(
    [ValidateSet('Preview', 'Apply', 'Undo')]
    [string]$Mode = 'Preview',
    [string]$Consent = '',
    [string]$SnapshotPath = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$format = 'nightglass-win11-hkcu-preferences-v1'

function Preferences {
    return @(
        [pscustomobject]@{ Path='HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced'; Name='HideFileExt'; Value=0; Label='Show known file extensions' }
        [pscustomobject]@{ Path='HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced'; Name='TaskbarDa'; Value=0; Label='Hide Widgets taskbar button' }
        [pscustomobject]@{ Path='HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced'; Name='ShowTaskViewButton'; Value=0; Label='Hide Task View button' }
        [pscustomobject]@{ Path='HKCU:\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager'; Name='SoftLandingEnabled'; Value=0; Label='Reduce consumer tips' }
        [pscustomobject]@{ Path='HKCU:\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager'; Name='SystemPaneSuggestionsEnabled'; Value=0; Label='Reduce system suggestions' }
        [pscustomobject]@{ Path='HKCU:\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager'; Name='SubscribedContent-338388Enabled'; Value=0; Label='Reduce promoted content' }
        [pscustomobject]@{ Path='HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'; Name='AppsUseLightTheme'; Value=0; Label='Dark app theme' }
        [pscustomobject]@{ Path='HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'; Name='SystemUsesLightTheme'; Value=0; Label='Dark system theme' }
    )
}

function Current-Dword {
    param([string]$Path, [string]$Name)
    if (-not (Test-Path -LiteralPath $Path)) {
        return [pscustomobject]@{ Exists=$false; Value=$null }
    }
    $key = Get-Item -LiteralPath $Path -ErrorAction Stop
    if (@($key.GetValueNames()) -notcontains $Name) {
        return [pscustomobject]@{ Exists=$false; Value=$null }
    }
    if ([string]$key.GetValueKind($Name) -ne 'DWord') {
        throw "Existing registry value has a different type; no changes: $Name"
    }
    return [pscustomobject]@{ Exists=$true; Value=[int]$key.GetValue($Name) }
}

function Assert-Windows11 {
    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        throw 'Use Windows PowerShell on a real Windows 11 desktop.'
    }
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    if ([string]$os.Caption -notmatch 'Windows 11') {
        throw 'Windows 11 not detected. Never apply these preferences to Windows 10.'
    }
}

$items = @(Preferences)
Write-Host 'Nightglass Windows 11 preference helper  -  optional / no external tools'
if ($Mode -eq 'Preview') {
    Write-Host 'PREVIEW ONLY: no file or registry writes.'
    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        Write-Host 'This preview has no Windows registry observations on this system.'
    } else {
        foreach ($item in $items) {
            try {
                $current = Current-Dword $item.Path $item.Name
                $seen = if ($current.Exists) { [string]$current.Value } else { '(not set)' }
                Write-Host ("{0} | current: {1} | preferred: {2}" -f $item.Label, $seen, $item.Value)
            } catch {
                Write-Host ("{0} | current: unreadable | preferred: {1}" -f $item.Label, $item.Value)
            }
        }
    }
    Write-Host 'No Defender, Update, firewall, encryption, OOBE, apps, services or firmware changes.'
    exit 0
}

Assert-Windows11

if ($Mode -eq 'Apply') {
    if ($Consent -cne 'APPLY NIGHTGLASS USER PREFERENCES') {
        throw 'No consent. To opt in later use -Mode Apply -Consent "APPLY NIGHTGLASS USER PREFERENCES".'
    }
    if ($SnapshotPath -ne '') {
        throw 'Apply chooses a NEW local snapshot automatically; do not supply -SnapshotPath.'
    }
    $records = @()
    foreach ($item in $items) {
        $current = Current-Dword $item.Path $item.Name
        $records += [pscustomobject]@{
            Path=$item.Path
            Name=$item.Name
            WasPresent=[bool]$current.Exists
            PreviousValue=$current.Value
            AppliedValue=[int]$item.Value
        }
    }
    $backupFolder = Join-Path $env:LOCALAPPDATA 'Nightglass\PreferenceSnapshots'
    if (-not (Test-Path -LiteralPath $backupFolder)) {
        New-Item -ItemType Directory -Path $backupFolder -Force -ErrorAction Stop | Out-Null
    }
    $file = Join-Path $backupFolder ('win11-hkcu-' + [guid]::NewGuid().ToString('N') + '.json')
    $payload = [pscustomobject]@{
        Format=$format
        CreatedUtc=[datetime]::UtcNow.ToString('o')
        Records=$records
    }
    $json = $payload | ConvertTo-Json -Depth 6
    $stream = [System.IO.File]::Open($file, [System.IO.FileMode]::CreateNew,
                                    [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
        try { $writer.WriteLine($json); $writer.Flush() } finally { $writer.Dispose() }
    } finally { $stream.Dispose() }
    Write-Host "Snapshot created before any preferences changed: $file"
    foreach ($item in $items) {
        if (-not (Test-Path -LiteralPath $item.Path)) {
            New-Item -Path $item.Path -Force -ErrorAction Stop | Out-Null
        }
        New-ItemProperty -Path $item.Path -Name $item.Name -PropertyType DWord -Value $item.Value -Force -ErrorAction Stop | Out-Null
        Write-Host ('Applied: ' + $item.Label)
    }
    Write-Host 'Completed; sign out and back in if taskbar/theme is not updated immediately.'
    Write-Host 'Undo later using -Mode Undo -SnapshotPath <the snapshot above> -Consent "UNDO NIGHTGLASS USER PREFERENCES".'
    exit 0
}

if ($Mode -eq 'Undo') {
    if ($Consent -cne 'UNDO NIGHTGLASS USER PREFERENCES') {
        throw 'No undo consent.'
    }
    if (-not $SnapshotPath -or -not (Test-Path -LiteralPath $SnapshotPath -PathType Leaf)) {
        throw 'An existing local snapshot file is required for Undo.'
    }
    $data = Get-Content -LiteralPath $SnapshotPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $data -or $data.Format -cne $format) { throw 'Unrecognized snapshot version.' }
    $records = @($data.Records)
    if ($records.Count -ne $items.Count) { throw 'Snapshot key count does not match the safe allowlist.' }
    for ($i=0; $i -lt $items.Count; $i++) {
        $item = $items[$i]
        $entry = $records[$i]
        if ([string]$entry.Path -cne [string]$item.Path -or
            [string]$entry.Name -cne [string]$item.Name -or
            [int]$entry.AppliedValue -ne [int]$item.Value -or
            ($entry.WasPresent -isnot [bool])) {
            throw 'Snapshot does not match the fixed safe preference allowlist.'
        }
        if ([bool]$entry.WasPresent -and $null -eq $entry.PreviousValue) {
            throw 'Snapshot missing the original DWORD value.'
        }
    }
    Write-Host 'Restoring preferences only when their current value still equals the value we applied.'
    for ($i=0; $i -lt $items.Count; $i++) {
        $item = $items[$i]
        $entry = $records[$i]
        $current = Current-Dword $item.Path $item.Name
        if (-not $current.Exists -or [int]$current.Value -ne [int]$item.Value) {
            Write-Host ('SKIPPED, modified since Apply: ' + $item.Label)
            continue
        }
        if ([bool]$entry.WasPresent) {
            New-ItemProperty -Path $item.Path -Name $item.Name -PropertyType DWord -Value ([int]$entry.PreviousValue) -Force -ErrorAction Stop | Out-Null
        } else {
            Remove-ItemProperty -Path $item.Path -Name $item.Name -ErrorAction Stop
        }
        Write-Host ('Restored: ' + $item.Label)
    }
    Write-Host 'Undo completed for eligible values. Snapshot was retained unchanged for audit.'
    exit 0
}
