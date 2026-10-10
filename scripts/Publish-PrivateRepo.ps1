# Standalone GitHub publish script. Only operates on Nightglass project directory.
# Requires GitHub CLI (gh) and git; never pulls, overwrites, deletes, or merges existing repos.
[CmdletBinding()]
param([string]$RepoName = 'nightglass-workspaces')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $projectRoot
try {
    if (-not (Test-Path 'pyproject.toml') -or -not (Test-Path 'nightglass\ui.py')) {
        throw 'Not running inside a Nightglass source checkout.'
    }
    if ($RepoName -notmatch '^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$') {
        throw 'Unsafe GitHub repository name.'
    }
    foreach ($program in @('git', 'gh')) {
        if (-not (Get-Command $program -ErrorAction SilentlyContinue)) { throw "Missing program: $program" }
    }
    & gh auth status
    if ($LASTEXITCODE -ne 0) { throw 'Sign into GitHub CLI: gh auth login' }
    if (-not (Test-Path '.git')) {
        & git init -b main
        if ($LASTEXITCODE -ne 0) { throw 'git init failed' }
        & git add -- .
        if ($LASTEXITCODE -ne 0) { throw 'git add failed' }
        & git commit -m 'Initial Nightglass workspace controller'
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed; configure git user.name and user.email' }
    } else {
        $changes = & git status --porcelain
        if ($changes) { throw 'Existing git checkout has local changes. Commit or stash them manually first.' }
        $origin = & git remote get-url origin 2>$null
        if ($LASTEXITCODE -eq 0 -and $origin) { throw 'Existing origin remote detected. Refusing to alter it.' }
    }
    Write-Host 'Creating a NEW PRIVATE repository. Existing GitHub repositories are untouched.'
    & gh repo create $RepoName --private --source . --remote origin --push
    if ($LASTEXITCODE -ne 0) { throw 'Private repository creation/push failed. No forced updates attempted.' }
} finally {
    Pop-Location
}
