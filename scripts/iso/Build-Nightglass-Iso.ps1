#requires -Version 5.1
<#
  Build the Nightglass Fedora installer ISO on Windows, inside a Fedora
  container (Docker Desktop, Linux containers). Reads the official ISO and this
  checkout read-only; writes only the new ISO into -OutputDir. Never writes to
  a USB stick or disk.
  Example:
    powershell -NoProfile -File scripts\iso\Build-Nightglass-Iso.ps1 `
      -IsoPath $HOME\Downloads\Fedora-Everything-netinst-x86_64-44-1.7.iso -Sha256 <hash from CHECKSUM>
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$IsoPath,
    [Parameter(Mandatory = $true)][string]$Sha256,
    [string]$OutputDir = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Nightglass-ISO'),
    [ValidatePattern('^[0-9]{2}$')][string]$FedoraVersion = '44'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($Sha256 -notmatch '^[0-9A-Fa-f]{64}$') { throw 'Sha256 must be the 64-character value from Fedora''s CHECKSUM file.' }
$iso = (Resolve-Path -LiteralPath $IsoPath).ProviderPath
if (-not (Test-Path -LiteralPath $iso -PathType Leaf)) { throw 'IsoPath must be the downloaded Fedora ISO file.' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop (Linux containers) is required.' }
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).ProviderPath
$out = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
New-Item -ItemType Directory -Force -Path $out | Out-Null
$isoDir = Split-Path -Parent $iso
$isoName = Split-Path -Leaf $iso
Write-Host 'Building in a privileged Fedora container: mkksiso needs loop devices to rebuild the EFI boot image.'
Write-Host 'Only the committed Nightglass code goes on the ISO; uncommitted changes are left out.'
# File name and hash are passed as arguments, never pasted into the shell text.
$inner = 'dnf -y -q install lorax xorriso isomd5sum python3-kickstart git >/dev/null && ' +
         'bash /src/scripts/iso/build-nightglass-iso.sh --iso "/in/$1" --sha256 "$2" --output /out'
& docker run --rm --privileged `
    -v ($repo + ':/src:ro') -v ($isoDir + ':/in:ro') -v ($out + ':/out') `
    ('registry.fedoraproject.org/fedora:' + $FedoraVersion) bash -c $inner nightglass $isoName $Sha256
if ($LASTEXITCODE -ne 0) { throw ('ISO build failed (exit ' + $LASTEXITCODE + '). No USB stick or disk was touched.') }
Write-Host ('Done. New ISO and .sha256 file are in ' + $out)
