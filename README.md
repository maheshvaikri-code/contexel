<p align="center">
  <img src="logo/contexel_logo.png" width="340" alt="contexel logo">
</p>

<p align="center">
  <a href="https://pypi.org/project/contexel/"><img src="https://img.shields.io/pypi/v/contexel?label=pypi" alt="PyPI"></a>
  <a href="https://github.com/maheshvaikri-code/contexel/actions"><img src="https://github.com/maheshvaikri-code/contexel/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python 3.9+"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/dependencies-0-brightgreen.svg" alt="Zero dependencies"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT license"></a>
</p>

**The context element.** Deterministic, dependency-free context shaping for
code-writing agents — the same transform, every run.

**Docs site:** [maheshvaikri-code.github.io/contexel](https://maheshvaikri-code.github.io/contexel/)
— architecture with a live budget demo, guides, the stage reference, and the
full benchmark story. Served from this repo's [site/](site/) directory (also
browsable locally: open `site/index.html`).

An agent's tools return big lists of records: search hits, file reads, API
responses. Before they reach the model's context window they must be cut
down — and today that cutting is usually code the model improvises fresh
each run, which drifts: different field choices, different truncation,
different survivors, every time. contexel replaces the improvisation with
vetted, versioned stages at the **tool → context boundary**. Same input,
byte-identical context, on every run.

## What it does, and exactly how

A *record* is a plain `dict`; a collection is `list[dict]` — the shape
tools already return. Every stage is `(records, **params) -> records`,
never mutates its input, and composes with the others:

| Stage | What it does | How, exactly |
|---|---|---|
| `select(records, fields)` | keep only the fields you need | per-record projection onto the keep-list, order preserved |
| `dedupe(records, key=...)` | drop duplicate records | type-qualified fingerprint of the key fields (`1`, `1.0`, `True`, `"1"` stay distinct); first occurrence wins, order preserved |
| `rescore(records, query=...)` | score relevance from evidence, instead of trusting the tool's score | BM25-style, computed inside the batch: per-term IDF `ln((N-df+0.5)/(df+0.5)+1)` × saturating term frequency `tf/(tf+1.5)`, exact word-boundary matching (`value` ≠ `values`, snake_case splits), plus a bonus when consecutive query terms appear in order within 80 chars |
| `rank(records, by=...)` | order by importance | stable sort on a field or key function; records missing the field go last |
| `truncate_field(records, field, max_tokens=...)` | clip one long text field | longest prefix that fits the token cap — closed-form for the built-in estimator, binary search for custom tokenizers — then `…` |
| `trim_to_budget(records, max_tokens=...)` | keep the top records that fit a budget | greedy prefix: each record costs the token count of its serialized text (+2 list framing); stops before the budget is crossed |
| `merge(*sources, schema=...)` | unify differently-shaped tool outputs | maps candidate field names onto one schema, first match wins; optional cross-source dedupe |

Compose them with `pipeline([...])` — plain function composition, any
`records -> records` callable is a valid stage — or attach a pipeline to a
tool with `@shaped` so the model never sees raw output. `trace()` records
what every stage removed, so a shaping decision is inspectable instead of
silent.

All of it is stdlib-only Python. No embeddings, no model calls, no
dependencies — which is what makes the determinism claim checkable: the
benchmark suite hashes the output of the same contract across fresh
interpreters with different `PYTHONHASHSEED` values and gets the same
SHA-256 every time ([benchmarks/RESULTS.md](benchmarks/RESULTS.md)).

## What the benchmark shows — and how to read it

Measured on real, public data: the full CodeSearchNet python/test split
(22,176 functions), reconstructed into 28,047 search-tool records with
genuine duplicates, plus 100 ground-truth episodes where the record the
agent *needed* is known in advance. Full method and tables in
[benchmarks/COMPARISON.md](benchmarks/COMPARISON.md); reproduce with
`python -m benchmarks.competitors` after `pip install -e ".[benchmarks]"`
(the first run downloads the CodeSearchNet split, ~30 MB).

