# contexel vs prior art — comparative benchmark

Generated 2026-11-23 by `python -m benchmarks.competitors`. The numbers
below are rendered from `benchmarks/COMPARISON.json`; `tools/check_benchmark_numbers.py`
fails when the README or the site disagree with it.

Environment: Python 3.12.7 on Windows (AMD64),
contexel 0.1.17; toolz 1.1.0,
langchain-core 1.4.9, llama-index-core
0.14.23.

**Dataset (public):** [CodeSearchNet](https://huggingface.co/datasets/code-search-net/code_search_net)
python/test split in full (22,176 rows) via the Hugging Face parquet export
(`benchmarks/fetch_dataset.py`, which verifies the committed SHA-256
`05049f798a197a8a80844707abe8b1319bf5c39d37a22fab303aba7625b868e5` before anything is read). Tool output is reconstructed the way an
agent session produces it: 16 overlapping substring queries over the
corpus, hit lists capped at 2000/query -> 28,047
records whose duplicates are real (the same function matching several
queries).

**Canonical task:** project 5 fields, dedupe by (path, symbol),
clip `snippet` to ~24 tokens, rank by score, fit a 2,000-token
budget.

**Fairness:** every implementation missing a native stage uses the *same*
hand-written glue helpers; the hand-written rows are the model-improvised
baseline contexel replaces (one trusting the tool's score, one with its own
term-overlap scorer). Semantic tools are matrix-only — contexel concedes
semantic quality by design.

## At a glance — all the benchmarks clubbed

One row per implementation, joining the tables below: **native operations**
(how many of the outcome task's six operations — select, dedupe, rescore,
truncate, rank, trim — the library expresses itself, computed from the code that
defines each implementation: see "Operations" below), **speed** on the
28,047-record canonical task, the ground-truth **outcome** metrics (recall under a
strong / weak retrieval signal; *compliance* = % of episodes whose final context
fit the 1,500-token budget; *fill* = mean context tokens / budget), and
**footprint**.

| Implementation | Native ops | ms @28k | ms/episode | Recall % s/w | Compliance % | Fill x | Useful % | Import ms | Deps |
|---|---|---|---|---|---|---|---|---|---|
| contexel | 6/6 (select, dedupe, rescore, truncate, rank, trim) | 73.68 | 39.56 | 100 / 100 | 100.00 | 0.95 | 100.00 | 19.88 | 0 |
| hand-written | 0/6 | 28.05 | 3.01 | 93 / 32 | 100.00 | 0.95 | 100.00 | - | - |
| hand-written (term overlap) | 0/6 | - | 28.97 | 97 / 97 | 100.00 | 0.94 | 100.00 | - | - |
| toolz | 2/6 (select, dedupe) | 44.22 | 13.97 | 100 / 100 | 0.00 | 91.62 | 100.00 | 12.82 | 0 |
| langchain-core | 1/6 (trim) | 230.96 | 15.52 | 30 / 30 | 100.00 | 0.52 | 89.75 | 90.58 | 25 |
| llama-index-core | 0/6 | 508.64 | 42.34 | 100 / 100 | 0.00 | 129.21 | 74.15 | 1,226.80 | 60 |

Recall columns come from the ground-truth outcome benchmark, where contexel's
standard contract includes `rescore` (relevance derived from the query, not
trusted from the tool); `ms @28k` is the query-free canonical task, which has no
rescore stage ("-" where a row has no timed task).

- Rows that keep the needed record under both retrieval signals, respect the
  budget in every episode and spend no tokens on duplicates or bloat:
  contexel.
- `ms/episode`: contexel is the slowest budget-compliant row (39.6 ms). contexel does the most per episode (projecting,
  deduping, scanning each record's own text to derive relevance, clipping to a
  token-accurate cap, ranking, enforcing the budget); a cheaper row is cheaper
  by doing less.
- These timings are from one run on one machine ("best of 5" within the run
  where a column says so): they are published as measured, and they vary with
  the machine's load and from run to run. The recall, compliance, fill and
  useful-share columns do not vary.

## Operations: native versus hand-written (computed)

Each implementation is an ordered list of steps (`benchmarks/competitors.py`).
A step is **native** when running it enters a Python function of the library's own
package, **glue** when it is hand-written code in this benchmark, and an
**adapter** when it only converts the operand to the shape the library requires.
`benchmarks/opcount.py` reads the counts from those definitions by running each
step over a small fixed sample; nothing about "native" is typed.

| Implementation | Native operations | Done by hand-written glue | Not done at all | Other native steps | Operand conversion | Operand |
|---|---|---|---|---|---|---|
| contexel | 6/6 (select, dedupe, rescore, truncate, rank, trim) | - | - | - | - | list[dict] |
| hand-written | 0/6 | select, dedupe, truncate, rank, trim | rescore | - | - | list[dict] |
| hand-written (term overlap) | 0/6 | select, dedupe, rescore, truncate, rank, trim | - | - | - | list[dict] |
| toolz | 2/6 (select, dedupe) | - | rescore, truncate, rank, trim | - | - | any dicts |
| langchain-core | 1/6 (trim) | - | select, dedupe, rescore, truncate, rank | - | wrap as messages | BaseMessage |
| llama-index-core | 0/6 | - | select, dedupe, rescore, truncate, rank, trim | score cutoff, long-context reorder | to nodes, from nodes | NodeWithScore |

Libraries this benchmark does not run (what their documentation says; they are
not counted above):

| Library | select | dedupe(key) | rescore(lexical) | rank | truncate(tok) | trim(budget) | merge(schema) | Operand | Status |
|---|---|---|---|---|---|---|---|---|---|
| haystack-ai (DocumentJoiner) | no | by doc id | no (rank fusion) | join/RRF | no | no | no (uniform Document) | Document | not run: pre-existing haystack/farm-haystack conflict in env |
| langchain EmbeddingsRedundantFilter | no | semantic | no | no | no | no | no | Document | not run: needs embedding model; model/version-dependent |
| LLMLingua / ColBERT / rerankers | no | no | semantic | semantic | semantic | semantic | no | text | out of scope by design (contexel concedes semantic quality) |
| context-engineering-toolkit | - | - | - | - | - | - | - | - | NOT FOUND on PyPI — prior-art claim did not verify |

## Canonical task on real records

| Implementation | Native stages (of 5) | ms (best of 5) | Records kept | Tokens out | Deterministic |
|---|---|---|---|---|---|
| contexel | 5/5 | 73.68 | 36 | 1,909 | yes |
| hand-written | 0/5 | 28.05 | 36 | 1,924 | yes |
| toolz | 2/5 | 44.22 | 36 | 1,924 | yes |
| langchain-core | 1/5 | 230.96 | 36 | 1,924 | yes |
| llama-index-core | 0/5 | 508.64 | 36 | 1,924 | yes |

## What each achieves natively (ground-truth outcome benchmark)

The tables above hold the *policy* constant and let glue fill the gaps. This
one asks the question that matters — **was the output useful?** — and lets
each library act only through its own operations. 100 episodes with
known ground truth: a target function, plus the hit list a
multi-term docstring search over the full corpus returns (the target is
always present in the raw hits, so every miss below is a *shaping* loss, not
a retrieval loss). Budget: 1,500 tokens. The queries are the target's
own words; the next section changes that.

Every hit carries two retrieval scores, because outcome quality depends on
the ranking signal the search tool hands the shaper: **strong** ranks
matching all the query's terms above matching one term often (the shape a
real multi-term search returns); **weak** is a raw substring count, which
buries the target under term-happy decoys.

