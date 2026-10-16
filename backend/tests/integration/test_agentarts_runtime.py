"""Offline transport and official SDK smoke over the same core graph/authorities."""

import ast
import asyncio
import importlib.util
import json
import runpy
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("langgraph", reason="Install optional agent extra")

from competition_copilot.agents.contracts import AgentRequest, ApprovalResponse
from competition_copilot.agents.graph import GraphInput, build_competition_copilot_graph
from competition_copilot.agents.human_contracts import (
    ClarificationResponse,
    HumanResume,
)
from competition_copilot.agents.routing import IntentRoutingProposal
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.integrations.agentarts.contracts import (
    AgentArtsInvocationEnvelope,
    AgentArtsInvocationResult,
)
from competition_copilot.integrations.agentarts.runtime import AgentArtsRuntimeAdapter

ROOT = Path(__file__).resolve().parents[3]
EXPLAIN = runpy.run_path(str(Path(__file__).with_name("test_agent_explanation.py")))
HUMAN, GRAPH = EXPLAIN["HUMAN"], EXPLAIN["GRAPH"]
SDK_AVAILABLE = importlib.util.find_spec("agentarts") is not None


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original_connect = socket.socket.connect

    def forbidden(*args, **kwargs):
        pytest.fail("Runtime tests must not access network/cloud")

    def connect(sock, address):
        # Windows asyncio creates its own loopback socket pair, without HTTP.
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original_connect(sock, address)
        return forbidden(sock, address)

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.fixture
def facade():
    return HUMAN["facade"].__wrapped__()


class Bindings:
    """Test-only trusted JSON handoff; not a production session store."""
    def __init__(self, frame, pending_json=None, execution=None):
        self.frame_json = frame.model_dump_json()
        self.pending_json, self.execution = pending_json, execution or {}
        self.calls = []

    def prepare_request(self, request):
        self.calls.append("prepare")
        return GraphInput.model_validate_json(self.frame_json)

    def resolve_continuation(self, reference):
        self.calls.append("resolve")
        if reference != "authorized-workflow-ref" or self.pending_json is None:
            raise LookupError("PRIVATE session location")
        return GraphInput.model_validate_json(self.pending_json)

    def prepare_resume(self, prior, reply):
        self.calls.append("resume_context")
        field = ("clarification" if isinstance(reply, ClarificationResponse) else
                 "approval" if isinstance(reply, ApprovalResponse) else "message")
        return HumanResume(**{field: reply, **self.execution})


class CoreSpy:
    def __init__(self, core):
        self.core, self.calls = core, []
    def run_turn(self, frame):
        self.calls.append(("run_turn", frame))
        return self.core.run_turn(frame)
    def resume(self, frame, reply):
        self.calls.append(("resume", frame))
        return self.core.resume(frame, reply)


def invoke(adapter, payload):
    return asyncio.run(adapter.invoke(payload))


def initial(frame):
    return {"request": frame.state.request.model_dump(mode="json")}


def resume_payload(reply):
    return {"continuation_ref": "authorized-workflow-ref", **reply.model_dump(mode="json", exclude_none=True)}


def assert_json(value):
    assert type(value) in (dict, list, str, int, float, bool, type(None))
    if isinstance(value, dict):
        for key, item in value.items():
            assert type(key) is str
            assert_json(item)
    elif isinstance(value, list):
        for item in value:
            assert_json(item)
    json.dumps(value, allow_nan=False)


class RoutingModel:
    def propose(self, value):
        return IntentRoutingProposal(intent="DISCOVER_COMPETITIONS", candidate_capability="list_competitions",
                                     ambiguity="NONE", missing_context=())


@pytest.mark.parametrize("mode", ["valid", "timeout"])
def test_local_runtime_parity_with_injected_routing_and_explanation(facade, mode):
    model = EXPLAIN["FakeExplanationModel"](mode)
    core = build_competition_copilot_graph(facade, intent_model=RoutingModel(), explanation_model=model)
    value = GRAPH["frame"](capability="list_competitions", intent="UNKNOWN", payload={})
    request = AgentRequest(**{**value.state.request.model_dump(), "user_message": "我想看看有哪些比赛"})
    state = type(value.state)(request=request)
    args = json.loads(value.arguments_json)
    value = GraphInput(**{**value.model_dump(), "state": state, "routing_invocation_id": "runtime-invoke",
        "routing_arguments_ref": args["artifact_ref"]})
    before = value.model_dump_json()
    local = core.run_turn(value)
    spy = CoreSpy(core)
    adapter = AgentArtsRuntimeAdapter(spy, Bindings(value))
    first, second = invoke(adapter, initial(value)), invoke(adapter, initial(value))
    assert first == second and first["response"] == local.response.model_dump(mode="json")
    assert first["error"] is None and len(spy.calls) == 2
    assert value.model_dump_json() == before
    assert_json(first)
    assert AgentArtsInvocationResult.model_validate_json(json.dumps(first)).model_dump(mode="json") == first


