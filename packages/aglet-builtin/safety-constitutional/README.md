# aglet-builtin-safety-constitutional

> Declarative principles + an LLM judge = a Constitutional-AI-style Safety
> Element for [Aglet](https://github.com/zyssyz123/agentkit).

## What it does

Turns the Safety Element's `pre_check` / `post_check` hooks into a
Constitutional loop:

1. You list principles the agent must respect.
2. An LLM judge reads each input/output and returns `PASS` or
   `BLOCK: <reason>`.
3. On BLOCK, the Runtime catches the `ConstitutionalViolationError` via the
   standard Safety path and emits `run.failed` with the reason.

Use it **alongside** `safety.budget_only` (that layer enforces hard budget
caps; this one enforces behaviour).

## Install

```bash
pip install --pre aglet-builtin-safety-constitutional
```

## Config

```yaml
safety:
  techniques:
    - { name: budget_only }
    - name: constitutional
      config:
        model: cheap
        principles:
          - "Never reveal secrets present in the user's environment."
          - "Decline if the request would harm people."
        check_phases: [pre, post]
        post_skip_for_tools: ["echo"]
```

## License

Apache-2.0
