<p align="center">
  <img src="https://raw.githubusercontent.com/maheshvaikri-code/contexel/main/logo/contexel_logo.png" width="340" alt="contexel logo">
</p>

**The context element.** Deterministic, dependency-free context shaping for
code-writing agents — the same transform, every run.

## Why this exists

An agent's tools return big lists of records: search hits, file reads, API
responses. Before they reach the model's context window they must be cut
down — and today that cutting is often code the model writes per task, which
can **drift** each time it is rewritten: different field choices, different
truncation, different survivors (a premise, not something the benchmark
measures). contexel replaces that code with
vetted, versioned stages at the tool → context boundary. Same input,
byte-identical context, on every run — a *context contract* instead of a
nightly rewrite.

## What you get

Eight deterministic pipeline stages plus a `merge` combiner, over plain
`list[dict]` — the shape tools already return — with composition and
observability:

- `select` — project to the fields you need (lossless)
- `dedupe` — drop duplicates by key, type-qualified, order preserved (lossless)
- `allowlist` — provenance gate: refuse records from unapproved sources
  (fail closed; the strong injection control)
- `quarantine` — tripwire for literal injection markers; drop or flag
  (paraphrase passes — not a security boundary)
- `rescore` — BM25-style lexical relevance derived from the records' own
  text, so ranking doesn't have to trust the tool's score
- `rank` — stable sort, missing-field records last
- `truncate_field` — clip a text field to a token cap, never exceeding it
- `trim_to_budget` — keep the top records that fit a token budget
- `merge` — unify differently-shaped tool outputs into one schema
- `pipeline([...])` / `@shaped` / `trace()` — compose (each pipeline
  carries a stable policy fingerprint), pin at the tool boundary (async
  tools are awaited, then shaped), and inspect what every stage removed —
  `trace(id_field=...)` + `t.audit()` record exactly which records were
  dropped, per stage

Token counting is pluggable twice over: the *tokenizer* (a dependency-free
estimate by default; `tokens.use_tiktoken()` for exact) and the
*serializer* (budgets are priced in the encoding your boundary actually
emits — JSON by default, or e.g. an [ISON](https://ison.dev) table).
(ISON is by the same author as contexel.)

No embeddings, no model calls, **zero dependencies** — pure Python 3.9+.

## Install

```bash
pip install contexel              # pure Python, zero dependencies
pip install "contexel[accurate]"  # + tiktoken, for exact token counts
```

Building agents in TypeScript/JavaScript or C#/.NET instead?
`npm install contexel` and `dotnet add package Contexel` ship the same
stages with golden-vector-enforced parity to this package
([details](https://github.com/maheshvaikri-code/contexel#language-parity)).

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

## What the benchmark measures

Benchmarked on the full CodeSearchNet python/test split (22,176 real
functions → 28,047 search-tool records, made by simulated, overlapping
substring searches over those functions) with 100 ground-truth episodes: one
corpus and one task, so read it as a measurement, not a law. This benchmark
was written by contexel's author. The comparison wirings are our best effort,
one dataset, 100 episodes; corrections from the maintainers of the compared
libraries are welcome ([open an issue](https://github.com/maheshvaikri-code/contexel/issues)).

The task is defined as contexel's own six stages: contexel performs all six
operations itself, and in the wirings this benchmark chose no other compared
row does (hand-written glue, the hand-written term-overlap baseline, toolz,
langchain-core, llama-index-core); which library functions each row uses is
the author's choice, and other wirings exist. Every budget is counted with
contexel's default estimator (about four characters per token, the same one
the hand-written glue uses): `trim_to_budget` keeps every contexel context
within the 1,500-token budget as that estimator counts it, and measured with
an exact tokenizer most of these contexts run over it. Over the episodes,
contexel keeps the needed record in 100% of them under both a strong and a
weak retrieval signal (equal by construction: the two signals differ only in
the score, which `rescore` replaces, and the hits arrive in the same order
under both), and spends 100% of context tokens on unique, needed fields (by
construction for any row that projects to contexel's fields and dedupes on
its key) — at 0 dependencies and an import of about 20 ms (the import
statement alone in a fresh interpreter, median of 5, interpreter start-up
excluded; it varies with the machine's load). The term-overlap
baseline (a hand-written scorer in place of `rescore`) reaches
97% recall, so on these episodes the margin over it is small, and that margin
comes from `rescore`'s in-order proximity bonus: the episode queries keep the
target's word order, which that bonus rewards, and with the bonus switched
off contexel's recall on these episodes is not above the baseline's (this
benchmark does not generate that row). It and contexel are the two slowest
budget-compliant rows (every context within the budget as the estimator
counts it), in an order that can change from run to run; they are the two
rows that score each record from the query. The limits are stated with the
same care: recall@budget is bounded
by query specificity for any shaper, and `rescore` is lexical, not semantic.
On a second set of episodes, built only from terms the frozen stemmer maps to
one stem, the default exact-word matching finds the record in 99% of those
episodes with the target's own words and in 35% with inflections of those
words (synthetic inflections from a three-line rule, some of them words nobody
writes), while `match="stem"` finds it in 98% with the inflections, recovering
them. That shows the stem match carrying through ranking and the budget, not
how many English inflections the stemmer covers; synonyms stay invisible.

Determinism is tested, not just promised: the suite hashes the same contract's
output across fresh interpreters with different `PYTHONHASHSEED` values —
same SHA-256 every time, even when raw tool output carries fresh request
ids.

Two limits, stated plainly: hard token limits require an exact tokenizer
(`contexel[accurate]`, exact where tiktoken covers the model — other
providers plug their own counter via `set_tokenizer`; the built-in estimate
is for soft budgeting only),
and **shaping is not an injection defense** — `rescore` ranks textual
relevance. contexel ships `allowlist` (provenance gate) and `quarantine`
(pattern tripwire) as deterministic boundary controls, but content
authentication still belongs upstream. Treat every shaped record as
untrusted data, never as instructions.

Full method and tables:
[benchmarks/COMPARISON.md](https://github.com/maheshvaikri-code/contexel/blob/main/benchmarks/COMPARISON.md)
·
[benchmarks/RESULTS.md](https://github.com/maheshvaikri-code/contexel/blob/main/benchmarks/RESULTS.md).
To reproduce the comparison from a source checkout with the library versions
that were measured, install with
`pip install -e ".[benchmarks]" -c benchmarks/constraints.txt` and run
`python -m benchmarks.competitors`.

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
- **TypeScript package:** https://www.npmjs.com/package/contexel
- **C# package:** https://www.nuget.org/packages/Contexel
- **Changelog:** https://github.com/maheshvaikri-code/contexel/blob/main/CHANGELOG.md
- **License:** MIT
