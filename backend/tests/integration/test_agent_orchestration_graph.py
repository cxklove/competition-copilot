"""Real offline LangGraph paths; caller selection, no model or live runtime."""

import ast
import inspect
import json
import runpy
import socket
from pathlib import Path

import pytest

pytest.importorskip("langgraph", reason="Install backend agent extra for Graph tests")

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.agents.contracts import (
    AgentIntent,
    AgentRequest,
    AgentResponse,
    CapabilityId,
    CapabilityInvocationRequest,
    ReferenceKind,
    ResultReference,
    WorkflowStatus,
)
from competition_copilot.agents.graph import (
    GraphInput,
    build_competition_copilot_graph,
)
from competition_copilot.agents.state import AgentState
from competition_copilot.application.eligibility import CompetitionEligibilityEvaluator
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.tools.competition import (
    GetCompetitionTool,
    ListCompetitionsTool,
)

ROOT = Path(__file__).resolve().parents[3]
P12_1 = runpy.run_path(str(ROOT / "backend/tests/agents/test_agent_contracts.py"))


@pytest.fixture(autouse=True)
def no_network_or_telemetry(monkeypatch):
    def reject(*args, **kwargs):
        pytest.fail("Graph must run offline, including ambient tracing")
    monkeypatch.setattr(socket, "create_connection", reject)
    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)
    # Public wrapper must suppress even ambient opt-in SDK tracing.
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")


class RecordingFacade(AgentCapabilityFacade):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = []

    def execute(self, invocation, arguments, *, result_ref):
        self.calls.append(invocation.capability)
        return super().execute(invocation, arguments, result_ref=result_ref)


@pytest.fixture
def facade():
    repository = JsonSeedCompetitionRepository(ROOT / "data/seed")
    return RecordingFacade(
        read_tools={CapabilityId.GET_COMPETITION: GetCompetitionTool(repository),
                    CapabilityId.LIST_COMPETITIONS: ListCompetitionsTool(repository)},
        eligibility=CompetitionEligibilityEvaluator(repository,
            JsonEligibilityPolicyProvider(ROOT / "data/eligibility")),
    )


def frame(capability=CapabilityId.GET_COMPETITION, *, payload=None,
          intent=AgentIntent.GET_COMPETITION_DETAILS, user_message="No inferred intent"):
    request = AgentRequest(request_id="controlled-r", user_message=user_message)
    invocation = CapabilityInvocationRequest(
        invocation_id="controlled-i", source_request_id=request.request_id,
        intent=intent if intent != AgentIntent.UNKNOWN else AgentIntent.GET_COMPETITION_DETAILS,
        capability=capability,
        requires_approval=capability == CapabilityId.REVISE_PLAN,
        arguments_ref=ResultReference(kind=ReferenceKind.CAPABILITY_ARGUMENTS, ref_id="controlled-a"),
    )
    # UNKNOWN must not contain a conflicting structured invocation.
    state = AgentState(request=request, intent=intent,
                       invocation=None if intent == AgentIntent.UNKNOWN else invocation)
    args = {"artifact_ref": invocation.arguments_ref.model_dump(mode="json"),
            "payload": {"competition_id": "huawei-ict"} if payload is None else payload}
    return GraphInput(state=state, clarification_id="controlled-q",
                      result_ref=ResultReference(kind=ReferenceKind.TOOL_RESULT, ref_id="controlled-result"),
                      arguments_json=json.dumps(args, default=lambda m: m.model_dump(mode="json")))


def path_and_response(graph, value):
    events = list(graph.stream(value))
    names = tuple(next(iter(update)) for update in events)
    response = next(update[name]["response"] for update in reversed(events)
                    for name in update if "response" in update[name])
    return names, response, events


def test_graph_build_compile_node_names_and_no_store(facade):
    graph = build_competition_copilot_graph(facade)
    assert set(graph.compiled.get_graph().nodes) == {
        "__start__", "__end__", "intake", "intent", "route", "clarification",
        "approval", "tool_execution", "result_validation", "explain",
    }
    assert graph.compiled.checkpointer is None and graph.compiled.store is None
    assert facade.calls == []


def test_real_read_known_path_is_deterministic_and_input_immutable(facade):
    graph = build_competition_copilot_graph(facade)
    value = frame()
    before = value.model_dump_json()
    first_path, first, updates = path_and_response(graph, value)
    second_path, second, _ = path_and_response(graph, value)
    assert first_path == second_path == (
        "intake", "intent", "route", "tool_execution", "result_validation", "explain",
    )
    assert first == second and first.model_dump_json() == second.model_dump_json()
    assert first.outcome == WorkflowStatus.COMPLETED
    assert value.model_dump_json() == before
    assert facade.calls == [CapabilityId.GET_COMPETITION, CapabilityId.GET_COMPETITION]
    receipt = next(update["tool_execution"]["receipt"] for update in updates if "tool_execution" in update)
    assert receipt.data.competition.id == "huawei-ict"
    assert first.audit == receipt.audit
    terminal = updates[-1]["explain"]["state"]
    assert terminal.status == "COMPLETED" and terminal.final_response == first
    assert terminal.tool_result.invocation_id == value.state.invocation.invocation_id


