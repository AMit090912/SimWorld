param(
  [int]$Port = 8000
)

$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "frontend\dist"
if (-not (Test-Path (Join-Path $dist "index.html"))) {
  Write-Host "Building frontend..."
  Push-Location (Join-Path $root "frontend")
  npm install
  npm run build
  Pop-Location
}
$env:PYTHONPATH = Join-Path $root "backend"
$env:SIMWORLD_DB_PATH = Join-Path $root "data\simworld.db"
$env:SIMWORLD_ENV = "production"
$env:SIMWORLD_STATIC_DIR = $dist
Write-Host "SimWorld on http://127.0.0.1:$Port (API docs at /api/docs)"
python -m uvicorn simworld.api.app:app --host 0.0.0.0 --port $Port