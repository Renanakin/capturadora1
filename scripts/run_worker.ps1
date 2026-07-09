# Wrapper Windows para arrancar el worker arq
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "env_helper.ps1")

$venvActivate = Join-Path $PSScriptRoot "..\.venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

Push-Location (Join-Path $PSScriptRoot "..")
try {
    Write-Host "Iniciando worker arq..." -ForegroundColor Green
    python -m ocr_tributario worker --max-jobs 2
} finally {
    Pop-Location
}