@pytest.mark.parametrize("level,status", [("graduate", "INELIGIBLE"), (None, "UNKNOWN")])
def test_business_negative_and_url_datetime_explanation_are_not_runtime_errors(facade, level, status):
    model = EXPLAIN["FakeExplanationModel"]("timeout")
    core = build_competition_copilot_graph(facade, explanation_model=model)
    value = GRAPH["frame"](capability="check_eligibility", intent="CHECK_ELIGIBILITY",
                           payload=EXPLAIN["eligibility_payload"](level))
    spy = CoreSpy(core)
    result = invoke(AgentArtsRuntimeAdapter(spy, Bindings(value)), initial(value))
    assert result["error"] is None and result["response"]["outcome"] == "COMPLETED"
    assert status in result["response"]["message"] and len(spy.calls) == 1
    assert facade.calls == ["check_eligibility"]
    context = model.contexts[0]
    source = next(e.source for e in context.evidence if e.source is not None)
    assert str(source.source_url) in result["response"]["message"]
    assert source.observed_at.isoformat() in result["response"]["message"]
    assert any(r["kind"] == "SOURCE" for r in result["response"]["audit"]["results"])
    assert_json(result)


@pytest.mark.parametrize("bad", [
    None, [], {}, {"message": "untyped shortcut"},
    {"request": {}}, {"request": {"request_id": 12, "user_message": "hello"}},
    {"request": {"request_id": "r", "user_message": "hello", "approved": True}},
    {"request": {"request_id": "r", "user_message": "hello"}, "handler": "os.system"},
    {"request": {"request_id": "r", "user_message": "hello"}, "state": {"status": "HUMAN_APPROVED"}},
    {"continuation_ref": "ref", "approved_by_ref": "admin"},
    {"continuation_ref": "ref", "approval": {"decision": "AUTO_APPROVE"}},
])
def test_invalid_transport_never_enters_core(facade, bad):
    value = GRAPH["frame"]()
    spy = CoreSpy(build_competition_copilot_graph(facade))
    bindings = Bindings(value)
    result = invoke(AgentArtsRuntimeAdapter(spy, bindings), bad)
    assert result["error"]["code"] == "INVALID_RUNTIME_PAYLOAD"
    assert result["response"] is None and spy.calls == [] and bindings.calls == []


def test_callable_and_client_execution_context_injection_rejected(facade):
    value = GRAPH["frame"]()
    spy = CoreSpy(build_competition_copilot_graph(facade))
    adapter = AgentArtsRuntimeAdapter(spy, Bindings(value))
    for key, item in (("handler", lambda: None), ("current_plan", {}),
                      ("authority", {"kind": "human_approved"}), ("capability", "DELETE_DATABASE")):
        result = invoke(adapter, {**initial(value), key: item})
        assert result["error"]["code"] == "INVALID_RUNTIME_PAYLOAD"
    assert spy.calls == [] and facade.calls == []


def test_unexposed_server_prepared_capability_still_hits_core_whitelist(facade):
    value = GRAPH["frame"](capability="explain_replanning")
    spy = CoreSpy(build_competition_copilot_graph(facade))
    result = invoke(AgentArtsRuntimeAdapter(spy, Bindings(value)), initial(value))
    assert result["error"] is None and result["response"]["outcome"] == "FAILED"
    assert result["response"]["message"] == "UNSUPPORTED_CAPABILITY" and facade.calls == []
    assert len(spy.calls) == 1


def test_clarification_json_resume_reconstructs_trusted_state_and_preserves_parity(facade):
    core = build_competition_copilot_graph(facade)
    value = HUMAN["read_frame"]()
    spy = CoreSpy(core)
    first = invoke(AgentArtsRuntimeAdapter(spy, Bindings(value)), initial(value))
    assert first["response"]["outcome"] == "NEEDS_CLARIFICATION" and facade.calls == []
    pending = GraphInput.model_validate_json(json.dumps(first["continuation"]))
    reply = HUMAN["clarification"](pending, competition_id="huawei-ict")
    local = core.resume(pending, reply)
    facade.calls.clear()
    # New binding instance built only from JSON, not the old process/object identity.
    bindings = Bindings(value, pending_json=json.dumps(first["continuation"]))
    result = invoke(AgentArtsRuntimeAdapter(spy, bindings), resume_payload(reply))
    assert result["response"] == local.response.model_dump(mode="json")
    assert facade.calls == ["get_competition"] and len(spy.calls) == 2
    assert result["continuation"] is None and result["error"] is None
    assert AgentArtsInvocationEnvelope.model_validate_json(json.dumps(resume_payload(reply))).clarification == reply.clarification


