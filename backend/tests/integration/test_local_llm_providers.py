"""Compatible-provider configuration and real parser/core wiring, entirely offline."""

import json
import socket

import pytest

pytest.importorskip("langgraph")

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError
from test_local_cloud_llm import (
    NOW,
    PLAN,
    ROOT,
    SENTINEL,
    Chat,
    count,
    invoke,
    proposal,
    request,
)

from competition_copilot.agents.contracts import AgentRequest
from competition_copilot.agents.explanation import ExplanationContext
from competition_copilot.agents.human_contracts import HumanMessage as Reply
from competition_copilot.agents.routing import (
    IntentModelInput,
    RoutingProposalValidator,
)
from competition_copilot.integrations.local_runtime.composition import create_local_host
from competition_copilot.integrations.local_runtime.llm import (
    LocalLLMConfig,
    LocalLLMConfigError,
    create_cloud_models,
)

PROVIDERS = ("openai", "bigmodel", "deepseek")
URLS = ("https://api.openai.com/v1", "https://open.bigmodel.cn/api/paas/v4/", "https://api.deepseek.com")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    original = socket.socket.connect

    def deny(sock, address):
        # Windows asyncio creates a loopback socket pair for its event loop.
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original(sock, address)
        pytest.fail("Provider tests must not access network")

    monkeypatch.setattr("socket.socket.connect", deny)


def config(provider, **changes):
    return LocalLLMConfig(mode="cloud", provider=provider, model="operator-selected-model",
                          api_key=SENTINEL, **changes)