| Implementation | Native ops | ms @28k | ms/episode | Recall % | Compliance % | Useful % | Import ms | Deps |
|---|---|---|---|---|---|---|---|---|
| **contexel** | **6/6** | 59 | 14.9 | **100 / 100** | **100** | **100** | 13 | **0** |
| hand-written | 0 | 27 | 1.6 | 93 / 32 | 100 | 100 | — | — |
| toolz | 2 | 42 | 6.9 | 100 / 100 | 0 | 100 | 13 | 0 |
| langchain-core | 1 | 139 | 7.2 | 30 / 30 | 100 | 89.8 | 91 | 25 |
| llama-index-core | 0 | 516 | 21.4 | 100 / 100 | 0 | 74.2 | 1,095 | 60 |

How to read each column, plainly:

- **Native ops** — how many of the task's operations the library expresses
  itself. The two speed columns are different experiments: in `ms @28k`,
  everything a library lacks was filled with the *same* hand-written glue,
  so timing differences are the library's; the Recall / Compliance / Useful
  columns are the opposite — each library acts *only* through its own
  operations, so those numbers show what each one ships.
- **Recall %** (strong / weak retrieval signal) — did the record the agent
  actually needed survive into a 1,500-token context? The episodes guarantee
  that record is present in the raw hits, so recall here isolates *shaping*
  loss, not retrieval loss. contexel kept it in 100/100 episodes under both
  signals because `rescore` derives relevance from the records' own text;
  the hand-written row trusts the tool's score and drops to 32% when that
  score is poor.
- **Compliance %** — did the final context actually fit the budget? The rows
  showing 100% recall with 0% compliance (toolz, llama-index) achieved
  recall by emitting 92–129× the budget: a context no window accepts.
- **Useful %** — share of final-context tokens spent on needed fields of
  unique records. langchain-core honors the budget but fills 10% of it with
  duplicates and field bloat it cannot remove; llama-index 26%.
- **ms/episode — contexel is the slowest compliant row, and that is the
  work, not overhead.** Per episode it projects, dedupes, scans ~1 KB of
  evidence per record to compute relevance, clips to a token-accurate cap,
  ranks, and enforces the budget. Every faster row does less: the
  hand-written glue trusts the score (1.6 ms, 32% recall on a weak signal),
  toolz skips the token layer entirely, langchain-core skips the record
  work. The extra milliseconds are the rescore and token-accuracy work
  itself — and every row here is negligible next to a single model call.

The same trade shows in `ms @28k` (the query-free bulk task): contexel's
59 ms includes token-accurate truncation; the 27 ms glue slices at ~4
chars/token and lands looser under the budget. Both are noise next to a
single model call.

**Limits, measured and stated:** recall@budget has a ceiling no shaper
escapes — when a query legitimately describes more records than the budget
holds, some valid record is cut, semantic or not. And `rescore` is lexical:
exact words, not meaning. A query saying *parsing* scores zero against a
document saying *parse*; synonyms and paraphrase are invisible. When you
need that, put a semantic reranker in front — contexel's own suite measures
what the lexical lane cannot reach instead of hiding it
([RESULTS.md](benchmarks/RESULTS.md) also quantifies the default
tokenizer's error: −29% on JSON-heavy records — install
`contexel[accurate]` when budget precision matters).

## Where it is used

contexel sits wherever tool output becomes model context:

1. **Inside agent-written code** (programmatic tool calling / code
   execution): the sandbox imports the stages, so the model composes vetted
   transforms instead of improvising them —
   [`examples/programmatic_tool_calling.py`](examples/programmatic_tool_calling.py)
2. **At the tool boundary**: decorate the tool, the model never sees raw
   output — [`examples/tool_boundary_wrapper.py`](examples/tool_boundary_wrapper.py)
3. **Inside an MCP server**: shape responses before they leave the server —
   [`examples/mcp_server.py`](examples/mcp_server.py)
4. **Under a framework**: a `records ⇄ Document` adapter for LangChain /
   LlamaIndex — [`examples/framework_adapter.py`](examples/framework_adapter.py)
