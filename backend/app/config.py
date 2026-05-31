"""Central configuration for Prosecuto backend.

All inference runs locally on the GX10 via vLLM (NVFP4 Nemotron Super).
No cloud LLM/embedding/reranking calls — Tavily is the only external API.

Import the singleton, never re-instantiate ``Settings`` directly::

    from app.config import settings
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- External API keys (Tavily only — all LLM inference is local) --------
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")

    # --- Infra endpoints ------------------------------------------------------
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

    # --- Local vLLM (NVFP4 Nemotron Super on GX10 GB10) ----------------------
    local_llm_endpoint: str = Field(
        default="http://localhost:8001/v1", alias="LOCAL_LLM_ENDPOINT"
    )
    local_llm_model: str = Field(
        default="nvidia/Llama-3_3-Nemotron-Super-49B-v1_5-NVFP4",
        alias="LOCAL_LLM_MODEL",
    )
    local_llm_api_key: str = Field(default="password", alias="LOCAL_LLM_API_KEY")
    llm_timeout_seconds: float = Field(default=120.0, alias="LLM_TIMEOUT_SECONDS")

    # --- Local embedding model (sentence-transformers, runs on GPU) -----------
    local_embed_model: str = Field(
        default="BAAI/bge-large-en-v1.5", alias="LOCAL_EMBED_MODEL"
    )

    # --- Voice / avatar gRPC endpoints ----------------------------------------
    riva_asr_endpoint: str = Field(
        default="grpc://localhost:50051", alias="RIVA_ASR_ENDPOINT"
    )
    riva_tts_endpoint: str = Field(
        default="grpc://localhost:50052", alias="RIVA_TTS_ENDPOINT"
    )
    a2f_endpoint: str = Field(default="grpc://localhost:52000", alias="A2F_ENDPOINT")

    # --- Behavioural knobs ----------------------------------------------------
    session_ttl_hours: int = Field(default=24, alias="SESSION_TTL_HOURS")
    max_rag_retries: int = Field(default=2, alias="MAX_RAG_RETRIES")
    tavily_max_sources: int = Field(default=5, alias="TAVILY_MAX_SOURCES")
    graph_runtime: str = Field(default="fast_ai", alias="PROSECUTO_GRAPH_RUNTIME")
    chroma_collection: str = Field(default="prosecuto", alias="CHROMA_COLLECTION")
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
    return Settings()


settings = get_settings()
