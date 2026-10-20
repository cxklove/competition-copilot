"""Repository-local startup, no installation or AgentArts SDK bootstrap required."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from competition_copilot.integrations.local_runtime.server import main

if __name__ == "__main__":
    main()
