# Safely import Nightglass files into the already-created private GitHub repository.
# Requires Git for Windows and valid Git credentials. No force push, no filesystem deletion.
[CmdletBinding()]
param(
    [string]$RepoUrl = 'https://github.com/EngineXus-dev/nightglass-workspaces.git',
    [string]$Branch = 'feat/nightglass-phase-01'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$source = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ($RepoUrl -ne 'https://github.com/EngineXus-dev/nightglass-workspaces.git') { throw 'Unexpected remote repository. Refusing.' }
if ($Branch -ne 'feat/nightglass-phase-01') { throw 'Unexpected branch. Refusing.' }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Install Git for Windows first.' }
if (-not (Test-Path (Join-Path $source 'nightglass\hypervisor.py'))) { throw 'Nightglass source files are missing.' }
$paths = @('.github', '.gitignore', 'LICENSE', 'README.md', 'docs', 'nightglass', 'pyproject.toml', 'scripts', 'tests')
$temp = Join-Path ([IO.Path]::GetTempPath()) ('nightglass-stage-' + [guid]::NewGuid().ToString('N'))
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
        Write-Host 'Changes staged for Nightglass feature branch:' -ForegroundColor Cyan
        & git diff --cached --stat
        $reply = Read-Host 'Type PUSH-NIGHTGLASS to commit and push reviewed project files'
        if ($reply -cne 'PUSH-NIGHTGLASS') { Write-Host 'Cancelled; no remote changes.'; return }
        & git diff --cached --quiet
        if ($LASTEXITCODE -eq 0) { Write-Host 'No changes to push.'; return }
        & git commit -m 'feat: import Nightglass Phase 1 application and tests'
        if ($LASTEXITCODE -ne 0) { throw 'Commit failed. Check Git user.name and user.email.' }
        & git push origin "HEAD:refs/heads/$Branch"
        if ($LASTEXITCODE -ne 0) { throw 'Push failed (no forced update performed).' }
        Write-Host 'Published to private feature branch. Review the PR before merging.' -ForegroundColor Green
    } finally { Pop-Location }
} finally {
    # Leave the staging clone for troubleshooting; no potentially destructive automatic removal.
    Write-Host "Temporary staging clone: $temp"
}
