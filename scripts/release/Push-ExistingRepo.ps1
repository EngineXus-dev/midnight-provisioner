# Safely import Midnight Provisioner files into the already-created private GitHub repository.
# Requires Git for Windows and valid Git credentials. No force push, no filesystem deletion.
[CmdletBinding()]
param(
    [string]$RepoUrl = 'https://github.com/EngineXus-dev/midnight-provisioner.git',
    [string]$Branch = 'feat/nightglass-phase-01'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$source = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ($RepoUrl -ne 'https://github.com/EngineXus-dev/midnight-provisioner.git') { throw 'Unexpected remote repository. Refusing.' }
if ($Branch -ne 'feat/nightglass-phase-01') { throw 'Unexpected branch. Refusing.' }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Install Git for Windows first.' }
if (-not (Test-Path (Join-Path $source 'midnight_provisioner\hypervisor.py'))) { throw 'Midnight Provisioner source files are missing.' }
$paths = @('.github', '.gitignore', 'LICENSE', 'README.md', 'docs', 'midnight_provisioner', 'pyproject.toml', 'scripts', 'tests')
$temp = Join-Path ([IO.Path]::GetTempPath()) ('midnight-provisioner-stage-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp -ErrorAction Stop | Out-Null
try {
    & git clone --no-checkout -- $RepoUrl $temp
    if ($LASTEXITCODE -ne 0) { throw 'Repository clone failed. Check credentials.' }
    Push-Location $temp
    try {
        & git fetch origin $Branch
        if ($LASTEXITCODE -ne 0) { throw 'Development branch missing. Stop rather than pushing to main.' }
        & git checkout -b $Branch --track "origin/$Branch"
        if ($LASTEXITCODE -ne 0) { throw 'Branch checkout failed.' }
        foreach ($relative in $paths) {
            $from = Join-Path $source $relative
            $to = Join-Path $temp $relative
            if (-not (Test-Path -LiteralPath $from)) { throw "Missing required project path: $relative" }
            if (Test-Path -LiteralPath $from -PathType Container) {
                New-Item -ItemType Directory -Force -Path $to | Out-Null
                Copy-Item -Path (Join-Path $from '*') -Destination $to -Recurse -Force
            } else {
                Copy-Item -LiteralPath $from -Destination $to -Force
            }
        }
        & git add -- $paths
        if ($LASTEXITCODE -ne 0) { throw 'Git staging failed.' }
        Write-Host 'Changes staged for Midnight Provisioner feature branch:' -ForegroundColor Cyan
        & git diff --cached --stat
        $reply = Read-Host 'Type PUSH-MIDNIGHT_PROVISIONER to commit and push reviewed project files'
        if ($reply -cne 'PUSH-MIDNIGHT_PROVISIONER') { Write-Host 'Cancelled; no remote changes.'; return }
        & git diff --cached --quiet
        if ($LASTEXITCODE -eq 0) { Write-Host 'No changes to push.'; return }
        & git commit -m 'feat: import Midnight Provisioner Phase 1 application and tests'
        if ($LASTEXITCODE -ne 0) { throw 'Commit failed. Check Git user.name and user.email.' }
        & git push origin "HEAD:refs/heads/$Branch"
        if ($LASTEXITCODE -ne 0) { throw 'Push failed (no forced update performed).' }
        Write-Host 'Published to private feature branch. Review the PR before merging.' -ForegroundColor Green
    } finally { Pop-Location }
} finally {
    # Leave the staging clone for troubleshooting; no potentially destructive automatic removal.
    Write-Host "Temporary staging clone: $temp"
}
