"""Both frozen protocol paths over the official Streamable HTTP ASGI app."""

import asyncio
import json
import socket
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="Install optional MCP SDK overlay")

import httpx2
from anyio import fail_after
from mcp import Client, MCPError
from mcp_execution_support import (
    COMPETITION,
    EDITION,
    arguments,
    eligibility_payload,
    real_facade,
)
from mcp_http_support import HttpHarness, catalog

from competition_copilot.integrations.mcp.contracts import McpToolResult
from competition_copilot.integrations.mcp.http import (
    AGENTARTS_MCP_COMPATIBILITY_VERSION,
    MCP_UPSTREAM_BASELINE,
    build_streamable_http_app,
)
from competition_copilot.integrations.mcp.registry import build_mcp_tool_registry
from competition_copilot.integrations.mcp.server import build_mcp_server


@pytest.fixture
def run(monkeypatch):
    runner = asyncio.Runner()
    runner.get_loop()  # Windows event-loop wakeup only, before socket denial.

    def reject(*args, **kwargs):
        pytest.fail("HTTP protocol tests must use ASGI, not network or listeners")
    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "bind", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)

    def execute(operation):
        async def bounded():
            with fail_after(20):
                return await operation()
        return runner.run(bounded())
    with runner:
        yield execute


def semantic(wire):
    """Truth carrier only; protocol envelope/HTTP headers are the exclusions."""
    assert json.loads(wire.content[0].text) == wire.structured_content
    result = McpToolResult.model_validate_json(json.dumps(wire.structured_content, allow_nan=False))
    return {"is_error": wire.is_error, "canonical_result": result.model_dump(mode="json")}


def test_targets_match_reviewed_baseline_and_construction_is_inert(run):
    plan = (Path(__file__).resolve().parents[3] / "docs/DEVELOPMENT_PLAN.md").read_text(encoding="utf-8")
    assert f"`MCP_UPSTREAM_BASELINE = {MCP_UPSTREAM_BASELINE}`" in plan
    assert f"`AGENTARTS_MCP_COMPATIBILITY_VERSION = {AGENTARTS_MCP_COMPATIBILITY_VERSION}`" in plan
    facade = real_facade()
    app = build_streamable_http_app(build_mcp_server(facade=facade))
    assert callable(app)
    assert not facade.calls


@pytest.mark.parametrize("mode,version", [("legacy", AGENTARTS_MCP_COMPATIBILITY_VERSION),
                                         ("auto", MCP_UPSTREAM_BASELINE)])
def test_http_negotiation_catalog_and_calls(mode, version, run):
    harness = HttpHarness(real_facade())

    async def scenario():
        async with harness.lifespan(), harness.client(mode) as client:
            assert client.session.protocol_version == version
            if mode == "legacy":
                assert client.session.initialize_result.protocol_version == version
                assert client.session.discover_result is None
            else:
                assert version in client.session.discover_result.supported_versions
                assert client.session.initialize_result is None
            listed = await client.list_tools(cache_mode="bypass")
            registry = build_mcp_tool_registry()
            assert [item.name for item in listed.tools] == [item.tool_name for item in registry.tools]
            for actual, definition in zip(listed.tools, registry.tools, strict=True):
                assert actual.description == definition.description
                assert actual.input_schema == definition.input_schema
                assert actual.output_schema == definition.output_schema
            assert not harness.facade.calls  # Initialization/discovery/list never execute.
            read = await client.call_tool("competition_list", arguments())
            assert semantic(read)["is_error"] is False
            assert len(harness.facade.calls) == 1
    run(scenario)
    assert all(response["session"] is None for response in harness.responses)
    calls = [item for item in harness.requests if item["method"] == "tools/call"]
    assert len(calls) == 1 and calls[0]["version"] == version
    if mode == "legacy":
        assert any(item["method"] == "initialize" and item["offered_version"] == version
                   for item in harness.requests)
    else:
        assert any(item["method"] == "server/discover" for item in harness.requests)
    response = next(item for item in harness.responses if item["method"] == "tools/call")
    assert response["status"] == 200
    assert response["content_type"].startswith("application/json")
    assert "text/event-stream" in calls[0]["accept"]


