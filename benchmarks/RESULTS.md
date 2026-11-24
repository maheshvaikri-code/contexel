# contexel benchmark results

Generated 2026-11-23 by `python -m benchmarks`. The numbers below are
rendered from `benchmarks/RESULTS.json`; `tools/check_benchmark_numbers.py` fails
when the README or the site disagree with it.

Environment: Python 3.12.7 on Windows (AMD64), contexel 0.1.17, single process, wall-clock via `perf_counter`, best of 5 runs. Datasets are seeded and byte-identical across machines (`benchmarks/datasets.py`).

## What this measures, and deliberately doesn't

contexel's claims are **determinism** (a versioned context contract: the same
shaping on every run), **budget enforcement**, and **zero inference cost** —
not compression magnitude. Per the README ("How much does it cut?") and the
prior-art review, a headline reduction percentage is a property of the data
and the budget, not of the library, so suite 5 *characterizes* reduction
across data profiles instead of advertising one number. Semantic quality
(vs. LLMLingua, ColBERT, cross-encoder rerankers) is explicitly out of scope:
contexel is deterministic and non-semantic by design.

## 1. Determinism (the core claim)

SHA-256 of the shaped output of the standard contract over 5,000 search-hit
records (30% duplicates), hash prefix `6c9fd99fc2f01c4b`:

| Check | Result |
|---|---|
| same process, same input -> identical output | PASS |
| raw inputs differ (fresh request ids / timestamps) | PASS |
| shaped outputs identical despite that noise | PASS |
| 3 fresh interpreters (PYTHONHASHSEED 0/1/2) -> same hash | PASS |

## 2. Budget tightness

`trim_to_budget` shaped with the default heuristic tokenizer vs an exact
tiktoken tokenizer, then measured with tiktoken (`cl100k_base`). "Actual"
is the token cost of the serialized output that would enter context.

| Budget | Shaped with | Records kept | Heuristic tokens | Actual tokens |
|---|---|---|---|---|
| 500 | heuristic | 10 | 479 | 500 |
| 500 | tiktoken | 8 | 514 | 472 |
| 1,000 | heuristic | 20 | 958 | 1,001 |
| 1,000 | tiktoken | 16 | 1,023 | 946 |
| 2,000 | heuristic | 40 | 1,912 | 2,010 |
| 2,000 | tiktoken | 32 | 2,032 | 1,890 |

`truncate_field` with `max_tokens=24` on 120-word snippets — worst clipped
field, measured with the tokenizer that shaped it (docstring claims
"~max_tokens"):

| Shaped with | Cap | Worst field tokens |
|---|---|---|
| heuristic | 24 | 24 |
| tiktoken | 24 | 24 |

## 3. Speed (no model calls, plain Python)

| Records | Stage | ms (best of 5) | Records/sec |
|---|---|---|---|
| 1,000 | select | 0.21 | 4,875,669.26 |
| 1,000 | hand-written select | 0.20 | 4,950,494.44 |
| 1,000 | dedupe (key) | 1.08 | 924,898.29 |
| 1,000 | rank | 0.14 | 7,052,190.38 |
| 1,000 | truncate_field | 0.92 | 1,089,324.61 |
| 1,000 | trim_to_budget | 3.70 | 270,219.15 |
| 1,000 | full contract | 4.09 | 244,588.48 |
| 10,000 | select | 2.08 | 4,806,999.24 |
| 10,000 | hand-written select | 2.12 | 4,725,674.48 |
| 10,000 | dedupe (key) | 12.25 | 816,359.85 |
| 10,000 | rank | 1.73 | 5,792,400.40 |
| 10,000 | truncate_field | 9.50 | 1,053,008.44 |
| 10,000 | trim_to_budget | 36.81 | 271,693.36 |
| 10,000 | full contract | 42.48 | 235,414.32 |
| 100,000 | select | 77.62 | 1,288,292.90 |
| 100,000 | hand-written select | 80.79 | 1,237,784.61 |
| 100,000 | dedupe (key) | 436.85 | 228,909.90 |
| 100,000 | rank | 67.88 | 1,473,161.94 |
| 100,000 | truncate_field | 257.84 | 387,840.28 |
| 100,000 | trim_to_budget | 994.73 | 100,529.35 |
| 100,000 | full contract | 1,356.89 | 73,698.03 |

Trace overhead on the full contract over 10,000 records: 141.2 ms inactive vs 442.0 ms active (3.13x). Inactive tracing is the "zero cost" claim; active tracing token-counts every stage boundary and is priced accordingly.

## 4. Default tokenizer accuracy (heuristic vs tiktoken cl100k_base)

Positive error = the heuristic over-estimates (conservative for budgets).

| Sample | Actual | Heuristic | Error % |
|---|---|---|---|
| prose (frozen README copy) | 10,609 | 10,327 | -2.66 |
| prose (the-context-contract.md) | 2,365 | 2,779 | 17.51 |
| code (contexel/stages.py) | 6,274 | 6,497 | 3.55 |
| code (reference_agent/tools.py) | 1,709 | 1,781 | 4.21 |
| json (500 search-hit records) | 56,877 | 40,606 | -28.61 |

## 5. Reduction characterization (a property of the data, not the library)

Standard contract over 2,000 records with 60-word snippets. Lossless =
`select` + `dedupe` (pure redundancy); by-choice = `truncate_field` +
`trim_to_budget` (budget enforcement you dialed in).

| Dup rate | Budget | Records | Tokens | Lossless % | By-choice % | Total % |
|---|---|---|---|---|---|---|
| 0.00 | 1,000 | 2000 -> 20 | 331,999 -> 952 | 21.69 | 78.02 | 99.71 |
| 0.00 | 4,000 | 2000 -> 80 | 331,999 -> 3,812 | 21.69 | 77.16 | 98.85 |
| 0.25 | 1,000 | 2000 -> 20 | 332,056 -> 956 | 41.08 | 58.63 | 99.71 |
| 0.25 | 4,000 | 2000 -> 80 | 332,056 -> 3,817 | 41.08 | 57.77 | 98.85 |
| 0.50 | 1,000 | 2000 -> 20 | 332,155 -> 957 | 60.45 | 39.26 | 99.71 |
| 0.50 | 4,000 | 2000 -> 80 | 332,155 -> 3,819 | 60.45 | 38.40 | 98.85 |

## 6. Encoding pairing (shape-then-encode)

Budgets are encoding-relative: `trim_to_budget` prices each record by its
serialized text. The same contract and budget, with the boundary priced and
serialized as JSON (contexel's default) vs a minimal ISON table
([ison.dev](https://ison.dev)) via `tokens.set_serializer`. `select` first
projects records onto a uniform field set — exactly the rows ISON's table
syntax encodes without repeating keys. Actual cost measured with tiktoken.

| Encoding | Budget | Records kept | Actual tokens | Tokens/record |
|---|---|---|---|---|
| json | 500 | 10 | 500 | 50.00 |
| ison | 500 | 13 | 442 | 34.00 |
| json | 1,000 | 20 | 1,001 | 50.05 |
| ison | 1,000 | 27 | 908 | 33.63 |
| json | 2,000 | 40 | 2,010 | 50.25 |
| ison | 2,000 | 54 | 1,800 | 33.33 |
