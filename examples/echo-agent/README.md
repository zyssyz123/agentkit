# echo-agent — M1 smoke test

An echo agent that requires no external services. It exercises the full canonical loop:

```
perception.passthrough -> memory.sliding_window -> planner.echo
                       -> output.streaming_text
                       -> observability.console + observability.jsonl
```

## Run

```bash
# from the monorepo root
uv sync
uv run agentkit run examples/echo-agent/agent.yaml --input "hello, AgentKit!"
```

Expected:

* console events stream live during the run
* the final answer (`Echo: hello, AgentKit!`) is printed
* a per-run trace file appears under `.agentkit/runs/<run_id>.jsonl` (and a parallel
  `<run_id>.events.jsonl` from the JSONL Observability Technique)
