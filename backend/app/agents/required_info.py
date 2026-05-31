"""Required Info Agent — conversational intake driving a field checklist.

Extracts ticket facts from the conversation and asks for what's still missing.
Will not declare itself complete until every required field is populated or
explicitly skipped (ARCHITECTURE.md section 5 / Phase 5 step 1). No tools.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field

from app.agents.base import AgentResult, BaseAgent
from app.orchestrator.state import SessionState
from app.prompts.characters import REQUIRED_INFO
from app.schemas.case import TicketDetails

_HUMAN = """{case}

## Conversation so far
{history}

Update the ticket details from everything said so far, then ask about the next \
missing fact(s). The latest user message is: "{last_user}"."""


class RequiredInfoOutput(BaseModel):
    """Structured result of one intake turn."""

    details: TicketDetails = Field(description="All ticket facts gathered so far.")
    newly_skipped: list[str] = Field(
        default_factory=list, description="Required fields the user declined or doesn't know."
    )
    message: str = Field(description="What the avatar should say next (a question or wrap-up).")
    complete: bool = Field(description="True once all required fields are filled or skipped.")


class RequiredInfoAgent(BaseAgent):
    name = "required_info"
    character_prompt = REQUIRED_INFO
    thinking = False  # form field extraction — no CoT needed

    async def run(self, state: SessionState) -> AgentResult:
        out: RequiredInfoOutput = await self.run_structured(
            RequiredInfoOutput,
            _HUMAN,
            {
                "case": self.format_case(state),
                "history": self.format_history(state),
                "last_user": state.last_user_message,
            },
        )

        details = _supported_details(state, out.details)
        # Merge skip list and recompute completeness deterministically — never
        # trust the model's `complete` flag over the actual checklist.
        merged_skips = sorted(set(details.skipped) | set(_supported_skips(state, out.newly_skipped)))
        details.skipped = merged_skips
        state.ticket_details = details
        state.current_agent = self.name
        state.touch()

        return AgentResult(updated_state=state, assistant_text=out.message, data=out)


def _evidence_text(state: SessionState) -> str:
    return " ".join(t.content for t in state.transcript if t.role == "user").lower()


def _tokens(value: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", value.lower()) if len(t) >= 2]


def _supported_string(evidence: str, value: str | None) -> str | None:
    if not value:
        return None
    tokens = _tokens(value)
    if not tokens:
        return None
    hits = sum(1 for token in tokens if token in evidence)
    return value if hits >= min(len(tokens), 2) else None


def _supported_date(evidence: str, value: date | None) -> date | None:
    if value is None:
        return None
    year = str(value.year)
    month = value.strftime("%B").lower()
    short_month = value.strftime("%b").lower()
    day = str(value.day)
    iso = value.isoformat()
    return value if iso in evidence or (year in evidence and day in evidence and (month in evidence or short_month in evidence)) else None


def _supported_amount(evidence: str, value: float | None) -> float | None:
    if value is None:
        return None
    as_int = str(int(value)) if value == int(value) else str(value)
    return value if as_int in evidence else None


def _supported_details(state: SessionState, proposed: TicketDetails) -> TicketDetails:
    existing = state.ticket_details or TicketDetails()
    evidence = _evidence_text(state)

    merged = existing.model_copy(deep=True)
    if proposed.ticket_type and merged.ticket_type is None:
        if proposed.ticket_type == "camera_issued" and ("camera" in evidence or "red light" in evidence):
            merged.ticket_type = proposed.ticket_type
        elif proposed.ticket_type == "officer_issued" and "officer" in evidence:
            merged.ticket_type = proposed.ticket_type

    for field in ("intersection", "municipality", "vehicle_owner", "who_was_driving", "ticket_number"):
        if getattr(merged, field) is None:
            setattr(merged, field, _supported_string(evidence, getattr(proposed, field)))

    if merged.ticket_date is None:
        merged.ticket_date = _supported_date(evidence, proposed.ticket_date)
    if merged.deadline_date is None:
        merged.deadline_date = _supported_date(evidence, proposed.deadline_date)
    if merged.fine_amount is None:
        merged.fine_amount = _supported_amount(evidence, proposed.fine_amount)

    return merged


def _supported_skips(state: SessionState, proposed: list[str]) -> list[str]:
    evidence = _evidence_text(state)
    if not any(phrase in evidence for phrase in ("don't know", "do not know", "not sure", "skip", "refuse")):
        return []
    return proposed
