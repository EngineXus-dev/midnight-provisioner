#requires -Version 5.1
<#
Nightglass source release candidate packager: NO fetch/checkout/merge/reset,
disk, boot, USB, VM, installer or backup operations. Archives only tracked files
from an explicitly pinned Git commit, never untracked .env or local .venv.
#>
[CmdletBinding()]
param(
 [string]$RepoPath = (Get-Location).Path,
 [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedCommit,
 [string]$OutputRoot = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Nightglass-ReleaseCandidates')
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function GitText([string[]]$GitArgs) {
 # Function-local 'Continue': PowerShell 5.1 would otherwise throw a raw
 # NativeCommandError on git stderr before the check below can explain it.
 $ErrorActionPreference = 'Continue'
 $lines = @(& git -C $RepoPath @GitArgs 2>&1)
 if ($LASTEXITCODE -ne 0) { throw ('Nightglass Git metadata check failed: ' + $GitArgs[0]) }
 return ($lines -join [Environment]::NewLine).Trim()
}
$RepoPath = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $RepoPath).Path).TrimEnd('\')
$top = [IO.Path]::GetFullPath((GitText @('rev-parse','--show-toplevel'))).TrimEnd('\')
if ($RepoPath -cne $top) { throw 'Use the Nightglass Git checkout ROOT.' }
$origin = GitText @('remote','get-url','origin')
if ($origin -notmatch '^(?:https://github\.com/|git@github\.com:)EngineXus-dev/nightglass-workspaces(?:\.git)?/?$') {
 throw 'Refusing unexpected GitHub remote.'
}
$sha = GitText @('rev-parse','--verify',($ExpectedCommit + '^{commit}'))
if ($sha -cne $ExpectedCommit) { throw 'Commit is unavailable or differs from requested exact SHA.' }
$mainBefore = GitText @('rev-parse','--verify','refs/heads/main^{commit}')
$tree = @((GitText @('ls-tree','-r','--name-only',$sha)) -split [char]10)
if ($tree.Count -lt 60) { throw 'Too few Git-tracked source files for a cumulative candidate.' }
foreach ($item in $tree) {
 $name = $item.Trim()
 if ($name -match '(^|/)(?:\.env(?:\..*)?|\.venv|venv|__pycache__|secrets?)(?:/|$)' -or
     $name -match '\.(?:pem|key|pfx|p12|p8|kdbx|qcow2?|vmdk|vdi|iso|img|vhdx)$') {
   throw ('Tracked secret/image path requires manual review: ' + $name)
 }
}
foreach ($required in @('nightglass/ui.py','nightglass/install_proposal_review.py',
                          'scripts/install/setup-nightglass.sh',
                          'config/nightglass-integration-snapshot-v2.json',
                          'scripts/release/Review-Nightglass-Integration.py')) {
 if ($tree -notcontains $required) { throw ('Required source absent: ' + $required) }
}
# PowerShell location, not the .NET process directory (Set-Location does not change it).
$root = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputRoot).TrimEnd('\')
if ($root -ieq $RepoPath -or
    $root.StartsWith($RepoPath + '\', [StringComparison]::OrdinalIgnoreCase)) {
 throw 'Release output must be OUTSIDE the checkout.'
}
$token = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$name = 'Nightglass-Integration-RC-' + $sha.Substring(0,12) + '-' + $token
New-Item -ItemType Directory -Path $root -Force | Out-Null
$stage = Join-Path $root $name
New-Item -ItemType Directory -Path $stage -ErrorAction Stop | Out-Null
$sourceZip = Join-Path $stage 'nightglass-source.zip'
$manifest = Join-Path $stage 'RELEASE-MANIFEST.json'
$readme = Join-Path $stage 'READ-FIRST.txt'
$bundle = Join-Path $root ($name + '.zip')
if (Test-Path -LiteralPath $bundle) { throw 'Refusing existing release archive.' }
Write-Host ('Git archive of pinned source commit: ' + $sha)
$null = & git -C $RepoPath archive --format=zip ('--output=' + $sourceZip) $sha
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $sourceZip)) { throw 'Git source archive failed.' }
$hash = (Get-FileHash -LiteralPath $sourceZip -Algorithm SHA256).Hash.ToLowerInvariant()
$mainAfter = GitText @('rev-parse','--verify','refs/heads/main^{commit}')
if ($mainAfter -cne $mainBefore) { throw 'Local main changed during package operation.' }
[ordered]@{
 schema='nightglass.integration.source-rc.v1'
 status='SOURCE_CANDIDATE_NOT_PRODUCTION_DEPLOYMENT'
 repository='EngineXus-dev/nightglass-workspaces'
 exact_git_commit=$sha
 local_main_before=$mainBefore
 local_main_after=$mainAfter
 timestamp_utc=(Get-Date).ToUniversalTime().ToString('o')
 tracked_source_files=$tree.Count
 source_zip_name='nightglass-source.zip'
 source_zip_sha256=$hash
 fedora_app_installer='scripts/install/setup-nightglass.sh'
 complete_os_installer_included=$false
 installed_fedora_gui_binary_included=$false
 physical_fedora_host_validated=$false
 user_backup_certified=$false
 merge_authorized=$false
 disk_write_authorized=$false
} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $manifest -Encoding UTF8
@'
Nightglass cumulative integration SOURCE RC.
Extract nightglass-source.zip to a NEW empty folder. It contains tracked
Python/Fedora application source and scripts/install/setup-nightglass.sh, not a
Windows executable, an installed Fedora image or OS installer.
No physical disk, USB, backup, VM, boot or firmware actions are performed.
User backups and real Fedora host security acceptance are not certified.
All development PRs remain draft until explicit separate merge approval.
Read docs/INTEGRATION_RELEASE_CANDIDATE.md and PR53 fork reconciliation.
'@ | Set-Content -LiteralPath $readme -Encoding UTF8
Compress-Archive -LiteralPath @($sourceZip,$manifest,$readme) -DestinationPath $bundle -CompressionLevel Optimal -ErrorAction Stop
if (-not (Test-Path -LiteralPath $bundle)) { throw 'Release bundle not created.' }
Write-Host ('SOURCE RC READY: ' + $bundle)
Write-Host ('SOURCE SHA256: ' + $hash)
Write-Host ('LOCAL MAIN UNCHANGED: ' + $mainAfter)
Write-Host 'No installation, merge, disk, USB, boot, backup or VM operation performed.'
