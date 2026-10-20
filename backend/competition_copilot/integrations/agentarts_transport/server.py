"""Development proxy startup. No credentials or cloud connections at import time."""

import argparse
import os

from competition_copilot.integrations.agentarts_transport.bridge import (
    create_bridge_server,
)
from competition_copilot.integrations.agentarts_transport.gateway import (
    AgentArtsGatewayClient,
    GatewayConfig,
)


def main():
    parser = argparse.ArgumentParser(description="Trusted AgentArts transport bridge")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    try:
        config = GatewayConfig(gateway_url=os.environ["COPILOT_AGENTARTS_GATEWAY_URL"],
            runtime_name=os.environ["COPILOT_AGENTARTS_RUNTIME_NAME"],
            authorization=os.environ["COPILOT_AGENTARTS_AUTHORIZATION"],
            endpoint=os.environ.get("COPILOT_AGENTARTS_ENDPOINT"),
            gateway_user_id=os.environ.get("COPILOT_AGENTARTS_GATEWAY_USER_ID"))
    except (ValueError, KeyError):
        raise SystemExit("INVALID_AGENTARTS_SERVER_CONFIG") from None
    server = create_bridge_server(AgentArtsGatewayClient(config), port=args.port)
    print(f"AGENTARTS_BRIDGE_URL=http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
