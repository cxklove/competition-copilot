"""Run with python -m competition_copilot.integrations.local_runtime.server."""

import argparse
from pathlib import Path

from competition_copilot.integrations.local_runtime.composition import create_local_host
from competition_copilot.integrations.local_runtime.http import create_server


def main():
    parser = argparse.ArgumentParser(description="Loopback-only offline Agent Runtime")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--origin", action="append", help="Exact allowed development browser origin; repeatable")
    args = parser.parse_args()
    server = create_server(create_local_host(args.root), port=args.port,
                           **({"origins": tuple(args.origin)} if args.origin else {}))
    print(f"LOCAL_RUNTIME_URL=http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
