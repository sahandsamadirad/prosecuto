"""Central configuration for Prosecuto backend.

Reads every environment variable from ARCHITECTURE.md section 15 via
``pydantic-settings`` and exposes a single cached ``settings`` object.

Import the singleton, never re-instantiate ``Settings`` directly::

    from app.config import settings
    print(settings.nim_llm_model)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor default data paths to the `backend/` dir (parent of `app/`) so they
# resolve the same regardless of the process working directory. An explicit
# CHROMA_PERSIST_DIR / CORPUS_DIR in the environment always wins.
_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """All runtime configuration. Values come from the environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Secrets / external API keys -------------------------------------
    nvidia_api_key: str = Field(default="", alias="NVIDIA_API_KEY")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")

    # --- Infra endpoints --------------------------------------------------
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    chroma_persist_dir: str = Field(
        default=str(_BACKEND_DIR / "data" / "chroma"), alias="CHROMA_PERSIST_DIR"
    )
    corpus_dir: str = Field(
        default=str(_BACKEND_DIR / "data" / "corpus"), alias="CORPUS_DIR"
    )
    uploads_dir: str = Field(
        default=str(_BACKEND_DIR / "data" / "uploads"), alias="UPLOADS_DIR"
    )

    # --- NVIDIA NIM model names ------------------------------------------
    nim_llm_model: str = Field(
        default="nvidia/llama-3.3-nemotron-super-49b-v1", alias="NIM_LLM_MODEL"
    )
    nim_embed_model: str = Field(
        default="nvidia/nv-embedqa-e5-v5", alias="NIM_EMBED_MODEL"
    )
    # Hosted model id for the spec's "nvidia/rerank-qa-mistral-4b".
    nim_rerank_model: str = Field(
        default="nv-rerank-qa-mistral-4b:1", alias="NIM_RERANK_MODEL"
    )

    # --- Voice / avatar gRPC endpoints -----------------------------------
    riva_asr_endpoint: str = Field(
        default="grpc://localhost:50051", alias="RIVA_ASR_ENDPOINT"
    )
    riva_tts_endpoint: str = Field(
        default="grpc://localhost:50052", alias="RIVA_TTS_ENDPOINT"
    )
    a2f_endpoint: str = Field(default="grpc://localhost:52000", alias="A2F_ENDPOINT")

    # --- Local LLM (llama-server alternative to NVIDIA NIM) --------------
    # LLM_PROVIDER: "nvidia" | "local" | "auto"
    # "auto" uses local when LOCAL_LLM_ENDPOINT is set, otherwise falls back to nvidia.
    llm_provider: str = Field(default="auto", alias="LLM_PROVIDER")
    local_llm_endpoint: str = Field(default="", alias="LOCAL_LLM_ENDPOINT")
    local_llm_model: str = Field(default="qwen3.6-35b", alias="LOCAL_LLM_MODEL")
    local_llm_api_key: str = Field(default="password", alias="LOCAL_LLM_API_KEY")
    # Timeout in seconds — 10s is fine for cloud NIM; local 35B needs more headroom.
    llm_timeout_seconds: float = Field(default=30.0, alias="LLM_TIMEOUT_SECONDS")

    # --- Behavioural knobs ------------------------------------------------
    session_ttl_hours: int = Field(default=24, alias="SESSION_TTL_HOURS")
    max_rag_retries: int = Field(default=2, alias="MAX_RAG_RETRIES")
    tavily_max_sources: int = Field(default=5, alias="TAVILY_MAX_SOURCES")
    graph_runtime: str = Field(default="fast_ai", alias="PROSECUTO_GRAPH_RUNTIME")

    # --- Collection name (not in .env spec but needed everywhere) --------
    chroma_collection: str = Field(default="prosecuto", alias="CHROMA_COLLECTION")

    # --- Admin auth for /api/index/rebuild -------------------------------
    admin_token: str = Field(default="", alias="ADMIN_TOKEN")

    @property
    def chroma_path(self) -> Path:
        return Path(self.chroma_persist_dir).resolve()

    @property
    def corpus_path(self) -> Path:
        return Path(self.corpus_dir).resolve()

    @property
    def uploads_path(self) -> Path:
        return Path(self.uploads_dir).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor so the env is parsed exactly once per process."""
    return Settings()


# Module-level singleton, imported across the codebase.
settings = get_settings()
