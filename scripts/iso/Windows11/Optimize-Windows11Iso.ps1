#requires -Version 5.1
#requires -RunAsAdministrator
<#
  Make a smaller Windows 11 ISO that holds ONLY the edition you install.
  Safe trim: DISM exports that one edition unchanged (optionally into the more
  compact install.esd format) and oscdimg rebuilds the ISO with the original,
  signed boot files. No Windows component, app, driver, update or security
  feature is removed, so Windows Update, Defender and WinRE keep working.

  Reads the original ISO read-only and writes a NEW ISO next to it. Never
  touches a USB stick or disk. Needs an elevated PowerShell (DISM requires it)
  and oscdimg from the Windows ADK "Deployment Tools" feature.

  With AtlasOS: inject first, then trim the injected ISO (or trim with
  -Format Wim first, since AME Wizard may need a mountable install.wim).
  Test the result in a VM before using it on the real PC.
#>
[CmdletBinding()]
param(
    [string]$IsoPath = '',
    [string]$Edition = 'Windows 11 Pro',
    [ValidateSet('Esd', 'Wim')][string]$Format = 'Esd',
    [string]$OscdimgPath = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $IsoPath) {
    $found = @(Get-ChildItem -LiteralPath $PSScriptRoot -File -Filter '*.iso' |
        Where-Object { $_.Name -notlike '*-single-edition.iso' })
    if ($found.Count -ne 1) { throw ('Put exactly one Windows ISO in ' + $PSScriptRoot + ' or pass -IsoPath (found ' + $found.Count + ').') }
    $IsoPath = $found[0].FullName
}
$iso = (Resolve-Path -LiteralPath $IsoPath).ProviderPath
if (-not $OscdimgPath) {
    $OscdimgPath = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\Assessment and Deployment Kit\Deployment Tools\amd64\Oscdimg\oscdimg.exe'
}
if (-not (Test-Path -LiteralPath $OscdimgPath -PathType Leaf)) {
    throw 'oscdimg.exe not found. Install the Windows ADK with only "Deployment Tools", or pass -OscdimgPath.'
}
$folder = Split-Path -Parent $iso
$target = Join-Path $folder ([IO.Path]::GetFileNameWithoutExtension($iso) + '-single-edition.iso')
if (Test-Path -LiteralPath $target) { throw ('Refusing to overwrite ' + $target) }
$needed = 2 * (Get-Item -LiteralPath $iso).Length
$free = (Get-PSDrive -Name (Split-Path -Qualifier $folder).TrimEnd(':')).Free
if ($free -lt $needed) { throw ('Not enough free space: need about ' + [math]::Ceiling($needed / 1GB) + ' GB on the drive holding the ISO.') }

$work = Join-Path $folder ('work-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
$mounted = $false
try {
    Write-Host ('Mounting (read-only): ' + $iso)
    $image = Mount-DiskImage -ImagePath $iso -Access ReadOnly -PassThru
    $mounted = $true
    $volume = $image | Get-Volume
    $source = $volume.DriveLetter + ':\'
    $label = [string]$volume.FileSystemLabel
    $wim = @('sources\install.wim', 'sources\install.esd' | ForEach-Object { Join-Path $source $_ } |
        Where-Object { Test-Path -LiteralPath $_ })
    if ($wim.Count -ne 1) { throw 'This does not look like a Windows installation ISO (no single sources\install.wim/esd).' }

    $editions = @(Get-WindowsImage -ImagePath $wim[0])
    $match = @($editions | Where-Object { $_.ImageName -eq $Edition })
    if ($match.Count -ne 1) {
        throw ('Edition "' + $Edition + '" not found. Available: ' + (($editions | ForEach-Object { $_.ImageName }) -join '; '))
    }
    Write-Host ('Keeping only: ' + $Edition + ' (index ' + $match[0].ImageIndex + ' of ' + $editions.Count + ')')

    Write-Host 'Copying setup and boot files (everything except the Windows image)...'
    & robocopy.exe $source $work /E /XF install.wim install.esd /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
    if ($LASTEXITCODE -ge 8) { throw ('Copying the ISO contents failed (robocopy ' + $LASTEXITCODE + ').') }
    Get-ChildItem -LiteralPath $work -Recurse -File | ForEach-Object { $_.IsReadOnly = $false }

    $extension = $Format.ToLowerInvariant()
    $compression = if ($Format -eq 'Esd') { 'recovery' } else { 'max' }
    $destination = Join-Path $work ('sources\install.' + $extension)
    Write-Host ('Exporting the edition with ' + $compression + ' compression (this takes a while)...')
    & dism.exe /Export-Image ('/SourceImageFile:' + $wim[0]) ('/SourceIndex:' + $match[0].ImageIndex) `
        ('/DestinationImageFile:' + $destination) ('/Compress:' + $compression) /CheckIntegrity
    if ($LASTEXITCODE -ne 0) { throw ('DISM export failed (exit ' + $LASTEXITCODE + ').') }
    $check = @(Get-WindowsImage -ImagePath $destination)
    if ($check.Count -ne 1 -or $check[0].ImageName -ne $Edition) { throw 'Exported image does not contain exactly the chosen edition.' }
} finally {
    if ($mounted) { Dismount-DiskImage -ImagePath $iso | Out-Null }
}

try {
    Write-Host 'Rebuilding a BIOS + UEFI bootable ISO with the original signed boot files...'
    if ($label.Length -lt 1 -or $label.Length -gt 32) { $label = 'WIN11_SINGLE' }
    Push-Location $work
    try {
        # Relative boot-file paths avoid quoting problems with spaces in folder names.
        & $OscdimgPath -m -o -u2 -udfver102 '-bootdata:2#p0,e,bboot\etfsboot.com#pEF,e,befi\microsoft\boot\efisys.bin' `
            ('-l' + $label) . $target
        if ($LASTEXITCODE -ne 0) { throw ('oscdimg failed (exit ' + $LASTEXITCODE + ').') }
    } finally { Pop-Location }
} finally {
    # Only the work folder this script created.
    Remove-Item -LiteralPath $work -Recurse -Force
}
$hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
($hash + '  ' + (Split-Path -Leaf $target)) | Set-Content -LiteralPath ($target + '.sha256') -Encoding ASCII
$before = (Get-Item -LiteralPath $iso).Length / 1GB
$after = (Get-Item -LiteralPath $target).Length / 1GB
Write-Host ('Done: {0} ({1:N2} GB, was {2:N2} GB)' -f $target, $after, $before)
Write-Host 'Test it in a VM before using it on the real PC. The original ISO is unchanged.'
