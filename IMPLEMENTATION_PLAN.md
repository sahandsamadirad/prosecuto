# Prosecuto — Phase-by-Phase Implementation Plan
> Build in this order. Each phase has a clear "done" criterion. Do not skip ahead.
> Pair with `ARCHITECTURE.md` for the full spec of what each component does.

---

## Build Philosophy

- **Vertical slices, not horizontal layers.** Each phase produces something runnable, even if narrow.
- **Mock first, integrate second.** Every external dependency (NIM endpoints, Riva, A2F) gets a mock during early phases so we're not blocked waiting on infra.
- **Tests live alongside code.** Every phase ends with at least one test that proves the phase works.
- **Don't add features mid-phase.** If you find a gap, write it down and finish the phase first.

---

## Phase 0 — Project Bootstrap
**Goal:** Working FastAPI app, env wiring, Docker compose, no business logic.
**Owner:** 1 person, ~1 hour.

### Tasks

1. Create the directory structure from `ARCHITECTURE.md` section 4. Empty files with docstrings are fine.
2. `pyproject.toml` with dependencies:
   ```
   fastapi, uvicorn[standard], pydantic, pydantic-settings,
   langchain, langgraph, langchain-nvidia-ai-endpoints,
   chromadb, redis, tavily-python,
   python-multipart, websockets, structlog,
   pytest, pytest-asyncio, httpx
   ```
3. `app/config.py` with `pydantic-settings`-based `Settings` reading from `.env`. List every env var from `ARCHITECTURE.md` section 15.
4. `app/main.py` with FastAPI app, `/api/health` endpoint that returns `{"status": "ok"}`.
5. `docker-compose.yml` for FastAPI + Redis + Chroma (NIM containers added later when we have hackathon hardware).
6. `.env.example` committed with all keys blank.

### Done when

- `docker-compose up` starts the stack with no errors
- `curl http://localhost:8000/api/health` → 200
- `pytest` runs (zero tests is fine)

---

## Phase 1 — Indexer
**Goal:** Build the RAG corpus pipeline. Directory of `.txt` files → embedded chunks in Chroma.
**Owner:** 1 person, ~2-3 hours.

### Tasks

1. **Stub corpus.** Place 3-5 small `.txt` files in `backend/data/corpus/` for testing. Real corpus comes later.
2. **Implement `app/rag/indexer.py`** with the signature from `ARCHITECTURE.md` section 7:
   ```python
   def build_index(corpus_dir, chroma_dir, collection_name, chunk_size, chunk_overlap, glob_pattern) -> IndexStats
   ```
3. Recursive file discovery using `pathlib.Path.rglob(glob_pattern)`.
4. Chunking with LangChain's `RecursiveCharacterTextSplitter`. Separators in order: `["\n\n", "\n", ". ", " ", ""]`.
5. Embedding with `NVIDIAEmbeddings(model="nvidia/nv-embedqa-e5-v5")`. Batch by 32.
6. Chroma upsert with idempotent IDs: `sha256(filepath + chunk_index)`.
7. Metadata: `{source_path, filename, chunk_index, char_start, char_end, total_chunks}`.
8. CLI entrypoint: `python -m app.rag.indexer --corpus-dir ... --chroma-dir ...`.
9. Return `IndexStats(files_processed, chunks_created, errors)`.

### Done when

- Running the CLI against the stub corpus creates a Chroma collection
- Re-running the CLI does NOT duplicate chunks (idempotent IDs verified by querying Chroma count)
- A pytest test loads a small file, indexes it, queries the collection, and gets back the right chunk

### Reference

Mirror the patterns in the reference repo at `tools/vector_database/chromadb/chroma_db.ipynb`.

---

## Phase 2 — Retriever + Self-RAG Critic
**Goal:** Given a query, return reranked, relevance-graded passages. Tavily fallback when relevance fails.
**Owner:** 1 person, ~3-4 hours.

### Tasks

1. **Implement `app/rag/retriever.py`** with the `ProsecutoRetriever` class.
2. Chroma similarity search, top-`k` (default 8).
3. Rerank with `NVIDIARerank(model="nvidia/rerank-qa-mistral-4b")` down to top-`n` (default 4).
4. **Implement `app/rag/critic.py`** with three critic functions, each using `ChatNVIDIA(model="nvidia/llama-3.3-nemotron-super-49b-v1")` with `with_structured_output`:
   - `grade_relevance(query, passage) -> {relevant: bool, reason: str}`
   - `grade_grounding(answer, passages) -> {grounded: bool, unsupported_claims: list[str]}`
   - `grade_adequacy(question, answer) -> {adequate: bool, missing: list[str]}`
