"""Trusted loopback development transport bridge; no Agent/Domain orchestration."""

import asyncio
from contextvars import ContextVar

from competition_copilot.integrations.agentarts_transport.gateway import GatewayFailure
from competition_copilot.integrations.local_runtime.http import (
    INVOCATION_PATH,
)
from competition_copilot.integrations.local_runtime.http import (
    create_server as create_local_http_server,
)


def bridge_path(runtime_name):
    return f"/runtime/agentarts/{runtime_name}/invoke"


def create_bridge_server(client, *, port=8766, origins=("http://127.0.0.1:5173", "http://localhost:5173")):
    # Reuse P14.5 bounded parsing/drain, exact Origin checks and error serialization.
    # ContextVar scopes transport metadata to this HTTP request/thread/async call.
    session = ContextVar("agentarts_transport_session", default=None)

    class Forwarder:
        handler_invocations = 0

        async def invoke(self, payload):
            self.handler_invocations += 1
            try:
                return await asyncio.to_thread(client.invoke, payload, session.get())
            except GatewayFailure as error:
                return error

    server = create_local_http_server(Forwarder(), port=port, origins=origins)
    base = server.RequestHandlerClass
    path = bridge_path(client.config.runtime_name)

    class Handler(base):
        def do_POST(self):
            if self.path != path:
                self.discard_request_body()
                return self.reply(404, {"error": "NOT_FOUND"})
            # Routing only: the inherited handler keeps /runtime/invoke semantics.
            self.path = INVOCATION_PATH
            token = session.set(self.headers.get("X-Copilot-Session-Id"))
            try:
                return super().do_POST()
            finally:
                session.reset(token)

        def reply(self, status, value):
            if isinstance(value, GatewayFailure):
                status, value = value.status, {"error": value.code}
            return super().reply(status, value)

    server.RequestHandlerClass = Handler
    return server
