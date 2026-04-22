"""Demo subprocess plugin — exposes a single 'reverse_text' Tool Technique."""

from __future__ import annotations

from aglet.plugin_sdk import register


@register(element="tool", name="reverse")
class ReverseTool:
    """A toy Tool living in its own subprocess to validate the JSON-RPC stdio path."""

    capabilities = ("list", "invoke")
    version = "0.1.0"

    async def list(self) -> list[dict]:
        return [
            {
                "name": "reverse_text",
                "description": "Return the input text with the characters reversed.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "technique": "reverse",
            }
        ]

    async def invoke(self, name: str, arguments: dict) -> dict:
        if name != "reverse_text":
            return {"output": None, "error": f"unknown tool {name}", "latency_ms": 0}
        text = str(arguments.get("text", ""))
        return {"output": text[::-1], "error": None, "latency_ms": 0}

    async def health(self) -> dict:
        return {"healthy": True, "detail": ""}
