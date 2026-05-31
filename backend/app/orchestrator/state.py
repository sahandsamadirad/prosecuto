"""SessionState — the single object threaded through the LangGraph (ARCHITECTURE §9).

Persisted to the session store after every node. Carries the case file, the
conversation transcript, the produced packages, and Judge Mode court state. Every
agent reads recent transcript + the populated case file from here so the user
never has to repeat themselves.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.case import ChosenPath, TicketDetails, TicketDiagnosis, Turn
from app.schemas.packages import (
    DisclosurePackage,
    ERPackage,
    ScreeningReviewPackage,
    TrialPrepPackage,
)

Mode = Literal["lawyer", "judge"]


class CourtPhase(str, Enum):
    """Judge Mode court state machine (ARCHITECTURE §12)."""

    IDLE = "idle"
    QUESTIONING = "questioning"
    FINAL = "final"
    CLERK_CALL_TO_ORDER = "clerk_call_to_order"
    CLERK_OATH = "clerk_oath"
    JUDGE_OPEN = "judge_open"
    CROWN_OPENING = "crown_opening"
    DEFENCE_OPENING = "defence_opening"
    CROWN_CASE = "crown_case"
    DEFENCE_CROSS_CROWN = "defence_cross_crown"
    DEFENCE_CASE = "defence_case"
    CROWN_CROSS_DEFENCE = "crown_cross_defence"
    CROWN_CLOSING = "crown_closing"
    DEFENCE_CLOSING = "defence_closing"
    VERDICT = "verdict"
    FEEDBACK = "feedback"
    DONE = "done"


class SessionState(BaseModel):
    """Full conversational + case state for one session."""

    session_id: str
    mode: Mode
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # --- Case data ---
    ticket_details: TicketDetails | None = None
    diagnosis: TicketDiagnosis | None = None
    chosen_path: ChosenPath | None = None
    disclosure_requested: bool = False
    sufficient_data: bool | None = None

    # --- Outputs ---
    er_package: ERPackage | None = None
    screening_review_package: ScreeningReviewPackage | None = None
    trial_prep_package: TrialPrepPackage | None = None
    disclosure_package: DisclosurePackage | None = None
    uploaded_files: list[str] = Field(default_factory=list)

    # --- Conversation ---
    transcript: list[Turn] = Field(default_factory=list)
    current_agent: str = ""
    last_user_message: str = ""

    # --- Judge Mode ---
    court_phase: CourtPhase | None = None
    court_transcript: list[Turn] | None = None

    # --- Confidence / flags ---
    flags: list[str] = Field(default_factory=list)

    # --- Helpers -----------------------------------------------------------

    def touch(self) -> None:
        self.updated_at = datetime.now()

    def add_turn(self, role, content: str, agent: str | None = None) -> None:
        self.transcript.append(Turn(role=role, content=content, agent=agent))
        if role == "user":
            self.last_user_message = content
        self.touch()

    def recent_transcript(self, k: int = 10) -> list[Turn]:
        """The last ``k`` turns, for the conversation-history window."""
        return self.transcript[-k:]

    def finalized_package(self):
        """Return whichever output package is non-null (ARCHITECTURE §11)."""
        return (
            self.trial_prep_package
            or self.screening_review_package
            or self.er_package
            or self.disclosure_package
        )
