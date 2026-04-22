# Changelog

## 0.1.0a6 — config sanity guards (2026-04-22)

A follow-on dogfood session tested what happens when an agent.yaml is
missing an Element or has `techniques: []`. Found that:

* Missing `planner` or empty `planner.techniques`: run completes silently
  with empty output, exit code 0. **Terrible first-time-user trap.**
* Missing `output`: the planner actually produces an answer but it's never
  rendered. Also silent.
* Unknown technique name (e.g. `name: does_not_exist`): correctly errors.
  ✅ already good.
* Missing `perception` / `safety`: mostly harmless.

Fixed in:

* **aglet 0.1.0a4** — `Runtime.from_config` now sanity-checks the config
  before building anything else. `planner` and `output` are REQUIRED (must
  be declared AND have at least one technique); missing either raises
  `AgentConfigError`. `perception` and `safety` are RECOMMENDED and emit a
  warning via the `aglet.runtime` logger but don't block.

* **aglet-cli 0.1.0a5** — `aglet doctor` surfaces the same distinction
  with `error` (red) and `warn` (yellow) rows before the per-technique
  `ok` list.

The idea is that `aglet doctor` should always be a reliable preflight:
green = `aglet run` will produce a final answer; yellow = probably fine
but notice these; red = the run will fail loudly instead of silently.

## 0.1.0a5 — first-time-user dogfood hot-fixes (2026-04-22)

Ran the README tutorial **verbatim** in a fresh venv and found four real bugs
that blocked new users. All fixed and republished.

| # | Bug | Fix |
| --- | --- | --- |
| 1 | `aglet init` scaffold referenced `observability.jsonl`, which wasn't in the README's minimum install list → the first `aglet run` crashed with "No Technique 'observability.jsonl' registered." | `aglet-cli 0.1.0a4` — scaffold now uses only `observability.console`, matching the quickstart exactly. A comment tells users how to opt into the jsonl exporter. |
| 2 | README's ReAct example used `import: datetime:datetime.utcnow`, but `local_python` only did a single `getattr(module, attr)` so nested class-method paths failed. | `aglet-builtin-tool-local-python 0.1.0a2` — split the post-colon attr on dots and walk deeper. |
| 3 | `--pre` allowed uv to resolve `httpx==1.0.dev3`, which dropped the top-level `httpx.AsyncClient` attribute. Any real LLM call then crashed with AttributeError. | `aglet 0.1.0a3`, `aglet-builtin-model-openai 0.1.0a2`, `aglet-builtin-tool-http-openapi 0.1.0a2` — pinned `httpx>=0.27,<1.0`. |
| 4 | Cosmetic: README badge still said "143 passing" (we are at 162). Scaffold description still said "built with Aglet M1". | README badge bumped; scaffold description rewritten. |

Packages republished: `aglet`, `aglet-cli`, `aglet-builtin-model-openai`,
`aglet-builtin-tool-http-openapi`, `aglet-builtin-tool-local-python`.

Validated against PyPI in a fresh venv: minimum install + `aglet init` +
`aglet run` + tool.utcnow roundtrip + httpx stays at `0.28.1`.

## 0.1.0a4 — M5 completion (2026-04-22)

Two more brand-new distributions finishing M5's "summary + constitutional"
roadmap line item:

* **`aglet-builtin-memory-summary 0.1.0a1`** — rolling LLM-summarised
  conversation memory. When the per-conversation buffer exceeds
  `trigger_chars` characters, the technique asks an LLM to compress the
  oldest half into one paragraph and recalls it on every subsequent turn.
  Pairs naturally with `memory.sliding_window` under `routing: parallel_merge`.
* **`aglet-builtin-safety-constitutional 0.1.0a1`** — declarative principles
  + an LLM judge enforcing them on `pre_check` / `post_check`. Returns
  `PASS` or `BLOCK: <reason>`; block raises
  `ConstitutionalViolationError` which the Runtime converts to a
  `run.failed` event with the reason preserved.

Marketplace index updated to cover both.

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
