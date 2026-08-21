[CmdletBinding()]
param(
    [string]$SshHost = $(if ($env:THREE_MM_DEPLOY_HOST) { $env:THREE_MM_DEPLOY_HOST } else { 'rasp-3mm' }),
    [string]$RemoteName = $(if ($env:THREE_MM_DEPLOY_REMOTE) { $env:THREE_MM_DEPLOY_REMOTE } else { 'origin' }),
    [string]$FrontendOrigin = $(if ($env:THREE_MM_FRONTEND_ORIGIN) { $env:THREE_MM_FRONTEND_ORIGIN } else { 'http://192.168.1.88:8080' }),
    [int]$HealthTimeoutSeconds = 60,
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

    Write-Step 'Checking local prerequisites'
    foreach ($command in @('git', 'npm', 'tar', 'ssh', 'scp')) {
        Assert-Command $command
    }

    $insideWorkTree = (Invoke-Native -Command 'git' -Arguments @('rev-parse', '--is-inside-work-tree') -Capture | Select-Object -Last 1).ToString().Trim()
    if ($insideWorkTree -ne 'true') {
        throw 'deploy.ps1 must be run from a Git working tree.'
    }

    Write-Step 'Verifying that the Git working tree is clean'
    $status = (Invoke-Native -Command 'git' -Arguments @('status', '--porcelain=v1', '--untracked-files=all') -Capture) -join "`n"
    if (-not [string]::IsNullOrWhiteSpace($status)) {
        throw "Git working tree is not clean. Commit or remove these changes before deployment:`n$status"
    }

    $branch = (Invoke-Native -Command 'git' -Arguments @('symbolic-ref', '--quiet', '--short', 'HEAD') -Capture | Select-Object -Last 1).ToString().Trim()
    if ([string]::IsNullOrWhiteSpace($branch)) {
        throw 'Detached HEAD deployments are not allowed.'
    }

    $commit = (Invoke-Native -Command 'git' -Arguments @('rev-parse', 'HEAD') -Capture | Select-Object -Last 1).ToString().Trim().ToLowerInvariant()
    if ($commit -notmatch '^[0-9a-f]{40}$') {
        throw "Unexpected Git commit value: $commit"
    }
    $shortCommit = $commit.Substring(0, 12)
    $releaseId = "$shortCommit-$(Get-Date -Format 'yyyyMMddHHmmss')"
    Write-Host "Branch:  $branch"
    Write-Host "Commit:  $commit"
    Write-Host "Release: $releaseId"

    if (-not $SkipPush) {
        Write-Step "Pushing the exact commit to $RemoteName/$branch"
        Invoke-Native -Command 'git' -Arguments @('push', $RemoteName, "HEAD:refs/heads/$branch")
    }
    else {
        Write-Warning 'Git push was skipped; the remote commit will still be verified.'
    }

    Write-Step 'Verifying that GitHub contains the exact commit'
    $remoteLines = Invoke-Native -Command 'git' -Arguments @('ls-remote', '--heads', $RemoteName, "refs/heads/$branch") -Capture
    $remoteLine = ($remoteLines | Select-Object -Last 1).ToString().Trim()
    if ($remoteLine -notmatch '^([0-9a-fA-F]{40})\s+') {
        throw "Could not resolve $RemoteName/$branch after push."
    }
    $remoteCommit = $Matches[1].ToLowerInvariant()
    if ($remoteCommit -ne $commit) {
        throw "Remote verification failed. Local commit is $commit but $RemoteName/$branch is $remoteCommit."
    }

    Write-Step 'Installing locked frontend dependencies locally'
    Invoke-Native -Command 'npm' -Arguments @('--prefix', 'frontend', 'ci')

    Write-Step 'Running frontend type-check'
    Invoke-Native -Command 'npm' -Arguments @('--prefix', 'frontend', 'run', 'type-check')

    Write-Step 'Building the frontend locally (the Raspberry Pi does not need Node.js)'
    Invoke-Native -Command 'npm' -Arguments @('--prefix', 'frontend', 'run', 'build-only')

    $distIndex = Join-Path $repoRoot 'frontend\dist\index.html'
    if (-not (Test-Path -LiteralPath $distIndex -PathType Leaf)) {
        throw "Frontend build did not produce $distIndex"
    }

    $statusAfterBuild = (Invoke-Native -Command 'git' -Arguments @('status', '--porcelain=v1', '--untracked-files=all') -Capture) -join "`n"
    if (-not [string]::IsNullOrWhiteSpace($statusAfterBuild)) {
        throw "The build changed tracked or unignored files. Deployment stopped:`n$statusAfterBuild"
    }

    Write-Step 'Checking SSH connectivity and non-interactive sudo'
    Invoke-Native -Command 'ssh' -Arguments @(
        '-o', 'BatchMode=yes',
        '-o', 'ConnectTimeout=10',
        $SshHost,
        'sudo -n true'
    )

    Write-Step 'Packaging the exact commit with the prebuilt frontend artifact'
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "3mm-deploy-$releaseId"
    $stageDir = Join-Path $tempRoot 'release'
    New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

    $sourceTar = Join-Path $tempRoot 'source.tar'
    Invoke-Native -Command 'git' -Arguments @('archive', '--format=tar', '--output', $sourceTar, $commit)
    Invoke-Native -Command 'tar' -Arguments @('-xf', $sourceTar, '-C', $stageDir)

    $stageDist = Join-Path $stageDir 'frontend\dist'
    New-Item -ItemType Directory -Path $stageDist -Force | Out-Null
    Copy-Item -Path (Join-Path $repoRoot 'frontend\dist\*') -Destination $stageDist -Recurse -Force

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Join-Path $stageDir '.3mm-release-commit'), "$commit`n", $utf8NoBom)

    $artifact = Join-Path $tempRoot "3mm-$releaseId.tar.gz"
    Invoke-Native -Command 'tar' -Arguments @('-czf', $artifact, '-C', $stageDir, '.')
    if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) {
        throw 'Release archive was not created.'
    }

    $remoteArchive = "/tmp/3mm-$releaseId.tar.gz"
    $remoteScript = "/tmp/3mm-deploy-$releaseId.sh"
    $localRemoteScript = Join-Path $tempRoot 'remote-deploy.sh'

    $remoteScriptContent = @'
