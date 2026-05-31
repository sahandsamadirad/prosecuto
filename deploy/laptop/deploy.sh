#!/usr/bin/env bash
# Deploy Prosecuto frontend on Linux/macOS laptop (alternative to deploy.ps1).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GX10_IP="${PROSECUTO_GX10_IP:-100.113.13.93}"
PORT="${PROSECUTO_FRONTEND_PORT:-3000}"
REPO_PATH="${PROSECUTO_REPO_PATH:-$ROOT}"

echo "=== Prosecuto laptop frontend deploy ==="
echo "Backend (GX10): http://${GX10_IP}:8000"

if [[ -d "$REPO_PATH/.git" ]]; then
  git -C "$REPO_PATH" fetch origin main
  git -C "$REPO_PATH" reset --hard origin/main
fi

cd "$REPO_PATH/frontend"
cat > .env.local <<EOF
BACKEND_URL=http://${GX10_IP}:8000
NEXT_PUBLIC_API_BASE=/api/backend
NEXT_PUBLIC_WS_URL=ws://${GX10_IP}:8000
EOF

npm ci --prefer-offline 2>/dev/null || npm install
npm run build

fuser -k "${PORT}/tcp" 2>/dev/null || true
nohup npm run start -- -H 0.0.0.0 -p "$PORT" > "$REPO_PATH/logs/frontend.log" 2>&1 &
echo $! > "$REPO_PATH/logs/frontend.pid"

echo "Frontend: http://0.0.0.0:${PORT}"
