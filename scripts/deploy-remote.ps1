param(
    [string]$Target,
    [string[]]$Targets,
    [switch]$AllTargets,
    [string]$ServerHost,
    [int]$ServerPort = 0,
    [string]$ServerUser,
    [string]$SshKeyPath,
    [string]$SshPassword,
    [string]$RemoteDeployDir,
    [string]$RemoteServiceName = "local-proxy",
    [string]$SharedDockerNetwork,
    [int]$AppPort = 0
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "[STEP] $Message" -ForegroundColor Cyan
}

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-PythonCommand([string]$RepoRoot) {
    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }
    throw "Python not found. Please install Python or create .venv first."
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

function Ensure-Paramiko([string]$PythonCommand) {
    & $PythonCommand -c "import paramiko" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Step "Install paramiko into local Python environment"
        & $PythonCommand -m pip install paramiko
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install paramiko."
        }
    }
}

function Invoke-RemoteHelper([string]$PythonCommand, [string[]]$Arguments, [string]$PasswordValue = "") {
    $oldPassword = $env:REMOTE_OPS_PASSWORD
    try {
        if ($PasswordValue) {
            $env:REMOTE_OPS_PASSWORD = $PasswordValue
        } else {
            Remove-Item Env:REMOTE_OPS_PASSWORD -ErrorAction SilentlyContinue
        }
        & $PythonCommand (Join-Path $PSScriptRoot "remote_ops.py") @Arguments
    } finally {
        if ($null -eq $oldPassword) {
            Remove-Item Env:REMOTE_OPS_PASSWORD -ErrorAction SilentlyContinue
        } else {
            $env:REMOTE_OPS_PASSWORD = $oldPassword
        }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Remote helper failed: $($Arguments -join ' ')"
    }
}

$repoRoot = Get-RepoRoot
$pythonCommand = Get-PythonCommand $repoRoot
Ensure-Paramiko $pythonCommand
$envPath = Join-Path $repoRoot ".env"
$envMap = Get-DotEnvMap $envPath

function Get-EnvOrEmpty([hashtable]$Map, [string]$Key) {
    if ($Map.ContainsKey($Key)) {
        return [string]$Map[$Key]
    }
    return ""
}

function Normalize-TargetName([string]$Name) {
    return (($Name -replace '[^A-Za-z0-9]', '_').Trim('_')).ToUpperInvariant()
}

function Resolve-TargetConfig([string]$TargetName, [hashtable]$EnvMap) {
    $normalized = Normalize-TargetName $TargetName
    $prefix = "DEPLOY_${normalized}_"
    $authMode = (Get-EnvOrEmpty $EnvMap ($prefix + "SSH_AUTH_MODE")).ToLowerInvariant()
    $cfg = [ordered]@{
        Target = $TargetName
        ServerHost = Get-EnvOrEmpty $EnvMap ($prefix + "SSH_HOST")
        ServerPort = Get-EnvOrEmpty $EnvMap ($prefix + "SSH_PORT")
        ServerUser = Get-EnvOrEmpty $EnvMap ($prefix + "SSH_USER")
        AuthMode = $authMode
        SshKeyPath = Resolve-OptionalPath (Get-EnvOrEmpty $EnvMap ($prefix + "SSH_KEY_PATH"))
        SshPassword = Get-EnvOrEmpty $EnvMap ($prefix + "SSH_PASSWORD")
        RemoteDeployDir = Get-EnvOrEmpty $EnvMap ($prefix + "REMOTE_PATH")
        RemoteServiceName = Get-EnvOrEmpty $EnvMap ($prefix + "SERVICE_NAME")
        ComposeFile = Get-EnvOrEmpty $EnvMap ($prefix + "COMPOSE_FILE")
        SharedDockerNetwork = Get-EnvOrEmpty $EnvMap ($prefix + "SHARED_DOCKER_NETWORK")
        AppPort = Get-EnvOrEmpty $EnvMap ($prefix + "APP_PORT")
        StorageDbHost = Get-EnvOrEmpty $EnvMap ($prefix + "STORAGE_DB_HOST")
        StorageDbPort = Get-EnvOrEmpty $EnvMap ($prefix + "STORAGE_DB_PORT")
        StorageDbUser = Get-EnvOrEmpty $EnvMap ($prefix + "STORAGE_DB_USER")
        StorageDbPassword = Get-EnvOrEmpty $EnvMap ($prefix + "STORAGE_DB_PASSWORD")
        StorageDbName = Get-EnvOrEmpty $EnvMap ($prefix + "STORAGE_DB_NAME")
    }
    if (-not $cfg.AuthMode) {
        if ($cfg.SshPassword) {
            $cfg.AuthMode = "password"
        } elseif ($cfg.SshKeyPath) {
            $cfg.AuthMode = "key"
        }
    }
    if (-not $cfg.ServerPort) { $cfg.ServerPort = "22" }
    if (-not $cfg.RemoteServiceName) { $cfg.RemoteServiceName = "local-proxy" }
    if (-not $cfg.AppPort) { $cfg.AppPort = [string](Get-EnvOrEmpty $EnvMap "PORT") }
    if (-not $cfg.AppPort) { $cfg.AppPort = "18765" }
    if (-not $cfg.SharedDockerNetwork) { $cfg.SharedDockerNetwork = "1panel-network" }
    return $cfg
}

