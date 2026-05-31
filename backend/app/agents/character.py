"""CharacterAgent — shared base for the Judge Mode speaking characters.

The Justice of the Peace, Crown Prosecutor, and Court Clerk all generate
free-text speech appropriate to the current ``court_phase``, using the running
court transcript and case facts as context (ARCHITECTURE.md section 5/12). The
graph node handles appending and phase advancement; the agent only speaks.
"""

from __future__ import annotations

from app.agents.base import AgentResult, BaseAgent
from app.orchestrator.state import CourtPhase, SessionState

_COURT_HUMAN = """Current court phase: {phase}

{case}

## Court proceedings so far
{court}

Speak your part for this phase, in character, as natural courtroom speech (no markdown)."""


class CharacterAgent(BaseAgent):
    """A speaking court character. Produces text for ``state.court_phase``."""

    thinking = False  # scripted speech — no CoT needed

    async def run(self, state: SessionState) -> AgentResult:
        phase = state.court_phase or CourtPhase.IDLE
        text = await self.generate_text(
            _COURT_HUMAN,
            {
                "phase": phase.value,
                "case": self.format_case(state),
                "court": self._court_so_far(state),
            },
        )
        return AgentResult(updated_state=state, assistant_text=text)

    @staticmethod
    def _court_so_far(state: SessionState, k: int = 12) -> str:
        turns = (state.court_transcript or [])[-k:]
        if not turns:
            return "(the trial has not started yet)"
        speaker = {"user": "Defendant", "assistant": None}
        lines = []
        for t in turns:
            who = t.agent or speaker.get(t.role) or t.role
            lines.append(f"[{who}] {t.content}")
        return "\n".join(lines)
