"""Config loader unit tests — including env-var expansion."""

from __future__ import annotations

import os

from aglet.config import expand_env, load_agent_config


def test_expand_env_simple(monkeypatch):
    monkeypatch.setenv("FOO", "bar")
    assert expand_env("hello ${FOO}!") == "hello bar!"


def test_expand_env_default_when_missing(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    assert expand_env("${MISSING_VAR:-fallback}") == "fallback"
    assert expand_env("${MISSING_VAR:fallback}") == "fallback"


def test_expand_env_default_when_empty(monkeypatch):
    monkeypatch.setenv("EMPTY", "")
    # `:-` returns default when var is unset OR empty (POSIX semantics).
    assert expand_env("${EMPTY:-fallback}") == "fallback"
    # `:` only kicks in when unset; an empty value passes through.
    assert expand_env("${EMPTY:fallback}") == ""


def test_expand_env_returns_empty_when_no_default(monkeypatch):
    monkeypatch.delenv("NOTSET", raising=False)
    assert expand_env("X${NOTSET}Y") == "XY"


def test_load_agent_config_expands_env_vars(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret-key-123")
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(
        """
schema_version: "1.0"
name: env-test
providers:
  - name: x
    type: openai_compat
    config:
      api_key: ${MY_KEY}
      base_url: ${API_URL:-https://api.openai.com/v1}
""",
        encoding="utf-8",
    )
    cfg = load_agent_config(yaml_path)
    assert cfg.providers[0].config["api_key"] == "secret-key-123"
    assert cfg.providers[0].config["base_url"] == "https://api.openai.com/v1"
