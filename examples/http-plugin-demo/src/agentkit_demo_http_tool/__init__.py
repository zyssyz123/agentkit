"""Demo HTTP plugin — a single 'shout' Tool exposed over /list_components + /invoke."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI


def build_app() -> FastAPI:
    app = FastAPI(title="agentkit-demo-http-tool")

    components = [
        {
            "name": "tool.shout",
            "element": "tool",
            "capabilities": ["list", "invoke"],
            "version": "0.1.0",
        }
    ]

    @app.get("/list_components")
    def list_components() -> list[dict[str, Any]]:
        return components

    @app.post("/invoke")
    def invoke(payload: dict[str, Any]) -> Any:
        component = payload.get("component")
        method = payload.get("method")
        args = payload.get("args") or {}
        if component != "tool.shout":
            return {"error": {"code": -32601, "message": f"unknown component {component}"}}
        if method == "list":
            return [
                {
                    "name": "shout",
                    "description": "Return the input text in upper-case with three exclamation marks.",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                        "additionalProperties": False,
                    },
                    "technique": "shout",
                }
            ]
        if method == "invoke":
            text = str(args.get("name") and args.get("arguments", {}).get("text", ""))
            return {
                "call_id": "",
                "output": f"{text.upper()}!!!",
                "error": None,
                "latency_ms": 1,
            }
        if method == "health":
            return {"healthy": True, "detail": ""}
        return {"error": {"code": -32601, "message": f"unknown method {method}"}}

    return app
