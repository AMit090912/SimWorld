param(
  [int]$ApiPort = 8000,
  [int]$WebPort = 5173
)

$root = Split-Path -Parent $PSScriptRoot
Write-Host "Starting SimWorld API on http://127.0.0.1:$ApiPort"
$env:PYTHONPATH = Join-Path $root "backend"
$env:SIMWORLD_DB_PATH = Join-Path $root "data\simworld.db"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; `$env:PYTHONPATH='backend'; python -m uvicorn simworld.api.app:app --reload --port $ApiPort"
Start-Sleep -Seconds 2
Write-Host "Starting Vite on http://localhost:$WebPort"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev -- --port $WebPort"
Write-Host "SimWorld is starting. Open http://localhost:$WebPort"