@pytest.mark.parametrize("provider,url", tuple(zip(PROVIDERS, URLS, strict=True)))
def test_provider_environment_defaults_and_same_three_wrappers(provider, url, monkeypatch):
    selected = LocalLLMConfig.from_environment({
        "COMPETITION_COPILOT_LLM_MODE": "cloud", "COMPETITION_COPILOT_LLM_PROVIDER": provider,
        "COMPETITION_COPILOT_LLM_MODEL": "operator-selected-model",
        "COMPETITION_COPILOT_LLM_API_KEY": SENTINEL})
    assert selected.base_url == url
    method = None if provider == "openai" else "function_calling"
    assert selected.structured_method == method
    observed = []
    original = Chat.with_structured_output

    def observe(self, schema, **kwargs):
        observed.append((schema.__name__, kwargs))
        return original(self, schema, **kwargs)

    monkeypatch.setattr(Chat, "with_structured_output", observe)
    create_cloud_models(selected, chat_model=Chat())
    assert [name for name, _ in observed] == ["IntentRoutingProposal", "ExplanationDraft", "ClarificationResolutionProposal"]
    intent_method = "json_mode" if provider == "bigmodel" else method
    assert selected.intent_structured_method == intent_method
    assert observed[0][1] == ({} if intent_method is None else {"method": intent_method})
    assert all(kwargs == ({} if method is None else {"method": method}) for _, kwargs in observed[1:])
    assert SENTINEL not in repr(selected)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_real_chatopenai_http_tool_call_and_zero_retries(provider, monkeypatch):
    module = pytest.importorskip("langchain_openai")
    original = module.ChatOpenAI
    calls, created = [], []

    def upstream(req):
        body = json.loads(req.content)
        calls.append(body)
        assert str(req.url) == config(provider).base_url.rstrip("/") + "/chat/completions"
        assert req.headers["authorization"] == "Bearer " + SENTINEL
        assert body["tools"][0]["function"]["name"] == "IntentRoutingProposal"
        assert "response_format" not in body
        if provider != "openai":
            assert "tool_choice" not in body and "parallel_tool_calls" not in body
        return httpx.Response(200, json={"id": "offline", "object": "chat.completion",
            "created": 0, "model": "operator-selected-model", "choices": [{"index": 0,
            "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
            "tool_calls": [{"id": "proposal", "type": "function", "function": {
                "name": "IntentRoutingProposal", "arguments": json.dumps(proposal())}}]}}]})

    with httpx.Client(transport=httpx.MockTransport(upstream)) as client:
        def factory(**kwargs):
            created.append(original(**kwargs, http_client=client))
            return created[-1]

        monkeypatch.setattr(module, "ChatOpenAI", factory)
        bundle = create_cloud_models(config(provider, structured_method="function_calling",
                                             intent_structured_method="function_calling"))
        result = bundle.intent.propose(IntentModelInput(
            request=AgentRequest.model_validate(request()["request"]), catalog=()))
    assert result.candidate_capability == "list_competitions" and len(calls) == 1
    assert created[0].max_retries == 0 and created[0].request_timeout == 30


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("method", ["json_schema", "function_calling", "json_mode"])
def test_explicit_methods_and_pydantic_reject_invalid_outputs(provider, method, monkeypatch):
    instructions = []

    def invalid(self, schema, **kwargs):
        assert kwargs == {"method": method}
        return RunnableLambda(lambda messages: instructions.append(messages) or {})

    monkeypatch.setattr(Chat, "with_structured_output", invalid)
    bundle = create_cloud_models(config(provider, structured_method=method,
                                       intent_structured_method=method), chat_model=Chat())
    with pytest.raises(ValidationError):
        bundle.intent.propose(IntentModelInput(request=AgentRequest.model_validate(request()["request"]), catalog=()))
    with pytest.raises(ValidationError):
        bundle.explanation.explain(ExplanationContext.model_construct(evidence=()))
    reply = Reply(interaction_id="question", source_request_id="cloud-request", text="choice", submitted_at=NOW)
    with pytest.raises(ValidationError):
        bundle.human_interpreter.clarify(reply, reply, ())
    assert len(instructions) == 3
    if method == "json_mode":
        assert all("OUTPUT SCHEMA" in messages[-1].content and "JSON" in messages[-1].content
                   for messages in instructions)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_prepared_proposal_same_graph_payload_once_and_domain_truth(provider, monkeypatch):
    monkeypatch.setattr("secrets.token_urlsafe", lambda size: "provider-parity")
    selected = proposal("CHECK_ELIGIBILITY", "check_eligibility")
    chat = Chat(proposals=[selected, proposal()])
    checked = []
    original = RoutingProposalValidator.validate

    def observe(self, candidate, actual_request, **kwargs):
        checked.append((candidate, kwargs["arguments"]))
        return original(self, candidate, actual_request, **kwargs)

    monkeypatch.setattr(RoutingProposalValidator, "validate", observe)
    target = create_local_host(ROOT, clock=lambda: NOW,
        cloud_models=create_cloud_models(config(provider), chat_model=chat))
    payload = request("eligibility", {"student_id": "local-graduate", "competition_id": "comap-mcm",
                                     "edition_id": "comap-mcm-2027"})
    cloud = invoke(target, payload)
    # Capture only cloud validation; offline also uses the same validator.
    assert len(checked) == 2 and checked[0][0] == checked[1][0]
    assert checked[1][1]["payload"]["competition_id"] == "comap-mcm"
    baseline = invoke(create_local_host(ROOT, clock=lambda: NOW), payload)
    assert cloud["presentation"] == baseline["presentation"]
    assert count(chat, "IntentRoutingProposal") == 1 and chat.proposals == [proposal()]


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("decision", ["APPROVE", "REJECT"])
def test_provider_approval_never_inferred(provider, decision):
    chat = Chat(proposals=[proposal("REQUEST_PLAN_REVISION", "revise_plan")])
    target = create_local_host(ROOT, clock=lambda: NOW,
        cloud_models=create_cloud_models(config(provider), chat_model=chat))
    pending = invoke(target, request("revise", {"plan_ref": PLAN}))
    approval = pending["runtime"]["response"]["approval_request"]
    ambiguous = invoke(target, {"continuation_ref": pending["runtime"]["continuation_ref"], "message": {
        "source_request_id": "cloud-request", "interaction_id": approval["approval_request_id"],
        "text": "yes", "submitted_at": NOW.isoformat()}})
    assert ambiguous["runtime"]["response"]["outcome"] == "WAITING_FOR_APPROVAL"
    completed = invoke(target, {"continuation_ref": ambiguous["runtime"]["continuation_ref"], "approval": {
        "source_request_id": "cloud-request", "approval_request_id": approval["approval_request_id"],
        "decision": decision, "submitted_at": NOW.isoformat()}})
    assert completed["runtime"]["response"]["outcome"] == "COMPLETED"
    assert count(chat, "ClarificationResolutionProposal") == 0
    assert count(chat, "IntentRoutingProposal") == 1
    assert any(a["model"] == "PlanDiff" for a in completed["presentation"]["artifacts"]) == (decision == "APPROVE")


