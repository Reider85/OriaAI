[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8501,
    [ValidateRange(30, 3600)]
    [int]$StartupTimeoutSeconds = 300,
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

    # Last occurrence wins, matching docker compose / dotenv semantics.
    $resolved = $Default
    $found = $false

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

        $found = $true
        $value = $trimmed.Substring($separatorIndex + 1).Trim().Trim('"').Trim("'")
        $resolved = if ($value.Length -eq 0) { $Default } else { $value }
    }

    if ($found) {
        return $resolved
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

function Test-PostgresContainerStarting {
    param([string]$DockerPath)

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $state = & $DockerPath inspect --format "{{.State.Status}}" llm-postgres 2>$null
        $inspectExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($inspectExitCode -ne 0 -or -not $state) {
        return $false
    }

    $status = ($state | Select-Object -Last 1).Trim()
    return $status -eq "running" -or $status -eq "restarting" -or $status -eq "created"
}

function Invoke-Compose {
    param(
        [string]$DockerPath,
        [string[]]$Arguments
    )

    $maxAttempts = 1
    if ($Arguments -contains "up") {
        $maxAttempts = 2
    }

    $exitCode = 1
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $DockerPath compose --project-directory $RepoRoot --env-file $EnvFile -f $ComposeFile @Arguments
            $exitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }

        if ($exitCode -eq 0) {
            return
        }

        $shouldRetry = $attempt -lt $maxAttempts -and
            (Test-PostgresContainerStarting -DockerPath $DockerPath) -and
            -not (Test-PostgresReady -DockerPath $DockerPath)

        if (-not $shouldRetry) {
            throw "docker compose $($Arguments -join ' ') failed with exit code $exitCode."
        }

        Write-Host "Postgres is still starting (crash recovery can take >120s after unclean Docker shutdown); waiting before retrying docker compose up..." -ForegroundColor Yellow
        $deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
        while ([DateTime]::UtcNow -lt $deadline) {
            if (Test-PostgresReady -DockerPath $DockerPath) {
                break
            }
            Start-Sleep -Seconds 2
        }
    }

    throw "docker compose $($Arguments -join ' ') failed with exit code $exitCode."
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
    param(
        [string]$DockerPath,
        [int]$TimeoutSeconds
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)

    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-HttpEndpoint -Uri "http://127.0.0.1:8000/health") {
            return
        }
        Start-Sleep -Seconds 2
    }

    $logs = Invoke-DockerExec -DockerPath $DockerPath -Arguments @(
        "logs",
        "--tail",
        "20",
        "llm-agent-service"
    )
    $logText = if ($logs) { "`nLast container output:`n$logs" } else { "" }
    throw "Agent service did not become ready within $TimeoutSeconds seconds on port 8000. It runs 'pip install -e .' on every start, so the first start after an image rebuild takes much longer (subsequent starts reuse the pip cache volume).$logText"
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

function Get-EffectiveRerankerDefault {
    $rerankerDefault = (Get-EnvValue -Name "RERANKER_DEFAULT")
    if (-not $rerankerDefault) {
        $rerankerDefault = "bge"
    }

    # If Cohere is selected but no API key is available, fall back to BGE
    if ($rerankerDefault -eq "cohere" -and -not (Get-EnvValue -Name "COHERE_API_KEY")) {
        $rerankerDefault = "bge"
    }

    return $rerankerDefault
}