function Build-RemoteArgs([hashtable]$Config, [string]$Action) {
    $args = @(
        $Action,
        "--host", [string]$Config.ServerHost,
        "--port", [string]$Config.ServerPort,
        "--user", [string]$Config.ServerUser
    )
    if ($Config.AuthMode -eq "key") {
        $args += @("--key-path", [string]$Config.SshKeyPath)
    }
    return $args
}

$targetConfigs = @()

if ($AllTargets) {
    $declaredTargets = @(
        ((Get-EnvOrEmpty $envMap "DEPLOY_TARGETS") -split "[,;\r\n]+" | ForEach-Object { $_.Trim() }) |
            Where-Object { $_ }
    )
    if (-not $declaredTargets -or $declaredTargets.Count -eq 0) {
        throw "DEPLOY_TARGETS is empty; cannot use -AllTargets."
    }
    foreach ($targetName in $declaredTargets) {
        $targetConfigs += ,(Resolve-TargetConfig $targetName $envMap)
    }
} elseif ($Targets -and $Targets.Count -gt 0) {
    foreach ($targetName in $Targets) {
        $targetConfigs += ,(Resolve-TargetConfig $targetName $envMap)
    }
} elseif ($Target) {
    $targetConfigs += ,(Resolve-TargetConfig $Target $envMap)
} else {
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
    if (-not $SshPassword) {
        $SshPassword = [string]$envMap["DEPLOY_SSH_PASSWORD"]
    }
    if (-not $RemoteDeployDir) {
        $RemoteDeployDir = [string]$envMap["DEPLOY_REMOTE_PATH"]
    }
    if (-not $SharedDockerNetwork) {
        $SharedDockerNetwork = [string]$envMap["SHARED_DOCKER_NETWORK"]
    }
    if ($AppPort -le 0) {
        $rawAppPort = [string]$envMap["PORT"]
        if ($rawAppPort) {
            $AppPort = [int]$rawAppPort
        }
    }
    $resolvedServerPort = if ($ServerPort -gt 0) { [string]$ServerPort } else { "22" }
    $resolvedSharedDockerNetwork = if ($SharedDockerNetwork) { $SharedDockerNetwork } else { "1panel-network" }
    $resolvedAppPort = if ($AppPort -gt 0) { [string]$AppPort } else { "18765" }
    $authMode = if ($SshPassword) { "password" } else { "key" }
    $targetConfigs += ,([ordered]@{
        Target = "default"
        ServerHost = $ServerHost
        ServerPort = $resolvedServerPort
        ServerUser = $ServerUser
        AuthMode = $authMode
        SshKeyPath = $SshKeyPath
        SshPassword = $SshPassword
        RemoteDeployDir = $RemoteDeployDir
        RemoteServiceName = $RemoteServiceName
        ComposeFile = ""
        SharedDockerNetwork = $resolvedSharedDockerNetwork
        AppPort = $resolvedAppPort
        StorageDbHost = [string]$envMap["DEPLOY_STORAGE_DB_HOST"]
        StorageDbPort = [string]$envMap["DEPLOY_STORAGE_DB_PORT"]
        StorageDbUser = [string]$envMap["DEPLOY_STORAGE_DB_USER"]
        StorageDbPassword = [string]$envMap["DEPLOY_STORAGE_DB_PASSWORD"]
        StorageDbName = [string]$envMap["DEPLOY_STORAGE_DB_NAME"]
    })
}

