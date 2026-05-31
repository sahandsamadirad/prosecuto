"""Phase 5 tests: the six Lawyer Mode agents.

All offline — the LLM, retriever, and critics are faked. Covers Phase 5
"done when": each agent verified in isolation against a SessionState fixture,
plus one end-to-end scripted walk through all six agents producing a package.
"""

from __future__ import annotations

from datetime import date

import pytest
from langchain_core.runnables import RunnableLambda

from app.agents.defence_theory import DefenceTheoryAgent
from app.agents.disclosure import DisclosureRequestAgent
from app.agents.procedure_map import ProcedureMapAgent, ProcedureMapOutput
from app.agents.required_info import RequiredInfoAgent, RequiredInfoOutput
from app.agents.sufficient_data import SufficientDataAgent, SufficientDataOutput
from app.agents.ticket_diagnosis import TicketDiagnosisAgent
from app.orchestrator.state import SessionState
from app.rag.critic import AdequacyGrade, GroundingGrade, RelevanceGrade
from app.rag.results import Passage, RetrievalResult
from app.schemas.case import PathOption, TicketDetails, TicketDiagnosis
from app.schemas.packages import DisclosurePackage, ERPackage


# --- Fakes ----------------------------------------------------------------


class FakeLLM:
    """`with_structured_output(Model)` → Runnable returning a scripted instance."""

    def __init__(self, outputs: dict):
        self.outputs = outputs  # {model_cls: instance}

    def with_structured_output(self, model):
        value = self.outputs[model]
        return RunnableLambda(lambda _: value)


class FakeRetriever:
    def __init__(self, passages, source="rag"):
        self._passages = passages
        self._source = source

    def retrieve(self, query, k=8, n=4, filters=None):
        return RetrievalResult(
            query=query,
            passages=self._passages,
            scores=[p.score or 0.0 for p in self._passages],
            source=self._source,
        )

    async def aretrieve(self, query, k=8, n=4, filters=None):
        return self.retrieve(query, k=k, n=n, filters=filters)

    def _tavily_result(self, query):
        return RetrievalResult(query=query, passages=[], source="none")

    async def atavily_result(self, query):
        return self._tavily_result(query)


class FakeCritics:
    def grade_relevance(self, q, p):
        return RelevanceGrade(relevant=True, reason="")

    async def agrade_relevance(self, q, p):
        return self.grade_relevance(q, p)

    def grade_grounding(self, a, ps):
        return GroundingGrade(grounded=True, unsupported_claims=[])

    async def agrade_grounding(self, a, ps):
        return self.grade_grounding(a, ps)

    def grade_adequacy(self, q, a):
        return AdequacyGrade(adequate=True, missing=[])

    async def agrade_adequacy(self, q, a):
        return self.grade_adequacy(q, a)


def _passages():
    return [
        Passage(content="O. Reg. 277/99 requires a certificate...", filename="oreg277.txt",
                source_path="oreg277.txt", score=0.9),
        Passage(content="HTA s.144 red light offence...", filename="hta.txt",
                source_path="hta.txt", score=0.8),
    ]


def _state(mode="lawyer", **kw) -> SessionState:
    st = SessionState(session_id="s1", mode=mode)
    st.add_turn("user", "I got a red light camera ticket on Nov 18")
    for k, v in kw.items():
        setattr(st, k, v)
    return st


# --- Per-agent unit tests -------------------------------------------------


async def test_required_info_agent_merges_details_and_skips():
    out = RequiredInfoOutput(
        details=TicketDetails(ticket_type="camera_issued", ticket_date=date(2025, 11, 18)),
        newly_skipped=["fine_amount"],
        message="What intersection was it at?",
        complete=False,
    )
    agent = RequiredInfoAgent(FakeLLM({RequiredInfoOutput: out}))
    res = await agent.run(_state())
    assert res.assistant_text == "What intersection was it at?"
    assert res.updated_state.ticket_details.ticket_type == "camera_issued"
    assert "fine_amount" in res.updated_state.ticket_details.skipped
    assert res.updated_state.current_agent == "required_info"


