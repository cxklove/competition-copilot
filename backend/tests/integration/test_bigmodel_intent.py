"""Intent-only configuration, real JSON parser/core and prompt regression; no cloud."""

import json
import socket

import pytest

pytest.importorskip("langgraph")

import httpx
from test_local_cloud_llm import ROOT, SENTINEL, invoke, proposal, request

from competition_copilot.agents.prompts import INTENT_ROUTING_PROMPT
from competition_copilot.agents.routing import RoutingProposalValidator
from competition_copilot.integrations.local_runtime.composition import create_local_host
from competition_copilot.integrations.local_runtime.llm import (
    LocalLLMConfig,
    LocalLLMConfigError,
    create_cloud_models,
)


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    original = socket.socket.connect

    def guard(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original(sock, address)
        pytest.fail("BigModel tests must never use external network")

    monkeypatch.setattr(socket.socket, "connect", guard)


def config(**changes):
    return LocalLLMConfig(mode="cloud", provider="bigmodel", model="operator-selected-model",
                          api_key=SENTINEL, **changes)


def test_role_defaults_and_generic_method_cannot_accidentally_override_intent():
    for generic in (None, "function_calling", "json_schema", "json_mode"):
        selected = config(structured_method=generic)
        assert selected.intent_structured_method == "json_mode" and selected.intent_temperature == 0.1
        assert selected.structured_method == (generic or "function_calling")
    selected = config(intent_structured_method="function_calling", intent_temperature=0.2)
    assert selected.intent_structured_method == "function_calling" and selected.intent_temperature == 0.2


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_other_providers_keep_default_temperature_and_method(provider):
    selected = LocalLLMConfig(mode="cloud", provider=provider, model="selected", api_key=SENTINEL)
    assert selected.intent_temperature is None
    assert selected.intent_structured_method == selected.structured_method


@pytest.mark.parametrize("temperature", [False, True, 0, 1, -0.1, 1.1, float("nan"), float("inf"), "0.1"])
def test_temperature_rejects_bool_nonfinite_and_out_of_range(temperature):
    with pytest.raises(LocalLLMConfigError, match="^INVALID_LOCAL_LLM_CONFIG$"):
        config(intent_temperature=temperature)


@pytest.mark.parametrize("temperature", ["nan", "inf", "true", "0", "1"])
def test_environment_temperature_validation(temperature):
    with pytest.raises(LocalLLMConfigError, match="^INVALID_LOCAL_LLM_CONFIG$"):
        LocalLLMConfig.from_environment({"COMPETITION_COPILOT_LLM_MODE": "cloud",
            "COMPETITION_COPILOT_LLM_PROVIDER": "bigmodel", "COMPETITION_COPILOT_LLM_API_KEY": SENTINEL,
            "COMPETITION_COPILOT_LLM_MODEL": "selected", "COMPETITION_COPILOT_LLM_INTENT_TEMPERATURE": temperature})


def test_environment_role_overrides_and_offline_ignores_them():
    env = {"COMPETITION_COPILOT_LLM_MODE": "cloud", "COMPETITION_COPILOT_LLM_PROVIDER": "bigmodel",
        "COMPETITION_COPILOT_LLM_API_KEY": SENTINEL, "COMPETITION_COPILOT_LLM_MODEL": "selected",
        "COMPETITION_COPILOT_LLM_INTENT_STRUCTURED_METHOD": "function_calling",
        "COMPETITION_COPILOT_LLM_INTENT_TEMPERATURE": "0.2"}
    selected = LocalLLMConfig.from_environment(env)
    assert selected.intent_structured_method == "function_calling" and selected.intent_temperature == 0.2
    with pytest.raises(LocalLLMConfigError):
        config(intent_structured_method="invalid")
    env.update(COMPETITION_COPILOT_LLM_MODE="offline", COMPETITION_COPILOT_LLM_INTENT_TEMPERATURE="invalid")
    assert create_cloud_models(LocalLLMConfig.from_environment(env)) is None


def test_real_constructor_temperature_is_intent_only_and_other_roles_keep_tools(monkeypatch):
    module = pytest.importorskip("langchain_openai")
    original = module.ChatOpenAI
    created = []

    def construct(**kwargs):
        chat = original(**kwargs)
        created.append(chat)
        return chat

    monkeypatch.setattr(module, "ChatOpenAI", construct)
    bundle = create_cloud_models(config())
    assert len(created) == 2
    general, intent = created
    assert general.temperature is None and intent.temperature == 0.1
    assert all(model.max_retries == 0 for model in created)
    # Inspect bound request options without invoking a model.
    assert bundle.intent._structured.steps[1].kwargs["response_format"] == {"type": "json_object"}
    for wrapper, name in ((bundle.explanation, "ExplanationDraft"),
                          (bundle.human_interpreter, "ClarificationResolutionProposal")):
        assert wrapper._structured.first.kwargs["tools"][0]["function"]["name"] == name
        assert "response_format" not in wrapper._structured.first.kwargs


@pytest.mark.parametrize("message,intent,capability,missing", [
    ("帮我看看我适不适合参加这个比赛", "CHECK_ELIGIBILITY", "check_eligibility",
     ["COMPETITION", "EDITION", "STUDENT_PROFILE"]),
    ("最近有什么比赛值得关注", "DISCOVER_COMPETITIONS", "list_competitions", []),
])
def test_scripted_json_proposal_real_core_asks_business_context_and_reuses_once(
    message, intent, capability, missing, monkeypatch,
):
    """Scripted LLM output tests delivery/validation, not live model accuracy."""
    module = pytest.importorskip("langchain_openai")
    original = module.ChatOpenAI
    calls, validations = [], []
    selected = proposal(intent, capability, missing_context=missing)
    original_validate = RoutingProposalValidator.validate

    def validate(self, candidate, actual_request, **kwargs):
        validations.append(candidate.model_dump())
        return original_validate(self, candidate, actual_request, **kwargs)

    def upstream(req):
        body = json.loads(req.content)
        assert body.get("response_format") == {"type": "json_object"}
        assert body.get("temperature") == 0.1 and "tools" not in body
        calls.append(body)
        systems = "\n".join(m["content"] for m in body["messages"] if m["role"] == "system")
        assert INTENT_ROUTING_PROMPT in systems and message in systems
        assert "OUTPUT SCHEMA" in systems and "IntentRoutingProposal" in systems
        assert "does NOT make the intent UNKNOWN" in systems
        assert "ambiguity=NONE" in systems and "RoutingValidator" in systems
        # No tool_calls at all: this is a JSON-mode response, parsed by the real provider bridge.
        return httpx.Response(200, json={"id": "scripted", "object": "chat.completion", "created": 0,
            "model": "operator-selected-model", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(selected)}}]})

    monkeypatch.setattr(RoutingProposalValidator, "validate", validate)
    with httpx.Client(transport=httpx.MockTransport(upstream)) as client:
        monkeypatch.setattr(module, "ChatOpenAI", lambda **kwargs: original(**kwargs, http_client=client))
        bundle = create_cloud_models(config())
        # Discovery may compose an explanation; deterministic grounding fallback
        # avoids a second *role* call in this intent-specific transport test.
        from dataclasses import replace

        target = create_local_host(ROOT, cloud_models=replace(bundle, explanation=None))
        result = invoke(target, request(message))
    assert len(calls) == 1 and len(validations) == 2 and validations[0] == validations[1]
    assert validations[1]["intent"] == intent and validations[1]["candidate_capability"] == capability
    response = result["runtime"]["response"]
    if missing:
        assert response["outcome"] == "NEEDS_CLARIFICATION"
        assert set(response["clarification"]["fields"]) == set(missing)
        assert "INTENT" not in response["clarification"]["fields"]
    else:
        assert response["outcome"] == "COMPLETED" and response["intent"] == intent


