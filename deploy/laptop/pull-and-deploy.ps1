# One-command update on laptop: git pull + redeploy frontend.
param(
    [string]$RepoPath = "D:\Github\prosecuto",
    [string]$Gx10Ip = "100.113.13.93"
)

$ErrorActionPreference = "Stop"
Set-Location $RepoPath
Write-Host "Pulling latest..."
git pull origin main
& "$RepoPath\deploy\laptop\deploy.ps1" -RepoPath $RepoPath -Gx10Ip $Gx10Ip -SkipPull
