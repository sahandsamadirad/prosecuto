#!/usr/bin/env bash
# Launch llama-server with qwen3.6:35b on full GPU (GB10, 124 GB unified VRAM)
pkill -x llama-server 2>/dev/null || true
sleep 2

GGUF=/usr/share/ollama/.ollama/models/blobs/sha256-f5ee307a2982106a6eb82b62b2c00b575c9072145a759ae4660378acda8dcf2d
LOGDIR=/home/asus/prosecuto/logs
mkdir -p "$LOGDIR"

nohup /home/asus/llama.cpp/build/bin/llama-server \
  --model "$GGUF" \
  --host 0.0.0.0 \
  --port 8081 \
  \
  `# ── GPU / compute ───────────────────────────────────────────────────` \
  --n-gpu-layers 999 \
  --flash-attn \
  \
  `# ── Batching ────────────────────────────────────────────────────────` \
  --cont-batching \
  --batch-size 2048 \
  --ubatch-size 512 \
  \
  `# ── Context / KV cache ──────────────────────────────────────────────` \
  --ctx-size 8192 \
  --parallel 4 \
  --cache-prompt \
  --defrag-thold 0.1 \
  --keep 1024 \
  \
  `# ── CPU threading (Grace CPU: 72 ARM cores) ─────────────────────────` \
  --threads 20 \
  --threads-batch 20 \
  \
  `# ── Memory ──────────────────────────────────────────────────────────` \
  --mlock \
  \
  > "$LOGDIR/llama-server.log" 2>&1 &

echo $! > "$LOGDIR/llama-server.pid"
echo "llama-server started PID=$(cat $LOGDIR/llama-server.pid)"