function Ensure-RerankerModel {
    param(
        [pscustomobject]$Python,
        [switch]$Skip
    )

    if ($Skip) {
        Write-Host "Skipping reranker model check (-SkipModelDownload)." -ForegroundColor DarkGray
        return $false
    }

    $effectiveDefault = Get-EffectiveRerankerDefault
    if ($effectiveDefault -ne "bge") {
        Write-Host "Effective reranker=$effectiveDefault; BGE model download is not required." -ForegroundColor DarkGray
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

function Get-EffectiveEmbeddingProvider {
    $provider = (Get-EnvValue -Name "EMBEDDING_PROVIDER")
    if (-not $provider) {
        $provider = "openai"
    }

    # If provider is explicitly none, return none (no download)
    if ($provider -eq "none") {
        return "none"
    }

    # If provider is explicitly local, return local (download if needed)
    if ($provider -eq "local") {
        return "local"
    }

    # For cloud providers, check if API keys are available
    if ($provider -eq "openai" -and -not (Get-EnvValue -Name "OPENAI_API_KEY")) {
        return "local"
    }
    if ($provider -eq "zai" -and -not (Get-EnvValue -Name "ZAI_API_KEY")) {
        return "local"
    }
    if ($provider -eq "custom-openai" -and (-not (Get-EnvValue -Name "CUSTOM_OPENAI_API_KEY") -or -not (Get-EnvValue -Name "CUSTOM_OPENAI_BASE_URL"))) {
        return "local"
    }

    return $provider
}

function Ensure-EmbeddingModel {
    param(
        [pscustomobject]$Python,
        [switch]$Skip
    )

    if ($Skip) {
        Write-Host "Skipping embedding model check (-SkipModelDownload)." -ForegroundColor DarkGray
        return $false
    }

    $effectiveProvider = Get-EffectiveEmbeddingProvider
    if ($effectiveProvider -ne "local") {
        Write-Host "Effective embedding provider=$effectiveProvider; local model download is not required." -ForegroundColor DarkGray
        return $false
    }

    $modelDir = Get-EnvValue -Name "LOCAL_EMBEDDING_MODEL_DIR"
    if (-not $modelDir) {
        $modelDir = "./models/bge-m3"
    }
    if (-not [System.IO.Path]::IsPathRooted($modelDir)) {
        $modelDir = Join-Path $RepoRoot $modelDir.TrimStart(".", "/", "\")
    }

    if (Test-Path -LiteralPath (Join-Path $modelDir "config.json")) {
        Write-Host "Local embedding model is present at $modelDir." -ForegroundColor DarkGray
        return $true
    }

    Write-Host "Downloading local embedding model (BAAI/bge-m3, ~2.2GB, one-time)..." -ForegroundColor Cyan
    $downloadScript = Join-Path $RepoRoot "scripts\download_embedding_model.py"
    if (-not (Test-Path -LiteralPath $downloadScript)) {
        throw "Local embedding model is missing and scripts\download_embedding_model.py was not found."
    }

    $previousLocation = Get-Location
    try {
        Set-Location -LiteralPath $RepoRoot
        $exitCode = Invoke-Python -Python $Python -Arguments @("scripts\download_embedding_model.py")
    }
    finally {
        Set-Location -LiteralPath $previousLocation
    }

    if ($exitCode -ne 0) {
        throw "Local embedding model download failed with exit code $exitCode. Run manually: $($Python.Path) scripts\download_embedding_model.py"
    }

    return $true
}

function Get-GrafanaPort {
    $raw = Get-EnvValue -Name "GRAFANA_PORT"
    $parsed = 0
    if ([int]::TryParse($raw, [ref]$parsed) -and $parsed -ge 1 -and $parsed -le 65535) {
        return $parsed
    }
    return 3000
}

function Get-ConflictingContainer {
    param(
        [string]$DockerPath,
        [int]$PortNumber
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $lines = & $DockerPath ps --format "{{.Names}}|{{.Ports}}" 2>$null
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    foreach ($line in @($lines)) {
        if (-not $line) {
            continue
        }
        $parts = $line -split "\|", 2
        if ($parts.Count -lt 2) {
            continue
        }

        $name = $parts[0].Trim()
        $portPattern = '(?i)(?:^|[:,])' + $PortNumber + '(?:->|:|$)'
        if ($parts[1] -match $portPattern) {
            return $name
        }
    }

    return $null
}

function Assert-HostPortsAvailable {
    param(
        [string]$DockerPath,
        [int[]]$PortNumbers
    )

    $conflicts = @()
    foreach ($portNumber in $PortNumbers) {
        if (-not (Test-TcpPort -PortNumber $portNumber)) {
            continue
        }

        $owners = @(
            Get-NetTCPConnection -LocalPort $portNumber -State Listen -ErrorAction SilentlyContinue |
                Where-Object { $_.OwningProcess } |
                ForEach-Object { (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName } |
                Where-Object { $_ } |
                Sort-Object -Unique
        )

        $isDockerOwned = $owners -contains "com.docker.backend"
        if ($isDockerOwned) {
            $container = Get-ConflictingContainer -DockerPath $DockerPath -PortNumber $portNumber
            if (-not $container) {
                continue
            }
            if ($container.StartsWith("llm-")) {
                continue
            }
            $conflicts += "  ${portNumber}: container '$container' from another compose project"
            continue
        }

        $conflicts += "  ${portNumber}: process $($owners -join ', ')"
    }

    if ($conflicts.Count -gt 0) {
        throw "Host ports are already in use:`n$($conflicts -join "`n")`nStop those owners, or override the port in .env (e.g. GRAFANA_PORT)."
    }
}

function Wait-ForInfrastructure {
    param(
        [string]$DockerPath,
        [int]$TimeoutSeconds,
        [int]$GrafanaPort
    )

    $checks = @(
        [pscustomobject]@{ Name = "Redis"; Test = { Test-TcpPort -PortNumber 6380 } },
        [pscustomobject]@{ Name = "PostgreSQL"; Test = { Test-PostgresReady -DockerPath $DockerPath } },
        [pscustomobject]@{ Name = "MinIO"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:9000/minio/health/ready" } },
        [pscustomobject]@{ Name = "Vault"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:8200/v1/sys/health" } },
        [pscustomobject]@{ Name = "Prometheus"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:9090/-/healthy" } },
        [pscustomobject]@{ Name = "Grafana"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:$GrafanaPort/api/health" } },
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

$rerankerModelReady = Ensure-RerankerModel -Python $python -Skip:$SkipModelDownload
$embeddingModelReady = Ensure-EmbeddingModel -Python $python -Skip:$SkipModelDownload

if (-not (Get-EnvValue -Name "TAVILY_API_KEY")) {
    $toolsEnabled = Get-EnvValue -Name "TOOLS_ENABLED"
    $defaultTools = "file_export,web_search,rag_query"
    if (-not $toolsEnabled -or $toolsEnabled -eq $defaultTools -or $toolsEnabled.Contains("web_search")) {
        Write-Host "Error: TAVILY_API_KEY is required when web_search is enabled (default in TOOLS_ENABLED). Set TAVILY_API_KEY or remove 'web_search' from TOOLS_ENABLED." -ForegroundColor Red
        exit 1
    } else {
        Write-Host "Warning: TAVILY_API_KEY is empty, but web_search is not enabled in TOOLS_ENABLED." -ForegroundColor Yellow
    }
}

$docker = Resolve-DockerExecutable
$grafanaPort = Get-GrafanaPort
Write-Host "Waiting for Docker Desktop..." -ForegroundColor Cyan
Wait-DockerEngine -DockerPath $docker -TimeoutSeconds $StartupTimeoutSeconds
Assert-HostPortsAvailable -DockerPath $docker -PortNumbers @(5434, 6380, 8000, 8200, 9000, 9001, 9090, 9101, $grafanaPort)
Write-Host "Starting infrastructure..." -ForegroundColor Cyan
Invoke-Compose -DockerPath $docker -Arguments @("up", "-d")
Wait-ForInitContainers -DockerPath $docker -TimeoutSeconds $StartupTimeoutSeconds
Wait-ForInfrastructure -DockerPath $docker -TimeoutSeconds $StartupTimeoutSeconds -GrafanaPort $grafanaPort
Write-Host "Verifying checkpoint WAL (ADR-010)..." -ForegroundColor Cyan
Test-CheckpointRedis -DockerPath $docker
Write-Host "Waiting for agent-service (first start installs dependencies, this can take a while)..." -ForegroundColor Cyan
Wait-ForAgentService -DockerPath $docker -TimeoutSeconds $StartupTimeoutSeconds
Write-Host "Starting Streamlit UI..." -ForegroundColor Cyan
Start-Streamlit -Python $python -PortNumber $Port

$rerankerStatus = (Get-EnvValue -Name "RERANKER_DEFAULT" "bge")
if ($rerankerModelReady) {
    $rerankerStatus = "$rerankerStatus (model ready)"
}
elseif ($SkipModelDownload -or $rerankerStatus -ne "bge") {
    $rerankerStatus = "$rerankerStatus (model not verified)"
}

$embeddingStatus = (Get-EffectiveEmbeddingProvider)
if ($embeddingModelReady -and $embeddingStatus -eq "local") {
    $embeddingStatus = "local bge-m3 (model ready)"
}
else {
    $embeddingStatus = "$embeddingStatus (cloud or disabled)"
}

Write-Host ""
Write-Host "OriaAI is running:" -ForegroundColor Green
Write-Host "  UI:          http://127.0.0.1:$Port"
Write-Host "  Agent:       http://127.0.0.1:8000"
Write-Host "  PostgreSQL:  127.0.0.1:5434 (db llm_client)"
Write-Host "  Redis:       127.0.0.1:6380 (db 0 pub/sub, db 1 checkpoint WAL)"
Write-Host "  MinIO:       http://127.0.0.1:9001"
Write-Host "  Grafana:     http://127.0.0.1:$grafanaPort"
Write-Host "  Prometheus:  http://127.0.0.1:9090"
Write-Host "  Vault:       http://127.0.0.1:8200"
Write-Host "  Ideality:    http://127.0.0.1:9101/metrics"
Write-Host "  Reranker:    $rerankerStatus"
Write-Host "  Embeddings:  $embeddingStatus"
Write-Host "  Logs:        $RuntimeDir"
Write-Host ""
Write-Host "Stop everything with: powershell -ExecutionPolicy Bypass -File scripts\stop.ps1"
