$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot '../../deploy.ps1'
$tokens = $null; $errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count) { throw ($errors | Out-String) }
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('3mm-deploy-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
Copy-Item -LiteralPath $scriptPath -Destination (Join-Path $testRoot 'deploy.ps1')
$testScript = Join-Path $testRoot 'deploy.ps1'
$global:testBundle = Join-Path $testRoot 'bundle'
New-Item -ItemType Directory -Path $testBundle | Out-Null
[IO.File]::WriteAllText((Join-Path $testBundle 'kit.tar.gz'), 'checked bytes')
$global:testKey = 'a' * 64
$global:testSha = (Get-FileHash -LiteralPath (Join-Path $testBundle 'kit.tar.gz')).Hash.ToLowerInvariant()
@{ key = $testKey; release_id = 'local-test'; kit_sha256 = $testSha } | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $testBundle 'ready.json')
$global:testCopies = @(); $global:testSsh = @(); $global:testWsl = @()
function wsl.exe {
    $global:testWsl += ,@($args)
    $global:LASTEXITCODE = 0
    if ($args[3] -eq 'wslpath') { $args[-1]; return }
    $index = [array]::IndexOf($args, '--result')
    @{ bundle = $global:testBundle; key = $global:testKey; reused = $true } | ConvertTo-Json |
        Set-Content -LiteralPath $args[$index + 1]
}
function scp { $global:testCopies += ,@($args); $global:LASTEXITCODE = 0 }
function ssh { $global:testSsh += ,@($args); $global:LASTEXITCODE = 0 }
try {
    & $testScript -Action Prepare -WithAgent
    if ($testCopies.Count -or $testSsh.Count) { throw 'Prepare contacted a device' }
    if ($testWsl[-2] -notcontains '--with-agent') { throw 'Explicit Agent selection was lost' }
    & $testScript -Bundle $testBundle
    if ($testCopies.Count -ne 1 -or $testSsh.Count -ne 1) { throw 'Expected one upload and one SSH invocation' }
    if ($testCopies[0][-1] -ne "raspberry@rasp-3mm.local:3mm-deploy-$testKey.tar.gz") { throw 'Wrong upload target' }
    if ($testSsh[0][-1] -notlike '*--follow' -or $testSsh[0][-1] -notlike '*sha256sum --check --status*') { throw 'Launch lost checksum or detached observer' }
    $before = $testWsl.Count
    & $testScript -Action Status
    & $testScript -Action Logs
    if ($testWsl.Count -ne $before -or $testCopies.Count -ne 1 -or $testSsh.Count -ne 3) { throw 'Observation prepared or uploaded a job' }
    $refused = $false
    try { & $testScript -SshHost 'bad;command' } catch { $refused = $true }
    if (-not $refused) { throw 'Unsafe SSH target accepted' }
    [IO.File]::AppendAllText((Join-Path $testBundle 'kit.tar.gz'), 'changed')
    $refused = $false
    try { & $testScript -Bundle $testBundle } catch { $refused = $_.Exception.Message -like '*changed after validation*' }
    if (-not $refused -or $testCopies.Count -ne 1) { throw 'Changed kit reached transfer' }
    Write-Host 'PowerShell deployment checks passed (command doubles; no network).'
} finally {
    # This exact randomly created test directory is the only deletion target.
    if ((Resolve-Path -LiteralPath $testRoot).Path -ne $testRoot) { throw 'Unexpected test cleanup target' }
    Remove-Item -LiteralPath $testRoot -Recurse -Force
}