5. **Implement `app/rag/tavily_fallback.py`** wrapping `TavilyClient.search()` with `max_results=5`.
6. Wire `ProsecutoRetriever.retrieve()` to call: Chroma → Rerank → Relevance Critic → return passages OR trigger Tavily.
7. Add session-scoped Tavily cache (dict keyed by query string).

### Done when

- Unit test: query → passages from Chroma with metadata
- Unit test: query that returns irrelevant passages triggers Tavily
- Unit test: each critic returns the expected Pydantic structure
- Hard cap of 2 generation retries enforced (test by mocking grounding critic to always return False — must not infinite loop)

### Reference

Mirror `LangChain/udemy_course/RAGs/langchain Documentation Helper(agentic-rag)` and `LangChain/udemy_course/search-agent` in the reference repo.

---

## Phase 3 — Schemas & State
**Goal:** Pydantic models for everything. No agents yet — just shapes.
**Owner:** 1 person, ~1-2 hours.

### Tasks

1. **`app/schemas/case.py`** — `TicketDetails`, `TicketDiagnosis`, `Turn`, `CaseFile`.
2. **`app/schemas/packages.py`** — `ERPackage`, `ScreeningReviewPackage`, `TrialPrepPackage`, `DisclosurePackage`. Field-level breakdown lives in the system prompt and the package specs we agreed on earlier. Every package has `confidence`, `is_preliminary`, `generated_at`, `flags`.
3. **`app/orchestrator/state.py`** — `SessionState`. Full schema from `ARCHITECTURE.md` section 9.
4. **`app/schemas/messages.py`** — WebSocket message envelope: `WSMessage` with `type`, `session_id`, `seq`, `timestamp`, `payload`. Union of all payload types.

### Done when

- All schemas import cleanly
- A unit test serializes and deserializes each one
- `mypy` (or `pyright`) is clean on the schemas folder

---

## Phase 4 — Memory Layer
**Goal:** SessionState load/save with Redis + in-memory fallback. Test-only mode if Redis is down.
**Owner:** 1 person, ~2 hours.

### Tasks

1. **`app/memory/store.py`** — abstract `SessionStore` with two implementations: `RedisSessionStore` and `InMemorySessionStore`.
2. **`app/memory/session.py`** — `load(session_id)`, `save(state)`, `delete(session_id)`, `lock(session_id)` (async context manager for mutex).
3. JSON serialization via Pydantic's `model_dump_json()`. Deserialization via `model_validate_json()`.
4. TTL of 24h on Redis keys.
5. Fallback: if Redis ping fails at startup, log a warning and use in-memory store. **Never crash.**

### Done when

- Unit test: save a SessionState, load it back, assert equality
- Unit test: in-memory fallback works when Redis URL is unreachable
- Concurrent save/load with the lock works (test with two asyncio tasks)

---

## Phase 5 — Lawyer Mode Agents (One by One)
**Goal:** All six Lawyer Mode agents implemented as separate LLM calls.
**Owner:** 2 people in parallel, ~4-6 hours total.

### General Agent Pattern

Each agent inherits from `BaseAgent` in `app/agents/base.py`:

```python
class BaseAgent:
    name: str
    system_prompt: str  # base + character

    def __init__(self, llm, retriever=None):
        self.llm = llm
        self.retriever = retriever

    async def run(self, state: SessionState) -> AgentResult:
        # 1. Build messages (system + conversation history + case file)
        # 2. Retrieve if needed
        # 3. Call LLM with structured output
        # 4. Return AgentResult(updated_state, assistant_text)
        ...
```

Every agent returns `AgentResult` with `updated_state: SessionState` and `assistant_text: str` (what the avatar will say next).

### Build Order

1. **Required Info Agent** (`app/agents/required_info.py`)
   - Checklist: ticket type (officer/camera), ticket date, intersection, vehicle owner, who was driving, ticket number, fine amount, deadline date
   - Conversational: ask one or two missing fields per turn
   - Tool: none
   - Output: populated `TicketDetails`

2. **Ticket Diagnosis Agent** (`app/agents/ticket_diagnosis.py`)
   - Input: `TicketDetails` + conversation history
   - Output: `TicketDiagnosis(type, sub_type, deadline_status, recap_text)`
   - For camera tickets, detect cutoff date (pre/post Jan 20 2025) for AMPS routing
   - Verify deadline using `datetime.now()` vs ticket date
   - Tool: retriever (filter to HTA + AMPS regs)

3. **Procedure Map Agent** (`app/agents/procedure_map.py`)
   - Input: `TicketDiagnosis`
   - Output: list of `PathOption` with descriptions
   - Reads the correct sub-tree based on officer vs camera
   - Tool: retriever

