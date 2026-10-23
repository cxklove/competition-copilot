"""TEST ONLY: official transport shape over real P12/Agent/Facade authorities.

The harness never computes business outcomes. Deterministic time/nonces are test
dependencies only; production host randomness is unchanged. No real credential.
"""

# ruff: noqa: E402
# Standalone test subprocess bootstraps the repository package before imports.

import argparse
import asyncio
import json
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from competition_copilot.integrations.agentarts_transport.bridge import (
    create_bridge_server,
)
from competition_copilot.integrations.agentarts_transport.gateway import (
    AgentArtsGatewayClient,
    GatewayConfig,
)
from competition_copilot.integrations.local_runtime.composition import create_local_host
from competition_copilot.integrations.local_runtime.http import create_server

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SYNTHETIC_AUTH = "Bearer synthetic-harness-only-not-a-credential"
LOCK = threading.Lock()


class DeterministicHost:
    def __init__(self):
        self.reset()

    def reset(self):
        self.host = create_local_host(ROOT, clock=lambda: NOW)
        self.sequence = 0

    @property
    def handler_invocations(self):
        return self.host.handler_invocations

    def nonce(self, size):
        self.sequence += 1
        return f"compat-nonce-{self.sequence:06d}"

    async def invoke(self, payload):
        with LOCK, patch("secrets.token_urlsafe", self.nonce):
            return await self.host.invoke(payload)


@contextmanager
def running(*, gateway_timeout=0.5):
    local, remote = DeterministicHost(), DeterministicHost()
    records = []

    class Gateway(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, value, content_type="application/json"):
            raw = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # Test timeout client already closed; not a successful HTTP result.

        def do_GET(self):
            self.reply(200, records) if self.path == "/__test__/observations" else self.reply(404, {})

        def do_POST(self):
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 1024 * 1024:
                return self.reply(413, {})
            body = json.loads(self.rfile.read(size))
            if self.path == "/__test__/reset":
                # Between serial frontend scenarios only; never a product route.
                local.reset()
                remote.reset()
                records.clear()
                self.server.fault = local_server.fault = None
                return self.reply(200, {})
            if self.path == "/__test__/control":
                self.server.fault = body
                return self.reply(200, {})
            records.append({"path": self.path, "body": body,
                            "session": self.headers.get("X-Hw-Agentarts-Session-Id"),
                            "user": self.headers.get("X-Hw-Agentgateway-User-Id"),
                            "authorized": self.headers.get("Authorization") == SYNTHETIC_AUTH,
                            "mcp": self.headers.get("Mcp-Session-Id"),
                            "accept": self.headers.get("Accept")})
            if not records[-1]["authorized"]:
                return self.reply(401, {"message": "not authorized"})
            if self.path != "/runtimes/competition-copilot/invocations?endpoint=dev":
                return self.reply(404, {})
            if not records[-1]["session"]:
                return self.reply(400, {})
            fault, self.server.fault = self.server.fault, None
            if fault:
                if fault.get("delay"):
                    threading.Event().wait(fault["delay"])
                return self.reply(fault.get("status", 200), fault.get("body"), fault.get("content_type", "application/json"))
            return self.reply(200, asyncio.run(remote.invoke(body)))

    gateway = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
    gateway.fault = None
    config = GatewayConfig(gateway_url=f"http://127.0.0.1:{gateway.server_port}",
        runtime_name="competition-copilot", authorization=SYNTHETIC_AUTH,
        endpoint="dev", gateway_user_id="gateway-observer", timeout=gateway_timeout,
        allow_loopback_http=True)
    client = AgentArtsGatewayClient(config)
    bridge = create_bridge_server(client, port=0)
    local_server = create_server(local, port=0)
    local_server.fault = None
    local_handler = local_server.RequestHandlerClass

    class LocalFaultHandler(local_handler):
        """Test-only HTTP fault injection; normal calls retain the real host."""

        def do_POST(self):
            if self.path == "/__test__/control":
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 1024 * 1024:
                    return self.reply(413, {})
                self.server.fault = json.loads(self.rfile.read(size))
                return self.reply(200, {})
            if self.path == "/runtime/invoke" and self.server.fault is not None:
                fault, self.server.fault = self.server.fault, None
                self.discard_request_body()
                return self.reply(fault.get("status", 200), fault.get("body"))
            return super().do_POST()

    local_server.RequestHandlerClass = LocalFaultHandler
    servers = (gateway, bridge, local_server)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for thread in threads:
        thread.start()
    try:
        yield {"local": f"http://127.0.0.1:{local_server.server_port}",
               "bridge": f"http://127.0.0.1:{bridge.server_port}",
               "gateway": config.gateway_url, "client": client,
               "records": records, "remote": remote, "local_host": local,
               "gateway_server": gateway}
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=3)
            assert not thread.is_alive()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-timeout", type=float, default=0.5)
    args = parser.parse_args()
    # Browser rendering adds scheduling load; timeout fault tests retain the default.
    with running(gateway_timeout=args.gateway_timeout) as environment:
        print("COMPAT_URLS=" + json.dumps({k: environment[k] for k in ("local", "bridge", "gateway")}), flush=True)
        # Parent test process owns shutdown. No external network or real credential.
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
