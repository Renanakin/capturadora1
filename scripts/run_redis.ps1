# Wrapper Windows para arrancar Redis
$ErrorActionPreference = "Stop"

$redisExe = "C:\Program Files\Redis\redis-server.exe"
if (-not (Test-Path $redisExe)) {
    Write-Host "redis-server no encontrado en $redisExe" -ForegroundColor Red
    exit 1
}

Write-Host "Iniciando Redis en :6379..." -ForegroundColor Green
& $redisExe --port 6379