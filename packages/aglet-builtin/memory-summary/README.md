# aglet-builtin-memory-summary

> Rolling LLM-summarised conversation memory — the right Memory Technique for
> long chats where a sliding window would drop important context.

Part of the [Aglet](https://github.com/zyssyz123/agentkit) pluggable Agent runtime.

## What it does

When the per-conversation buffer grows past `trigger_chars`, the technique
asks an LLM to compress the oldest half of the history into a single short
paragraph and recalls that summary on every subsequent turn. Recent turns are
kept verbatim.

Best combined with `memory.sliding_window` under `routing: parallel_merge`:

```yaml
memory:
  techniques:
    - { name: sliding_window, config: { max_messages: 10 } }
    - name: summary
      config:
        model: cheap
        trigger_chars: 6000
        keep_recent: 6
  routing: parallel_merge
```

## Install

```bash
pip install --pre aglet-builtin-memory-summary
```

## Config

| Key | Default | Description |
| --- | --- | --- |
| `model` | `default` | Model alias (from agent.yaml `models:`) used for compression |
| `trigger_chars` | `6000` | Compress when the conversation buffer exceeds this many chars |
| `keep_recent` | `6` | Number of most-recent messages kept verbatim |
| `summary_prefix` | `"[Prior conversation summary]"` | Label prepended to recalled summaries |

## License

Apache-2.0
