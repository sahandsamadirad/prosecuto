"""Judge Mode tests: a single judge runs a question/answer mock hearing."""

from __future__ import annotations

from app.agents.base import AgentResult
from app.orchestrator.graph_judge import (
    MAX_JUDGE_ANSWERS,
    JudgeCharacters,
    astream_court_turn,
    build_judge_graph,
)
from app.orchestrator.state import CourtPhase, SessionState


class FakeJudge:
    name = "judge"

    async def run(self, state: SessionState) -> AgentResult:
        return AgentResult(
            updated_state=state,
            assistant_text=f"judge speaking at {state.court_phase.value}",
        )


def _graph():
    from langgraph.checkpoint.memory import MemorySaver

    return build_judge_graph(JudgeCharacters(judge=FakeJudge()), MemorySaver())


def _session():
    return SessionState(
        session_id="trial1", mode="judge", court_phase=CourtPhase.IDLE, court_transcript=[]
    )


async def _drive(graph, session, msg=None):
    out = []
    async for speaker, text, _ in astream_court_turn(graph, session, msg):
        out.append((speaker, text))
    return out


async def test_judge_opens_with_one_question_then_waits():
    graph = _graph()
    s = _session()

    t = await _drive(graph, s)

    assert [sp for sp, _ in t] == ["judge"]
    assert "questioning" in t[0][1]
    assert s.court_phase == CourtPhase.QUESTIONING


async def test_judge_asks_once_per_user_answer_then_finalizes():
    graph = _graph()
    s = _session()
    await _drive(graph, s)

    for idx in range(MAX_JUDGE_ANSWERS - 1):
        t = await _drive(graph, s, f"My answer {idx + 1}.")
        assert [sp for sp, _ in t] == ["judge"]
        assert "questioning" in t[0][1]
        assert s.court_phase == CourtPhase.QUESTIONING

    t = await _drive(graph, s, "My final answer.")
    assert [sp for sp, _ in t] == ["judge"]
    assert "final" in t[0][1]
    assert s.court_phase == CourtPhase.DONE


async def test_user_can_request_finish_early():
    graph = _graph()
    s = _session()
    await _drive(graph, s)

    t = await _drive(graph, s, "Please finish and give final feedback.")

    assert [sp for sp, _ in t] == ["judge"]
    assert "final" in t[0][1]
    assert s.court_phase == CourtPhase.DONE


async def test_court_transcript_records_judge_and_user():
    graph = _graph()
    s = _session()
    await _drive(graph, s)
    await _drive(graph, s, "My answer.")

    assert any(t.role == "assistant" and t.agent == "judge" for t in s.court_transcript)
    assert any(t.role == "user" and t.agent == "defence" for t in s.court_transcript)
    assert len(s.transcript) == len(s.court_transcript)


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
    await _drive(graph1, s)

    reloaded = SessionState.model_validate_json(s.model_dump_json())
    graph2 = _graph()
    t = await _drive(graph2, reloaded, "My defence, Your Worship.")

    assert [sp for sp, _ in t] == ["judge"]
    assert reloaded.court_phase == CourtPhase.QUESTIONING
