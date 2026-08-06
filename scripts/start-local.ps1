[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.env'
$runtimeFile = Join-Path $projectRoot '.testhub-processes.json'
$logDir = Join-Path $projectRoot 'logs'

if (-not (Test-Path $envFile)) {
    throw "Missing local configuration: $envFile"
}

$localEnv = @{}
foreach ($line in Get-Content $envFile) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#')) {
        continue
    }

    $parts = $trimmed.Split('=', 2)
    if ($parts.Count -eq 2) {
        $localEnv[$parts[0].Trim()] = $parts[1].Trim()
    }
}

$backendPortValue = $localEnv['BACKEND_PORT']
$frontendPortValue = $localEnv['FRONTEND_PORT']
if (-not $backendPortValue) {
    $backendPortValue = '8000'
}
if (-not $frontendPortValue) {
    $frontendPortValue = '3000'
}
$backendPort = [int]$backendPortValue
$frontendPort = [int]$frontendPortValue

if (Test-Path $runtimeFile) {
    $existing = Get-Content -Raw $runtimeFile | ConvertFrom-Json
    $backendRunning = Get-Process -Id $existing.backendPid -ErrorAction SilentlyContinue
    $frontendRunning = Get-Process -Id $existing.frontendPid -ErrorAction SilentlyContinue
    if ($backendRunning -and $frontendRunning) {
        Write-Host "TestHub is already running."
        Write-Host "Frontend: http://127.0.0.1:$frontendPort"
        Write-Host "API docs: http://127.0.0.1:$backendPort/api/docs/"
        exit 0
    }

    Remove-Item -LiteralPath $runtimeFile -Force
}

foreach ($port in @($backendPort, $frontendPort)) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($listener) {
        throw "Port $port is already in use by PID $($listener[0].OwningProcess)."
    }
}

$python = Join-Path $projectRoot '.venv\python.exe'
$node = (Get-Command node.exe -ErrorAction Stop).Source
$vite = Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'

if (-not (Test-Path $python)) {
    throw "Missing Python environment: $python"
}
if (-not (Test-Path $vite)) {
    throw "Missing frontend dependencies: $vite"
}

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

# Some sandboxed shells expose both Path and PATH, which breaks Start-Process.
$processEnv = [Environment]::GetEnvironmentVariables()
$pathKeys = @($processEnv.Keys | Where-Object { $_ -ieq 'PATH' })
if ($pathKeys.Count -gt 1) {
    $pathValue = [string]$processEnv[$pathKeys[0]]
    [Environment]::SetEnvironmentVariable('PATH', $null, 'Process')
    [Environment]::SetEnvironmentVariable('Path', $pathValue, 'Process')
}

$env:PYTHONUTF8 = '1'
$backend = $null
$frontend = $null

try {
    $backend = Start-Process `
        -FilePath $python `
        -ArgumentList '-m', 'daphne', '-b', '0.0.0.0', '-p', $backendPort, 'backend.asgi:application' `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput (Join-Path $logDir 'backend.stdout.log') `
        -RedirectStandardError (Join-Path $logDir 'backend.stderr.log') `
        -WindowStyle Hidden `
        -PassThru

    $frontend = Start-Process `
        -FilePath $node `
        -ArgumentList $vite, '--host', '0.0.0.0' `
        -WorkingDirectory (Join-Path $projectRoot 'frontend') `
        -RedirectStandardOutput (Join-Path $logDir 'frontend.stdout.log') `
        -RedirectStandardError (Join-Path $logDir 'frontend.stderr.log') `
        -WindowStyle Hidden `
        -PassThru

    @{
        backendPid = $backend.Id
        frontendPid = $frontend.Id
        backendPort = $backendPort
        frontendPort = $frontendPort
        startedAt = (Get-Date).ToString('o')
    } | ConvertTo-Json | Set-Content -Encoding UTF8 $runtimeFile
}
catch {
    if ($backend) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontend) {
        Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
    }
    throw
}

Write-Host "TestHub started."
Write-Host "Frontend: http://127.0.0.1:$frontendPort"
Write-Host "API docs: http://127.0.0.1:$backendPort/api/docs/"
Write-Host "Backend PID: $($backend.Id)"
Write-Host "Frontend PID: $($frontend.Id)"
