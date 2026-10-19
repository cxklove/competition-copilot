"""Same full seed composition across Agent/Runtime/Facade and all MCP entries."""

import json

import pytest

pytest.importorskip("mcp", reason="Install optional MCP overlay")
pytest.importorskip("langgraph", reason="Install optional Agent overlay")

from agent_e2e_support import Harness, frame
from mcp import Client
from mcp_execution_support import COMPETITION, EDITION, eligibility_payload
from mcp_gateway_support import GatewayHarness
from mcp_http_support import catalog
from mcp_real_support import run as run

from competition_copilot.agents.contracts import CapabilityInvocationRequest
from competition_copilot.integrations.mcp.contracts import McpToolResult
from competition_copilot.integrations.mcp.registry import build_mcp_tool_registry


def canonical(wire):
    document = wire.structured_content
    assert document == json.loads(wire.content[0].text)
    value = McpToolResult.model_validate_json(json.dumps(document, allow_nan=False))
    assert not wire.is_error and value.error is None
    return value.result.model_dump(mode="json")


@pytest.mark.parametrize("tool,payload,intent,capability", [
    ("competition_list", {}, "DISCOVER_COMPETITIONS", "list_competitions"),
    ("competition_get", {"competition_id": COMPETITION}, "GET_COMPETITION_DETAILS", "get_competition"),
    ("competition_editions_list", {"competition_id": COMPETITION}, "GET_COMPETITION_DETAILS", "list_competition_editions"),
    ("competition_edition_get", {"edition_id": EDITION}, "GET_COMPETITION_DETAILS", "get_competition_edition"),
    ("competition_tracks_list", {"edition_id": EDITION}, "GET_COMPETITION_DETAILS", "list_edition_tracks"),
    ("competition_track_get", {"track_id": EDITION + "-engineering-practice"},
     "GET_COMPETITION_DETAILS", "get_competition_track"),
    ("competition_snapshot_build", {"target": {"competition_id": COMPETITION, "edition_id": EDITION},
                                    "observed_at": "2026-10-19T08:00:00+08:00"},
     "CHECK_COMPETITION_CHANGES", "build_competition_snapshot"),
    ("eligibility_check", eligibility_payload("graduate"), "CHECK_ELIGIBILITY", "check_eligibility"),
    ("eligibility_check", eligibility_payload("undergraduate"), "CHECK_ELIGIBILITY", "check_eligibility"),
])
def test_real_authority_receipt_equal_across_all_entries(tool, payload, intent, capability, run):
    prepared = frame(payload, "Explicit real integration request", request_id="cross-entry")
    agent = Harness(prepared, intent, capability)
    registry = build_mcp_tool_registry()
    definition = registry.get(tool)
    raw = {"invocation_id": prepared.routing_invocation_id,
           "source_request_id": prepared.state.request.request_id,
           "arguments_ref": prepared.routing_arguments_ref.model_dump(mode="json"),
           "result_ref": prepared.result_ref.model_dump(mode="json"), "payload": payload}
    value = definition.input_model.model_validate(raw)
    invocation = CapabilityInvocationRequest(invocation_id=value.invocation_id,
        source_request_id=value.source_request_id, intent=intent,
        capability=definition.capability_id, arguments_ref=value.arguments_ref)
    gateway = GatewayHarness(agent.facade)

    async def scenario():
        direct = agent.facade.execute(invocation, {
            "artifact_ref": raw["arguments_ref"], "payload": payload}, result_ref=value.result_ref)
        expected = direct.model_dump(mode="json")
        assert len(agent.calls) == 1
        response = agent.agent.invoke(prepared.state.request)
        assert response.outcome == "COMPLETED"
        assert len(agent.calls) == 2 and agent.receipts[-1].model_dump(mode="json") == expected
        runtime = await agent.adapter.invoke({"request": prepared.state.request.model_dump(mode="json")})
        assert runtime["error"] is None and runtime["response"]["outcome"] == "COMPLETED"
        assert len(agent.calls) == 3 and agent.receipts[-1].model_dump(mode="json") == expected
        model_counts = (len(agent.routing.calls), len(agent.explanation.contexts))
        async with gateway.connect() as client:
            listed = await client.list_tools(cache_mode="bypass")
            assert [t.name for t in listed.tools] == [d.tool_name for d in registry.tools]
            for actual, declared in zip(listed.tools, registry.tools, strict=True):
                assert actual.input_schema == declared.input_schema
            assert canonical(await client.call_tool(tool, raw)) == expected
            assert len(agent.calls) == 4
            for mode in ("legacy", "auto"):
                async with gateway.target.client(mode) as http:
                    assert canonical(await http.call_tool(tool, raw)) == expected
            async with Client(gateway.target.server, cache=None) as local:
                assert canonical(await local.call_tool(tool, raw)) == expected
                full_catalog = await local.list_tools(cache_mode="bypass")
                async with gateway.target.client("auto") as modern:
                    assert catalog(await modern.list_tools(cache_mode="bypass")) == catalog(full_catalog)
        assert len(agent.calls) == 7  # Direct, Agent, Runtime, Gateway, 2 HTTP, local.
        assert model_counts == (len(agent.routing.calls), len(agent.explanation.contexts))
        if tool == "eligibility_check":
            expected_status = "ineligible" if payload["student"]["education_level"] == "graduate" else "unknown"
            assert expected["data"]["status"] == expected_status
            assert expected["audit"]["reasons"] and expected["audit"]["results"]
            sources = [item["source"] for item in expected["data"]["evidence"] if item.get("source")]
            assert sources
            for source in sources:
                assert source["source_url"].startswith("http")
                assert source["source_type"] and source["verification_status"]
                assert "T" in source["observed_at"]
        if tool == "competition_snapshot_build":
            assert expected["data"]["observed_at"] == "2026-10-19T00:00:00Z"
        for field, wrapper in (("competition_id", "competition"), ("edition_id", "edition"), ("track_id", "track")):
            if field in payload and wrapper in expected["data"]:
                assert expected["data"][wrapper]["id"] == payload[field]
    run(scenario)
