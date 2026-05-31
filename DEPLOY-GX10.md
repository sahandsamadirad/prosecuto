# Prosecuto - GX10 Supercomputer Deployment Guide

ASUS GX10 / NVIDIA GB10 Grace Blackwell Superchip
20 ARM64 cores | 121 GB unified memory | CUDA 13.0
All AI models run 100% locally -- zero cloud, zero API latency.

---
## Hardware

  CPU:    10x Cortex-X925 + 10x Cortex-A725 (ARM64, 20 cores)
  GPU:    NVIDIA GB10 (Blackwell, compute 12.1)
  Memory: 121 GB unified (CPU+GPU share one pool -- no VRAM cap)
  Disk:   916 GB NVMe (565 GB free)
  OS:     Ubuntu 24.04.4 LTS (aarch64) | CUDA 13.0
  Host:   gx10-4d82 / Tailscale 100.113.13.93

---
## Local AI Models (Ollama)

Unified memory: CPU and GPU share the same 121 GB pool.
No VRAM limit. No PCIe bottleneck. All models load fully into memory.

  nemotron-3-super:latest  86 GB   PRIMARY LLM (Lawyer/Judge/Prosecutor)  [ACTIVE]
  nomic-embed-text:latest 274 MB   RAG embeddings                         [ACTIVE]
  qwen3:30b-a3b            18 GB   Fast MoE alternative (3B active params)
  gemma4:26b               17 GB   Alternative LLM
  nemotron3:33b            27 GB   Alternative LLM
  qwen3.6:35b              23 GB   Alternative LLM
  nemotron-mini:latest    2.7 GB   Lightweight LLM

Switch LLM (no rebuild):
  nano ~/prosecuto/backend/.env
  # change: OLLAMA_LLM_MODEL=qwen3:30b-a3b  (faster, 18 GB MoE)
  docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml restart api

Verify active LLM:
  docker exec prosecuto-api python3 -c \
    "from app.llm import get_chat_llm; l=get_chat_llm(); print(type(l).__name__, l.model)"

Direct Ollama:
  ollama run nemotron-3-super:latest   # interactive chat
  ollama list                          # list all models
  ollama pull <name>                   # download model
  ollama rm <name>                     # remove model (free disk)
  watch -n1 nvidia-smi                 # GPU/memory during inference

---
## Architecture

  Browser (Tailscale) --> :3000  Next.js frontend  (host process)
                              |
                              v :8000  FastAPI backend (Docker: prosecuto-api)
                              |
                              +-- :6379  Redis (Docker: prosecuto-redis)
                              |
                              v :11434  Ollama (systemd, 0.0.0.0)
                                  +-- nemotron-3-super:latest (86 GB in unified mem)
                                  +-- nomic-embed-text:latest (274 MB)

---
## Access URLs (Tailscale required)

  App home   http://100.113.13.93:3000
  Lawyer     http://100.113.13.93:3000/lawyer
  Judge      http://100.113.13.93:3000/judge
  Health     http://100.113.13.93:8000/api/health
  API docs   http://100.113.13.93:8000/docs

---
## SSH into GX10

  ssh asus@gx10-4d82           # Tailscale hostname
  ssh asus@100.113.13.93       # Tailscale IP

---
## Pull and Deploy

  bash ~/prosecuto/deploy/gx10/pull-and-deploy.sh   # one command

  # Manual equivalent
  cd ~/prosecuto
  git fetch origin main && git merge origin/main --no-edit
  bash deploy/gx10/deploy-all.sh

  NOTE: backend/.env and frontend/.env.local are NOT overwritten by git pull.

---
## Restart (no pull)

  bash ~/prosecuto/deploy/gx10/deploy-all.sh    # full stack

  docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml restart api   # backend only

  # Frontend only
  kill $(cat ~/prosecuto/logs/frontend.pid) 2>/dev/null || true
  cd ~/prosecuto/frontend
  nohup npm run start -- -H 0.0.0.0 -p 3000 > ~/prosecuto/logs/frontend.log 2>&1 &
  echo $! > ~/prosecuto/logs/frontend.pid

  sudo systemctl restart ollama

---
## Stop Everything

  docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml down
  kill $(cat ~/prosecuto/logs/frontend.pid) 2>/dev/null

