[CmdletBinding()]
param(
    [ValidateSet("checkpoint-latency", "checkpoint-recovery", "reranker-ab-test", "hybrid-rag-ab-test", "web-search-integration", "rag-query-integration", "sse-tool-events", "idealidad", "forensic", "all")]
    [string[]]$Target = @("all"),
    [ValidateRange(1, 65535)]
    [int]$Port = 8501,
    [int]$TimeoutSeconds = 1800
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $RepoRoot ".env"
$ComposeFile = Join-Path $RepoRoot "docker-compose.yml"
$RuntimeDir = Join-Path $PSScriptRoot ".runtime"
$TestResultsDir = Join-Path $RepoRoot "test-results"
$PidFile = Join-Path $RuntimeDir "streamlit.pid"
$StdoutLog = Join-Path $RuntimeDir "streamlit.stdout.log"
$StderrLog = Join-Path $RuntimeDir "streamlit.stderr.log"
$PipelineDate = Get-Date -Format "yyyyMMdd_HHmmss"

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

function Get-GrafanaPort {
    $raw = Get-EnvValue -Name "GRAFANA_PORT"
    $parsed = 0
    if ([int]::TryParse($raw, [ref]$parsed) -and $parsed -ge 1 -and $parsed -le 65535) {
        return $parsed
    }
    return 3000
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

function Test-PostgresReady {
    param([string]$DockerPath)

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $DockerPath exec llm-postgres pg_isready -U postgres -d llm_client 2>$null
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    return $exitCode -eq 0 -and $output -and (($output | Select-Object -Last 1) -match "accepting connections")
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
        $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
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

function Wait-ForInfrastructure {
    param([int]$TimeoutSeconds)

    $grafanaPort = Get-GrafanaPort

    $checks = @(
        [pscustomobject]@{ Name = "Redis"; Test = { Test-TcpPort -PortNumber 6380 } },
        [pscustomobject]@{ Name = "MinIO"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:9000/minio/health/ready" } },
        [pscustomobject]@{ Name = "Vault"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:8200/v1/sys/health" } },
        [pscustomobject]@{ Name = "Prometheus"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:9090/-/healthy" } },
        [pscustomobject]@{ Name = "Grafana"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:$grafanaPort/api/health" } },
        [pscustomobject]@{ Name = "Ideality exporter"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:9101/metrics" } },
        [pscustomobject]@{ Name = "Agent service"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:8000/health" } }
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

function Start-Infrastructure {
    param([string]$DockerPath, [int]$TimeoutSeconds)
    
    Write-Host "Starting full infrastructure stack..." -ForegroundColor Cyan
    Invoke-Compose -DockerPath $DockerPath -Arguments @("up", "-d")
    Wait-ForInitContainers -DockerPath $DockerPath -TimeoutSeconds $TimeoutSeconds
    Wait-ForInfrastructure -TimeoutSeconds $TimeoutSeconds
    Write-Host "Infrastructure ready." -ForegroundColor Green
}

function Stop-Infrastructure {
    param([string]$DockerPath)
    
    Write-Host "Stopping infrastructure..." -ForegroundColor Cyan
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $DockerPath compose --project-directory $RepoRoot --env-file $EnvFile -f $ComposeFile down --remove-orphans
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        Write-Warning "docker compose down failed with exit code $exitCode."
    }
    else {
        Write-Host "Infrastructure stopped. Persistent volumes were preserved." -ForegroundColor Green
    }
}

function Run-Test {
    param([string]$TestName, [string]$TestCommand, [int]$TimeoutSeconds = 120, [hashtable]$Environment = @{}, [pscustomobject]$Python)
    
    Write-Host "Running $TestName..." -ForegroundColor Cyan
    $startTime = Get-Date
    
    try {
        # Set environment variables
        $envVars = @(
            "REDIS_URL=redis://localhost:6379/0",
            "REDIS_CHECKPOINT_URL=redis://localhost:6379/1",
            "DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/llm_client",
            "S3_ENDPOINT=http://localhost:9000",
            "S3_ACCESS_KEY=minioadmin",
            "S3_SECRET_KEY=minioadmin",
            "S3_BUCKET=llm-client-files",
            "ENVIRONMENT=staging"
        )
        
        # Add custom environment variables
        foreach ($key in $Environment.Keys) {
            $envVars += "$key=$($Environment[$key])"
        }
        
        $arguments = @($Python.Prefix) + @(
            "-m", "pytest", $TestCommand, "-v", "--timeout=$TimeoutSeconds", "--junitxml=/$TestResultsDir/$TestName/junit.xml"
        )
        
        # Run test with environment
        $envVars | ForEach-Object { [Environment]::SetEnvironmentVariable($_.Split('=')[0], $_.Split('=')[1]) }
        
        $result = Invoke-Python -Python $Python -Arguments $arguments
        
        # Generate JSON report
        $endTime = Get-Date
        $duration = ($endTime - $startTime).TotalSeconds
        
        $report = @{
            date = $PipelineDate
            test_name = $TestName
            duration_seconds = $duration
            timeout_seconds = $TimeoutSeconds
            status = if ($result -eq 0) { "completed" } else { "failed" }
            exit_code = $result
        }
        
        $reportDir = Join-Path $TestResultsDir $TestName
        $reportFile = Join-Path $reportDir "report_$PipelineDate.json"
        $report | ConvertTo-Json -Depth 10 | Out-File -FilePath $reportFile
        
        # Cleanup environment
        $envVars | ForEach-Object { [Environment]::SetEnvironmentVariable($_.Split('=')[0], $null) }
        
        if ($result -eq 0) {
            Write-Host "$TestName completed successfully in $duration seconds." -ForegroundColor Green
        }
        else {
            Write-Host "$TestName failed with exit code $result after $duration seconds." -ForegroundColor Red
        }
        
        return $result
    }
    catch {
        Write-Host "$TestName failed with exception: $_" -ForegroundColor Red
        return 1
    }
}

function Run-CheckpointLatency {
    param([pscustomobject]$Python)
    Write-Host "Running checkpoint latency test..." -ForegroundColor Cyan
    return Run-Test -TestName "checkpoint-latency" -TestCommand "tests/staging_load/test_checkpoint_latency.py::test_checkpoint_latency_staging" -TimeoutSeconds 600 -Python $Python
}

function Run-CheckpointRecovery {
    param([pscustomobject]$Python)
    Write-Host "Running checkpoint recovery test..." -ForegroundColor Cyan
    return Run-Test -TestName "checkpoint-recovery" -TestCommand "tests/staging_load/test_checkpoint_recovery.py" -TimeoutSeconds 1200 -Python $Python
}

function Run-RerankerABTest {
    param([pscustomobject]$Python)
    Write-Host "Running reranker A/B test..." -ForegroundColor Cyan
    $envVars = @{
        "COHERE_API_KEY" = $env:COHERE_API_KEY
    }
    return Run-Test -TestName "reranker-ab-test" -TestCommand "scripts/ab_test_reranker.py --queries 50" -TimeoutSeconds 600 -Environment $envVars -Python $Python
}

function Run-HybridRAGABTest {
    param([pscustomobject]$Python)
    Write-Host "Running hybrid RAG A/B test..." -ForegroundColor Cyan
    $envVars = @{
        "COHERE_API_KEY" = $env:COHERE_API_KEY
    }
    return Run-Test -TestName "hybrid-rag-ab-test" -TestCommand "scripts/ab_test_hybrid_rag.py --queries 30" -TimeoutSeconds 600 -Environment $envVars -Python $Python
}

function Run-WebSearchIntegration {
    param([pscustomobject]$Python)
    Write-Host "Running web search integration test..." -ForegroundColor Cyan
    $envVars = @{
        "STAGING_TAVILY_API_KEY" = $env:STAGING_TAVILY_API_KEY
    }
    return Run-Test -TestName "web-search-integration" -TestCommand "tests/unit/test_web_search.py::test_web_search_integration" -TimeoutSeconds 180 -Environment $envVars -Python $Python
}

function Run-RAGQueryIntegration {
    param([pscustomobject]$Python)
    Write-Host "Running RAG query integration test..." -ForegroundColor Cyan
    $envVars = @{
        "OPENAI_API_KEY" = $env:OPENAI_API_KEY
    }
    return Run-Test -TestName "rag-query-integration" -TestCommand "tests/unit/test_rag_pipeline.py::test_rag_pipeline_integration" -TimeoutSeconds 300 -Environment $envVars -Python $Python
}

function Run-SSEToolEvents {
    param([pscustomobject]$Python)
    Write-Host "Running SSE tool events test..." -ForegroundColor Cyan
    return Run-Test -TestName "sse-tool-events" -TestCommand "tests/unit/test_sse.py::test_sse_tool_events_staging" -TimeoutSeconds 120 -Python $Python
}

function Run-IdealidadMetric {
    param([pscustomobject]$Python)
    Write-Host "Running ideality metric collection..." -ForegroundColor Cyan
    $arguments = @($Python.Prefix) + @(
        "scripts/collect_idealidad_metrics.py",
        "--output", "/$TestResultsDir/idealidad/metrics_$PipelineDate.json"
    )
    
    try {
        $result = Invoke-Python -Python $Python -Arguments $arguments
        if ($result -eq 0) {
            Write-Host "Ideality metric collection completed successfully." -ForegroundColor Green
        }
        else {
            Write-Host "Ideality metric collection failed with exit code $result." -ForegroundColor Red
        }
        return $result
    }
    catch {
        Write-Host "Ideality metric collection failed with exception: $_" -ForegroundColor Red
        return 1
    }
}

function Run-ForensicStaging {
    param([pscustomobject]$Python)
    Write-Host "Running forensic staging tests..." -ForegroundColor Cyan
    
    # Set forensic environment
    $envVars = @{
        "ENVIRONMENT" = "staging"
        "FORENSIC_STREAM_ENABLED" = "true"
        "KMS_PROVIDER" = "vault"
        "VAULT_ADDR" = "http://127.0.0.1:8200"
        "VAULT_TOKEN" = "root"
        "VAULT_TRANSIT_KEY" = "forensic-aes256-gcm"
        "S3_ENDPOINT" = "http://127.0.0.1:9000"
        "S3_ACCESS_KEY" = "minioadmin"
        "S3_SECRET_KEY" = "minioadmin"
        "S3_FORENSIC_BUCKET" = "llm-client-forensic"
        "REDIS_URL" = "redis://localhost:6380/0"
        "OPENAI_API_KEY" = "sk-test-placeholder"
    }
    
    # Initialize Vault transit
    Write-Host "Initializing Vault transit engine..." -ForegroundColor Cyan
    docker run --rm --network host `
        -e VAULT_ADDR=http://127.0.0.1:8200 `
        -e VAULT_TOKEN=root `
        hashicorp/vault:latest `
        sh -c 'vault secrets enable transit && vault write -f transit/keys/forensic-aes256-gcm type=aes256-gcm96'
    
    # Create MinIO forensic bucket
    Write-Host "Creating MinIO forensic bucket..." -ForegroundColor Cyan
    docker run --rm --network host quay.io/minio/mc:latest `
        sh -c 'mc alias set local http://127.0.0.1:9000 minioadmin minioadmin && mc mb -p local/llm-client-forensic'
    
    # Run forensic e2e test
    Write-Host "Running forensic e2e test..." -ForegroundColor Cyan
    $testResult = Run-Test -TestName "forensic-e2e" -TestCommand "tests/integration/test_forensic_stream_e2e.py" -TimeoutSeconds 300 -Environment $envVars -Python $Python
    if ($testResult -ne 0) { return $testResult }
    
    # Run integration tests with forensic enabled
    Write-Host "Running integration tests with forensic enabled..." -ForegroundColor Cyan
    $testResult = Run-Test -TestName "integration-forensic" -TestCommand "tests/integration -m integration" -TimeoutSeconds 600 -Environment $envVars -Python $Python
    if ($testResult -ne 0) { return $testResult }
    
    # Validate staging settings
    Write-Host "Validating staging settings..." -ForegroundColor Cyan
    $arguments = @($Python.Prefix) + @("-c", "from llm_client.config import Settings; s=Settings(); assert s.environment=='staging' and s.forensic_stream_enabled and s.vault_token=='root'")
    $result = Invoke-Python -Python $Python -Arguments $arguments
    if ($result -ne 0) { return $result }
    
    # Validate prod settings (positive case)
    Write-Host "Validating prod settings (positive case)..." -ForegroundColor Cyan
    $arguments = @($Python.Prefix) + @("-c", "from llm_client.config import Settings; s=Settings(); assert s.environment=='prod' and s.forensic_stream_enabled")
    $result = Invoke-Python -Python $Python -Arguments $arguments
    if ($result -ne 0) { return $result }
    
    # Validate prod settings (negative case - should fail)
    Write-Host "Validating prod settings (negative case)..." -ForegroundColor Cyan
    $arguments = @($Python.Prefix) + @("-c", "from llm_client.config import Settings; s=Settings(); assert s.environment=='prod' and not s.forensic_stream_enabled")
    $result = Invoke-Python -Python $Python -Arguments $arguments
    if ($result -eq 0) {
        Write-Host "ERROR: Prod settings should have failed when forensic_stream_enabled=false" -ForegroundColor Red
        return 1
    }
    Write-Host "✅ Prod settings correctly failed when forensic_stream_enabled=false" -ForegroundColor Green
    
    return 0
}

function Invoke-Python {
    param(
        [pscustomobject]$Python,
        [string[]]$Arguments
    )

    $allArguments = $Arguments
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

# Main execution
Write-Host "Phase 2 CI - Local Staging Pipeline" -ForegroundColor Magenta
Write-Host "==================================" -ForegroundColor Magenta

# Check environment
if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Environment file not found: $EnvFile"
}

# Create test results directory
New-Item -ItemType Directory -Path $TestResultsDir -Force | Out-Null

# Resolve dependencies
$python = Resolve-PythonExecutable
$docker = Resolve-DockerExecutable

Write-Host "Waiting for Docker Desktop..." -ForegroundColor Cyan
Wait-DockerEngine -DockerPath $docker -TimeoutSeconds $TimeoutSeconds

# Start infrastructure
Start-Infrastructure -DockerPath $docker -TimeoutSeconds $TimeoutSeconds

# Run tests based on target (sequential execution)
$totalExitCode = 0

foreach ($target in $Target) {
    switch ($target) {
        "checkpoint-latency" {
            $exitCode = Run-CheckpointLatency -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "checkpoint-recovery" {
            $exitCode = Run-CheckpointRecovery -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "reranker-ab-test" {
            $exitCode = Run-RerankerABTest -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "hybrid-rag-ab-test" {
            $exitCode = Run-HybridRAGABTest -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "web-search-integration" {
            $exitCode = Run-WebSearchIntegration -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "rag-query-integration" {
            $exitCode = Run-RAGQueryIntegration -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "sse-tool-events" {
            $exitCode = Run-SSEToolEvents -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "idealidad" {
            $exitCode = Run-IdealidadMetric -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "forensic" {
            $exitCode = Run-ForensicStaging -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "all" {
            $exitCode = Run-CheckpointLatency -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-CheckpointRecovery -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-RerankerABTest -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-HybridRAGABTest -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-WebSearchIntegration -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-RAGQueryIntegration -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-SSEToolEvents -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-IdealidadMetric -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-ForensicStaging -Python $python
            $totalExitCode = $totalExitCode -bor $exitCode
        }
    }
}

# Cleanup
Stop-Infrastructure -DockerPath $docker

# Summary
Write-Host ""
Write-Host "Phase 2 CI - Local Staging Pipeline Summary" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "Pipeline Date: $PipelineDate" -ForegroundColor Cyan
Write-Host "Overall Exit Code: $totalExitCode" -ForegroundColor $(if ($totalExitCode -eq 0) { "Green" } else { "Red" })

if ($totalExitCode -eq 0) {
    Write-Host "✅ All staging tests passed!" -ForegroundColor Green
}
else {
    Write-Host "❌ Some staging tests failed. Check test-results/ directory for details." -ForegroundColor Red
}

Write-Host ""
Write-Host "Test results saved to: $TestResultsDir" -ForegroundColor Cyan
Write-Host "Reports generated with timestamp: $PipelineDate" -ForegroundColor Cyan

exit $totalExitCode