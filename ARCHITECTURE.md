# Prosecuto — Backend Architecture & Development Spec
> Read this in full before writing any backend code.
> Pair with `IMPLEMENTATION_PLAN.md` for the build order.
> Root `CLAUDE.md` stays minimal (loads every message); link here for detail.

---

## 1. Product Recap

Prosecuto is an Ontario red light camera ticket dispute tool with two modes that share one backend pipeline:

- **Lawyer Mode** — agentic prep flow producing one of three packages (E.R. Package, Screening Review Package, Trial Prep Package). User talks to a 3D avatar (Alex).
- **Judge Mode** — full mock trial simulation with three rotating characters (Justice of the Peace, Crown Prosecutor, Court Clerk) driven by a court-procedure state machine.

Both modes are **real-time voice conversations** with a 3D avatar. The pipeline must be low-latency end to end (target <2s from end of user speech to start of avatar speech).

---

## 2. Tech Stack — Exact

### Core
- **Python 3.11+**
- **FastAPI** — HTTP and WebSocket server
- **LangChain** — orchestration primitives, retrievers, prompt scaffolding
- **LangGraph** — stateful agent orchestrator (this is what runs the conversation graph)
- **ChromaDB** — vector store (local persistent client)
- **Pydantic v2** — every payload, state object, and package schema is a Pydantic model
- **Redis** — session memory persistence (optional in dev; required for resumable sessions)

### NVIDIA NIM (via `langchain-nvidia-ai-endpoints`)
- **LLM:** `nvidia/llama-3.3-nemotron-super-49b-v1` — Lawyer, Judge, Prosecutor, all critics
- **Embedding:** `nvidia/nv-embedqa-e5-v5`
- **Reranker:** `nvidia/rerank-qa-mistral-4b` — exposed via `NVIDIARerank`
- **ASR:** Riva Parakeet (streaming) — gRPC client
- **TTS:** Riva TTS or Magpie TTS — gRPC client, streaming output
- **Avatar:** Audio2Face-3D NIM — audio in, blendshapes out, gRPC + WebSocket

### Tooling
- **Tavily** — web search fallback (max 5 sources per call)
- **uv** or **pip** — package management. `uv` preferred.
- **pytest** — test runner

### Frontend (separate folder in same monorepo)
- React + Three.js for 3D head rendering and ARKit-compatible blendshape streaming. The backend doesn't render anything; it streams audio + blendshape values over WebSocket.

---

## 3. Reference Repository Patterns

The team's reference repo `https://github.com/Abtinz/LLM-GANs-Projects` contains patterns to draw from directly:

- `LangChain/udemy_course/RAGs/langchain Documentation Helper(agentic-rag)` — agentic-RAG structure with retriever + critic
- `LangChain/udemy_course/langgraph` — ReAct-style LangGraph agent with crawl/search tools and loop safeguards (use the loop-cap pattern verbatim — Self-RAG can infinite-loop without it)
- `LangChain/udemy_course/search-agent` — Tavily-powered search agent pattern
- `Lang-Graph/codebasics_tutorial/memory_in_langgraph.ipynb` — LangGraph memory persistence
- `tools/vector_database/chromadb/chroma_db.ipynb` — Chroma collection management, embedding storage, similarity query workflow
- `MCP/Authentiation` — FastAPI + FastMCP scaffolding pattern for the WebSocket/HTTP layer

Mirror those patterns. Don't reinvent.

---

## 4. Repo Structure