5. **Ahead of a token-efficient encoding**: shape-then-encode with
   [ISON](https://ison.dev) — [`examples/ison_boundary.py`](examples/ison_boundary.py)

And a complete, runnable code-execution agent in
[`reference_agent/`](reference_agent/) (`python -m reference_agent`, no API
key needed) whose tests prove the headline guarantee: two runs build
byte-identical context even though the raw tool output carries fresh
request ids every call.

## How to use it

```bash
pip install contexel              # pure Python, zero dependencies
pip install "contexel[accurate]"  # + tiktoken, for exact token counts
```

From source — also how you get the benchmark suites:

```bash
git clone https://github.com/maheshvaikri-code/contexel && cd contexel
pip install -e ".[benchmarks]"    # everything the benchmark suites use
```

Inline, with the shaping visible and traced:

```python
from contexel import select, dedupe, rescore, truncate_field, rank, trim_to_budget, trace

raw = search_tool(query=user_query)              # a batch of verbose results

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

Or as a named, versioned policy applied at the tool boundary — a *context
contract* the model can't vary:

```python
from contexel import shaped, stage, select, dedupe, trim_to_budget

@shaped([
    stage(select, fields=["path", "line", "snippet"]),
    stage(dedupe, key=["path", "line"]),
    stage(trim_to_budget, max_tokens=2000),
])
def search_code(query: str) -> list[dict]:
    return repo.search(query)     # raw and heavy — shaped identically, every call
```

Token accounting is pluggable on two axes. The *tokenizer*: the default is
a dependency-free ~4-chars/token estimate; `contexel.tokens.use_tiktoken()`
switches to exact counts, `set_tokenizer(fn)` plugs in your own. The
*serializer*: budgets are encoding-relative — a record's cost is the token
count of its serialized text, canonical JSON by default. If your boundary
emits something else (an ISON table, say), `contexel.tokens.set_serializer(fn)`
keeps budgets priced in the encoding that actually enters context.

## Alternatives, and what pairs with it

The tool → context shaping *pattern* is industry consensus; what varies is
the mechanism. The nearest neighbours, so you can pick deliberately:

- **LangChain** `trim_messages` token-trims *chat turns*, not tool records;
  `EmbeddingsRedundantFilter` dedupes semantically — it needs an embedding
  model, and results shift with model versions. **Haystack** `DocumentJoiner`
  and **LlamaIndex** node postprocessors cover similar operations, coupled to
  their frameworks' `Document`/node types. **`context-engineering-toolkit`**
  has been cited as the closest standalone library but was not on PyPI as of
  2026-07.
- **Semantic compressors** (LLMLingua, ColBERT, cross-encoder rerankers)
  understand meaning; contexel is deterministic and lexical by design —
  complementary, not superior. The comparison measures exactly where that
  line sits.
- **The pattern itself** (Anthropic's "code execution with MCP", Cloudflare
  Code Mode) ships as a description, with the shaping left to code the model
  improvises each run — the drift contexel exists to remove.

**Serialization formats are the complementary layer, not competitors**:
contexel decides *what survives*; the encoding decides *what the survivors
cost*. It pairs naturally with [ISON](https://ison.dev) — `select` projects
records onto a uniform field set, exactly the rows ISON's table syntax
encodes without repeating keys (measured in benchmark suite 6), and
`tokens.set_serializer()` keeps budgets priced in that encoding (see
[`examples/ison_boundary.py`](examples/ison_boundary.py)).

Measured, not asserted: [`benchmarks/COMPARISON.md`](benchmarks/COMPARISON.md)
runs the same shaping task through the nearest neighbours on real
CodeSearchNet records (`python -m benchmarks.competitors`), and
[`benchmarks/RESULTS.md`](benchmarks/RESULTS.md) covers contexel's own claims
(`python -m benchmarks` — needs the `accurate` extra; the competitor run
needs the `benchmarks` extra).

## Design

- Every stage is `(records, **params) -> records` over plain `list[dict]`,
  never mutates its input, and is deterministic — no randomness, no wall
  clock, no model calls. That is what lets a pipeline be a *versioned
  contract* rather than a convenience.
- Stages are stateless between calls. contexel pins the *shaping*; it cannot
  make nondeterministic retrieval or a changed repo identical, and it is not
  a memory layer.
- The deterministic stages are free and reproducible. Model-augmented stages
  (semantic reranking, summarization, semantic dedupe) would layer on top
  behind an injected client — deliberately out of scope today.

[![SkillDen](https://skillden.cv/card/maheshvaikri-code.svg?theme=certificate)](https://skillden.cv/u/maheshvaikri-code?theme=certificate)

## License

MIT
