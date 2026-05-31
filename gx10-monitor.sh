#!/usr/bin/env bash
# GX10 system monitor — GPU, memory, services, inference speed
# Usage: bash ~/prosecuto/gx10-monitor.sh [--watch]

BOLD='\033[1m'; CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'

show() {
  clear
  echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════${RESET}"
  echo -e "${BOLD}  GX10 Supercomputer — $(date '+%Y-%m-%d %H:%M:%S')${RESET}"
  echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════${RESET}"

  # GPU
  echo -e "\n${BOLD}${YELLOW}GPU — NVIDIA GB10 (Blackwell, compute 12.1)${RESET}"
  nvidia-smi --query-gpu=utilization.gpu,utilization.memory,power.draw,temperature.gpu \
    --format=csv,noheader,nounits 2>/dev/null | \
    awk -F', ' '{printf "  Compute: %s%%  |  Mem BW: %s%%  |  Power: %sW  |  Temp: %s°C\n", $1, $2, $3, $4}'

  # GPU processes
  echo -e "  ${BOLD}Processes:${RESET}"
  nvidia-smi --query-compute-apps=pid,used_memory,name --format=csv,noheader 2>/dev/null | \
    awk -F', ' '{printf "    PID %-8s  %s MiB  %s\n", $1, $2, $3}' | \
    sed 's|/usr/local/bin/||; s|/home/asus/llama.cpp/build/bin/||'

  # Ollama loaded models
  echo -e "  ${BOLD}Loaded models:${RESET}"
  curl -s http://localhost:11434/api/ps 2>/dev/null | \
    python3 -c "
import json,sys
d=json.load(sys.stdin)
for m in d.get('models',[]):
    sz=m.get('size',0)//1024//1024
    print(f\"    {m['name']}  {sz} MiB  (expires: {m.get('expires_at','?')[:10]})\")
" 2>/dev/null || echo "    (none loaded)"

  # Memory
  echo -e "\n${BOLD}${YELLOW}Memory (121 GB unified CPU+GPU pool)${RESET}"
  free -h | awk '
    /^Mem:/ { printf "  RAM:   Used %-8s  Free %-8s  Available %s\n", $3, $4, $7 }
    /^Swap:/ { printf "  Swap:  Used %-8s  Free %s\n", $3, $4 }
  '

  # CPU
  echo -e "\n${BOLD}${YELLOW}CPU — 20 cores (10x Cortex-X925 + 10x Cortex-A725)${RESET}"
  top -bn1 | awk '/^%Cpu/ {printf "  Load:  %.1f%% user  %.1f%% sys  %.1f%% idle\n", $2, $4, $8}'
  uptime | awk -F'load average:' '{printf "  Load avg: %s\n", $2}'

  # Services
  echo -e "\n${BOLD}${YELLOW}Services${RESET}"
  # Backend
  if curl -sf http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
    MODEL=$(docker exec prosecuto-api python3 -c "from app.config import settings; print(settings.ollama_llm_model)" 2>/dev/null)
    echo -e "  ${GREEN}●${RESET} Backend (FastAPI :8000)  model=${MODEL}"
  else
    echo -e "  ${RED}●${RESET} Backend (FastAPI :8000)  DOWN"
  fi

  # Frontend
  if curl -sf -o /dev/null http://127.0.0.1:3000/ 2>/dev/null; then
    echo -e "  ${GREEN}●${RESET} Frontend (Next.js :3000)"
  else
    echo -e "  ${RED}●${RESET} Frontend (Next.js :3000)  DOWN"
  fi

  # Redis
  if docker exec prosecuto-redis redis-cli ping > /dev/null 2>&1; then
    REDIS_MEM=$(docker exec prosecuto-redis redis-cli info memory 2>/dev/null | grep used_memory_human | cut -d: -f2 | tr -d '\r')
    echo -e "  ${GREEN}●${RESET} Redis (:6379)  mem=${REDIS_MEM}"
  else
    echo -e "  ${RED}●${RESET} Redis (:6379)  DOWN"
  fi

  # Ollama
  if curl -sf http://localhost:11434/ > /dev/null 2>&1; then
    echo -e "  ${GREEN}●${RESET} Ollama (:11434)"
  else
    echo -e "  ${RED}●${RESET} Ollama (:11434)  DOWN"
  fi

  # Disk
  echo -e "\n${BOLD}${YELLOW}Disk${RESET}"
  df -h / | awk 'NR==2 {printf "  /  Used: %s / %s (%s)  Free: %s\n", $3, $2, $5, $4}'
  du -sh /usr/share/ollama/.ollama/models/ 2>/dev/null | awk '{printf "  Ollama models: %s\n", $1}'

  # Quick inference benchmark (only if --bench flag)
  if [[ "${1}" == "--bench" ]]; then
    echo -e "\n${BOLD}${YELLOW}Inference Benchmark${RESET}"
    MODEL=$(curl -s http://localhost:11434/api/ps | python3 -c "
import json,sys
d=json.load(sys.stdin)
models=d.get('models',[])
print(models[0]['name'] if models else 'nemotron3:33b')
" 2>/dev/null)
    echo -n "  Testing ${MODEL}... "
    RESULT=$(curl -s -X POST http://localhost:11434/api/generate \
      -d "{\"model\":\"${MODEL}\",\"prompt\":\"Count 1 to 5\",\"stream\":false}" \
      --max-time 30 | \
      python3 -c "
import json,sys
d=json.load(sys.stdin)
ev=d.get('eval_count',0)
dur=d.get('eval_duration',1)
print(f'{round(ev/dur*1e9,1)} tok/s ({ev} tokens)')
" 2>/dev/null)
    echo -e "${GREEN}${RESULT}${RESET}"
  fi

  echo -e "\n${BOLD}${CYAN}══════════════════════════════════════════════════════${RESET}"
  echo -e "  ${BOLD}nvitop${RESET}          interactive GPU monitor"
  echo -e "  ${BOLD}gpustat${RESET}         one-line GPU status"
  echo -e "  ${BOLD}glances${RESET}         full system overview"
  echo -e "  ${BOLD}glances -w${RESET}      web UI on :61208 (open in browser)"
  echo -e "  ${BOLD}nsys profile${RESET}    NVIDIA Nsight profiler"
  echo -e "  ${BOLD}watch -n1 nvidia-smi${RESET}  live GPU stats"
  echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════${RESET}"
}

if [[ "${1}" == "--watch" ]]; then
  while true; do show; sleep 3; done
elif [[ "${1}" == "--bench" ]]; then
  show --bench
else
  show
fi