4. **Sufficient Data Check** (`app/agents/sufficient_data.py`)
   - Two steps:
     - Rule-based: are all required `TicketDetails` fields populated?
     - LLM-based: does the case have enough substantive content to build a defence on?
   - Output: `{sufficient: bool, reason: str}`
   - Tool: none

5. **Disclosure Request Agent** (`app/agents/disclosure.py`)
   - Output: `DisclosurePackage` with formal request text, itemized requests, submission instructions, diary date
   - Tool: retriever (filter to disclosure + Stinchcombe)

6. **Defence Theory Agent** (`app/agents/defence_theory.py`)
   - The heaviest. Produces one of three packages based on `chosen_path`:
     - `early_resolution` → `ERPackage`
     - `screening_review` → `ScreeningReviewPackage`
     - `trial` → `TrialPrepPackage`
   - Full Self-RAG with all three critics
   - Tools: retriever, Tavily fallback
   - Tag output `is_preliminary=True` if disclosure was requested but not yet received

### Done when

- Each agent has a unit test that mocks the LLM and verifies the agent calls structured output correctly
- One end-to-end test: walk through a scripted conversation hitting all 6 agents in order, assert final package is well-formed
- Each agent can be invoked in isolation with a SessionState fixture

---

## Phase 6 — Lawyer Mode Orchestrator (LangGraph)
**Goal:** Compose the 6 agents into a graph with conditional edges and checkpointing.
**Owner:** 1 person, ~3-4 hours.

### Tasks

1. **`app/orchestrator/graph_lawyer.py`** — build the graph from `ARCHITECTURE.md` section 12.
2. Each node = one agent's `run()` method.
3. Conditional edges:
   - After `procedure_map`, route based on `state.chosen_path`
   - After `sufficient_data`, route to `disclosure` (False) or directly to `defence_theory` (True)
4. Checkpointer: use LangGraph's `RedisSaver` (or `MemorySaver` in dev) for state persistence.
5. Graph state is `SessionState`.
6. Streaming support: `graph.astream()` so the WS layer can pipe each node's `assistant_text` to TTS immediately.

### Done when

- Integration test: feed a full scripted conversation through the graph, end-to-end, in one process
- Test resumability: kill mid-graph, reload state from Redis, continue from same node
- Each node's `assistant_text` is yielded as it completes — the test asserts streaming order

---

## Phase 7 — HTTP API
**Goal:** REST endpoints for session lifecycle and file upload.
**Owner:** 1 person, ~2 hours.

### Tasks

Implement endpoints from `ARCHITECTURE.md` section 11:

1. `POST /api/session` — create session, allocate session_id, set mode, save initial state.
2. `GET /api/session/{session_id}` — return current SessionState.
3. `DELETE /api/session/{session_id}` — delete from store.
4. `POST /api/session/{session_id}/upload` — accept multipart ticket photo. Store to `data/uploads/{session_id}/`. Stretch: OCR with Tesseract or pass to a vision model later.
5. `GET /api/session/{session_id}/package` — return whichever package is non-null.
6. `POST /api/index/rebuild` — trigger indexer. Protected by simple bearer token from `.env`.
7. `GET /api/health` — already exists; expand to ping Redis, Chroma, NIM endpoints.

### Done when

- All endpoints have httpx integration tests
- Returns appropriate 4xx for missing/invalid session IDs
- File upload size limits enforced (e.g. 10MB)

---

## Phase 8 — WebSocket Text Channel
**Goal:** Text-only conversation channel hitting the orchestrator. Voice comes next.
**Owner:** 1 person, ~2-3 hours.

### Tasks

1. **`app/api/ws.py`** — WS endpoint at `/ws/text/{session_id}`.
2. On connect: load SessionState from store. If missing, close with 4404.
3. On user message: append to `state.transcript`, invoke `graph.astream()`, stream each node's `assistant_text` back as `agent_text` WS messages.
4. On graph completion: save final state, emit `state_update` message with summary.
5. Use the WS message envelope from `app/schemas/messages.py`.
6. Acquire session lock before invoking the graph. Release after final save.

### Done when

- Two browser tabs (or two test clients) can hold simultaneous sessions without interference
- Closing the WS mid-conversation does NOT corrupt state (lock + atomic save)
- Reconnecting with the same session_id resumes from where the user left off

---

## Phase 9 — Voice Pipeline
**Goal:** Live conversation with the user via mic → ASR → orchestrator → TTS → A2F → blendshapes/audio out.
**Owner:** 1-2 people, ~6-8 hours.

### Tasks

