"""ModelProvider — pluggable LLM access.

Models are *transversal infrastructure* shared by many Techniques (planner.react,
memory.summary, perception.query_rewrite, memory.rag for embeddings…). They are
therefore not one of the 9 Elements; instead they are first-class plugins under
their own entry-point group ``aglet.models``.

A ``ModelProvider`` exposes one or more *capabilities* (chat / embed / tool_use).
Techniques request a model by **logical alias** (e.g. ``"default"``) which the
``ModelHub`` resolves to ``(provider, concrete_model_id)`` according to the
agent.yaml ``models:`` table.

Configuration shape::

    providers:
      - name: openai
        type: openai_compat
        config:
          api_key: ${OPENAI_API_KEY}
          base_url: https://api.openai.com/v1
      - name: local
        type: ollama
        config:
          base_url: http://localhost:11434

    models:
      default:  openai/gpt-4o-mini
      planner:  openai/gpt-4o
      embedder: openai/text-embedding-3-small
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from importlib import metadata
from typing import Any, Callable, Literal, Protocol, runtime_checkable

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP_MODELS = "aglet.models"


# ---------- value types ---------------------------------------------------------------------


@dataclass(frozen=True)
class ModelMessage:
    """A single chat message passed to a chat-capable provider.

    For assistant messages that issued tool calls, ``tool_calls`` must be populated so
    the provider can correlate subsequent ``role="tool"`` responses by ``tool_call_id``.
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple["ModelToolCall", ...] = ()


@dataclass(frozen=True)
class ModelToolCall:
    """A tool call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelResponse:
    """Aggregated (non-streaming) response from a chat completion."""

    content: str = ""
    tool_calls: tuple[ModelToolCall, ...] = ()
    finish_reason: str = "stop"
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


@dataclass(frozen=True)
class ModelChunk:
    """A streaming delta from a chat completion."""

    delta_content: str = ""
    delta_tool_call: ModelToolCall | None = None
    finish_reason: str | None = None


# ---------- protocol -------------------------------------------------------------------------


@runtime_checkable
class ModelProvider(Protocol):
    """Pluggable LLM provider. Implementations declare which capabilities they support."""

    name: str
    capabilities: frozenset[str]  # subset of {"chat", "stream", "embed", "tool_use"}

    async def setup(self) -> None: ...
    async def teardown(self) -> None: ...

    # Chat
    async def complete(
        self,
        model: str,
        messages: list[ModelMessage],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ModelResponse: ...

    async def stream(
        self,
        model: str,
        messages: list[ModelMessage],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ModelChunk]: ...

    # Embeddings
    async def embed(self, model: str, texts: list[str]) -> list[list[float]]: ...


# ---------- hub ------------------------------------------------------------------------------


@dataclass
class _ProviderEntry:
    name: str
    type: str
    instance: ModelProvider


@dataclass
class ModelHub:
    """Registry of named ModelProvider instances + alias -> (provider, model) resolution.

    Built by the Runtime from the ``providers:`` and ``models:`` blocks of agent.yaml.
    Pass the hub to Techniques via :class:`aglet.protocols.BootContext`.
    """

    providers: dict[str, _ProviderEntry] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)  # alias -> "<provider>/<model_id>"

    def register(self, name: str, type_: str, instance: ModelProvider) -> None:
        if name in self.providers:
            log.warning("ModelProvider %s re-registered; overriding", name)
        self.providers[name] = _ProviderEntry(name=name, type=type_, instance=instance)

    def set_alias(self, alias: str, qualified: str) -> None:
        if "/" not in qualified:
            raise ValueError(
                f"Model alias '{alias}' must point to '<provider>/<model_id>'; got {qualified!r}"
            )
        self.aliases[alias] = qualified

    def resolve(self, alias: str) -> tuple[ModelProvider, str]:
        """Resolve a logical alias (e.g. 'default') to a concrete provider + model id."""
        if alias not in self.aliases:
            raise KeyError(
                f"No model alias '{alias}' configured. Available: {sorted(self.aliases)}"
            )
        provider_name, _, model_id = self.aliases[alias].partition("/")
        if provider_name not in self.providers:
            raise KeyError(
                f"Alias '{alias}' references unknown provider '{provider_name}'. "
                f"Configured providers: {sorted(self.providers)}"
            )
        return self.providers[provider_name].instance, model_id

    def list(self) -> list[str]:
        return sorted(self.providers)

    # ------------------------------------------------------------------
    # entry-point discovery

    @staticmethod
    def discover_factories() -> dict[str, Callable[..., ModelProvider]]:
        """Load all registered ``aglet.models`` factories keyed by their entry-point name.

        Each entry point should expose a callable that takes ``config: dict`` and returns
        a configured :class:`ModelProvider` instance.
        """
        factories: dict[str, Callable[..., ModelProvider]] = {}
        try:
            eps = metadata.entry_points(group=ENTRY_POINT_GROUP_MODELS)
        except TypeError:
            eps = metadata.entry_points().get(ENTRY_POINT_GROUP_MODELS, [])  # type: ignore[assignment]
        for ep in eps:
            try:
                factories[ep.name] = ep.load()
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to load model entry point %s: %s", ep.name, exc)
        return factories
