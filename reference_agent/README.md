# Reference agent — contexel at the tool → context boundary

A complete, runnable code-execution agent that uses **contexel** as the
deterministic context-economy layer. It is the reusable form of the pattern the
industry has converged on — *code execution with MCP* / programmatic tool
calling — with the one piece that pattern usually leaves improvised made
explicit: the shaping of tool output before it re-enters context.

## Run it

```bash
pip install -e .                      # from the contexel repo root
python -m reference_agent             # scripted model — no API key needed
python -m reference_agent.demo --live # real model — needs ANTHROPIC_API_KEY
```

The scripted run is fully deterministic, which is the point of the demo.

## The loop

1. The model proposes **either** Python code to run **or** a final answer.
2. Code runs in a sandbox namespace that exposes the tools and the contexel
   stages. Only the distilled `result` it assigns is folded back into context.
3. Repeat until the model answers or the step budget is hit.

Tool output never enters context raw. It is shaped two ways, which stack:

- **At the tool boundary** — each tool is wrapped with `@shaped(<contract>)`, so
  even a direct call returns bounded, reshaped records (`shaping.py`).
- **In the agent's code** — the model can shape further inline with
  `pipeline([...])` for what a given step needs.

## Why this is more than an example

The stages are deterministic and the contracts drop nondeterministic noise, so
**the context that gets built is identical on every run** — a versioned *context
contract*, not reshaping the model re-derives each time. The tests prove it:

- `test_context_is_identical_across_runs` — two runs build byte-identical context.
- `test_contract_neutralizes_nondeterministic_noise` — the raw tool output
  carries a fresh `request_id` each call, but the shaped output that reaches
  context is identical.

## Files

| File | Role |
|------|------|
| `shaping.py` | The **context contracts** — one named contexel pipeline per tool |
| `tools.py` | An in-memory repo + 4 tools, each `@shaped` with a contract |
| `context.py` | `ContextWindow` — token accounting + FIFO budget eviction |
| `model.py` | `ModelClient` protocol, `ScriptedClient` (no key), `AnthropicClient` (live) |
| `agent.py` | The loop + the reference sandbox runner |
| `demo.py` | The runnable end-to-end demo |
| `test_reference_agent.py` | Deterministic tests, including the guarantees above |

## Production note

`run_code` uses `exec` in-process. That is a **reference**, not a security
boundary — untrusted model-authored code must be isolated (subprocess, container,
gVisor/seccomp, microVM). The contexel pattern at the boundary is identical
regardless of how you isolate the execution.
