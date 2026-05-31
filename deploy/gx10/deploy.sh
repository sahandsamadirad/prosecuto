#!/usr/bin/env bash
# Deploy Prosecuto backend + AI stack on Asus GX10 supercomputer.
# Triggered by GitHub Actions self-hosted runner or manual invocation.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEPLOY_DIR="$ROOT/deploy/gx10"
LOG_DIR="$ROOT/logs"
GX10_IP="${PROSECUTO_GX10_IP:-100.113.13.93}"
LAPTOP_IP="${PROSECUTO_LAPTOP_IP:-100.125.125.54}"
LAPTOP_WEBHOOK="${PROSECUTO_LAPTOP_WEBHOOK:-http://${LAPTOP_IP}:9876/deploy}"

mkdir -p "$LOG_DIR" "$ROOT/backend/data/chroma" "$ROOT/backend/data/corpus" "$ROOT/backend/data/uploads"

echo "=== Prosecuto GX10 deploy ==="
echo "Host: $(hostname) | IP: $GX10_IP"
echo "Repo: $ROOT"

# Sync latest if this is a git checkout (preserve local deploy commits)
if [[ -d "$ROOT/.git" ]]; then
  echo "Syncing with origin/main..."
  git -C "$ROOT" fetch origin main
  git -C "$ROOT" merge --ff-only origin/main 2>/dev/null || {
    echo "Local commits present — skipping fast-forward (deploying current tree)."
  }
fi

# Ensure backend .env exists
if [[ ! -f "$ROOT/backend/.env" ]]; then
  if [[ -f "$ROOT/backend/.env.example" ]]; then
    cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
    echo "Created backend/.env from example — set NVIDIA_API_KEY before production use."
  else
    echo "ERROR: backend/.env missing"; exit 1
  fi
fi

# Docker build + restart (uses BuildKit cache for speed)
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

cd "$DEPLOY_DIR"
echo "Building and starting backend stack..."
docker compose pull redis 2>/dev/null || true
docker compose build --parallel api
docker compose up -d --remove-orphans

# Wait for health
echo "Waiting for API health..."
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
    echo "Backend healthy after ${i}s"
    curl -s "http://127.0.0.1:8000/api/health" | head -c 200
    echo ""
    break
  fi
  sleep 2
  if [[ $i -eq 30 ]]; then
    echo "WARNING: health check timed out — check: docker compose -f $DEPLOY_DIR/docker-compose.yml logs api"
  fi
done

# Trigger laptop frontend deploy via Tailscale webhook (if configured)
if [[ -n "${DEPLOY_WEBHOOK_SECRET:-}" ]]; then
  echo "Triggering laptop frontend deploy at $LAPTOP_WEBHOOK ..."
  curl -sf -X POST "$LAPTOP_WEBHOOK" \
    -H "Authorization: Bearer $DEPLOY_WEBHOOK_SECRET" \
    -H "Content-Type: application/json" \
    -d "{\"ref\":\"main\",\"gx10\":\"$GX10_IP\"}" \
    && echo "Laptop deploy triggered." \
    || echo "WARNING: laptop webhook unreachable — deploy frontend manually on laptop."
fi

echo ""
echo "=== GX10 deploy complete ==="
echo "  Backend:  http://${GX10_IP}:8000/api/health"
echo "  Redis:    ${GX10_IP}:6379"
echo "  Logs:     docker compose -f $DEPLOY_DIR/docker-compose.yml logs -f api"
