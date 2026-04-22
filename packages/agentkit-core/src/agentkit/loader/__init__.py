"""Plugin loader. Only the in-process variant ships in M1; subprocess/HTTP/MCP follow in M3."""

from agentkit.loader.in_process import InProcessRuntime, PluginLoader

__all__ = ["InProcessRuntime", "PluginLoader"]
