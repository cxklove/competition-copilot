"""Real public SDK client -> catalog-only server. Offline, no business calls."""

import asyncio
import json
import socket
from dataclasses import replace

import pytest

pytest.importorskip("mcp", reason="Install optional mcp extra / requirements-mcp.lock")

from anyio import fail_after
from mcp import Client, MCPError
from mcp.server import Server
from mcp.types import INVALID_PARAMS, ListToolsResult

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.integrations.mcp.registry import build_mcp_tool_registry
from competition_copilot.integrations.mcp.server import build_mcp_server, to_sdk_tool


@pytest.fixture(autouse=True)
def offline_and_no_business(monkeypatch):
    # Windows asyncio creates a loopback wakeup socketpair when its loop starts.
    # Initialize that OS mechanism before denying all subsequent connections.
    runner = asyncio.Runner()
    runner.get_loop()
    def reject(*args, **kwargs):
        pytest.fail("Catalog core must not use network or business execution")
    monkeypatch.setattr(socket, "create_connection", reject)
    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)
    monkeypatch.setattr(AgentCapabilityFacade, "execute", reject)
    with runner:
        yield runner


@pytest.fixture
def run(offline_and_no_business):
    def execute(operation):
        async def bounded():
            with fail_after(10):
                return await operation()
        return offline_and_no_business.run(bounded())
    return execute


def test_construction_advertises_tools_only_without_execution():
    server = build_mcp_server()
    assert isinstance(server, Server)
    caps = server.get_capabilities()
    assert caps.tools is not None
    assert caps.resources is None and caps.prompts is None
    assert caps.logging is None and caps.completions is None


def test_real_sdk_list_matches_registry_metadata_schema_and_order(run):
    registry = build_mcp_tool_registry()

    async def scenario():
        async with Client(build_mcp_server(registry)) as client:
            listing = await client.list_tools(cache_mode="bypass")
            assert isinstance(listing, ListToolsResult)
            assert listing.next_cursor is None
            assert [t.name for t in listing.tools] == [t.tool_name for t in registry.tools]
            for actual, expected in zip(listing.tools, registry.tools, strict=True):
                assert actual.description == expected.description
                assert actual.input_schema == expected.input_schema
                assert actual.output_schema == expected.output_schema
                assert actual.title is None and actual.annotations is None
                assert actual.meta is None and actual.execution is None
            data = json.loads(listing.model_dump_json(by_alias=True))
            assert ListToolsResult.model_validate(data) == listing
            assert json.loads(json.dumps(data, allow_nan=False)) == data
    run(scenario)


def test_injected_registry_is_single_catalog_source(run):
    # Local composition policy input, not a client-controlled tool mutation.
    registry = build_mcp_tool_registry()
    first = replace(registry.tools[0], description="Controlled catalog description.")
    injected = replace(registry, tools=(first, *registry.tools[1:]))

    async def scenario():
        async with Client(build_mcp_server(injected)) as client:
            listing = await client.list_tools()
            assert listing.tools[0].description == first.description
            assert len(listing.tools) == len(injected.tools)
    run(scenario)


def test_no_mutating_excluded_or_internal_tools_in_real_listing(run):
    registry = build_mcp_tool_registry()

    async def scenario():
        async with Client(build_mcp_server(registry)) as client:
            listing = await client.list_tools()
            assert {t.name for t in listing.tools} == {t.tool_name for t in registry.tools}
            assert not {"revise_plan", "approve_plan", "reject_plan", "create_human_authority",
                        "resolve_approval", "intent_interpret", "explain_replanning",
                        "grounding_validate", "context_build"} & {t.name for t in listing.tools}
    run(scenario)


@pytest.mark.parametrize("name", ["revise_plan", "approve_plan", "competition_lsit", "unknown"])
def test_unknown_and_excluded_calls_fail_closed(name, run):
    async def scenario():
        async with Client(build_mcp_server()) as client:
            await client.list_tools()
            with pytest.raises(MCPError) as caught:
                await client.call_tool(name, {"approved": True})
            assert caught.value.error.code == INVALID_PARAMS
            assert caught.value.error.message == "UNKNOWN_TOOL"
    run(scenario)


@pytest.mark.parametrize("name", [t.tool_name for t in build_mcp_tool_registry().tools])
def test_every_known_tool_execution_is_disabled(name, run):
    async def scenario():
        async with Client(build_mcp_server()) as client:
            await client.list_tools()
            result = await client.call_tool(name, {"admin_override": True, "secret": "not-echoed"})
            assert result.is_error is True
            assert result.structured_content is None
            assert [item.text for item in result.content] == ["NOT_IMPLEMENTED_P13_3"]
            assert "not-echoed" not in result.model_dump_json()
    run(scenario)


def test_catalog_determinism_across_instances_sessions_and_repeated_requests(run):
    registry = build_mcp_tool_registry()

    async def fetch(server):
        async with Client(server) as client:
            first = await client.list_tools(cache_mode="bypass")
            # Mutating a returned model must not poison the next request/catalog.
            first.tools[0].input_schema.clear()
            return (await client.list_tools(cache_mode="bypass")).model_dump(mode="json")

    async def scenario():
        server = build_mcp_server(registry)
        a = await fetch(server)
        b = await fetch(server)
        c = await fetch(build_mcp_server(build_mcp_tool_registry()))
        assert a == b == c
        assert a["tools"][0]["input_schema"]
    run(scenario)


def test_sdk_projection_returns_detached_json_schemas():
    definition = build_mcp_tool_registry().tools[0]
    tool = to_sdk_tool(definition)
    assert tool.input_schema == definition.input_schema
    tool.input_schema.clear()
    assert to_sdk_tool(definition).input_schema == definition.input_schema
