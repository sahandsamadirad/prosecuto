#!/usr/bin/env bash
# One-command update on GX10: git pull + redeploy backend.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
echo "Pulling latest..."
git pull origin main
exec bash "$ROOT/deploy/gx10/deploy.sh"
