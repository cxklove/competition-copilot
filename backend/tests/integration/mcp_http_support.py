"""Local ASGI HTTP fixtures using the real SDK transport, never real sockets."""

import json
from contextlib import asynccontextmanager

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from competition_copilot.integrations.mcp.http import build_streamable_http_app
from competition_copilot.integrations.mcp.server import build_mcp_server

# A logical ASGI URL only. No port is bound, and :0 retains SDK Host protection.
BASE = "http://localhost:0"


class HttpHarness:
    def __init__(self, facade):
        self.facade = facade
        self.server = build_mcp_server(facade=facade)
        self.app = build_streamable_http_app(self.server)
        self.requests = []
        self.responses = []

    async def record_request(self, request):
        try:
            document = json.loads(request.content)
        except (ValueError, TypeError):
            document = {}
        if not isinstance(document, dict):
            document = {}
        params = document.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        self.requests.append({
            "method": document.get("method"),
            "version": request.headers.get("mcp-protocol-version"),
            "offered_version": params.get("protocolVersion"),
            "content_type": request.headers.get("content-type"),
            "accept": request.headers.get("accept"),
        })

    async def record_response(self, response):
        try:
            request = json.loads(response.request.content)
        except (ValueError, TypeError):
            request = {}
        self.responses.append({
            "method": request.get("method") if isinstance(request, dict) else None,
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "session": response.headers.get("mcp-session-id"),
        })

    @asynccontextmanager
    async def lifespan(self):
        async with self.app.router.lifespan_context(self.app):
            yield self

    @asynccontextmanager
    async def http_client(self, *, headers=None, response_hook=None):
        hooks = [self.record_response]
        if response_hook is not None:
            hooks.append(response_hook)
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(self.app), base_url=BASE,
            headers=headers, event_hooks={"request": [self.record_request], "response": hooks},
        ) as http:
            yield http

    @asynccontextmanager
    async def client(self, mode, *, headers=None, response_hook=None):
        async with self.http_client(headers=headers, response_hook=response_hook) as http:
            transport = streamable_http_client(f"{BASE}/mcp", http_client=http)
            async with Client(transport, mode=mode, cache=None, read_timeout_seconds=5) as client:
                yield client


def catalog(result):
    """Compare every Tool field; exclude only catalog protocol/cache envelopes."""
    return [tool.model_dump(mode="json") for tool in result.tools]