@pytest.mark.parametrize("education,expected", [("graduate", "ineligible"),
                                              ("undergraduate", "unknown")])
def test_catalog_execution_and_local_parity_preserve_full_json(education, expected, run):
    harness = HttpHarness(real_facade())
    raw = arguments(eligibility_payload(education))

    async def scenario():
        async with harness.lifespan():
            catalogs, results = [], []
            for mode in ("legacy", "auto"):
                async with harness.client(mode) as client:
                    catalogs.append(catalog(await client.list_tools(cache_mode="bypass")))
                    results.append(semantic(await client.call_tool("eligibility_check", raw)))
            async with Client(harness.server, cache=None) as local:
                local_catalog = catalog(await local.list_tools(cache_mode="bypass"))
                local_result = semantic(await local.call_tool("eligibility_check", raw))
            assert catalogs[0] == catalogs[1] == local_catalog
            assert results[0] == results[1] == local_result
            assert not results[0]["is_error"]
            receipt = results[0]["canonical_result"]["result"]
            assert receipt["data"]["status"] == expected
            assert receipt["audit"]["reasons"] and receipt["audit"]["results"]
            sources = [item["source"] for item in receipt["data"]["evidence"] if item.get("source")]
            assert sources
            for source in sources:
                assert isinstance(source["source_url"], str)
                assert source["source_type"] and source["verification_status"]
                assert "T" in source["observed_at"]
                assert source["observed_at"].endswith("Z") or "+" in source["observed_at"]
    run(scenario)
    assert len(harness.facade.calls) == 3  # One per explicit local/legacy/modern call.
    assert [item["status"] for item in harness.responses if item["method"] == "tools/call"] == [200, 200]


@pytest.mark.parametrize("mode", ["legacy", "auto"])
@pytest.mark.parametrize("name", ["unknown", "revise_plan", "approve_plan", "../../revision"])
def test_unknown_and_mutation_tools_over_http_fail_closed(mode, name, run):
    harness = HttpHarness(real_facade())

    async def scenario():
        async with harness.lifespan(), harness.client(mode) as client:
            with pytest.raises(MCPError) as caught:
                await client.call_tool(name, arguments())
            assert caught.value.error.message == "UNKNOWN_TOOL"
    run(scenario)
    assert not harness.facade.calls
    assert all(item["status"] < 500 for item in harness.responses)


@pytest.mark.parametrize("mode", ["legacy", "auto"])
@pytest.mark.parametrize("raw", [arguments(), {**arguments(), "approved": True},
                                  {**arguments(), "capability_id": "revise_plan"}])
def test_invalid_arguments_remain_typed_over_http(mode, raw, run):
    harness = HttpHarness(real_facade())

    async def scenario():
        async with harness.lifespan(), harness.client(mode) as client:
            wire = await client.call_tool("eligibility_check", raw)
            result = semantic(wire)
            assert result["is_error"]
            assert result["canonical_result"]["error"]["code"] == "INVALID_ARGUMENTS"
    run(scenario)
    assert not harness.facade.calls
    assert [r["status"] for r in harness.responses if r["method"] == "tools/call"] == [200]


def test_unsupported_protocol_is_rejected_by_official_sdk(run):
    harness = HttpHarness(real_facade())

    async def scenario():
        async with harness.lifespan(), harness.client("auto") as client:
            with pytest.raises(MCPError) as caught:
                await client.session.send_discover("2099-01-01")
            assert caught.value.error.code == -32022
            assert caught.value.error.data["requested"] == "2099-01-01"
    run(scenario)
    assert not harness.facade.calls
    assert harness.responses[-1]["status"] == 400


@pytest.mark.parametrize("body", ["{", "[]", '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":42}'])
def test_malformed_request_is_not_python_execution(body, run):
    harness = HttpHarness(real_facade())

    async def scenario():
        async with harness.lifespan(), harness.http_client() as http:
            response = await http.post("/mcp", content=body, headers={
                "content-type": "application/json", "accept": "application/json, text/event-stream",
                "mcp-protocol-version": AGENTARTS_MCP_COMPATIBILITY_VERSION})
            assert response.status_code == 400
            assert "Traceback" not in response.text
    run(scenario)
    assert not harness.facade.calls


