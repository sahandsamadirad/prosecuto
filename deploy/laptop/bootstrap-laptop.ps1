# Self-contained Prosecuto laptop deploy — download and run, no git push needed.
# Run from PowerShell:
#   iwr http://100.113.13.93:8888/bootstrap-laptop.ps1 -UseBasicParsing | iex
param(
    [string]$RepoPath = "D:\Github\prosecuto",
    [string]$Gx10Ip = "100.113.13.93",
    [int]$Port = 3000
)
$ErrorActionPreference = "Stop"
$BackendUrl = "http://${Gx10Ip}:8000"

Write-Host "=== Prosecuto laptop bootstrap ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoPath"
Write-Host "Backend: $BackendUrl"

if (-not (Test-Path "$RepoPath\frontend\package.json")) {
    Write-Error "Frontend not found at $RepoPath\frontend — clone repo first: git clone https://github.com/sahandsamadirad/prosecuto.git $RepoPath"
}

New-Item -ItemType Directory -Force -Path "$RepoPath\deploy\laptop" | Out-Null

Set-Location "$RepoPath\frontend"

@"
NEXT_PUBLIC_API_BASE=$BackendUrl
NEXT_PUBLIC_WS_BASE=ws://${Gx10Ip}:8000
"@ | Set-Content -Path ".env.local" -Encoding utf8
Write-Host "Wrote frontend/.env.local" -ForegroundColor Green

Write-Host "Stopping old frontend on port $Port ..."
Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

Write-Host "Installing dependencies..."
Set-Location "$RepoPath\frontend"
if (Test-Path package-lock.json) {
    npm ci 2>$null
    if ($LASTEXITCODE -ne 0) { npm install }
} else {
    npm install
}

Write-Host "Building production frontend..."
npm run build
if ($LASTEXITCODE -ne 0) { Write-Error "npm run build failed with exit code $LASTEXITCODE" }

Write-Host "Starting frontend..."
Start-Process -WindowStyle Hidden -FilePath "npm" -ArgumentList "run","start","--","-H","0.0.0.0","-p","$Port" -WorkingDirectory "$RepoPath\frontend"

Start-Sleep -Seconds 4

try {
    $health = Invoke-RestMethod -Uri "$BackendUrl/api/health" -TimeoutSec 10
    Write-Host "Backend health: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host "WARNING: Cannot reach backend at $BackendUrl — check Tailscale." -ForegroundColor Yellow
}

try {
    $r = Invoke-WebRequest -Uri "http://localhost:${Port}/" -UseBasicParsing -TimeoutSec 10
    Write-Host "Frontend HTTP: $($r.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "WARNING: Frontend not responding on port $Port yet." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:${Port}"
Write-Host "  Lawyer:   http://localhost:${Port}/lawyer"
Write-Host "  Backend:  $BackendUrl/api/health"
