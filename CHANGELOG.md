# Changelog

## 0.1.0a3 — M5 release (2026-04-22)

Two packages republished, one brand-new distribution published:

* **`aglet-cli 0.1.0a3`** — adds the `aglet marketplace` subcommand group
  (`list` / `search [--element]` / `install`) backed by a static index at
  `docs/marketplace.json`. Install pathway still shells out to
  `pip install --pre` so any PyPI name works even if not curated.
  Fixes a subtle `httpx.get(timeout=...)` incompatibility against httpx
  1.0.dev (switched the marketplace fetcher to stdlib `urllib`).
* **`aglet-builtin-planner-workflow 0.1.0a1`** (new) — declarative-DAG planner
  that walks a fixed node graph of tool calls instead of letting an LLM
  decide. Emits the same PLANNER_ACTION / PLANNER_FINAL events as any other
  planner, so it plugs into `executor.sequential` / Hooks / observability
  without any change. Supports `{input}` and `{nodes.<id>[.<field>]}`
  template substitution; explicit `edges:` trigger topo-sort with cycle
  detection.

Non-packaged additions:

* README rewritten as a 5-minute tutorial, with a 2 MB 1200×720 demo gif
  rendered from `docs/media/demo.tape` via [VHS](https://github.com/charmbracelet/vhs).
* Launch blog + Twitter thread + community-submission templates under
  `docs/blog/`.

## 0.1.0a2 (2026-04-22)

### `aglet` core only

* **Bug fix**: `aglet/loader/http.py` was eagerly imported by `aglet.__init__`
  but `httpx` was not declared as a dependency of the `aglet` distribution
  (only by `aglet-builtin-tool-http-openapi` and `aglet-builtin-model-openai`).
  Fresh installs of just `aglet` therefore failed at import time. Added
  `httpx>=0.27` to `aglet`'s direct dependencies.

No other packages republished — they continue to pin `aglet>=0.1.0a1` which
0.1.0a2 satisfies.

## 0.1.0a1 (2026-04-22)

First public alpha. **All 26 PyPI distributions** published from a single monorepo
(20 in the first publish wave; the remaining 6 — `aglet-cli`, `aglet-server`,
`aglet-eval`, and `aglet-builtin-tool-{local-python,mcp,subagent}` — landed in
a second wave once PyPI's per-account "too many new projects per hour" guard
expired ~30 minutes later):

| Tier | Packages |
| --- | --- |
| Core | `aglet`, `aglet-cli`, `aglet-server`, `aglet-eval` |
| Perception | `aglet-builtin-perception-passthrough` |
| Memory | `aglet-builtin-memory-{sliding-window,rag}` |
| Planner | `aglet-builtin-planner-{echo,react,reflexion,tot}` |
| Tool | `aglet-builtin-tool-{local-python,http-openapi,mcp,subagent}` |
| Executor | `aglet-builtin-executor-sequential` |
| Safety | `aglet-builtin-safety-budget` |
| Output | `aglet-builtin-output-streaming-text` |
| Observability | `aglet-builtin-obs-{console,jsonl,otel,langfuse}` |
| Extensibility | `aglet-builtin-extensibility-hooks` |
| Model providers | `aglet-builtin-model-{openai,litellm,mock}` |

### What's in 0.1.0a1

* 9 first-class Element protocols + the ModelProvider plugin point.
* Immutable `AgentContext` + `ContextPatch` event-sourcing model.
* Default canonical Loop with built-in Hook system, Budget enforcement,
  three routing strategies (`all` / `first_match` / `parallel_merge`),
  and four plugin runtimes (in-process, subprocess JSON-RPC, HTTP, MCP).
* `Runtime.resume(run_id)` checkpoint replay over the JSONL store.
* Reflexion + Tree-of-Thoughts planners; multi-agent via `tool.subagent`.
* Eval harness (`agentkit-eval suite.yaml`) with JUnit XML output.
* HTTP+SSE server (`aglet-serve agent.yaml`).
* CLI (`aglet`) with `init` / `run` / `chat` / `resume` / `runs` /
  `elements` / `techniques` / `doctor` / `plugin install|list|remove`.
