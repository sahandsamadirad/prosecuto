#!/usr/bin/env bash
# Deploy Prosecuto backend (Docker) + frontend (Next.js) on Asus GX10.
# Usage: bash deploy/gx10/deploy-all.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEPLOY_DIR="$ROOT/deploy/gx10"
LOG_DIR="$ROOT/logs"
GX10_IP="${PROSECUTO_GX10_IP:-100.113.13.93}"
FRONTEND_PORT="${PROSECUTO_FRONTEND_PORT:-3000}"

mkdir -p "$LOG_DIR" "$ROOT/backend/data/chroma" "$ROOT/backend/data/corpus" "$ROOT/backend/data/uploads"

# GX10 hardware tuning (20 cores, 121 GB RAM)
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
export COMPOSE_PARALLEL_LIMIT=4
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=8192}"
export NEXT_TELEMETRY_DISABLED=1
export UV_THREADPOOL_SIZE=20

echo "=== Prosecuto GX10 full deploy ==="
echo "Host: $(hostname) | Tailscale: $GX10_IP"
echo "CPU: $(nproc) cores | RAM: $(free -h | awk '/^Mem:/ {print $2}')"
echo "Repo: $ROOT"

# --- Stop conflicting frontend processes (leave Docker backend alone) ---
echo "Stopping old frontend on :${FRONTEND_PORT}..."
pkill -f "next dev -H 0.0.0.0" 2>/dev/null || true
pkill -f "next start -H 0.0.0.0" 2>/dev/null || true
if [[ -f "$LOG_DIR/frontend.pid" ]]; then
  kill "$(cat "$LOG_DIR/frontend.pid")" 2>/dev/null || true
  rm -f "$LOG_DIR/frontend.pid"
fi
fuser -k "${FRONTEND_PORT}/tcp" 2>/dev/null || true

# --- Backend .env ---
if [[ ! -f "$ROOT/backend/.env" ]]; then
  cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
  echo "Created backend/.env — set NVIDIA_API_KEY before production use."
fi

# --- Backend (Docker) ---
cd "$DEPLOY_DIR"
echo "Starting backend stack (Docker)..."
docker compose pull redis 2>/dev/null || true
docker compose build api
docker compose up -d --remove-orphans

echo "Waiting for backend health..."
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
    echo "Backend healthy after ${i}s"
    break
  fi
  sleep 2
  [[ $i -eq 30 ]] && { echo "ERROR: backend health timeout"; exit 1; }
done

# --- Frontend env (Tailscale IP so browser on any Tailscale device works) ---
cat > "$ROOT/frontend/.env.local" <<EOF
NEXT_PUBLIC_API_BASE=http://${GX10_IP}:8000
NEXT_PUBLIC_WS_BASE=ws://${GX10_IP}:8000
EOF
echo "Wrote frontend/.env.local → $GX10_IP:8000"

# --- Frontend build + start ---
cd "$ROOT/frontend"
echo "Installing frontend dependencies..."
if [[ -f package-lock.json ]]; then
  npm ci --prefer-offline 2>/dev/null || npm install
else
  npm install
fi

echo "Building frontend (production)..."
npm run build

echo "Starting frontend on 0.0.0.0:${FRONTEND_PORT}..."
nohup npm run start -- -H 0.0.0.0 -p "$FRONTEND_PORT" > "$LOG_DIR/frontend.log" 2>&1 &
echo $! > "$LOG_DIR/frontend.pid"

echo "Waiting for frontend..."
for i in $(seq 1 20); do
  if curl -sf -o /dev/null "http://127.0.0.1:${FRONTEND_PORT}/"; then
    echo "Frontend ready after ${i}s"
    break
  fi
  sleep 2
  [[ $i -eq 20 ]] && { echo "WARNING: frontend not responding — see $LOG_DIR/frontend.log"; }
done

# --- Verify ---
echo ""
echo "=== Health checks ==="
curl -sf "http://127.0.0.1:8000/api/health" | head -c 120 && echo ""
curl -sf -o /dev/null -w "Local frontend:  HTTP %{http_code}\n" "http://127.0.0.1:${FRONTEND_PORT}/"
curl -sf -o /dev/null -w "Tailscale front: HTTP %{http_code}\n" "http://${GX10_IP}:${FRONTEND_PORT}/" || true

echo ""
echo "=== Prosecuto running on GX10 ==="
echo "  Browser SSH:  https://login.tailscale.com/admin/machines → gx10-4d82 → SSH"
echo "  Terminal SSH: tailscale ssh asus@gx10-4d82"
echo "  Frontend:     http://${GX10_IP}:${FRONTEND_PORT}"
echo "  Lawyer:       http://${GX10_IP}:${FRONTEND_PORT}/lawyer"
echo "  Judge:        http://${GX10_IP}:${FRONTEND_PORT}/judge"
echo "  Backend:      http://${GX10_IP}:8000/api/health"
echo "  Logs:         $LOG_DIR/frontend.log"
echo "                docker compose -f $DEPLOY_DIR/docker-compose.yml logs -f api"
echo ""
echo "Restart: bash $ROOT/deploy/gx10/deploy-all.sh"
