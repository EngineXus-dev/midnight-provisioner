#requires -Version 5.1
<#
  Small bootstrap for users whose ORIGINAL Midnight Provisioner checkout is still on
  main and does not yet contain scripts/testing/Run-Midnight-Provisioner-Fedora-Checks.ps1.
  Downloads that exact script from YOUR verified GitHub remote into a
  NEW temp folder, then executes it. No worktree reset, pull or merge.
#>
[CmdletBinding()]
param([string]$RepoPath = "")
$ErrorActionPreference = "Stop"
$branch = "main"
try {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git CLI not available."
    }
    $candidates = @()
    if ($RepoPath.Trim()) {
        $candidates += $RepoPath
    } else {
        $candidates += (Get-Location).Path
        $candidates += (Join-Path ([Environment]::GetFolderPath("MyDocuments")) "midnight-provisioner")
    }
    $repo = $null
    # Windows PowerShell 5.1 turns redirected native stderr (e.g. git's "not a git
    # repository") into a terminating error under 'Stop'; probes must continue instead.
    $ErrorActionPreference = 'Continue'
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) { continue }
        $candidateRoot = (& git -C $candidate rev-parse --show-toplevel 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $candidateRoot) { continue }
        $origin = (& git -C $candidateRoot remote get-url origin 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { continue }
        if ($origin -match '(?i)(^|[:/])EngineXus-dev/midnight-provisioner(\.git)?$') {
            $repo = (Resolve-Path -LiteralPath $candidateRoot).Path
            break
        }
    }
    $ErrorActionPreference = 'Stop'
    if (-not $repo) {
        throw "Expected Midnight Provisioner Git checkout not found; run from its original directory or pass -RepoPath."
    }
    Write-Host "Midnight Provisioner Fedora Docker test bootstrap" -ForegroundColor Cyan
    Write-Host "Original repo: $repo"
    Write-Host "Fetching only the integration branch. No merge or checkout change."
    & git -C $repo fetch --no-tags origin ("refs/heads/{0}:refs/remotes/origin/{0}" -f $branch)
    if ($LASTEXITCODE -ne 0) { throw "Git fetch failed." }
    $destination = Join-Path ([IO.Path]::GetTempPath()) ("Midnight-Provisioner-Docker-Launcher-" + [guid]::NewGuid().ToString("N"))
    [void](New-Item -ItemType Directory -Path $destination -ErrorAction Stop)
    $runner = Join-Path $destination "Run-Midnight-Provisioner-Fedora-Checks.ps1"
    # Git outputs checked-in text; temp target is NEW and not in the project.
    & git -C $repo show ("refs/remotes/origin/{0}:scripts/testing/Run-Midnight-Provisioner-Fedora-Checks.ps1" -f $branch) |
        Set-Content -LiteralPath $runner -Encoding UTF8
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $runner -PathType Leaf)) {
        throw "Unable to retrieve the versioned Midnight Provisioner Fedora runner."
    }
    Write-Host "Starting the versioned Fedora test runner..."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runner -RepoPath $repo
    exit $LASTEXITCODE
} catch {
    Write-Host ("[FAILED] " + $_.Exception.Message) -ForegroundColor Red
    Write-Host "Original checkout and all existing files remain untouched."
    exit 1
}
