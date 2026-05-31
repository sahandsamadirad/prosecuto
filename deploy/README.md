# Prosecuto deployment — Asus GX10 + Laptop split architecture

## Architecture

```
GitHub push (main)
       │
       ▼
┌──────────────────────────────────────────────────┐
│  GitHub Actions                                   │
│  ├─ deploy-backend-gx10  → self-hosted gx10      │
│  └─ deploy-frontend      → laptop runner/webhook │
└──────────────────────────────────────────────────┘
       │                              │
       ▼                              ▼
┌─────────────────┐          ┌─────────────────┐
│  GX10 (super)   │◄─Tailscale─►│  Laptop (Win)   │
│  100.113.13.93  │          │  100.125.125.54 │
│                 │          │                 │
│  • FastAPI :8000│          │  • Next.js :3000│
│  • Redis :6379  │          │  • 3D avatar UI │
│  • Chroma (vol) │          │                 │
│  • NVIDIA NIM   │          │                 │
└─────────────────┘          └─────────────────┘
```

## Machine specs (GX10)

| Resource | Value |
|----------|-------|
| CPU | 20 cores (10× Cortex-X925 + 10× Cortex-A725, ARM64) |
| RAM | 121 GB |
| GPU | NVIDIA GB10 (CUDA 13.0) |
| Hostname | `gx10-4d82` |
| Tailscale | `100.113.13.93` |

## One-time setup

### 1. GX10 — backend secrets

```bash
cd /home/asus/prosecuto
cp backend/.env.example backend/.env
# Edit backend/.env — set NVIDIA_API_KEY (required), TAVILY_API_KEY (optional)
```

### 2. GX10 — GitHub self-hosted runner

```bash
chmod +x deploy/install-gx10-runner.sh deploy/gx10/deploy.sh
./deploy/install-gx10-runner.sh
# Follow printed instructions to register the runner with label `gx10`
```

Add GitHub repo secrets at https://github.com/sahandsamadirad/prosecuto/settings/secrets/actions:
- `DEPLOY_WEBHOOK_SECRET` — shared secret for laptop webhook (optional)

Add repo variables (optional):
- `PROSECUTO_GX10_IP` = `100.113.13.93`
- `PROSECUTO_LAPTOP_IP` = `100.125.125.54`

### 3. Laptop — frontend (choose one)

**Option A — Self-hosted GitHub runner (recommended)**

1. Install [GitHub Actions runner for Windows](https://github.com/sahandsamadirad/prosecuto/settings/actions/runners/new)
2. Label it `laptop`
3. Push to `main` — frontend deploys automatically after backend

**Option B — Webhook listener**

```powershell
cd D:\Github\prosecuto
git pull
$env:DEPLOY_WEBHOOK_SECRET = "your-secret"
powershell -ExecutionPolicy Bypass -File deploy/laptop/start-webhook.ps1
```

GX10 deploy will POST to `http://100.125.125.54:9876/deploy` after backend is up.

**Option C — Manual deploy**

```powershell
powershell -ExecutionPolicy Bypass -File D:\Github\prosecuto\deploy\laptop\deploy.ps1
```

## Manual deploy (without GitHub Actions)

```bash
# GX10
bash /home/asus/prosecuto/deploy/gx10/deploy.sh

# Laptop
powershell -File D:\Github\prosecuto\deploy\laptop\deploy.ps1
```

## Verify

```bash
# GX10 backend
curl http://100.113.13.93:8000/api/health

# Laptop frontend
curl http://100.125.125.54:3000/
```

## Operations

```bash
# Logs
docker compose -f deploy/gx10/docker-compose.yml logs -f api

# Restart
docker compose -f deploy/gx10/docker-compose.yml restart api

# Stop
docker compose -f deploy/gx10/docker-compose.yml down
```

## Skip frontend on push

Commit message containing `[skip-frontend]` skips the laptop webhook trigger.
