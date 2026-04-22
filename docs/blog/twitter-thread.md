# Twitter / X thread for Aglet launch

Paste one tweet per message in a thread. Each row below respects the 280-char
limit (URLs count as 23). Total: 14 tweets.

---

**1/**
Shipping Aglet today: a pluggable Agent runtime where every Element
(perception, memory, planner, tool, executor, safety, output, observability,
extensibility) AND every Technique within an Element is distributed as its
own PyPI package.

One YAML file composes your Agent. 🧵

---

**2/**
Most Agent frameworks hardcode memory/planner/tool semantics into the
runtime. Swapping one means forking the framework.

Aglet inverts it: the runtime is a protocol layer. All 9 Elements are
plugins. Third parties can even publish wholly new Element kinds.

---

**3/**
Minimum runnable Agent, in 30 MB and two commands:

```
pip install --pre aglet aglet-cli \
  aglet-builtin-{perception-passthrough,memory-sliding-window,\
                 planner-echo,output-streaming-text,\
                 safety-budget,obs-console}

aglet init my-agent && aglet run my-agent/agent.yaml --input "hello"
```

---

**4/**
Want a real LLM loop? Add `aglet-builtin-planner-react` +
`aglet-builtin-model-openai`. Flip the planner block in YAML. No code.

Want self-critique? Swap `react` -> `reflexion` in the same file.

Want parallel candidate sampling? Swap it for `tot` (Tree of Thoughts).

---

**5/**
Multi-agent orchestration is *just a Tool technique*
(`aglet-builtin-tool-subagent`). Parent agent calls sub-agents with the same
function-calling API it uses for any other tool.

No "meta-planner" concept. No team protocol. ~100 lines.

---

**6/**
AgentContext is immutable. Every Element returns a ContextPatch. The
runtime appends patches to a JSONL file per run.

Free replay. Free checkpoint. `Runtime.resume(run_id)` picks up where a
crashed run left off.

---

**7/**
Four plugin runtimes behind one protocol:

- In-process (Python entry points)
- Subprocess (JSON-RPC 2.0 over stdio)
- HTTP (GET /list_components + POST /invoke)
- MCP (as a Tool technique)

Your plugin can be Python, Rust, Go, anything speaking JSON on stdio.

---

**8/**
The "publish a new Element kind" test is 60 lines:

```toml
[project.entry-points."aglet.elements"]
compliance = "my_pkg:ComplianceProtocol"

[project.entry-points."aglet.techniques"]
"compliance.cn_pii_scanner" = "my_pkg:CnPiiScanner"
```

pip install -> aglet auto-discovers. Zero core changes.

---

**9/**
Declarative eval harness is built in:

```yaml
agent: ./agent.yaml
cases:
  - input: "what's the weather?"
    expected_contains: ["temperature"]
    max_steps: 3
```

`aglet-eval suite.yaml --junit junit.xml` → CI-ready.

---

**10/**
26 PyPI distributions shipped in the first release window:

- 4 core (aglet, aglet-cli, aglet-server, aglet-eval)
- 19 built-in Techniques (ReAct, Reflexion, ToT, MCP, RAG, OTel, LangFuse…)
- 3 model providers (OpenAI-compat, LiteLLM, Mock)

All under Apache-2.0.

---

**11/**
Tests: 143 passing in <1s. Real LLM end-to-end validated against OpenAI
gpt-4o-mini (~5s per simple turn).

Clean-venv smoke install against PyPI itself passes: the entry-points
plugin discovery genuinely works across distribution boundaries.

---

**12/**
Two rough edges we hit and documented:

- `aglet 0.1.0a1` shipped missing `httpx` as a direct dep. Caught in a
  clean venv, hot-fix 0.1.0a2 within minutes.
- PyPI rate-limits "too many new projects / hour". Pace bulk publishes
  with `--skip-existing`.

---

**13/**
Next up (M5):

- Static marketplace index + `aglet marketplace search/install` CLI
- `planner.workflow` declarative DAG for known call graphs
- Summary / KG / Episodic memory techniques
- Constitutional-AI safety layer

Protocol freeze at 1.0; expect breaking changes through 0.x.

---

**14/**
If the "every Element is pluggable" thesis resonates:

⭐ https://github.com/zyssyz123/agentkit
📦 https://pypi.org/project/aglet/

Even more valuable than a star — publish a new Technique under the
`aglet.techniques` entry-point group. We auto-discover it the moment it's
installed. No PR needed.

