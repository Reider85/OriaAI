[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8501,
    [int]$TimeoutSeconds = 600,
    [switch]$KeepInfra
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

function Wait-ForInfrastructure {
    param([int]$TimeoutSeconds)

    $checks = @(
        [pscustomobject]@{ Name = "Redis"; Test = { Test-TcpPort -PortNumber 6380 } },
        [pscustomobject]@{ Name = "MinIO"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:9000/minio/health/live" } },
        [pscustomobject]@{ Name = "Vault"; Test = { Test-HttpEndpoint -Uri "http://127.0.0.1:8200/v1/sys/health" } }
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
    
    Write-Host "Starting forensic infrastructure..." -ForegroundColor Cyan
    $env:ENVIRONMENT = "staging"
    $env:FORENSIC_STREAM_ENABLED = "true"
    $env:KMS_PROVIDER = "vault"
    Invoke-Compose -DockerPath $DockerPath -Arguments @("up", "-d")
    Wait-ForInitContainers -DockerPath $DockerPath -TimeoutSeconds $TimeoutSeconds
    Wait-ForInfrastructure -TimeoutSeconds $TimeoutSeconds
    Write-Host "Infrastructure ready." -ForegroundColor Green
}

function Stop-Infrastructure {
    param([string]$DockerPath)
    
    if ($KeepInfra) {
        Write-Host "Keeping infrastructure running (use -KeepInfra to change this behavior)" -ForegroundColor Yellow
        return
    }
    
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

function Run-ForensicTests {
    param([pscustomobject]$Python, [int]$TimeoutSeconds)
    
    # Set forensic environment
    $env:ENVIRONMENT = "staging"
    $env:FORENSIC_STREAM_ENABLED = "true"
    $env:KMS_PROVIDER = "vault"
    $env:VAULT_ADDR = "http://127.0.0.1:8200"
    $env:VAULT_TOKEN = "root"
    $env:VAULT_TRANSIT_KEY = "forensic-aes256-gcm"
    $env:S3_ENDPOINT = "http://127.0.0.1:9000"
    $env:S3_ACCESS_KEY = "minioadmin"
    $env:S3_SECRET_KEY = "minioadmin"
    $env:S3_FORENSIC_BUCKET = "llm-client-forensic"
    $env:REDIS_URL = "redis://localhost:6380/0"
    $env:OPENAI_API_KEY = "sk-test-placeholder"
    
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
    $arguments = @($Python.Prefix) + @("-m", "pytest", "tests/integration/test_forensic_stream_e2e.py", "-v", "--timeout=$TimeoutSeconds")
    $result = Invoke-Python -Python $Python -Arguments $arguments
    if ($result -ne 0) { return $result }
    
    # Run integration tests with forensic enabled
    Write-Host "Running integration tests with forensic enabled..." -ForegroundColor Cyan
    $arguments = @($Python.Prefix) + @("-m", "pytest", "tests/integration", "-m", "integration", "--timeout=$TimeoutSeconds", "--maxfail=1")
    $result = Invoke-Python -Python $Python -Arguments $arguments
    if ($result -ne 0) { return $result }
    
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
Write-Host "Phase 1 CI - Local Forensic Integration Pipeline" -ForegroundColor Magenta
Write-Host "=================================================" -ForegroundColor Magenta

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

# Start infrastructure (trap to ensure cleanup)
trap { Stop-Infrastructure -DockerPath $docker }

Start-Infrastructure -DockerPath $docker -TimeoutSeconds $TimeoutSeconds

# Run forensic tests
$startTime = Get-Date
Write-Host "Running forensic tests..." -ForegroundColor Cyan
$testResult = Run-ForensicTests -Python $python -TimeoutSeconds $TimeoutSeconds
$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds

# Cleanup
Stop-Infrastructure -DockerPath $docker

# Summary
Write-Host ""
Write-Host "Phase 1 CI - Local Forensic Integration Pipeline Summary" -ForegroundColor Magenta
Write-Host "=========================================================" -ForegroundColor Magenta
Write-Host "Overall Exit Code: $testResult" -ForegroundColor $(if ($testResult -eq 0) { "Green" } else { "Red" })
Write-Host "Duration: $duration seconds" -ForegroundColor Cyan

if ($testResult -eq 0) {
    Write-Host "✅ All forensic tests passed!" -ForegroundColor Green
}
else {
    Write-Host "❌ Some forensic tests failed." -ForegroundColor Red
}

exit $testResult