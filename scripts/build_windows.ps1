[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$HookDirectory = Join-Path $ProjectRoot "packaging\hooks"
$EntryPoint = Join-Path $ProjectRoot "scripts\desktop_entry.py"
$BuildDirectory = Join-Path $ProjectRoot "build"
$DistDirectory = Join-Path $ProjectRoot "dist"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "No se encontro .venv\Scripts\python.exe. Crea primero el entorno virtual."
}

& $Python -m pip install --no-build-isolation -e "$ProjectRoot[desktop,build]"
if ($LASTEXITCODE -ne 0) {
    throw "No se pudieron instalar las dependencias de escritorio."
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "GARMIN-QPRO" `
    --additional-hooks-dir $HookDirectory `
    --hidden-import "garminconnect" `
    --hidden-import "keyring" `
    --hidden-import "keyring.backends.Windows" `
    --specpath $BuildDirectory `
    --workpath $BuildDirectory `
    --distpath $DistDirectory `
    --paths (Join-Path $ProjectRoot "src") `
    $EntryPoint

if ($LASTEXITCODE -ne 0) {
    throw "No se pudo generar GARMIN-QPRO.exe."
}

Write-Host ""
Write-Host "Aplicacion creada en:"
Write-Host (Join-Path $ProjectRoot "dist\GARMIN-QPRO.exe")
