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
| 1,000 | select | 0.21 | 4,655,493.36 |
| 1,000 | hand-written select | 0.21 | 4,672,897.20 |
| 1,000 | dedupe (key) | 1.58 | 634,517.76 |
| 1,000 | rank | 0.15 | 6,816,634.77 |
| 1,000 | truncate_field | 2.67 | 374,953.14 |
| 1,000 | trim_to_budget | 3.64 | 274,876.31 |
| 1,000 | full contract | 4.59 | 217,651.54 |
| 10,000 | select | 2.28 | 4,380,393.29 |
| 10,000 | hand-written select | 2.22 | 4,510,193.03 |
| 10,000 | dedupe (key) | 16.16 | 618,727.65 |
| 10,000 | rank | 1.88 | 5,333,333.12 |
| 10,000 | truncate_field | 27.32 | 366,004.08 |
| 10,000 | trim_to_budget | 37.93 | 263,672.06 |
| 10,000 | full contract | 48.64 | 205,573.09 |
| 100,000 | select | 32.95 | 3,034,532.98 |
| 100,000 | hand-written select | 32.73 | 3,055,440.98 |
| 100,000 | dedupe (key) | 175.46 | 569,922.02 |
| 100,000 | rank | 30.10 | 3,322,744.85 |
| 100,000 | truncate_field | 299.91 | 333,437.37 |
| 100,000 | trim_to_budget | 389.89 | 256,485.62 |
| 100,000 | full contract | 523.65 | 190,967.87 |

Trace overhead on the full contract over 10,000 records: 52.2 ms inactive vs 173.9 ms active (3.33x). Inactive tracing is the "zero cost" claim; active tracing token-counts every stage boundary and is priced accordingly.

## 4. Default tokenizer accuracy (heuristic vs tiktoken cl100k_base)

Positive error = the heuristic over-estimates (conservative for budgets).

| Sample | Actual | Heuristic | Error % |
|---|---|---|---|
| prose (README.md) | 2,177 | 2,169 | -0.37 |
| prose (the-context-contract.md) | 2,365 | 2,779 | 17.51 |
| code (contexel/stages.py) | 1,328 | 1,390 | 4.67 |
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
