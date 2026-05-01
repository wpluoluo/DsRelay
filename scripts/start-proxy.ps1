$ErrorActionPreference = "Stop"

$scriptPath = $MyInvocation.MyCommand.Path
$scriptDir = Split-Path -Parent $scriptPath
$projectRoot = Split-Path -Parent $scriptDir
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$envPath = Join-Path $projectRoot ".env"
$envExamplePath = Join-Path $projectRoot ".env.example"
$appPath = Join-Path $projectRoot "app.py"
$frontendDir = Join-Path $projectRoot "frontend"
$configDir = Join-Path $projectRoot "config"
$varDir = Join-Path $projectRoot "var"
$logDir = Join-Path $varDir "logs"
$cacheDir = Join-Path $varDir "cache"
$runDir = Join-Path $varDir "run"
$bootstrapLogPath = Join-Path $logDir "server.bootstrap.log"
$stdoutLogPath = Join-Path $logDir "server.out.log"
$stderrLogPath = Join-Path $logDir "server.err.log"
$pidPath = Join-Path $runDir "proxy.pid.json"
$dashboardTemplatePath = Join-Path $frontendDir "dashboard.html"
$proxyConfigPath = Join-Path $configDir "proxy-config.json"
$proxyLogPath = Join-Path $logDir "proxy.log"
$sqliteDbPath = Join-Path $cacheDir "proxy-cache.sqlite3"
$modelRouteCachePath = Join-Path $cacheDir "model-route-cache.json"
$port = 18765
$healthUrl = "http://127.0.0.1:$port/health"
$startDeadlineSeconds = 25
$venvScripts = Join-Path $projectRoot ".venv\Scripts"
$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$isolatedPathParts = @($venvScripts, $machinePath, $userPath) | Where-Object { $_ -and $_.Trim() }
$isolatedPath = ($isolatedPathParts -join ";")

