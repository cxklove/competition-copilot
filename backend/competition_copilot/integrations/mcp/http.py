"""Official Streamable HTTP hosting boundary; no business/protocol reimplementation."""

from typing import Final

from mcp.server import Server
from starlette.applications import Starlette

# Canonical targets frozen by the REVIEW_PASS P13.0 compatibility matrix.
MCP_UPSTREAM_BASELINE: Final = "2026-07-28"
AGENTARTS_MCP_COMPATIBILITY_VERSION: Final = "2025-11-25"


def build_streamable_http_app(server: Server) -> Starlette:
    """Wrap the same core with SDK negotiation, encoding and ASGI lifespan.

    Stateless HTTP also avoids legacy session storage. Ordinary JSON responses
    need no held-open business stream. No app/server starts on import or build.
    The host/Origin protections remain SDK defaults; production hosting is P16.
    """
    return server.streamable_http_app(stateless_http=True, json_response=True)
