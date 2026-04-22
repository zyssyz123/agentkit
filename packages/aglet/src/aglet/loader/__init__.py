"""Plugin loader.

Four runtime flavours, all behind the same ``load_*_plugin`` shape:

* :func:`aglet.loader.in_process` — Python entry-points, importlib (M1)
* :func:`aglet.loader.subprocess.load_subprocess_plugin` — JSON-RPC stdio (M3)
* :func:`aglet.loader.http.load_http_plugin`            — REST plugin server (M3)
* MCP transport adoption ships via the ``tool.mcp`` Technique today (M2).
"""

from aglet.loader.http import HttpPluginRuntime, load_http_plugin
from aglet.loader.in_process import InProcessRuntime, PluginLoader
from aglet.loader.subprocess import SubprocessPluginRuntime, load_subprocess_plugin

__all__ = [
    "InProcessRuntime",
    "PluginLoader",
    "SubprocessPluginRuntime",
    "load_subprocess_plugin",
    "HttpPluginRuntime",
    "load_http_plugin",
]
