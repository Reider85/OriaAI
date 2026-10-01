[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8501,
    [ValidateRange(30, 900)]
    [int]$StartupTimeoutSeconds = 180,
    [switch]$SkipModelDownload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $RepoRoot ".env"
$EnvExampleFile = Join-Path $RepoRoot ".env.example"
$ComposeFile = Join-Path $RepoRoot "docker-compose.yml"
$AppFile = Join-Path $RepoRoot "src\llm_client\ui\app.py"
$RuntimeDir = Join-Path $PSScriptRoot ".runtime"
$PidFile = Join-Path $RuntimeDir "streamlit.pid"
$StdoutLog = Join-Path $RuntimeDir "streamlit.stdout.log"
$StderrLog = Join-Path $RuntimeDir "streamlit.stderr.log"

function Get-EnvValue {
    param(
        [string]$Name,
        [string]$Default = ""
    )

    if (-not (Test-Path -LiteralPath $EnvFile)) {
        return $Default
    }

    foreach ($line in Get-Content -LiteralPath $EnvFile) {
        $trimmed = $line.Trim()
        if ($trimmed.StartsWith("#")) {
            continue
        }

        $separatorIndex = $trimmed.IndexOf("=")
        if ($separatorIndex -le 0) {
            continue
        }

        $key = $trimmed.Substring(0, $separatorIndex).Trim()
        if ($key -ne $Name) {
            continue
        }

        $value = $trimmed.Substring($separatorIndex + 1).Trim()
        if ($value.Length -eq 0) {
            return $Default
        }
        return $value.Trim('"').Trim("'")
    }

    return $Default
}

function Invoke-NativeQuiet {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $FilePath @Arguments 2>$null | Out-Null
        return $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Test-PythonExecutable {
    param(
        [string]$Path,
        [string[]]$Prefix = @()
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    $arguments = @($Prefix) + @(
        "-c",
        "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    )
    return (Invoke-NativeQuiet -FilePath $Path -Arguments $arguments) -eq 0
}

function Resolve-PythonExecutable {
    $candidates = @()

    $virtualEnvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    $candidates += [pscustomobject]@{ Path = $virtualEnvPython; Prefix = @() }

    if ($env:LOCALAPPDATA) {
        foreach ($version in @("313", "312", "311", "310")) {
            $path = Join-Path $env:LOCALAPPDATA "Programs\Python\Python$version\python.exe"
            $candidates += [pscustomobject]@{ Path = $path; Prefix = @() }
        }
    }

    if ($env:ProgramFiles) {
        foreach ($version in @("313", "312", "311", "310")) {
            $path = Join-Path $env:ProgramFiles "Python$version\python.exe"
            $candidates += [pscustomobject]@{ Path = $path; Prefix = @() }
        }
    }

    $pyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $candidates += [pscustomobject]@{ Path = $pyLauncher.Source; Prefix = @("-3.11") }
        $candidates += [pscustomobject]@{ Path = $pyLauncher.Source; Prefix = @("-3") }
    }

    foreach ($commandName in @("python.exe", "python3.exe", "python", "python3")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command) {
            $candidates += [pscustomobject]@{ Path = $command.Source; Prefix = @() }
        }
    }

    foreach ($candidate in $candidates) {
        if (Test-PythonExecutable -Path $candidate.Path -Prefix $candidate.Prefix) {
            return $candidate
        }
    }

    throw "Python 3.11+ was not found. Install Python or create .venv in the project root."
}

function Invoke-Python {
    param(
        [pscustomobject]$Python,
        [string[]]$Arguments
    )

    $allArguments = @($Python.Prefix) + @($Arguments)
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Python.Path @allArguments
        return $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Resolve-DockerExecutable {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"),
        (Join-Path $env:LOCALAPPDATA "Docker\resources\bin\docker.exe")
    )

    $command = Get-Command "docker.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw "Docker Desktop was not found. Install Docker Desktop with WSL2 and run this script again."
}

function Test-DockerEngine {
    param([string]$DockerPath)

    $arguments = @("info", "--format", "{{.ServerVersion}}")
    return (Invoke-NativeQuiet -FilePath $DockerPath -Arguments $arguments) -eq 0
}

function Wait-DockerEngine {
    param(
        [string]$DockerPath,
        [int]$TimeoutSeconds
    )

    if (Test-DockerEngine -DockerPath $DockerPath) {
        return
    }

    $desktopPath = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $desktopPath)) {
        throw "Docker CLI exists, but Docker Desktop was not found at $desktopPath."
    }

    Start-Process -FilePath $desktopPath -WindowStyle Hidden
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)

    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Seconds 2
        if (Test-DockerEngine -DockerPath $DockerPath) {
            return
        }
    }

    throw "Docker Desktop did not become ready within $TimeoutSeconds seconds."
}

