"""Phase 10 tests: the Judge Mode court state machine.

Fake characters return deterministic per-phase text so the test exercises the
state machine — phase ordering, wait-on-user pauses, the crown-cross pause, and
the verdict→feedback tail — not the LLM. Covers Phase 10 "done when": a full
mock trial runs from call-to-order to feedback with the right speaker each beat.
"""

from __future__ import annotations

from app.agents.base import AgentResult
from app.orchestrator.graph_judge import (
    JudgeCharacters,
    astream_court_turn,
    build_judge_graph,
)
from app.orchestrator.state import CourtPhase, SessionState


class FakeChar:
    def __init__(self, name):
        self.name = name

    async def run(self, state: SessionState) -> AgentResult:
        return AgentResult(
            updated_state=state,
            assistant_text=f"{self.name} speaking at {state.court_phase.value}",
        )


def _graph():
    from langgraph.checkpoint.memory import MemorySaver

    chars = JudgeCharacters(
        clerk=FakeChar("court_clerk"),
        judge=FakeChar("judge"),
        prosecutor=FakeChar("crown_prosecutor"),
    )
    return build_judge_graph(chars, MemorySaver())


def _session():
    return SessionState(
        session_id="trial1", mode="judge", court_phase=CourtPhase.IDLE, court_transcript=[]
    )


async def _drive(graph, session, msg=None):
    out = []
    async for speaker, text, _ in astream_court_turn(graph, session, msg):
        out.append((speaker, text))
    return out


async def test_full_mock_trial_runs_to_feedback():
    graph = _graph()
    s = _session()

    # Opening run: clerk, clerk, judge, crown → pause at DEFENCE_OPENING.
    t = await _drive(graph, s)
    assert [sp for sp, _ in t] == ["court_clerk", "court_clerk", "judge", "crown_prosecutor"]
    assert s.court_phase == CourtPhase.DEFENCE_OPENING

    # Defendant opens → CROWN_CASE → pause at DEFENCE_CROSS_CROWN.
    t = await _drive(graph, s, "My opening statement, Your Worship.")
    assert [sp for sp, _ in t] == ["crown_prosecutor"]
    assert s.court_phase == CourtPhase.DEFENCE_CROSS_CROWN

    # Defendant cross-examines → next beat is DEFENCE_CASE (also user) → no speech.
    t = await _drive(graph, s, "Officer, was the camera calibrated?")
    assert t == []
    assert s.court_phase == CourtPhase.DEFENCE_CASE

    # Defendant presents case → crown cross-examines, then pauses for the answer.
    t = await _drive(graph, s, "Here is my account of events.")
    assert [sp for sp, _ in t] == ["crown_prosecutor"]
    assert s.court_phase == CourtPhase.CROWN_CLOSING  # advanced past the cross

    # Defendant answers the cross → CROWN_CLOSING → pause at DEFENCE_CLOSING.
    t = await _drive(graph, s, "I was not the driver that day.")
    assert [sp for sp, _ in t] == ["crown_prosecutor"]
    assert s.court_phase == CourtPhase.DEFENCE_CLOSING

    # Defendant closes → VERDICT then FEEDBACK (judge breaks character) → DONE.
    t = await _drive(graph, s, "In closing, the Crown has not met its burden.")
    assert [sp for sp, _ in t] == ["judge", "judge"]
    assert "verdict" in t[0][1]
    assert "feedback" in t[1][1]
    assert s.court_phase == CourtPhase.DONE


async def test_court_transcript_records_both_sides():
    graph = _graph()
    s = _session()
    await _drive(graph, s)
    await _drive(graph, s, "My opening, Your Worship.")

    # Defendant words land in court_transcript tagged 'defence'.
    user_turns = [t for t in s.court_transcript if t.role == "user"]
    assert any(t.agent == "defence" and "opening" in t.content.lower() for t in user_turns)
    # And character beats are recorded too.
    assert any(t.role == "assistant" and t.agent == "court_clerk" for t in s.court_transcript)
    # Overall transcript mirrors the proceedings.
    assert len(s.transcript) >= len(s.court_transcript) - 0


async def test_finished_trial_yields_nothing():
    graph = _graph()
    s = _session()
    s.court_phase = CourtPhase.DONE
    assert await _drive(graph, s, "anything") == []


def test_to_speech_strips_markdown_for_voice():
    from app.agents.base import to_speech

    out = to_speech("**Your Worship**\n\n## Opening\n- a\n- b\nThe `cert` is in.")
    assert "**" not in out and "##" not in out and "`" not in out
    assert "Your Worship" in out and "cert" in out


async def test_resume_trial_from_reloaded_state():
    graph1 = _graph()
    s = _session()
    await _drive(graph1, s)  # advance to DEFENCE_OPENING

    reloaded = SessionState.model_validate_json(s.model_dump_json())
    graph2 = _graph()
    t = await _drive(graph2, reloaded, "My opening.")
    assert [sp for sp, _ in t] == ["crown_prosecutor"]
    assert reloaded.court_phase == CourtPhase.DEFENCE_CROSS_CROWN