- **Recall@budget** — the record the agent actually needed survived into the
  final context, under each signal.
- **Compliance** — episodes where the context fits the budget; **Fill** —
  mean context tokens / budget (over 1.00 = blown).
- **Useful share** — fraction of context tokens spent on needed fields of
  first-occurrence records (the rest is duplicates and field bloat).

| Implementation | Recall % (strong) | Recall % (weak) | Compliance % | Fill x | Useful share % | ms/episode |
|---|---|---|---|---|---|---|
| contexel | 100.00 | 100.00 | 100.00 | 0.95 | 100.00 | 39.56 |
| hand-written | 93.00 | 32.00 | 100.00 | 0.95 | 100.00 | 3.01 |
| hand-written (term overlap) | 97.00 | 97.00 | 100.00 | 0.94 | 100.00 | 28.97 |
| toolz | 100.00 | 100.00 | 0.00 | 91.62 | 100.00 | 13.97 |
| langchain-core | 30.00 | 30.00 | 100.00 | 0.52 | 89.75 | 15.52 |
| llama-index-core | 100.00 | 100.00 | 0.00 | 129.21 | 74.15 | 42.34 |

What the numbers say each is best at:

- **contexel** (select, dedupe, `rescore`, truncate, rank, trim): recall
  100% / 100%, compliance
  100%, useful share 100%. Its two recall columns are identical because `rescore` derives relevance from the query and the records' own fields (batch BM25: exact word tokens, IDF x saturating tf, in-order proximity), so the tool's score quality does not matter.