@pytest.mark.parametrize("answer", ["APPROVE", "REJECT"])
@pytest.mark.parametrize("explanation", ["valid", "timeout"])
def test_real_p11_approval_transport_resume_and_reject(facade, answer, explanation):
    core = build_competition_copilot_graph(facade, explanation_model=EXPLAIN["FakeExplanationModel"](explanation))
    value, _, before = HUMAN["revision_frame"](facade)
    snapshot = before.model_dump_json()
    spy = CoreSpy(core)
    first = invoke(AgentArtsRuntimeAdapter(spy, Bindings(value)), initial(value))
    assert first["response"]["outcome"] == "WAITING_FOR_APPROVAL" and facade.calls == []
    q = first["response"]["approval_request"]
    assert q["before_plan"]["version"] == before.version and q["instruction_refs"]
    pending = GraphInput.model_validate_json(json.dumps(first["continuation"]))
    reply = HUMAN["approval"](pending, answer)
    execution = {k: v for k, v in reply.model_dump().items() if k in ("approved_by_ref", "current_plan", "executed_at")}
    # Actor/current version/time originate in trusted binding, never public payload.
    public = {"continuation_ref": "authorized-workflow-ref", "approval": reply.approval.model_dump(mode="json")}
    local = core.resume(pending, reply)
    facade.calls.clear()
    bindings = Bindings(value, pending_json=json.dumps(first["continuation"]), execution=execution)
    result = invoke(AgentArtsRuntimeAdapter(spy, bindings), public)
    assert result["response"] == local.response.model_dump(mode="json") and result["error"] is None
    assert result["response"]["outcome"] == "COMPLETED"
    assert facade.calls == (["revise_plan"] if answer == "APPROVE" else []) and len(spy.calls) == 2
    assert before.model_dump_json() == snapshot
    if answer == "APPROVE":
        assert "status active -> cancelled" in result["response"]["message"]
        assert any(r["kind"] == "PLAN_DIFF" for r in result["response"]["audit"]["results"])
    else:
        assert "未执行 mutation" in result["response"]["message"]
    assert_json(result)


@pytest.mark.parametrize("case", ["wrong_id", "cross_request", "stale", "unknown_ref"])
def test_approval_binding_errors_survive_transport(facade, case):
    core = build_competition_copilot_graph(facade)
    value, _, before = HUMAN["revision_frame"](facade)
    pending = core.run_turn(value).continuation
    reply = HUMAN["approval"](pending)
    execution = {"current_plan": reply.current_plan, "executed_at": reply.executed_at,
                 "approved_by_ref": reply.approved_by_ref}
    raw = reply.approval.model_dump(mode="json")
    if case == "wrong_id":
        raw["approval_request_id"] = "wrong-operation"
    elif case == "cross_request":
        raw["source_request_id"] = "another-request"
    elif case == "stale":
        execution["current_plan"] = PlanReference(**{**reply.current_plan.model_dump(), "version": before.version + 1})
    payload = {"continuation_ref": "unknown" if case == "unknown_ref" else "authorized-workflow-ref", "approval": raw}
    spy = CoreSpy(core)
    result = invoke(AgentArtsRuntimeAdapter(spy, Bindings(value, pending.model_dump_json(), execution)), payload)
    if case == "unknown_ref":
        assert result["error"]["code"] == "RUNTIME_DEPENDENCY_ERROR" and spy.calls == []
    else:
        assert result["error"] is None and result["response"]["outcome"] == "FAILED" and len(spy.calls) == 1
    assert before.status == "active" and facade.calls == []


@pytest.mark.parametrize("stage,code", [("binding", "RUNTIME_DEPENDENCY_ERROR"),
    ("binding_validation", "CORE_VALIDATION_ERROR"), ("core", "CORE_EXECUTION_ERROR"),
    ("core_validation", "CORE_VALIDATION_ERROR")])
def test_errors_are_sanitized_and_core_has_no_retry(facade, stage, code):
    value = GRAPH["frame"]()
    bindings = Bindings(value)
    calls = []
    def fail(*args):
        calls.append(True)
        error = ValueError if stage.endswith("validation") else RuntimeError
        raise error("PRIVATE C:/Users/secret/file.py API_KEY=not-a-real-key traceback")
    core = CoreSpy(build_competition_copilot_graph(facade))
    if stage.startswith("binding"):
        bindings.prepare_request = fail
    else:
        core.run_turn = fail
    result = invoke(AgentArtsRuntimeAdapter(core, bindings), initial(value))
    assert result["error"]["code"] == code and calls == [True]
    assert all(token not in json.dumps(result) for token in ("PRIVATE", "C:/", "API_KEY", "traceback"))
    assert facade.calls == []


