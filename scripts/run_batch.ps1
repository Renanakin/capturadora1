# Wrapper Windows para correr el pipeline en batch

$ErrorActionPreference = "Stop"

# Cargar helper de entorno (PATH, TESSDATA_PREFIX)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "env_helper.ps1")

# Activar venv si existe
$venvActivate = Join-Path $PSScriptRoot "..\.venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

# Argumentos: --input / --output opcionales
$inputArg = ""
$outputArg = ""
for ($i = 1; $i -lt $args.Count; $i++) {
    switch ($args[$i]) {
        "--input"  { $i++; $inputArg  = "--input `"$($args[$i])`"" }
        "--output" { $i++; $outputArg = "--output `"$($args[$i])`"" }
    }
}

Push-Location (Join-Path $PSScriptRoot "..")
try {
    Invoke-Expression "python -m ocr_tributario $inputArg $outputArg"
} finally {
    Pop-Location
}