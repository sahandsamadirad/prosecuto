"""Chat LLM factory — local vLLM serving NVFP4 Nemotron Super on GX10.

All inference runs through the OpenAI-compatible vLLM endpoint at
LOCAL_LLM_ENDPOINT (default http://localhost:8001/v1). No cloud fallback.

Thinking toggle: Nemotron Super supports /no_think in the system prompt to
skip chain-of-thought reasoning tokens. BaseAgent.system_prompt injects this
prefix for agents where thinking=False, so no extra param is needed here.
"""

from __future__ import annotations

import structlog
from langchain_openai import ChatOpenAI

from app.config import settings

log = structlog.get_logger(__name__)


def get_chat_llm(temperature: float = 0.0, **kwargs) -> ChatOpenAI:
    """Return a ChatOpenAI instance pointed at the local vLLM endpoint.

    Args:
        temperature: 0.0 for deterministic critic/structured calls; higher for
            conversational agents that benefit from some variety.
        **kwargs: forwarded to ChatOpenAI (e.g. max_tokens, streaming).
    """
    llm = ChatOpenAI(
        model=settings.local_llm_model,
        base_url=settings.local_llm_endpoint,
        api_key=settings.local_llm_api_key,
        temperature=temperature,
        timeout=settings.llm_timeout_seconds,
        **kwargs,
    )
    log.info(
        "llm.selected",
        model=settings.local_llm_model,
        endpoint=settings.local_llm_endpoint,
        temperature=temperature,
    )
    return llm
