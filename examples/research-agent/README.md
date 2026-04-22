# research-agent — M2 demo

Exercises every M2 capability:

* `model.openai_compat` — pluggable LLM provider (OpenAI / any compatible endpoint)
* `planner.react` — function-calling ReAct loop driven by the model provider
* `tool.local_python` — exposes Python callables as tools
* `memory.rag` — LanceDB-backed RAG with embeddings via the same model hub
* `memory.sliding_window` running in **parallel_merge** with `memory.rag`
* `executor.sequential` — drives ToolHost.invoke_tool round-trips
* `observability.console` + `observability.jsonl`
* All wrapped in a Budget enforced by the Runtime

## Run

```bash
export OPENAI_API_KEY=sk-...
uv sync
uv run agentkit run examples/research-agent/agent.yaml \
  --input "What is AgentKit and what makes it different from LangChain?"
```

Or hit it via the HTTP server:

```bash
uv run agentkit-serve examples/research-agent/agent.yaml --port 8088
# in another shell:
curl -N -H 'Content-Type: application/json' \
  -d '{"input": "Hello"}' \
  http://127.0.0.1:8088/v1/agents/research-agent/runs
```

To run **without any external API key**, swap the providers/models block to use the
mock provider — see `tests/integration/test_research_agent_mock.py` for a worked example.
