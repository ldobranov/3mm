[CmdletBinding()]
param(
    [string]$SshHost = $(if ($env:THREE_MM_DEPLOY_HOST) { $env:THREE_MM_DEPLOY_HOST } else { 'rasp-3mm' }),
    [string]$RemoteName = $(if ($env:THREE_MM_DEPLOY_REMOTE) { $env:THREE_MM_DEPLOY_REMOTE } else { 'origin' }),
    [string]$FrontendOrigin = $(if ($env:THREE_MM_FRONTEND_ORIGIN) { $env:THREE_MM_FRONTEND_ORIGIN } else { 'http://192.168.1.88' }),
    [int]$HealthTimeoutSeconds = 90,
    [switch]$IncludeWorkingTree,
    [switch]$InteractiveSudo,
    [switch]$RollbackTestAfterHealth,
    [switch]$SkipPush
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [string[]]$Arguments = @(),
        [switch]$Capture
    )

    if ($Capture) {
        $output = & $Command @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            throw "Command failed ($exitCode): $Command $($Arguments -join ' ')`n$($output -join [Environment]::NewLine)"
        }
        return $output
    }

    & $Command @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Command failed ($exitCode): $Command $($Arguments -join ' ')"
    }
}

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Wait-Http {
    param(
        [string]$Url,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return
            }
            $lastError = "HTTP $($response.StatusCode)"
        }
        catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    }

    throw "Health check failed for $Url after $TimeoutSeconds seconds. Last error: $lastError"
}

