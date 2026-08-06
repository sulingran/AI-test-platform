[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeFile = Join-Path $projectRoot '.testhub-processes.json'

if (-not (Test-Path $runtimeFile)) {
    Write-Host 'TestHub is not running or its PID file is missing.'
    exit 0
}

$runtime = Get-Content -Raw $runtimeFile | ConvertFrom-Json
foreach ($processId in @($runtime.backendPid, $runtime.frontendPid)) {
    if ($processId) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

Remove-Item -LiteralPath $runtimeFile -Force
Write-Host 'TestHub stopped.'