foreach ($cfg in $targetConfigs) {
    if (-not $cfg.ServerHost) { throw "Missing SSH host for target '$($cfg.Target)'." }
    if (-not $cfg.ServerUser) { throw "Missing SSH user for target '$($cfg.Target)'." }
    if (-not $cfg.RemoteDeployDir) { throw "Missing remote deploy path for target '$($cfg.Target)'." }
    if ($cfg.AuthMode -eq "key" -and -not $cfg.SshKeyPath) { throw "Missing SSH key path for target '$($cfg.Target)'." }
    if ($cfg.AuthMode -eq "password" -and -not $cfg.SshPassword) { throw "Missing SSH password for target '$($cfg.Target)'." }
    if ($cfg.AuthMode -eq "key" -and -not (Test-Path $cfg.SshKeyPath)) { throw "SSH key not found for target '$($cfg.Target)': $($cfg.SshKeyPath)" }
}

$gitStatus = & git -C $repoRoot status --short --untracked-files=no
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
$runtimeConfigPath = Join-Path $repoRoot "config\proxy-config.json"
$hasRuntimeConfig = Test-Path $runtimeConfigPath

Write-Step "Archive commit $commit"
if (Test-Path $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}
& git -C $repoRoot archive --format=tar --output=$archivePath HEAD
if ($LASTEXITCODE -ne 0) {
    throw "git archive failed."
}

foreach ($cfg in $targetConfigs) {
    $remoteArchivePath = "/tmp/local-proxy-$commit-$($cfg.Target).tar"
    $remoteRuntimeConfigPath = "/tmp/local-proxy-runtime-config-$commit-$($cfg.Target).json"
    $remoteRuntimeConfigResultPath = "/tmp/local-proxy-runtime-config-result-$commit-$($cfg.Target).json"
    $remoteExtractDir = "/tmp/local-proxy-$commit-$($cfg.Target)"
    $remoteBaseArgs = Build-RemoteArgs $cfg "exec"
    $uploadArgs = Build-RemoteArgs $cfg "upload"
    $passwordValue = if ($cfg.AuthMode -eq "password") { [string]$cfg.SshPassword } else { "" }
    $composeFile = if ([string]::IsNullOrWhiteSpace([string]$cfg.ComposeFile)) { "docker-compose.yml" } else { [string]$cfg.ComposeFile }

    Write-Step "[$($cfg.Target)] Upload archive to $($cfg.ServerUser)@$($cfg.ServerHost):$remoteArchivePath"
    Invoke-RemoteHelper $pythonCommand ($uploadArgs + @("--local-path", $archivePath, "--remote-path", $remoteArchivePath)) $passwordValue
    if ($hasRuntimeConfig) {
        Write-Step "[$($cfg.Target)] Upload local runtime config"
        Invoke-RemoteHelper $pythonCommand ($uploadArgs + @("--local-path", $runtimeConfigPath, "--remote-path", $remoteRuntimeConfigPath)) $passwordValue
    }

    $remoteEnvUpdates = [ordered]@{
        STORAGE_DB_HOST = [string]$cfg.StorageDbHost
        STORAGE_DB_PORT = [string]$cfg.StorageDbPort
        STORAGE_DB_USER = [string]$cfg.StorageDbUser
        STORAGE_DB_PASSWORD = [string]$cfg.StorageDbPassword
        STORAGE_DB_NAME = [string]$cfg.StorageDbName
        SHARED_DOCKER_NETWORK = [string]$cfg.SharedDockerNetwork
    }
    $filteredUpdates = [ordered]@{}
    foreach ($entry in $remoteEnvUpdates.GetEnumerator()) {
        if (-not [string]::IsNullOrWhiteSpace([string]$entry.Value)) {
            $filteredUpdates[$entry.Key] = [string]$entry.Value
        }
    }
    if ($filteredUpdates.Count -gt 0) {
        Write-Step "[$($cfg.Target)] Sync remote env values"
        $payloadJson = $filteredUpdates | ConvertTo-Json -Compress
        $payloadB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payloadJson))
        $envSyncCommand = @'
