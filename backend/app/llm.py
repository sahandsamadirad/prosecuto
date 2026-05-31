"""Chat LLM factory — NVIDIA Nemotron Super 49B via LangChain.

ARCHITECTURE.md pins the LLM for the Lawyer, Judge, Prosecutor and every critic
to ``nvidia/llama-3.3-nemotron-super-49b-v1``, accessed through
``langchain-nvidia-ai-endpoints`` (``ChatNVIDIA``). Everything that needs a chat
model — agents and critics — obtains it here so the model name, temperature and
timeout policy live in one place.

``with_structured_output(PydanticModel)`` is used directly on the returned model
for the critics/graders, mirroring the reference Self-RAG ``chains`` pattern.
"""

from __future__ import annotations

import structlog

from app.config import settings

log = structlog.get_logger(__name__)

# Anti-pattern guard from IMPLEMENTATION_PLAN.md: no single LLM call may hang
# the pipeline. Hard per-request timeout.
LLM_TIMEOUT_SECONDS = 10.0


def get_chat_llm(temperature: float = 0.0, **kwargs):
    """Return a ``ChatNVIDIA`` instance for Nemotron Super 49B.

    Args:
        temperature: 0.0 for deterministic critic/structured calls; raise for
            conversational agents that want some variety.
        **kwargs: forwarded to ``ChatNVIDIA`` (e.g. ``max_tokens``).
    """
    from langchain_nvidia_ai_endpoints import ChatNVIDIA

    llm = ChatNVIDIA(
        model=settings.nim_llm_model,
        api_key=settings.nvidia_api_key,
        temperature=temperature,
        timeout=LLM_TIMEOUT_SECONDS,
        **kwargs,
    )
    log.info("llm.selected", model=settings.nim_llm_model, temperature=temperature)
    return llm
