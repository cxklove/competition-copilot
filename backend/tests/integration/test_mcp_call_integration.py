"""Real SDK calls -> real Facade/P4/P5/P9; no HTTP, cloud or model."""

import asyncio
import json
import socket

import pytest

pytest.importorskip("mcp", reason="Install optional MCP SDK overlay")

from anyio import fail_after
from mcp import Client, MCPError
from mcp_execution_support import (
    COMPETITION,
    EDITION,
    RecordingFacade,
    arguments,
    eligibility_payload,
    real_facade,
)

from competition_copilot.agents.capabilities import CapabilityStatus
from competition_copilot.agents.contracts import (
    AgentIntent,
    CapabilityInvocationRequest,
    ReferenceKind,
    ResultReference,
)
from competition_copilot.integrations.mcp import server as server_module
from competition_copilot.integrations.mcp.contracts import McpToolResult
from competition_copilot.integrations.mcp.registry import build_mcp_tool_registry
from competition_copilot.integrations.mcp.server import (
    build_mcp_server,
    map_tool_result_to_mcp,
)


@pytest.fixture
def run(monkeypatch):
    runner = asyncio.Runner()
    runner.get_loop()  # Windows loopback wakeup socket, not a business connection.

    def reject(*args, **kwargs):
        pytest.fail("MCP execution integration must stay offline")
    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)

    def execute(operation):
        async def bounded():
            with fail_after(15):
                return await operation()
        return runner.run(bounded())
    with runner:
        yield execute


def restore(wire):
    assert json.loads(wire.content[0].text) == wire.structured_content
    return McpToolResult.model_validate_json(json.dumps(wire.structured_content, allow_nan=False))


@pytest.mark.parametrize("name,payload", [
    ("competition_list", {}),
    ("competition_get", {"competition_id": COMPETITION}),
    ("competition_editions_list", {"competition_id": COMPETITION}),
    ("competition_edition_get", {"edition_id": EDITION}),
    ("competition_tracks_list", {"edition_id": EDITION}),
    ("competition_snapshot_build", {"target": {"competition_id": COMPETITION, "edition_id": EDITION},
                                    "observed_at": "2026-10-19T08:00:00+08:00"}),
])
def test_real_read_calls_json_and_exactly_once(name, payload, run):
    facade = real_facade()

    async def scenario():
        async with Client(build_mcp_server(facade=facade)) as client:
            before = (await client.list_tools(cache_mode="bypass")).model_dump(mode="json")
            wire = await client.call_tool(name, arguments(payload))
            result = restore(wire)
            assert not wire.is_error
            assert result.result.status == CapabilityStatus.SUCCESS
            assert result.result.result_ref.ref_id == "mcp-result"
            after = (await client.list_tools(cache_mode="bypass")).model_dump(mode="json")
            assert before == after
    run(scenario)
    assert len(facade.calls) == 1


@pytest.mark.parametrize("education,status", [("graduate", "ineligible"),
                                             ("undergraduate", "unknown")])
def test_real_p5_negative_unknown_evidence_and_direct_facade_parity(education, status, run):
    registry = build_mcp_tool_registry()
    definition = registry.get("eligibility_check")
    raw = arguments(eligibility_payload(education))
    value = definition.input_model.model_validate(raw)
    direct = real_facade().execute(CapabilityInvocationRequest(
        invocation_id=value.invocation_id, source_request_id=value.source_request_id,
        intent=AgentIntent.CHECK_ELIGIBILITY, capability=definition.capability_id,
        arguments_ref=value.arguments_ref,
    ), {"artifact_ref": value.arguments_ref.model_dump(mode="json"),
        "payload": value.payload.model_dump(mode="json")}, result_ref=value.result_ref)
    facade = real_facade()

    async def scenario():
        async with Client(build_mcp_server(facade=facade)) as client:
            wire = await client.call_tool("eligibility_check", raw)
            result = restore(wire)
            assert wire.is_error is False
            assert result.result.data.status.value == status
            assert result.result.model_dump(mode="json") == direct.model_dump(mode="json")
            assert result.result.audit.reasons == direct.audit.reasons
            assert result.result.audit.results == direct.audit.results
            assert {ReferenceKind.EVIDENCE, ReferenceKind.SOURCE} <= {
                ref.kind for ref in result.result.audit.results}
            for item in result.result.data.evidence:
                if item.source:
                    assert item.source.model_dump(mode="json") == direct.data.evidence[
                        result.result.data.evidence.index(item)].source.model_dump(mode="json")
                    assert item.source.observed_at.tzinfo is not None
            a = map_tool_result_to_mcp(result).model_dump(mode="json")
            assert a == map_tool_result_to_mcp(result).model_dump(mode="json")
    run(scenario)
    assert len(facade.calls) == 1


