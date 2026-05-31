#!/usr/bin/env bash
# Deploy Prosecuto on GX10: vLLM + API + Redis (Docker) + Next.js (host).
# Usage: bash deploy/gx10/deploy-all.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEPLOY_DIR="$ROOT/deploy/gx10"
LOG_DIR="$ROOT/logs"
GX10_IP="${PROSECUTO_GX10_IP:-100.113.13.93}"
FRONTEND_PORT="${PROSECUTO_FRONTEND_PORT:-3000}"

mkdir -p "$LOG_DIR" "$ROOT/backend/data/chroma" "$ROOT/backend/data/corpus" "$ROOT/backend/data/uploads"

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
export COMPOSE_PARALLEL_LIMIT=4
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=8192}"
export NEXT_TELEMETRY_DISABLED=1

echo "=== Prosecuto GX10 deploy ==="
echo "Host: $(hostname) | Tailscale: $GX10_IP"
echo "CPU: $(nproc) cores | RAM: $(free -h | awk '/^Mem:/ {print $2}')"

# --- Ensure Ollama is stopped (competes with vLLM for unified memory) -------
if systemctl is-active --quiet ollama 2>/dev/null; then
  echo "Stopping Ollama (conflicts with vLLM for unified memory)..."
  systemctl stop ollama
fi

# --- Stop old frontend processes --------------------------------------------
echo "Stopping old frontend on :${FRONTEND_PORT}..."
pkill -f "next dev -H 0.0.0.0" 2>/dev/null || true
pkill -f "next start -H 0.0.0.0" 2>/dev/null || true
if [[ -f "$LOG_DIR/frontend.pid" ]]; then
  kill "$(cat "$LOG_DIR/frontend.pid")" 2>/dev/null || true
  rm -f "$LOG_DIR/frontend.pid"
fi
fuser -k "${FRONTEND_PORT}/tcp" 2>/dev/null || true

# --- Bootstrap .env if missing ----------------------------------------------
if [[ ! -f "$ROOT/backend/.env" ]]; then
  cp "$ROOT/backend/.env.example" "$ROOT/backend/.env" 2>/dev/null || cat > "$ROOT/backend/.env" <<'ENVEOF'
TAVILY_API_KEY=
LOCAL_LLM_ENDPOINT=http://localhost:8001/v1
LOCAL_LLM_MODEL=nvidia/Llama-3_3-Nemotron-Super-49B-v1_5-NVFP4
LOCAL_LLM_API_KEY=password
LOCAL_EMBED_MODEL=BAAI/bge-large-en-v1.5
LLM_TIMEOUT_SECONDS=120
REDIS_URL=redis://localhost:6379/0
ENVEOF
  echo "Created backend/.env — add TAVILY_API_KEY for web search fallback."
fi

# --- Backend stack (vLLM + API + Redis via Docker) --------------------------
cd "$DEPLOY_DIR"
echo "Building and starting backend stack (vLLM + API + Redis)..."
docker compose build api
docker compose up -d --remove-orphans

echo "Waiting for vLLM to load model (this takes 2-3 min on first boot)..."
for i in $(seq 1 60); do
  if curl -sf -H "Authorization: Bearer password" \
      "http://127.0.0.1:8001/v1/models" >/dev/null 2>&1; then
    echo "vLLM ready after $((i * 5))s"
    break
  fi
  sleep 5
  [[ $i -eq 60 ]] && { echo "ERROR: vLLM health timeout (5 min)"; exit 1; }
done

echo "Waiting for API health..."
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
    echo "API healthy after $((i * 2))s"
    break
  fi
  sleep 2
  [[ $i -eq 30 ]] && { echo "ERROR: API health timeout"; exit 1; }
done

# --- Frontend env -----------------------------------------------------------
cat > "$ROOT/frontend/.env.local" <<EOF
NEXT_PUBLIC_API_BASE=http://${GX10_IP}:8000
NEXT_PUBLIC_WS_BASE=ws://${GX10_IP}:8000
EOF
echo "Wrote frontend/.env.local → $GX10_IP:8000"

# --- Frontend build + start -------------------------------------------------
cd "$ROOT/frontend"
echo "Installing frontend dependencies..."
if [[ -f package-lock.json ]]; then
  npm ci --prefer-offline 2>/dev/null || npm install
else
  npm install
fi
echo "Building frontend..."
npm run build
echo "Starting frontend on 0.0.0.0:${FRONTEND_PORT}..."
nohup npm run start -- -H 0.0.0.0 -p "$FRONTEND_PORT" > "$LOG_DIR/frontend.log" 2>&1 &
echo $! > "$LOG_DIR/frontend.pid"

for i in $(seq 1 20); do
  if curl -sf -o /dev/null "http://127.0.0.1:${FRONTEND_PORT}/"; then
    echo "Frontend ready after $((i * 2))s"
    break
  fi
  sleep 2
  [[ $i -eq 20 ]] && echo "WARNING: frontend not responding — see $LOG_DIR/frontend.log"
done

# --- Health summary ---------------------------------------------------------
echo ""
echo "=== Health ==="
curl -sf "http://127.0.0.1:8000/api/health" | python3 -m json.tool 2>/dev/null || \
  curl -sf "http://127.0.0.1:8000/api/health" | head -c 200 && echo ""
curl -sf -o /dev/null -w "Frontend: HTTP %{http_code}\n" "http://127.0.0.1:${FRONTEND_PORT}/"

echo ""
echo "=== Prosecuto running ==="
echo "  App:     http://${GX10_IP}:${FRONTEND_PORT}"
echo "  Lawyer:  http://${GX10_IP}:${FRONTEND_PORT}/lawyer"
echo "  Judge:   http://${GX10_IP}:${FRONTEND_PORT}/judge"
echo "  API:     http://${GX10_IP}:8000/api/health"
echo ""
echo "  Backend logs:  docker compose -f $DEPLOY_DIR/docker-compose.yml logs -f api"
echo "  vLLM logs:     docker compose -f $DEPLOY_DIR/docker-compose.yml logs -f vllm"
echo "  Frontend logs: tail -f $LOG_DIR/frontend.log"
echo ""
echo "  Restart: bash $ROOT/deploy/gx10/deploy-all.sh"
