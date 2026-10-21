"""Cloud missing-context hints never override real bindings or P12 validation."""

import json
import socket
import threading
from urllib.request import Request, urlopen

import pytest

pytest.importorskip("langgraph")

import httpx
from test_local_cloud_llm import (
    NOW,
    ROOT,
    SENTINEL,
    Chat,
    count,
    invoke,
    proposal,
    request,
)

from competition_copilot.agents.contracts import ContextField
from competition_copilot.agents.routing import RoutingProposalValidator
from competition_copilot.integrations.local_runtime.composition import create_local_host
from competition_copilot.integrations.local_runtime.http import create_server
from competition_copilot.integrations.local_runtime.llm import (
    LocalLLMConfig,
    create_cloud_models,
)

COMPETITION = "gcxl-engineering-practice-innovation"
EDITION = "gcxl-engineering-practice-innovation-2027"
MESSAGE = "帮我看看我适不适合参加这个比赛"


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    original = socket.socket.connect

    def guard(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original(sock, address)
        pytest.fail("Authority regression must not call external network")

    monkeypatch.setattr(socket.socket, "connect", guard)

    def forbid_fallback(*args, **kwargs):
        pytest.fail("Cloud failures must not construct OfflineIntentModel")

    monkeypatch.setattr("competition_copilot.integrations.local_runtime.composition.OfflineIntentModel", forbid_fallback)


def context(student="local-graduate"):
    return {"student_id": student, "competition_id": COMPETITION, "edition_id": EDITION}


def cloud(chat, provider="bigmodel"):
    bundle = create_cloud_models(LocalLLMConfig(mode="cloud", provider=provider,
        model="test-model", api_key=SENTINEL), chat_model=chat)
    return create_local_host(ROOT, clock=lambda: NOW, cloud_models=bundle)


@pytest.mark.parametrize("provider", ["bigmodel", "openai", "deepseek"])
@pytest.mark.parametrize("student,status", [("local-graduate", "ineligible"), ("local-unknown", "unknown")])
@pytest.mark.parametrize("hints", [["STUDENT_PROFILE"], [field.value for field in ContextField]])
def test_complete_context_executes_real_p5_regardless_of_model_hints(provider, student, status, hints, monkeypatch):
    selected = proposal("CHECK_ELIGIBILITY", "check_eligibility", missing_context=hints)
    chat = Chat(proposals=[selected, proposal()])
    observed = []
    original = RoutingProposalValidator.validate

    def validate(self, candidate, actual_request, **kwargs):
        result = original(self, candidate, actual_request, **kwargs)
        observed.append((candidate.model_dump(), kwargs["arguments"], result.status))
        return result

    monkeypatch.setattr(RoutingProposalValidator, "validate", validate)
    result = invoke(cloud(chat, provider), request(MESSAGE, context(student)))
    response = result["runtime"]["response"]
    assert response["outcome"] == "COMPLETED" and response["intent"] == "CHECK_ELIGIBILITY"
    decision = next(a["value"] for a in result["presentation"]["artifacts"] if a["model"] == "EligibilityDecision")
    assert decision["status"] == status and decision["evidence"]
    assert len(observed) == 2 and observed[0][0] == observed[1][0]
    assert all(item[0]["missing_context"] == () for item in observed)
    assert observed[-1][2] == "READY"
    assert observed[-1][1]["payload"]["student"]["id"] == student
    assert count(chat, "IntentRoutingProposal") == 1 and chat.proposals == [proposal()]
    assert selected["missing_context"] == hints  # Source model data was not mutated.


@pytest.mark.parametrize("hints", [[], ["STUDENT_PROFILE"], [field.value for field in ContextField]])
def test_empty_context_always_asks_deterministic_required_fields(hints):
    chat = Chat(proposals=[proposal("CHECK_ELIGIBILITY", "check_eligibility", missing_context=hints)])
    result = invoke(cloud(chat), request(MESSAGE))
    response = result["runtime"]["response"]
    assert response["outcome"] == "NEEDS_CLARIFICATION"
    assert set(response["clarification"]["fields"]) == {"COMPETITION", "EDITION", "STUDENT_PROFILE"}
    assert count(chat, "IntentRoutingProposal") == 1


@pytest.mark.parametrize("missing,field", [("student_id", "STUDENT_PROFILE"),
    ("competition_id", "COMPETITION"), ("edition_id", "EDITION")])
def test_each_missing_reference_still_produces_real_clarification(missing, field):
    values = context()
    del values[missing]
    expected = {field}
    if missing == "competition_id":
        # Frozen AgentContext forbids an edition reference without its parent.
        del values["edition_id"]
        expected.add("EDITION")
    chat = Chat(proposals=[proposal("CHECK_ELIGIBILITY", "check_eligibility", missing_context=[])])
    result = invoke(cloud(chat), request(MESSAGE, values))
    assert result["runtime"]["response"]["outcome"] == "NEEDS_CLARIFICATION"
    assert set(result["runtime"]["response"]["clarification"]["fields"]) == expected
    assert count(chat, "IntentRoutingProposal") == 1


def test_unknown_student_reference_does_not_fabricate_profile():
    chat = Chat(proposals=[proposal("CHECK_ELIGIBILITY", "check_eligibility", missing_context=[])])
    result = invoke(cloud(chat), request(MESSAGE, context("nonexistent-profile")))
    response = result["runtime"]["response"]
    assert response["outcome"] == "NEEDS_CLARIFICATION"
    assert response["clarification"]["fields"] == ["STUDENT_PROFILE"]
    assert not result["presentation"] or not result["presentation"]["artifacts"]
    assert count(chat, "IntentRoutingProposal") == 1


@pytest.mark.parametrize("changes", [
    {"intent": "UNKNOWN", "candidate_capability": None, "ambiguity": "INTENT"},
    {"ambiguity": "INTENT"}, {"ambiguity": "TARGET"}, {"ambiguity": "MULTI_STEP"},
])
def test_genuine_unknown_or_ambiguity_still_requests_intent(changes, monkeypatch):
    selected = proposal("CHECK_ELIGIBILITY", "check_eligibility", missing_context=["STUDENT_PROFILE"]) | changes
    chat = Chat(proposals=[selected])
    seen = []
    original = RoutingProposalValidator.validate

    def validate(self, candidate, *args, **kwargs):
        seen.append(candidate)
        return original(self, candidate, *args, **kwargs)

    monkeypatch.setattr(RoutingProposalValidator, "validate", validate)
    result = invoke(cloud(chat), request(MESSAGE, context()))
    response = result["runtime"]["response"]
    assert response["outcome"] == "NEEDS_CLARIFICATION" and response["clarification"]["fields"] == ["INTENT"]
    assert all(p.intent == selected["intent"] and p.candidate_capability == selected["candidate_capability"]
               and p.ambiguity == selected["ambiguity"] and not p.missing_context for p in seen)
    assert count(chat, "IntentRoutingProposal") == 1


def test_normalizing_hints_does_not_erase_asserted_target_conflict():
    chat = Chat(proposals=[proposal("CHECK_ELIGIBILITY", "check_eligibility",
        missing_context=["STUDENT_PROFILE"], targets={"student_id": "invented-profile"})])
    result = invoke(cloud(chat), request(MESSAGE, context()))
    assert result["runtime"]["response"]["outcome"] == "FAILED"
    assert result["runtime"]["response"]["message"] == "CONTEXT_CONFLICT"
    assert count(chat, "IntentRoutingProposal") == 1


def test_intent_failure_still_fails_closed_without_retry_or_fallback(caplog):
    chat = Chat(intent_failure=True)
    result = invoke(cloud(chat), request(MESSAGE, context()))
    assert result["runtime"]["response"]["outcome"] == "FAILED"
    assert result["runtime"]["response"]["message"] == "INTENT_MODEL_FAILED"
    assert count(chat, "IntentRoutingProposal") == 1 and len(chat.calls) == 1
    assert SENTINEL not in json.dumps(result) + caplog.text


@pytest.mark.parametrize("values,status,fields", [
    (context("local-graduate"), "ineligible", None),
    (context("local-unknown"), "unknown", None),
    (context("does-not-exist"), None, {"STUDENT_PROFILE"}),
    ({}, None, {"COMPETITION", "EDITION", "STUDENT_PROFILE"}),
    ({"competition_id": COMPETITION, "edition_id": EDITION}, None, {"STUDENT_PROFILE"}),
    ({"student_id": "local-unknown"}, None, {"COMPETITION", "EDITION"}),
    ({"student_id": "local-unknown", "competition_id": COMPETITION}, None, {"EDITION"}),
])
def test_real_http_and_bigmodel_json_parser_preserve_authoritative_profile_lookup(
    values, status, fields, monkeypatch,
):
    """Fresh Local HTTP host, real intent parser and P5; scripted upstream only."""
    module = pytest.importorskip("langchain_openai")
    original_chat = module.ChatOpenAI
    from competition_copilot.integrations.local_runtime import composition

    original_profile = composition.StudentProfile
    created_profiles, validations, calls = {}, [], []
    original_validate = RoutingProposalValidator.validate

    def observe_profile(**kwargs):
        profile = original_profile(**kwargs)
        created_profiles[profile.id] = profile
        return profile

    def validate(self, candidate, actual_request, **kwargs):
        validations.append((candidate.model_dump(), kwargs["arguments"]))
        return original_validate(self, candidate, actual_request, **kwargs)

    def upstream(req):
        body = json.loads(req.content)
        calls.append(body)
        assert body["response_format"] == {"type": "json_object"} and body["temperature"] == 0.1
        assert "tools" not in body
        candidate = proposal("CHECK_ELIGIBILITY", "check_eligibility", missing_context=["STUDENT_PROFILE"])
        return httpx.Response(200, json={"id": "scripted", "object": "chat.completion", "created": 0,
            "model": "test-model", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(candidate)}}]})

    monkeypatch.setattr(composition, "StudentProfile", observe_profile)
    monkeypatch.setattr(RoutingProposalValidator, "validate", validate)
    with httpx.Client(transport=httpx.MockTransport(upstream)) as client:
        def construct(**kwargs):
            # Explanation uses the existing grounded fake model; only the intent
            # provider uses the real ChatOpenAI JSON parser and mocked HTTP API.
            if "temperature" not in kwargs:
                return Chat()
            return original_chat(**kwargs, http_client=client)

        monkeypatch.setattr(module, "ChatOpenAI", construct)
        bundle = create_cloud_models(LocalLLMConfig(mode="cloud", provider="bigmodel",
            model="test-model", api_key=SENTINEL))
        host = create_local_host(ROOT, clock=lambda: NOW, cloud_models=bundle)
        assert set(created_profiles) == {"local-undergraduate", "local-graduate", "local-unknown",
                                         "local-recommendation-demo"}
        assert isinstance(created_profiles["local-unknown"], original_profile)
        assert created_profiles["local-unknown"].education_level is None
        assert created_profiles["local-graduate"].education_level == "graduate"
        server = create_server(host, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            call = Request(f"http://127.0.0.1:{server.server_port}/runtime/invoke",
                data=json.dumps(request(MESSAGE, values)).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            with urlopen(call, timeout=10) as response:
                assert response.status == 200
                result = json.load(response)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            assert not thread.is_alive()
    assert len(calls) == 1 and host.handler_invocations == 1
    assert len(validations) == 2 and validations[0][0] == validations[1][0]
    assert all(not candidate["missing_context"] for candidate, _ in validations)
    response = result["runtime"]["response"]
    if status is not None:
        assert response["outcome"] == "COMPLETED" and response["intent"] == "CHECK_ELIGIBILITY"
        student = validations[1][1]["payload"]["student"]
        assert student == created_profiles[values["student_id"]].model_dump(mode="json")
        decision = next(a["value"] for a in result["presentation"]["artifacts"] if a["model"] == "EligibilityDecision")
        assert decision["status"] == status
    else:
        assert response["outcome"] == "NEEDS_CLARIFICATION"
        assert set(response["clarification"]["fields"]) == fields
        if values.get("student_id") == "does-not-exist":
            assert "student" not in validations[1][1]["payload"]