#!/usr/bin/env bash
set -Eeuo pipefail

archive=${1:?release archive is required}
release_id=${2:?release id is required}
expected_commit=${3:?expected commit is required}
frontend_origin=${4:?frontend origin is required}

install_root=/opt/3mm
releases_root="$install_root/releases"
release_dir="$releases_root/$release_id"
current_link="$install_root/current"
state_root=/var/lib/3mm
core_state="$state_root/core"
database="$core_state/3mm.db"
backup_root="$state_root/deploy-backups/$release_id"
services=(3mm-agent.service 3mm-core.service 3mm-web.service)
previous_release=""
activated=0
backup_created=0

log() {
  printf '\n==> %s\n' "$1"
}

install_units() {
  local source_release=$1
  local python_path=/opt/3mm/venv/bin/python
  if [[ -x "$source_release/.venv/bin/python" ]]; then
    python_path="$source_release/.venv/bin/python"
  fi

  for unit in 3mm-agent.service 3mm-core.service 3mm-web.service 3mm-setup.service; do
    sed "s|/opt/3mm/venv/bin/python|$python_path|g" \
      "$source_release/deployment/systemd/$unit" > "/etc/systemd/system/$unit"
    chmod 0644 "/etc/systemd/system/$unit"
    chown root:root "/etc/systemd/system/$unit"
  done
  systemctl daemon-reload
}

start_and_verify() {
  systemctl disable --now 3mm-setup.service >/dev/null 2>&1 || true
  systemctl enable --now "${services[@]}"

  local endpoints=(
    http://127.0.0.1:8890/ready
    http://127.0.0.1:8887/ready
    http://127.0.0.1:8080/user/login
  )
  local endpoint
  for endpoint in "${endpoints[@]}"; do
    local ready=0
    for _ in $(seq 1 60); do
      if curl -fsS --max-time 3 "$endpoint" >/dev/null; then
        ready=1
        break
      fi
      sleep 1
    done
    if [[ $ready -ne 1 ]]; then
      echo "Health check failed: $endpoint" >&2
      return 1
    fi
  done
}

rollback() {
  local exit_code=$?
  trap - ERR
  echo >&2
  echo "Deployment failed; rolling back to ${previous_release:-<none>}." >&2
  systemctl stop "${services[@]}" >/dev/null 2>&1 || true

  if [[ -n $previous_release && -d $previous_release ]]; then
    ln -sfn "$previous_release" "$current_link"
    install_units "$previous_release" || true
  fi

  if [[ $backup_created -eq 1 && -f "$backup_root/3mm.db" ]]; then
    install -o 3mm -g 3mm -m 0640 "$backup_root/3mm.db" "$database"
    rm -f "${database}-wal" "${database}-shm"
  fi

  if [[ -n $previous_release && -d $previous_release ]]; then
    start_and_verify || {
      systemctl --no-pager --full status "${services[@]}" >&2 || true
      echo 'Rollback was attempted but the previous release is not healthy.' >&2
    }
  fi

  if [[ $activated -eq 0 ]]; then
    rm -rf -- "$release_dir"
  fi
  rm -f -- "$archive"
  exit "$exit_code"
}
trap rollback ERR

