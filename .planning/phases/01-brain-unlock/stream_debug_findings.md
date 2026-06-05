# Stream Debug Findings — Phase 1 (01-04)

Captured from a real `JARVIS_STREAM_DEBUG=1` session on 2026-06-05 (a Mac-control turn
"abra o Safari e vá no apple.com" + a plain chat turn). Raw lines: `stream_debug.ndjson`.
Resolves the MEDIUM-confidence event shapes that `brain.py think_stream` was built against.

## 1. No token-level streaming — the claude CLI streams whole MESSAGES

`--output-format stream-json --verbose` emits **0 `content_block_delta` / partial events**.
Each assistant turn arrives as a complete `assistant` message with complete content blocks.

**Implication:** there is no ChatGPT-style letter-by-letter effect available from the CLI.
- A single-message reply (e.g. a one-line joke) arrives as ONE `text` block → renders at once.
- Multi-step (computer-use) turns stream **per step**: each `tool_use` and each `text` block
  arrives as it completes, so step labels + interim text appear *during* the turn.

This satisfies ROADMAP Phase 1 criterion 2 ("text + tool-call step labels arrive as they
happen, not only after the turn completes") at the message/step granularity — which is the
finest granularity the `claude` CLI offers.

## 2. `tool_use` shape — CONFIRMED (think_stream is correct)

Observed (line 14, 17):
```
type: "assistant"
  message.content[]: { "type": "tool_use", "name": "<tool>", "input": {...} }
```
`think_stream` reads `block.get("name")` / `block.get("input")` — **correct, verified**.
Examples seen: `name: "ToolSearch"`, `name: "mcp__computer__run_applescript"`.

## 3. `tool_result` / screenshot shape — CORRECTED (think_stream branch is WRONG)

`think_stream` currently looks for a **top-level** `type == "tool_result"` event. That event
type **never occurs**. Tool results actually arrive as **`user`** messages:
```
type: "user"
  message.content[]: { "type": "tool_result", "content": [ ... ] }
```
Inner `content[]` kinds observed this run: `["tool_reference"]`, `["text"]`.

**Screenshot image shape still UNVERIFIED:** this turn used `run_applescript`, not the
`screenshot` tool, so no `image` block was captured. Expected (per Anthropic tool_result
image convention, to confirm on a real screenshot turn):
```
type: "user"
  message.content[]: { "type": "tool_result",
    "content": [ { "type": "image", "source": { "type": "base64", "data": "<b64>" } } ] }
```

### Required fix (owner: Phase 2 — Live Activity UI, which renders steps + screenshots)
In `brain.py think_stream`, replace the `elif t == "tool_result":` branch with handling of
`t == "user"` → iterate `message.content[]` → for `tool_result` blocks, walk their inner
`content[]` and yield `{"type":"screenshot","data": <image.source.data>}` for `image` kinds.
Confirm the exact image path against a real `screenshot`-tool turn before shipping.

**Status:** tool_use confirmed; tool_result/screenshot correction recorded for Phase 2.
No Phase 1 regression — think_stream simply does not yet emit screenshot events (it never
crashes; the unused `tool_result` branch is dead code until corrected).
