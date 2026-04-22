# aglet-builtin-planner-workflow

> Aglet declarative-DAG planner: walk a fixed node graph of tool calls instead of letting an LLM decide.

Part of the [Aglet](https://github.com/zyssyz123/agentkit) pluggable Agent
runtime.

Use `planner.workflow` when the call graph is known up front (extract →
summarise → render), and you want the determinism and predictability of a
classical pipeline while still plugging into Aglet's Event / Patch / Budget /
Hook / Observability stack.

## Install

```bash
pip install --pre aglet-builtin-planner-workflow
```

## Example

```yaml
planner:
  techniques:
    - name: workflow
      config:
        nodes:
          - id: fetch
            tool: http_get
            arguments:
              url: "https://example.com/api/{input}"
          - id: final
            final: "Fetched status: {nodes.fetch.status}"
```

The planner yields one tool call per round (PLANNER_ACTION with `next_action`
set), the Runtime dispatches it through the Executor, and the planner resumes
on the next iteration with the result available at `{nodes.<id>}`.

Templates support:

- `{input}` — user's raw input text.
- `{nodes.<id>}` — full output of a previous node.
- `{nodes.<id>.<field>}` — nested-dict field access.

## License

Apache-2.0
