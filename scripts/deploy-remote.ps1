param(
    [string]$ServerHost,
    [int]$ServerPort = 0,
    [string]$ServerUser,
    [string]$SshKeyPath,
    [string]$RemoteDeployDir,
    [string]$RemoteServiceName = "local-proxy"
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "[STEP] $Message" -ForegroundColor Cyan
}

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-DotEnvMap([string]$Path) {
    $result = @{}
    if (-not (Test-Path $Path)) {
        return $result
    }
    foreach ($line in Get-Content $Path) {
        if ($null -eq $line) {
            continue
        }
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $index = $line.IndexOf("=")
        if ($index -lt 1) {
            continue
        }
        $key = $line.Substring(0, $index).Trim()
        $value = $line.Substring($index + 1)
        $result[$key] = $value
    }
    return $result
}

function Resolve-OptionalPath([string]$PathValue) {
    if (-not $PathValue) {
        return ""
    }
    $expanded = [Environment]::ExpandEnvironmentVariables($PathValue)
    if ($expanded.StartsWith("~/") -or $expanded.StartsWith("~\")) {
        return Join-Path $HOME $expanded.Substring(2)
    }
    return $expanded
}

function Invoke-Ssh([string]$Command) {
    & ssh -i $SshKeyPath -p $ServerPort -o StrictHostKeyChecking=no "$ServerUser@$ServerHost" $Command
    if ($LASTEXITCODE -ne 0) {
        throw "SSH command failed: $Command"
    }
}

function Invoke-Scp([string]$LocalPath, [string]$RemotePath) {
    & scp -i $SshKeyPath -P $ServerPort -o StrictHostKeyChecking=no $LocalPath "${ServerUser}@${ServerHost}:$RemotePath"
    if ($LASTEXITCODE -ne 0) {
        throw "SCP failed: $LocalPath -> $RemotePath"
    }
}

$repoRoot = Get-RepoRoot
$envPath = Join-Path $repoRoot ".env"
$envMap = Get-DotEnvMap $envPath

if (-not $ServerHost) {
    $ServerHost = [string]$envMap["DEPLOY_SSH_HOST"]
}
if ($ServerPort -le 0) {
    $rawPort = [string]$envMap["DEPLOY_SSH_PORT"]
    if ($rawPort) {
        $ServerPort = [int]$rawPort
    }
}
if (-not $ServerUser) {
    $ServerUser = [string]$envMap["DEPLOY_SSH_USER"]
}
if (-not $SshKeyPath) {
    $SshKeyPath = Resolve-OptionalPath ([string]$envMap["DEPLOY_SSH_KEY_PATH"])
}
if (-not $RemoteDeployDir) {
    $RemoteDeployDir = [string]$envMap["DEPLOY_REMOTE_PATH"]
}

if (-not $ServerHost) {
    throw "Missing DEPLOY_SSH_HOST or -ServerHost."
}
if ($ServerPort -le 0) {
    $ServerPort = 22
}
if (-not $ServerUser) {
    throw "Missing DEPLOY_SSH_USER or -ServerUser."
}
if (-not $SshKeyPath) {
    throw "Missing DEPLOY_SSH_KEY_PATH or -SshKeyPath."
}
if (-not (Test-Path $SshKeyPath)) {
    throw "SSH key not found: $SshKeyPath"
}
if (-not $RemoteDeployDir) {
    throw "Missing DEPLOY_REMOTE_PATH or -RemoteDeployDir."
}

$gitStatus = & git -C $repoRoot status --short
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read git status."
}
if ($gitStatus) {
    Write-Host "[WARN] Working tree has uncommitted changes; deployment will publish HEAD only." -ForegroundColor Yellow
}

$commit = (& git -C $repoRoot rev-parse --short HEAD).Trim()
if (-not $commit) {
    throw "Unable to resolve current commit."
}

$archivePath = Join-Path $repoRoot "local-proxy-$commit.tar"
$remoteArchivePath = "/tmp/local-proxy-$commit.tar"
$remoteExtractDir = "/tmp/local-proxy-$commit"

$remoteDbEnv = @{
    STORAGE_DB_HOST = [string]$envMap["DEPLOY_STORAGE_DB_HOST"]
    STORAGE_DB_PORT = [string]$envMap["DEPLOY_STORAGE_DB_PORT"]
    STORAGE_DB_USER = [string]$envMap["DEPLOY_STORAGE_DB_USER"]
    STORAGE_DB_PASSWORD = [string]$envMap["DEPLOY_STORAGE_DB_PASSWORD"]
    STORAGE_DB_NAME = [string]$envMap["DEPLOY_STORAGE_DB_NAME"]
}