- **hand-written** is the same pipeline as improvised code writes it: it trusts
  the tool's score, so its recall tracks that score's quality
  (93% / 32%), and it gets
  re-derived, slightly differently, every run.
- **hand-written (term overlap)** adds the scorer such code would improvise:
  recall 97% / 97% (the two columns agree because it, too, ignores the tool's score).
  This is contexel's fairest comparison for `rescore`: another rescorer, not none.
- Recall@budget has a ceiling no shaper escapes, semantic or not: when a
  query legitimately describes more records than the budget can hold, some
  valid record is cut. Any recall short of 100% below is that ambiguity,
  now measured — not a scoring defect.
- **toolz** performs 2 of the six operations
  (select, dedupe); no step performs rescore, truncate, rank, trim,
  so the "context" blows the budget by the fill factor shown (91.6x).
  Best at: fast lossless projection/dedup when something else enforces budgets.
- **langchain-core** is best at what it actually ships: budget enforcement
  over message streams (trim). With no record-level
  projection or dedupe, the budget fills with bloat and duplicates (useful share
  89.7%), and whether the target makes the cut depends entirely
  on incoming order (recall 30%).
- **llama-index-core**'s postprocessors (score cutoff 2.0,
  lost-in-middle reorder) are built for reordering retrieved RAG nodes, not
  bounding them — they serve none of the six operations, so recall
  (100%) comes from keeping nearly everything, at a fill
  factor of 129.2x that no context window accepts.

## Inflected-query episodes (inflection robustness, not semantic paraphrase)

The episodes above query with the target's own words, so exact-word matching
is never tested: a query saying "parse" always meets a document saying "parse".
These 100 episodes keep the same kind of hit lists (the
retrieval tool searched with the target's original terms) but hand the shaper a
deterministic **inflection** of each term (`partial` -> `partialing`, `bounds` -> `bound`, `none` -> `noning`, `simple` -> `simpling`, `extractor` -> `extractoring`, `anchor` -> `anchoring`). An exact-word
shaper fails on them by construction; a stem-matching one is *measured*, not
assumed. The rule (`benchmarks/inflection.py`) is three lines, and a term is
used only when it is a plain lower-case word, its inflection differs from it,
the frozen stemmer maps both to one stem, and the inflection is not a word of
the target's own text. The inflections are synthetic — some are words nobody
writes — so this measures what the stemmer reaches on inflection and nothing
else: **not synonyms, not paraphrase, not meaning.**

| Shaper | Recall % (original terms) | Recall % (inflected terms) |
|---|---|---|
| contexel | 99.00 | 35.00 |
| contexel (match=stem) | 98.00 | 98.00 |
| hand-written (term overlap) | 96.00 | 35.00 |
| hand-written | 90.00 | 90.00 |

- `rescore(match="word")` (the default): 99% with the
  original terms, 35% with the inflected ones.
- `rescore(match="stem")`: 98% with the original terms,
  98% with the inflected ones. Opting in to the stemmer costs 1 point on the original terms.
- The hand-written term-overlap scorer matches whole words too:
  96% with the original terms,
  35% with the inflected ones.
- The hand-written baseline that trusts the tool's score never reads the query,
  so inflection cannot touch it: 90% and
  90% (it is the control).

## Footprint

Import time is a fresh interpreter importing only the library; transitive
deps counts installed distributions the package requires (recursive).

| Library | Import ms | Transitive deps |
|---|---|---|
| contexel | 19.88 | 0 |
| toolz | 12.82 | 0 |
| langchain-core | 90.58 | 25 |
| llama-index-core | 1,226.80 | 60 |

## Reading the results

- No library in the timed set expresses more than 2 of the 5 stages natively on tool-output records; contexel is the only 5/5. That gap — not
  raw speed — is the claim this comparison tests.
- contexel is slower than the hand-written glue on this task, and that is the
  honest price of accuracy: `truncate_field` binary-searches to a true token
  cap where the glue slices at 4 chars/token, which is why contexel's output
  lands tighter under budget. All rows are microseconds per record —
  negligible next to a single model call.
- All timed implementations are deterministic on this task: mechanical shaping is reproducible whoever provides it.
  The nondeterminism contexel removes lives in the *hand-written baseline
  being re-improvised per run* (and in the semantic alternatives), not in these
  libraries' primitives.
- `context-engineering-toolkit`, cited by the prior-art review as the closest
  standalone competitor, could not be found on PyPI at benchmark time.
