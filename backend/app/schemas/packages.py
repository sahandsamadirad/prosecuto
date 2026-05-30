"""Output package schemas — the deterministic shapes the Defence Theory and
Disclosure agents produce via ``with_structured_output`` (ARCHITECTURE §13).

Four packages:
* ``DisclosurePackage``      — formal disclosure request (Stinchcombe).
* ``ERPackage``             — Early Resolution prep.
* ``ScreeningReviewPackage`` — Screening Review prep.
* ``TrialPrepPackage``      — full trial preparation.

Every package carries the common envelope: ``confidence``, ``is_preliminary``,
``generated_at``, ``flags``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]


class Citation(BaseModel):
    """A legal claim tied to its corpus source (ARCHITECTURE §14 'Cite the source').

    Used internally; can be hidden from the user-facing UI.
    """

    claim: str
    source_filename: str
    source_path: str | None = None
    quote: str | None = None


class PackageBase(BaseModel):
    """Common envelope on every produced package."""

    confidence: Confidence = "medium"
    is_preliminary: bool = False  # True when produced before disclosure received
    generated_at: datetime = Field(default_factory=datetime.now)
    flags: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class DisclosurePackage(PackageBase):
    """Formal disclosure request script + submission instructions."""

    kind: Literal["disclosure"] = "disclosure"
    request_text: str  # the formal request the user submits
    itemized_requests: list[str] = Field(default_factory=list)
    submission_instructions: str = ""
    diary_date: date | None = None  # follow-up date to refresh the package


class ERPackage(PackageBase):
    """Early Resolution package — meeting with the prosecutor."""

    kind: Literal["early_resolution"] = "early_resolution"
    summary: str
    defence_grounds: list[str] = Field(default_factory=list)
    mitigation_points: list[str] = Field(default_factory=list)
    proposed_resolution: str = ""
    talking_points: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class ScreeningReviewPackage(PackageBase):
    """Screening Review package — administrative review of a camera AMPS penalty."""

    kind: Literal["screening_review"] = "screening_review"
    summary: str
    grounds_for_review: list[str] = Field(default_factory=list)
    supporting_arguments: list[str] = Field(default_factory=list)
    requested_outcome: str = ""  # cancel / reduce / extend time to pay
    talking_points: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class TrialPrepPackage(PackageBase):
    """Full trial preparation package."""

    kind: Literal["trial_prep"] = "trial_prep"
    defence_theory: str
    legal_arguments: list[str] = Field(default_factory=list)
    evidence_challenges: list[str] = Field(default_factory=list)
    cross_examination_questions: list[str] = Field(default_factory=list)
    witness_notes: list[str] = Field(default_factory=list)
    anticipated_crown_evidence: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


# Union of every producible package (handy for typing / serialization).
AnyPackage = (
    DisclosurePackage | ERPackage | ScreeningReviewPackage | TrialPrepPackage
)
