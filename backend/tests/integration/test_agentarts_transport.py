"""Offline AgentArts ExecuteRuntime transport/identity/credential/parity tests."""

import ast
import asyncio
import json
import runpy
import socket
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from competition_copilot.integrations.agentarts_transport.gateway import (
    GatewayConfig,
    GatewayFailure,
    safe_delivery,
)

ROOT = Path(__file__).resolve().parents[3]
HARNESS = runpy.run_path(str(ROOT / "backend/tests/agentarts_gateway_harness.py"))
PLAN = json.loads((ROOT / "frontend/src/demo/local-plan.json").read_text())
STAMP = HARNESS["NOW"].isoformat()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    connect = socket.socket.connect

    def guarded(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return connect(sock, address)
        pytest.fail("External network forbidden in compatibility tests")

    monkeypatch.setattr(socket.socket, "connect", guarded)


@pytest.fixture
def env():
    with HARNESS["running"]() as value:
        yield value


def post(url, body, *, session="transport-session", path="/runtime/agentarts/competition-copilot/invoke"):
    request = Request(url + path, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "X-Copilot-Session-Id": session})
    try:
        response = urlopen(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def pair(env, payload):
    left = post(env["local"], payload, path="/runtime/invoke")
    right = post(env["bridge"], payload)
    assert left == right
    assert env["records"][-1]["body"] == payload
    return right[1]


@pytest.mark.parametrize("message,context", [
    ("discovery", {}),
    ("eligibility", {"student_id": "local-graduate", "competition_id": "gcxl-engineering-practice-innovation", "edition_id": "gcxl-engineering-practice-innovation-2027"}),
    ("eligibility", {"student_id": "local-unknown", "competition_id": "gcxl-engineering-practice-innovation", "edition_id": "gcxl-engineering-practice-innovation-2027"}),
    ("skill", {"student_id": "local-graduate", "competition_id": "comap-mcm", "edition_id": "comap-mcm-2027"}),
    ("plan", {"student_id": "local-graduate", "competition_id": "comap-mcm", "edition_id": "comap-mcm-2027"}),
    ("recommend", {"student_id": "local-graduate", "competition_id": "comap-mcm", "edition_id": "comap-mcm-2027"}),
])
def test_real_business_and_grounding_parity(env, message, context):
    result = pair(env, {"request": {"request_id": " request-1 ", "user_message": message, "context": context}})
    assert result["runtime"]["response"]["request_id"] == "request-1"
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    assert result["presentation"]["artifacts"]
    record = env["records"][-1]
    assert record["path"] == "/runtimes/competition-copilot/invocations?endpoint=dev"
    assert record["authorized"] and record["accept"] == "application/json"
    assert record["session"] == "transport-session" and record["user"] == "gateway-observer"
    assert record["mcp"] is None


def test_clarification_continuation_parity_and_session_is_not_authority(env):
    initial = pair(env, {"request": {"request_id": "r", "user_message": "detail"}})
    runtime = initial["runtime"]
    question = runtime["response"]["clarification"]
    reply = {"continuation_ref": runtime["continuation_ref"], "clarification": {
        "source_request_id": "r", "clarification_id": question["clarification_id"],
        "values": {"competition_id": "huawei-ict"}, "submitted_at": STAMP}}
    left = post(env["local"], reply, path="/runtime/invoke")
    right = post(env["bridge"], reply, session="different-session")
    assert left == right and right[1]["runtime"]["response"]["outcome"] == "COMPLETED"
    # Same cloud session cannot authorize a used continuation.
    assert post(env["bridge"], reply)[1]["runtime"]["error"]["code"] == "CORE_VALIDATION_ERROR"


@pytest.mark.parametrize("decision", ["APPROVE", "REJECT"])
def test_approval_authority_plan_diff_parity(env, decision):
    pending = pair(env, {"request": {"request_id": "r", "user_message": "controlled revision", "context": {"plan_ref": PLAN}}})
    runtime = pending["runtime"]
    proposal = runtime["response"]["approval_request"]
    assert proposal["before_plan"] == PLAN and proposal["affected_scope_ref"]
    reply = {"continuation_ref": runtime["continuation_ref"], "approval": {
        "source_request_id": "r", "approval_request_id": proposal["approval_request_id"],
        "decision": decision, "submitted_at": STAMP}}
    assert "HUMAN_APPROVED" not in json.dumps(reply)
    result = pair(env, reply)
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    diffs = [a for a in result["presentation"]["artifacts"] if a["model"] == "PlanDiff"]
    assert bool(diffs) == (decision == "APPROVE")
    if diffs:
        assert diffs[0]["value"]["status_change"] == {"field": "status", "before_status": "active", "after_status": "cancelled"}


@pytest.mark.parametrize("status,expected", [(401, "AGENTARTS_AUTH_ERROR"), (403, "AGENTARTS_AUTH_ERROR"), (404, "AGENTARTS_RUNTIME_NOT_FOUND"), (500, "AGENTARTS_SERVER_ERROR"), (503, "AGENTARTS_SERVER_ERROR"), (302, "AGENTARTS_HTTP_ERROR")])
def test_safe_error_mapping_exactly_one_upstream_call(env, status, expected):
    env["gateway_server"].fault = {"status": status, "body": {"message": "PRIVATE C:/path traceback Authorization=secret"}}
    code, body = post(env["bridge"], {"request": {"request_id": "r", "user_message": "discovery"}})
    assert code == 502 and body == {"error": expected}
    assert len(env["records"]) == 1 and env["remote"].handler_invocations == 0


def test_timeout_no_retry_and_invalid_payload_no_upstream(env):
    assert post(env["bridge"], {"state": "HUMAN_APPROVED"})[0] == 400
    assert not env["records"]
    env["gateway_server"].fault = {"delay": 0.8, "body": {}}
    assert post(env["bridge"], {"request": {"request_id": "r", "user_message": "discovery"}}) == (504, {"error": "AGENTARTS_TIMEOUT"})
    assert len(env["records"]) == 1


def test_gateway_network_failure_is_sanitized(monkeypatch):
    from competition_copilot.integrations.agentarts_transport.gateway import (
        AgentArtsGatewayClient,
    )
    client = AgentArtsGatewayClient(GatewayConfig("https://gateway.invalid", "runtime-name", "Bearer not-a-credential"))
    def fail(*args, **kwargs):
        raise OSError("PRIVATE TOKEN and local path")
    monkeypatch.setattr("http.client.HTTPSConnection.request", fail)
    with pytest.raises(GatewayFailure, match="^AGENTARTS_NETWORK_ERROR$"):
        client.invoke({"request": {"request_id": "r", "user_message": "x"}}, "session")


@pytest.mark.parametrize("changes", [
    {"runtime_name": True}, {"runtime_name": "bad/name"}, {"runtime_name": "a"},
    {"gateway_url": "http://external.invalid"}, {"gateway_url": "https://user:secret@gateway.invalid"},
    {"authorization": "Bearer token\r\nX-Evil: yes"}, {"authorization": "Bearer "},
    {"timeout": True}, {"timeout": 0}, {"timeout": float("inf")},
    {"gateway_user_id": "bad\nuser"}, {"endpoint": "../bad"},
    {"allow_loopback_http": "yes"},
])
def test_strict_server_config_no_secret_repr(changes):
    values = {"gateway_url": "https://gateway.invalid", "runtime_name": "runtime-name", "authorization": "Bearer synthetic-not-a-credential"}
    with pytest.raises(ValueError, match="^INVALID_AGENTARTS_SERVER_CONFIG$"):
        GatewayConfig(**{**values, **changes})
    assert "synthetic-not-a-credential" not in repr(GatewayConfig(**values))


def test_private_or_invalid_upstream_cannot_reach_browser():
    valid = {"runtime": {"response": {"request_id": "r", "intent": "DISCOVER_COMPETITIONS", "outcome": "COMPLETED", "message": "ready"}}, "presentation": None}
    assert safe_delivery(valid) == valid
    for handle in ({"state": "private"}, [], "", "unexpected-handle"):
        assert safe_delivery({"runtime": {**valid["runtime"], "continuation_ref": handle}}) == {"runtime": None, "presentation": None}
    assert safe_delivery({"response": {}, "continuation": {"state": "private"}}) == {"runtime": None, "presentation": None}
    assert safe_delivery({"runtime": {"response": {}, "continuation": {"state": "private"}}}) == {"runtime": None, "presentation": None}
    assert safe_delivery({"runtime": {"error": {"code": "CORE_EXECUTION_ERROR", "message": "PRIVATE token traceback"}}}) == {"runtime": {"error": {"code": "CORE_EXECUTION_ERROR", "message": "CORE_EXECUTION_ERROR"}}, "presentation": None}


def test_bridge_rejects_unknown_routes_origin_and_content_type_without_upstream(env):
    for path, headers, expected in [
        ("/agentarts/eligibility", {}, 404),
        ("/runtime/agentarts/another-runtime/invoke", {}, 404),
        ("/runtime/agentarts/competition-copilot/invoke", {"Origin": "https://external.invalid"}, 403),
        ("/runtime/agentarts/competition-copilot/invoke", {"Content-Type": "text/plain"}, 415),
    ]:
        request = Request(env["bridge"] + path, data=json.dumps({"discard": "x" * 65536}).encode(),
                          headers={"Content-Type": "application/json", **headers})
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=5)
        assert error.value.code == expected
        error.value.close()
    assert not env["records"] and env["remote"].handler_invocations == 0
    assert post(env["bridge"], {"request": {"request_id": "r", "user_message": "discovery"}}, session="bad\tvalue")[0] == 400
    assert not env["records"]


def test_bridge_has_no_business_mcp_or_sdk_imports():
    for name in ("bridge.py", "gateway.py"):
        tree = ast.parse((ROOT / "backend/competition_copilot/integrations/agentarts_transport" / name).read_text())
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(".domain" in item or ".mcp" in item or ".agents.agent" in item or "agentarts.sdk" in item for item in imports)


def test_hosted_sdk_entrypoint_uses_existing_private_host(env, monkeypatch):
    pytest.importorskip("agentarts.sdk")
    from agentarts.sdk import AgentArtsRuntimeApp

    from competition_copilot.integrations.agentarts_transport.hosting import (
        create_hosted_app,
    )
    registered = []
    original = AgentArtsRuntimeApp.entrypoint
    def capture(self, handler):
        registered.append(handler)
        return original(self, handler)
    monkeypatch.setattr(AgentArtsRuntimeApp, "entrypoint", capture)
    create_hosted_app(env["remote"])
    value = asyncio.run(registered[0]({"request": {"request_id": "r", "user_message": "discovery"}}))
    assert value["runtime"]["response"]["outcome"] == "COMPLETED"
    assert "continuation" not in value["runtime"]