```
prosecuto/
├── frontend/                          # React + Three.js (separate concern)
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI entrypoint, mounts routers
│   │   ├── config.py                  # env vars, model names, paths
│   │   ├── api/
│   │   │   ├── http.py                # REST endpoints (session CRUD, file uploads)
│   │   │   └── ws.py                  # WebSocket endpoints (voice loop)
│   │   ├── agents/
│   │   │   ├── base.py                # BaseAgent abstract class
│   │   │   ├── required_info.py       # Required Info Agent
│   │   │   ├── ticket_diagnosis.py    # Ticket Diagnosis Agent
│   │   │   ├── procedure_map.py       # Procedure Map Agent
│   │   │   ├── sufficient_data.py     # Internal gate (rule + LLM)
│   │   │   ├── disclosure.py          # Disclosure Request Agent
│   │   │   ├── defence_theory.py      # Defence Theory Agent
│   │   │   ├── judge.py               # Judge (JP) for Mode 2
│   │   │   ├── prosecutor.py          # Crown Prosecutor for Mode 2
│   │   │   └── clerk.py               # Court Clerk for Mode 2
│   │   ├── orchestrator/
│   │   │   ├── graph_lawyer.py        # LangGraph for Lawyer Mode
│   │   │   ├── graph_judge.py         # LangGraph for Judge Mode (state machine)
│   │   │   └── state.py               # SessionState Pydantic model
│   │   ├── rag/
│   │   │   ├── indexer.py             # Directory → chunks → Chroma
│   │   │   ├── retriever.py           # Self-RAG retrieve + rerank
│   │   │   ├── critic.py              # Relevance + hallucination + answer grader
│   │   │   └── tavily_fallback.py     # Web search fallback (≤5 sources)
│   │   ├── voice/
│   │   │   ├── asr.py                 # Riva Parakeet client
│   │   │   ├── tts.py                 # Riva/Magpie TTS client
│   │   │   └── audio2face.py          # A2F-3D streaming client
│   │   ├── memory/
│   │   │   ├── session.py             # Session memory load/save
│   │   │   └── store.py               # Redis (or in-mem fallback) backend
│   │   ├── schemas/
│   │   │   ├── case.py                # CaseFile, TicketDetails
│   │   │   ├── packages.py            # E.R., Screening Review, Trial Prep schemas
│   │   │   └── messages.py            # WS message envelope types
│   │   └── prompts/
│   │       ├── base.py                # Universal system prompt (from SYSTEM_PROMPT.md)
│   │       └── characters/            # Per-agent character prompts
│   ├── data/
│   │   ├── corpus/                    # .txt files for indexing (HTA, POA, AMPS regs, case law)
│   │   └── chroma/                    # Chroma persistent dir
│   ├── tests/
│   ├── pyproject.toml
│   └── docker-compose.yml             # FastAPI + Redis + Chroma + NIM containers
├── ARCHITECTURE.md                    # this file
├── IMPLEMENTATION_PLAN.md
├── SYSTEM_PROMPT.md                   # universal AI behaviour spec
└── CLAUDE.md                          # minimal, root-level (loads every message)
```

---

## 5. Agent Inventory

Six Lawyer Mode agents + three Judge Mode characters. Each is **a separate LLM call** with its own system prompt, called by the LangGraph orchestrator.

### Lawyer Mode

| Agent | Purpose | Tools | Output |
|-------|---------|-------|--------|
| **Required Info Agent** | Conversational intake. Drives a checklist of required fields. Will not advance until all fields are filled or explicitly skipped. | none | Populated `TicketDetails` |
| **Ticket Diagnosis Agent** | Classifies ticket: Officer-issued vs Camera-issued. Detects camera ticket date cutoff (pre/post Jan 20 2025). Generates structured recap shown back to user. Verifies deadline using current date + ticket date. | RAG (for deadline rules) | `TicketDiagnosis` + recap text |
| **Procedure Map Agent** | Explains the user's available paths (Pay / E.R. / Trial / Screening Review) based on diagnosis. Reads the appropriate sub-tree from the procedure map. | RAG | Path options + explanation |
| **Sufficient Data Check** | Internal gate. Step (a): rule-based — all required fields populated? Step (b): LLM judgment — is there enough substantive content to build a real defence? Both must pass. | none | `bool + reason` |
| **Disclosure Request Agent** | Activated when Sufficient Data = False or user explicitly requests it. Generates the formal disclosure request script + submission instructions. Flags the eventual package as "preliminary, refresh after disclosure." | RAG | `DisclosurePackage` |
| **Defence Theory Agent** | The heaviest agent. Uses Self-RAG to pull regs and case law. Produces the path-appropriate package: E.R., Screening Review, or Trial Prep. | RAG (Self-RAG), Tavily fallback | One of three package Pydantic models |

### Judge Mode

