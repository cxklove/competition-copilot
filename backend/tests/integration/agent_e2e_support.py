"""Prepared test inputs, fake models and explicit transport-only parity policy."""

import asyncio
import json
import runpy
import socket
from pathlib import Path

import pytest

from competition_copilot.agents.contracts import (
    AgentRequest,
    AgentResponse,
    ResultReference,
)
from competition_copilot.agents.explanation import ExplanationDraft
from competition_copilot.agents.graph import GraphInput
from competition_copilot.agents.routing import IntentRoutingProposal
from competition_copilot.agents.state import AgentState
from competition_copilot.composition import build_seed_agent
from competition_copilot.integrations.agentarts.runtime import AgentArtsRuntimeAdapter

ROOT = Path(__file__).resolve().parents[3]
OLD = runpy.run_path(str(Path(__file__).with_name("test_agentarts_runtime.py")))
HUMAN, FIX = OLD["HUMAN"], OLD["HUMAN"]["FIXTURES"]
P11 = HUMAN["P11"]
TIME = HUMAN["TIME"]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    files = tuple(p for p in (ROOT / "data").rglob("*") if p.is_file())
    before = {p: p.read_bytes() for p in files}
    original = socket.socket.connect

    def reject(*args, **kwargs):
        pytest.fail("End-to-end integration must not access external network")

    def connect(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original(sock, address)  # Windows asyncio socketpair only.
        return reject(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)
    yield
    assert {p: p.read_bytes() for p in files} == before


class Routing:
    def __init__(self, intent, capability, mode="valid"):
        self.intent, self.capability, self.mode = intent, capability, mode
        self.calls = []

    def propose(self, value):
        self.calls.append(value)
        if self.mode == "error":
            raise TimeoutError("test-only model failure")
        return IntentRoutingProposal(intent=self.intent, candidate_capability=self.capability,
            ambiguity="NONE", missing_context=())


class Explanation:
    def __init__(self, mode="valid"):
        self.mode, self.contexts, self.drafts = mode, [], []

    def explain(self, context):
        self.contexts.append(context)
        if self.mode == "error":
            raise TimeoutError("test-only explanation failure")
        draft = OLD["EXPLAIN"]["valid_draft"](context)
        self.drafts.append(draft)
        return draft


class Interpreter:
    def clarify(self, message, question, options):
        # Fixture selects a supplied repository-backed choice, never invents IDs.
        return {"clarification_id": question.clarification_id,
            "source_request_id": question.source_request_id,
            "selections": [{"field": o.field, "value": o.value} for o in options],
            "ambiguous": False}


def frame(payload, message, *, context=None, options=(), request_id="e2e-request"):
    request = AgentRequest(request_id=request_id, user_message=message, context=context or {})
    args = ResultReference(kind="CAPABILITY_ARGUMENTS", ref_id=request_id + "/args")
    return GraphInput(state=AgentState(request=request),
        clarification_id=request_id + "/question",
        result_ref=ResultReference(kind="TOOL_RESULT", ref_id=request_id + "/result"),
        routing_invocation_id=request_id + "/invocation", routing_arguments_ref=args,
        arguments_json=json.dumps({"artifact_ref": args.model_dump(mode="json"), "payload": payload},
            default=lambda v: v.model_dump(mode="json")),
        clarification_options=options)


class Harness:
    def __init__(self, prepared, intent, capability, *, explanation="valid", routing="valid", scoring=None):
        self.prepared = prepared
        self.bindings = OLD["Bindings"](prepared)
        self.routing = Routing(intent, capability, routing)
        self.explanation = Explanation(explanation)
        scoring = scoring or FIX["P6"]["engine"]([0.8])[0]
        self.composition = build_seed_agent(seed_directory=ROOT / "data/seed",
            policy_directory=ROOT / "data/eligibility", inputs=self.bindings, scoring=scoring,
            intent_model=self.routing, explanation_model=self.explanation,
            human_interpreter=Interpreter())
        self.agent, self.facade = self.composition.agent, self.composition.facade
        self.calls, self.receipts = [], []
        execute = self.facade.execute

        def record(invocation, *args, **kwargs):
            self.calls.append(invocation.capability)
            result = execute(invocation, *args, **kwargs)
            self.receipts.append(result)
            return result

        self.facade.execute = record
        self.adapter = AgentArtsRuntimeAdapter(self.agent, self.bindings)

    def runtime(self, payload=None):
        return asyncio.run(self.adapter.invoke(payload or {
            "request": self.prepared.state.request.model_dump(mode="json")}))

    def pending(self, value, execution=None):
        # New application binding reconstructed from JSON, no global session map.
        self.bindings = OLD["Bindings"](self.prepared, json.dumps(value), execution)
        self.adapter = AgentArtsRuntimeAdapter(self.agent, self.bindings)


# Only the transport wrapper, continuation and explicitly named correlation metadata
# are excluded. Every AgentResponse field (including audit/message/errors) is compared.
PARITY_EXCLUSIONS = ("transport wrapper", "continuation", "transport correlation metadata")


def semantic(value):
    if isinstance(value, dict) and "response" in value:
        assert set(value) <= {"response", "continuation", "error", "transport"}
        assert value.get("error") is None
        if "transport" in value:
            assert set(value["transport"]) <= {"request_id", "session_id"}
        value = value["response"]
    response = AgentResponse.model_validate(value)
    return json.loads(response.model_dump_json())


def parity(local, runtime):
    assert semantic(local) == semantic(runtime)


def assert_grounded(harness, response):
    ctx, draft = harness.explanation.contexts[-1], harness.explanation.drafts[-1]
    assert ExplanationDraft.model_validate_json(draft.model_dump_json()) == draft
    assert set(draft.evidence_refs) <= {e.id for e in ctx.evidence}
    assert set(draft.reason_codes) <= set(ctx.reason_codes)
    assert all(r in response.audit.results for r in ctx.result_refs)
    assert all(e.reference in response.audit.results for e in ctx.evidence if e.kind == "SOURCE")
    assert ctx.authoritative_status in response.message