python3 - <<'PY'
import base64
import json
from pathlib import Path

env_path = Path("__REMOTE_ENV_PATH__")
updates = json.loads(base64.b64decode("__PAYLOAD_B64__").decode("utf-8"))
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
env_path.parent.mkdir(parents=True, exist_ok=True)
env_path.write_text("\n".join(output) + "\n", encoding="utf-8")
print("synced_remote_env_keys=" + ",".join(sorted(updates)))
PY
'@
        $envSyncCommand = $envSyncCommand.Replace("__REMOTE_ENV_PATH__", "$($cfg.RemoteDeployDir)/.env")
        $envSyncCommand = $envSyncCommand.Replace("__PAYLOAD_B64__", $payloadB64)
        $envSyncCommandB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($envSyncCommand))
        Invoke-RemoteHelper $pythonCommand ($remoteBaseArgs + @("--command-b64", $envSyncCommandB64)) $passwordValue
    }

    Write-Step "[$($cfg.Target)] Sync tracked code while preserving remote .env and var/; runtime config is synced separately"
    $deployCommand = @'
set -e
mkdir -p "__REMOTE_DEPLOY_DIR__"
rm -rf "__REMOTE_EXTRACT_DIR__"
mkdir -p "__REMOTE_EXTRACT_DIR__"
tar -xf "__REMOTE_ARCHIVE_PATH__" -C "__REMOTE_EXTRACT_DIR__"
python3 - <<'PY'
from pathlib import Path
import shutil

source_root = Path("__REMOTE_EXTRACT_DIR__")
deploy_root = Path("__REMOTE_DEPLOY_DIR__")
skip_exact = {".env", "config/proxy-config.json"}
skip_prefix = ("var/",)

for path in sorted(source_root.rglob("*")):
    rel = path.relative_to(source_root).as_posix()
    if rel in skip_exact:
        continue
    if any(rel == prefix[:-1] or rel.startswith(prefix) for prefix in skip_prefix):
        continue
    target = deploy_root / rel
    if path.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        continue
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)

for relative in ("start.sh", "node_proxy.js", "app.py"):
    path = deploy_root / relative
    if not path.exists():
        continue
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if normalized != raw:
        path.write_bytes(normalized)
PY
cd "__REMOTE_DEPLOY_DIR__"
chmod +x ./start.sh
docker compose -f "__COMPOSE_FILE__" up -d --build __REMOTE_SERVICE_NAME__
attempt=1
while [ "$attempt" -le 45 ]; do
  if curl -fsS http://127.0.0.1:__APP_PORT__/health >/dev/null; then
    break
  fi
  if [ "$attempt" -eq 45 ]; then
    echo "health check failed after $attempt attempts" >&2
    docker ps --filter name=__REMOTE_SERVICE_NAME__ || true
    docker logs --tail 120 __REMOTE_SERVICE_NAME__ || true
    exit 1
  fi
  sleep 2
  attempt=$((attempt + 1))
done
curl -fsS http://127.0.0.1:__APP_PORT__/health
if [ -f "__REMOTE_RUNTIME_CONFIG_PATH__" ]; then
  python3 - <<'PY'
import json
import re
from html import unescape
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

env = {}
env_path = Path("__REMOTE_DEPLOY_DIR__") / ".env"
for raw_line in env_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in raw_line:
        continue
    key, value = raw_line.split("=", 1)
    env[key.strip()] = value