$hasRemoteDbEnv = $false
foreach ($key in $remoteDbEnv.Keys) {
    if ([string]::IsNullOrWhiteSpace([string]$remoteDbEnv[$key])) {
        $hasRemoteDbEnv = $false
        break
    }
    $hasRemoteDbEnv = $true
}

Write-Step "Archive commit $commit"
if (Test-Path $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}
& git -C $repoRoot archive --format=tar --output=$archivePath HEAD
if ($LASTEXITCODE -ne 0) {
    throw "git archive failed."
}

Write-Step "Upload archive to ${ServerUser}@${ServerHost}:$remoteArchivePath"
Invoke-Scp -LocalPath $archivePath -RemotePath $remoteArchivePath

if ($hasRemoteDbEnv) {
    Write-Step "Sync remote MySQL env values"
    $payloadJson = $remoteDbEnv | ConvertTo-Json -Compress
    $payloadB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payloadJson))
    $remoteEnvPath = "$RemoteDeployDir/.env"
    $pythonScript = @"
import base64
import json
from pathlib import Path

env_path = Path("$remoteEnvPath")
updates = json.loads(base64.b64decode("$payloadB64").decode("utf-8"))
lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
seen = set()
output = []
for line in lines:
    if "=" not in line or line.lstrip().startswith("#"):
        output.append(line)
        continue
    key, value = line.split("=", 1)
    if key in updates:
        output.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        output.append(line)
for key, value in updates.items():
    if key not in seen:
        output.append(f"{key}={value}")
env_path.write_text("\n".join(output) + "\n", encoding="utf-8")
print("synced remote db env keys:", ",".join(sorted(updates)))
"@
    $pythonScriptPath = Join-Path $repoRoot "var\tmp-remote-env-sync.py"
    New-Item -ItemType Directory -Force -Path (Split-Path $pythonScriptPath -Parent) | Out-Null
    Set-Content -LiteralPath $pythonScriptPath -Value $pythonScript -Encoding UTF8
    $remoteScriptPath = "/tmp/local-proxy-env-sync.py"
    Invoke-Scp -LocalPath $pythonScriptPath -RemotePath $remoteScriptPath
    Invoke-Ssh "python3 '$remoteScriptPath' && rm -f '$remoteScriptPath'"
}

Write-Step "Sync tracked code while preserving remote .env, config/proxy-config.json and var/"
$deployCommand = @'
set -e
mkdir -p '__REMOTE_DEPLOY_DIR__'
rm -rf '__REMOTE_EXTRACT_DIR__'
mkdir -p '__REMOTE_EXTRACT_DIR__'
tar -xf '__REMOTE_ARCHIVE_PATH__' -C '__REMOTE_EXTRACT_DIR__'
rsync -a --delete \
  --exclude '.env' \
  --exclude 'config/proxy-config.json' \
  --exclude 'var/' \
  '__REMOTE_EXTRACT_DIR__/' '__REMOTE_DEPLOY_DIR__/'
cd '__REMOTE_DEPLOY_DIR__'
python3 - <<'PY'
from pathlib import Path

targets = [
    Path('/app/start.sh'),
    Path('/app/node_proxy.js'),
    Path('/app/app.py'),
]

repo_root = Path('.').resolve()
for relative in ('start.sh', 'node_proxy.js', 'app.py'):
    path = repo_root / relative
    if not path.exists():
        continue
    raw = path.read_bytes()
    normalized = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
    if normalized != raw:
        path.write_bytes(normalized)
PY
chmod +x ./start.sh
docker compose up -d --build __REMOTE_SERVICE_NAME__
attempt=1
while [ "$attempt" -le 30 ]; do
  if curl -fsS http://127.0.0.1:18765/health >/dev/null; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "health check failed after $attempt attempts" >&2
    docker ps --filter name=__REMOTE_SERVICE_NAME__ || true
    docker logs --tail 80 __REMOTE_SERVICE_NAME__ || true
    exit 1
  fi
  sleep 2
  attempt=$((attempt + 1))
done
curl -fsS http://127.0.0.1:18765/health
rm -rf '__REMOTE_EXTRACT_DIR__' '__REMOTE_ARCHIVE_PATH__'
'@
$deployCommand = $deployCommand.Replace("__REMOTE_DEPLOY_DIR__", $RemoteDeployDir)
$deployCommand = $deployCommand.Replace("__REMOTE_EXTRACT_DIR__", $remoteExtractDir)
$deployCommand = $deployCommand.Replace("__REMOTE_ARCHIVE_PATH__", $remoteArchivePath)
$deployCommand = $deployCommand.Replace("__REMOTE_SERVICE_NAME__", $RemoteServiceName)
Invoke-Ssh $deployCommand

Write-Step "Deploy complete: $commit"
