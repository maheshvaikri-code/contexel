<p align="center">
  <img src="https://raw.githubusercontent.com/maheshvaikri-code/contexel/main/logo/contexel_logo.png" width="340" alt="contexel logo">
</p>

**The context element.** Deterministic, dependency-free context shaping for
code-writing agents — the same transform, every run.

## Why this exists

An agent's tools return big lists of records: search hits, file reads, API
responses. Before they reach the model's context window they must be cut
down — and today that cutting is usually code the model improvises fresh
each run, which **drifts**: different field choices, different truncation,
different survivors, every time. contexel replaces the improvisation with
vetted, versioned stages at the tool → context boundary. Same input,
byte-identical context, on every run — a *context contract* instead of a
nightly rewrite.

## What you get

Six deterministic pipeline stages plus a `merge` combiner, over plain
`list[dict]` — the shape tools already return — with composition and
observability:

- `select` — project to the fields you need (lossless)
- `dedupe` — drop duplicates by key, type-qualified, order preserved (lossless)
- `rescore` — BM25-style lexical relevance derived from the records' own
  text, so ranking doesn't have to trust the tool's score
- `rank` — stable sort, missing-field records last
- `truncate_field` — clip a text field to a token cap, never exceeding it
- `trim_to_budget` — keep the top records that fit a token budget
- `merge` — unify differently-shaped tool outputs into one schema
- `pipeline([...])` / `@shaped` / `trace()` — compose, pin at the tool
  boundary, and inspect what every stage removed

Token counting is pluggable twice over: the *tokenizer* (a dependency-free
estimate by default; `tokens.use_tiktoken()` for exact) and the
*serializer* (budgets are priced in the encoding your boundary actually
emits — JSON by default, or e.g. an [ISON](https://ison.dev) table).

No embeddings, no model calls, **zero dependencies** — pure Python 3.9+.

## Sixty seconds

```python
from contexel import select, dedupe, rescore, truncate_field, rank, trim_to_budget, trace

raw = search_tool(query=user_query)          # a batch of verbose results

with trace() as t:
    r = select(raw, ["title", "url", "snippet", "published"])
    r = dedupe(r, key="url")
    r = rescore(r, query=user_query, fields=("title", "snippet"))
    r = truncate_field(r, "snippet", max_tokens=120)
    r = rank(r, by="score", desc=True)
    r = trim_to_budget(r, max_tokens=1500)

print(t.report())    # per-stage: records in -> out, tokens before -> after
context = r          # only this distilled result enters the model's context
```

Or pin the policy at the tool boundary, so the model never sees raw output:

```python
from contexel import shaped, stage, select, dedupe, trim_to_budget

@shaped([
    stage(select, fields=["path", "line", "snippet"]),
    stage(dedupe, key=["path", "line"]),
    stage(trim_to_budget, max_tokens=2000),
])
def search_code(query: str) -> list[dict]:
    return repo.search(query)     # shaped identically, every call
```

## Measured, not asserted

Benchmarked on the full CodeSearchNet python/test split (22,176 real
functions → 28,047 search-tool records) with 100 ground-truth episodes:
contexel is the only implementation among the near-neighbours
(hand-written glue, toolz, langchain-core, llama-index-core) that covers
all the operations natively, holds a 1,500-token budget in 100% of
episodes, keeps the needed record in 100% of them under both a strong and
a weak retrieval signal, and spends 100% of context tokens on unique,
needed fields — at 0 dependencies and a 13 ms import. It is also the
slowest budget-compliant row, *because it does the most work per record* —
and the limits are stated with the same care: recall@budget is bounded by
query specificity for any shaper, and `rescore` is lexical, not semantic.

Determinism is proven, not promised: the suite hashes the same contract's
output across fresh interpreters with different `PYTHONHASHSEED` values —
same SHA-256 every time, even when raw tool output carries fresh request
ids.

Full method and tables:
[benchmarks/COMPARISON.md](https://github.com/maheshvaikri-code/contexel/blob/main/benchmarks/COMPARISON.md)
·
[benchmarks/RESULTS.md](https://github.com/maheshvaikri-code/contexel/blob/main/benchmarks/RESULTS.md)

## Where it fits

Inside agent-written code (programmatic tool calling), as a `@shaped` tool
wrapper, inside an MCP server, under LangChain/LlamaIndex via a thin
adapter, or ahead of a token-efficient encoding — each with a runnable
example in
[`examples/`](https://github.com/maheshvaikri-code/contexel/tree/main/examples),
plus a complete no-API-key reference agent
(`python -m reference_agent`).

## Links

- **Docs:** https://maheshvaikri-code.github.io/contexel/
- **Source:** https://github.com/maheshvaikri-code/contexel
- **Changelog:** https://github.com/maheshvaikri-code/contexel/blob/main/CHANGELOG.md
- **License:** MIT
