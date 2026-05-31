# Manual deploy (no GitHub Actions)

One `git pull` on each machine, then start services.

## Network

| Machine | Tailscale IP | Role |
|---------|--------------|------|
| GX10 supercomputer | `100.113.13.93` | Backend + AI |
| Windows laptop | `100.125.125.54` | Frontend |

---

## SSH into the supercomputer

Both machines must be on Tailscale (same account).

### Option A — Tailscale SSH (already enabled on GX10)

From **PowerShell or CMD on the laptop**:

```powershell
tailscale ssh asus@gx10-4d82
```

Or by IP:

```powershell
tailscale ssh asus@100.113.13.93
```

First time, Tailscale may ask you to approve the device in the admin console.

### Option B — Normal SSH (OpenSSH on port 22)

```powershell
ssh asus@100.113.13.93
```

Uses your SSH key (`~/.ssh/id_ed25519` or `id_rsa` on Windows).  
To add your laptop’s public key to GX10 (run once from laptop, then paste on GX10):

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub
```

On GX10:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "PASTE_YOUR_PUBLIC_KEY" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### Useful commands after SSH

```bash
cd ~/prosecuto
git pull origin main
bash deploy/gx10/deploy.sh

# Logs
docker compose -f deploy/gx10/docker-compose.yml logs -f api

# Health
curl http://127.0.0.1:8000/api/health
```

---

## Backend vs SSH

| Purpose | How to connect |
|---------|----------------|
| **Shell / manage GX10** | SSH (above) |
| **App API (frontend → backend)** | HTTP `http://100.113.13.93:8000` |
| **WebSocket (voice/chat)** | `ws://100.113.13.93:8000` |

The frontend does **not** use SSH for the API — only HTTP/WebSocket over Tailscale.

---

## Step 1 — Supercomputer (GX10)

SSH in, then:

```bash
cd /home/asus/prosecuto
git pull origin main
bash deploy/gx10/deploy.sh
```

Verify from laptop browser or PowerShell:

```powershell
curl http://100.113.13.93:8000/api/health
```

Expected: `"status":"ok"`.

---

## Step 2 — Laptop (Windows)

In **PowerShell**:

```powershell
cd D:\Github\prosecuto
git pull origin main
powershell -ExecutionPolicy Bypass -File deploy\laptop\deploy.ps1
```

This:

1. Sets `frontend/.env.local` → backend `http://100.113.13.93:8000`
2. Runs `npm ci`, `npm run build`, `npm run start` on port **3000**

Open:

- http://localhost:3000
- http://100.125.125.54:3000 (from other Tailscale devices)

---

## Step 3 — Verify end-to-end

```powershell
# Backend (GX10)
curl http://100.113.13.93:8000/api/health

# Frontend (laptop)
curl http://localhost:3000
```

---

## When you update code

Run on **both** machines (order: GX10 first, then laptop):

```bash
# GX10
cd /home/asus/prosecuto && git pull origin main && bash deploy/gx10/deploy.sh
```

```powershell
# Laptop
cd D:\Github\prosecuto; git pull origin main; powershell -ExecutionPolicy Bypass -File deploy\laptop\deploy.ps1
```

Keep `backend/.env` on GX10 — it is not in git. Never overwrite it with `git pull`.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| SSH timeout | Check Tailscale: `tailscale status` on both machines |
| Backend unreachable from laptop | `curl http://100.113.13.93:8000/api/health` — restart: `bash deploy/gx10/deploy.sh` |
| Frontend build fails | `cd frontend; npm install; npm run build` |
| Port 3000 in use | Close old Next.js or change `-Port 3001` in deploy.ps1 |