| Character | Purpose | Tools |
|-----------|---------|-------|
| **Judge (JP)** | Runs the court state machine. Rules on objections. Delivers verdict. Breaks character at end for feedback. | RAG (procedural rulings) |
| **Crown Prosecutor** | Tenders standard red light camera evidence. Cross-examines. | RAG |
| **Court Clerk** | Call to order, oath/affirmation, exhibit handling. Short, formal, no opinions. | none |

---

## 6. Self-RAG Pipeline

This is the retrieval architecture used by every agent that touches the corpus.

### Flow

```
user_query
   │
   ▼
[1] Retrieve top-K from Chroma
   │
   ▼
[2] Rerank with nv-rerank-qa-mistral-4b → top-N (default N=4)
   │
   ▼
[3] Critic — Relevance grade
     "Is this passage relevant to the query?"
     ├── No relevant docs → fall to [4b]
     └── Yes
   │
   ▼
[4a] Generate answer with retrieved context
   │
   ▼
[5] Critic — Grounding/hallucination check
     "Is the generated answer supported by the retrieved passages?"
     ├── No → loop back to [4a] with stricter prompt (max 1 retry)
     └── Yes
   │
   ▼
[6] Critic — Answer adequacy
     "Does this fully answer the user's question?"
     ├── No → [4b] Tavily fallback
     └── Yes → return

[4b] Tavily fallback (max 5 sources, instruction-guided)
     → re-enter [4a] with web context
     → if still ungrounded after retry, return with low-confidence flag
```

### Critic Implementation

The critic is one LLM (Nemotron Super 49B) with three different system prompts, called sequentially:

1. **Relevance critic** — input: passage + query. Output: `{relevant: bool, reason: str}`.
2. **Grounding critic** — input: answer + passages. Output: `{grounded: bool, unsupported_claims: list[str]}`.
3. **Answer-adequacy critic** — input: question + answer. Output: `{adequate: bool, missing: list[str]}`.

Each critic call uses **structured output** (Pydantic JSON schema). Use LangChain's `with_structured_output` on the Nemotron model.

### Loop Safeguard

**Hard cap of 2 generation retries per agent call.** No infinite loops. After cap, return what we have with `confidence: "low"` and let downstream code (or the user) decide. Mirror the loop-safeguard pattern from the reference repo's `langgraph` folder.

### Tavily Fallback Rules

- Trigger: relevance critic returns no relevant docs **OR** answer-adequacy critic fails on the RAG path
- Max 5 sources per call (`max_results=5`)
- Instruction-guided crawl when possible (specify the legal jurisdiction in the query)
- Cache results for the session — same query within the same session reuses results, no re-call

---

## 7. Indexer Specification

The indexer ingests the corpus into ChromaDB. **Reusable, idempotent, takes a directory path as input.**

### Behaviour

```python
# Pseudocode signature
def build_index(
    corpus_dir: str,                    # directory to recursively scan
    chroma_dir: str,                    # Chroma persistent dir
    collection_name: str = "prosecuto", # Chroma collection
    chunk_size: int = 1000,             # characters
    chunk_overlap: int = 200,
    glob_pattern: str = "**/*.txt",     # recursive .txt
) -> IndexStats: ...
```

### Steps

1. **Discover** — recursively walk `corpus_dir` for files matching `glob_pattern`. Default `.txt`.
2. **Load** — each file becomes one or more Documents. Preserve filename and relative path as metadata.
3. **Chunk** — `RecursiveCharacterTextSplitter` from LangChain, separators `["\n\n", "\n", ". ", " ", ""]`. `chunk_size=1000`, `chunk_overlap=200`.
4. **Embed** — `NVIDIAEmbeddings(model="nvidia/nv-embedqa-e5-v5")`. Batch in groups of 32.
5. **Upsert** — into Chroma collection. Each chunk's ID = `sha256(filepath + chunk_index)` so re-indexing the same file is idempotent.
6. **Metadata per chunk** — `{source_path, filename, chunk_index, char_start, char_end, total_chunks_in_doc}`.

### Initial Corpus Files

To be placed under `backend/data/corpus/`:

