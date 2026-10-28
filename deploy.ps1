[CmdletBinding()]
param(
    [ValidateSet('Prepare', 'Deploy', 'Status', 'Logs')][string]$Action = 'Deploy',
    [string]$SshHost = $(if ($env:THREE_MM_DEPLOY_HOST) { $env:THREE_MM_DEPLOY_HOST } else { 'raspberry@rasp-3mm.local' }),
    [string]$WslDistribution = 'Ubuntu-26.04',
    [ValidateSet('aarch64', 'x86_64')][string]$Architecture = 'aarch64',
    [ValidateSet('3.12', '3.13', '3.14')][string]$PythonVersion = '3.13',
    [string[]]$TestPaths = @(),
    [string]$Bundle,
    [switch]$WithoutImages,
    [switch]$WithAgent
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
if ($SshHost -notmatch '^[a-zA-Z0-9_][a-zA-Z0-9_.-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*$') {
    throw 'SshHost must be user@hostname (configure SSH options in ~/.ssh/config).'
}

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments, [switch]$Capture)
    if ($Capture) {
        $output = & $Program @Arguments
        if ($LASTEXITCODE -ne 0) { throw "$Program failed ($LASTEXITCODE)." }
        return ($output -join "`n").Trim()
    }
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed ($LASTEXITCODE). Use -Action Status or -Action Logs after an interrupted deployment." }
}

function Invoke-Wsl {
    param([string[]]$Arguments, [switch]$Capture)
    Invoke-Checked -Program wsl.exe -Arguments (@('-d', $WslDistribution, '--exec') + $Arguments) -Capture:$Capture
}

$localState = Join-Path $repo '.runtime/deploy'
New-Item -ItemType Directory -Force -Path $localState | Out-Null
$targetFile = Join-Path $localState ("target-$SshHost.json")

# Observation must never build, upload or start a job.
if ($Action -in @('Status', 'Logs')) {
    if (-not (Test-Path -LiteralPath $targetFile)) { throw 'No recorded deployment attempt for this SSH target.' }
    $record = Get-Content -Raw -LiteralPath $targetFile | ConvertFrom-Json
    $key = $record.key
    if ($key -notmatch '^[0-9a-f]{64}$') { throw 'Invalid saved deployment key.' }
    if ($Action -eq 'Status') {
        $observe = 'sudo python3 -c ''from pathlib import Path; p=Path("/var/lib/3mm/local-deploy/KEY/status.json"); print(p.read_text() if p.is_file() else "not_started")'''
        $observe = $observe.Replace('KEY', $key)
    } else {
        $observe = "sudo journalctl --no-pager -n 100 -f -u 3mm-deploy-$($key.Substring(0, 24)).service"
    }
    Invoke-Checked -Program ssh -Arguments @('-t', $SshHost, $observe)
    return
}

$linuxRepo = Invoke-Wsl -Arguments @('wslpath', '-a', '-u', $repo) -Capture
$resultPath = Join-Path $localState ('client-' + [guid]::NewGuid().ToString('N') + '.json')
$linuxResult = Invoke-Wsl -Arguments @('wslpath', '-a', '-u', $resultPath) -Capture
$arguments = @('python3', "$linuxRepo/tools/deploy.py")
if ($Bundle) {
    $Bundle = (Resolve-Path -LiteralPath $Bundle).Path
    $linuxBundle = Invoke-Wsl -Arguments @('wslpath', '-a', '-u', $Bundle) -Capture
    $arguments += @('validate', '--bundle', $linuxBundle)
} else {
    $arguments += @('prepare', '--repo', $linuxRepo, '--architecture', $Architecture, '--python-version', $PythonVersion)
    if ($WithoutImages) { $arguments += '--without-images' }
    if ($TestPaths.Count) { $arguments += @('--test-paths') + $TestPaths }
}
$arguments += @('--result', $linuxResult)
if ($WithAgent) { $arguments += '--with-agent' }
try {
    Invoke-Wsl -Arguments $arguments
    $prepared = Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json
    $Bundle = Invoke-Wsl -Arguments @('wslpath', '-w', $prepared.bundle) -Capture
} finally { Remove-Item -LiteralPath $resultPath -Force -ErrorAction SilentlyContinue }
$ready = Get-Content -Raw -LiteralPath (Join-Path $Bundle 'ready.json') | ConvertFrom-Json
$key = $ready.key
if ($key -notmatch '^[0-9a-f]{64}$' -or $key -ne $prepared.key -or $ready.kit_sha256 -notmatch '^[0-9a-f]{64}$') {
    throw 'Invalid prepared deployment identity.'
}
$kit = Join-Path $Bundle 'kit.tar.gz'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $kit).Hash.ToLowerInvariant() -ne $ready.kit_sha256) {
    throw 'Kit changed after validation; nothing transferred.'
}
Write-Host "Ready: $($ready.release_id) (reused: $($prepared.reused))"
Write-Host "Bundle: $Bundle"
if ($Action -eq 'Prepare') { return }

# Keep a receipt before network dispatch: a lost SSH acknowledgement is uncertain.
$temporaryReceipt = "$targetFile.$([guid]::NewGuid().ToString('N')).tmp"
@{ key = $key; bundle = $Bundle; target = $SshHost; attempted_at = [DateTime]::UtcNow.ToString('o') } |
    ConvertTo-Json | Set-Content -LiteralPath $temporaryReceipt -Encoding UTF8
Move-Item -LiteralPath $temporaryReceipt -Destination $targetFile -Force
$remoteKit = "3mm-deploy-$key.tar.gz"
Invoke-Checked -Program scp -Arguments @($kit, "${SshHost}:$remoteKit")
# Names/digests are strict generated hex; no user input enters remote shell code.
# SSH and sudo prompt normally. The root worker belongs to systemd, not SSH.
$remoteCommand = "printf '%s  %s\n' '$($ready.kit_sha256)' '$remoteKit' | sha256sum --check --status && tar -xOf '$remoteKit' deploy_remote.py | sudo python3 - start --kit '$remoteKit' --sha256 '$($ready.kit_sha256)' --follow"
Write-Host 'Starting or observing detached deployment. Ctrl+C closes only the log viewer.'
Invoke-Checked -Program ssh -Arguments @('-t', $SshHost, $remoteCommand)
