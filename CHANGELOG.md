# Changelog

## 0.1.0a9 — marketplace polish + bare-name install (2026-04-22)

Third round of first-time-user dogfood caught three more rough edges on
the plugin-install / discovery path. All three fixed in `aglet-cli 0.1.0a8`.

| # | Bug | Fix |
| --- | --- | --- |
| F7 | `aglet marketplace list` truncated package names to `aglet-builtin-too…` — users couldn't read what to install | Added `overflow="fold"` to the Package column so long names wrap onto multiple lines instead of ellipsising. |
| F8 | `aglet marketplace install` reported every already-installed technique as "newly registered" (same class of bug we fixed earlier for `aglet plugin install`). | Capture the registry state BEFORE pip runs so the diff is against the real prior state. |
| F9 | `aglet plugin install my-new-tech` was interpreted by uv pip as a PyPI distribution name (which doesn't exist) instead of the local directory the user just scaffolded with `aglet plugin new`. | New `_normalise_install_target()` helper: if the target is a bare name AND a local directory with that name + a `pyproject.toml` inside exists, auto-prepend `./` and print a "(interpreted … as a local directory)" breadcrumb. |

Validated against PyPI in a fresh venv:

* `aglet marketplace list` now shows wrapped-but-readable package names
  such as `aglet-builtin-mode` / `l-openai` across two lines.
* `aglet marketplace install aglet-builtin-planner-reflexion` reports
  only `+ technique planner.reflexion` instead of everything.
* `aglet plugin install my-demo` (no `./`) auto-resolves to the local
  directory and prints the inferred path.

## 0.1.0a8 — runtime ctx inspection + plugin install sandboxing (2026-04-22)

Closes the last open dogfood finding — at runtime, users had no way to see
what patches produced which `ctx.metadata` / `scratchpad` / `tool_results`
values. Plus fixed a silently-dangerous bug in `aglet plugin install`.

**aglet-cli 0.1.0a7** ships:

* New `--show-ctx` flag on `aglet run`. After the run completes it prints a
  `rich`-rendered tree of the final AgentContext: raw / parsed input, plan
  final answer, recalled memory items (grouped by source technique),
  scratchpad thoughts (by author), tool round-trips (calls paired with
  results), metadata keys, and budget usage.

* New top-level `aglet inspect <run_id> --config agent.yaml` command.
  Rebuilds ANY past run's AgentContext from its store — the same tree —
  without re-running the agent. Pass `--patches` to also see the full
  change log (which element / technique produced each patch, timestamped
  to milliseconds, plus the field names changed). Makes "why did memory
  end up with that value" a one-command debug, not a Python-scripting
  exercise.

* **Bug fix (subtle!)**: `aglet plugin install` used the bare
  `uv pip install` form without `--python sys.executable`. When the user
  invoked `aglet` via its venv binary without activating the venv, `uv pip`
  picked a nearby conda env instead — the install silently went to the
  wrong interpreter and the freshly "installed" plugin was unreachable.
  Now every pip subcommand is pinned to the Python that's running `aglet`
  itself (`_pip_install_prefix` / `_pip_uninstall_prefix`).

Internal helpers introduced:

* `aglet_cli.main._rebuild_ctx(runtime, run_id, input_text)` – returns the
  replayed AgentContext for a run id.
* `aglet_cli.main._print_ctx_snapshot(runtime, run_id)` – rich tree printer,
  robust against dataclass-vs-dict fields (the JSONL store deserialises
  back to dicts, so the printer uses a `_get()` helper that accepts both).
* `aglet_cli.main._print_patch_log(runtime, run_id)` – timestamped patch
  table.

## 0.1.0a7 — plugin-author dogfood (2026-04-22)

Walked two real plugin-author scenarios end-to-end:

A. **Brand-new `intent` Element** (third-party-intent-element) — defines its
   own Protocol, contributes `intent.keyword` technique, wires in via
   `hooks: after.perception.parse`. Classifies user queries into typed
   IntentLabels stamped onto `ctx.metadata["intent"]`.
B. **New Technique `memory.entity`** (third-party-memory-entity) — implements
   the existing MemoryTechnique contract (recall/store), tracks named
   entities across conversation turns, runs in `parallel_merge` alongside
   `memory.sliding_window`.

Both live under `examples/` as copy-paste reference.

Fixes / polish that fell out of the dogfood:

* **`aglet-cli 0.1.0a6`**
    * New `aglet plugin new <dir> --element X --technique Y [--new-element]`
      scaffolds a complete pyproject.toml + `src/<pkg>/__init__.py` ready
      for `aglet plugin install .`. `--new-element` also wires in the
      second entry-point group for a brand-new Element kind.
    * `aglet plugin install` now captures the registry state BEFORE running
      pip, so the "Newly registered" delta reports only the truly new
      techniques and elements (previously it showed every preexisting
      technique because the registry was lazily empty on CLI startup).

* **New doc: `docs/plugin-development.md`** — a step-by-step guide for
  both scenarios (new technique vs new Element), with a comparison table,
  scaffolder instructions, three bridging strategies for new Elements,
  and links to the working examples in `examples/`.

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
