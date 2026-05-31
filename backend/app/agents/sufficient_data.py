"""Sufficient Data Check — internal gate before building a defence package.

Two steps (ARCHITECTURE.md section 5 / Phase 5 step 4), BOTH must pass:
  (a) rule-based — are all required ticket fields populated/skipped?
  (b) LLM judgment — is there enough substantive content for a real defence?

Not a speaking agent; its text is an internal transition note. No tools.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import AgentResult, BaseAgent
from app.orchestrator.state import SessionState
from app.prompts.characters import SUFFICIENT_DATA
from app.schemas.case import TicketDetails

_HUMAN = """{case}

## Conversation so far
{history}

Judge whether there is enough SUBSTANTIVE content (a genuine factual or legal angle) \
to build a real defence. Return sufficient and a brief reason."""


class SufficientDataOutput(BaseModel):
    sufficient: bool = Field(description="True if there's enough to build a defence on.")
    reason: str = Field(description="Brief justification.")


class SufficientDataAgent(BaseAgent):
    name = "sufficient_data"
    character_prompt = SUFFICIENT_DATA

    async def run(self, state: SessionState) -> AgentResult:
        td = state.ticket_details or TicketDetails()

        # Step (a): rule-based completeness.
        fields_complete = td.is_complete()

        # Step (b): LLM substantive judgment.
        out: SufficientDataOutput = await self.run_structured(
            SufficientDataOutput,
            _HUMAN,
            {"case": self.format_case(state), "history": self.format_history(state)},
        )

        sufficient = fields_complete and out.sufficient
        state.sufficient_data = sufficient
        state.current_agent = self.name
        if not sufficient and not fields_complete:
            reason = f"Missing required fields: {', '.join(td.missing_fields())}. {out.reason}"
        else:
            reason = out.reason
        state.touch()

        return AgentResult(updated_state=state, assistant_text=reason, data=out)