@pytest.mark.parametrize("message", ["Check eligibility", "资格", "可以，改吧", "Recommend and replan"])
def test_unknown_intent_never_guesses_or_executes(facade, message):
    graph = build_competition_copilot_graph(facade)
    value = frame(intent=AgentIntent.UNKNOWN, user_message=message)
    path, response, _ = path_and_response(graph, value)
    assert path == ("intake", "intent", "clarification")
    assert response.outcome == "NEEDS_CLARIFICATION" and response.error is None
    assert response.clarification.reason == "AMBIGUOUS_INTENT"
    assert value.state.request.context.competition_id is None
    assert facade.calls == []


def test_missing_structured_selection_requires_clarification(facade):
    value = frame()
    state = AgentState(request=value.state.request, intent=value.state.intent)
    value = GraphInput(**{**value.model_dump(), "state": state})
    path, response, _ = path_and_response(build_competition_copilot_graph(facade), value)
    assert path == ("intake", "intent", "route", "clarification")
    assert response.clarification.fields == ("CAPABILITY_INVOCATION",)
    assert facade.calls == []


def test_missing_target_is_normal_clarification_not_failure(facade):
    value = frame(payload={})
    path, response, _ = path_and_response(build_competition_copilot_graph(facade), value)
    assert path[-1] == "clarification" and "tool_execution" not in path
    assert response.outcome == "NEEDS_CLARIFICATION"
    assert response.clarification.fields == ("COMPETITION",)
    assert response.error is None and facade.calls == []


def test_unsupported_capability_no_fallback(facade):
    value = frame(CapabilityId.EXPLAIN_REPLANNING)
    path, response, _ = path_and_response(build_competition_copilot_graph(facade), value)
    assert path == ("intake", "intent", "route")
    assert response.outcome == "FAILED" and response.message == "UNSUPPORTED_CAPABILITY"
    assert facade.calls == []


@pytest.mark.parametrize("message", ["Please cancel", "可以，改吧"])
def test_approval_wait_boundary_never_invents_authority(facade, message):
    plan_ref = P12_1["plan_ref"].__wrapped__()
    request = P12_1["agent_request"].__wrapped__(plan_ref)
    request = AgentRequest(**{**request.model_dump(), "user_message": message})
    invocation = P12_1["invocation"].__wrapped__(request)
    audit = P12_1["audit"].__wrapped__()
    proposal = P12_1["approval"].__wrapped__(request, invocation, audit)
    state = AgentState(request=request, intent=invocation.intent, invocation=invocation)
    value = GraphInput(
        state=state, clarification_id="q", result_ref=ResultReference(kind="TOOL_RESULT", ref_id="r"),
        approval_proposal=proposal,
        # Required argument shape present; no authority is fabricated or executed.
        arguments_json=json.dumps({"artifact_ref": invocation.arguments_ref.model_dump(mode="json"),
                                   "payload": {"before": {}, "replanning_input": {},
                                               "executed_at": "2026-10-14T12:00:00Z"}}),
    )
    path, response, updates = path_and_response(build_competition_copilot_graph(facade), value)
    assert path == ("intake", "intent", "route", "approval")
    assert response.outcome == "WAITING_FOR_APPROVAL"
    assert response.approval_request == proposal
    assert updates[-1]["approval"]["state"].approval_response is None
    assert not hasattr(proposal, "authority") and facade.calls == []


def test_missing_approval_proposal_facts_cannot_be_invented(facade):
    value = frame(CapabilityId.REVISE_PLAN, payload={
        "before": {}, "replanning_input": {}, "executed_at": "2026-10-14T12:00:00Z",
    }, intent=AgentIntent.REQUEST_PLAN_REVISION)
    path, response, _ = path_and_response(build_competition_copilot_graph(facade), value)
    assert path[-1] == "clarification" and response.outcome == "NEEDS_CLARIFICATION"
    assert response.clarification.reason == "MISSING_APPROVAL_CONTEXT"
    assert facade.calls == []


@pytest.mark.parametrize("level,expected", [("graduate", "ineligible"), (None, "unknown")])
def test_real_eligibility_negative_remains_completed_and_evidence_intact(facade, level, expected):
    value = frame(CapabilityId.CHECK_ELIGIBILITY, intent=AgentIntent.CHECK_ELIGIBILITY, payload={
        "student": {"id": "controlled-graduate", "education_level": level},
        "competition_id": "gcxl-engineering-practice-innovation",
        "edition_id": "gcxl-engineering-practice-innovation-2027",
    })
    path, response, events = path_and_response(build_competition_copilot_graph(facade), value)
    receipt = next(e["tool_execution"]["receipt"] for e in events if "tool_execution" in e)
    assert receipt.data.status.value == expected
    assert response.outcome == "COMPLETED" and response.error is None
    assert response.audit == receipt.audit
    assert response.audit.reasons
    assert {r.kind for r in response.audit.results} >= {ReferenceKind.EVIDENCE, ReferenceKind.SOURCE}
    assert path[-2:] == ("result_validation", "explain")


