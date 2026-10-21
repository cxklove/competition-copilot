"""Standard-library loopback HTTP transport; no Domain/SDK/business imports."""

import asyncio
import ipaddress
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from competition_copilot.integrations.local_runtime.hosting import failure

INVOCATION_PATH = "/runtime/invoke"
MAX_BODY_BYTES = 1024 * 1024


def reject_constant(value):
    raise ValueError("Non-finite JSON is not accepted")


def create_server(host, *, port=8765, bind="127.0.0.1", origins=("http://127.0.0.1:5173", "http://localhost:5173")):
    if not ipaddress.ip_address(bind).is_loopback:
        raise ValueError("Local Runtime must bind loopback only")
    if "*" in origins:
        raise ValueError("Wildcard origins are not allowed")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # No payload/handles/secrets in access logs.

        def reply(self, status, value, *, preflight=False):
            raw = b"" if status == 204 else json.dumps(value, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Local-Handler-Count", str(host.handler_invocations))
            self.send_header("Vary", "Origin")
            origin = self.headers.get("Origin")
            if origin is not None and origin in origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                if preflight:
                    self.send_header("Access-Control-Allow-Methods", "POST")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(raw)

        def discard_request_body(self):
            # Consume a normal bounded POST before closing its connection. Leaving
            # bytes unread can reset the socket before the client receives reply.
            # Invalid/oversized framing must not trigger an unbounded drain or
            # change the early rejection's existing status priority.
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return
            if 0 < length <= MAX_BODY_BYTES:
                self.rfile.read(length)

        def do_OPTIONS(self):
            self.discard_request_body()
            if self.path != INVOCATION_PATH:
                return self.reply(404, {"error": "NOT_FOUND"})
            if self.headers.get("Origin") not in origins:
                return self.reply(403, {"error": "ORIGIN_NOT_ALLOWED"})
            if self.headers.get("Access-Control-Request-Method") != "POST":
                return self.reply(403, {"error": "CORS_METHOD_NOT_ALLOWED"})
            requested = self.headers.get("Access-Control-Request-Headers", "")
            if requested and any(header.strip().lower() != "content-type" for header in requested.split(",")):
                return self.reply(403, {"error": "CORS_HEADERS_NOT_ALLOWED"})
            return self.reply(204, None, preflight=True)

        def do_POST(self):
            if self.path != INVOCATION_PATH:
                self.discard_request_body()
                return self.reply(404, {"error": "NOT_FOUND"})
            if self.headers.get("Origin") not in (None, *origins):
                self.discard_request_body()
                return self.reply(403, {"error": "ORIGIN_NOT_ALLOWED"})
            if self.headers.get_content_type() != "application/json":
                self.discard_request_body()
                return self.reply(415, {"error": "JSON_REQUIRED"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY_BYTES:
                    return self.reply(413, {"error": "PAYLOAD_LIMIT"})
                payload = json.loads(self.rfile.read(length), parse_constant=reject_constant)
            except Exception:
                return self.reply(200, failure("INVALID_RUNTIME_PAYLOAD"))
            try:
                value = asyncio.run(host.invoke(payload))
            except Exception:
                value = failure("RUNTIME_DEPENDENCY_ERROR")
            return self.reply(200, value)

        def do_GET(self):
            return self.reply(404, {"error": "NOT_FOUND"})

    return ThreadingHTTPServer((bind, port), Handler)