async def test_ticket_diagnosis_sets_diagnosis_and_retrieves():
    diag = TicketDiagnosis(
        type="camera_issued", sub_type="amps_camera", is_red_light_camera=True,
        camera_cutoff="post_jan_20_2025", deadline_status="within_window",
        recap_text="So this is a red light camera ticket from November 18th.",
    )
    agent = TicketDiagnosisAgent(FakeLLM({TicketDiagnosis: diag}), retriever=FakeRetriever(_passages()))
    res = await agent.run(_state())
    assert res.updated_state.diagnosis.sub_type == "amps_camera"
    assert res.assistant_text.startswith("So this is")
    assert "out_of_scope_ticket" not in res.updated_state.flags


async def test_ticket_diagnosis_flags_out_of_scope():
    diag = TicketDiagnosis(
        type="officer_issued", sub_type="poa_part_i", is_red_light_camera=False,
        recap_text="This looks like an officer-issued ticket, which is out of scope.",
    )
    agent = TicketDiagnosisAgent(FakeLLM({TicketDiagnosis: diag}), retriever=FakeRetriever([]))
    res = await agent.run(_state())
    assert "out_of_scope_ticket" in res.updated_state.flags


async def test_procedure_map_returns_options():
    out = ProcedureMapOutput(
        options=[
            PathOption(path="early_resolution", title="Early Resolution", description="Meet the prosecutor"),
            PathOption(path="trial", title="Trial", description="Contest at trial"),
        ],
        message="You can pursue early resolution or a trial. Which sounds right?",
    )
    agent = ProcedureMapAgent(FakeLLM({ProcedureMapOutput: out}), retriever=FakeRetriever(_passages()))
    res = await agent.run(_state())
    assert res.data.options[0].path == "early_resolution"
    assert "early resolution" in res.assistant_text.lower()


async def test_sufficient_data_requires_both_rule_and_llm():
    # Rule-based fails (incomplete fields) even though the LLM says sufficient.
    out = SufficientDataOutput(sufficient=True, reason="There is a calibration angle.")
    agent = SufficientDataAgent(FakeLLM({SufficientDataOutput: out}))
    state = _state()  # ticket_details is None → incomplete
    res = await agent.run(state)
    assert res.updated_state.sufficient_data is False
    assert "Missing required fields" in res.assistant_text


async def test_sufficient_data_passes_when_complete_and_llm_true():
    out = SufficientDataOutput(sufficient=True, reason="Strong calibration challenge.")
    complete = TicketDetails(
        ticket_type="camera_issued", ticket_date=date(2025, 11, 18), intersection="King & Bay",
        vehicle_owner="self", who_was_driving="self", ticket_number="RLC123",
        fine_amount=325.0, deadline_date=date(2026, 1, 1),
    )
    agent = SufficientDataAgent(FakeLLM({SufficientDataOutput: out}))
    res = await agent.run(_state(ticket_details=complete))
    assert res.updated_state.sufficient_data is True


async def test_disclosure_agent_produces_preliminary_package():
    pkg = DisclosurePackage(request_text="Please disclose the following...", diary_date=date(2026, 6, 15))
    agent = DisclosureRequestAgent(FakeLLM({DisclosurePackage: pkg}), retriever=FakeRetriever(_passages()))
    res = await agent.run(_state())
    assert res.updated_state.disclosure_requested is True
    assert res.updated_state.disclosure_package is not None
    assert "preliminary_pending_disclosure" in res.updated_state.disclosure_package.flags