function Copy-WorkingTreeFiles {
    param(
        [string]$RepositoryRoot,
        [string]$DestinationRoot
    )

    $paths = Invoke-Native -Command 'git' -Arguments @(
        '-c', 'core.quotepath=false',
        'ls-files', '--cached', '--others', '--exclude-standard'
    ) -Capture

    foreach ($relativePath in $paths) {
        if ([string]::IsNullOrWhiteSpace($relativePath)) {
            continue
        }
        $platformPath = $relativePath.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
        $source = Join-Path $RepositoryRoot $platformPath
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            continue
        }
        $destination = Join-Path $DestinationRoot $platformPath
        $destinationDirectory = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$originalLocation = Get-Location
$tempRoot = $null

try {
    Set-Location $repoRoot

    if ($SshHost -notmatch '^[A-Za-z0-9._@-]+$') {
        throw "SSH host contains unsupported characters: $SshHost"
    }
    if ($FrontendOrigin -notmatch '^https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?$') {
        throw "Frontend origin must be a plain HTTP(S) origin without a path: $FrontendOrigin"
    }
    $versionFile = Join-Path $repoRoot 'VERSION'
    if (-not (Test-Path -LiteralPath $versionFile -PathType Leaf)) {
        throw "Project VERSION file was not found: $versionFile"
    }
    $projectVersion = [System.IO.File]::ReadAllText($versionFile).Trim()
    if ($projectVersion -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') {
        throw "Project VERSION is not a supported semantic version: $projectVersion"
    }
    if ($RollbackTestAfterHealth -and -not $IncludeWorkingTree) {
        throw 'RollbackTestAfterHealth requires IncludeWorkingTree for an explicit test snapshot.'
    }

    Write-Step 'Checking local prerequisites'
    foreach ($command in @('git', 'pnpm', 'tar', 'ssh', 'scp')) {
        Assert-Command $command
    }

    $insideWorkTree = (Invoke-Native -Command 'git' -Arguments @(
        'rev-parse', '--is-inside-work-tree'
    ) -Capture | Select-Object -Last 1).ToString().Trim()
    if ($insideWorkTree -ne 'true') {
        throw 'deploy.ps1 must be run from a Git working tree.'
    }

    $statusBeforeBuild = (Invoke-Native -Command 'git' -Arguments @(
        'status', '--porcelain=v1', '--untracked-files=all'
    ) -Capture) -join "`n"
    $isDirty = -not [string]::IsNullOrWhiteSpace($statusBeforeBuild)
    if ($isDirty -and -not $IncludeWorkingTree) {
        throw "Git working tree is not clean. Use -IncludeWorkingTree only for an intentional test deployment.`n$statusBeforeBuild"
    }

    $branch = (Invoke-Native -Command 'git' -Arguments @(
        'symbolic-ref', '--quiet', '--short', 'HEAD'
    ) -Capture | Select-Object -Last 1).ToString().Trim()
    if ([string]::IsNullOrWhiteSpace($branch)) {
        throw 'Detached HEAD deployments are not allowed.'
    }

    $commit = (Invoke-Native -Command 'git' -Arguments @(
        'rev-parse', 'HEAD'
    ) -Capture | Select-Object -Last 1).ToString().Trim().ToLowerInvariant()
    if ($commit -notmatch '^[0-9a-f]{40}$') {
        throw "Unexpected Git commit value: $commit"
    }
    $shortCommit = $commit.Substring(0, 12)
    $releasePrefix = $(
        if ($RollbackTestAfterHealth) { "rollback-test-worktree-$shortCommit" }
        elseif ($isDirty) { "worktree-$shortCommit" }
        else { $shortCommit }
    )
    $releaseId = "$releasePrefix-$(Get-Date -Format 'yyyyMMddHHmmss')"
    Write-Host "Branch:  $branch"
    Write-Host "Commit:  $commit"
    Write-Host "Version: $projectVersion"
    Write-Host "Dirty:   $isDirty"
    Write-Host "Release: $releaseId"

    if (-not $isDirty) {
        if (-not $SkipPush) {
            Write-Step "Pushing the exact commit to $RemoteName/$branch"
            Invoke-Native -Command 'git' -Arguments @(
                'push', $RemoteName, "HEAD:refs/heads/$branch"
            )
        }

        Write-Step 'Verifying the exact remote commit'
        $remoteLines = Invoke-Native -Command 'git' -Arguments @(
            'ls-remote', '--heads', $RemoteName, "refs/heads/$branch"
        ) -Capture
        $remoteLine = ($remoteLines | Select-Object -Last 1).ToString().Trim()
        if ($remoteLine -notmatch '^([0-9a-fA-F]{40})\s+') {
            throw "Could not resolve $RemoteName/$branch."
        }
        if ($Matches[1].ToLowerInvariant() -ne $commit) {
            throw "Remote verification failed for $RemoteName/$branch."
        }
    }
    else {
        Write-Warning 'Deploying the explicit working-tree snapshot; Git push is intentionally skipped.'
    }

    Write-Step 'Installing locked frontend dependencies'
    Invoke-Native -Command 'pnpm' -Arguments @(
        '--dir', 'frontend', 'install', '--frozen-lockfile'
    )

    Write-Step 'Running frontend tests and type-check'
    Invoke-Native -Command 'pnpm' -Arguments @(
        '--dir', 'frontend', 'exec', 'vitest', 'run'
    )
    Invoke-Native -Command 'pnpm' -Arguments @(
        '--dir', 'frontend', 'run', 'type-check'
    )

    Write-Step 'Building the frontend locally'
    Invoke-Native -Command 'pnpm' -Arguments @(
        '--dir', 'frontend', 'run', 'build-only'
    )

    $distIndex = Join-Path $repoRoot 'frontend\dist\index.html'
    if (-not (Test-Path -LiteralPath $distIndex -PathType Leaf)) {
        throw "Frontend build did not produce $distIndex"
    }
    $statusAfterBuild = (Invoke-Native -Command 'git' -Arguments @(
        'status', '--porcelain=v1', '--untracked-files=all'
    ) -Capture) -join "`n"
    if ($statusAfterBuild -ne $statusBeforeBuild) {
        throw "The frontend build changed tracked or unignored files. Deployment stopped.`n$statusAfterBuild"
    }

    Write-Step 'Checking SSH connectivity'
    Invoke-Native -Command 'ssh' -Arguments @(
        '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', $SshHost, 'true'
    )
    if (-not $InteractiveSudo) {
        Invoke-Native -Command 'ssh' -Arguments @(
            '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            $SshHost, 'sudo -n true'
        )
    }
    $rollbackTargetBefore = $null
    if ($RollbackTestAfterHealth) {
        $rollbackTargetBefore = (Invoke-Native -Command 'ssh' -Arguments @(
            '-o', 'BatchMode=yes', $SshHost, 'readlink -f /opt/3mm/current'
        ) -Capture | Select-Object -Last 1).ToString().Trim()
        if ($rollbackTargetBefore -notmatch '^/opt/3mm/releases/[A-Za-z0-9._-]+$') {
            throw "Unexpected active release before rollback test: $rollbackTargetBefore"
        }
    }

    Write-Step 'Packaging the verified release snapshot'
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "3mm-deploy-$releaseId"
    $stageDir = Join-Path $tempRoot 'release'
    New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

    if ($isDirty) {
        Copy-WorkingTreeFiles -RepositoryRoot $repoRoot -DestinationRoot $stageDir
    }
    else {
        $sourceTar = Join-Path $tempRoot 'source.tar'
        Invoke-Native -Command 'git' -Arguments @(
            'archive', '--format=tar', '--output', $sourceTar, $commit
        )
        Invoke-Native -Command 'tar' -Arguments @('-xf', $sourceTar, '-C', $stageDir)
    }

    $stageDist = Join-Path $stageDir 'frontend\dist'
    New-Item -ItemType Directory -Path $stageDist -Force | Out-Null
    Copy-Item -Path (Join-Path $repoRoot 'frontend\dist\*') -Destination $stageDist -Recurse -Force

    $releaseMetadata = [ordered]@{
        release_id = $releaseId
        branch = $branch
        commit = $commit
        version = $projectVersion
        includes_working_tree = $isDirty
        created_at = (Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText(
        (Join-Path $stageDir '.3mm-release.json'),
        "$releaseMetadata`n",
        $utf8NoBom
    )

    $artifact = Join-Path $tempRoot "3mm-$releaseId.tar.gz"
    Invoke-Native -Command 'tar' -Arguments @('-czf', $artifact, '-C', $stageDir, '.')
    $artifactSha256 = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant()

    $remoteArchive = "/tmp/3mm-$releaseId.tar.gz"
    $remoteInstaller = "/tmp/3mm-install-$releaseId.sh"
    $normalizedInstaller = Join-Path $tempRoot 'install-systemd.sh'
    $installerContent = [System.IO.File]::ReadAllText(
        (Join-Path $repoRoot 'deployment\install-systemd.sh')
    ).Replace("`r`n", "`n")
    [System.IO.File]::WriteAllText(
        $normalizedInstaller,
        "$($installerContent.TrimEnd("`n"))`n",
        $utf8NoBom
    )

    Write-Step "Uploading release artifact to $SshHost"
    Invoke-Native -Command 'scp' -Arguments @(
        '-o', 'BatchMode=yes', $artifact, "${SshHost}:$remoteArchive"
    )
    Invoke-Native -Command 'scp' -Arguments @(
        '-o', 'BatchMode=yes', $normalizedInstaller, "${SshHost}:$remoteInstaller"
    )

    Write-Step 'Creating and activating the remote release'
    $sudoCommand = $(if ($InteractiveSudo) { 'sudo' } else { 'sudo -n' })
    $installerCommand = $(
        if ($RollbackTestAfterHealth) {
            "$sudoCommand env THREE_MM_INSTALLER_TEST_FAIL_AFTER_HEALTH=1 bash"
        }
        else {
            "$sudoCommand bash"
        }
    )
    $remoteCommand = "$installerCommand $remoteInstaller $remoteArchive $releaseId $FrontendOrigin '' $artifactSha256; result=`$?; rm -f $remoteInstaller; exit `$result"
    $sshArguments = @('-o', 'ConnectTimeout=10')
    if ($InteractiveSudo) {
        $sshArguments += '-tt'
    }
    else {
        $sshArguments += @('-o', 'BatchMode=yes')
    }
    $sshArguments += @($SshHost, $remoteCommand)
    if ($RollbackTestAfterHealth) {
        & ssh @sshArguments
        $installerExitCode = $LASTEXITCODE
        if ($installerExitCode -eq 0) {
            throw 'Rollback acceptance deployment unexpectedly succeeded.'
        }
    }
    else {
        Invoke-Native -Command 'ssh' -Arguments $sshArguments
    }

    Write-Step 'Checking the active runtime from the deployment machine'
    $originUri = [Uri]$FrontendOrigin
    $runtimeModeCommand = 'if systemctl is-active --quiet 3mm-setup.service; then printf setup; elif systemctl is-active --quiet 3mm-core.service && systemctl is-active --quiet 3mm-web.service && systemctl is-active --quiet 3mm-agent.service; then printf application; else printf unknown; fi'
    $runtimeMode = (Invoke-Native -Command 'ssh' -Arguments @(
        '-o', 'BatchMode=yes', $SshHost, $runtimeModeCommand
    ) -Capture | Select-Object -Last 1).ToString().Trim()
    if ($runtimeMode -eq 'setup') {
        Wait-Http -Url "http://$($originUri.Host):8895/ready" -TimeoutSeconds $HealthTimeoutSeconds
        Write-Host 'First-boot setup runtime is healthy.' -ForegroundColor Green
        Write-Host 'Open Wi-Fi network: 3mm Setup XXXX'
        Write-Host 'Setup page after joining it: http://10.42.0.1:8895/setup'
    }
    elseif ($runtimeMode -eq 'application') {
        Wait-Http -Url "http://$($originUri.Host):8887/ready" -TimeoutSeconds $HealthTimeoutSeconds
        Wait-Http -Url "$($FrontendOrigin.TrimEnd('/'))/user/login" -TimeoutSeconds $HealthTimeoutSeconds
    }
    else {
        throw 'The Raspberry Pi has neither a healthy setup runtime nor a complete application runtime.'
    }

    if ($RollbackTestAfterHealth) {
        $candidateState = (Invoke-Native -Command 'ssh' -Arguments @(
            '-o', 'BatchMode=yes', $SshHost,
            "if test -e /opt/3mm/releases/$releaseId; then echo present; else echo absent; fi"
        ) -Capture | Select-Object -Last 1).ToString().Trim()
        if ($candidateState -ne 'absent') {
            throw "Failed rollback release was not removed: $releaseId"
        }
        $rollbackTargetAfter = (Invoke-Native -Command 'ssh' -Arguments @(
            '-o', 'BatchMode=yes', $SshHost, 'readlink -f /opt/3mm/current'
        ) -Capture | Select-Object -Last 1).ToString().Trim()
        if ($rollbackTargetAfter -ne $rollbackTargetBefore) {
            throw "Rollback restored the wrong release: $rollbackTargetAfter"
        }
        $testBackupPath = "/var/lib/3mm/deploy-backups/$releaseId"
        $cleanupSshArguments = @('-o', 'ConnectTimeout=10')
        if ($InteractiveSudo) {
            $cleanupSshArguments += '-tt'
        }
        else {
            $cleanupSshArguments += @('-o', 'BatchMode=yes')
        }
        $cleanupSshArguments += @(
            $SshHost,
            "$sudoCommand rm -rf -- $testBackupPath"
        )
        Invoke-Native -Command 'ssh' -Arguments $cleanupSshArguments
        Write-Host "`nRollback acceptance test completed successfully." -ForegroundColor Green
        Write-Host "Rejected release: $releaseId"
        Write-Host "Restored release: $rollbackTargetAfter"
        Write-Host 'Restored runtime: healthy'
        exit 0
    }

    Write-Host "`nDeployment completed successfully." -ForegroundColor Green
    Write-Host "Release: $releaseId"
    Write-Host "Commit:  $commit"
    Write-Host "Web:     $FrontendOrigin"
}
catch {
    Write-Host "`nDeployment failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    if ($tempRoot -and (Test-Path -LiteralPath $tempRoot)) {
        $resolvedTempRoot = [System.IO.Path]::GetFullPath($tempRoot)
        $resolvedSystemTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        $tempLeaf = Split-Path -Leaf $resolvedTempRoot
        if ($resolvedTempRoot.StartsWith($resolvedSystemTemp) -and $tempLeaf.StartsWith('3mm-deploy-')) {
            Remove-Item -LiteralPath $resolvedTempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    Set-Location $originalLocation
}
