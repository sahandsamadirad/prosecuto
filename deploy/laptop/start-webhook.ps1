# Deploy webhook on laptop (Windows PowerShell)
param(
    [string]$RepoPath = "D:\Github\prosecuto",
    [int]$Port = 9876
)

$ErrorActionPreference = "Stop"

if (-not $env:DEPLOY_WEBHOOK_SECRET) {
    Write-Host "Set DEPLOY_WEBHOOK_SECRET first:" -ForegroundColor Yellow
    Write-Host '  [System.Environment]::SetEnvironmentVariable("DEPLOY_WEBHOOK_SECRET", "your-secret", "User")'
    exit 1
}

Set-Location $RepoPath
Write-Host "Starting deploy webhook on port $Port ..."
python deploy/webhook/server.py --port $Port
