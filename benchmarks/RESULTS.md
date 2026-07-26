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
| 1,000 | select | 0.22 | 4,504,505.64 |
| 1,000 | hand-written select | 0.22 | 4,545,456.01 |
| 1,000 | dedupe (key) | 1.54 | 648,382.29 |
| 1,000 | rank | 0.15 | 6,640,107.01 |
| 1,000 | truncate_field | 2.69 | 372,231.53 |
| 1,000 | trim_to_budget | 3.84 | 260,281.10 |
| 1,000 | full contract | 4.74 | 210,868.14 |
| 10,000 | select | 2.42 | 4,127,967.09 |
| 10,000 | hand-written select | 2.25 | 4,453,549.51 |
| 10,000 | dedupe (key) | 16.78 | 595,944.01 |
| 10,000 | rank | 1.94 | 5,152,779.94 |
| 10,000 | truncate_field | 28.63 | 349,264.45 |
| 10,000 | trim_to_budget | 38.90 | 257,062.14 |
| 10,000 | full contract | 51.71 | 193,404.52 |
| 100,000 | select | 34.40 | 2,906,951.39 |
| 100,000 | hand-written select | 36.21 | 2,761,363.01 |
| 100,000 | dedupe (key) | 182.47 | 548,045.51 |
| 100,000 | rank | 34.78 | 2,874,951.12 |
| 100,000 | truncate_field | 300.48 | 332,805.28 |
| 100,000 | trim_to_budget | 386.19 | 258,938.56 |
| 100,000 | full contract | 517.85 | 193,104.81 |

Trace overhead on the full contract over 10,000 records: 52.3 ms inactive vs 172.1 ms active (3.29x). Inactive tracing is the "zero cost" claim; active tracing token-counts every stage boundary and is priced accordingly.

## 4. Default tokenizer accuracy (heuristic vs tiktoken cl100k_base)

Positive error = the heuristic over-estimates (conservative for budgets).

| Sample | Actual | Heuristic | Error % |
|---|---|---|---|
| prose (README.md) | 1,674 | 1,636 | -2.27 |
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
