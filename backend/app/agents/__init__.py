"""Lawyer Mode agents (and Judge Mode characters in Phase 10)."""

from app.agents.base import AgentResult, BaseAgent
from app.agents.defence_theory import DefenceTheoryAgent
from app.agents.disclosure import DisclosureRequestAgent
from app.agents.procedure_map import ProcedureMapAgent
from app.agents.required_info import RequiredInfoAgent
from app.agents.sufficient_data import SufficientDataAgent
from app.agents.ticket_diagnosis import TicketDiagnosisAgent

__all__ = [
    "AgentResult",
    "BaseAgent",
    "RequiredInfoAgent",
    "TicketDiagnosisAgent",
    "ProcedureMapAgent",
    "SufficientDataAgent",
    "DisclosureRequestAgent",
    "DefenceTheoryAgent",
]