if [[ ! $release_id =~ ^[a-zA-Z0-9._-]+$ ]]; then
  echo 'Release ID contains unsupported characters.' >&2
  exit 2
fi
if [[ ! $expected_commit =~ ^[0-9a-f]{40}$ ]]; then
  echo 'Expected commit is invalid.' >&2
  exit 2
fi
if [[ $frontend_origin != http://* && $frontend_origin != https://* ]]; then
  echo 'Frontend origin must use http or https.' >&2
  exit 2
fi
if [[ ! -f $archive ]]; then
  echo "Release archive does not exist: $archive" >&2
  exit 2
fi
if [[ -L $current_link ]]; then
  previous_release=$(readlink -f "$current_link")
fi
if [[ -z $previous_release || ! -d $previous_release ]]; then
  echo 'No valid current release exists; safe rollback is impossible.' >&2
  exit 2
fi
if [[ -e $release_dir ]]; then
  echo "Release already exists: $release_dir" >&2
  exit 2
fi

log 'Creating immutable release directory'
install -d -o root -g root -m 0755 "$releases_root" "$release_dir"
tar -xzf "$archive" -C "$release_dir"

actual_commit=$(tr -d '\r\n' < "$release_dir/.3mm-release-commit")
if [[ $actual_commit != "$expected_commit" ]]; then
  echo "Artifact commit mismatch: expected $expected_commit, got $actual_commit" >&2
  exit 2
fi
if [[ ! -f "$release_dir/frontend/dist/index.html" ]]; then
  echo 'Release does not contain frontend/dist/index.html.' >&2
  exit 2
fi

log 'Creating release-specific Python environment and installing dependencies'
python3 -m venv "$release_dir/.venv"
"$release_dir/.venv/bin/python" -m pip install \
  --disable-pip-version-check \
  --requirement "$release_dir/backend/requirements.txt"

log 'Stopping services and backing up persistent database state'
systemctl stop "${services[@]}"
install -d -o root -g root -m 0700 "$backup_root"
if [[ -f $database ]]; then
  install -o root -g root -m 0600 "$database" "$backup_root/3mm.db"
  backup_created=1
fi

log 'Installing release service definitions'
install_units "$release_dir"

log 'Running database migrations against persistent state'
install -d -o 3mm -g 3mm -m 0750 \
  "$core_state" \
  "$core_state/uploads" \
  "$core_state/uploads/modules" \
  "$core_state/extensions/backend" \
  "$core_state/extensions/frontend" \
  "$core_state/extensions/compiled"
runuser -u 3mm -- env \
  DATABASE_URL=sqlite:////var/lib/3mm/core/3mm.db \
  UPLOADS_DIR=/var/lib/3mm/core/uploads \
  PYTHONPATH="$release_dir" \
  "$release_dir/.venv/bin/python" "$release_dir/deployment/migrate_database.py"

log 'Activating release atomically'
ln -sfn "$release_dir" "$current_link"
activated=1

log 'Starting services and checking local readiness'
start_and_verify

log 'Deployment succeeded'
rm -f -- "$archive"
systemctl --no-pager --full status "${services[@]}"
trap - ERR
'@

    [System.IO.File]::WriteAllText(
        $localRemoteScript,
        $remoteScriptContent.Replace("`r`n", "`n") + "`n",
        $utf8NoBom
    )

    Write-Step "Uploading release artifact to $SshHost"
    Invoke-Native -Command 'scp' -Arguments @(
        '-o', 'BatchMode=yes',
        $artifact,
        "${SshHost}:$remoteArchive"
    )
    Invoke-Native -Command 'scp' -Arguments @(
        '-o', 'BatchMode=yes',
        $localRemoteScript,
        "${SshHost}:$remoteScript"
    )

    Write-Step 'Creating and activating the remote release'
    $remoteCommand = "sudo -n bash $remoteScript $remoteArchive $releaseId $commit $FrontendOrigin; result=`$?; rm -f $remoteScript; exit `$result"
    Invoke-Native -Command 'ssh' -Arguments @(
        '-o', 'BatchMode=yes',
        '-o', 'ConnectTimeout=10',
        $SshHost,
        $remoteCommand
    )

    Write-Step 'Checking the application from the deployment machine'
    $originUri = [Uri]$FrontendOrigin
    $hostForHealth = $originUri.Host
    Wait-Http -Url "http://${hostForHealth}:8887/ready" -TimeoutSeconds $HealthTimeoutSeconds
    Wait-Http -Url "$($FrontendOrigin.TrimEnd('/'))/user/login" -TimeoutSeconds $HealthTimeoutSeconds

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
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    Set-Location $originalLocation
}