@pytest.mark.parametrize("case", ["invalid", "dependency", "not_found"])
def test_tool_invocation_errors_are_failure_without_retry(facade, case):
    if case == "dependency":
        facade = RecordingFacade()
    value = frame(payload={"competition_id": 123 if case == "invalid" else "absent"})
    path, response, _ = path_and_response(build_competition_copilot_graph(facade), value)
    assert path[-1] == "result_validation" and "explain" not in path
    assert response.outcome == "FAILED"
    assert response.error.code == "CAPABILITY_EXECUTION_FAILED"
    assert len(facade.calls) == 1


def test_corrupted_receipt_rejected_without_business_reassessment(facade):
    original = facade.execute
    def mismatched(*args, **kwargs):
        result = original(*args, **kwargs)
        return {**result.model_dump(), "invocation_id": "another-invocation"}
    facade.execute = mismatched
    path, response, _ = path_and_response(build_competition_copilot_graph(facade), frame())
    assert response.outcome == "FAILED" and path[-1] == "result_validation"
    assert response.error.code == "INVALID_WORKFLOW_TRANSITION"


@pytest.mark.parametrize("outcome", [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED])
def test_terminal_states_cannot_restart(facade, outcome):
    value = frame()
    from competition_copilot.agents.contracts import AgentError
    error = AgentError(code="TOOL_UNAVAILABLE", message="Unavailable") if outcome == "FAILED" else None
    response = AgentResponse(request_id=value.state.request.request_id, intent=value.state.intent,
                             outcome=outcome, message="Finished", error=error)
    state = AgentState(request=value.state.request, intent=value.state.intent,
                       status=outcome, final_response=response, error=error)
    value = GraphInput(**{**value.model_dump(), "state": state})
    with pytest.raises(ValueError, match="cannot restart"):
        build_competition_copilot_graph(facade).invoke(value)
    assert facade.calls == []


def test_json_input_response_roundtrip_and_state_delta_validation(facade):
    value = frame()
    raw = json.loads(value.model_dump_json())
    graph = build_competition_copilot_graph(facade)
    response = graph.invoke(raw)
    assert isinstance(response, AgentResponse)
    assert AgentResponse.model_validate_json(json.dumps(response.model_dump(mode="json"))) == response
    assert GraphInput.model_validate_json(value.model_dump_json()) == value
    for update in graph.stream(value):
        for delta in update.values():
            if "state" in delta:
                assert AgentState.model_validate_json(delta["state"].model_dump_json()) == delta["state"]


def test_graph_import_boundary_and_no_message_interpretation():
    import competition_copilot.agents.graph as module
    text = inspect.getsource(module)
    imports = [n.module or "" for n in ast.walk(ast.parse(text)) if isinstance(n, ast.ImportFrom)]
    assert not any("infrastructure" in name or "agentarts" in name for name in imports)
    assert not any("event_impact_analyzer" in name or "plan_revision_service" in name for name in imports)
    assert "user_message" not in text and "human_approved" not in text
    assert "while " not in text and "ChatOpenAI" not in text


def test_structured_approve_cannot_replace_p11_authorized_input(facade):
    plan_ref = P12_1["plan_ref"].__wrapped__()
    request = P12_1["agent_request"].__wrapped__(plan_ref)
    invocation = P12_1["invocation"].__wrapped__(request)
    proposal = P12_1["approval"].__wrapped__(request, invocation, P12_1["audit"].__wrapped__())
    submitted = P12_1["submitted"](proposal)
    state = AgentState(request=request, intent=invocation.intent,
                       status=WorkflowStatus.READY_TO_EXECUTE, invocation=invocation,
                       approval_request=proposal, approval_response=submitted)
    from competition_copilot.domain.plan_revision_service import PlanRevisionService
    # Real Facade + real P11 authority; malformed formal input must still reject.
    facade._revision = PlanRevisionService()
    value = GraphInput(state=state, clarification_id="q",
        result_ref=ResultReference(kind="TOOL_RESULT", ref_id="r"),
        arguments_json=json.dumps({"artifact_ref": invocation.arguments_ref.model_dump(mode="json"),
                                   "payload": {"before": {}, "replanning_input": {},
                                               "executed_at": "2026-10-14T12:00:00Z"}}))
    path, response, _ = path_and_response(build_competition_copilot_graph(facade), value)
    assert path[-1] == "result_validation" and response.outcome == "FAILED"
    assert "INVALID_INPUT" in response.message and facade.calls == [CapabilityId.REVISE_PLAN]


def test_missing_and_malformed_arguments_stop_safely(facade):
    graph = build_competition_copilot_graph(facade)
    value = frame()
    missing = GraphInput(**{**value.model_dump(), "arguments_json": None})
    assert graph.invoke(missing).outcome == "NEEDS_CLARIFICATION"
    malformed = GraphInput(**{**value.model_dump(), "arguments_json": "not json"})
    assert graph.invoke(malformed).error.code == "SERIALIZATION_ERROR"
    assert facade.calls == []
