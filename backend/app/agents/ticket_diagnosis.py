"""Ticket Diagnosis Agent — classify the ticket and check the deadline.

Officer-issued vs red light camera; for camera tickets, pre/post Jan 20 2025 AMPS
cutoff; deadline status from the current date; a spoken recap for confirmation.
Uses the retriever for the deadline/AMPS rules (ARCHITECTURE.md section 5/8).
"""

from __future__ import annotations

from datetime import date

from app.agents.base import AgentResult, BaseAgent
from app.orchestrator.state import SessionState
from app.prompts.characters import TICKET_DIAGNOSIS
from app.schemas.case import TicketDiagnosis

# The AMPS cutoff that splits camera-ticket routing.
AMPS_CUTOFF = date(2025, 1, 20)

_HUMAN = """{case}

Current date: {today}

## Retrieved legal sources
{context}

## Conversation so far
{history}

Classify the ticket and assess the deadline. Fill the structured diagnosis, \
including a spoken recap in recap_text grounded in the sources above."""


class TicketDiagnosisAgent(BaseAgent):
    name = "ticket_diagnosis"
    character_prompt = TICKET_DIAGNOSIS

    async def run(self, state: SessionState) -> AgentResult:
        query = "red light camera ticket deadline to dispute and AMPS process Ontario"
        context = await self.retrieve_context(query)

        diagnosis: TicketDiagnosis = await self.run_structured(
            TicketDiagnosis,
            _HUMAN,
            {
                "case": self.format_case(state),
                "today": date.today().isoformat(),
                "context": context,
                "history": self.format_history(state),
            },
        )

        state.diagnosis = diagnosis
        state.current_agent = self.name
        if not diagnosis.is_red_light_camera:
            state.flags.append("out_of_scope_ticket")
        state.touch()

        return AgentResult(
            updated_state=state, assistant_text=diagnosis.recap_text, data=diagnosis
        )
