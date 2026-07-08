# Helper para CAPTURADORM3: setea PATH y TESSDATA_PREFIX al inicio
# Uso: . .\scripts\env_helper.ps1

$machinePath = [System.Environment]::GetEnvironmentVariable('Path','Machine')
$userPath    = [System.Environment]::GetEnvironmentVariable('Path','User')

# Rutas adicionales que necesitamos y que viven en WinGet/Poppler/Tesseract
$extra = @(
    'C:\Program Files\Tesseract-OCR'
    'C:\Users\Tranquilidad\AppData\Local\Microsoft\WinGet\Packages\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe\poppler-25.07.0\Library\bin'
)

$merged = "$machinePath;$userPath"
foreach ($p in $extra) {
    if ($merged -notlike "*$p*") { $merged += ";$p" }
}
$env:Path = $merged
$env:TESSDATA_PREFIX = 'C:\Users\Tranquilidad\.tessdata\'

Write-Host "[env_helper] PATH y TESSDATA_PREFIX seteados." -ForegroundColor Green