---
## Logs

  docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml logs -f api      # backend follow
  docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml logs --tail 100 api
  tail -f ~/prosecuto/logs/frontend.log    # frontend
  journalctl -u ollama -f                   # Ollama
  watch -n1 nvidia-smi                      # GPU/memory usage

---
## Health Checks

  curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
  curl -sf -o /dev/null -w 'Frontend: HTTP %{http_code}\n' http://127.0.0.1:3000/
  curl -s http://localhost:11434/api/tags | python3 -m json.tool
  docker ps --filter name=prosecuto
  ss -tlnp | grep -E ':3000|:8000|:11434'

---
## Rebuild Backend (code changed)

  cd ~/prosecuto/deploy/gx10
  docker compose build api              # fast (layer cache)
  docker compose build --no-cache api   # full rebuild
  docker compose up -d --remove-orphans

---
## Rebuild Frontend (code changed)

  cd ~/prosecuto/frontend
  NEXT_TELEMETRY_DISABLED=1 npm run build
  kill $(cat ~/prosecuto/logs/frontend.pid) 2>/dev/null || true
  nohup npm run start -- -H 0.0.0.0 -p 3000 > ~/prosecuto/logs/frontend.log 2>&1 &
  echo $! > ~/prosecuto/logs/frontend.pid

---
## .env Config  (~/prosecuto/backend/.env -- not tracked by git)

  OLLAMA_BASE_URL=http://host.docker.internal:11434
  OLLAMA_LLM_MODEL=nemotron-3-super:latest   # 86 GB -- highest quality
  # OLLAMA_LLM_MODEL=qwen3:30b-a3b           # 18 GB MoE -- faster
  OLLAMA_EMBED_MODEL=nomic-embed-text        # 274 MB embeddings

  # Cloud fallback (only used if OLLAMA_BASE_URL is empty)
  NVIDIA_API_KEY=nvapi-...
  TAVILY_API_KEY=      # optional web search fallback
  ADMIN_TOKEN=         # optional API protection

---
## Performance Tuning

Ollama systemd override (/etc/systemd/system/ollama.service.d/override.conf):
  OLLAMA_HOST=0.0.0.0           # all interfaces (Docker needs this)
  OLLAMA_NUM_PARALLEL=4         # 4 concurrent inference requests
  OLLAMA_MAX_LOADED_MODELS=2    # keep 2 models hot in 121 GB pool

Pre-warm model after boot (eliminates cold-start latency):
  ollama run nemotron-3-super:latest hello && echo warm

Cron auto-warmup on reboot:
  crontab -e
  @reboot sleep 30 && ollama run nemotron-3-super:latest hello

Backend already tuned:
  - Uvicorn: uvloop + httptools (fastest async IO on ARM64)
  - API container: 16 CPU cores, 32 GB RAM limit
  - Redis: 5 GB cap, LRU eviction

---
## Troubleshooting

  Port 3000 in use       : fuser -k 3000/tcp
  Backend unhealthy      : docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml logs api
  Ollama Docker error    : sudo systemctl restart ollama
                           ss -tlnp | grep 11434  (must show *:11434)
  Slow first LLM call    : ollama run nemotron-3-super:latest hello  (pre-warm 86 GB)
  Want faster responses  : OLLAMA_LLM_MODEL=qwen3:30b-a3b in .env, restart api
  Out of disk            : ollama list, remove unused models
  Frontend build fails   : npm install && npm run build
  Laptop cannot connect  : tailscale status on both machines
  Force fresh Docker     : docker compose build --no-cache api

---
## Cheat Sheet

  DEPLOY       bash ~/prosecuto/deploy/gx10/pull-and-deploy.sh
  BACK LOGS    docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml logs -f api
  FRONT LOGS   tail -f ~/prosecuto/logs/frontend.log
  OLLAMA LOGS  journalctl -u ollama -f
  HEALTH       curl http://127.0.0.1:8000/api/health | python3 -m json.tool
  GPU STATS    nvidia-smi
  RESTART ALL  bash ~/prosecuto/deploy/gx10/deploy-all.sh

---
## Git Workflow

  cd ~/prosecuto
  git fetch origin main && git merge origin/main --no-edit
  git log --oneline -10

  Files git pull NEVER overwrites:
    backend/.env         secrets and model config
    frontend/.env.local  Tailscale IP/port config
    logs/                runtime log files

---
Generated: 2026-05-31 | ASUS GX10 | NVIDIA GB10 Grace Blackwell Superchip
