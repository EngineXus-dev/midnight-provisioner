#requires -Version 5.1
<#
Nightglass isolated offline verification launcher for native Windows.
DEFAULT: PREVIEW ONLY. All non-default operations require named switches.
- Never checks out, resets, cleans, merges or rewrites the user's local source.
- FetchRefs updates only Git remote-tracking metadata if explicitly requested.
- AuditStack reads existing local Git objects/refs, creates ONE isolated temp
  copy of an audited Python script, then runs a read-only local graph check.
- RunDockerGate is additionally guarded by exact literal consent, and uses
  new detached worktrees and isolated Docker synthetic checks.
- No Windows 11 setup, Ubuntu/WSL install, EFI, partition, USB or VM start.
- No GitHub Actions, internet script installers, WinUtil or debloat actions.
#>
[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [switch]$FetchRefs,
    [switch]$AuditStack,
    [switch]$RunDockerGate,
    [switch]$PullPythonImages,
    [switch]$BuildFedoraImage,
    [string]$ConfirmOfflineTests = '',
    [string]$ExpectedCommit = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$branch = 'security/backup-boundary-fix'
$requiredConsent = 'RUN NIGHTGLASS OFFLINE TESTS'
$repoUrlPattern = '^(?:https://github\.com/|git@github\.com:)EngineXus-dev/nightglass-workspaces(?:\.git)?/?$'

Write-Host 'NIGHTGLASS / WINDOWS OFFLINE VERIFICATION'
Write-Host ('Target branch: ' + $branch)

if (($PullPythonImages -or $BuildFedoraImage) -and -not $RunDockerGate) {
    throw 'Docker image pull/build options require an explicitly selected -RunDockerGate.'
}
if ($RunDockerGate -and $ConfirmOfflineTests -cne $requiredConsent) {
    throw ('No Docker test approval. Supply -ConfirmOfflineTests "' +
           $requiredConsent + '" only when ready.')
}
if ($ExpectedCommit -ne '' -and $ExpectedCommit -cnotmatch '^[0-9a-f]{40}$') {
    throw 'ExpectedCommit must be a full lowercase 40-character Git SHA.'
}
if (-not ($FetchRefs -or $AuditStack -or $RunDockerGate)) {
    Write-Host 'PLAN ONLY: no Git calls, filesystem writes, Docker access or Windows changes.'
    Write-Host 'Optional -FetchRefs: fetch remote branch metadata without a checkout.'
    Write-Host 'Optional -AuditStack: inspect already-fetched branch refs and workflow policy.'
    Write-Host 'Optional -RunDockerGate: needs explicit consent and tests in isolated Docker.'
    Write-Host 'Optional -PullPythonImages or -BuildFedoraImage: image preparation opt-ins.'
    Write-Host 'Never merges pull requests or installs Windows/Fedora.'
    exit 0
}

if ($RepoPath -eq '') { $RepoPath = (Get-Location).Path }
$repoPathValue = [System.IO.Path]::GetFullPath($RepoPath)

$git = Get-Command 'git.exe' -CommandType Application -ErrorAction SilentlyContinue
if ($null -eq $git) {
    $git = Get-Command 'git' -CommandType Application -ErrorAction Stop
}
$gitExe = $git.Source
$python = Get-Command 'python.exe' -CommandType Application -ErrorAction SilentlyContinue
if ($null -eq $python) {
    $python = Get-Command 'python' -CommandType Application -ErrorAction Stop
}
$pythonExe = $python.Source

$rootText = @(& $gitExe -C $repoPathValue rev-parse --show-toplevel)
if ($LASTEXITCODE -ne 0 -or $rootText.Count -ne 1) {
    throw 'Nightglass repository root could not be established.'
}
$root = [System.IO.Path]::GetFullPath([string]$rootText[0])
$remoteText = @(& $gitExe -C $root remote get-url origin)
if ($LASTEXITCODE -ne 0 -or $remoteText.Count -ne 1) {
    throw 'Git origin could not be confirmed.'
}
if ([string]$remoteText[0] -cnotmatch $repoUrlPattern) {
    throw 'Refusing to audit a repository with a non-Nightglass GitHub origin.'
}
Write-Host ('Confirmed checkout: ' + $root)

if ($FetchRefs) {
    Write-Host 'Fetching remote-tracking metadata ONLY. No pull, checkout, merge or reset.'
    & $gitExe -C $root fetch --no-tags origin
    if ($LASTEXITCODE -ne 0) {
        throw 'Fetch failed; no test commands were started.'
    }
}
if (-not ($AuditStack -or $RunDockerGate)) {
    Write-Host 'Fetch phase complete. No tests or OS operations executed.'
    exit 0
}

$ref = 'refs/remotes/origin/' + $branch
$shaText = @(& $gitExe -C $root rev-parse --verify $ref)
if ($LASTEXITCODE -ne 0 -or $shaText.Count -ne 1) {
    throw 'Candidate branch ref unavailable. Explicitly select -FetchRefs first.'
}
$sha = [string]$shaText[0]
if ($sha -cnotmatch '^[0-9a-f]{40}$') {
    throw 'Candidate SHA is invalid.'
}
if ($ExpectedCommit -ne '' -and $sha -cne $ExpectedCommit) {
    throw 'Candidate branch changed; expected SHA mismatch. Stop and review new commits.'
}
Write-Host ('Candidate Git SHA: ' + $sha)

$temp = Join-Path $env:TEMP ('Nightglass-Offline-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $temp) { throw 'Refusing to reuse an existing temp directory.' }
New-Item -ItemType Directory -Path $temp -ErrorAction Stop | Out-Null
Write-Host ('Separate temporary scripts folder: ' + $temp)

function Copy-GitSourceToNewTemp {
    param(
        [Parameter(Mandatory=$true)][string]$ScriptPath,
        [Parameter(Mandatory=$true)][string]$FileName
    )
    if ($ScriptPath -notmatch '^scripts/[A-Za-z0-9_.-]+\.py$' -or
        $FileName -notmatch '^[A-Za-z0-9_.-]+\.py$') {
        throw 'Unexpected program path in pinned candidate Git object.'
    }
    $objectRef = $sha + ':' + $ScriptPath
    $lines = @(& $gitExe -C $root show $objectRef)
    if ($LASTEXITCODE -ne 0 -or $lines.Count -eq 0) {
        throw ('Cannot retrieve audited script from pinned Git object: ' + $FileName)
    }
    $destination = Join-Path $temp $FileName
    if (Test-Path -LiteralPath $destination) {
        throw 'Refusing to overwrite a previously retrieved Python script.'
    }
    $lines | Set-Content -LiteralPath $destination -Encoding UTF8 -ErrorAction Stop
    return $destination
}

if ($AuditStack) {
    $audit = Copy-GitSourceToNewTemp -ScriptPath 'scripts/Audit-Nightglass-PR-Stack.py' -FileName 'Audit-Nightglass-PR-Stack.py'
    Write-Host 'Running read-only local Git ancestry and CI policy audit.'
    & $pythonExe -B $audit --repo $root --verify --expected-candidate-sha $sha
    if ($LASTEXITCODE -ne 0) {
        throw 'PR stack audit BLOCKED. No Docker tests started by this launcher.'
    }
    Write-Host 'Local ancestry audit returned PASS (NOT permission to merge).'
}

if ($RunDockerGate) {
    $runner = Copy-GitSourceToNewTemp -ScriptPath 'scripts/Run-Nightglass-Offline-Release-Gate.py' -FileName 'Run-Nightglass-Offline-Release-Gate.py'
    $arguments = @('-B', $runner, '--repo', $root, '--run', '--expected-commit', $sha)
    if ($PullPythonImages) {
        $arguments += '--pull-python-images'
    }
    if ($BuildFedoraImage) {
        $arguments += '--build-fedora-image'
    }
    Write-Host 'Running explicit isolated Docker test gate; no Windows/Linux installation.'
    & $pythonExe @arguments
    if ($LASTEXITCODE -ne 0) {
        throw 'Offline test gate INCOMPLETE / BLOCKED. Examine private local log.'
    }
    Write-Host 'Synthetic test gate reported PASS. Real Fedora hardware acceptance remains PENDING.'
}

Write-Host 'Finished selected local checks. All GitHub PRs remain unmerged.'
