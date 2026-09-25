[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $RepoRoot ".env"
$ComposeFile = Join-Path $RepoRoot "docker-compose.yml"
$AppFile = Join-Path $RepoRoot "src\llm_client\ui\app.py"
$PidFile = Join-Path $PSScriptRoot ".runtime\streamlit.pid"

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

function Test-OwnedUiProcess {
    param([pscustomobject]$Process)

    if (-not $Process -or [string]::IsNullOrWhiteSpace($Process.CommandLine)) {
        return $false
    }

    $normalizedAppFile = $AppFile.Replace("/", "\")
    $appPattern = '(?i)(?:^|\s)"?' + [regex]::Escape($normalizedAppFile) + '"?(?:\s|$)'
    $streamlitPattern = "(?i)(?:^|\s)streamlit(?:\s|$)"
    return $Process.CommandLine -match $appPattern -and $Process.CommandLine -match $streamlitPattern
}

function Get-OwnedUiProcesses {
    $processes = @()

    if (Test-Path -LiteralPath $PidFile) {
        try {
            $storedPid = [int](Get-Content -LiteralPath $PidFile -Raw).Trim()
            $storedProcess = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $storedPid" -ErrorAction SilentlyContinue
            if (Test-OwnedUiProcess -Process $storedProcess) {
                $processes += $storedProcess
            }
        }
        catch {
            $processes = @()
        }
    }

    $existingProcessIds = @($processes | ForEach-Object { $_.ProcessId })
    $discoveredProcesses = Get-CimInstance -ClassName Win32_Process |
        Where-Object {
            $_.ProcessId -notin $existingProcessIds -and
            (Test-OwnedUiProcess -Process $_)
        }

    return @($processes) + @($discoveredProcesses)
}

function Stop-Streamlit {
    $processes = @(Get-OwnedUiProcesses)

    if ($processes.Count -eq 0) {
        Write-Host "Streamlit is already stopped." -ForegroundColor Yellow
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    foreach ($process in $processes) {
        $processId = [int]$process.ProcessId
        Write-Host "Stopping Streamlit process $processId..." -ForegroundColor Cyan
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue

        $deadline = [DateTime]::UtcNow.AddSeconds(10)
        while ([DateTime]::UtcNow -lt $deadline) {
            $runningProcess = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if (-not $runningProcess) {
                break
            }

            Start-Sleep -Milliseconds 200
        }

        if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
            throw "Streamlit process $processId did not stop within 10 seconds."
        }
    }

    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Streamlit stopped." -ForegroundColor Green
}

function Resolve-DockerExecutable {
    $command = Get-Command "docker.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"),
        (Join-Path $env:LOCALAPPDATA "Docker\resources\bin\docker.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    return $null
}

function Test-DockerEngine {
    param([string]$DockerPath)

    $arguments = @("info", "--format", "{{.ServerVersion}}")
    return (Invoke-NativeQuiet -FilePath $DockerPath -Arguments $arguments) -eq 0
}

function Stop-Infrastructure {
    $docker = Resolve-DockerExecutable
    if (-not $docker) {
        Write-Host "Docker Desktop is not installed; infrastructure stop skipped." -ForegroundColor Yellow
        return
    }

    if (-not (Test-DockerEngine -DockerPath $docker)) {
        Write-Host "Docker engine is not running; infrastructure is already stopped." -ForegroundColor Yellow
        return
    }

    if (-not (Test-Path -LiteralPath $EnvFile)) {
        throw ".env not found; infrastructure cannot be stopped safely."
    }

    Write-Host "Stopping infrastructure..." -ForegroundColor Cyan
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $docker compose --project-directory $RepoRoot --env-file $EnvFile -f $ComposeFile down --remove-orphans
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        throw "docker compose down failed with exit code $exitCode."
    }

    Write-Host "Infrastructure stopped. Persistent volumes were preserved." -ForegroundColor Green
}

Stop-Streamlit
Stop-Infrastructure
Write-Host "OriaAI stopped." -ForegroundColor Green
