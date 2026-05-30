"""Disclosure Request Agent — produce a formal disclosure request package.

Activated when Sufficient Data = False or the user asks for it. Generates the
formal request script + itemized items + submission instructions + diary date,
grounded in disclosure/Stinchcombe sources (ARCHITECTURE.md section 5/8). Flags
the eventual package as preliminary until disclosure is received.
"""

from __future__ import annotations

from app.agents.base import AgentResult, BaseAgent
from app.orchestrator.state import SessionState
from app.prompts.characters import DISCLOSURE
from app.schemas.packages import DisclosurePackage

_HUMAN = """{case}

## Retrieved disclosure sources
{context}

## Conversation so far
{history}

Produce the disclosure request package: a formal request_text, itemized_requests, \
submission_instructions, and a diary_date. Cite source filenames for any legal basis."""


class DisclosureRequestAgent(BaseAgent):
    name = "disclosure"
    character_prompt = DISCLOSURE

    async def run(self, state: SessionState) -> AgentResult:
        context = self.retrieve_context(
            "Crown disclosure obligations Stinchcombe red light camera evidence "
            "certificate maintenance records Ontario"
        )
        package: DisclosurePackage = await self.run_structured(
            DisclosurePackage,
            _HUMAN,
            {
                "case": self.format_case(state),
                "context": context,
                "history": self.format_history(state),
            },
        )
        # This is a request, so any downstream defence package is preliminary.
        if "preliminary_pending_disclosure" not in package.flags:
            package.flags.append("preliminary_pending_disclosure")

        state.disclosure_package = package
        state.disclosure_requested = True
        state.current_agent = self.name
        state.touch()

        msg = (
            "I've prepared a formal disclosure request for you to submit. Once you receive "
            "the evidence, we'll refine your package — until then it stays preliminary."
        )
        return AgentResult(updated_state=state, assistant_text=msg, data=package)
