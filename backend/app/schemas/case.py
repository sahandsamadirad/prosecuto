"""Case-file schemas: ticket intake, diagnosis, conversation turns.

These are the structured shapes the Lawyer Mode agents read and write
(IMPLEMENTATION_PLAN.md Phase 3 / Phase 5). Every field the Required Info Agent
collects lives on ``TicketDetails``; the Ticket Diagnosis Agent emits
``TicketDiagnosis``; the orchestrator records the dialogue as ``Turn``s.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

# --- Enums (as Literals for clean JSON) -----------------------------------

TicketType = Literal["officer_issued", "camera_issued"]

# Camera tickets split on the Jan 20 2025 AMPS cutoff (ARCHITECTURE §5 / Phase 5).
CameraCutoff = Literal["pre_jan_20_2025", "post_jan_20_2025"]

DeadlineStatus = Literal["within_window", "past_deadline", "unknown"]

ChosenPath = Literal["pay", "early_resolution", "screening_review", "trial"]

Role = Literal["user", "assistant"]


class Turn(BaseModel):
    """One conversational turn, user or assistant."""

    role: Role
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    agent: str | None = None  # which agent/character produced an assistant turn


class TicketDetails(BaseModel):
    """The Required Info Agent's checklist. All optional — filled conversationally.

    A field set to ``None`` means "not yet collected"; the agent will not advance
    until everything is populated or explicitly skipped (tracked in ``skipped``).
    """

    ticket_type: TicketType | None = None
    ticket_date: date | None = None
    intersection: str | None = None
    municipality: str | None = None
    vehicle_owner: str | None = None        # who the plate is registered to
    who_was_driving: str | None = None
    ticket_number: str | None = None
    fine_amount: float | None = None
    deadline_date: date | None = None

    # Fields the user explicitly declined to provide (treated as satisfied).
    skipped: list[str] = Field(default_factory=list)

    # The eight checklist fields the intake gate cares about.
    REQUIRED_FIELDS: ClassVar[tuple[str, ...]] = (
        "ticket_type",
        "ticket_date",
        "intersection",
        "vehicle_owner",
        "who_was_driving",
        "ticket_number",
        "fine_amount",
        "deadline_date",
    )

    def missing_fields(self) -> list[str]:
        """Required fields that are neither populated nor explicitly skipped."""
        return [
            f
            for f in self.REQUIRED_FIELDS
            if getattr(self, f) is None and f not in self.skipped
        ]

    def is_complete(self) -> bool:
        return not self.missing_fields()


class TicketDiagnosis(BaseModel):
    """The Ticket Diagnosis Agent's structured classification + recap."""

    type: TicketType
    sub_type: str  # e.g. "amps_camera", "poa_part_i_officer"
    is_red_light_camera: bool  # MVP scope gate (ARCHITECTURE §14/§17)
    camera_cutoff: CameraCutoff | None = None  # only for camera tickets
    deadline_status: DeadlineStatus = "unknown"
    deadline_date: date | None = None
    recap_text: str = ""  # shown back to the user for confirmation


class PathOption(BaseModel):
    """One available path produced by the Procedure Map Agent."""

    path: ChosenPath
    title: str
    description: str
    eligible: bool = True
    notes: str | None = None


class CaseFile(BaseModel):
    """Aggregate view of everything known about the case.

    Convenience bundle threaded into agent prompts so the user never has to
    repeat themselves (ARCHITECTURE §9 "Known case details").
    """

    ticket_details: TicketDetails = Field(default_factory=TicketDetails)
    diagnosis: TicketDiagnosis | None = None
    chosen_path: ChosenPath | None = None
    path_options: list[PathOption] = Field(default_factory=list)
