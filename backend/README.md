# Prosecuto Backend

AI + API services for Prosecuto — an Ontario red light camera ticket dispute tool.
See `../ARCHITECTURE.md` and `../IMPLEMENTATION_PLAN.md` for the full spec.

## Quick start (local)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # fill in NVIDIA_API_KEY, TAVILY_API_KEY

uvicorn app.main:app --reload --port 8000
curl http://localhost:8000/api/health   # -> {"status":"ok"}
```

## Docker

```bash
cd backend
cp .env.example .env
docker compose up --build
```

## Tests

```bash
cd backend
pytest
```

## Layout

```
app/
  main.py            FastAPI entrypoint
  config.py          pydantic-settings singleton
  api/               http.py (REST) + ws.py (WebSocket)
  agents/            Lawyer + Judge mode agents
  orchestrator/      LangGraph graphs + SessionState
  rag/               indexer, retriever, critic, tavily_fallback
  voice/             asr / tts / audio2face clients
  memory/            session store (Redis + in-memory fallback)
  schemas/           Pydantic models (case, packages, messages)
  prompts/           system + character prompts
data/
  corpus/            .txt source files for indexing (gitignored)
  chroma/            Chroma persistent dir (gitignored)
```

## Build order

Phases are tracked in `../IMPLEMENTATION_PLAN.md`. Build vertically, phase by phase.
```
