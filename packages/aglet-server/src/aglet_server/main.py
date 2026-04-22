"""``aglet-serve`` console script."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from aglet_server.app import build_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Aglet HTTP+SSE server.")
    parser.add_argument(
        "agents",
        nargs="*",
        type=Path,
        help="Paths to agent.yaml files to register at startup.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    app = build_app(agents=args.agents)
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
