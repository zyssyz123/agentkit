"""Entry point: launch the JSON-RPC server over stdio."""

from __future__ import annotations

from agentkit.plugin_sdk import PluginServer

# Importing the package above triggers ``@register`` decorators.
import agentkit_demo_subprocess_tool  # noqa: F401  (side-effect: registers components)


def main() -> None:
    PluginServer().serve_stdio()


if __name__ == "__main__":
    main()
