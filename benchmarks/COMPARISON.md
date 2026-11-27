# contexel vs prior art — comparative benchmark

Generated 2026-11-24 by `python -m benchmarks.competitors`. The numbers
below are rendered from `benchmarks/COMPARISON.json`; `tools/check_benchmark_numbers.py`
fails when the README or the site disagree with it.

This benchmark was written by contexel's author. The comparison wirings are our
best effort, one dataset, 100 episodes; corrections from the maintainers of the
compared libraries are welcome ([open an issue](https://github.com/maheshvaikri-code/contexel/issues)).

Environment: Python 3.12.7 on Windows (AMD64),
contexel 0.1.17; toolz 1.1.0,
langchain-core 1.4.9, llama-index-core
0.14.23. The `benchmarks` extra does not pin
these versions; to install the ones measured here, add the constraints file:
`pip install -e ".[benchmarks]" -c benchmarks/constraints.txt`.

**Dataset (public):** [CodeSearchNet](https://huggingface.co/datasets/code-search-net/code_search_net)
python/test split in full (22,176 rows) via the Hugging Face parquet export
(`benchmarks/fetch_dataset.py`, which verifies the committed SHA-256
`05049f798a197a8a80844707abe8b1319bf5c39d37a22fab303aba7625b868e5` before anything is read). The functions are real; the tool calls
are simulated: 16 fixed, overlapping substring searches over the corpus, hit
lists capped at 2000/query -> 28,047 records. Almost all of
the duplicates are the same function matched by several searches; a few are different
functions from different repositories that share a path and a symbol.

**Canonical task:** project 5 fields, dedupe by (path, symbol),
clip `snippet` to ~24 tokens, rank by score, fit a 2,000-token
budget.

**Tokens:** every budget, cap and price in this benchmark, and the Fill and Useful
columns, are counted with contexel's default estimator (about four characters per
token), the same one the hand-written glue uses. The estimator is for soft budgeting: a
hard limit needs an exact tokenizer (`contexel[accurate]` and `tokens.use_tiktoken()`,
or the provider's own counter). Measured with an exact tokenizer, most of the contexts
that fill the budget here run over the estimated budget.

**Fairness, and its limits:** in the timed canonical task every implementation missing
a native stage uses the *same* hand-written glue helpers. The hand-written rows stand in
for shaping code written per task (one trusting the tool's score, one with its own
term-overlap scorer). The task is contexel's own six stages and it is scored with
contexel's estimator, field list and dedupe key, so it measures how much of that task
each library covers in these wirings, not how good each library is at its own job.
Semantic tools are not run (what their documentation offers is listed under
"Operations"): contexel concedes semantic quality by design.

## At a glance — all the benchmarks clubbed

One row per implementation, joining the tables below: **native operations**
(how many of the outcome task's six operations — select, dedupe, rescore,
truncate, rank, trim — the library performed itself in the wiring this benchmark
chose: see "Operations" below), **speed** on the
28,047-record canonical task, the ground-truth **outcome** metrics (recall under a
strong / weak retrieval signal; *fill* = mean estimated context tokens ÷ the
1,500-token budget, over 1.00 when the contexts run over it; *useful* =
share of context tokens on needed fields of unique records), and **footprint**
(import time; transitive deps = the installed dependency closure, no extras).

| Implementation | Native ops (in this wiring) | ms @28k | ms/episode | Recall % s/w | Fill × (estimated tokens ÷ budget) | Useful % | Import ms | Transitive deps |
|---|---|---|---|---|---|---|---|---|
| contexel | 6/6 (select, dedupe, rescore, truncate, rank, trim) | 67.41 | 37.60 | 100 / 100 | 0.95 | 100.00 | 20.97 | 0 |
| hand-written | 0/6 | 19.64 | 3.06 | 93 / 32 | 0.95 | 100.00 | - | - |
| hand-written (term overlap) | 0/6 | - | 33.93 | 97 / 97 | 0.94 | 100.00 | - | - |
| toolz | 2/6 (select, dedupe) | 37.85 | 14.16 | 100 / 100 | 91.62 | 100.00 | 12.09 | 0 |
| langchain-core | 1/6 (trim) | 395.77 | 17.93 | 30 / 30 | 0.52 | 89.75 | 87.92 | 25 |
| llama-index-core | 0/6 | 463.76 | 49.57 | 100 / 100 | 129.21 | 74.15 | 1,155.93 | 60 |

Recall columns come from the ground-truth outcome benchmark, where contexel's
standard contract includes `rescore` (relevance derived from the query, not
trusted from the tool); `ms @28k` is the query-free canonical task, which has no
rescore stage ("-" where a row has no timed task).

- On this task, defined by contexel's six stages and scored with contexel's
  estimator, field list and dedupe key, the rows that keep the needed record under
  both retrieval signals, stay within the budget on average (Fill at most 1.00) and
  spend no tokens on duplicates or bloat: contexel.
- `ms/episode` is the mean wall time per episode of the shaping plus the benchmark's
  own scoring of the result (one pass), so a row whose contexts are very large also
  pays for scoring them: contexel is the slowest of the rows whose every context fits the budget as the estimator counts it (37.6 ms). contexel does the most per episode (projecting
  fields, deduping on a key, deriving relevance from each record's own text with
  batch IDF, saturating term frequency and in-order proximity, clipping, ranking,
  enforcing the budget stage by stage); a cheaper row is cheaper by doing less.
  Every cap and price is computed with the active tokenizer, here the default
  estimate of ~4 characters per token, the same estimate the hand-written glue
  uses.
- These timings are from one run on one machine ("best of 5" within the run
  where a column says so, and the import time is the median of
  5 fresh interpreters): they are published as measured, and they vary with
  the machine's load and from run to run. The recall, fill and useful-share columns
  do not vary.

## Operations: native versus hand-written, in the wiring this benchmark chose

Each implementation is an ordered list of steps (`benchmarks/competitors.py`).
A step is **native** when running it enters a Python function of the library's own
package, **glue** when it is hand-written code in this benchmark, and an
**adapter** when it only converts the operand to the shape the library requires.
Whether a step enters library code is detected automatically (`benchmarks/opcount.py`
runs each step over a small fixed sample); which library functions each implementation
uses, and which operation each step serves, are the benchmark author's choices. The
counts therefore describe these wirings, not what each library can do. Other wirings
exist and are not counted here: toolz's `topk` and `accumulate` can express a rank and a
running budget cut, and llama-index-core has metadata exclusion
(`excluded_llm_metadata_keys`), ingestion dedupe (`IngestionPipeline` with a docstore)
and a token-limited `ChatMemoryBuffer`.

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
| haystack-ai (DocumentJoiner, MetaFieldRanker, LostInTheMiddleRanker) | no | by document id (DocumentJoiner) | no | by a meta field (MetaFieldRanker); rank fusion (DocumentJoiner) | no | word-count budget (LostInTheMiddleRanker; keeps the document that crosses it) | no (uniform Document) | Document | not run in this benchmark |
| langchain-community EmbeddingsRedundantFilter | no | by embedding similarity | no | no | no | no | no | Document | not run: needs an embedding model; results depend on the model and the threshold |
| LLMLingua | no | no | no | no | removes tokens a small language model scores as non-essential | compresses to `target_token` or `rate` | no | text | not run: out of scope by design (contexel is lexical and deterministic) |
| ColBERT, cross-encoder rerankers | no | no | no (learned relevance) | by learned relevance, top-k | no | no token budget | no | query and passages | not run: out of scope by design (contexel is lexical and deterministic) |
| context-engineering-toolkit | - | - | - | - | - | - | - | - | not on PyPI as of 2026-11-26 (`pip index versions context-engineering-toolkit`) |

## Canonical task on real records

| Implementation | Native stages (of 5, in this wiring) | ms (best of 5) | Records kept | Tokens out | Deterministic |
|---|---|---|---|---|---|
| contexel | 5/5 | 67.41 | 36 | 1,909 | yes |
| hand-written | 0/5 | 19.64 | 36 | 1,924 | yes |
| toolz | 2/5 | 37.85 | 36 | 1,924 | yes |
| langchain-core | 1/5 | 395.77 | 36 | 1,924 | yes |
| llama-index-core | 0/5 | 463.76 | 36 | 1,924 | yes |

For langchain-core and llama-index-core most of this time is converting the records to
the library's message or node type (and, for llama-index-core, back): in llama-index-core's
row the only llama-index code that runs is building and unbuilding its node objects, and
langchain-core's one native step is `trim_messages`.

## What each achieves natively (ground-truth outcome benchmark)

The tables above hold the *policy* constant and let glue fill the gaps. This
one asks **was the output useful?** and lets each library act only through the
operations this benchmark wired for it (listed above): a different wiring can change
these rows, and they do not rate the libraries at their own jobs. 100 episodes with
known ground truth: a target function, plus the hit list a
multi-term docstring search over the full corpus returns (the target is
always present in the raw hits, so every miss below is a *shaping* loss, not
a retrieval loss). Budget: 1,500 tokens, as the default estimator counts
them. The queries are the target's own words: up to the first three words of at least
five characters in its docstring, in their order. The next section changes the words.

Every hit carries two retrieval scores, because outcome quality depends on
the ranking signal the search tool hands the shaper: **strong** ranks
matching all the query's terms above matching one term often (the shape a
real multi-term search returns); **weak** is a raw substring count, which
buries the target under term-happy decoys. The two signals differ only in the score
value: the hit lists arrive in the same order under both (per search term, by the weak
count), so a row that never reads the score has identical columns by construction.

- **Recall@budget** — the record the agent actually needed survived into the
  final context, under each signal.
- **Fill** — mean estimated context tokens ÷ budget (over 1.00 = the contexts
  run over the budget).
- **Useful share** — fraction of context tokens spent on needed fields of
  first-occurrence records (the rest is duplicates and field bloat). The needed fields
  and the dedupe key are contexel's, so a row that projects to those fields and dedupes
  on that key scores 100% by construction. A context that is empty counts as fully
  useful by the current scoring; langchain-core returns one when its first record alone
  exceeds the budget.

| Implementation | Recall % (strong) | Recall % (weak) | Fill × (estimated tokens ÷ budget) | Useful share % | ms/episode |
|---|---|---|---|---|---|
| contexel | 100.00 | 100.00 | 0.95 | 100.00 | 37.60 |
| hand-written | 93.00 | 32.00 | 0.95 | 100.00 | 3.06 |
| hand-written (term overlap) | 97.00 | 97.00 | 0.94 | 100.00 | 33.93 |
| toolz | 100.00 | 100.00 | 91.62 | 100.00 | 14.16 |
| langchain-core | 30.00 | 30.00 | 0.52 | 89.75 | 17.93 |
| llama-index-core | 100.00 | 100.00 | 129.21 | 74.15 | 49.57 |

What the numbers say, row by row:

- **contexel** (select, dedupe, `rescore`, truncate, rank, trim): recall
  100% / 100%, fill
  0.95, useful share 100%. Its two recall columns are identical by construction: `rescore` replaces the tool's score with relevance derived from the query and the records' own fields (batch BM25: exact word tokens, IDF x saturating tf, in-order proximity), and the two signals differ only in that score. This shows that `rescore` does not depend on the tool's score; any row that ignores the score has equal columns.
- **hand-written** is the same pipeline written by hand: it trusts
  the tool's score, so its recall tracks that score's quality
  (93% / 32%). It stands in for
  shaping code a model writes per task; when such code is rewritten, its field choices
  and truncation can differ (a claim, not measured here).
- **hand-written (term overlap)** adds a scorer such code might write:
  recall 97% / 97% (the two columns agree because it, too, ignores the tool's score).
  This is contexel's fairest comparison for `rescore` (another rescorer, not none), with
  one caveat: contexel's lead over it comes from `rescore`'s in-order proximity bonus.
  The episode queries keep the target's word order, which that bonus rewards, and with
  the bonus switched off contexel's recall on these episodes is not above the
  term-overlap baseline's (this benchmark does not generate that row).
- Recall@budget has a ceiling no shaper escapes, semantic or not: when a
  query legitimately describes more records than the budget can hold, some
  valid record is cut. Where contexel's recall in these tables falls short
  of 100%, that is most likely this ambiguity (not analysed per episode).
- **toolz** performs 2 of the six operations
  (select, dedupe) in this wiring; no step here performs
  rescore, truncate, rank, trim, so the context runs over the budget by the fill factor
  shown (91.6x). toolz has no token concept, but its `topk` and
  `accumulate` can express a rank and a budget cut (not wired here). In this wiring it
  does fast lossless projection and dedupe and leaves the budget to something else.
- **langchain-core** in this wiring: `trim_messages` (trim)
  over the raw records wrapped as messages. `trim_messages` trims a message list to a
  token count; it does not see the records inside a message, and no langchain-core step
  in this wiring projects or dedupes them, so the budget fills with field bloat and
  duplicates that its own operations here do not remove (useful share
  89.7%). It never reads the score, so whether the target makes the cut
  depends on the incoming order, the same weak per-term order under both signals (recall
  30%).
- **llama-index-core** offers related operations on its node types: a score cutoff
  (`SimilarityPostprocessor`), a score-ordered reorder (`LongContextReorder`), rerankers
  with `top_n`, metadata exclusion, docstore dedupe, `PromptHelper` truncation to the
  context window and a `ChatMemoryBuffer` token limit. This benchmark wires two of them
  (the score cutoff and the reorder) and counts neither as one of the six stages.
  The cutoff (2.0) removes nothing under the strong signal, where every score is at least 11; under the weak signal it drops the hits whose raw count is below it. No budget step is wired, so recall
  (100%) comes from keeping nearly everything, at a fill
  factor of 129.2x; llama-index-core's response synthesizers fit text to the
  context window with `PromptHelper`, which this wiring does not use.

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

Import time is the median of 5 fresh interpreters, each importing
only the library's top-level package (interpreter start-up excluded; the modules a
task uses can cost more, and the time varies with the machine's load). Transitive
deps counts the installed distributions the package requires, recursively: the
installed closure, with environment markers evaluated for this machine and no extras.

| Library | Import ms | Transitive deps |
|---|---|---|
| contexel | 20.97 | 0 |
| toolz | 12.09 | 0 |
| langchain-core | 87.92 | 25 |
| llama-index-core | 1,155.93 | 60 |

## Reading the results

- In the wirings used here, no library in the timed set performs more than 2 of the 5 stages natively on tool-output records; contexel is the only 5/5 (its stages define the task). That
  coverage of this task, not raw speed, is what this comparison tests.
- contexel is slower than the hand-written glue on this task. Its time includes
  the checks each stage runs on its input and the pipeline's plumbing (how much
  of the gap each accounts for is not measured), while the cuts are of the same
  kind. Both clip and price with the ~4 characters per token estimate here;
  `truncate_field` finds the longest prefix that fits the cap in closed form for
  the built-in estimator and by binary search for a custom tokenizer. All rows
  are microseconds per record — negligible next to a single model call.
- All timed implementations are deterministic on this task: mechanical shaping is reproducible whoever provides it.
  What contexel adds is a fixed, versioned contract: shaping code a model writes per
  task can differ each time it is rewritten (a claim, not measured here), and the
  semantic alternatives depend on a model; these libraries' primitives are not the
  source of nondeterminism.
- `context-engineering-toolkit` was not on PyPI as of 2026-11-26
  (`pip index versions context-engineering-toolkit` finds no distribution). Other
  standalone context-shaping libraries exist, for example keli-wen/context-kit (GitHub)
  and `ctxeng` (PyPI); this benchmark did not run them.