- `hta_s144.txt` — Highway Traffic Act section 144 (red light offence)
- `hta_s205.txt` — admissibility of camera evidence
- `poa_part_i.txt` — Provincial Offences Act Part I (officer-issued tickets)
- `ontario_reg_355_22.txt` — administrative monetary penalty system regulation
- `ontario_reg_258_98.txt` — Rules of the Small Claims Court (only for reference — out of scope but useful context)
- `disclosure_law_stinchcombe.txt` — *R. v. Stinchcombe* summary
- `red_light_camera_amps_toronto.txt` — Toronto AMPS process documentation
- `red_light_camera_amps_mississauga.txt`, etc. — other municipalities
- `early_resolution_process.txt`
- `trial_procedure_poa.txt`
- `defence_grounds_red_light.txt` — the 7 legitimate defence grounds, with case law for each

Source these from official sites (ontariocourts.ca, e-laws.gov.on.ca, municipal sites) and paste cleaned text into the files. **Do not commit copyrighted full texts** — keep them gitignored or in a separate private corpus dir.

### CLI Entrypoint

```bash
python -m backend.app.rag.indexer \
    --corpus-dir backend/data/corpus \
    --chroma-dir backend/data/chroma \
    --collection prosecuto
```

---

## 8. Retriever Specification

### Interface

```python
class ProsecutoRetriever:
    def retrieve(
        self,
        query: str,
        k: int = 8,            # initial Chroma retrieval
        n: int = 4,            # post-rerank
        filters: dict = None,  # optional metadata filter
    ) -> RetrievalResult: ...
```

### Steps

1. Chroma similarity search, top-`k` (default 8)
2. Rerank with `NVIDIARerank(model="nvidia/rerank-qa-mistral-4b")` down to top-`n` (default 4)
3. Pass to Relevance Critic
4. If all docs filtered out → return empty + trigger Tavily fallback upstream
5. Return `RetrievalResult(passages: list[Passage], scores: list[float], source: "rag" | "tavily")`

### Metadata Filtering

Use Chroma metadata filters to scope retrieval per agent:
- Ticket Diagnosis Agent → filter `{source_path: contains "hta" or "amps"}`
- Defence Theory Agent → no filter, broad search
- Disclosure Agent → filter `{source_path: contains "disclosure" or "stinchcombe"}`

---

## 9. Session Memory

**Memory is critical** — every agent must see what the user said earlier, what the diagnosis was, what path they chose, what's in their case file.

### State Object

One `SessionState` Pydantic model carried through the LangGraph. Persisted to Redis after every node.

```python
class SessionState(BaseModel):
    session_id: str
    mode: Literal["lawyer", "judge"]
    created_at: datetime
    updated_at: datetime

    # Case data
    ticket_details: TicketDetails | None
    diagnosis: TicketDiagnosis | None
    chosen_path: Literal["pay", "early_resolution", "screening_review", "trial"] | None
    disclosure_requested: bool
    sufficient_data: bool | None

    # Outputs
    er_package: ERPackage | None
    screening_review_package: ScreeningReviewPackage | None
    trial_prep_package: TrialPrepPackage | None
    disclosure_package: DisclosurePackage | None

    # Conversation
    transcript: list[Turn]  # alternating user/assistant turns with timestamps
    current_agent: str       # which agent is active
    last_user_message: str

    # Judge Mode
    court_phase: CourtPhase | None
    court_transcript: list[Turn] | None

    # Confidence / flags
    flags: list[str]  # e.g. "preliminary_pending_disclosure", "low_confidence_rag"
```

### Memory in Voice Loop

Because the user is **speaking in real time**, the orchestrator must:

1. Append each user turn (ASR transcription) to `transcript` before invoking the agent
2. Pass `transcript[-k:]` (recent window, e.g. k=10) into every agent prompt as conversation history
3. Pass the populated case file (`ticket_details`, `diagnosis`, etc.) into every agent prompt regardless of position in graph — the user shouldn't have to re-say things
4. Append assistant turn (the LLM text response) before TTS streams to the user

### Conversation History Format

Inside agent prompts:

```
## Conversation so far
[user, 14:02:11] I got a ticket from a red light camera last week.
[assistant, 14:02:14] When was it issued? Do you have the date?
[user, 14:02:20] November 18th.
...

## Known case details
- Ticket type: Red light camera (AMPS — post Jan 20 2025)
- Issue date: 2025-11-18
- Intersection: TBD
- Vehicle owner: confirmed self
```

