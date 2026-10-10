# Archive local Nightglass verification evidence after a completed test run.
# Opt-in, source ZIP unchanged, no Git/VM/installer/USB or backup disk operations.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateNotNullOrEmpty()]
    [string] $ResultsZip,
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string] $CommitSha,
    [ValidatePattern('^[A-Za-z0-9_-]{1,32}$')]
    [string] $Label = 'FinalWindows',
    [string] $ArchiveRoot
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$src = (Resolve-Path -LiteralPath $ResultsZip -ErrorAction Stop).ProviderPath
$sourceFile = Get-Item -LiteralPath $src
if ($sourceFile.PSIsContainer -or ($sourceFile.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Refusing linked, reparse-point or directory result sources.'
}
if ($sourceFile.Length -gt 209715200) { throw 'Result ZIP exceeds 200 MiB review limit.' }
if (-not $ArchiveRoot) {
    $documents = [Environment]::GetFolderPath('MyDocuments')
    if (-not $documents) { throw 'Documents location is unavailable; supply -ArchiveRoot.' }
    $ArchiveRoot = Join-Path $documents 'Nightglass-Verification-Results'
}
if (-not (Test-Path -LiteralPath $ArchiveRoot)) {
    New-Item -ItemType Directory -Path $ArchiveRoot -ErrorAction Stop | Out-Null
}
$root = Get-Item -LiteralPath $ArchiveRoot
if (-not $root.PSIsContainer -or ($root.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Archive root must be a normal, non-reparse directory.'
}
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$name = "$stamp-$Label-$($CommitSha.Substring(0,12))-$([guid]::NewGuid().ToString('N').Substring(0,8))"
$dest = Join-Path $root.FullName $name
$reportDir = Join-Path $dest 'reports'

# Read and validate every ZIP entry before creating the destination.
$zip = [IO.Compression.ZipFile]::OpenRead($src)
try {
    $entries = @($zip.Entries)
    if ($entries.Count -lt 2 -or $entries.Count -gt 300) { throw 'Unexpected report ZIP entry count.' }
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $total = [int64]0
    foreach ($entry in $entries) {
        if ($entry.FullName -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$' -or
            $entry.FullName -eq '.' -or $entry.FullName -eq '..' -or
            -not $seen.Add($entry.FullName)) {
            throw "Unsafe or duplicate ZIP entry: $($entry.FullName)"
        }
        if ($entry.Length -gt 10485760) { throw "Oversized result log: $($entry.FullName)" }
        $total += $entry.Length
        if ($total -gt 209715200) { throw 'Uncompressed reports exceed 200 MiB.' }
    }
    if (-not $seen.Contains('manifest.txt') -or -not $seen.Contains('summary.csv')) {
        throw 'Missing manifest.txt or summary.csv in result archive.'
    }
}
finally { $zip.Dispose() }

# Result evidence is always retained, even when the test suite itself failed.
New-Item -ItemType Directory -Path $dest -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Path $reportDir -ErrorAction Stop | Out-Null
Copy-Item -LiteralPath $src -Destination (Join-Path $dest 'original-results.zip') -ErrorAction Stop
[IO.Compression.ZipFile]::ExtractToDirectory($src, $reportDir)

$manifest = [IO.File]::ReadAllText((Join-Path $reportDir 'manifest.txt'))
if (-not $manifest.Contains($CommitSha)) {
    throw "Manifest does not contain the required commit SHA. Review incomplete folder: $dest"
}
$rows = @(Import-Csv -LiteralPath (Join-Path $reportDir 'summary.csv'))
if ($rows.Count -lt 1) {
    throw "Result summary is empty. Review incomplete folder: $dest"
}
$failed = @($rows | Where-Object { $_.ExitCode -notmatch '^0$' })
$status = if ($failed.Count -eq 0) { 'SUITES_EXITED_ZERO_REVIEW_SKIPS' } else { 'FAILED_OR_INCOMPLETE' }
$files = @(Get-ChildItem -LiteralPath $dest -File -Recurse | Sort-Object FullName)
$hashes = foreach ($file in $files) {
    $relative = $file.FullName.Substring($dest.Length).TrimStart('\','/')
    [pscustomobject]@{
        relative_path = $relative.Replace('\','/')
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        bytes = $file.Length
    }
}
$hashes | Export-Csv -LiteralPath (Join-Path $dest 'sha256-inventory.csv') -NoTypeInformation -Encoding UTF8
[pscustomobject]@{
    archived_utc = [DateTime]::UtcNow.ToString('o')
    commit_sha = $CommitSha.ToLowerInvariant()
    label = $Label
    status = $status
    suites = $rows.Count
    failing_suites = $failed.Count
    original_zip_name = $sourceFile.Name
    note = 'Unverified skips and Fedora/hardware acceptance are independent gates. SHA256 inventory is unsigned.'
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $dest 'archive-metadata.json') -Encoding UTF8
Write-Host "Nightglass verification evidence: $dest"
Write-Host "Status: $status | Suites: $($rows.Count) | Nonzero: $($failed.Count)"
Write-Host 'Keep this directory for long-term reference. Do not treat synthetic-only tests as Fedora acceptance.'
