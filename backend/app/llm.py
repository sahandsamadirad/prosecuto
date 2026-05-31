"""Chat LLM factory — NVIDIA Nemotron Super 49B via NIM, or local llama-server.

``LLM_PROVIDER`` controls which backend is used:
  - ``"nvidia"``  — always use NVIDIA NIM (ChatNVIDIA, requires NVIDIA_API_KEY)
  - ``"local"``   — always use the llama-server at LOCAL_LLM_ENDPOINT (OpenAI-compat API)
  - ``"auto"``    — use local when LOCAL_LLM_ENDPOINT is set, otherwise nvidia

The per-request timeout is now ``LLM_TIMEOUT_SECONDS`` (default 30 s); 10 s was
fine for the low-latency NIM cloud but is too tight for local 35B inference.
"""

from __future__ import annotations

import structlog

from app.config import settings

log = structlog.get_logger(__name__)


def get_chat_llm(temperature: float = 0.0, thinking: bool = True, **kwargs):
    """Return a chat LLM instance routed to the configured provider.

    Args:
        temperature: 0.0 for deterministic critic/structured calls; raise for
            conversational agents that want some variety.
        thinking: When False, disables chain-of-thought reasoning tokens on
            Nemotron Super. Use for scripted/form-filling agents to skip the
            200-800 token CoT overhead. Ignored on the NIM cloud path.
        **kwargs: forwarded to the underlying LangChain class.
    """
    use_local = (
        settings.llm_provider == "local"
        or (settings.llm_provider == "auto" and bool(settings.local_llm_endpoint))
    )

    if use_local:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.local_llm_model,
            base_url=settings.local_llm_endpoint,
            api_key="local",
            temperature=temperature,
            timeout=settings.llm_timeout_seconds,
            **kwargs,
        )
        log.info(
            "llm.selected",
            provider="local",
            model=settings.local_llm_model,
            endpoint=settings.local_llm_endpoint,
            temperature=temperature,
            thinking=thinking,
        )
        return llm

    from langchain_nvidia_ai_endpoints import ChatNVIDIA

    llm = ChatNVIDIA(
        model=settings.nim_llm_model,
        api_key=settings.nvidia_api_key,
        temperature=temperature,
        timeout=settings.llm_timeout_seconds,
        **kwargs,
    )
    log.info(
        "llm.selected",
        provider="nvidia",
        model=settings.nim_llm_model,
        temperature=temperature,
    )
    return llm
