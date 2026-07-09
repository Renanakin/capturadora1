# Wrapper Windows para arrancar la API FastAPI
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "env_helper.ps1")

$venvActivate = Join-Path $PSScriptRoot "..\.venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

Push-Location (Join-Path $PSScriptRoot "..")
try {
    $port = if ($args.Count -gt 0) { $args[0] } else { "8000" }
    Write-Host "CapturadorM3 API en http://127.0.0.1:$port/docs" -ForegroundColor Green
    python -m ocr_tributario api --host 127.0.0.1 --port $port
} finally {
    Pop-Location
}