"""Crown Prosecutor — tenders red light camera evidence, cross-examines, closes."""

from __future__ import annotations

from app.agents.character import CharacterAgent
from app.prompts.characters import CROWN_PROSECUTOR


class CrownProsecutorAgent(CharacterAgent):
    name = "crown_prosecutor"
    character_prompt = CROWN_PROSECUTOR
