"""Justice of the Peace — opens, rules, delivers verdict, then coaches in feedback."""

from __future__ import annotations

from app.agents.character import CharacterAgent
from app.prompts.characters import JUDGE_JP


class JudgeAgent(CharacterAgent):
    name = "judge"
    character_prompt = JUDGE_JP
