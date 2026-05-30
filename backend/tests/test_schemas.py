"""Phase 3 tests: every schema imports, validates, and round-trips JSON."""

from __future__ import annotations

from datetime import date

from app.orchestrator.state import CourtPhase, SessionState
from app.schemas.case import (
    CaseFile,
    PathOption,
    TicketDetails,
    TicketDiagnosis,
    Turn,
)
from app.schemas.messages import TextPayload, WSMessage
from app.schemas.packages import (
    Citation,
    DisclosurePackage,
    ERPackage,
    ScreeningReviewPackage,
    TrialPrepPackage,
)


def _roundtrip(model):
    """Serialize to JSON and back; assert equality."""
    cls = type(model)
    restored = cls.model_validate_json(model.model_dump_json())
    assert restored == model
    return restored


# --- case.py --------------------------------------------------------------


def test_ticket_details_roundtrip_and_completeness():
    td = TicketDetails(ticket_type="camera_issued", ticket_date=date(2025, 11, 18))
    _roundtrip(td)
    assert not td.is_complete()
    assert "intersection" in td.missing_fields()
    assert "ticket_type" not in td.missing_fields()


def test_ticket_details_skip_counts_as_satisfied():
    td = TicketDetails(skipped=["fine_amount"])
    assert "fine_amount" not in td.missing_fields()


def test_required_fields_is_not_a_model_field():
    # ClassVar must not leak into the serialized payload.
    assert "REQUIRED_FIELDS" not in TicketDetails().model_dump()


def test_diagnosis_turn_pathoption_casefile_roundtrip():
    _roundtrip(
        TicketDiagnosis(
            type="camera_issued",
            sub_type="amps_camera",
            is_red_light_camera=True,
            camera_cutoff="post_jan_20_2025",
            deadline_status="within_window",
            recap_text="Red light camera ticket, AMPS.",
        )
    )
    _roundtrip(Turn(role="user", content="hi"))
    _roundtrip(PathOption(path="trial", title="Trial", description="Go to trial"))
    _roundtrip(CaseFile(ticket_details=TicketDetails(ticket_number="ABC123")))


# --- packages.py ----------------------------------------------------------


def test_all_packages_roundtrip_with_envelope():
    cite = Citation(claim="x", source_filename="hta_s144.txt")
    packages = [
        DisclosurePackage(request_text="Please disclose...", diary_date=date(2026, 6, 1)),
        ERPackage(summary="ER summary", confidence="high"),
        ScreeningReviewPackage(summary="SR summary", is_preliminary=True),
        TrialPrepPackage(defence_theory="Theory", citations=[cite]),
    ]
    for pkg in packages:
        restored = _roundtrip(pkg)
        # Common envelope present on all four.
        assert restored.confidence in ("high", "medium", "low")
        assert isinstance(restored.is_preliminary, bool)
        assert restored.generated_at is not None
        assert isinstance(restored.flags, list)


def test_package_kind_discriminator():
    assert ERPackage(summary="s").kind == "early_resolution"
    assert TrialPrepPackage(defence_theory="t").kind == "trial_prep"
    assert DisclosurePackage(request_text="r").kind == "disclosure"
    assert ScreeningReviewPackage(summary="s").kind == "screening_review"


# --- messages.py ----------------------------------------------------------


def test_ws_message_roundtrip_and_make_helper():
    msg = WSMessage.make("agent_text", "sess-1", TextPayload(text="hello", agent="alex"), seq=3)
    restored = _roundtrip(msg)
    assert restored.type == "agent_text"
    assert restored.payload["text"] == "hello"
    assert restored.seq == 3


# --- state.py -------------------------------------------------------------


def test_session_state_roundtrip_and_helpers():
    st = SessionState(session_id="s1", mode="lawyer")
    st.add_turn("user", "I got a red light camera ticket")
    st.add_turn("assistant", "When was it issued?", agent="ticket_diagnosis")
    st.diagnosis = TicketDiagnosis(
        type="camera_issued", sub_type="amps_camera", is_red_light_camera=True
    )
    st.er_package = ERPackage(summary="done")

    restored = _roundtrip(st)
    assert restored.last_user_message == "I got a red light camera ticket"
    assert len(restored.recent_transcript(k=1)) == 1
    assert restored.finalized_package().kind == "early_resolution"


def test_session_state_judge_mode_court_phase():
    st = SessionState(session_id="s2", mode="judge", court_phase=CourtPhase.CLERK_OATH)
    restored = _roundtrip(st)
    assert restored.court_phase == CourtPhase.CLERK_OATH
    assert restored.court_phase.value == "clerk_oath"
