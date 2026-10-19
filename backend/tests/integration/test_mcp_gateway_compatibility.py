"""Offline AgentArts Gateway contract acceptance; no cloud SDK or resources."""

import asyncio
import hashlib
import json
import socket

import pytest

pytest.importorskip("mcp", reason="Install optional MCP SDK overlay")

from anyio import fail_after
from jsonschema import Draft202012Validator
from mcp import Client, MCPError
from mcp_execution_support import (
    COMPETITION,
    EDITION,
    RecordingFacade,
    arguments,
    eligibility_payload,
    real_facade,
)
from mcp_gateway_support import GatewayHarness
from mcp_http_support import catalog

from competition_copilot.agents.capabilities import CapabilityAccess
from competition_copilot.integrations.mcp.contracts import McpToolResult
from competition_copilot.integrations.mcp.registry import build_mcp_tool_registry


@pytest.fixture
def run(monkeypatch):
    runner = asyncio.Runner()
    runner.get_loop()  # Windows loop wakeup only, before denying all network IO.

    def reject(*args, **kwargs):
        pytest.fail("Gateway compatibility must not access sockets/cloud")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "bind", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)

    def execute(operation):
        async def bounded():
            with fail_after(25):
                return await operation()
        return runner.run(bounded())
    with runner:
        yield execute


def receipt(wire):
    text = json.loads(wire.content[0].text)
    if wire.structured_content is not None:
        assert wire.structured_content == text
    restored = McpToolResult.model_validate_json(json.dumps(text, allow_nan=False))
    return {"is_error": wire.is_error, "receipt": restored.model_dump(mode="json")}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def test_gateway_discovery_schema_ingestion_stability_and_exclusions(run):
    facade = real_facade()
    harness = GatewayHarness(facade)

    async def scenario():
        snapshots = []
        for headers in (None, {"authorization": "Bearer test-placeholder", "x-agentarts-role": "admin"}):
            async with harness.connect(headers=headers) as client:
                first = await client.list_tools(cache_mode="bypass")
                second = await client.list_tools(cache_mode="bypass")
                assert catalog(first) == catalog(second)
                snapshots.append(catalog(first))
                registry = build_mcp_tool_registry()
                assert [t.name for t in first.tools] == [d.tool_name for d in registry.tools]
                for tool, definition in zip(first.tools, registry.tools, strict=True):
                    assert tool.description == definition.description
                    assert tool.input_schema == definition.input_schema
                    Draft202012Validator.check_schema(tool.input_schema)
                    assert tool.input_schema["additionalProperties"] is False
                    assert set(tool.input_schema["required"]) == set(definition.input_schema["required"])
                    assert tool.output_schema is None and tool.annotations is None and tool.icons is None
                    assert definition.access_type != CapabilityAccess.MUTATING
                    assert not definition.requires_explicit_approval
                    assert not any(word in tool.description.lower() for word in (
                        "ignore previous", "always call", "override domain", "skip approval"))
                # Ingestion validates actual arguments, nested models, enum refs,
                # required fields and extra policy without outputSchema support.
                schema = next(t.input_schema for t in first.tools if t.name == "eligibility_check")
                validator = Draft202012Validator(schema)
                validator.validate(arguments(eligibility_payload()))
                assert list(validator.iter_errors({**arguments(), "approved": True}))
        assert fingerprint(snapshots[0]) == fingerprint(snapshots[1])
    run(scenario)
    assert not facade.calls
    assert {"initialize", "tools/list"} <= set(harness.methods)
    assert any(t.startswith("text/event-stream") for t in harness.content_types)


@pytest.mark.parametrize("name,payload,status", [
    ("competition_get", {"competition_id": COMPETITION}, None),
    ("eligibility_check", eligibility_payload("graduate"), "ineligible"),
    ("eligibility_check", eligibility_payload("undergraduate"), "unknown"),
    ("competition_snapshot_build", {"target": {"competition_id": COMPETITION, "edition_id": EDITION},
                                    "observed_at": "2026-10-19T08:00:00+08:00"}, None),
])
@pytest.mark.parametrize("text_only", [False, True])
def test_four_path_semantic_parity_json_and_exactly_once(name, payload, status, text_only, run):
    facade = real_facade()
    harness = GatewayHarness(facade, text_only=text_only)
    raw = arguments(payload)

    async def scenario():
        async with harness.connect() as gateway:
            discovered = await gateway.list_tools(cache_mode="bypass")
            schema = next(t.input_schema for t in discovered.tools if t.name == name)
            Draft202012Validator(schema).validate(raw)
            gateway_result = receipt(await gateway.call_tool(name, raw))
            assert len(facade.calls) == 1
            invocation, typed, result_ref = facade.calls[0]
            direct_facade = real_facade()
            direct = direct_facade.execute(invocation, typed, result_ref=result_ref)
            assert len(direct_facade.calls) == 1
            assert gateway_result["receipt"] == {"error": None, "result": direct.model_dump(mode="json")}
            async with Client(harness.target.server, cache=None) as local:
                assert receipt(await local.call_tool(name, raw)) == gateway_result
            async with harness.target.client("auto") as modern:
                assert receipt(await modern.call_tool(name, raw)) == gateway_result
            assert not gateway_result["is_error"]
            if status:
                assert direct.data.status.value == status
                assert direct.audit.reasons and direct.audit.results
                for evidence in direct.data.evidence:
                    if evidence.source:
                        source = evidence.source.model_dump(mode="json")
                        assert isinstance(source["source_url"], str)
                        assert source["source_type"] and source["verification_status"]
                        assert evidence.source.observed_at.tzinfo is not None
            if name == "competition_snapshot_build":
                assert gateway_result["receipt"]["result"]["data"]["observed_at"] == "2026-10-19T00:00:00Z"
    run(scenario)
    assert len(facade.calls) == 3  # Three explicit calls, never retries.