@pytest.mark.parametrize("content", ["{broken JSON", "null", "{}",
    json.dumps(proposal(intent="NOT_A_REAL_INTENT")),
    json.dumps(proposal() | {"HUMAN_APPROVED": True})])
def test_invalid_json_or_proposal_fails_closed_once_without_offline_fallback(content, monkeypatch, caplog):
    module = pytest.importorskip("langchain_openai")
    original = module.ChatOpenAI
    calls = []

    def upstream(req):
        calls.append(req)
        return httpx.Response(200, json={"id": "invalid", "object": "chat.completion", "created": 0,
            "model": "operator-selected-model", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": content}}]})

    def forbid_offline(*args, **kwargs):
        pytest.fail("Cloud intent must never fall back to OfflineIntentModel")

    monkeypatch.setattr("competition_copilot.integrations.local_runtime.composition.OfflineIntentModel", forbid_offline)
    with httpx.Client(transport=httpx.MockTransport(upstream)) as client:
        monkeypatch.setattr(module, "ChatOpenAI", lambda **kwargs: original(**kwargs, http_client=client))
        result = invoke(create_local_host(ROOT, cloud_models=create_cloud_models(config())), request())
    assert len(calls) == 1 and result["runtime"]["response"]["outcome"] == "FAILED"
    assert result["runtime"]["response"]["message"] == "INTENT_MODEL_FAILED"
    assert not result["presentation"] or not result["presentation"]["artifacts"]
    assert SENTINEL not in json.dumps(result) + caplog.text