1. **`app/voice/asr.py`** — Riva Parakeet gRPC client. Streaming input, emits interim + final transcripts.
2. **`app/voice/tts.py`** — Riva or Magpie TTS client. Sentence-by-sentence streaming.
3. **`app/voice/audio2face.py`** — Audio2Face-3D client. Takes audio chunks, emits blendshape values @ ~30fps.
4. **`/ws/voice/in/{session_id}`** — accept PCM audio frames, forward to ASR, emit `asr_interim` and `asr_final` upstream.
5. **`/ws/voice/out/{session_id}`** — accept TTS audio + blendshape stream, push to browser as `tts_audio` + `a2f_blendshapes` messages.
6. **Orchestrator integration:**
   - On `asr_final` → append to transcript, invoke graph
   - As graph streams `assistant_text` → segment by sentence → push to TTS pipeline
   - TTS audio → simultaneously to A2F + to outbound WS
   - A2F blendshapes → outbound WS
7. **Interruption handling** — when ASR detects new voice activity during avatar speech: cancel in-flight LLM/TTS via `asyncio.CancelledError`, drain queues, start new turn.

### Done when

- End-to-end voice loop works on dev hardware (even with placeholder NIM endpoints)
- Latency from end of user speech to start of avatar speech is measured and logged
- Interruption test passes: user starts speaking mid-response, avatar stops cleanly
- Two concurrent voice sessions don't cross wires

### Reference

The reference repo doesn't cover real-time voice — this is novel ground for the project. Use NVIDIA's official A2F-3D NIM streaming examples as the base.

---

## Phase 10 — Judge Mode
**Goal:** Mock trial simulation with three characters (Judge/Prosecutor/Clerk) and a court state machine.
**Owner:** 1-2 people, ~4-6 hours.

### Tasks

1. **`app/agents/judge.py`**, **`app/agents/prosecutor.py`**, **`app/agents/clerk.py`** — three character agents, each with its own system prompt.
2. **`app/orchestrator/graph_judge.py`** — LangGraph implementing the court state machine from `ARCHITECTURE.md` section 12.
3. Each state is a node. "Waits on user" nodes pause execution and yield to the WS layer.
4. State stores both `transcript` (overall) and `court_transcript` (just the trial proceedings).
5. After VERDICT, route to FEEDBACK node. Judge breaks character and gives critique referencing specific moments in the trial transcript.

### Done when

- Full mock trial runs end-to-end from CLERK_CALL_TO_ORDER to FEEDBACK
- Voice-driven version works (uses Phase 9 infrastructure)
- The active speaker switches correctly between Judge, Prosecutor, Clerk (each gets a different TTS voice)
- Feedback at the end references actual moments the user said

---

## Phase 11 — Real Corpus & Hardening
**Goal:** Replace stub corpus with the real Ontario legal corpus. Tighten error handling. Measure latency.
**Owner:** Whole team, ~ongoing.

### Tasks

1. Populate `data/corpus/` with the real files listed in `ARCHITECTURE.md` section 7.
2. Re-run indexer.
3. End-to-end test with a real ticket scenario (sample user transcript).
4. Latency profiling: where are we spending time? ASR? Retrieval? LLM? Optimize the slowest leg.
5. Error handling: every external call (NIM, Redis, Chroma, Tavily) needs a timeout + retry policy.
6. Logging: structured logs with `structlog`, session_id on every line.
7. Loading screen + status messages in the frontend during long retrievals.

### Done when

- A demo run with a real example ticket works in <2.5s per turn end-to-end
- No external call can hang the pipeline for more than 5 seconds
- Logs let you trace one user turn from mic to avatar response cleanly

---

## Phase 12 — Demo Prep
**Goal:** Hackathon-ready demo.
**Owner:** Whole team.

### Tasks

1. Two scripted demos: one Lawyer Mode (officer ticket disputed via E.R.), one Judge Mode (camera-ticket-style trial).
2. Recorded fallback in case live infra fails during demo.
3. One-page README with what Prosecuto does and how to run it.
4. Demo script with timing.

---

## Anti-Patterns to Avoid

- **Don't skip the Self-RAG critic.** Hallucinated legal advice is the failure mode.
- **Don't put business logic in WS handlers.** Handlers are thin — they marshal messages. Logic lives in the orchestrator.
- **Don't pass raw dicts between agents.** Pydantic models everywhere.
- **Don't run the indexer at startup.** It's a separate CLI step.
- **Don't make agents call each other directly.** Only the orchestrator routes between agents.
- **Don't store NVIDIA API keys in commits.** `.env` is gitignored.
- **Don't let any single LLM call take >10s.** Set hard timeouts.

---

*Prosecuto · Implementation Plan v1.0 · Spark Hack Toronto*
