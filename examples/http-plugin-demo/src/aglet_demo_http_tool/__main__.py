"""Run the demo HTTP plugin under uvicorn."""

from __future__ import annotations

import argparse

import uvicorn

from aglet_demo_http_tool import build_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    uvicorn.run(build_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
