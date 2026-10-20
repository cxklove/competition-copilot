"""Real loopback/P12/Agent/Graph/Facade authorities; no cloud or external model."""

import ast
import json
import runpy
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

pytest.importorskip("langgraph", reason="Install agent extra for Local Runtime")

from competition_copilot.agents.agent import CompetitionCopilotAgent
from competition_copilot.agents.contracts import AgentResponse
from competition_copilot.application.eligibility import CompetitionEligibilityEvaluator
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.student import StudentProfile
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.integrations.local_runtime.composition import create_local_host
from competition_copilot.integrations.local_runtime.http import create_server

ROOT = Path(__file__).resolve().parents[3]
PLAN = json.loads((ROOT / "frontend/src/demo/local-plan.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    connect = socket.socket.connect
    def only_loopback(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return connect(sock, address)
        pytest.fail("Local Runtime tests must not contact external network")
    monkeypatch.setattr(socket.socket, "connect", only_loopback)


@pytest.fixture
def hosted():
    host = create_local_host(ROOT)
    factory = host.factory
    calls = []
    def observe(request):
        session = factory(request)
        assert isinstance(session.adapter._core, CompetitionCopilotAgent)
        assert session.adapter._core.graph.compiled.__class__.__module__.startswith("langgraph")
        core = session.adapter._core
        run, resume = core.run_turn, core.resume
        def initial(frame):
            calls.append(("run", frame.state.request.request_id))
            return run(frame)
        def continuation(frame, reply):
            calls.append(("resume", frame.state.request.request_id))
            return resume(frame, reply)
        core.run_turn, core.resume = initial, continuation
        return session
    host.factory = observe
    server = create_server(host, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    before = {path: path.read_bytes() for path in (ROOT / "data").rglob("*.json")}
    yield host, f"http://127.0.0.1:{server.server_port}", calls
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert before == {path: path.read_bytes() for path in before}


def post(url, payload, *, headers=None, route="/runtime/invoke"):
    data = json.dumps(payload).encode()
    request = Request(url + route, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response), dict(response.headers)


def initial(url, message="有哪些比赛？", request_id="request-1", context=None):
    return post(url, {"request": {"request_id": request_id, "user_message": message, "context": context or {}}})


def approval_reply(pending, decision):
    response = pending["runtime"]["response"]
    return {"continuation_ref": pending["runtime"]["continuation_ref"], "approval": {
        "approval_request_id": response["approval_request"]["approval_request_id"],
        "source_request_id": response["request_id"], "decision": decision,
        "submitted_at": datetime.now(timezone.utc).isoformat()}}


def test_real_discovery_canonical_identity_and_no_context_from_headers(hosted):
    host, url, calls = hosted
    status, value, headers = initial(url, request_id=" request-1 ")
    assert status == 200 and host.handler_invocations == 1 and calls == [("run", "request-1")]
    response = AgentResponse.model_validate(value["runtime"]["response"])
    assert response.request_id == value["presentation"]["request_id"] == "request-1"
    assert response.outcome == "COMPLETED" and "continuation" not in value["runtime"]
    competitions = value["presentation"]["artifacts"][0]["value"]["competitions"]
    assert [item["id"] for item in competitions] == [item.id for item in JsonSeedCompetitionRepository(ROOT / "data/seed").list_competitions()]
    assert headers["Cache-Control"] == "no-store"
    status, other, _ = post(url, {"request": {"request_id": "other", "user_message": "discovery"}},
        headers={"Cookie": "student_id=admin; approved=true", "X-Student-Id": "owner"})
    assert status == 200 and other["runtime"]["response"]["request_id"] == "other"
    assert other["presentation"]["artifacts"][0]["value"] == value["presentation"]["artifacts"][0]["value"]


@pytest.mark.parametrize("student,status", [("local-graduate", "ineligible"), ("local-unknown", "unknown")])
def test_real_business_negative_and_full_sources_are_http_success(hosted, student, status):
    _, url, _ = hosted
    code, value, _ = initial(url, "eligibility", context={"student_id": student,
        "competition_id": "gcxl-engineering-practice-innovation", "edition_id": "gcxl-engineering-practice-innovation-2027"})
    assert code == 200 and value["runtime"]["error"] is None
    assert value["runtime"]["response"]["outcome"] == "COMPLETED"
    result = next(a["value"] for a in value["presentation"]["artifacts"] if a["model"] == "EligibilityDecision")
    assert result["status"] == status
    evaluator = CompetitionEligibilityEvaluator(JsonSeedCompetitionRepository(ROOT / "data/seed"), JsonEligibilityPolicyProvider(ROOT / "data/eligibility"))
    profile = StudentProfile(id=student, **({"education_level": "graduate"} if student == "local-graduate" else {}))
    assert evaluator.evaluate(profile, "gcxl-engineering-practice-innovation", "gcxl-engineering-practice-innovation-2027").model_dump(mode="json") == result
    source = SourceMetadata.model_validate(next(e["source"] for e in result["evidence"] if e["source"]))
    assert str(source.source_url).startswith("http://") and source.observed_at.tzinfo


def test_real_clarification_identity_single_use_and_cross_request_fail_closed(hosted):
    host, url, calls = hosted
    _, pending, _ = initial(url, "赛事详情")
    public = pending["runtime"]
    question = public["response"]["clarification"]
    assert question["fields"] == ["COMPETITION"]
    assert "continuation" not in public and "state" not in json.dumps(public)
    reply = {"continuation_ref": public["continuation_ref"], "clarification": {
        "clarification_id": question["clarification_id"], "source_request_id": question["source_request_id"],
        "values": {"competition_id": "huawei-ict"}, "submitted_at": datetime.now(timezone.utc).isoformat()}}
    code, value, _ = post(url, reply)
    assert code == 200 and value["runtime"]["response"]["outcome"] == "COMPLETED"
    assert value["runtime"]["response"]["request_id"] == "request-1"
    assert value["presentation"]["artifacts"][0]["value"]["competition"]["id"] == "huawei-ict"
    assert host.handler_invocations == len(calls) == 2
    assert post(url, reply)[1]["runtime"]["error"]["code"] == "CORE_VALIDATION_ERROR"
    assert host.handler_invocations == len(calls) == 2
    _, new, _ = initial(url, "detail", request_id="different")
    reply["continuation_ref"] = new["runtime"]["continuation_ref"]
    assert post(url, reply)[1]["runtime"]["error"]["code"] == "CORE_VALIDATION_ERROR"


@pytest.mark.parametrize("decision", ["APPROVE", "REJECT"])
def test_real_approval_bridge_identity_replay_and_actual_plan_diff(hosted, decision):
    host, url, calls = hosted
    _, pending, _ = initial(url, "controlled revision", context={"plan_ref": PLAN})
    response = pending["runtime"]["response"]
    proposal = response["approval_request"]
    assert response["outcome"] == "WAITING_FOR_APPROVAL" and proposal["before_plan"] == PLAN
    assert proposal["action"] == "PLAN_REVISION" and proposal["affected_scope_ref"]
    assert not pending["presentation"]["artifacts"]
    reply = approval_reply(pending, decision)
    assert "HUMAN_APPROVED" not in json.dumps(reply)
    code, result, _ = post(url, reply)
    assert code == 200 and result["runtime"]["response"]["outcome"] == "COMPLETED"
    assert host.handler_invocations == len(calls) == 2
    diffs = [a["value"] for a in result["presentation"]["artifacts"] if a["model"] == "PlanDiff"]
    if decision == "APPROVE":
        assert len(diffs) == 1 and diffs[0]["before"]["status"] == "active"
        assert diffs[0]["after"]["status"] == "cancelled" and diffs[0]["after"]["version"] == PLAN["version"] + 1
        assert proposal["approval_request_id"] in result["runtime"]["response"]["message"]
        # Another stale workflow cannot approve the old version after actual revision.
        assert initial(url, "controlled revision", request_id="stale", context={"plan_ref": PLAN})[1]["runtime"]["error"]["code"] == "CORE_VALIDATION_ERROR"
    else:
        assert not diffs and "REJECTED" in result["runtime"]["response"]["message"]
    assert post(url, reply)[1]["runtime"]["error"]["code"] == "CORE_VALIDATION_ERROR"


@pytest.mark.parametrize("message,model", [("skill", "SkillGapDecision"), ("plan", "CompetitionPlan"), ("recommend", "RecommendationRankingResult")])
def test_p6_p7_p8_real_authorities(hosted, message, model):
    _, url, _ = hosted
    _, value, _ = initial(url, message, context={"student_id": "local-graduate", "competition_id": "comap-mcm", "edition_id": "comap-mcm-2027"})
    assert value["runtime"]["response"]["outcome"] == "COMPLETED"
    result = next(a["value"] for a in value["presentation"]["artifacts"] if a["model"] == model)
    if model == "CompetitionPlan":
        assert result["planning_needs"] and result["milestones"]


def test_parallel_requests_and_expired_handles_are_isolated(hosted):
    host, url, _ = hosted
    with ThreadPoolExecutor() as pool:
        results = list(pool.map(lambda id: initial(url, request_id=id)[1], ("a", "b")))
    assert [r["runtime"]["response"]["request_id"] for r in results] == ["a", "b"]
    assert results[0]["runtime"]["response"]["audit"] != results[1]["runtime"]["response"]["audit"]
    host.ttl = 0
    _, pending, _ = initial(url, "controlled revision", context={"plan_ref": PLAN})
    assert post(url, approval_reply(pending, "REJECT"))[1]["runtime"]["error"]["code"] == "CORE_VALIDATION_ERROR"


@pytest.mark.parametrize("route,headers,status,error", [
    ("/eligibility", {}, 404, "NOT_FOUND"),
    ("/runtime/invoke", {"Origin": "https://external.invalid"}, 403, "ORIGIN_NOT_ALLOWED"),
    ("/runtime/invoke", {"Content-Type": "text/plain"}, 415, "JSON_REQUIRED"),
    # Draining must not alter path -> origin -> content-type rejection priority.
    ("/eligibility", {"Origin": "https://external.invalid", "Content-Type": "text/plain"}, 404, "NOT_FOUND"),
    ("/runtime/invoke", {"Origin": "https://external.invalid", "Content-Type": "text/plain"}, 403, "ORIGIN_NOT_ALLOWED"),
])
def test_early_reject_drains_bounded_nonempty_post_body(hosted, route, headers, status, error):
    host, url, calls = hosted
    code, body, response_headers = post(url, {"discard": "x" * 65536}, route=route, headers=headers)
    assert code == status
    assert body == {"error": error}
    assert int(response_headers["Content-Length"]) == len(json.dumps(body).encode("utf-8"))
    assert host.handler_invocations == 0 and calls == []


def test_repeated_unsupported_posts_receive_complete_404_without_retry(hosted):
    host, url, calls = hosted
    for index in range(20):
        status, body, _ = post(url, {"index": index, "discard": "x" * 4096}, route="/eligibility")
        assert status == 404
        assert body == {"error": "NOT_FOUND"}
        assert host.handler_invocations == 0 and calls == []


def test_invalid_metadata_inputs_origin_paths_and_sanitized_runtime_failures(hosted):
    host, url, _ = hosted
    assert post(url, {"request": {"request_id": "r", "user_message": "x", "approved": True}})[1]["runtime"]["error"]["code"] == "INVALID_RUNTIME_PAYLOAD"
    assert post(url, {"state": {"status": "HUMAN_APPROVED"}})[1]["runtime"]["error"]["code"] == "INVALID_RUNTIME_PAYLOAD"
    assert host.handler_invocations == 0
    assert post(url, {}, headers={"Origin": "https://external.invalid"})[0] == 403
    assert post(url, {}, route="/eligibility")[0] == 404
    original = host.factory
    def broken(request):
        raise RuntimeError("PRIVATE C:/secret/path API_KEY=secret traceback")
    host.factory = broken
    assert initial(url)[1] == {"runtime": {"error": {"code": "RUNTIME_DEPENDENCY_ERROR", "message": "RUNTIME_DEPENDENCY_ERROR"}}, "presentation": None}
    def bad_core(request):
        session = original(request)
        session.adapter._core.run_turn = broken
        return session
    host.factory = bad_core
    assert initial(url)[1]["runtime"]["error"]["code"] == "CORE_EXECUTION_ERROR"


def test_local_boundary_sdk_is_optional_and_no_mcp_or_domain_http_shortcut():
    path = ROOT / "backend/competition_copilot/integrations/local_runtime/http.py"
    imports = [n.module or "" for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.ImportFrom)]
    assert not any(".domain" in name or ".mcp" in name or "agentarts.sdk" in name for name in imports)
    with pytest.raises(ValueError):
        create_server(None, bind="0.0.0.0")
    result = subprocess.run([sys.executable, "-c", "import sys;sys.path.insert(0,'backend');from competition_copilot.integrations.local_runtime.composition import create_local_host;assert 'agentarts.sdk' not in sys.modules"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_controlled_fixture_and_public_plan_ref_remain_canonical():
    export = runpy.run_path(str(ROOT / "scripts/export_local_runtime_fixture.py"))
    assert (ROOT / "data/local_runtime/controlled_revision.json").read_text(encoding="utf-8") == export["fixture"]()
    from competition_copilot.domain.replanning import PlanReference
    from competition_copilot.domain.replanning_input import ReplanningInput
    value = json.loads(export["fixture"]())
    source = ReplanningInput.model_validate(value["proposal"])
    assert PlanReference.from_plan(source.before).model_dump(mode="json") == PLAN