def test_http_session_metadata_and_concurrent_calls_do_not_mix_inputs(run):
    harness = HttpHarness(real_facade())

    async def call(mode, education, request_id):
        raw = arguments(eligibility_payload(education))
        raw["source_request_id"] = request_id
        raw["payload"]["student"]["id"] = request_id
        async with harness.client(mode, headers={"x-student-id": "wrong-student", "x-plan-id": "wrong-plan"}) as client:
            wire = await client.call_tool("eligibility_check", raw, meta={
                "session_id": "wrong-session", "role": "admin", "approved": True})
            return semantic(wire)

    async def scenario():
        async with harness.lifespan():
            a, b = await asyncio.gather(call("legacy", "graduate", "student-A"),
                                        call("auto", "undergraduate", "student-B"))
            assert a["canonical_result"]["result"]["source_request_id"] == "student-A"
            assert b["canonical_result"]["result"]["source_request_id"] == "student-B"
            assert a["canonical_result"]["result"]["data"]["status"] == "ineligible"
            assert b["canonical_result"]["result"]["data"]["status"] == "unknown"
            assert "wrong-session" not in json.dumps([a, b])
    run(scenario)
    assert len(harness.facade.calls) == 2
    assert {args.payload.student.id for _, args, _ in harness.facade.calls} == {"student-A", "student-B"}
    assert all(item["session"] is None for item in harness.responses)


@pytest.mark.parametrize("mode", ["legacy", "auto"])
def test_aware_capture_time_roundtrips_over_http(mode, run):
    harness = HttpHarness(real_facade())

    async def scenario():
        async with harness.lifespan(), harness.client(mode) as client:
            wire = await client.call_tool("competition_snapshot_build", arguments({
                "target": {"competition_id": COMPETITION, "edition_id": EDITION},
                "observed_at": "2026-10-19T08:00:00+08:00"}))
            result = semantic(wire)
            assert not result["is_error"]
            snapshot = result["canonical_result"]["result"]["data"]
            assert snapshot["observed_at"] == "2026-10-19T00:00:00Z"
    run(scenario)
    assert len(harness.facade.calls) == 1


@pytest.mark.parametrize("mode", ["legacy", "auto"])
def test_mcp_session_header_cannot_supply_or_override_student(mode, run):
    harness = HttpHarness(real_facade())

    async def scenario():
        async with harness.lifespan(), harness.client(mode, headers={
            "mcp-session-id": "fake-student-plan-approval"}) as client:
            invalid = arguments(eligibility_payload())
            del invalid["payload"]["student"]
            wire = await client.call_tool("eligibility_check", invalid)
            assert semantic(wire)["canonical_result"]["error"]["code"] == "INVALID_ARGUMENTS"
            assert not harness.facade.calls
            valid = await client.call_tool("eligibility_check", arguments(eligibility_payload()))
            assert not semantic(valid)["is_error"]
    run(scenario)
    assert len(harness.facade.calls) == 1
    assert harness.facade.calls[0][1].payload.student.id == "mcp-student"


def test_connection_loss_after_execution_does_not_retry_business(run):
    harness = HttpHarness(real_facade())

    async def drop(response):
        request = json.loads(response.request.content)
        if request.get("method") == "tools/call":
            raise httpx2.ReadError("Controlled response loss; execution outcome is unknown to caller")

    async def scenario():
        with pytest.raises(ExceptionGroup) as caught:
            async with harness.lifespan(), harness.client("auto", response_hook=drop) as client:
                await client.call_tool("competition_list", arguments())
        def leaves(error):
            if isinstance(error, BaseExceptionGroup):
                return [leaf for child in error.exceptions for leaf in leaves(child)]
            return [error]
        assert all(isinstance(error, httpx2.ReadError) for error in leaves(caught.value))
    run(scenario)
    assert len(harness.facade.calls) == 1
    assert len([item for item in harness.requests if item["method"] == "tools/call"]) == 1
