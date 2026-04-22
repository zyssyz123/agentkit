# Third-party Element demo — proving "double pluggability"

This is a self-contained third-party plugin that does two things at once:

1. **Contributes a wholly new Element** called `compliance` — i.e. a 10th first-class
   citizen alongside the framework's built-in 9 (perception, memory, planner, …).
2. **Contributes a Technique** (`compliance.cn_pii_scanner`) that implements that Element.

Both are published via standard Python `entry_points` groups, so AgentKit's Runtime
auto-discovers them with no core changes.

## Run

```bash
# from the monorepo root
uv pip install -e examples/third-party-element-demo
uv run agentkit techniques --element compliance
# → compliance / cn_pii_scanner

uv run agentkit run examples/third-party-element-demo/agent.yaml \
  --input "My phone is 13800138000, please call me."
```

The Runtime instantiates a generic `ElementHost` for the unknown `compliance` element
and the agent runs end-to-end. The PII scanner stamps any findings into
`ctx.metadata["compliance_findings"]` via a `ContextPatch`, demonstrating that custom
Elements share the exact same data contract as built-ins.

See `tests/integration/test_third_party_element.py` for an end-to-end test.