username = env.get("ADMIN_USERNAME", "admin").strip()
password = env.get("ADMIN_PASSWORD", "").strip()
if not password:
    raise SystemExit("missing ADMIN_PASSWORD in remote .env")

base_url = "http://127.0.0.1:__APP_PORT__"
cookie_jar = CookieJar()
opener = build_opener(HTTPCookieProcessor(cookie_jar))

login_html = opener.open(base_url + "/login", timeout=30).read().decode("utf-8", errors="replace")
match = re.search(r'name="_csrf_token" value="([^"]+)"', login_html)
if not match:
    raise SystemExit("login csrf token not found while syncing runtime config")

csrf_token = unescape(match.group(1))
login_payload = urlencode(
    {
        "username": username,
        "password": password,
        "_csrf_token": csrf_token,
    }
).encode("utf-8")
login_response = opener.open(
    Request(
        base_url + "/login?next=/debug/config",
        data=login_payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ),
    timeout=30,
)
login_body = login_response.read().decode("utf-8", errors="replace")
if "/login" in str(getattr(login_response, "geturl", lambda: "")()) and "_csrf_token" in login_body:
    raise SystemExit("login failed while syncing runtime config")
if not any(cookie.name for cookie in cookie_jar):
    raise SystemExit("login did not establish a session cookie")

sync_response = opener.open(
    Request(
        base_url + "/debug/config",
        data=Path("__REMOTE_RUNTIME_CONFIG_PATH__").read_bytes(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    ),
    timeout=120,
)
sync_text = sync_response.read().decode("utf-8", errors="replace")
Path("__REMOTE_RUNTIME_CONFIG_RESULT_PATH__").write_text(sync_text, encoding="utf-8")

payload = json.loads(sync_text)
config = payload.get("config") if isinstance(payload, dict) else {}
runtime = payload.get("runtime") if isinstance(payload, dict) else {}
print(
    "runtime_config_synced request_timeout={request_timeout} stream_first_event_timeout_seconds={stream_first_event_timeout_seconds} "
    "max_retries={max_retries} route_switch_window_seconds={route_switch_window_seconds} model_capability_count={model_capability_count}".format(
        request_timeout=config.get("request_timeout"),
        stream_first_event_timeout_seconds=config.get("stream_first_event_timeout_seconds"),
        max_retries=config.get("max_retries"),
        route_switch_window_seconds=config.get("route_switch_window_seconds"),
        model_capability_count=runtime.get("model_capability_count"),
    )
)
PY
fi
rm -f "__REMOTE_RUNTIME_CONFIG_PATH__" "__REMOTE_RUNTIME_CONFIG_RESULT_PATH__"
rm -rf "__REMOTE_EXTRACT_DIR__" "__REMOTE_ARCHIVE_PATH__"
'@
    $deployCommand = $deployCommand.Replace("__REMOTE_DEPLOY_DIR__", [string]$cfg.RemoteDeployDir)
    $deployCommand = $deployCommand.Replace("__REMOTE_EXTRACT_DIR__", $remoteExtractDir)
    $deployCommand = $deployCommand.Replace("__REMOTE_ARCHIVE_PATH__", $remoteArchivePath)
    $deployCommand = $deployCommand.Replace("__REMOTE_RUNTIME_CONFIG_PATH__", $remoteRuntimeConfigPath)
    $deployCommand = $deployCommand.Replace("__REMOTE_RUNTIME_CONFIG_RESULT_PATH__", $remoteRuntimeConfigResultPath)
    $deployCommand = $deployCommand.Replace("__REMOTE_SERVICE_NAME__", [string]$cfg.RemoteServiceName)
    $deployCommand = $deployCommand.Replace("__COMPOSE_FILE__", $composeFile)
    $deployCommand = $deployCommand.Replace("__APP_PORT__", [string]$cfg.AppPort)
    $deployCommandB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($deployCommand))
    Invoke-RemoteHelper $pythonCommand ($remoteBaseArgs + @("--command-b64", $deployCommandB64)) $passwordValue
    Write-Step "[$($cfg.Target)] Deploy complete: $commit"
}
