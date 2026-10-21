"""Prompt precedence plus real JSON parsing/P5/P6; scripted LLM, no cloud accuracy claim."""

import json
import socket

import pytest

pytest.importorskip("langgraph")

import httpx
from test_local_cloud_llm import NOW, ROOT, SENTINEL, Chat, invoke, proposal, request

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.agents.prompts import INTENT_ROUTING_PROMPT
from competition_copilot.agents.routing import RoutingProposalValidator
from competition_copilot.integrations.local_runtime.composition import create_local_host
from competition_copilot.integrations.local_runtime.llm import (
    LocalLLMConfig,
    create_cloud_models,
)

CASES = [
    ("我能参加这个比赛吗", "CHECK_ELIGIBILITY", "check_eligibility"),
    ("我有资格报名吗", "CHECK_ELIGIBILITY", "check_eligibility"),
    ("这个比赛适合我吗", "GET_RECOMMENDATIONS", "get_recommendations"),
    ("有没有更值得优先准备的比赛", "GET_RECOMMENDATIONS", "get_recommendations"),
    ("这个比赛适合我吗？有没有更值得优先准备的比赛？", "GET_RECOMMENDATIONS", "get_recommendations"),
    ("先判断我有没有资格，再告诉我值不值得优先准备", "GET_RECOMMENDATIONS", "get_recommendations"),
]


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    original = socket.socket.connect

    def guard(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original(sock, address)
        pytest.fail("Intent precedence tests must not access external network")

    monkeypatch.setattr(socket.socket, "connect", guard)

    def forbid_fallback(*args, **kwargs):
        pytest.fail("No OfflineIntentModel fallback is permitted")

    monkeypatch.setattr("competition_copilot.integrations.local_runtime.composition.OfflineIntentModel", forbid_fallback)


@pytest.mark.parametrize("message,intent,capability", CASES)
def test_prompt_precedence_real_parser_and_authoritative_capability_workflow(message, intent, capability, monkeypatch):
    module = pytest.importorskip("langchain_openai")
    original_chat = module.ChatOpenAI
    original_execute = AgentCapabilityFacade.execute
    original_validate = RoutingProposalValidator.validate
    upstream_calls, executed, validations, models = [], [], [], []

    def upstream(req):
        body = json.loads(req.content)
        upstream_calls.append(body)
        assert body["response_format"] == {"type": "json_object"} and body["temperature"] == 0.1
        systems = "\n".join(m["content"] for m in body["messages"] if m["role"] == "system")
        assert INTENT_ROUTING_PROMPT in systems
        assert f"“{message}” -> {intent} / {capability}." in systems
        assert "Do not request INTENT clarification when one operation subsumes its prerequisite" in systems
        assert json.loads(body["messages"][1]["content"])["request"]["user_message"] == message
        return httpx.Response(200, json={"id": "scripted", "object": "chat.completion", "created": 0,
            "model": "test-model", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(proposal(intent, capability))}}]})

    def execute(self, invocation, arguments, *, result_ref):
        receipt = original_execute(self, invocation, arguments, result_ref=result_ref)
        executed.append((invocation.capability, arguments, receipt))
        return receipt

    def validate(self, candidate, actual_request, **kwargs):
        validations.append(candidate.model_dump())
        return original_validate(self, candidate, actual_request, **kwargs)

    monkeypatch.setattr(AgentCapabilityFacade, "execute", execute)
    monkeypatch.setattr(RoutingProposalValidator, "validate", validate)
    with httpx.Client(transport=httpx.MockTransport(upstream)) as client:
        def construct(**kwargs):
            assert kwargs["max_retries"] == 0
            if "temperature" not in kwargs:
                return Chat()  # Existing evidence-only explanation fake, no business truth.
            chat = original_chat(**kwargs, http_client=client)
            models.append(chat)
            return chat

        monkeypatch.setattr(module, "ChatOpenAI", construct)
        bundle = create_cloud_models(LocalLLMConfig(mode="cloud", provider="bigmodel",
            model="test-model", api_key=SENTINEL))
        host = create_local_host(ROOT, clock=lambda: NOW, cloud_models=bundle)
        result = invoke(host, request(message, {"student_id": "local-graduate",
            "competition_id": "gcxl-engineering-practice-innovation",
            "edition_id": "gcxl-engineering-practice-innovation-2027"}))
    response = result["runtime"]["response"]
    assert response["outcome"] == "COMPLETED" and response["intent"] == intent
    assert response["clarification"] is None
    assert len(upstream_calls) == 1 and host.handler_invocations == 1 and models[0].max_retries == 0
    assert len(validations) == 2 and validations[0] == validations[1]
    assert validations[0]["ambiguity"] == "NONE"
    p5_calls = [item for item in executed if item[0] == "check_eligibility"]
    assert all(item[2].status == "SUCCESS" for item in p5_calls)
    p5 = next(item[2].data for item in p5_calls
              if item[2].data.competition_id == "gcxl-engineering-practice-innovation")
    assert p5.status == "ineligible"  # Real P5, not the scripted intent model.
    artifacts = result["presentation"]["artifacts"]
    if intent == "GET_RECOMMENDATIONS":
        assert len(p5_calls) > 1
        assert [item[0] for item in executed] == ["check_eligibility"] * len(p5_calls) + ["get_recommendations"]
        p6_args, receipt = executed[-1][1:]
        assert [item["eligibility_decision"] for item in p6_args["payload"]["contexts"]] == [
            item[2].data.model_dump(mode="json") for item in p5_calls]
        assert receipt.status == "SUCCESS" and receipt.data.__class__.__name__ == "RecommendationRankingResult"
        anchor = next(item for item in receipt.data.blocked
                      if item.candidate.competition_id == "gcxl-engineering-practice-innovation")
        assert anchor.eligibility_decision.model_dump(mode="json") == p5.model_dump(mode="json")
        ranking = next(a["value"] for a in artifacts if a["model"] == "RecommendationRankingResult")
        assert ranking == receipt.data.model_dump(mode="json")
        assert "RANKED" in response["message"]
        assert sum(len(ranking[b]) for b in ("confirmed", "uncertain", "blocked")) == len(p5_calls)
    else:
        assert len(executed) == 1
        assert next(a["value"] for a in artifacts if a["model"] == "EligibilityDecision") == p5.model_dump(mode="json")