function Invoke-Compose {
    param(
        [string]$DockerPath,
        [string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $DockerPath compose --project-directory $RepoRoot --env-file $EnvFile -f $ComposeFile @Arguments
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        throw "docker compose $($Arguments -join ' ') failed with exit code $exitCode."
    }
}

function Wait-ForInitContainers {
    param(
        [string]$DockerPath,
        [int]$TimeoutSeconds
    )

    $containerNames = @("llm-minio-init", "llm-vault-init")
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)

    while ([DateTime]::UtcNow -lt $deadline) {
        $pending = @()

        foreach ($containerName in $containerNames) {
            $previousErrorActionPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                $state = & $DockerPath inspect --format "{{.State.Status}}|{{.State.ExitCode}}" $containerName 2>$null
                $inspectExitCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }

            if ($inspectExitCode -ne 0 -or -not $state) {
                $pending += $containerName
                continue
            }

            $stateValue = ($state | Select-Object -Last 1).Trim()
            if ($stateValue -eq "exited|0") {
                continue
            }

            if ($stateValue -match "^exited\|([1-9][0-9]*)$") {
                throw "Initialization container $containerName failed with exit code $($Matches[1])."
            }

            $pending += $containerName
        }

        if ($pending.Count -eq 0) {
            return
        }

        Start-Sleep -Seconds 1
    }

    $names = ($containerNames -join ", ")
    throw "Initialization containers did not complete within $TimeoutSeconds seconds: $names"
}

function Test-HttpEndpoint {
    param([string]$Uri)

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 300
    }
    catch {
        return $false
    }
}

function Test-TcpPort {
    param([int]$PortNumber)

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect("127.0.0.1", $PortNumber)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Wait-ForAgentService {
    param([int]$TimeoutSeconds = 30)

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)

    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-HttpEndpoint -Uri "http://127.0.0.1:8000/health") {
            return
        }
        Start-Sleep -Seconds 2
    }

    throw "Agent service did not become ready within $TimeoutSeconds seconds on port 8000."
}

