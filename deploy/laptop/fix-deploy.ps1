# Prosecuto laptop fix — run locally, no git push required.
# Usage: powershell -ExecutionPolicy Bypass -File D:\Github\prosecuto\deploy\laptop\fix-deploy.ps1
param(
    [string]$RepoPath = "D:\Github\prosecuto",
    [string]$Gx10Ip = "100.113.13.93",
    [int]$Port = 3000
)
$ErrorActionPreference = "Stop"
$BackendUrl = "http://${Gx10Ip}:8000"

Write-Host "=== Prosecuto frontend fix ===" -ForegroundColor Cyan
Write-Host "Backend: $BackendUrl"

if (-not (Test-Path "$RepoPath\frontend")) {
    Write-Error "Repo not found at $RepoPath\frontend"
}

Set-Location "$RepoPath\frontend"

@"
NEXT_PUBLIC_API_BASE=$BackendUrl
NEXT_PUBLIC_WS_BASE=ws://${Gx10Ip}:8000
"@ | Set-Content -Path ".env.local" -Encoding utf8
Write-Host "Wrote .env.local"

Write-Host "Installing dependencies..."
if (Test-Path package-lock.json) {
    npm ci 2>$null
    if ($LASTEXITCODE -ne 0) { npm install }
} else {
    npm install
}

Write-Host "Building..."
npm run build
if ($LASTEXITCODE -ne 0) { Write-Error "Build failed" }

Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Write-Host "Starting on port $Port ..."
Start-Process -NoNewWindow -FilePath "npm" -ArgumentList "run","start","--","-H","0.0.0.0","-p","$Port"

Start-Sleep -Seconds 3
try {
    $h = Invoke-RestMethod -Uri "$BackendUrl/api/health" -TimeoutSec 10
    Write-Host "Backend health: $($h.status)" -ForegroundColor Green
} catch {
    Write-Host "WARNING: Cannot reach backend at $BackendUrl" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Open http://localhost:${Port}" -ForegroundColor Green
