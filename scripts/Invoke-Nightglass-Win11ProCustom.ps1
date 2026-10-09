#requires -Version 5.1
<#
  Nightglass Windows 11 Pro post-install customization planner.
  DEFAULT = Preview, no writes. Current Windows 10 is never modified.
  Optional ApplyCore: ONLY after an independently verified future clean
  Windows 11 Pro install, successful backup, explicit consent, and manual
  review of a local, SHA256-pinned Win11Debloat.ps1 (not the Get.ps1 downloader).
  Does NOT perform app removal, BitLocker changes, Sandbox/WSL installation,
  Windows Update disabling, USB formatting, OS installation or browser hacks.
#>
[CmdletBinding()]
param(
  [ValidateSet('Preview','ExportPlan','ApplyCore')]
  [string]$Mode = 'Preview',
  [string]$PlanPath = '',
  [string]$Win11DebloatPath = '',
  [string]$ExpectedSha256 = '',
  [string]$Consent = '',
  [switch]$BackupVerified,
  [switch]$AllowBrowserTweaks
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# All paths are relative to the checked-out Nightglass project. No absolute
# Windows-specific project or user directory is baked into the repository.
$root = Split-Path -Parent $PSScriptRoot
$catalogPath = Join-Path $root 'config\windows11-pro-custom.json'
if (-not (Test-Path -LiteralPath $catalogPath -PathType Leaf)) {
  throw 'Windows 11 Pro profile catalog is missing; do not proceed.'
}
$profile = Get-Content -LiteralPath $catalogPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($profile.schema -cne 'nightglass.windows11.pro.custom.v1') {
  throw 'Unrecognized Nightglass Win11 Pro catalog schema.'
}
$entries = @($profile.items)
if ($entries.Count -ne 35) { throw 'Incomplete customization catalog.' }
$expectedIds = @(1..35)
if (@(Compare-Object -ReferenceObject $expectedIds -DifferenceObject @($entries | ForEach-Object { [int]$_.id })).Count -ne 0) {
  throw 'Catalog IDs were edited, repeated or omitted.'
}

# This is an intentionally hardcoded approved subset, independent of
# catalog data (which is untrusted if someone edits a local JSON file).
# An edited JSON cannot cause additional PowerShell switches to execute.
$coreIds = @(1,2,3,4,5,6,7,8,9,10,11,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,31,35)
$approvedSwitches = @(
  'DisableTelemetry','DisableSuggestions','DisableLockscreenTips','DisableEdgeAds',
  'DisableLocationServices','DisableFindMyDevice',
  'DisableSettings365Ads','DisableAISvcAutoStart','DisableEdgeAI',
  'DisablePaintAI','DisableNotepadAI','DisableDragTray',
  'RevertContextMenu','DisableStickyKeys','DisableStorageSense',
  'DisableFastStartup','DisableModernStandbyNetworking',
  'DisableUpdateASAP','PreventUpdateAutoReboot',
  'DisableDeliveryOptimization','DisableDeviceAutoAppDownload',
  'EnableDarkMode','DisableTransparency','DisableAnimations',
  'DisableDesktopSpotlight','DisableStartRecommended','DisableStartPhoneLink','DisableBing',
  'EnableEndTask','ShowKnownFileExt',
  'ShowHiddenFolders','HideHome','HideGallery','HideOnedrive',
  'DisableWindowSnapping','DisableDVR','DisableGameBarIntegration',
  'DisableRecall','DisableClickToDo'
)
$requested = @()
foreach ($item in $entries) {
  if ([int]$item.id -in $coreIds) {
    foreach ($flag in @($item.switches)) {
      # Actual gaming app and Copilot app uninstalls must remain separate
      # user-approved steps; upstream -DisableCopilot removes the app.
      if ($flag -in @('RemoveGamingApps','DisableCopilot','DisableSearchHistory',
                      'ClearStart','StartAllAppsList','DisableStoreSearchSuggestions')) { continue }
      if ($flag -notin $approvedSwitches) {
        throw ('Catalog attempted an unapproved core switch: ' + $flag)
      }
      if ($flag -notin $requested) { $requested += [string]$flag }
    }
  }
}
foreach ($flag in $approvedSwitches) {
  if ($flag -notin $requested) {
    throw ('Missing approved core flag: ' + $flag)
  }
}
if ($requested.Count -ne $approvedSwitches.Count) {
  throw 'Core switch count does not match fixed allowlist.'
}
if ($AllowBrowserTweaks) {
  # Brave-specific changes are still an opt-in within the already
  # reviewed local Win11Debloat CLI; Chrome must be configured separately.
  $requested += 'DisableBraveBloat'
}
$reviewIds = @(1,12,21,23,29,30,32,33,34)
$reviewItems = @($entries | Where-Object { [int]$_.id -in $reviewIds })
if ($reviewItems.Count -ne $reviewIds.Count) {
  throw 'Missing deferred/manual review items.'
}
Write-Host 'Nightglass / WINDOWS 11 PRO privacy + minimal customization'
Write-Host ('Mode: ' + $Mode)
Write-Host ('Catalog: ' + $catalogPath)
Write-Host ('CORE proposed switches: ' + $requested.Count)
Write-Host 'ApplyCore never performs app uninstall, disables encryption, enables Sandbox/WSL, or formats a drive.'
Write-Host 'Pro licence must activate on a separately verified clean Windows 11 installation.'
Write-Host 'Required diagnostic data cannot be reduced to absolute zero on Windows Pro.'
Write-Host ''

if ($Mode -eq 'Preview' -or $Mode -eq 'ExportPlan') {
  foreach ($item in $entries) {
    $status = if ([int]$item.id -eq 35) {
      'CORE RECALL/CLICK-TO-DO; COPILOT UNINSTALL SEPARATE'
    } elseif ([int]$item.id -eq 23) {
      'CORE BING; STORE SEARCH REQUIRES ACL REVIEW'
    } elseif ([int]$item.id -eq 21) {
      'CORE RECOMMENDATIONS; PIN RESET/LAYOUT SEPARATE'
    } elseif ([int]$item.id -eq 1) {
      'CORE OPTIONAL TELEMETRY REDUCTION; MORE MANUAL'
    } elseif ([int]$item.id -eq 31) {
      'CORE GAME-DVR/OVERLAY; XBOX UNINSTALL SEPARATE'
    } elseif ([int]$item.id -eq 6) {
      'CORE EDGE/PAINT/NOTEPAD; CHROME MANUAL'
    } elseif ([int]$item.id -in $coreIds) {
      'CORE-PROPOSED'
    } else {
      'SEPARATE-REVIEW'
    }
    Write-Host ('{0,2} [{1}] {2}' -f $item.id, $status, $item.title)
  }
  Write-Host ''
  Write-Host ('CORE: ' + ($requested -join ', '))
  Write-Host 'DEFERRED: OneDrive/Xbox/Copilot/Widget/promotional app removals, TPM/encryption, Start pins, Store search ACLs, Sandbox, WSL, Brave/Chrome policy, required telemetry.'
  Write-Host 'Preview/ExportPlan never runs Win11Debloat/WinUtil or changes Windows settings.'
  if ($Mode -eq 'Preview') { exit 0 }

  if (-not $PlanPath) { throw 'ExportPlan requires -PlanPath to a NEW local JSON file.' }
  $destination = [System.IO.Path]::GetFullPath($PlanPath)
  if (-not (Test-Path -LiteralPath (Split-Path -Parent $destination) -PathType Container)) {
    throw 'Report parent folder does not exist.'
  }
  $report = [ordered]@{
    schema = 'nightglass.windows11.pro.preview.v1'
    createdUtc = [datetime]::UtcNow.ToString('o')
    edition = 'Pro; activation to verify after clean installation'
    deploymentStatus = 'NOT INSTALLED / NOT APPLIED / HOLD'
    reviewedCoreSwitches = $requested
    deferredReviewIds = $reviewIds
    data = 'Plan excludes private disk IDs, user paths, product keys and secrets'
  }
  $json = $report | ConvertTo-Json -Depth 6
  # CreateNew refuses overwriting ANY prior file, even a symlink target.
  $file = [System.IO.File]::Open($destination, [System.IO.FileMode]::CreateNew,
                                [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
  try {
    $writer = [System.IO.StreamWriter]::new($file, [System.Text.UTF8Encoding]::new($false))
    try { $writer.WriteLine($json) ; $writer.Flush() } finally { $writer.Dispose() }
  } finally { $file.Dispose() }
  Write-Host 'Created new offline plan file only.'
  exit 0
}

# Future-only ApplyCore: this intentionally does NOT include app uninstalls,
# disable BitLocker auto-encryption, WSL/Sandbox enablement or Start reset.
if ($Consent -cne 'APPLY NIGHTGLASS WINDOWS11 PRO CORE') {
  throw 'ApplyCore requires explicit literal consent, not provided.'
}
if (-not $BackupVerified) {
  throw 'ApplyCore requires -BackupVerified after independently checking external backups and recovery.'
}
if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
  throw 'ApplyCore requires native Windows 11 Pro.'
}
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
if ([string]$os.Caption -notmatch 'Windows 11 Pro') {
  throw 'Only installed Windows 11 Pro is eligible; Windows 10 and other editions are blocked.'
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'ApplyCore needs a separately opened elevated PowerShell terminal. No self-elevation is performed.'
}
if (-not $Win11DebloatPath -or -not (Test-Path -LiteralPath $Win11DebloatPath -PathType Leaf)) {
  throw 'Supply a locally reviewed Win11Debloat.ps1 (NOT downloader Get.ps1).'
}
if ([System.IO.Path]::GetFileName($Win11DebloatPath) -cne 'Win11Debloat.ps1') {
  throw 'Only the actual Win11Debloat.ps1 file can be supplied. Never use Get.ps1.'
}
if ($ExpectedSha256 -notmatch '^[A-Fa-f0-9]{64}$') {
  throw 'Provide the SHA256 of the exact previously inspected local Win11Debloat.ps1.'
}
$actual = (Get-FileHash -LiteralPath $Win11DebloatPath -Algorithm SHA256).Hash
if ($actual -cne $ExpectedSha256.ToUpperInvariant()) {
  throw 'Third-party script SHA256 mismatch. Nothing executed.'
}
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
  $Win11DebloatPath, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count -gt 0 -or $null -eq $ast.ParamBlock) {
  throw 'Third-party Win11Debloat script parser rejected file or parameter block absent.'
}
$available = @($ast.ParamBlock.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath })
foreach ($required in (@('CreateRestorePoint') + $requested)) {
  if ($required -notin $available) {
    throw ('Reviewed Win11Debloat version does not support flag: ' + $required)
  }
}
$invocation = @{ CreateRestorePoint = $true }
foreach ($switch in $requested) { $invocation[$switch] = $true }
Write-Host 'Starting reviewed, hash-pinned local Win11Debloat script with CORE switches only.'
Write-Host 'A restore point is requested, not guaranteed. Independent full backup remains mandatory.'
# Win11Debloat is external code; its ability to reverse uninstall actions
# is limited. We deliberately exclude app uninstalls from this invocation.
& $Win11DebloatPath @invocation
if (-not $?) { throw 'Win11Debloat returned a PowerShell error; inspect local logs and backups.' }
Write-Host 'Command returned. Verify each selected setting, app compatibility and Windows Update manually.'