async def test_defence_theory_builds_path_package_with_confidence():
    pkg = ERPackage(summary="Early resolution plan")
    async def generate(q, passages, strict):
        return "grounded analysis text"

    agent = DefenceTheoryAgent(
        FakeLLM({ERPackage: pkg}),
        retriever=FakeRetriever(_passages()),
        critics=FakeCritics(),
        generate=generate,
    )
    state = _state(chosen_path="early_resolution")
    res = await agent.run(state)
    assert res.updated_state.er_package is not None
    assert res.updated_state.er_package.confidence == "high"  # FakeCritics → grounded+adequate
    assert res.updated_state.er_package.citations  # citations attached from passages
    assert res.updated_state.er_package.is_preliminary is False


async def test_defence_theory_marks_preliminary_when_disclosure_requested():
    pkg = ERPackage(summary="plan")
    async def generate(q, p, s):
        return "text"
    agent = DefenceTheoryAgent(
        FakeLLM({ERPackage: pkg}), retriever=FakeRetriever(_passages()),
        critics=FakeCritics(), generate=generate,
    )
    state = _state(chosen_path="early_resolution", disclosure_requested=True)
    res = await agent.run(state)
    assert res.updated_state.er_package.is_preliminary is True
    assert "preliminary_pending_disclosure" in res.updated_state.er_package.flags


# --- End-to-end walk through all six agents -------------------------------


async def test_end_to_end_lawyer_flow_produces_package():
    state = SessionState(session_id="e2e", mode="lawyer")
    state.add_turn("user", "I got a red light camera ticket")

    complete = TicketDetails(
        ticket_type="camera_issued", ticket_date=date(2025, 11, 18), intersection="King & Bay",
        vehicle_owner="self", who_was_driving="self", ticket_number="RLC123",
        fine_amount=325.0, deadline_date=date(2026, 1, 1),
    )

    # 1. Required Info
    ri = RequiredInfoAgent(FakeLLM({RequiredInfoOutput: RequiredInfoOutput(
        details=complete, message="Great, I have everything.", complete=True)}))
    state = (await ri.run(state)).updated_state

    # 2. Ticket Diagnosis
    td = TicketDiagnosisAgent(FakeLLM({TicketDiagnosis: TicketDiagnosis(
        type="camera_issued", sub_type="amps_camera", is_red_light_camera=True,
        deadline_status="within_window", recap_text="Red light camera ticket, within the window.")}),
        retriever=FakeRetriever(_passages()))
    state = (await td.run(state)).updated_state

    # 3. Procedure Map → user chooses early resolution
    pm = ProcedureMapAgent(FakeLLM({ProcedureMapOutput: ProcedureMapOutput(
        options=[PathOption(path="early_resolution", title="ER", description="meet prosecutor")],
        message="You could try early resolution.")}), retriever=FakeRetriever(_passages()))
    state = (await pm.run(state)).updated_state
    state.chosen_path = "early_resolution"  # user's spoken choice

    # 4. Sufficient Data (complete + llm true → passes)
    sd = SufficientDataAgent(FakeLLM({SufficientDataOutput: SufficientDataOutput(
        sufficient=True, reason="Genuine calibration challenge available.")}))
    state = (await sd.run(state)).updated_state
    assert state.sufficient_data is True

    # 5. Sufficient → straight to Defence Theory (no disclosure)
    async def generate(q, p, s):
        return "grounded analysis"
    dt = DefenceTheoryAgent(
        FakeLLM({ERPackage: ERPackage(summary="ER plan", proposed_resolution="reduce fine")}),
        retriever=FakeRetriever(_passages()), critics=FakeCritics(),
        generate=generate)
    result = await dt.run(state)
    state = result.updated_state

    pkg = state.finalized_package()
    assert pkg is not None
    assert pkg.kind == "early_resolution"
    assert pkg.confidence in ("high", "medium", "low")
    assert pkg.citations
    # Memory intact across all agents: the original opening turn survives.
    assert state.transcript[0].content == "I got a red light camera ticket"
    assert state.current_agent == "defence_theory"