def test_real_track_read_uses_explicit_seed_track_argument(run):
    # Get the real track ID through the existing read capability, not server lookup.
    facade = real_facade()

    async def scenario():
        async with Client(build_mcp_server(facade=facade)) as client:
            listed = restore(await client.call_tool(
                "competition_tracks_list", arguments({"edition_id": EDITION})))
            track_id = listed.result.data.tracks[0].id
            wire = await client.call_tool("competition_track_get", arguments({"track_id": track_id}))
            assert not wire.is_error
            assert restore(wire).result.data.track.id == track_id
    run(scenario)
    assert len(facade.calls) == 2  # Two separate caller turns, one execution each.


@pytest.mark.parametrize("name", ["revise_plan", "apply_approved_plan_revision", "approve_plan",
                                  "get_recommendations", "../../revision", "__import__"])
def test_sdk_mutation_internal_and_name_attacks_are_fail_closed(name, run):
    facade = real_facade()

    async def scenario():
        async with Client(build_mcp_server(facade=facade)) as client:
            with pytest.raises(MCPError) as caught:
                await client.call_tool(name, {"approved": True})
            assert caught.value.error.message == "UNKNOWN_TOOL"
    run(scenario)
    assert not facade.calls


@pytest.mark.parametrize("field", ["approve", "human_approved", "admin_override", "capability_id"])
def test_sdk_authority_and_capability_injection_does_not_execute(field, run):
    facade = real_facade()

    async def scenario():
        async with Client(build_mcp_server(facade=facade)) as client:
            wire = await client.call_tool("competition_list", {**arguments(), field: "revise_plan"})
            assert wire.is_error
            assert restore(wire).error.code == "INVALID_ARGUMENTS"
    run(scenario)
    assert not facade.calls


def test_canonical_failure_is_error_but_preserves_receipt(run):
    facade = RecordingFacade()

    async def scenario():
        async with Client(build_mcp_server(facade=facade)) as client:
            wire = await client.call_tool("competition_list", arguments())
            result = restore(wire)
            assert wire.is_error
            assert result.result.status == CapabilityStatus.ERROR
            assert result.result.error.code == "DEPENDENCY_UNAVAILABLE"
            assert result.result.result_ref.ref_id == "mcp-result"
    run(scenario)
    assert len(facade.calls) == 1


def test_facade_exception_safe_over_sdk_and_no_retry(run, monkeypatch):
    facade = real_facade()
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("C:/private/path API_KEY=secret Traceback")
    monkeypatch.setattr(facade, "execute", fail)

    async def scenario():
        async with Client(build_mcp_server(facade=facade)) as client:
            wire = await client.call_tool("competition_list", arguments())
            assert wire.is_error
            assert restore(wire).error.code == "EXECUTION_FAILURE"
            assert "secret" not in wire.model_dump_json()
            assert "private" not in wire.model_dump_json()
    run(scenario)
    assert calls == [1]


def test_mapper_failure_does_not_reexecute_completed_capability(run, monkeypatch):
    facade = real_facade()

    def fail(*args, **kwargs):
        raise RuntimeError("mapping failed C:/private secret")
    monkeypatch.setattr(server_module, "map_tool_result_to_mcp", fail)

    async def scenario():
        async with Client(build_mcp_server(facade=facade)) as client:
            wire = await client.call_tool("competition_list", arguments())
            assert wire.is_error
            assert wire.structured_content["error"]["code"] == "EXECUTION_FAILURE"
            assert "secret" not in wire.model_dump_json()
    run(scenario)
    assert len(facade.calls) == 1


def test_session_and_metadata_independence(run):
    facade = real_facade()
    server = build_mcp_server(facade=facade)

    async def call(meta):
        async with Client(server) as client:
            wire = await client.call_tool("eligibility_check", arguments(eligibility_payload()), meta=meta)
            return restore(wire).model_dump(mode="json")

    async def scenario():
        first = await call(None)
        second = await call({"session_id": "other-plan", "role": "admin", "approved": True})
        assert first == second
        assert first["result"]["data"]["status"] == "ineligible"
        assert "other-plan" not in json.dumps(second)
    run(scenario)
    assert len(facade.calls) == 2


def test_bad_result_identity_over_sdk_is_rejected(run, monkeypatch):
    facade = real_facade()
    original = facade.execute

    def mismatch(invocation, args, *, result_ref):
        return original(invocation, args, result_ref=ResultReference(
            kind=ReferenceKind.TOOL_RESULT, ref_id="other-result"))
    monkeypatch.setattr(facade, "execute", mismatch)

    async def scenario():
        async with Client(build_mcp_server(facade=facade)) as client:
            wire = await client.call_tool("competition_list", arguments())
            assert wire.is_error
            assert restore(wire).error.code == "EXECUTION_FAILURE"
    run(scenario)
    assert len(facade.calls) == 1
