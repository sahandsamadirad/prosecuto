"""Required Info Agent — conversational intake driving a field checklist.

Extracts ticket facts from the conversation and asks for what's still missing.
Will not declare itself complete until every required field is populated or
explicitly skipped (ARCHITECTURE.md section 5 / Phase 5 step 1). No tools.
"""

from __future__ import annotations

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

        details = out.details
        # Merge skip list and recompute completeness deterministically — never
        # trust the model's `complete` flag over the actual checklist.
        merged_skips = sorted(set(details.skipped) | set(out.newly_skipped))
        details.skipped = merged_skips
        state.ticket_details = details
        state.current_agent = self.name
        state.touch()

        return AgentResult(updated_state=state, assistant_text=out.message, data=out)