### Redis Schema

```
session:{session_id} → JSON-serialized SessionState (TTL: 24h)
session:{session_id}:lock → mutex for concurrent updates
```

In-memory dict fallback if Redis is not running (dev mode).

---

## 10. Real-Time Voice Pipeline

This is the live conversation loop. Every interaction goes through this.

### Topology

```
Browser mic
   │ (audio PCM via WebSocket)
   ▼
FastAPI WS endpoint  ── streams to ──>  Riva Parakeet ASR
                                            │
                                            ▼ (interim + final transcripts)
                                       Orchestrator
                                            │
                                            ▼ (text response chunks, streamed)
                                       Riva/Magpie TTS
                                            │
                                            ▼ (audio chunks)
                                       Audio2Face-3D NIM
                                            │
                                            ▼ (blendshape values @ ~30fps + audio)
                                       FastAPI WS  ── streams to ──>  Browser
                                                                          │
                                                                          ▼
                                                                  Three.js head + <audio>
```

### Latency Budget

Target end-to-end (end of user speech → start of avatar speech): **<2 seconds**.

Achieve this by:
- **Streaming, not batching.** ASR streams interim → final. Orchestrator starts LLM call on final. LLM streams tokens. TTS streams sentence-by-sentence (split on `.`, `!`, `?`). A2F streams blendshapes as audio arrives.
- **First-sentence kickoff.** Don't wait for full LLM completion to start TTS. As soon as the first complete sentence is generated, push to TTS. The user hears the avatar start speaking while the rest is still being generated.
- **No mid-turn retrieval blocks.** Self-RAG retrievals happen *before* the LLM generation step. If retrieval takes >800ms, prefer Tavily timeout to stalling the avatar.

### WebSocket Message Envelope

All WS messages use this envelope:

```json
{
  "type": "asr_interim | asr_final | agent_text | tts_audio | a2f_blendshapes | state_update | error",
  "session_id": "uuid",
  "seq": 1234,
  "timestamp": "2026-05-30T14:02:14.123Z",
  "payload": { ... }
}
```

### Two Concurrent WS Channels Per Session

1. **Inbound channel** (`/ws/voice/in/{session_id}`) — browser mic → ASR.
2. **Outbound channel** (`/ws/voice/out/{session_id}`) — TTS audio + blendshapes → browser.

Two channels avoid head-of-line blocking when audio is flowing both ways.

### Interruption Handling

If the user starts speaking while the avatar is still talking:
1. ASR detects voice activity → emits `asr_interim` immediately
2. Orchestrator receives interim → cancels in-flight LLM/TTS
3. Browser stops playing audio
4. New ASR final triggers a new turn

Implement using `asyncio.CancelledError` propagation through the pipeline.

---

## 11. API Endpoints

### HTTP (REST)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/session` | Create new session. Returns `session_id`, `mode`. |
| `GET` | `/api/session/{session_id}` | Fetch current `SessionState` (for frontend re-hydration). |
| `DELETE` | `/api/session/{session_id}` | End session. |
| `POST` | `/api/session/{session_id}/upload` | Upload ticket photo. Stored to session-scoped object storage. |
| `GET` | `/api/session/{session_id}/package` | Return the finalized package (whichever was produced). |
| `POST` | `/api/index/rebuild` | Admin: rebuild Chroma index from corpus dir. Optional auth. |
| `GET` | `/api/health` | Liveness check — pings Chroma, Redis, NIM endpoints. |

### WebSocket

| Path | Purpose |
|------|---------|
| `/ws/voice/in/{session_id}` | Inbound audio (browser → backend) |
| `/ws/voice/out/{session_id}` | Outbound audio + blendshapes (backend → browser) |
| `/ws/text/{session_id}` | Text-only fallback channel (no voice). Same orchestrator. |

### Mode Switching

Mode (Lawyer vs Judge) is set at session creation and is **immutable** within a session. To switch, the user creates a new session. This keeps the LangGraph cleanly bounded.

---

## 12. LangGraph Orchestrators

### Lawyer Mode Graph

Nodes (each is one agent invocation):

