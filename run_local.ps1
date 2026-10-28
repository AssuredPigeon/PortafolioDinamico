# Script de inicio rápido para Windows PowerShell — Portafolio Dinámico Auto-actualizable
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "=== Portafolio Dinámico Auto-actualizable ===" -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[INFO] Se creó .env a partir de .env.example (usando BD SQL local por defecto)." -ForegroundColor Yellow
}

if (-not (Test-Path "backend\ml\artifacts\readme_model.pt")) {
    Write-Host "[1/2] Entrenando red neuronal PyTorch (PortfolioReadmeNet)..." -ForegroundColor Cyan
    py -3.11 -m backend.ml.train
}

if (-not (Test-Path "data\backup_portfolio.json")) {
    Write-Host "[INFO] Ejecutando sincronización inicial con GitHub..." -ForegroundColor Cyan
    py -3.11 -m backend.sync_service
}

# Liberar instancias previas huérfanas de uvicorn en el puerto 8000 (evita sockets colgados en Windows)
$oldListeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
if ($oldListeners) {
    foreach ($procId in $oldListeners) {
        Write-Host "[INFO] Liberando instancia previa en puerto 8000 (PID $procId)..." -ForegroundColor Yellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 400
}

Write-Host "[OK] Iniciando servidor FastAPI en http://localhost:8000 (Ctrl+C para detener)..." -ForegroundColor Green
py -3.11 -m uvicorn backend.main:app --reload --reload-dir backend --port 8000

