# contexel

[![PyPI](https://img.shields.io/pypi/v/contexel.svg)](https://pypi.org/project/contexel/)
[![CI](https://github.com/maheshvaikri-code/contexel/actions/workflows/ci.yml/badge.svg)](https://github.com/maheshvaikri-code/contexel/actions)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://pypi.org/project/contexel/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**The context element.** Deterministic, dependency-free context shaping for
code-writing agents — the same transform, every run.

When an agent processes a tool's output in code (programmatic tool calling), it
re-derives the reshaping logic on every run — mishandling empty results,
overshooting the budget, producing slightly different code each time. `contexel`
replaces that with vetted, deterministic stages: reshape, dedupe, rank, and trim
tool output to fit a token budget **before** it reaches the model's context
window — identically on every call.

It rides the pattern that already won — code as the transform substrate — rather
than introducing a new primitive. It lives at the **tool → context boundary**:
inside a programmatic-tool-calling sandbox, a tool wrapper, or an MCP server.

## Why not just let the model write it?

For the easy stages — projecting fields, sorting, a simple trim — a capable model
can write the code inline. The reason to reach for `contexel` is **determinism**:
code written fresh each run drifts; an imported, vetted stage behaves the same
every time. When one agent works the same repo across many iterations, runs, and
stories, that consistency is the point — a versioned *context contract*, not
improvised reshaping. (And the hard stages — token-accurate truncation,
cross-source schema `merge` — are easy to get wrong by hand.)

## Install

```bash
pip install contexel              # pure Python, no native deps
pip install "contexel[accurate]"  # add tiktoken for exact token counts
```

## Quickstart

```python
from contexel import select, dedupe, truncate_field, rank, trim_to_budget, trace

raw = search_tool(query=user_query)          # a batch of verbose results

with trace() as t:
    r = select(raw, ["title", "url", "snippet", "published"])  # drop scores/meta
    r = dedupe(r, key="url")
    r = truncate_field(r, "snippet", max_tokens=120)
    r = rank(r, by="published", desc=True)
    r = trim_to_budget(r, max_tokens=1500)

print(t.report())
# select          32 -> 32    6,143 -> 5,339   tokens
# dedupe          32 -> 30    5,339 -> 4,990   tokens
# truncate_field  30 -> 30    4,990 -> 2,245   tokens
# rank            30 -> 30    2,245 -> 2,245   tokens
# trim_to_budget  30 -> 19    2,245 -> 1,419   tokens
# illustrative only — the percentage depends entirely on your data and your
# budget settings; see "How much does it cut?" below

return r   # only this distilled result re-enters the model context
```

## How much does it cut?

A reduction percentage is **not** a property of `contexel` — it depends on how
much genuine redundancy your data carries and how aggressively you set
truncation and budget. Two different things happen:

- **Lossless** — `select` drops unused fields and `dedupe` removes true
  duplicates. These cost nothing; the removed tokens were pure redundancy.
- **By choice** — `truncate_field` and `trim_to_budget` discard detail and
  low-ranked records to hit limits *you* set. Loosen the limits and the savings
  shrink. This is budget enforcement, not free compression.

So treat no single number as a benchmark. What `contexel` guarantees is that it
removes redundancy reliably and enforces your budget deterministically, keeping
the highest-ranked content — work the model would otherwise re-derive by hand,
less reliably, on every run. The magnitude is yours to dial.

## Stages

- `select(records, fields)` — project to the fields you need
- `dedupe(records, key=...)` — drop duplicates, preserving order
- `rank(records, by=..., desc=True)` — sort by a field (missing → last)
- `truncate_field(records, field, max_tokens=...)` — clip a long text field to a token budget
- `trim_to_budget(records, max_tokens=...)` — keep the top records that fit the budget
- `merge(*sources, schema=..., dedupe_key=...)` — normalize heterogeneous tool outputs into one shape

Compose them with `pipeline([...])` — plain in-language composition. Any
`records -> records` callable (even a lambda) is a valid stage, so you can drop
to code for anything irregular and still breakpoint inside it.

```python
from contexel import pipeline, stage, select, dedupe, trim_to_budget

shape = pipeline([
    stage(select, fields=["title", "url", "snippet"]),
    stage(dedupe, key="url"),
    stage(trim_to_budget, max_tokens=1500),
])
return shape(raw)
```

Or apply a pipeline at the **tool boundary** with `@shaped`, so the model calls
the tool normally and never writes the reshaping:

```python
from contexel import shaped, stage, select, dedupe, trim_to_budget

@shaped([
    stage(select, fields=["path", "line", "snippet"]),
    stage(dedupe, key=["path", "line"]),
    stage(trim_to_budget, max_tokens=2000),
])
def search_code(query: str) -> list[dict]:
    return repo.search(query)        # raw, heavy — shaped automatically, identically
```

## Token awareness

Stages reason in tokens, not rows. The default tokenizer needs no native
dependency (a ~4-chars/token estimate); call `contexel.tokens.use_tiktoken()`
for exact counts, or `contexel.tokens.set_tokenizer(fn)` to plug in your own.

## Design

- A *record* is a plain `dict`; a collection is a `list[dict]` — the shape almost
  every tool returns. Every stage is `(records, **params) -> records` and never
  mutates its input, which is what lets them compose.
- The deterministic stages above are free and reproducible. Model-augmented
  stages (relevance ranking, summarization, semantic dedupe) layer on top and
  take an injected model client — these are the next addition.

## Examples

Runnable patterns in [`examples/`](examples/):

- `programmatic_tool_calling.py` — shape a tool's output inside the agent's sandbox code
- `tool_boundary_wrapper.py` — the `@shaped` wrapper pattern
- `mcp_server.py` — shape responses inside an MCP server
- `framework_adapter.py` — a `records ⇄ Document` adapter for LangChain / LlamaIndex

And a full, runnable agent in [`reference_agent/`](reference_agent/) — a
code-execution agent that uses contexel as the deterministic context-economy
layer at the tool → context boundary (`python -m reference_agent`).

## License

MIT