def test_application_binding_cannot_silently_overwrite_payload_request(facade):
    value = GRAPH["frame"]()
    spy = CoreSpy(build_competition_copilot_graph(facade))
    changed = {**initial(value), "request": {**value.state.request.model_dump(mode="json"), "context": {"student_id": "s1"}}}
    result = invoke(AgentArtsRuntimeAdapter(spy, Bindings(value)), changed)
    assert result["error"]["code"] == "CORE_VALIDATION_ERROR" and spy.calls == []


@pytest.mark.skipif(not SDK_AVAILABLE, reason="Install optional agentarts extra/SDK overlay")
def test_real_sdk_import_app_and_public_invocation_endpoint(facade):
    import httpx
    from agentarts.sdk import AgentArtsRuntimeApp

    from competition_copilot.integrations.agentarts.app import create_app

    value = GRAPH["frame"]()
    spy = CoreSpy(build_competition_copilot_graph(facade))
    adapter = AgentArtsRuntimeAdapter(spy, Bindings(value))
    app = create_app(adapter)
    assert isinstance(app, AgentArtsRuntimeApp)
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local.test") as client:
            response = await client.post("/invocations", json=initial(value))
            assert response.status_code == 200
            return response.json()
    result = asyncio.run(request())
    assert result["response"]["outcome"] == "COMPLETED" and len(spy.calls) == 1
    assert facade.calls == ["get_competition"] and result["error"] is None
    assert_json(result)


@pytest.mark.skipif(not SDK_AVAILABLE, reason="Install optional agentarts extra/SDK overlay")
def test_sdk_context_identity_roles_and_tokens_cannot_become_business_context(facade, monkeypatch):
    from agentarts.sdk import AgentArtsRuntimeApp

    from competition_copilot.integrations.agentarts.app import create_app

    registered = []
    original = AgentArtsRuntimeApp.entrypoint
    def register(app, function):
        registered.append(function)
        return original(app, function)
    monkeypatch.setattr(AgentArtsRuntimeApp, "entrypoint", register)
    value, _, _ = HUMAN["revision_frame"](facade)
    spy = CoreSpy(build_competition_copilot_graph(facade))
    create_app(AgentArtsRuntimeAdapter(spy, Bindings(value)))
    context = SimpleNamespace(user_id="platform-other-student", session_id="platform-other-plan",
        role="admin", approved=True, workload_access_token="not-a-real-secret")
    first = asyncio.run(registered[0](initial(value), context))
    second = asyncio.run(registered[0](initial(value), None))
    assert first == second and first["response"]["outcome"] == "WAITING_FOR_APPROVAL"
    assert facade.calls == [] and len(spy.calls) == 2
    assert spy.calls[0][1].state.request.context == value.state.request.context
    assert all(token not in json.dumps(first) for token in ("platform-other", "not-a-real-secret", "RequestContext"))


def test_sdk_imports_are_isolated_and_core_runs_with_sdk_blocked():
    source = ROOT / "backend/competition_copilot"
    for path in source.rglob("*.py"):
        imports = [node.module or "" for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                   if isinstance(node, ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(node, ast.Import) for alias in node.names]
        if path == source / "integrations/agentarts/app.py":
            assert "agentarts.sdk" in imports
        else:
            assert not any(name == "agentarts" or name.startswith("agentarts.") for name in imports), path
    script = '''
import sys, importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "agentarts" or fullname.startswith("agentarts."):
            raise ModuleNotFoundError("SDK intentionally absent")
sys.meta_path.insert(0, Block())
from competition_copilot.agents.contracts import AgentRequest, ResultReference
from competition_copilot.agents.state import AgentState
from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.agents.graph import GraphInput, build_competition_copilot_graph
from competition_copilot.integrations.agentarts.runtime import AgentArtsRuntimeAdapter
graph = build_competition_copilot_graph(AgentCapabilityFacade())
frame = GraphInput(state=AgentState(request=AgentRequest(request_id="r", user_message="hello")),
    clarification_id="q", result_ref=ResultReference(kind="TOOL_RESULT", ref_id="result"))
assert graph.invoke(frame).outcome == "NEEDS_CLARIFICATION"
assert not any(k == "agentarts" or k.startswith("agentarts.") for k in sys.modules)
'''
    result = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr


def test_runtime_python_syntax_and_dependency_isolation():
    import tomllib

    project = tomllib.loads((ROOT / "backend/pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["requires-python"] == ">=3.11"
    assert "agentarts-sdk==0.1.6" in project["project"]["optional-dependencies"]["agentarts"]
    assert not any("agentarts" in d for d in project["project"]["dependencies"])
    for path in (ROOT / "backend/competition_copilot/integrations/agentarts").glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 11))
    assert "agentarts-sdk" not in (ROOT / "backend/requirements-agent.lock").read_text(encoding="utf-8")