@pytest.mark.parametrize("name", ["unknown", "revise_plan", "approve_plan", "reject_plan",
                                  "apply_approved_plan_revision", "../../revision"])
def test_gateway_unknown_mutation_and_approval_calls_fail_closed(name, run):
    facade = real_facade()
    harness = GatewayHarness(facade)

    async def scenario():
        async with harness.connect() as client:
            with pytest.raises(MCPError) as caught:
                await client.call_tool(name, arguments())
            assert caught.value.error.message == "UNKNOWN_TOOL"
    run(scenario)
    assert not facade.calls


@pytest.mark.parametrize("field", ["approve", "approved", "human_approved", "admin_override",
                                   "capability_id", "force", "skip_approval"])
def test_gateway_argument_injection_fails_before_facade(field, run):
    facade = real_facade()
    harness = GatewayHarness(facade)

    async def scenario():
        async with harness.connect() as client:
            wire = await client.call_tool("competition_list", {**arguments(), field: "revise_plan"})
            result = receipt(wire)
            assert result["is_error"] and result["receipt"]["error"]["code"] == "INVALID_ARGUMENTS"
    run(scenario)
    assert not facade.calls


def test_gateway_independent_clients_metadata_and_missing_context(run):
    facade = real_facade()
    harness = GatewayHarness(facade)

    async def scenario():
        results = []
        for student, education in (("student-A", "graduate"), ("student-B", "undergraduate")):
            async with harness.connect(headers={"authorization": "Bearer test-placeholder",
                    "mcp-session-id": "fake-approval", "x-user-id": "wrong-user"}) as client:
                missing = arguments(eligibility_payload())
                del missing["payload"]["student"]
                assert receipt(await client.call_tool("eligibility_check", missing))["is_error"]
                before = len(facade.calls)
                raw = arguments(eligibility_payload(education))
                raw["payload"]["student"]["id"] = student
                value = receipt(await client.call_tool("eligibility_check", raw, meta={
                    "admin": True, "approved": True, "user_id": "wrong-user",
                    "agent_id": "test-agent", "session_id": "fake-approval"}))
                assert len(facade.calls) == before + 1
                assert facade.calls[-1][1].payload.student.id == student
                assert "wrong-user" not in json.dumps(value)
                results.append(value["receipt"]["result"]["data"]["status"])
                with pytest.raises(MCPError):
                    await client.call_tool("revise_plan", arguments(), meta={
                        "admin": True, "approved": True, "user_id": student})
                assert len(facade.calls) == before + 1
        assert results == ["ineligible", "unknown"]
    run(scenario)
    assert len(facade.calls) == 2
    assert all(r["session"] is None for r in harness.target.responses)


@pytest.mark.parametrize("unexpected", [False, True])
def test_gateway_execution_failure_is_safe_and_never_retried(unexpected, run, monkeypatch):
    facade = real_facade() if unexpected else RecordingFacade()
    calls = []
    if unexpected:
        def fail(*args, **kwargs):
            calls.append(1)
            raise RuntimeError("Traceback C:/private/path API_KEY=secret <Python repr>")
        monkeypatch.setattr(facade, "execute", fail)
    harness = GatewayHarness(facade)

    async def scenario():
        async with harness.connect() as client:
            wire = await client.call_tool("competition_list", arguments())
            result = receipt(wire)
            assert result["is_error"]
            if unexpected:
                assert result["receipt"]["error"]["code"] == "EXECUTION_FAILURE"
            else:
                assert result["receipt"]["result"]["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
            assert not any(word in wire.model_dump_json() for word in (
                "Traceback", "C:/", "private", "API_KEY", "secret", "<Python"))
    run(scenario)
    assert len(calls if unexpected else facade.calls) == 1
