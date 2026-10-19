"""Test-only Gateway contract profile, not a Huawei emulator or deployment.

See frozen P13.0 and Huawei agentarts_10_024/063: legacy negotiation, tools,
omitted discovery metadata and event-stream client responses. Official SDKs own
both wire boundaries; every upstream call uses the unchanged real /mcp endpoint.
"""

import json
from contextlib import asynccontextmanager

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server import Server
from mcp.types import ListToolsResult
from mcp_http_support import HttpHarness

from competition_copilot.integrations.mcp.http import (
    AGENTARTS_MCP_COMPATIBILITY_VERSION,
    build_streamable_http_app,
)


class GatewayHarness:
    def __init__(self, facade, *, text_only=False):
        self.target = HttpHarness(facade)
        self.text_only = text_only
        self.methods = []
        self.content_types = []

    @asynccontextmanager
    async def connect(self, *, headers=None):
        # SDK ASGI lifespans are single-use. Fresh transport host, same target
        # core/registry/dispatcher/dependencies, across independent connections.
        self.target.app = build_streamable_http_app(self.target.server)
        async with self.target.lifespan(), self.target.client("legacy", headers=headers) as upstream:
            assert upstream.session.protocol_version == AGENTARTS_MCP_COMPATIBILITY_VERSION

            async def list_tools(context, params):
                result = await upstream.list_tools(cache_mode="bypass")
                # Model documented omissions, never maintain another tool list.
                tools = []
                for tool in result.tools:
                    schema = json.loads(json.dumps(tool.input_schema, allow_nan=False))
                    schema.pop("$schema", None)
                    tools.append(tool.model_copy(update={
                        "input_schema": schema, "output_schema": None,
                        "annotations": None, "icons": None,
                    }))
                return ListToolsResult(tools=tools)

            async def call_tool(context, params):
                result = await upstream.call_tool(params.name, params.arguments, meta=params.meta)
                # Conservative fallback test: structuredContent preservation is
                # not assumed. Existing canonical JSON text must suffice too.
                if self.text_only:
                    return result.model_copy(update={"structured_content": None})
                return result

            proxy = Server("gateway-contract-test", on_list_tools=list_tools, on_call_tool=call_tool)
            app = proxy.streamable_http_app(stateless_http=True, json_response=False)

            async def request_hook(request):
                document = json.loads(request.content) if request.content else {}
                assert isinstance(document, dict)  # No JSON-RPC batches.
                assert "task" not in (document.get("params") or {})
                method = document.get("method")
                if method and not method.startswith("notifications/"):
                    assert method in {"initialize", "tools/list", "tools/call", "ping"}
                    self.methods.append(method)

            async def response_hook(response):
                self.content_types.append(response.headers.get("content-type", ""))

            async with app.router.lifespan_context(app), httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app), base_url="http://localhost:0",
                headers=headers, event_hooks={"request": [request_hook], "response": [response_hook]},
            ) as http:
                transport = streamable_http_client("http://localhost:0/mcp", http_client=http)
                async with Client(transport, mode="legacy", cache=None, read_timeout_seconds=5) as client:
                    assert client.session.protocol_version == AGENTARTS_MCP_COMPATIBILITY_VERSION
                    yield client