foreach ($dir in @($frontendDir, $configDir, $logDir, $cacheDir, $runDir)) {
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

function Write-BootstrapLog {
    param(
        [string]$Level,
        [string]$Message
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "$timestamp [$Level] $Message"
    Write-Host $line
    Add-Content -LiteralPath $bootstrapLogPath -Value $line -Encoding UTF8
}

function Get-ListeningProcessId {
    param([int]$ListenPort)

    try {
        $conn = Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction Stop | Select-Object -First 1
        if ($null -ne $conn) {
            return [int]$conn.OwningProcess
        }
    } catch {
    }

    return $null
}

function Test-PathUnderProject {
    param(
        [string]$Path,
        [string]$ProjectRoot
    )

    if (-not $Path) {
        return $false
    }

    try {
        $normalizedPath = [System.IO.Path]::GetFullPath($Path).TrimEnd("\").ToLowerInvariant()
        $normalizedRoot = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd("\").ToLowerInvariant()
        return ($normalizedPath -eq $normalizedRoot -or $normalizedPath.StartsWith("$normalizedRoot\"))
    } catch {
        return $false
    }
}

function Test-HealthMatchesProject {
    param(
        [string]$Url,
        [string]$ProjectRoot
    )

    if (-not $Url) {
        return $false
    }

    try {
        $payload = Invoke-RestMethod -Uri $Url -TimeoutSec 3
        $runtime = $payload.runtime
        if ($null -eq $runtime) {
            return $false
        }

        $paths = @(
            [string]$runtime.config_path,
            [string]$runtime.model_routing.sqlite_path,
            [string]$runtime.model_routing.cache_path
        ) | Where-Object { $_ -and $_.Trim() }

        foreach ($path in $paths) {
            if (Test-PathUnderProject -Path $path -ProjectRoot $ProjectRoot) {
                return $true
            }
        }
    } catch {
    }

    return $false
}

function Get-PidFileProxyProcessIds {
    param(
        [string]$PidFilePath,
        [string]$ProjectRoot
    )

    if (-not (Test-Path -LiteralPath $PidFilePath)) {
        return @()
    }

    try {
        $payload = Get-Content -LiteralPath $PidFilePath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return @()
    }

    $healthOk = Test-HealthMatchesProject -Url ([string]$payload.health_url) -ProjectRoot $ProjectRoot
    if (-not $healthOk) {
        return @()
    }

    $ids = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($rawId in @($payload.launcher_pid, $payload.listener_pid)) {
        if ($null -eq $rawId) {
            continue
        }

        $processId = 0
        if (-not [int]::TryParse([string]$rawId, [ref]$processId)) {
            continue
        }

        try {
            $item = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction Stop
        } catch {
            continue
        }

        $cmd = [string]($item.CommandLine)
        if ([string]$item.Name -eq "python.exe" -and $cmd.ToLowerInvariant().Contains("app.py")) {
            [void]$ids.Add($processId)
        }
    }

    return @($ids)
}

function Get-ProxyProcessIds {
    param(
        [string]$ProjectRoot,
        [string]$AppPath
    )

    $normalizedRoot = [System.IO.Path]::GetFullPath($ProjectRoot).ToLowerInvariant()
    $normalizedApp = [System.IO.Path]::GetFullPath($AppPath).ToLowerInvariant()
    $allProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $rootIds = New-Object 'System.Collections.Generic.HashSet[int]'

    foreach ($item in $allProcesses) {
        if ([string]$item.Name -ne "python.exe") {
            continue
        }
        $cmd = [string]($item.CommandLine)
        $exe = [string]($item.ExecutablePath)
        if (-not $cmd) {
            continue
        }
        $cmdLower = $cmd.ToLowerInvariant()
        $exeLower = $exe.ToLowerInvariant()
        $isProjectApp = (
            $cmdLower.Contains("app.py") -and
            (
                $cmdLower.Contains($normalizedRoot) -or
                $cmdLower.Contains($normalizedApp) -or
                $exeLower.Contains($normalizedRoot)
            )
        )
        if ($isProjectApp) {
            [void]$rootIds.Add([int]$item.ProcessId)
        }
    }

    $pidFileIds = @(Get-PidFileProxyProcessIds -PidFilePath $pidPath -ProjectRoot $ProjectRoot)
    foreach ($id in $pidFileIds) {
        [void]$rootIds.Add([int]$id)
    }

    $managedIds = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($id in $rootIds) {
        [void]$managedIds.Add([int]$id)
    }

    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($item in $allProcesses) {
            if ([string]$item.Name -ne "python.exe") {
                continue
            }
            $processId = [int]$item.ProcessId
            $parentProcessId = [int]$item.ParentProcessId
            if ($managedIds.Contains($processId)) {
                continue
            }
            if ($managedIds.Contains($parentProcessId)) {
                [void]$managedIds.Add($processId)
                $changed = $true
            }
        }
    }

    return @($managedIds)
}

function Get-ProxyProcesses {
    param(
        [string]$ProjectRoot,
        [string]$AppPath
    )

    $ids = @(Get-ProxyProcessIds -ProjectRoot $ProjectRoot -AppPath $AppPath)
    if ($ids.Count -eq 0) {
        return @()
    }
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $ids -contains [int]$_.ProcessId }
}

function Stop-ProxyProcesses {
    param(
        [string]$ProjectRoot,
        [string]$AppPath,
        [int[]]$ExcludePids = @()
    )

    $targets = @(Get-ProxyProcesses -ProjectRoot $ProjectRoot -AppPath $AppPath)
    $targets = @($targets | Sort-Object ParentProcessId -Descending)
    foreach ($target in $targets) {
        if ($ExcludePids -contains [int]$target.ProcessId) {
            continue
        }
        try {
            Write-BootstrapLog -Level "WARN" -Message "stopping_existing_proxy pid=$($target.ProcessId) parent=$($target.ParentProcessId) exe=$($target.ExecutablePath)"
            Stop-Process -Id ([int]$target.ProcessId) -Force -ErrorAction Stop
        } catch {
            Write-BootstrapLog -Level "WARN" -Message "stop_existing_proxy_failed pid=$($target.ProcessId) error=$($_.Exception.Message)"
        }
    }
}

function Wait-PortReleased {
    param(
        [int]$ListenPort,
        [int]$TimeoutSeconds = 8
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $listenerPid = Get-ListeningProcessId -ListenPort $ListenPort
        if (-not $listenerPid) {
            return $true
        }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

function Release-ProjectPort {
    param(
        [int]$ListenPort,
        [string]$ProjectRoot,
        [string]$AppPath,
        [string]$Stage
    )

    $existingPid = Get-ListeningProcessId -ListenPort $ListenPort
    if (-not $existingPid) {
        return $true
    }

    $managedIds = @(Get-ProxyProcessIds -ProjectRoot $ProjectRoot -AppPath $AppPath)
    if ($managedIds -contains [int]$existingPid) {
        Write-BootstrapLog -Level "WARN" -Message "port_occupied_by_project_proxy port=$ListenPort pid=$existingPid stage=$Stage"
        Stop-ProxyProcesses -ProjectRoot $ProjectRoot -AppPath $AppPath
        return (Wait-PortReleased -ListenPort $ListenPort -TimeoutSeconds 8)
    }

    try {
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $existingPid" -ErrorAction Stop
        Write-BootstrapLog -Level "ERROR" -Message "port_occupied_by_foreign_process port=$ListenPort pid=$existingPid process=$($owner.Name) exe=$($owner.ExecutablePath) stage=$Stage"
        if ($owner.CommandLine) {
            Write-BootstrapLog -Level "ERROR" -Message "foreign_process_cmd=$($owner.CommandLine)"
        }
    } catch {
        Write-BootstrapLog -Level "ERROR" -Message "port_occupied_by_unknown_process port=$ListenPort pid=$existingPid stage=$Stage error=$($_.Exception.Message)"
    }
    return $false
}

function Wait-ProxyReady {
    param(
        [string]$Url,
        [int]$DeadlineSeconds
    )

    $deadline = (Get-Date).AddSeconds($DeadlineSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 700
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        } catch {
        }
    }

    return $false
}

Set-Location $projectRoot

"" | Set-Content -LiteralPath $bootstrapLogPath -Encoding UTF8
Write-BootstrapLog -Level "INFO" -Message "project_root=$projectRoot"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-BootstrapLog -Level "ERROR" -Message "python_not_found path=$pythonPath"
    exit 1
}

if (-not (Test-Path -LiteralPath $envPath)) {
    if (Test-Path -LiteralPath $envExamplePath) {
        Copy-Item -LiteralPath $envExamplePath -Destination $envPath -Force
        Write-BootstrapLog -Level "WARN" -Message "env_missing copied_from_example=true"
    } else {
        Write-BootstrapLog -Level "WARN" -Message "env_missing copied_from_example=false"
    }
}

if (-not (Test-Path -LiteralPath $appPath)) {
    Write-BootstrapLog -Level "ERROR" -Message "app_not_found path=$appPath"
    exit 1
}

if (-not (Test-Path -LiteralPath $dashboardTemplatePath)) {
    Write-BootstrapLog -Level "WARN" -Message "dashboard_template_missing path=$dashboardTemplatePath"
}

$projectProxyProcesses = @(Get-ProxyProcesses -ProjectRoot $projectRoot -AppPath $appPath)
if ($projectProxyProcesses.Count -gt 0) {
    Write-BootstrapLog -Level "WARN" -Message "existing_proxy_processes count=$($projectProxyProcesses.Count)"
    Stop-ProxyProcesses -ProjectRoot $projectRoot -AppPath $appPath
    Start-Sleep -Seconds 1
}

$releasedBeforeStart = Release-ProjectPort -ListenPort $port -ProjectRoot $projectRoot -AppPath $appPath -Stage "before_start"
if (-not $releasedBeforeStart) {
    Write-BootstrapLog -Level "ERROR" -Message "port_release_failed port=$port stage=before_start"
    exit 5
}

Write-BootstrapLog -Level "INFO" -Message "python_path=$pythonPath"
Write-BootstrapLog -Level "INFO" -Message "command=$pythonPath app.py"
Write-BootstrapLog -Level "INFO" -Message "dashboard_template=$dashboardTemplatePath"
Write-BootstrapLog -Level "INFO" -Message "config_path=$proxyConfigPath"
Write-BootstrapLog -Level "INFO" -Message "cache_path=$cacheDir"
Write-BootstrapLog -Level "INFO" -Message "stdout_log=$stdoutLogPath"
Write-BootstrapLog -Level "INFO" -Message "stderr_log=$stderrLogPath"
Write-BootstrapLog -Level "INFO" -Message "path_mode=isolated_venv_first"

"" | Set-Content -LiteralPath $stdoutLogPath -Encoding UTF8
"" | Set-Content -LiteralPath $stderrLogPath -Encoding UTF8

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $pythonPath
$startInfo.Arguments = "app.py"
$startInfo.WorkingDirectory = $projectRoot
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$startInfo.EnvironmentVariables["PATH"] = $isolatedPath
$startInfo.EnvironmentVariables["PYTHONHOME"] = ""
$startInfo.EnvironmentVariables["PYTHONPATH"] = ""
$startInfo.EnvironmentVariables.Remove("PYTHONEXECUTABLE")
$startInfo.EnvironmentVariables["PYTHONNOUSERSITE"] = "1"
$startInfo.EnvironmentVariables["BT_PYTHON"] = ""
$startInfo.EnvironmentVariables["FLASK_DEBUG"] = "0"
$startInfo.EnvironmentVariables["WERKZEUG_RUN_MAIN"] = ""
$startInfo.EnvironmentVariables["PROXY_CONFIG_PATH"] = $proxyConfigPath
$startInfo.EnvironmentVariables["PROXY_LOG_PATH"] = $proxyLogPath
$startInfo.EnvironmentVariables["SQLITE_DB_PATH"] = $sqliteDbPath
$startInfo.EnvironmentVariables["MODEL_ROUTE_CACHE_PATH"] = $modelRouteCachePath
$startInfo.EnvironmentVariables["PORT"] = [string]$port

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $startInfo
$stdoutWriter = [System.IO.StreamWriter]::new($stdoutLogPath, $false, [System.Text.Encoding]::UTF8)
$stderrWriter = [System.IO.StreamWriter]::new($stderrLogPath, $false, [System.Text.Encoding]::UTF8)
$process.add_OutputDataReceived({
    param($sender, $args)
    if ($null -ne $args.Data) {
        $stdoutWriter.WriteLine($args.Data)
        $stdoutWriter.Flush()
    }
})
$process.add_ErrorDataReceived({
    param($sender, $args)
    if ($null -ne $args.Data) {
        $stderrWriter.WriteLine($args.Data)
        $stderrWriter.Flush()
    }
})
$null = $process.Start()
$process.BeginOutputReadLine()
$process.BeginErrorReadLine()

Write-BootstrapLog -Level "INFO" -Message "process_started pid=$($process.Id)"

$ready = Wait-ProxyReady -Url $healthUrl -DeadlineSeconds $startDeadlineSeconds
if (-not $ready) {
    $stdoutPreview = ""
    $stderrPreview = ""

    if (Test-Path -LiteralPath $stdoutLogPath) {
        $stdoutPreview = (Get-Content -LiteralPath $stdoutLogPath -Tail 20 -ErrorAction SilentlyContinue) -join "`n"
    }
    if (Test-Path -LiteralPath $stderrLogPath) {
        $stderrPreview = (Get-Content -LiteralPath $stderrLogPath -Tail 20 -ErrorAction SilentlyContinue) -join "`n"
    }

    try {
        Stop-ProxyProcesses -ProjectRoot $projectRoot -AppPath $appPath
    } catch {
    }

    Write-BootstrapLog -Level "ERROR" -Message "healthcheck_failed url=$healthUrl deadline_seconds=$startDeadlineSeconds"
    if ($stdoutPreview) {
        Write-BootstrapLog -Level "ERROR" -Message "stdout_tail=$stdoutPreview"
    }
    if ($stderrPreview) {
        Write-BootstrapLog -Level "ERROR" -Message "stderr_tail=$stderrPreview"
    }
    exit 2
}

$listenerPid = Get-ListeningProcessId -ListenPort $port
$pidPayload = @{
    launcher_pid = $process.Id
    listener_pid = $listenerPid
    port = $port
    started_at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    health_url = $healthUrl
}
$pidPayload | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $pidPath -Encoding UTF8

Write-BootstrapLog -Level "INFO" -Message "service_ready url=$healthUrl launcher_pid=$($process.Id) listener_pid=$listenerPid"
exit 0
