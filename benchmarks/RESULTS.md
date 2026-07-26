# contexel benchmark results

Generated 2026-07-26 by `python -m benchmarks`.

Environment: Python 3.12.7 on Windows (AMD64), single process, wall-clock via `perf_counter`, best of 5 runs. Datasets are seeded and byte-identical across machines (`benchmarks/datasets.py`).

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
| 1,000 | select | 0.23 | 4,321,520.88 |
| 1,000 | hand-written select | 0.22 | 4,640,370.99 |
| 1,000 | dedupe (key) | 1.05 | 956,571.61 |
| 1,000 | rank | 0.14 | 6,983,238.14 |
| 1,000 | truncate_field | 0.91 | 1,098,177.09 |
| 1,000 | trim_to_budget | 3.88 | 258,011.25 |
| 1,000 | full contract | 4.19 | 238,743.26 |
| 10,000 | select | 2.46 | 4,072,324.36 |
| 10,000 | hand-written select | 2.24 | 4,472,672.15 |
| 10,000 | dedupe (key) | 12.48 | 801,243.53 |
| 10,000 | rank | 1.96 | 5,110,906.68 |
| 10,000 | truncate_field | 9.89 | 1,010,979.22 |
| 10,000 | trim_to_budget | 38.39 | 260,504.86 |
| 10,000 | full contract | 44.35 | 225,487.28 |
| 100,000 | select | 33.97 | 2,944,163.93 |
| 100,000 | hand-written select | 33.89 | 2,950,792.59 |
| 100,000 | dedupe (key) | 165.25 | 605,152.51 |
| 100,000 | rank | 30.19 | 3,312,640.38 |
| 100,000 | truncate_field | 113.11 | 884,074.03 |
| 100,000 | trim_to_budget | 393.53 | 254,109.14 |
| 100,000 | full contract | 524.81 | 190,546.86 |

Trace overhead on the full contract over 10,000 records: 49.8 ms inactive vs 173.3 ms active (3.48x). Inactive tracing is the "zero cost" claim; active tracing token-counts every stage boundary and is priced accordingly.

## 4. Default tokenizer accuracy (heuristic vs tiktoken cl100k_base)

Positive error = the heuristic over-estimates (conservative for budgets).

| Sample | Actual | Heuristic | Error % |
|---|---|---|---|
| prose (README.md) | 3,749 | 3,693 | -1.49 |
| prose (the-context-contract.md) | 2,365 | 2,779 | 17.51 |
| code (contexel/stages.py) | 2,640 | 2,667 | 1.02 |
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