@pytest.mark.parametrize("provider", PROVIDERS)
def test_missing_key_no_cross_provider_fallback(provider, caplog):
    env = {"COMPETITION_COPILOT_LLM_MODE": "cloud", "COMPETITION_COPILOT_LLM_PROVIDER": provider,
           "COMPETITION_COPILOT_LLM_MODEL": "selected-model"}
    if provider != "openai":
        env["OPENAI_API_KEY"] = SENTINEL
    with pytest.raises(LocalLLMConfigError, match="API_KEY_REQUIRED") as error:
        LocalLLMConfig.from_environment(env)
    assert SENTINEL not in str(error.value) + caplog.text


@pytest.mark.parametrize("changes", [
    {"provider": "other"}, {"base_url": "http://api.deepseek.com"},
    {"base_url": "https://api.openai.com/v1"}, {"base_url": "https://api.deepseek.com.evil.invalid"},
    {"base_url": "https://user:password@api.deepseek.com"},
    {"base_url": "https://api.deepseek.com/?key=private"}, {"base_url": "https://api.deepseek.com/#private"},
    {"base_url": "https://api.deepseek.com:8443"}, {"structured_method": "invalid"},
])
def test_invalid_config_sanitized(changes):
    values = {"mode": "cloud", "provider": "deepseek", "model": "selected", "api_key": SENTINEL, **changes}
    with pytest.raises(LocalLLMConfigError, match="^INVALID_LOCAL_LLM_CONFIG$") as error:
        LocalLLMConfig(**values)
    assert SENTINEL not in str(error.value)


def test_explicit_base_path_and_unified_key_precedence():
    result = LocalLLMConfig.from_environment({"COMPETITION_COPILOT_LLM_MODE": "cloud",
        "COMPETITION_COPILOT_LLM_MODEL": "selected", "COMPETITION_COPILOT_LLM_API_KEY": SENTINEL,
        "OPENAI_API_KEY": "unused", "COMPETITION_COPILOT_LLM_BASE_URL": "https://api.openai.com/v1/"})
    assert result.api_key == SENTINEL and result.base_url == "https://api.openai.com/v1/"
    assert LocalLLMConfig.from_environment({"COMPETITION_COPILOT_LLM_PROVIDER": "invalid",
        "COMPETITION_COPILOT_LLM_STRUCTURED_METHOD": "invalid"}).mode == "offline"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_upstream_failure_sanitized_once(provider, monkeypatch, caplog, capsys):
    module = pytest.importorskip("langchain_openai")
    original = module.ChatOpenAI
    calls = []

    def fail(req):
        calls.append(req)
        return httpx.Response(500, json={"error": {"message": SENTINEL}})

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        monkeypatch.setattr(module, "ChatOpenAI", lambda **kwargs: original(**kwargs, http_client=client))
        target = create_local_host(ROOT, cloud_models=create_cloud_models(config(provider)))
        result = invoke(target, request())
    assert len(calls) == 1 and result["runtime"]["response"]["outcome"] == "FAILED"
    assert SENTINEL not in json.dumps(result) + caplog.text + str(capsys.readouterr())


def test_json_mode_instructions_include_schema_without_changing_input(monkeypatch):
    captured = []

    def answer(self, schema, **kwargs):
        return RunnableLambda(lambda messages: captured.append(messages) or proposal())

    monkeypatch.setattr(Chat, "with_structured_output", answer)
    bundle = create_cloud_models(config("bigmodel", structured_method="json_mode"), chat_model=Chat())
    value = IntentModelInput(request=AgentRequest.model_validate(request()["request"]), catalog=())
    assert bundle.intent.propose(value).candidate_capability == "list_competitions"
    assert isinstance(captured[0][0], SystemMessage) and isinstance(captured[0][1], HumanMessage)
    assert json.loads(captured[0][1].content) == value.model_dump(mode="json")