```
[start]
  → required_info
  → ticket_diagnosis
  → procedure_map
  → user_choice         (conditional edge based on chosen_path)
      ├─ pay            → [end]
      ├─ early_resolution / screening_review / trial:
          → sufficient_data
              ├─ False → disclosure → defence_theory
              └─ True  → defence_theory
          → [end]
```

State is `SessionState`. Persistence is via LangGraph's checkpointer wired to Redis.

### Judge Mode Graph

Linear state machine matching the court procedure. Each state node = one agent invocation; state advances when the agent emits a `phase_complete` signal in its structured output.

```
IDLE → CLERK_CALL_TO_ORDER → CLERK_OATH → JUDGE_OPEN
     → CROWN_OPENING → DEFENCE_OPENING (waits on user)
     → CROWN_CASE → DEFENCE_CROSS_CROWN (waits on user)
     → DEFENCE_CASE (waits on user) → CROWN_CROSS_DEFENCE (waits on user)
     → CROWN_CLOSING → DEFENCE_CLOSING (waits on user)
     → VERDICT → FEEDBACK → [end]
```

"Waits on user" nodes pause the graph and the orchestrator yields control to the WS layer to await the user's spoken response.

---

## 13. Package Schemas (Pydantic)

These are the **deterministic output shapes** the Defence Theory Agent must produce. Use `with_structured_output` on the Nemotron model.

See section 13 of `SYSTEM_PROMPT.md` (or expand later) for the field-level breakdown of:
- `ERPackage` (Early Resolution)
- `ScreeningReviewPackage`
- `TrialPrepPackage`
- `DisclosurePackage`

Every package includes:
- `confidence: Literal["high", "medium", "low"]`
- `is_preliminary: bool` (true if produced before disclosure received)
- `generated_at: datetime`
- `flags: list[str]`

---

## 14. Behavioural Rules

These apply to every agent in the system. Mirror what's in `SYSTEM_PROMPT.md`:

- **Stay in MVP scope.** Red light camera tickets in Ontario only. Reject everything else with a brief redirect.
- **Never guarantee outcomes.** No "you will win." No "strong case."
- **Never advise lying.** Including advising the user to misidentify a driver.
- **Form of address.** "Your Worship" for the JP. Never "Your Honour."
- **Deadlines matter.** Required Info Agent checks the dispute window using current date + ticket date. If past deadline, surface RAG-grounded alternatives.
- **Cite the source.** Defence Theory Agent must include the source filename for any legal claim in its output (used internally; can be hidden from user UI).

---

## 15. Configuration

`.env` (gitignored):

```
NVIDIA_API_KEY=...
TAVILY_API_KEY=...
REDIS_URL=redis://localhost:6379/0
CHROMA_PERSIST_DIR=./backend/data/chroma
CORPUS_DIR=./backend/data/corpus

NIM_LLM_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1
NIM_EMBED_MODEL=nvidia/nv-embedqa-e5-v5
NIM_RERANK_MODEL=nvidia/rerank-qa-mistral-4b

RIVA_ASR_ENDPOINT=grpc://localhost:50051
RIVA_TTS_ENDPOINT=grpc://localhost:50052
A2F_ENDPOINT=grpc://localhost:52000

SESSION_TTL_HOURS=24
MAX_RAG_RETRIES=2
TAVILY_MAX_SOURCES=5
```

`config.py` reads via `pydantic-settings` and exposes a singleton `settings` object.

---

## 16. Testing

- **Unit:** every agent, retriever, critic, indexer chunker.
- **Integration:** full Lawyer Mode graph against a recorded user transcript fixture.
- **Latency:** measure end-to-end voice loop on the hackathon hardware. Anything >2.5s gets investigated.
- **Schema validation:** every package output is Pydantic-validated. Invalid output → automatic retry once → raise.

---

## 17. Things Not in This MVP

Explicit non-goals so no one quietly adds them:

- Any ticket type other than red light camera
- Civil small claims
- Criminal matters
- Hardship/financial relief pathway (decided out of MVP scope)
- Hearing Review (post-Screening-Review escalation)
- Other provinces
- French-language proceedings
- Real submission of disclosure requests or screening review submissions (we produce the script/text; user submits)
- Multi-user collaboration on one case

---

*Prosecuto · Backend Architecture v1.0 · Spark Hack Toronto*
