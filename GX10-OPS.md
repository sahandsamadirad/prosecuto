# Prosecuto — GX10 Quick Ops

> Save this file. Copy-paste commands when you need to deploy, restart, or check logs.

---

## Links (open in browser — Tailscale required)

| What | URL |
|------|-----|
| **App home** | http://100.113.13.93:3000 |
| **Lawyer** | http://100.113.13.93:3000/lawyer |
| **Judge** | http://100.113.13.93:3000/judge |
| **Backend health** | http://100.113.13.93:8000/api/health |
| **Tailscale machines (browser SSH)** | https://login.tailscale.com/admin/machines |
| **GitHub repo** | https://github.com/sahandsamadirad/prosecuto |

---

## SSH into GX10

```bash
# Browser — no terminal needed
# → https://login.tailscale.com/admin/machines → gx10-4d82 → SSH

# Terminal (from laptop on Tailscale)
tailscale ssh asus@gx10-4d82

# Or standard SSH
ssh asus@100.113.13.93
```

---

## Pull + deploy (most common)

```bash
# One command: git pull + rebuild + restart everything
bash ~/prosecuto/deploy/gx10/pull-and-deploy.sh
```

Manual steps if you prefer:

```bash
cd ~/prosecuto
git fetch origin main
git merge origin/main --no-edit
bash deploy/gx10/deploy-all.sh
```

> **Note:** `backend/.env` is local only (not in git). Pull never overwrites it.

---

## Restart without pulling new code

```bash
# Full redeploy (rebuild backend image + frontend)
bash ~/prosecuto/deploy/gx10/deploy-all.sh

# Backend only (Docker)
docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml restart api

# Backend + Redis (Docker)
docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml restart

# Frontend only (Next.js)
kill $(cat ~/prosecuto/logs/frontend.pid) 2>/dev/null || true
cd ~/prosecuto/frontend && nohup npm run start -- -H 0.0.0.0 -p 3000 > ~/prosecuto/logs/frontend.log 2>&1 &
echo $! > ~/prosecuto/logs/frontend.pid
```

---

## Stop everything

```bash
# Stop backend + Redis
docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml down

# Stop frontend
kill $(cat ~/prosecuto/logs/frontend.pid) 2>/dev/null || pkill -f "next start -H 0.0.0.0"
```

---

## View logs

```bash
# Backend (live, follow)
docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml logs -f api

# Backend (last 100 lines)
docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml logs --tail 100 api

# Redis
docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml logs -f redis

# Frontend
tail -f ~/prosecuto/logs/frontend.log
```

---

## Health checks

```bash
# Backend
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool

# Frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:3000/

# From Tailscale (same as laptop browser)
curl -s http://100.113.13.93:8000/api/health
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://100.113.13.93:3000/
```

---

## Status at a glance

```bash
docker ps --filter name=prosecuto
ss -tlnp | grep -E ':3000|:8000'
tail -3 ~/prosecuto/logs/frontend.log
```

---

## Machine info

| Item | Value |
|------|-------|
| Hostname | `gx10-4d82` |
| Tailscale IP | `100.113.13.93` |
| Repo path | `/home/asus/prosecuto` |
| Backend port | `8000` |
| Frontend port | `3000` |
| CPU / RAM | 20 cores / 121 GB |
| GPU | NVIDIA GB10 (CUDA 13.0) |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Port 3000 in use | `fuser -k 3000/tcp` then redeploy |
| Backend unhealthy | `docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml logs api` |
| Frontend build fails | `cd ~/prosecuto/frontend && npm install && npm run build` |
| Can't reach from laptop | Run `tailscale status` on both machines |
| Need fresh Docker build | `docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml build --no-cache api` |

---

## Copy-paste cheat sheet

```bash
# DEPLOY
bash ~/prosecuto/deploy/gx10/pull-and-deploy.sh

# LOGS
docker compose -f ~/prosecuto/deploy/gx10/docker-compose.yml logs -f api
tail -f ~/prosecuto/logs/frontend.log

# RESTART
bash ~/prosecuto/deploy/gx10/deploy-all.sh

# HEALTH
curl http://100.113.13.93:8000/api/health && curl -I http://100.113.13.93:3000
```
