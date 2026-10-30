#requires -Version 5.1
<#
  Build the Midnight Provisioner Fedora installer ISO on Windows, inside a Fedora
  container (Docker Desktop, Linux containers). Reads the official ISO and this
  checkout read-only; writes only the new ISO. Never writes to a USB stick or disk.

  Easiest: put the official Fedora Everything netinstall ISO and its CHECKSUM
  file in this folder (scripts\iso\Fedora), then run with no arguments:
    powershell -NoProfile -File scripts\iso\Fedora\Build-Midnight-Provisioner-Iso.ps1
  Fedora's signature on CHECKSUM is verified inside the container before use.
#>
[CmdletBinding()]
param(
    [string]$IsoPath = '',
    [string]$ChecksumPath = '',
    [string]$Sha256 = '',
    [string]$OutputDir = $PSScriptRoot,
    [string]$OutputName = '',
    [ValidatePattern('^[0-9]{2}$')][string]$FedoraVersion = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Find-One([string]$Folder, [string]$Pattern, [string]$What) {
    $found = @(Get-ChildItem -LiteralPath $Folder -File -Filter $Pattern)
    if ($found.Count -ne 1) {
        throw ('Expected exactly one ' + $What + ' (' + $Pattern + ') in ' + $Folder + ', found ' + $found.Count + '. Pass it explicitly.')
    }
    return $found[0].FullName
}

if (-not $IsoPath) { $IsoPath = Find-One $PSScriptRoot 'Fedora-Everything-netinst-x86_64-*.iso' 'Fedora netinstall ISO' }
$iso = (Resolve-Path -LiteralPath $IsoPath).ProviderPath
if (-not (Test-Path -LiteralPath $iso -PathType Leaf)) { throw 'IsoPath must be the downloaded Fedora ISO file.' }
$isoDir = Split-Path -Parent $iso
$isoName = Split-Path -Leaf $iso
if ($Sha256 -and $ChecksumPath) { throw 'Give either -Sha256 or -ChecksumPath, not both.' }
if ($Sha256 -and $Sha256 -notmatch '^[0-9A-Fa-f]{64}$') { throw 'Sha256 must be 64 hexadecimal characters.' }
if (-not $Sha256 -and -not $ChecksumPath) { $ChecksumPath = Find-One $isoDir '*CHECKSUM' 'Fedora CHECKSUM file' }
$checksumName = '-'  # Windows PowerShell 5.1 drops empty native arguments; '-' means none
if ($ChecksumPath) {
    $checksum = (Resolve-Path -LiteralPath $ChecksumPath).ProviderPath
    if ((Split-Path -Parent $checksum) -ne $isoDir) { throw 'Keep the CHECKSUM file in the same folder as the ISO.' }
    $checksumName = Split-Path -Leaf $checksum
}
if (-not $FedoraVersion) {
    if ($isoName -notmatch '-x86_64-([0-9]{2})-') { throw 'Cannot tell the Fedora version from the ISO name; pass -FedoraVersion.' }
    $FedoraVersion = $Matches[1]
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop (Linux containers) is required.' }
$repo = (Get-Item -LiteralPath $PSScriptRoot).Parent.Parent.Parent.FullName
$out = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
New-Item -ItemType Directory -Force -Path $out | Out-Null

# Preserve existing ISOs and their checksum sidecars. Pick the name on the host
# before Docker downloads/installs packages; pass that exact name to the builder.
$explicitName = [bool]$OutputName
if (-not $OutputName) { $OutputName = 'Midnight-Provisioner-Installer-' + $isoName }
if ($OutputName -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*\.iso$') {
    throw 'OutputName must be an ISO filename containing only letters, digits, dots, underscores or hyphens, without a directory.'
}
function Test-OutputCollision([string]$Name) {
    return (Test-Path -LiteralPath (Join-Path $out $Name)) -or (Test-Path -LiteralPath (Join-Path $out ($Name + '.sha256')))
}
if (Test-OutputCollision $OutputName) {
    if ($explicitName) { throw ('Refusing to overwrite ' + (Join-Path $out $OutputName) + ' or its checksum. Choose another -OutputName or -OutputDir.') }
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($OutputName)
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
    $OutputName = $stem + '-rebuild-' + $stamp + '.iso'
    $sequence = 1
    while (Test-OutputCollision $OutputName) {
        $OutputName = $stem + '-rebuild-' + $stamp + '-' + $sequence + '.iso'
        $sequence++
    }
    Write-Host 'Existing build preserved; using a new output filename.'
}
Write-Host ('Output ISO: ' + (Join-Path $out $OutputName))

Write-Host ('Fedora ' + $FedoraVersion + ' ISO: ' + $isoName)
Write-Host 'Building in a privileged Fedora container: mkksiso needs loop devices to rebuild the EFI boot image.'
Write-Host 'Only the committed Midnight Provisioner code goes on the ISO; uncommitted changes are left out.'
# File names and the hash are passed as arguments, never pasted into the shell text.
$inner = 'dnf -y -q install lorax xorriso isomd5sum mtools python3-kickstart git gnupg2 >/dev/null && ' +
         'if [ "$2" != - ]; then verify=(--checksum "/in/$2"); else verify=(--sha256 "$3"); fi && ' +
         'bash /src/scripts/iso/Fedora/build-midnight-provisioner-iso.sh --iso "/in/$1" "${verify[@]}" --output /out --name "$4"'
& docker run --rm --privileged `
    -v ($repo + ':/src:ro') -v ($isoDir + ':/in:ro') -v ($out + ':/out') `
    ('registry.fedoraproject.org/fedora:' + $FedoraVersion) bash -c $inner midnight-provisioner $isoName $checksumName $(if ($Sha256) { $Sha256 } else { '-' }) $OutputName
if ($LASTEXITCODE -ne 0) { throw ('ISO build failed (exit ' + $LASTEXITCODE + '). No USB stick or disk was touched.') }
Write-Host ('Done. ISO: ' + (Join-Path $out $OutputName))
Write-Host ('Checksum: ' + (Join-Path $out ($OutputName + '.sha256')))