function Invoke-DockerExec {
    param(
        [string]$DockerPath,
        [string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $DockerPath exec $Arguments 2>$null
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        return $null
    }

    return (($output | Where-Object { $_ }) -join " ").Trim()
}

function Test-PostgresReady {
    param([string]$DockerPath)

    if (-not (Test-TcpPort -PortNumber 5434)) {
        return $false
    }

    $output = Invoke-DockerExec -DockerPath $DockerPath -Arguments @(
        "llm-postgres",
        "pg_isready",
        "-U",
        "postgres",
        "-d",
        "llm_client"
    )
    return $null -ne $output -and $output -match "accepting connections"
}

function Test-CheckpointRedis {
    param([string]$DockerPath)

    $ping = Invoke-DockerExec -DockerPath $DockerPath -Arguments @(
        "llm-redis",
        "redis-cli",
        "-n",
        "1",
        "PING"
    )
    if ($null -eq $ping -or $ping -notmatch "PONG") {
        throw "Redis checkpoint WAL (DB 1) is not reachable in container llm-redis."
    }

    $policy = Invoke-DockerExec -DockerPath $DockerPath -Arguments @(
        "llm-redis",
        "redis-cli",
        "CONFIG",
        "GET",
        "maxmemory-policy"
    )
    $expectedPolicy = "noeviction"
    if ($null -eq $policy -or $policy -notmatch [regex]::Escape($expectedPolicy)) {
        Write-Host "Warning: Redis maxmemory-policy is '$policy' but ADR-010 requires '$expectedPolicy' for the checkpoint WAL (A-1)." -ForegroundColor Yellow
        return
    }

    Write-Host "Redis checkpoint WAL (DB 1) is ready with maxmemory-policy=$expectedPolicy." -ForegroundColor DarkGray
}

function Ensure-BgeModel {
    param(
        [pscustomobject]$Python,
        [switch]$Skip
    )

    if ($Skip) {
        Write-Host "Skipping BGE reranker model check (-SkipModelDownload)." -ForegroundColor DarkGray
        return $false
    }

    $rerankerDefault = (Get-EnvValue -Name "RERANKER_DEFAULT")
    if (-not $rerankerDefault) {
        $rerankerDefault = "bge"
    }

    if ($rerankerDefault -ne "bge") {
        Write-Host "RERANKER_DEFAULT=$rerankerDefault; BGE model download is not required." -ForegroundColor DarkGray
        return $false
    }

    $modelDir = Get-EnvValue -Name "RERANKER_MODEL_DIR"
    if (-not $modelDir) {
        $modelDir = "./models/bge-reranker-base"
    }
    if (-not [System.IO.Path]::IsPathRooted($modelDir)) {
        $modelDir = Join-Path $RepoRoot $modelDir.TrimStart(".", "/", "\")
    }

    if (Test-Path -LiteralPath (Join-Path $modelDir "config.json")) {
        Write-Host "BGE reranker model is present at $modelDir." -ForegroundColor DarkGray
        return $true
    }

    Write-Host "Downloading BGE reranker model (ADR-017, ~600MB, one-time)..." -ForegroundColor Cyan
    $downloadScript = Join-Path $RepoRoot "scripts\download_bge_reranker.py"
    if (-not (Test-Path -LiteralPath $downloadScript)) {
        throw "BGE reranker model is missing and scripts\download_bge_reranker.py was not found."
    }

    $previousLocation = Get-Location
    try {
        Set-Location -LiteralPath $RepoRoot
        $exitCode = Invoke-Python -Python $Python -Arguments @("scripts\download_bge_reranker.py")
    }
    finally {
        Set-Location -LiteralPath $previousLocation
    }

    if ($exitCode -ne 0) {
        throw "BGE reranker download failed with exit code $exitCode. Run manually: $($Python.Path) scripts\download_bge_reranker.py"
    }

    return $true
}

function Wait-ForInfrastructure {
    param(
        [string]$DockerPath,
        [int]$TimeoutSeconds
    )

    $checks = @(
        [pscustomobject]@{ Name = "Redis"; Test = { Test-TcpPort -PortNumber 6380 } },
        [pscustomobject]@{ Name = "PostgreSQL"; Test = { Test-PostgresReady -DockerPath $DockerPath } },
        [pscustomobject]@{ Name = "MinIO"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:9000/minio/health/ready" } },
        [pscustomobject]@{ Name = "Vault"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:8200/v1/sys/health" } },
        [pscustomobject]@{ Name = "Prometheus"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:9090/-/healthy" } },
        [pscustomobject]@{ Name = "Grafana"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:3000/api/health" } },
        [pscustomobject]@{ Name = "Ideality exporter"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:9101/metrics" } }
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $pending = @($checks)

    while ($pending.Count -gt 0 -and [DateTime]::UtcNow -lt $deadline) {
        $pending = @($pending | Where-Object { -not (& $_.Test) })
        if ($pending.Count -gt 0) {
            Start-Sleep -Seconds 2
        }
    }

    if ($pending.Count -gt 0) {
        $names = ($pending | ForEach-Object { $_.Name }) -join ", "
        throw "Infrastructure did not become ready within $TimeoutSeconds seconds: $names"
    }
}

function Test-OwnedUiProcess {
    param(
        [pscustomobject]$Process,
        [int]$ExpectedPort
    )

    if (-not $Process -or [string]::IsNullOrWhiteSpace($Process.CommandLine)) {
        return $false
    }

    $normalizedAppFile = $AppFile.Replace("/", "\")
    $appPattern = '(?i)(?:^|\s)"?' + [regex]::Escape($normalizedAppFile) + '"?(?:\s|$)'
    $streamlitPattern = "(?i)(?:^|\s)streamlit(?:\s|$)"
    if ($Process.CommandLine -notmatch $appPattern -or $Process.CommandLine -notmatch $streamlitPattern) {
        return $false
    }

    if ($ExpectedPort -gt 0) {
        $portPattern = '(?i)(?:^|\s)--server\.port(?:\s+|=)"?' + $ExpectedPort + '"?(?:\s|$)'
        return $Process.CommandLine -match $portPattern
    }

    return $true
}

function Get-OwnedUiProcess {
    param([int]$ExpectedPort)

    if (Test-Path -LiteralPath $PidFile) {
        try {
            $storedPid = [int](Get-Content -LiteralPath $PidFile -Raw).Trim()
            $storedProcess = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $storedPid" -ErrorAction SilentlyContinue
            if (Test-OwnedUiProcess -Process $storedProcess -ExpectedPort $ExpectedPort) {
                return $storedProcess
            }

            Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        }
        catch {
            Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        }
    }

    return Get-CimInstance -ClassName Win32_Process |
        Where-Object { Test-OwnedUiProcess -Process $_ -ExpectedPort $ExpectedPort } |
        Select-Object -First 1
}

function Start-Streamlit {
    param(
        [pscustomobject]$Python,
        [int]$PortNumber
    )

    $existingProcess = Get-OwnedUiProcess -ExpectedPort $PortNumber
    if ($existingProcess) {
        if (Test-HttpEndpoint -Uri "http://127.0.0.1:$PortNumber/_stcore/health") {
            Write-Host "Streamlit is already running at http://127.0.0.1:$PortNumber" -ForegroundColor Yellow
            return
        }
        Stop-Process -Id $existingProcess.ProcessId -Force -ErrorAction SilentlyContinue
    }

    if (Test-TcpPort -PortNumber $PortNumber) {
        throw "Port $PortNumber is already used by another process."
    }

    New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
    Remove-Item -LiteralPath $StdoutLog, $StderrLog -Force -ErrorAction SilentlyContinue

    $srcPath = Join-Path $RepoRoot "src"
    $env:PYTHONPATH = if ($env:PYTHONPATH) { "$srcPath;$env:PYTHONPATH" } else { $srcPath }

    $arguments = @($Python.Prefix) + @(
        "-m",
        "streamlit",
        "run",
        "`"$AppFile`"",
        "--server.port",
        "$PortNumber",
        "--server.address",
        "127.0.0.1",
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false"
    )

    $process = Start-Process `
        -FilePath $Python.Path `
        -ArgumentList $arguments `
        -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog `
        -WindowStyle Hidden `
        -PassThru

    Set-Content -LiteralPath $PidFile -Value $process.Id -Encoding ASCII

    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    while ([DateTime]::UtcNow -lt $deadline) {
        $process.Refresh()
        if ($process.HasExited) {
            $errorText = if (Test-Path -LiteralPath $StderrLog) {
                Get-Content -LiteralPath $StderrLog -Raw
            } else {
                ""
            }
            Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
            throw "Streamlit exited during startup. $errorText"
        }

        if (Test-HttpEndpoint -Uri "http://127.0.0.1:$PortNumber/_stcore/health") {
            return
        }

        Start-Sleep -Milliseconds 500
    }

    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    throw "Streamlit did not become ready within 60 seconds. See $StderrLog"
}

if (-not (Test-Path -LiteralPath $EnvExampleFile)) {
    throw "Environment template not found: $EnvExampleFile"
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    Copy-Item -LiteralPath $EnvExampleFile -Destination $EnvFile
    Write-Host "Created .env from .env.example" -ForegroundColor Yellow
}

$python = Resolve-PythonExecutable
$dependencyCheck = Invoke-Python -Python $python -Arguments @(
    "-c",
    "import streamlit, httpx, pydantic"
)
if ($dependencyCheck -ne 0) {
    throw "UI dependencies are missing. Run: $($python.Path) -m pip install -e `"$RepoRoot`""
}

$bgeModelReady = Ensure-BgeModel -Python $python -Skip:$SkipModelDownload

if (-not (Get-EnvValue -Name "TAVILY_API_KEY")) {
    Write-Host "Warning: TAVILY_API_KEY is empty. The web_search tool (AG-5) will not reach Tavily." -ForegroundColor Yellow
}

$docker = Resolve-DockerExecutable
Write-Host "Waiting for Docker Desktop..." -ForegroundColor Cyan
Wait-DockerEngine -DockerPath $docker -TimeoutSeconds $StartupTimeoutSeconds
Write-Host "Starting infrastructure..." -ForegroundColor Cyan
Invoke-Compose -DockerPath $docker -Arguments @("up", "-d")
Wait-ForInitContainers -DockerPath $docker -TimeoutSeconds $StartupTimeoutSeconds
Wait-ForInfrastructure -DockerPath $docker -TimeoutSeconds $StartupTimeoutSeconds
Write-Host "Verifying checkpoint WAL (ADR-010)..." -ForegroundColor Cyan
Test-CheckpointRedis -DockerPath $docker
Write-Host "Waiting for agent-service..." -ForegroundColor Cyan
Wait-ForAgentService -TimeoutSeconds 30
Write-Host "Starting Streamlit UI..." -ForegroundColor Cyan
Start-Streamlit -Python $python -PortNumber $Port

$rerankerStatus = (Get-EnvValue -Name "RERANKER_DEFAULT" "bge")
if ($bgeModelReady) {
    $rerankerStatus = "$rerankerStatus (model ready)"
}
elseif ($SkipModelDownload -or $rerankerStatus -ne "bge") {
    $rerankerStatus = "$rerankerStatus (model not verified)"
}

Write-Host ""
Write-Host "OriaAI is running:" -ForegroundColor Green
Write-Host "  UI:          http://127.0.0.1:$Port"
Write-Host "  Agent:       http://127.0.0.1:8000"
Write-Host "  PostgreSQL:  127.0.0.1:5434 (db llm_client)"
Write-Host "  Redis:       127.0.0.1:6380 (db 0 pub/sub, db 1 checkpoint WAL)"
Write-Host "  MinIO:       http://127.0.0.1:9001"
Write-Host "  Grafana:     http://127.0.0.1:3000"
Write-Host "  Prometheus:  http://127.0.0.1:9090"
Write-Host "  Vault:       http://127.0.0.1:8200"
Write-Host "  Ideality:    http://127.0.0.1:9101/metrics"
Write-Host "  Reranker:    $rerankerStatus"
Write-Host "  Logs:        $RuntimeDir"
Write-Host ""
Write-Host "Stop everything with: powershell -ExecutionPolicy Bypass -File scripts\stop.ps1"
