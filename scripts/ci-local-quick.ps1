[CmdletBinding()]
param(
    [ValidateSet("lint", "typecheck", "unit", "integration", "checkpoint", "bm25", "reranker", "hybrid-rag", "web-search", "rag-query", "ui", "all")]
    [string[]]$Target = @("all"),
    [ValidateRange(1, 65535)]
    [int]$Port = 8501,
    [int]$TimeoutSeconds = 300
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

function Wait-ForInfrastructure {
    param([int]$TimeoutSeconds)

    $checks = @(
        [pscustomobject]@{ Name = "Redis"; Test = { Test-TcpPort -PortNumber 6380 } },
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

function Start-Infrastructure {
    param([string]$DockerPath, [int]$TimeoutSeconds)
    
    Write-Host "Starting infrastructure..." -ForegroundColor Cyan
    Invoke-Compose -DockerPath $docker -Arguments @("up", "-d")
    Wait-ForInitContainers -DockerPath $docker -TimeoutSeconds $TimeoutSeconds
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
    param([string]$TestName, [string]$TestCommand, [int]$TimeoutSeconds = 120)
    
    Write-Host "Running $TestName..." -ForegroundColor Cyan
    $startTime = Get-Date
    
    try {
        $arguments = @($python.Prefix) + @(
            "-m", "pytest", $TestCommand, "-v", "-x", "--timeout=$TimeoutSeconds"
        )
        $result = Invoke-Python -Python $python -Arguments $arguments
        
        $endTime = Get-Date
        $duration = ($endTime - $startTime).TotalSeconds
        
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

function Run-Lint {
    Write-Host "Running lint (ruff)..." -ForegroundColor Cyan
    $arguments = @($python.Prefix) + @("ruff", "check", "src", "tests")
    $result = Invoke-Python -Python $python -Arguments $arguments
    if ($result -eq 0) {
        Write-Host "Lint completed successfully." -ForegroundColor Green
    }
    else {
        Write-Host "Lint failed with exit code $result." -ForegroundColor Red
    }
    return $result
}

function Run-TypeCheck {
    Write-Host "Running type check (mypy)..." -ForegroundColor Cyan
    $arguments = @($python.Prefix) + @("mypy", "src/llm_client")
    $result = Invoke-Python -Python $python -Arguments $arguments
    if ($result -eq 0) {
        Write-Host "Type check completed successfully." -ForegroundColor Green
    }
    else {
        Write-Host "Type check failed with exit code $result." -ForegroundColor Red
    }
    return $result
}

function Run-UnitTests {
    Write-Host "Running unit tests..." -ForegroundColor Cyan
    $arguments = @($python.Prefix) + @("pytest", "tests/unit", "-v", "--cov=src/llm_client", "--cov-report=term-missing")
    $result = Invoke-Python -Python $python -Arguments $arguments
    if ($result -eq 0) {
        Write-Host "Unit tests completed successfully." -ForegroundColor Green
    }
    else {
        Write-Host "Unit tests failed with exit code $result." -ForegroundColor Red
    }
    return $result
}

function Run-IntegrationTests {
    Write-Host "Running integration tests..." -ForegroundColor Cyan
    $arguments = @($python.Prefix) + @("pytest", "tests/integration", "-v", "-m", "integration", "--timeout=120")
    $result = Invoke-Python -Python $python -Arguments $arguments
    if ($result -eq 0) {
        Write-Host "Integration tests completed successfully." -ForegroundColor Green
    }
    else {
        Write-Host "Integration tests failed with exit code $result." -ForegroundColor Red
    }
    return $result
}

function Run-CheckpointQuick {
    Write-Host "Running checkpoint quick test..." -ForegroundColor Cyan
    return Run-Test -TestName "Checkpoint Quick" -TestCommand "tests/staging_load/test_checkpoint_latency.py::test_checkpoint_latency_quick" -TimeoutSeconds 120
}

function Run-BM25Indexing {
    Write-Host "Running BM25 indexing regression..." -ForegroundColor Cyan
    return Run-Test -TestName "BM25 Indexing" -TestCommand "tests/unit/test_bm25_indexer.py" -TimeoutSeconds 30
}

function Run-RerankerQuick {
    Write-Host "Running reranker quick test..." -ForegroundColor Cyan
    return Run-Test -TestName "Reranker Quick" -TestCommand "tests/unit/test_ab_test_reranker.py::test_reranker_quick" -TimeoutSeconds 180
}

function Run-HybridRAGQuick {
    Write-Host "Running hybrid RAG quick test..." -ForegroundColor Cyan
    return Run-Test -TestName "Hybrid RAG Quick" -TestCommand "tests/unit/test_ab_test_hybrid_rag.py::test_hybrid_rag_quick" -TimeoutSeconds 300
}

function Run-WebSearchQuick {
    Write-Host "Running web search quick test..." -ForegroundColor Cyan
    return Run-Test -TestName "Web Search Quick" -TestCommand "tests/unit/test_web_search.py::test_web_search_mock" -TimeoutSeconds 60
}

function Run-RAGQueryQuick {
    Write-Host "Running RAG query quick test..." -ForegroundColor Cyan
    return Run-Test -TestName "RAG Query Quick" -TestCommand "tests/unit/test_rag_pipeline.py::test_rag_pipeline_mock" -TimeoutSeconds 120
}

function Run-UIQuick {
    Write-Host "Running UI quick tests..." -ForegroundColor Cyan
    $arguments = @($python.Prefix) + @(
        "pytest",
        "tests/unit/test_ui_render.py",
        "tests/unit/test_ui_streamlit_client.py",
        "tests/unit/test_ui_sidebar.py",
        "tests/unit/test_ui_session.py",
        "tests/unit/test_ui_client.py",
        "tests/unit/test_ui_chat.py",
        "-v", "-x", "--timeout=60"
    )
    return Invoke-Python -Python $python -Arguments $arguments
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

# Main execution
Write-Host "Phase 2 CI - Local Quick Pipeline" -ForegroundColor Magenta
Write-Host "=================================" -ForegroundColor Magenta

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

# Run tests based on target
$totalExitCode = 0

foreach ($target in $Target) {
    switch ($target) {
        "lint" {
            $exitCode = Run-Lint
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "typecheck" {
            $exitCode = Run-TypeCheck
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "unit" {
            $exitCode = Run-UnitTests
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "integration" {
            $exitCode = Run-IntegrationTests
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "checkpoint" {
            $exitCode = Run-CheckpointQuick
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "bm25" {
            $exitCode = Run-BM25Indexing
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "reranker" {
            $exitCode = Run-RerankerQuick
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "hybrid-rag" {
            $exitCode = Run-HybridRAGQuick
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "web-search" {
            $exitCode = Run-WebSearchQuick
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "rag-query" {
            $exitCode = Run-RAGQueryQuick
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "ui" {
            $exitCode = Run-UIQuick
            $totalExitCode = $totalExitCode -bor $exitCode
        }
        "all" {
            $exitCode = Run-Lint
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-TypeCheck
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-UnitTests
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-IntegrationTests
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-CheckpointQuick
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-BM25Indexing
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-RerankerQuick
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-HybridRAGQuick
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-WebSearchQuick
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-RAGQueryQuick
            $totalExitCode = $totalExitCode -bor $exitCode
            
            $exitCode = Run-UIQuick
            $totalExitCode = $totalExitCode -bor $exitCode
        }
    }
}

# Cleanup
Stop-Infrastructure -DockerPath $docker

# Summary
Write-Host ""
Write-Host "Phase 2 CI - Local Quick Pipeline Summary" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "Overall Exit Code: $totalExitCode" -ForegroundColor $(if ($totalExitCode -eq 0) { "Green" } else { "Red" })

if ($totalExitCode -eq 0) {
    Write-Host "✅ All tests passed!" -ForegroundColor Green
}
else {
    Write-Host "❌ Some tests failed. Check test-results/ directory for details." -ForegroundColor Red
}

exit $totalExitCode