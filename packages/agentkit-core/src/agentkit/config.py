"""agent.yaml schema + loader."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

# Matches ${VAR}, ${VAR:-default}, ${VAR:default}.
# (?P<name>...)  variable name
# (?P<sep>:-|:)  optional separator introducing a default
# (?P<default>...) optional default value (anything except '}')
_ENV_REF_RE = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:(?P<sep>:-|:)(?P<default>[^}]*))?\}")


class TechniqueConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    config: dict[str, Any] = Field(default_factory=dict)


class ElementConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    techniques: list[TechniqueConfig] = Field(default_factory=list)
    routing: str = "all"


class BudgetConfig(BaseModel):
    max_steps: int = 20
    max_tokens: int = 50_000
    max_seconds: float = 120.0
    max_cost_usd: float = 0.50


class HookConfig(BaseModel):
    on: str
    technique: str
    config: dict[str, Any] = Field(default_factory=dict)


class StoreConfig(BaseModel):
    type: str = "jsonl"  # "jsonl" | "memory"
    directory: str = ".agentkit/runs"


class ProviderConfig(BaseModel):
    """One ModelProvider declaration in agent.yaml `providers:`."""

    model_config = ConfigDict(extra="allow")

    name: str
    type: str  # entry-point name under "agentkit.models"
    config: dict[str, Any] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    name: str
    description: str = ""

    elements: dict[str, ElementConfig] = Field(default_factory=dict)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)

    providers: list[ProviderConfig] = Field(default_factory=list)
    # alias -> "<provider>/<model_id>"
    models: dict[str, str] = Field(default_factory=dict)

    hooks: list[HookConfig] = Field(default_factory=list)
    store: StoreConfig = Field(default_factory=StoreConfig)

    # Optional: dotted module paths to side-effect-import before discovery.
    plugin_modules: list[str] = Field(default_factory=list)


# ---------- loader ---------------------------------------------------------------------------


def expand_env(text: str) -> str:
    """Expand ``${VAR}``, ``${VAR:-default}`` and ``${VAR:default}`` references.

    Unlike :func:`os.path.expandvars` this honours shell-style default values, which
    is the syntax users naturally reach for in YAML config files.
    """

    def _replace(m: re.Match[str]) -> str:
        value = os.environ.get(m.group("name"))
        if value is None or (m.group("sep") == ":-" and value == ""):
            return m.group("default") if m.group("sep") else ""
        return value

    return _ENV_REF_RE.sub(_replace, text)


def load_agent_config(path: str | Path) -> AgentConfig:
    raw = Path(path).read_text(encoding="utf-8")
    expanded = expand_env(raw)
    data = yaml.safe_load(expanded) or {}
    return AgentConfig.model_validate(data)
