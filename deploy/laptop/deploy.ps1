# Deploy Prosecuto frontend on local Windows laptop.
# Connects to GX10 backend over Tailscale.
param(
    [string]$RepoPath = "D:\Github\prosecuto",
    [string]$Gx10Ip = "100.113.13.93",
    [int]$Port = 3000
)

$ErrorActionPreference = "Stop"
$BackendUrl = "http://${Gx10Ip}:8000"

Write-Host "=== Prosecuto laptop frontend deploy ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoPath"
Write-Host "Backend (GX10): $BackendUrl"

if (-not (Test-Path $RepoPath)) {
    Write-Host "Cloning repo..."
    git clone https://github.com/sahandsamadirad/prosecuto.git $RepoPath
}

Set-Location $RepoPath

Write-Host "Pulling latest..."
git fetch origin main
git reset --hard origin/main

Set-Location "$RepoPath\frontend"

# Write env pointing at GX10 supercomputer
@"
BACKEND_URL=$BackendUrl
NEXT_PUBLIC_API_BASE=/api/backend
NEXT_PUBLIC_WS_URL=ws://${Gx10Ip}:8000
"@ | Set-Content -Path ".env.local" -Encoding utf8

Write-Host "Installing dependencies..."
npm ci --prefer-offline 2>$null
if ($LASTEXITCODE -ne 0) { npm install }

Write-Host "Building production frontend..."
npm run build

# Stop existing Next.js on this port
Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Write-Host "Starting frontend on http://0.0.0.0:${Port} ..."
$env:PORT = $Port
Start-Process -NoNewWindow -FilePath "npm" -ArgumentList "run", "start", "--", "-H", "0.0.0.0", "-p", "$Port"

Write-Host ""
Write-Host "=== Frontend deploy complete ===" -ForegroundColor Green
Write-Host "  Local:    http://localhost:${Port}"
Write-Host "  Tailscale: http://$(tailscale ip -4 2>$null):${Port}"
Write-Host "  Backend:  $BackendUrl/api/health"
