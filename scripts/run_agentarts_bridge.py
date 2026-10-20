"""Start the server-side development invocation transport bridge."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from competition_copilot.integrations.agentarts_transport.server import main

if __name__ == "__main__":
    main()
