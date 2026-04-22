# Community submissions — copy-paste templates

## 1. Hacker News — Show HN

**Submit at**: https://news.ycombinator.com/submit

### Title (max 80 chars)

```
Show HN: Aglet – every Agent capability is a swappable PyPI package
```

### URL

```
https://github.com/zyssyz123/agentkit
```

### Text (first comment)

```text
Hi HN — I built Aglet because every LLM Agent framework I've used hardcodes
what an Agent is made of: you can swap Tools, maybe swap a memory backend,
but the core Elements (perception, memory, planner, executor, safety,
output, observability, extensibility) are baked into the runtime. Adding a
new kind of concern means forking the framework.

Aglet inverts that. The runtime is a 600-line protocol layer. All 9 Elements
are pluggable. Third parties can also publish a 10th Element kind via Python
entry points — we validate this end-to-end in the repo with a compliance
Element contributed from a standalone package.

One YAML file composes an Agent:

    elements:
      memory:
        techniques:
          - { name: sliding_window }
          - { name: rag, config: { uri: ./vec, top_k: 4 } }
        routing: parallel_merge    # run both, merge hits

      planner:
        techniques:
          - { name: reflexion, config: { inner: react } }

Want ToT sampling instead? Change one line. Want multi-agent? Add
`tool.subagent` and wire sub-agent YAMLs. Want to add a brand-new Element
the framework doesn't know about? Publish a package declaring it under the
`aglet.elements` entry-point group.

26 PyPI distributions shipped yesterday under Apache-2.0, 143 tests
passing, real-LLM end-to-end verified with gpt-4o-mini and an OpenAI-compat
provider. Checkpoint/resume via event-sourced ContextPatches, FastAPI+SSE
server, declarative eval harness, four plugin runtimes (in-process,
subprocess JSON-RPC, HTTP, MCP).

I'd love feedback on:

- Whether the "both layers pluggable" design actually buys you the
  flexibility I claim, or whether the complexity tax outweighs it.
- Is the Element list right? Would you collapse/split any of the 9?
- The subprocess plugin protocol is JSON-RPC over stdio. I considered
  WASM but chickened out for M3. Worth revisiting?

Full architecture writeup with UML (class, sequence, state, deployment) at
  https://github.com/zyssyz123/agentkit/blob/main/docs/architecture.md

Blog post on why / how:
  https://github.com/zyssyz123/agentkit/blob/main/docs/blog/launch.md
```

---

## 2. awesome-llm PRs

Most awesome-llm lists take one-line entries. Candidates to submit to:

### https://github.com/Hannibal046/Awesome-LLM

Section: **Applications & Use-Cases** → **Agents & Tool Use**
Line to add (keep alphabetical order inside the list):

```markdown
- [Aglet](https://github.com/zyssyz123/agentkit) - A pluggable Agent runtime where every Element (perception, memory, planner, tool, executor, safety, output, observability, extensibility) and every Technique is distributed as its own PyPI package.
```

### https://github.com/kaushikb11/awesome-llm-agents

Section: **Frameworks**

```markdown
- [Aglet](https://github.com/zyssyz123/agentkit) — Two-dimensional pluggable Agent runtime: 9 Elements × N Techniques, all distributed via PyPI entry points. Apache-2.0.
```

### https://github.com/e2b-dev/awesome-ai-agents

Section: **Open-Source AI Agents Frameworks**

```markdown
- **Aglet** — Pluggable Agent runtime where every Element and Technique is a swappable PyPI package. Hooks, checkpoint/resume, multi-agent via `tool.subagent`, Reflexion + Tree-of-Thoughts planners, declarative eval harness. [GitHub](https://github.com/zyssyz123/agentkit) · [PyPI](https://pypi.org/project/aglet/)
```

### https://github.com/e-p-armstrong/amplifier-awesome-llm-agents

Same line as above; keep alphabetical.

### https://github.com/EvanZhuang/awesome-llm-tool-use

Section: **Open-Source Tools**

```markdown
- [aglet-builtin-tool-mcp](https://pypi.org/project/aglet-builtin-tool-mcp/) — MCP stdio client as a pluggable Tool Technique for the [Aglet](https://github.com/zyssyz123/agentkit) runtime.
```

---

## 3. r/LocalLLaMA

**Subreddit**: https://www.reddit.com/r/LocalLLaMA/

### Title

```
[Open-source] Aglet — a pluggable Agent runtime where every capability (including new Element kinds) is a PyPI package
```

### Body

Paste the first 2/3 of the launch blog post. Keep the mermaid diagram out
(reddit strips it). Close with direct links:

```
Repo:      https://github.com/zyssyz123/agentkit
PyPI:      https://pypi.org/project/aglet/
Blog:      https://github.com/zyssyz123/agentkit/blob/main/docs/blog/launch.md
Arch doc:  https://github.com/zyssyz123/agentkit/blob/main/docs/architecture.md
```

---

## 4. LangChain / LlamaIndex Discord community channels

Short "hey I built this, would love feedback" post, 3-4 lines. Template:

```
Hey folks — I've been chewing on "why is every Agent framework a fork of
itself" and ended up building Aglet: every Element (perception/memory/
planner/tool/executor/safety/output/observability/extensibility) AND every
Technique within an Element is a PyPI package.

Repo: https://github.com/zyssyz123/agentkit   ·   PyPI: https://pypi.org/project/aglet/

Would love blunt feedback on the pluggable-Element design — is this a useful
abstraction or am I overfitting to my own pain?
```

---

## 5. DEV.to / Medium cross-posts

The blog post at `docs/blog/launch.md` is already in a DEV-compatible
Markdown dialect. To publish:

1. Copy `docs/blog/launch.md` into DEV.to's editor as-is.
2. Add front matter:

   ```
   ---
   title: "Aglet: every Agent capability is a swappable plugin"
   published: true
   tags: python, llm, ai, opensource
   canonical_url: https://github.com/zyssyz123/agentkit/blob/main/docs/blog/launch.md
   cover_image: https://raw.githubusercontent.com/zyssyz123/agentkit/main/docs/media/demo.gif
   ---
   ```

3. Commit the rendered gif before publishing so `cover_image` resolves.

---

## Submission timing advice

* **Hacker News**: best on weekday mornings Pacific time (8-10am).
* **r/LocalLLaMA**: any weekday evening Pacific; weekends are quieter.
* **Twitter**: Tue-Thu afternoons tend to do well; tag
  @LangChainAI, @llama_index, @AnthropicAI to increase reach.
* **awesome-llm lists**: one PR per repo, not as a batch — reviewers
  dislike bulk submissions.
