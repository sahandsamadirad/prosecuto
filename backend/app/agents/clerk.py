"""Court Clerk — call to order, oath/affirmation, exhibit handling. No tools."""

from __future__ import annotations

from app.agents.character import CharacterAgent
from app.prompts.characters import COURT_CLERK


class CourtClerkAgent(CharacterAgent):
    name = "court_clerk"
    character_prompt = COURT_CLERK
