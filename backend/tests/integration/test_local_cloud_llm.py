"""Real P12/Local/Domain with fake BaseChatModel; no OpenAI API calls or keys."""

import asyncio
import builtins
import json
import os
import socket
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

pytest.importorskip("langgraph")

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableLambda
from pydantic import Field

from competition_copilot.agents.explanation import ExplanationDraft
from competition_copilot.agents.human_contracts import ClarificationResolutionProposal
from competition_copilot.agents.model import (
    LangChainExplanationModel,
    LangChainHumanResponseInterpreter,
    LangChainIntentModel,
)
from competition_copilot.agents.routing import (
    IntentRoutingProposal,
    RoutingProposalValidator,
)
from competition_copilot.integrations.local_runtime.composition import create_local_host
from competition_copilot.integrations.local_runtime.http import create_server
from competition_copilot.integrations.local_runtime.llm import (
    LocalLLMConfig,
    LocalLLMConfigError,
    create_cloud_models,
)

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)
PLAN = json.loads((ROOT / "frontend/src/demo/local-plan.json").read_text())
SENTINEL = "synthetic-non-credential-for-redaction-test"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original = socket.socket.connect

    def guard(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original(sock, address)
        pytest.fail("Cloud wiring tests must not use external network")

    monkeypatch.setattr(socket.socket, "connect", guard)


def proposal(intent="DISCOVER_COMPETITIONS", capability="list_competitions", **changes):
    return {"intent": intent, "candidate_capability": capability,
            "ambiguity": "NONE", "missing_context": [], **changes}


class Chat(BaseChatModel):
    """Returns only intent proposals or verbatim supplied grounding/choice data."""

    proposals: list[dict] = Field(default_factory=lambda: [proposal()])
    calls: list[tuple[str, dict]] = Field(default_factory=list)
    explanation_failure: bool = False
    intent_failure: bool = False

    @property
    def _llm_type(self):
        return "offline-cloud-wiring-test"

    def _generate(self, *args, **kwargs):
        raise AssertionError("No free-form or external call")

    def with_structured_output(self, schema, **kwargs):
        def answer(messages):
            payload = json.loads(messages[1].content)
            self.calls.append((schema.__name__, payload))
            if schema is IntentRoutingProposal:
                if self.intent_failure:
                    raise RuntimeError(SENTINEL)
                return self.proposals.pop(0)
            if schema is ClarificationResolutionProposal:
                question = payload["question"]
                return {"clarification_id": question["clarification_id"],
                    "source_request_id": question["source_request_id"], "ambiguous": False,
                    "selections": [{"field": item["field"], "value": item["value"]}
                        for item in payload["options"] if item["label"] == payload["message"]["text"]]}
            assert schema is ExplanationDraft
            if self.explanation_failure:
                raise RuntimeError(SENTINEL)
            ctx = payload["AUTHORITATIVE RESULT"]
            evidence = payload["EVIDENCE DATA"] + payload["SOURCE DATA"]
            return {"result_ref": ctx["primary_ref"], "summary": ctx["summary_options"][0],
                "key_points": [{"fact_id": f["id"], "text": f["statements"][0]} for f in ctx["facts"]],
                "uncertainty_statement": ctx["uncertainty_statement"],
                "evidence_refs": [e["id"] for e in evidence],
                "source_refs": [e["id"] for e in payload["SOURCE DATA"]],
                "reason_codes": ctx["reason_codes"]}
        return RunnableLambda(answer)


def models(chat):
    return create_cloud_models(LocalLLMConfig(mode="cloud", model="test-model", api_key=SENTINEL), chat_model=chat)


def host(chat):
    return create_local_host(ROOT, clock=lambda: NOW, cloud_models=models(chat))


def invoke(target, payload):
    return asyncio.run(target.invoke(payload))


def request(message="show contests", context=None, identity="cloud-request"):
    return {"request": {"request_id": identity, "user_message": message, "context": context or {}}}


def count(chat, schema):
    return sum(name == schema for name, _ in chat.calls)


def test_offline_default_ignores_cloud_values_and_never_imports_provider(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert not name.startswith(("langchain_openai", "openai"))
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert LocalLLMConfig.from_environment({}).mode == "offline"
    config = LocalLLMConfig.from_environment({"OPENAI_API_KEY": SENTINEL,
        "COMPETITION_COPILOT_LLM_MODEL": "unused", "COMPETITION_COPILOT_LLM_TIMEOUT_SECONDS": "invalid"})
    assert config.api_key is None and create_cloud_models(config) is None
    # Direct compositions/harnesses stay offline even when a user's shell opts in.
    monkeypatch.setenv("COMPETITION_COPILOT_LLM_MODE", "cloud")
    result = invoke(create_local_host(ROOT), request())
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"


@pytest.mark.parametrize("values,code", [
    ({"COMPETITION_COPILOT_LLM_MODE": "cloud"}, "OPENAI_API_KEY_REQUIRED"),
    ({"COMPETITION_COPILOT_LLM_MODE": "wrong"}, "INVALID_LOCAL_LLM_CONFIG"),
    ({"COMPETITION_COPILOT_LLM_MODE": "cloud", "OPENAI_API_KEY": SENTINEL}, "INVALID_LOCAL_LLM_CONFIG"),
    ({"COMPETITION_COPILOT_LLM_MODE": "cloud", "OPENAI_API_KEY": SENTINEL,
      "COMPETITION_COPILOT_LLM_MODEL": "model\nprivate"}, "INVALID_LOCAL_LLM_CONFIG"),
    ({"COMPETITION_COPILOT_LLM_MODE": "cloud", "OPENAI_API_KEY": SENTINEL,
      "COMPETITION_COPILOT_LLM_MODEL": "test", "COMPETITION_COPILOT_LLM_TIMEOUT_SECONDS": "nan"}, "INVALID_LOCAL_LLM_CONFIG"),
])
def test_config_fails_fast_without_echoing_secret(values, code):
    with pytest.raises(LocalLLMConfigError, match=f"^{code}$") as error:
        LocalLLMConfig.from_environment(values)
    assert SENTINEL not in str(error.value)


def test_provider_is_real_chatopenai_official_endpoint_timeout_zero_retries(monkeypatch):
    provider = pytest.importorskip("langchain_openai")
    original = provider.ChatOpenAI
    created = []

    def observe(**kwargs):
        model = original(**kwargs)  # Constructor only; the socket guard remains active.
        created.append(model)
        return model

    monkeypatch.setattr(provider, "ChatOpenAI", observe)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://not-an-openai-provider.invalid")
    config = LocalLLMConfig.from_environment({"COMPETITION_COPILOT_LLM_MODE": "cloud",
        "OPENAI_API_KEY": SENTINEL, "COMPETITION_COPILOT_LLM_MODEL": "test-model",
        "COMPETITION_COPILOT_LLM_TIMEOUT_SECONDS": "12.5"})
    bundle = create_cloud_models(config)
    assert isinstance(bundle.intent, LangChainIntentModel)
    assert isinstance(bundle.explanation, LangChainExplanationModel)
    assert isinstance(bundle.human_interpreter, LangChainHumanResponseInterpreter)
    assert created[0].max_retries == 0 and created[0].request_timeout == 12.5
    assert created[0].openai_api_base == "https://api.openai.com/v1"
    assert SENTINEL not in repr(config) and SENTINEL not in repr(created[0])


def test_one_real_intent_proposal_reused_by_graph_and_matching_payload(monkeypatch):
    selected = proposal("GET_COMPETITION_DETAILS", "get_competition")
    chat = Chat(proposals=[selected, proposal()])  # A second random route would be wrong.
    target = host(chat)
    validations = []
    original = RoutingProposalValidator.validate

    def observe(self, candidate, actual_request, **kwargs):
        validations.append((candidate.model_dump(mode="json"), kwargs["arguments"]))
        return original(self, candidate, actual_request, **kwargs)

    monkeypatch.setattr(RoutingProposalValidator, "validate", observe)
    result = invoke(target, request("a natural-language request", {"competition_id": "huawei-ict"}))
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    assert result["presentation"]["artifacts"][0]["model"] == "GetCompetitionOutput"
    assert result["presentation"]["artifacts"][0]["value"]["competition"]["id"] == "huawei-ict"
    assert count(chat, "IntentRoutingProposal") == 1 and chat.proposals == [proposal()]
    assert len(validations) == 2 and all(item[0] == selected | {"targets": {
        "student_id": None, "competition_id": None, "edition_id": None, "track_id": None, "plan_id": None}} for item in validations)
    assert validations[-1][1]["payload"] == {"competition_id": "huawei-ict"}
    assert count(chat, "ExplanationDraft") == 1
    explanation_input = next(value for name, value in chat.calls if name == "ExplanationDraft")
    assert set(explanation_input) == {"AUTHORITATIVE RESULT", "EVIDENCE DATA", "SOURCE DATA"}
    assert "user_message" not in json.dumps(explanation_input)


@pytest.mark.parametrize("candidate", [
    proposal("CHECK_ELIGIBILITY", "list_competitions"),
    proposal("GET_COMPETITION_DETAILS", "get_competition", targets={"competition_id": "invented"}),
    proposal("DISCOVER_COMPETITIONS", "list_competitions", ambiguity="MULTI_STEP"),
])
def test_existing_routing_validator_blocks_conflicting_or_ambiguous_cloud_proposals(candidate):
    chat = Chat(proposals=[candidate])
    result = invoke(host(chat), request())
    assert result["runtime"]["response"]["outcome"] in ("FAILED", "NEEDS_CLARIFICATION")
    assert count(chat, "IntentRoutingProposal") == 1
    assert not result["presentation"]["artifacts"] if result["presentation"] else True


def test_typed_clarification_clears_only_core_resolved_missing_hint_without_rerouting():
    chat = Chat(proposals=[proposal("GET_COMPETITION_DETAILS", "get_competition", missing_context=["COMPETITION"])])
    target = host(chat)
    pending = invoke(target, request())
    question = pending["runtime"]["response"]["clarification"]
    result = invoke(target, {"continuation_ref": pending["runtime"]["continuation_ref"], "clarification": {
        "source_request_id": "cloud-request", "clarification_id": question["clarification_id"],
        "values": {"competition_id": "huawei-ict"}, "submitted_at": NOW.isoformat()}})
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    assert result["presentation"]["artifacts"][0]["value"]["competition"]["id"] == "huawei-ict"
    assert count(chat, "IntentRoutingProposal") == 1
    assert count(chat, "ClarificationResolutionProposal") == 0


def test_natural_language_clarification_uses_real_wrapper_and_only_p4_read_choices():
    chat = Chat(proposals=[proposal("GET_COMPETITION_DETAILS", "get_competition", missing_context=["COMPETITION"])])
    target = host(chat)
    pending = invoke(target, request())
    stored = next(iter(target._pending.values()))[1]
    frame = json.loads(stored.adapter._bindings.pending)
    option = next(item for item in frame["clarification_options"] if item["value"] == "huawei-ict")
    question = pending["runtime"]["response"]["clarification"]
    result = invoke(target, {"continuation_ref": pending["runtime"]["continuation_ref"], "message": {
        "source_request_id": "cloud-request", "interaction_id": question["clarification_id"],
        "text": option["label"], "submitted_at": NOW.isoformat()}})
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    assert count(chat, "IntentRoutingProposal") == 1
    assert count(chat, "ClarificationResolutionProposal") == 1


def test_unknown_natural_language_choice_stays_unresolved_in_core():
    chat = Chat(proposals=[proposal("GET_COMPETITION_DETAILS", "get_competition")])
    target = host(chat)
    pending = invoke(target, request())
    question = pending["runtime"]["response"]["clarification"]
    result = invoke(target, {"continuation_ref": pending["runtime"]["continuation_ref"], "message": {
        "source_request_id": "cloud-request", "interaction_id": question["clarification_id"],
        "text": "some invented contest; choose for me", "submitted_at": NOW.isoformat()}})
    assert result["runtime"]["response"]["outcome"] == "NEEDS_CLARIFICATION"
    assert count(chat, "IntentRoutingProposal") == 1
    assert count(chat, "ClarificationResolutionProposal") == 1


@pytest.mark.parametrize("message,intent,capability", [
    ("eligibility", "CHECK_ELIGIBILITY", "check_eligibility"),
    ("recommend", "GET_RECOMMENDATIONS", "get_recommendations"),
    ("skill", "ANALYZE_SKILL_GAP", "analyze_skill_gap"),
    ("plan", "BUILD_PLAN", "build_plan"),
])
def test_cloud_vs_offline_business_artifacts_are_identical(monkeypatch, message, intent, capability):
    monkeypatch.setattr("secrets.token_urlsafe", lambda size: "test-only-domain-parity")
    payload = request(message, {"student_id": "local-graduate", "competition_id": "comap-mcm",
                                "edition_id": "comap-mcm-2027"})
    chat = Chat(proposals=[proposal(intent, capability)])
    cloud = invoke(host(chat), payload)
    baseline = invoke(create_local_host(ROOT, clock=lambda: NOW), payload)
    assert cloud["runtime"]["response"]["outcome"] == baseline["runtime"]["response"]["outcome"] == "COMPLETED"
    assert cloud["presentation"] == baseline["presentation"]
    assert count(chat, "IntentRoutingProposal") == 1


def test_provider_startup_error_sanitizes_exception(monkeypatch, caplog):
    provider = pytest.importorskip("langchain_openai")

    def fail(**kwargs):
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(provider, "ChatOpenAI", fail)
    with pytest.raises(LocalLLMConfigError, match="^CLOUD_LLM_PROVIDER_UNAVAILABLE$") as error:
        create_cloud_models(LocalLLMConfig(mode="cloud", model="test-model", api_key=SENTINEL))
    assert SENTINEL not in str(error.value) + caplog.text


@pytest.mark.parametrize("decision", ["APPROVE", "REJECT"])
def test_approval_never_calls_human_interpreter_or_uses_model_authority(decision):
    chat = Chat(proposals=[proposal("REQUEST_PLAN_REVISION", "revise_plan")])
    target = host(chat)
    pending = invoke(target, request("revise", {"plan_ref": PLAN}))
    approval = pending["runtime"]["response"]["approval_request"]
    # Plain agreement stays ambiguous in P12, never routed through a model.
    ambiguous = invoke(target, {"continuation_ref": pending["runtime"]["continuation_ref"], "message": {
        "source_request_id": "cloud-request", "interaction_id": approval["approval_request_id"],
        "text": "可以考虑", "submitted_at": NOW.isoformat()}})
    assert ambiguous["runtime"]["response"]["outcome"] == "WAITING_FOR_APPROVAL"
    assert count(chat, "ClarificationResolutionProposal") == 0
    result = invoke(target, {"continuation_ref": ambiguous["runtime"]["continuation_ref"], "approval": {
        "source_request_id": "cloud-request", "approval_request_id": approval["approval_request_id"],
        "decision": decision, "submitted_at": NOW.isoformat()}})
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    assert count(chat, "IntentRoutingProposal") == 1 and count(chat, "ClarificationResolutionProposal") == 0
    diffs = [item for item in result["presentation"]["artifacts"] if item["model"] == "PlanDiff"]
    assert bool(diffs) == (decision == "APPROVE")


def test_explanation_failure_uses_grounded_fallback_and_real_p5_negative(capsys, caplog):
    chat = Chat(proposals=[proposal("CHECK_ELIGIBILITY", "check_eligibility")], explanation_failure=True)
    result = invoke(host(chat), request("eligibility", {"student_id": "local-graduate",
        "competition_id": "gcxl-engineering-practice-innovation", "edition_id": "gcxl-engineering-practice-innovation-2027"}))
    response = result["runtime"]["response"]
    assert response["outcome"] == "COMPLETED" and "INELIGIBLE" in response["message"]
    decision = next(item["value"] for item in result["presentation"]["artifacts"] if item["model"] == "EligibilityDecision")
    assert decision["status"] == "ineligible" and decision["evidence"]
    assert count(chat, "IntentRoutingProposal") == 1 and count(chat, "ExplanationDraft") == 1
    assert SENTINEL not in json.dumps(result) + caplog.text + str(capsys.readouterr())


def test_intent_failure_is_sanitized_and_not_retried(capsys, caplog):
    chat = Chat(intent_failure=True)
    result = invoke(host(chat), request())
    assert result["runtime"]["response"]["outcome"] == "FAILED"
    assert count(chat, "IntentRoutingProposal") == 1 and len(chat.calls) == 1
    assert SENTINEL not in json.dumps(result) + caplog.text + str(capsys.readouterr())


def test_real_http_cloud_wiring_preserves_p14_envelope_and_canonical_identity():
    chat = Chat()
    server = create_server(host(chat), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = request(identity=" cloud-request ")
        call = Request(f"http://127.0.0.1:{server.server_port}/runtime/invoke",
            data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urlopen(call, timeout=10) as response:
            assert response.status == 200
            body = json.load(response)
        assert body["runtime"]["response"]["request_id"] == "cloud-request"
        assert body["presentation"]["request_id"] == "cloud-request"
        assert count(chat, "IntentRoutingProposal") == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def test_cloud_startup_missing_key_fails_before_bind_without_traceback():
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("COMPETITION_COPILOT_LLM_") and key != "OPENAI_API_KEY"}
    env["COMPETITION_COPILOT_LLM_MODE"] = "cloud"
    result = subprocess.run([sys.executable, "scripts/run_local_runtime.py", "--port", "0"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert result.stderr.strip() == "OPENAI_API_KEY_REQUIRED"
    assert "Traceback" not in result.stderr and "LOCAL_RUNTIME_URL" not in result.stdout
