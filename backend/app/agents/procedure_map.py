"""Procedure Map Agent — explain the user's available dispute paths.

Reads the correct sub-tree (officer vs camera) and presents Pay / Early
Resolution / Screening Review / Trial with plain explanations, then invites a
choice (ARCHITECTURE.md section 5 / Phase 5 step 3). Uses the retriever.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import AgentResult, BaseAgent
from app.orchestrator.state import SessionState
from app.prompts.characters import PROCEDURE_MAP
from app.schemas.case import PathOption

_HUMAN = """{case}

## Retrieved procedure sources
{context}

## Conversation so far
{history}

List the dispute paths that apply to this ticket with a short plain explanation of \
each, mark which are available, and in the message invite the user to choose."""


class ProcedureMapOutput(BaseModel):
    options: list[PathOption] = Field(description="The applicable dispute paths.")
    message: str = Field(description="Spoken explanation inviting the user to choose.")


class ProcedureMapAgent(BaseAgent):
    name = "procedure_map"
    character_prompt = PROCEDURE_MAP

    async def run(self, state: SessionState) -> AgentResult:
        context = self.retrieve_context(
            "options to dispute a red light camera ticket: pay, early resolution, "
            "screening review, trial — Ontario procedure"
        )
        out: ProcedureMapOutput = await self.run_structured(
            ProcedureMapOutput,
            _HUMAN,
            {
                "case": self.format_case(state),
                "context": context,
                "history": self.format_history(state),
            },
        )
        state.current_agent = self.name
        state.touch()
        return AgentResult(updated_state=state, assistant_text=out.message, data=out)
