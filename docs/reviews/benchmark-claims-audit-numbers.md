> Filed 2026-11-27 from an independent audit commissioned after the benchmark comparisons drew public criticism. Sanitised: no user name, home or temporary path, e-mail address or agent identifier. Audited commit: `1825844` (contexel 0.1.17). The audit text is kept as written; what was done about each finding is recorded in `docs/plans/foundation-hardening.md` and in the CHANGELOG.

# contexel benchmark numbers: independent audit

Audited tree: detached checkout of main at 1825844 (contexel 0.1.17), called `<wt>`. The audit scripts and outputs are in `<data>` (a scratch directory outside the repository). Python 3.12.7 on Windows (AMD64), toolz 1.1.0, langchain-core 1.4.9, llama-index-core 0.14.23, tiktoken present. Every Python command ran as `PYTHONPATH=<wt> python ...`, and `contexel.__file__` resolved into `<wt>` (checked: `True`). Nothing was installed, no network was used, and the repository checkout was not modified.

## 0. Bottom line

* **Reproduction is clean.** Three full runs of `python -m benchmarks.competitors` and two of `python -m benchmarks` give zero differences from the committed JSON in every value that is not a timing: episodes, recall, compliance, fill, useful %, native ops, deps, record and token counts, hashes and examples. My own code recomputed the dataset facts and every outcome metric and matches the published values exactly (fill to 4 decimals). Thin wrappers I wrote around toolz, langchain-core and llama-index-core produce byte-identical outputs to the harness.
* **The timings vary a lot from run to run** (factor 0.3 to 3.3), but every published ordering held in all runs.
  * The "about 20 ms" import passed in 2 of 4 measurements.
* **The main problems are description and metric design, not arithmetic.**
  1. contexel's lead over the hand-written rescorer comes entirely from its in-order proximity bonus. That bonus mirrors how the episode queries are built.
  2. "Budget compliance" is measured in estimator tokens. Under a real tokenizer, 94 of 100 of contexel's "compliant" contexts exceed 1,500 tokens.
  3. Empty contexts score as 100% useful and compliant. langchain-core returns an empty context in 31 of 100 episodes.
  4. "Same recall under both signals" holds by construction, not by measurement.
  5. One stale, incorrect number on the docs site is not covered by the checker: `site/stages.html:292`, "49.8 vs 44.4 ms".

Verdict counts (table in section 4, 89 claims):

| Verdict | Count |
|---|---|
| CORRECT | 45 |
| CORRECT-BUT-MISLEADING | 30 |
| INCORRECT | 2 |
| DRIFT-RISK-UNCHECKED (correct today, no check covers it) | 12 |
| NOT-REPRODUCIBLE | 0 |

## 1. Reproduction

### 1.1 Dataset pin

```
$ sha256sum benchmarks/data/codesearchnet_python_test_full.jsonl
07640b5c7d4093454edf88ebd115c875a38ac13499c7c9e9d01c3e5fca4308b9   <- raw bytes (the cached file has CRLF line endings)
$ cat benchmarks/dataset.sha256
05049f798a197a8a80844707abe8b1319bf5c39d37a22fab303aba7625b868e5
$ python -c "... hashlib.sha256(b.replace(b'\r\n', b'\n'))"
39202517 22176 22176
LF  05049f798a197a8a80844707abe8b1319bf5c39d37a22fab303aba7625b868e5   <- equals the pin
```

`fetch_dataset.digest()` is documented as reading CRLF as LF, so the pin verifies. A plain `sha256sum` on a Windows-written cache does not match the pin, which may confuse someone checking by hand. The JSON reports the digest that `verify()` computed: `05049f79...`.

### 1.2 Commands run

| Command | Runs | Wall time | Non-timing differences from HEAD |
|---|---|---|---|
| `python -m benchmarks.competitors` | 3 | ~58 s each | **0** in each run, and 0 between runs |
| `python -m benchmarks` (tiktoken available) | 2 | ~40 s each | **0** in each run, and 0 between runs |
| `python tools/check_benchmark_numbers.py` on the HEAD tree | 1 | | `benchmark numbers: README, PyPI README and site agree with the generated results` (exit 0) |
| the checker on each regenerated tree | 3 | | runs 1 and 2: only the 4 "block differs" problems (timing cells). Run 3 adds 2 more: `README_PYPI.md: claim 'import time' says about 20 ms, contexel's import measured 39.1 ms` (and the same for `site/index.html`) |

The diff was done by `<data>/cmpjson.py`, which walks both JSON trees and splits timing keys (`ms`, `ms_per_episode`, `import_ms`, `off_ms`, `on_ms`, `ratio`, `records_per_sec`, `generated`) from everything else. Example output:

```
== COMPARISON committed vs run3
non-timing differences: 0
== RESULTS committed vs run1
non-timing differences: 0
== RESULTS run1 vs run2
non-timing differences: 0
== COMPARISON run1 vs run2
non-timing differences: 0
```

### 1.3 Timing variation (committed / run 1 / run 2 / run 3)

| Row | ms @28k | ms/episode | Import ms |
|---|---|---|---|
| contexel | 67.4 / 72.0 / 63.8 / 152.4 | 37.6 / 15.2 / 16.2 / 32.7 | 21.0 / 19.2 / 17.6 / 39.1 |
| hand-written | 19.6 / 22.4 / 23.5 / 64.7 | 3.1 / 1.4 / 1.3 / 3.3 | - |
| hand-written (term overlap) | - | 33.9 / 13.8 / 15.9 / 31.1 | - |
| toolz | 37.8 / 40.9 / 40.1 / 91.6 | 14.2 / 6.6 / 7.7 / 11.1 | 12.1 / 13.2 / 12.4 / 33.4 |
| langchain-core | 395.8 / 115.2 / 128.1 / 331.1 | 17.9 / 7.6 / 6.9 / 14.0 | 87.9 / 89.1 / 93.0 / 202.3 |
| llama-index-core | 463.8 / 168.8 / 180.7 / 459.0 | 49.6 / 17.6 / 22.5 / 38.6 | 1155.9 / 1101.9 / 1410.6 / 2285.5 |

A separate measurement of my own, in fresh interpreters, taken while the machine was in a slow phase:

```
import contexel: n=15 median 38.2 min 34.9 max 42.3 ms
import toolz: n=15 median 26.5 ; import langchain_core: n=15 median 178.5 ; import llama_index.core: n=7 median 2636.3
whole process 'import contexel' median 126 ms vs bare interpreter 81 ms
```

The published Import ms therefore excludes interpreter start-up (~80 ms here).

Suite timings (committed / run 1 / run 2):

| Measurement | committed | run 1 | run 2 |
|---|---|---|---|
| full contract, 100k records | 1528.2 ms | 673.8 ms | 1192.9 ms |
| select / hand-written select, 100k records | 94.2 / 94.5 ms | 33.8 / 43.9 ms | 34.0 / 30.0 ms |
| trace off / on (ratio) | 166.5 / 436.0 ms (2.62x) | 61.7 / 188.6 ms (3.06x) | 109.8 / 349.9 ms (3.19x) |

Qualitative claims checked against every run:

* **"Two slowest budget-compliant rows are contexel and the term-overlap scorer": held in 4 of 4.** Compliant rows, slowest first, were `['contexel', 'hand-written (term overlap)', 'langchain-core', 'hand-written']` in the committed run and in runs 1, 2 and 3.
  * The order between the two flipped once in my own same-process timing loop (term overlap 27.23 vs contexel 26.81 ms per episode), so "the order can change" is supported.
* **ms @28k ordering: identical in 4 of 4** (`hand-written < toolz < contexel < langchain-core < llama-index-core`).
  * The contexel to langchain-core ratio ranges from 1.6x (run 1) to 5.9x (committed). In the committed run, langchain-core and llama-index-core were about 3x slower than in runs 1 and 2, while contexel was unchanged. Load was not uniform during the published run.
* **"About 20 ms import": the checker's own tolerance (25%) passes in 2 of 4** (19.2, 17.6 pass; 39.1, 38.2 fail). It describes an idle machine.
* **"The other columns do not vary": confirmed** (0 non-timing differences in every run).

## 2. Independent recomputation (my own code, no harness metric functions)

The scripts are in `<data>`.

* `indep.py` re-implements the tool-output reconstruction and the episode generator from the documented algorithm.
* `metrics.py` uses its own ceil(len/4) estimate, its own hand-written baselines and its own metric code. It reaches contexel only through its public stages, and each competitor through its own API (`toolz.unique` + `keyfilter`, `trim_messages`, `SimilarityPostprocessor` + `LongContextReorder`).
* `harness_cmp.py` imports the harness only to compare outputs.

### 2.1 Dataset facts

```
functions (rows): 22176
tool-output records: 28047
distinct (path,symbol): 14126  distinct url: 14133  distinct (repo,path,symbol): 14131
records removed by (path,symbol) dedupe: 13921
  of which same function (same url as an earlier record): 13914
(path,symbol) keys covering >1 distinct function (url): 5  extra functions merged away: 7
   e.g. ('setup.py', 'read') 4 functions
   e.g. ('setup.py', 'get_version') 2 functions
corpus: distinct (path,symbol) 22161 of 22176 rows; keys with >1 function: 9
episodes (seed 11): 100  built in 10.9s
```

| Fact | Published | Mine | Verdict |
|---|---|---|---|
| CodeSearchNet python/test rows | 22,176 | 22,176 | CORRECT |
| search-tool records | 28,047 | 28,047 | CORRECT |
| "genuine duplicates / the same function matching several queries" | (no count) | 13,921 removed by the key; 13,914 are re-hits of the same function; **7** are distinct functions from different repositories that share `(path, symbol)` | CORRECT-BUT-MISLEADING (low) |
| ground-truth episodes | 100 | 100; target present in raw hits in 100/100 (no candidate was dropped by the filter) | CORRECT |
| evaluation budget | 1,500 | 1,500 estimator tokens (ceil(chars/4)) | CORRECT (see defect D2 on what a "token" is) |

### 2.2 Outcome metrics, recomputed (`metrics.py`)

```
contexel                       recall 100.0 / 100.0  compl 100.0  fill   0.9455  useful 100.00  digest(strong) 4983746906415a78
hand-written                   recall  93.0 /  32.0  compl 100.0  fill   0.9472  useful 100.00  digest(strong) e18549ffc9ed33ea
hand-written (term overlap)    recall  97.0 /  97.0  compl 100.0  fill   0.9442  useful 100.00  digest(strong) b754d667b479120c
toolz                          recall 100.0 / 100.0  compl   0.0  fill  91.6240  useful 100.00  digest(strong) f70141000f7a80d2
langchain-core                 recall  30.0 /  30.0  compl 100.0  fill   0.5210  useful  89.75  digest(strong) 19b7ef59ce5d3543
llama-index-core               recall 100.0 / 100.0  compl   0.0  fill 129.2128  useful  74.15  digest(strong) 9a5a884a32ee3bb5
contexel proximity=False       recall  95.0 /  95.0  compl 100.0  fill   0.9463  useful 100.00
contexel match=stem            recall  99.0 /  99.0  compl 100.0  fill   0.9457  useful 100.00
```

Committed JSON for comparison:

| Row | fill_x | useful % |
|---|---|---|
| contexel | 0.94549 | 100 |
| hand-written | 0.94723 | 100 |
| term overlap | 0.94419 | 100 |
| toolz | 91.62398 | 100 |
| langchain-core | 0.52101 | 89.7456 |
| llama-index-core | 129.21278 | 74.1509 |

Recall and compliance are identical for every row.

The output records of each row, compared with the harness by digest over the 100 episodes:

```
harness episodes == independent episodes: True
contexel                       harness 4983746906415a78  independent 4983746906415a78  SAME
hand-written                   harness e18549ffc9ed33ea  independent e18549ffc9ed33ea  SAME
hand-written (term overlap)    harness b754d667b479120c  independent b754d667b479120c  SAME
toolz                          harness f70141000f7a80d2  independent f70141000f7a80d2  SAME
langchain-core                 harness 19b7ef59ce5d3543  independent 19b7ef59ce5d3543  SAME
llama-index-core               harness 9a5a884a32ee3bb5  independent 9a5a884a32ee3bb5  SAME
```

The inflected table (99/35, 98/98, 96/35, 90/90; 100 episodes, 296 terms) came out identical in all three harness runs. As a cross-check, contexel `match="stem"` on the main episodes gives 99/99 (1 point below word mode, the same cost COMPARISON.md states for the inflected set).

### 2.3 Extra probes (`probe.py`, `seeds.py`, `timing.py`, `steps.py`, `tok.py`, `deps.py`, `det_*.py`)

Triviality, leakage and order robustness on the published episodes:

```
episodes 100: raw hits median 615.0 (min 20, max 900); unique median 550.5
records kept by contexel at 1,500 tokens: median 24.0 (min 17, max 27)
target position in incoming deduped order: median 15.0; within first 30: 60; first 15: 48; position 0: 14
target is the unique top rescore score: proximity on 70/100, proximity off 39/100
target receives the in-order proximity bonus: 100/100
term-overlap: records scoring >= target (target's tie group incl. itself): median 2.0, >30 in 3 episodes
all query terms appear in the target's snippet in query order: 99/100
no-rank control (incoming order, same glue): recall 55%
contexel proximity=False: 95% (strong) 95% (weak)
shuffled hit order x5, contexel: [100.0, 100.0, 100.0, 100.0, 100.0]
shuffled hit order x5, term overlap: [97.0, 97.0, 98.0, 97.0, 99.0]
shuffled hit order x5, hand-written (strong): [94.0, 93.0, 93.0, 93.0, 93.0]
shuffled hit order x5, contexel prox=False: [95.0, 95.0, 95.0, 95.0, 95.0]
strong signal: target score in [37, 38, 39] (max possible 39); records scoring >= target: median 2.0, max 183; episodes with >24 such records: 8
```

The same pipelines on episode sets built with other seeds (the documented generator, 100 episodes each, recall strong/weak):

```
seed  n   contexel  contexel prox=False  term overlap  hand-written
  11 100  100/100   95/95                97/97         93/32     <- the published seed
   1 100  100/100   98/98                98/98         94/37
   2 100   99/99    99/99                99/99         98/26
   3 100  100/100   98/98                99/99         97/41
   4 100  100/100   99/99               100/100       100/35
   5 100  100/100   96/96                99/99         96/39
   6 100  100/100   97/97                98/98         94/25
   7 100   98/98    96/96                96/96         92/28
   8 100  100/100  100/100              100/100        99/37
   9 100   98/98    96/96                98/98         97/22
mean      99.5      97.4                 98.4          96.0 / 32.2
```

What the seed table shows:

* contexel is never below the term-overlap baseline. Its lead is 0 to 3 points, and the published seed has the largest lead of the ten.
* Without the proximity bonus, contexel is below the baseline on 6 seeds, level on 4, and never above.
* The published seed is also the 3rd-worst of the ten for the score-trusting baseline.

Real-token check (tiktoken cl100k_base) of the "1,500-token" contexts on the published episodes:

```
contexel        estimated tokens mean 1418 (max 1459); cl100k tokens mean 1627 (min 1109, max 1796); episodes over 1,500 cl100k tokens: 94/100
hand-written    estimated tokens mean 1421 (max 1459); cl100k tokens mean 1591 (min 1096, max 1766); episodes over 1,500 cl100k tokens: 91/100
term overlap    estimated tokens mean 1416 (max 1454); cl100k tokens mean 1589 (min 1096, max 1748); episodes over 1,500 cl100k tokens: 92/100
langchain-core  estimated tokens mean 782 (max 1477); cl100k tokens mean 846 (min 1, max 1794); episodes over 1,500 cl100k tokens: 21/100
```

Empty contexts:

```
harness on an empty context: total 1 useful 1 -> share 1.0
langchain-core: empty context in 31/100 episodes (first raw record alone exceeds the budget in 31)
langchain-core: empty 31; useful share over the 69 non-empty contexts 85.1%; recall among non-empty 30/69
```

Breakdown of ms/episode (the same loop as `native_outcomes`, strong signal, best of 3 passes; this is the second of two runs). "Scoring" is the time the timed loop spends scoring the result rather than shaping it:

```
contexel                       shaping   26.81  shaping+scoring (what ms/episode times)   26.99  scoring share   0.7%
hand-written                   shaping    2.76  shaping+scoring (what ms/episode times)    2.93  scoring share   5.6%
hand-written (term overlap)    shaping   27.23  shaping+scoring (what ms/episode times)   27.40  scoring share   0.6%
toolz                          shaping    2.57  shaping+scoring (what ms/episode times)   11.67  scoring share  78.0%
langchain-core                 shaping   15.21  shaping+scoring (what ms/episode times)   15.29  scoring share   0.5%
llama-index-core               shaping   26.69  shaping+scoring (what ms/episode times)   37.96  scoring share  29.7%
```

The first run showed the same scoring shares (toolz 77.5%, llama-index-core 31.0%) plus one load spike (term overlap 72.6 ms).

Per step of the timed 28k task (best of 5, during a slow machine phase):

```
contexel           select(select) 27.2 | dedupe(dedupe) 83.1 | truncate(truncate) 26.4 | rank(rank) 3.0 | trim(trim) 0.2
hand-written       select(select) 31.7 | dedupe(dedupe) 12.7 | truncate(truncate) 10.9 | rank(rank) 2.6 | trim(trim) 0.2
toolz              select(select) 49.1 | dedupe(dedupe) 11.5 | truncate(truncate) 10.0 | rank(rank) 2.4 | trim(trim) 0.2
langchain-core     select 27.1 | dedupe 11.8 | truncate 13.5 | rank 4.2 | wrap as messages(adapter) 196.2 | trim(trim) 21.7
llama-index-core   select 24.4 | dedupe 11.7 | to nodes(adapter) 335.8 | from nodes(adapter) 19.2 | truncate 14.4 | rank 3.3 | trim 0.2
```

Determinism, re-tested in fresh interpreters. The suite-1 contract was re-stated by hand, and the outcome pipeline with `rescore` was also tested; the suite itself never tests rescore:

```
PYTHONHASHSEED=0: outcome-with-rescore digest 4983746906415a78
   suite-1 shaped ['6c9fd99fc2f01c4b', '6c9fd99fc2f01c4b', '6c9fd99fc2f01c4b'] raw ['b89a036c', 'd23ac4b1', '3d2695c0']
(identical lines for PYTHONHASHSEED=1, 2, 12345 and random)
```

The rescore digest was computed from the WEAK-signal input. It equals the strong-signal digest in section 2.2, so contexel's whole output is byte-identical under both signals.

Trace overhead with tracing inactive versus the same stages called directly (`timing.py`):

```
10k records, best of 7: direct stage calls 94.7 ms, pipeline (trace inactive) 94.4 ms, trace active 308.7 ms; inactive-vs-direct -0.3 ms
10k records, best of 7: direct stage calls 95.6 ms, pipeline (trace inactive) 97.3 ms, trace active 294.6 ms; inactive-vs-direct +1.7 ms
10k records, best of 7: direct stage calls 94.8 ms, pipeline (trace inactive) 98.0 ms, trace active 311.3 ms; inactive-vs-direct +3.2 ms
```

Tokenizer and serialization (tiktoken cl100k_base, independent, `tok.py`):

```
prose_sample.md            tiktoken  10609 est  10327 error -2.66%
the-context-contract.md    tiktoken   2365 est   2779 error +17.51%
contexel/stages.py         tiktoken   6274 est   6497 error +3.55%
reference_agent/tools.py   tiktoken   1709 est   1781 error +4.21%
json 500 records           tiktoken  56877 est  40606 error -28.61%
prose_sample.md == README.md: False      (it is a frozen older copy, as labelled)
estimator vs cl100k on real CodeSearchNet hit records (20 episodes' raw hits, 12,798,860 chars): est 3,199,715 actual 3,329,894 error -3.9%
budget 500: json 10 rec 500 tok (50.00/rec), compact json 401 (40.10/rec), ISON same 10 rec 341 (34.10/rec); ISON-priced 13 rec 442 (34.00/rec)
budget 2000: json 40 rec 2010 tok (50.25/rec), compact json 1611 (40.27/rec), ISON same 40 rec 1341 (33.52/rec); ISON-priced 54 rec 1800 (33.33/rec)
```

Dependency closures, recomputed with my own traversal (`deps.py`):

```
contexel: 0 installed transitive deps; required-but-not-installed (not counted): none
toolz: 0 ... none
langchain-core: 25 ... none
llama-index-core: 60 ... none
pyproject.toml:26  dependencies = []
```

Other README numbers checked by running them:

```
split 1,000,000 chars into 1,000,000 chunks: 11.53s (under tracemalloc), retained 436 MB, peak 436 MB
  same without tracemalloc: 1.58s
traced split, 50,000-char side field, 4,000 chunks: 1.10s
128,000 alternating combining marks: rescore default 9.5 ms, normalize='nfc' 7.88 s
README examples: 'ERROR timeout after retry\nWARN retry limit reached\n' [54, 13]
                 [0, 0, 0] [0.268574, 0.188001, 0]
                 [0.392332, 0, 0] [0.188001, 0.188001, 0]
determinism dataset: 5000 records, distinct (path,line): 3481 -> duplicate share 30.4%
native-ops demo:  toolz as published: 2/6 (select, dedupe)
                  toolz + toolz.topk as rank: 3/6 (select, dedupe, rank)
```

## 3. Definitions versus text

| Column | What the text says | What the code does | Verdict |
|---|---|---|---|
| Native ops | "computed from the code that defines each implementation ... not typed" (README.md:112-116, benchmarks.html:102-103) | `opcount.count` profiles each step and calls it native if a function of the library's package runs. That part is computed. Which steps each row has, which operation each step serves (`Step(name, fn, "dedupe")`), and the adapter/other labels are typed by hand in competitors.py. toolz ships `topk`; using it as the rank step turns toolz's 2/6 into 3/6. | CORRECT-BUT-MISLEADING |
| Recall (strong / weak) | "did the record the agent actually needed survive into a 1,500-token context" | `_has_target`: is (path, symbol) present in the context. `_with_score` swaps only the `score` value; hit-list order is identical in both signals (sorted by weak count per term), so any shaper that ignores the score gets identical columns. | Numbers CORRECT; the two-signal framing is misleading (D5) |
| Compliance | "did the final context actually fit the budget?" | `est_tokens(json.dumps(context)) <= 1500`, where est = ceil(chars/4). Any row that trims by summing per-record costs (+2 each) is guaranteed 100%: the list adds only 2 characters per record. An empty context counts as compliant. | CORRECT-BUT-MISLEADING (D2, D4) |
| Fill x | "mean context tokens / budget" | the same estimator, averaged over episodes | CORRECT |
| Useful % | "share of final-context tokens spent on needed fields of unique records" | tokens of the FIELDS-projected first occurrences / total tokens. Any select(FIELDS)+dedupe pipeline scores exactly 100% by construction. An empty context scores 1/1 = 100%. | CORRECT-BUT-MISLEADING (D4) |
| ms/episode | "the work, not overhead" | one pass (not best-of) over 100 episodes, strong signal only, timing shaping **plus** the harness's scoring (`json.dumps` of the context, `_has_target`, `_useful_tokens`). Scoring is 0.5-5.6% of the figure for compliant rows, **78%** for toolz and **30%** for llama-index-core. | CORRECT-BUT-MISLEADING (D7) |
| ms @28k | "everything a library lacks was filled with the same glue, so timing differences are the library's" | best of 5 over 28,047 records, 2,000-token budget. For langchain-core and llama-index-core, 72% and 82% of the time is the benchmark's operand conversion (json.dumps of every record into a HumanMessage or TextNode), not the library's operation: native `trim_messages` takes 21.7 ms. | CORRECT-BUT-MISLEADING (D9) |
| Import ms | "median of 5 fresh interpreters, each importing only the library" | `sys.executable -c "t0=perf_counter(); import X; print(...)"` with cwd=<wt>, median of 5. It is in-process time of the import statement, **excluding** interpreter start-up (~80 ms here). Warm file cache after the first run. The same interpreter as the benchmark. | CORRECT, under-described (warm, start-up excluded) |
| Deps | "installed distributions the package requires (recursive)" | `importlib.metadata` closure of non-extra requirements, with markers evaluated for this Python/OS, counting only installed distributions (none were missing). For contexel the metadata read is the **installed dist-info** (here a user-site copy of 0.1.17), not `<wt>/pyproject.toml`; both list no dependencies. | CORRECT (environment-dependent; it could read a stale install) |

## 4. Every claim audited

"Chk" says whether `tools/check_benchmark_numbers.py` covers the item: **B** = generated block, **C** = registered claim, **R** = the report re-render check (the .md equals its template rendered from the JSON), **-** = nothing checks it. All B/C/R checks compare against the **committed** JSON; CI never re-runs the benchmark.

| id | file:line | Exact text (trimmed) | Published | Mine | Verdict | Chk | Evidence |
|---|---|---|---|---|---|---|---|
| R1 | README.md:79-80 | "across fresh interpreters with different `PYTHONHASHSEED` values and gets the same SHA-256 every time" | same hash | same hash, 5 seeds, 6c9fd99fc2f01c4b | DRIFT-RISK-UNCHECKED | - | det_suite.py |
| R2 | README.md:85 | "(22,176 functions)" | 22,176 | 22,176 | CORRECT | C | indep.py |
| R3 | README.md:85 | "28,047 search-tool records" | 28,047 | 28,047 | CORRECT | C | indep.py |
| R4 | README.md:85-86 | "with genuine duplicates" | - | 13,914 of 13,921 removed are re-hits; 7 are distinct functions | CORRECT-BUT-MISLEADING | - | indep.py |
| R5 | README.md:86 | "100 ground-truth episodes" | 100 | 100 | CORRECT | C | indep.py |
| R6 | README.md:90 | "downloads the CodeSearchNet split, ~30 MB" | ~30 MB | not verifiable offline; derived JSONL is 39.2 MB | DRIFT-RISK-UNCHECKED | - (MB is not a checked unit) | `39202517` bytes |
| R7 | README.md:100-107 | glance table, non-timing cells (ops, recall, compliance, fill, useful, deps) | table | identical, independently recomputed | CORRECT | B | sections 2.2, 1.2 |
| R8 | README.md:100-107 | glance timing cells (67, 37.6, 21, 20, 3.1, 33.9, 38, 14.2, 12, 396, 17.9, 88, 464, 49.6, 1,156) | one run | 0.29x-3.3x across runs; all orderings held | CORRECT (one run, disclosed) | B | section 1.3 |
| R9 | README.md:112-116 | "*computed* from the code that defines each implementation ..., not typed" | - | step lists and op labels are typed; toolz.topk unused | CORRECT-BUT-MISLEADING | - | native-ops demo |
| R10 | README.md:116-119 | "in `ms @28k`, everything a library lacks was filled with the *same* hand-written glue, so timing differences are the library's" | - | langchain 72%, llama 82% is the benchmark's operand conversion | CORRECT-BUT-MISLEADING | - | steps.py |
| R11 | README.md:122-123 | "survive into a 1,500-token context?" | 1,500 | 1,500 estimator tokens = mean 1,627 cl100k tokens | CORRECT-BUT-MISLEADING | C (number only) | cl100k check |
| R12 | README.md:123-125 | "The episodes guarantee that record is present in the raw hits" | - | 100/100 | CORRECT | - | competitors.py:621; probe |
| R13 | README.md:125-126 | "contexel's recall is the same under both signals, because `rescore` derives relevance from the records' own text" | same | same, but by construction: hit order identical, output digest identical | CORRECT-BUT-MISLEADING | C (`_same_recall`) | det_child.py, weak = strong digest |
| R14 | README.md:128-130 | "it is the fairest comparison for `rescore`, another rescorer rather than none" | - | contexel's 3-point lead is the proximity bonus (95% without it) | CORRECT-BUT-MISLEADING | - | probe, seeds |
| R15 | README.md:131 | "**Compliance %** — did the final context actually fit the budget?" | 100% | estimator budget; 94/100 over 1,500 cl100k tokens; guaranteed for any summing trim | CORRECT-BUT-MISLEADING | - | cl100k check |
| R16 | README.md:131-133 | "A row with full recall and zero compliance (toolz, llama-index) got there by emitting many times the budget" | 91.62x / 129.21x | 91.6240 / 129.2128 | CORRECT | C | metrics.py |
| R17 | README.md:134-136 | "langchain-core honors the budget but spends part of it on duplicates and field bloat ...; llama-index spends more" | 89.7 / 74.2 | 89.75 / 74.15 (85.1% over langchain's non-empty contexts) | CORRECT-BUT-MISLEADING | C | empty-context check |
| R18 | README.md:137 | "**ms/episode is the work, not overhead.**" | - | contexel scoring share 0.7%; toolz 78%, llama 30% | CORRECT-BUT-MISLEADING | - | ms/episode breakdown |
| R19 | README.md:143-145 | "the two slowest budget-compliant rows, in an order that can change from run to run" | - | 4/4 runs; the order flipped once in my loop | CORRECT | C | section 1.3 |
| R20 | README.md:146-148 | "Every other compliant row is faster because it does less still" | - | hand-written and langchain faster in 4/4 | CORRECT | (follows from C) | section 1.3 |
| R21 | README.md:148-150 | "they vary with the machine's load ...; the other columns do not" | - | 0 non-timing differences in 3+2 runs | CORRECT | - | cmpjson.py |
| R22 | README.md:152-155 | "contexel's time includes the checks each stage runs ... Both are noise next to a single model call" | - | contexel dedupe 83 ms vs hand 13 ms on 28k; qualitative | CORRECT | - | steps.py |
| R23 | README.md:162-164 | "Its target records differ from the main table's" | - | yes (pool=4, term filter) | CORRECT | - | competitors.py:630 |
| R24 | README.md:169-176 | inflected table 99/35, 98/98, 96/35, 90/90 | table | identical in 3 runs | CORRECT | B | cmpjson.py |
| R25 | README.md:178-180 | "Exact-word matching (the default) collapses ... `match="stem"` recovers them" | - | 99->35, 96->35; stem 98->98 | CORRECT | C | |
| R26 | README.md:180-182 | "never reads the query, so inflection cannot touch it: it is the control" | 90 / 90 | true by construction (the row carries no signal) | CORRECT | C | code |
| R27 | README.md:195 | "−29% on JSON-heavy records" | −29% | −28.61% on the synthetic hex-id sample; −3.9% (raw) and −12.8% (shaped) on this benchmark's real records | CORRECT-BUT-MISLEADING | C | tok.py |
| R28 | README.md:41 | rescore: "IDF `ln((N-df+0.5)/(df+0.5)+1)` × ... `tf/(tf+1.5)` ... within 80 chars" | - | matches stages.py:476-488 | CORRECT | - | code |
| R29 | README.md:330-334 | example output `[54, 13]` | [54, 13] | [54, 13] | CORRECT | - | ran |
| R30 | README.md:415-418 | `[0, 0, 0]` / `[0.268574, 0.188001, 0]` | | same | CORRECT | - | ran |
| R31 | README.md:448-450 | `[0.392332, 0, 0]` / `[0.188001, 0.188001, 0]` | | same | CORRECT | - | ran |
| R32 | README.md:380-381 | "a 1,000,000-character text retains roughly 440 MB in Python, 140 MB in TypeScript and 540 MB in C#" | 440 MB (Py) | 436 MB (Py); TS/C# not verified | DRIFT-RISK-UNCHECKED | - | tracemalloc |
| R33 | README.md:382 | "about 0.4 to 2 seconds per million chunks" | 0.4-2 s | 1.58 s | DRIFT-RISK-UNCHECKED | - (seconds excluded by design) | |
| R34 | README.md:384-386 | "with a 50,000-character side field and 4,000 chunks a traced `split` took about 0.6 to 2 seconds" | 0.6-2 s | 1.10 s | DRIFT-RISK-UNCHECKED | - | |
| R35 | README.md:470-474 | "128,000 of U+0301 and U+0323 ... takes seconds with `normalize="nfc"` ... the default takes milliseconds" | s / ms | 7.88 s / 9.5 ms | DRIFT-RISK-UNCHECKED | - | |
| R36 | README.md:662-664 | "`context-engineering-toolkit` ... was not on PyPI as of 2026-07" | - | not verifiable offline | DRIFT-RISK-UNCHECKED | - | |
| R37 | README.md:11, 236 | "dependencies-0" badge; "zero dependencies" | 0 | pyproject `dependencies = []`; closure 0 | CORRECT | - (badge URL not scanned) | deps.py |
| R38 | README.md:676-678 | "(measured in benchmark suite 6)" | - | suite 6 exists: 34 vs 50 tokens/record | CORRECT | - | RESULTS.md section 6 |
| P1 | README_PYPI.md:97-98 | "22,176 real functions → 28,047 search-tool records" | | same | CORRECT | C | |
| P2 | README_PYPI.md:98 | "with 100 ground-truth episodes" | 100 | 100 | CORRECT | C | |
| P3 | README_PYPI.md:99-102 | "contexel expresses all six operations natively, which no other compared row does" | 6/6 vs ≤2/6 | as computed, under authored step lists | CORRECT-BUT-MISLEADING | C | native-ops demo |
| P4 | README_PYPI.md:102-103 | "It holds a 1,500-token budget in 100% of episodes" | 100% | 100% in estimator tokens; 6% in cl100k tokens | CORRECT-BUT-MISLEADING | C | cl100k check |
| P5 | README_PYPI.md:103-104 | "keeps the needed record in 100% of them under both a strong and a weak retrieval signal" | 100% | 100%, but both columns are identical by construction | CORRECT-BUT-MISLEADING | C | det_child.py |
| P6 | README_PYPI.md:104-105 | "spends 100% of context tokens on unique, needed fields" | 100% | 100% (guaranteed by select+dedupe = the metric's definition) | CORRECT | C | metrics.py |
| P7 | README_PYPI.md:105 | "at 0 dependencies" | 0 | 0 | CORRECT | C | deps.py |
| P8 | README_PYPI.md:105 | "an import of about 20 ms" | ~20 | 19.2 / 17.6 / 39.1 (runs); 38.2 (15-run median) | CORRECT-BUT-MISLEADING | C (±25% vs committed only) | section 1.3 |
| P9 | README_PYPI.md:106-108 | "reaches 97% recall and 100% budget compliance, so on these episodes the margin over it is small" | 97 / 100 | 97 / 100; 10-seed means 99.5 vs 98.4 | CORRECT | C | seeds.py |
| P10 | README_PYPI.md:108-110 | "the two slowest budget-compliant rows ..., *because they do the most work per record*" | - | ordering held 4/4; the "because" is not measured (the overlap scorer does less work and takes as long) | CORRECT-BUT-MISLEADING | C (ordering) | |
| P11 | README_PYPI.md:112-117 | "in 99% ... in 35% with inflections ... `match="stem"` finds it in 98%" | 99/35/98 | 99/35/98 | CORRECT | C | |
| P12 | README_PYPI.md:120-123 | "same SHA-256 every time, even when raw tool output carries fresh request ids" | | yes (noise_neutralized PASS; 5 hash seeds) | DRIFT-RISK-UNCHECKED | - | det_suite.py |
| I1 | site/index.html:61-63 | determinism card (same text as P12) | | same | DRIFT-RISK-UNCHECKED | - | |
| I2 | site/index.html:78 | "Plain Python, about 20&nbsp;ms import" | ~20 | as P8 | CORRECT-BUT-MISLEADING | C | |
| I3 | site/index.html:79-80 | "Eight pipeline stages ... plus a `merge` combiner" | 8 | 8 record stages; `split` is also used as a pipeline stage (README.md:318-324) | CORRECT-BUT-MISLEADING (low) | - | |
| I4 | site/index.html:87-90 | "28,047 real search-tool records ... 100 ground-truth episodes at a 1,500-token budget" | | same (estimator tokens) | CORRECT | C | |
| I5 | site/index.html:94-106 | home glance incl. "0% (92× budget)", "0% (129× budget)" | | 91.62 -> 92, 129.21 -> 129 | CORRECT | B | |
| I6 | site/index.html:108-109 | "contexel is the only row with full marks in every outcome column" | | true | CORRECT | C | |
| I7 | site/index.html:110-116 | "two slowest ... Every other compliant row is faster by doing less still ... negligible next to a single model call" | | held 4/4 | CORRECT | C | |
| B1 | site/benchmarks.html:41-44 | "Every number on this page is generated, or checked against the results" | | "~30 MB" is unchecked; checks compare against committed JSON, not a re-run | CORRECT-BUT-MISLEADING | - | |
| B2 | site/benchmarks.html:53-60 | suite1 block, deterministic rows: 4/4 PASS, 6c9fd99fc2f01c4b, 1,890 of 2,000, +0.5%, 24 / 24, the five tokenizer errors | | identical, independently recomputed | CORRECT | B | tok.py |
| B3 | site/benchmarks.html:57-59 | suite1 timing rows: 65,438 records/s (1,528 ms), 94.2 vs 94.5 ms, 166.5 vs 436.0 ms (2.62x) | | 674 / 1,193 ms; 33.8 vs 43.9 and 34.0 vs 30.0; 3.06x / 3.19x | CORRECT-BUT-MISLEADING (low: suite 1 has no one-run caveat) | B | section 1.3 |
| B4 | site/benchmarks.html:65-67 | "it under-estimates JSON-heavy records" | | −28.6% synthetic; −3.9% to −12.8% real | CORRECT | C | tok.py |
| B5 | site/benchmarks.html:67-69 | "Inactive tracing is the "zero cost" claim" | | the suite never measures inactive vs untraced; I measured −0.3 to +3.2 ms on ~95 ms | CORRECT-BUT-MISLEADING | - | timing.py |
| B6 | site/benchmarks.html:74 | "~30&nbsp;MB" | | not verifiable | DRIFT-RISK-UNCHECKED | - | |
| B7 | site/benchmarks.html:75-79 | "22,176 real functions ... 28,047 ... 100 ... guaranteed present ... Budget: 1,500 tokens" | | same | CORRECT | C | |
| B8 | site/benchmarks.html:81-93 | full glance block | | non-timing identical | CORRECT | B | |
| B9 | site/benchmarks.html:97-103 | "timing differences are theirs ... Native ops are *computed* ..., not typed" | | as R9 / R10 | CORRECT-BUT-MISLEADING | - | |
| B10 | site/benchmarks.html:104-108 | "langchain-core holds the budget but ... the needed record survives only when it happens to arrive early" | | true; plus an EMPTY context in 31/100 episodes, not mentioned | CORRECT-BUT-MISLEADING (low) | C | |
| B11 | site/benchmarks.html:122-127 | "The two recall columns bound the semantic concession ... so its two columns read the same — on these episodes" | | identical by construction | CORRECT-BUT-MISLEADING | C | |
| B12 | site/benchmarks.html:145-163 | inflected block and "collapses ... recovers ... it is the control" | | identical | CORRECT | B / C | |
| B13 | site/benchmarks.html:169-171 | "Full recall here means the ambiguity clusters resolved once exact-word evidence was used" | | exact-word evidence alone gives 95%; the in-order proximity bonus closes the gap | CORRECT-BUT-MISLEADING | - | probe |
| S1 | site/stages.html:290-293 | "Inactive overhead is a single ContextVar lookup per stage — single-digit milliseconds (49.8 vs 44.4&nbsp;ms over 10k records in RESULTS.md)" | 49.8 vs 44.4 | RESULTS.md has 166.5 (inactive) vs 436.0 (active); no 49.8 or 44.4 anywhere; my inactive vs direct: −0.3 to +3.2 ms | **INCORRECT** | - (stages.html is not in `publish.FILES`) | RESULTS.md section 3 |
| S2 | site/stages.html:102, 160 | "(seconds for 128,000 of them)" | | 7.88 s | DRIFT-RISK-UNCHECKED | - | |
| S3 | site/stages.html:180; architecture.html:81 | "closed-form (`ceil(len/4)` is invertible: 4×budget characters)"; "≈4 chars/token ... +2 framing per record"; "Never exceeds the cap" | | matches code; worst field 24 for a cap of 24 | CORRECT | - | stages.py:497-500, 557 |
| C1 | benchmarks/COMPARISON.md:17-19 | "28,047 records whose duplicates are real (the same function matching several queries)" | | 7 of 13,921 are different functions | CORRECT-BUT-MISLEADING (low) | R | indep.py |
| C2 | benchmarks/COMPARISON.md:59 | "contexel is the slowest budget-compliant row (37.6 ms)" | | contexel slowest compliant in 4/4 harness runs | CORRECT | R | |
| C3 | benchmarks/COMPARISON.md:147 | "Its two recall columns are identical because `rescore` derives relevance ..., so the tool's score quality does not matter" | | by construction | CORRECT-BUT-MISLEADING | R | |
| C4 | benchmarks/COMPARISON.md (hand-written bullet) | "it gets re-derived, slightly differently, every run" | | not measured: the benchmark's row is fixed code, Deterministic = yes | CORRECT-BUT-MISLEADING | static template | |
| C5 | benchmarks/COMPARISON.md (ceiling bullet) | "Where contexel's recall ... falls short of 100%, that is this ambiguity, measured — not a scoring defect" | | not measured; with proximity off recall is 95% on the same episodes | CORRECT-BUT-MISLEADING | static template | probe |
| C6 | benchmarks/COMPARISON.md:161-167 | "(91.6x)", "useful share 89.7%", "recall 30%", "129.2x" | | same | CORRECT | R | |
| C7 | benchmarks/COMPARISON.md:199 | "Opting in to the stemmer costs 1 point on the original terms" | 1 | 99 -> 98 (also 100 -> 99 on the main episodes) | CORRECT | R | metrics.py extra |
| C8 | benchmarks/COMPARISON.md:222 | "No library in the timed set expresses more than 2 of the 5 stages natively ...; contexel is the only 5/5" | | as computed under authored step lists | CORRECT-BUT-MISLEADING | R | native-ops demo |
| C9 | benchmarks/COMPARISON.md (reading bullets) | "All rows are microseconds per record" | | 2.4-16.5 µs/record (committed); 16.4 µs (run 3, llama) | CORRECT | static template | |
| C10 | benchmarks/COMPARISON.md:231 | "All timed implementations are deterministic on this task" | | yes; outputs identical across 3 runs | CORRECT | R | |
| X1 | benchmarks/RESULTS.md:13 | "Per the README ("How much does it cut?")" | | the README has no such section (also suites.py:15, benchmarks/__init__.py:8) | **INCORRECT** | R (renders, but the reference is not validated) | grep |
| X2 | benchmarks/RESULTS.md:7 | "best of 5 runs. Datasets are seeded and byte-identical across machines" | | byte-identical across 5 interpreters and 2 runs on one machine; cross-machine not verifiable | CORRECT (one machine) | - | det_suite.py |
| X3 | benchmarks/RESULTS.md:21-22 | "5,000 search-hit records (30% duplicates), hash prefix `6c9fd99fc2f01c4b`"; 4 x PASS | | 30.4% duplicates; same prefix; 4 PASS | CORRECT | R | |
| X4 | benchmarks/RESULTS.md sections 2, 4, 5, 6 | budget, truncate, accuracy, reduction and encoding tables | | identical in 2 runs; accuracy recomputed independently | CORRECT | R | |
| X5 | benchmarks/RESULTS.md section 6 | ISON vs JSON table (50.00 vs 34.00 tokens/record at 500) | | correct, but the JSON baseline is contexel's spaced JSON; compact JSON is 40.1 tokens/record | CORRECT-BUT-MISLEADING (low) | R | tok.py |
| X6 | contexel/tokens.py:106 | "it undercounts JSON-heavy records by ~29% in the benchmark" | 29% | 28.61% | DRIFT-RISK-UNCHECKED | - | |

Verdict totals from this table (89 rows):

| Verdict | Count |
|---|---|
| CORRECT | 45 |
| CORRECT-BUT-MISLEADING | 30 |
| INCORRECT | 2 |
| DRIFT-RISK-UNCHECKED | 12 |
| NOT-REPRODUCIBLE | 0 |

**Cross-file agreement.** Every shared number agrees across README.md, README_PYPI.md, site/index.html, site/benchmarks.html, COMPARISON.md and RESULTS.md: 22,176; 28,047; 100; 1,500; every recall, compliance, fill and useful value; 21 / 20.97 / "about 20"; 91.62 / 91.6x / 92x; 129.21 / 129.2x / 129x; −28.61 / −28.6% / −29%. The differences are only rounding at the precision each page prints. The single disagreement is site/stages.html:292 against RESULTS.md (S1).

## 5. "Only X" / "every other" / "fairest" / "same under both signals" / "control"

* **"contexel is the only row with full marks in every outcome column" / "expresses all six operations natively, which no other compared row does": true of the data.**
  * The second statement holds only under the step lists the benchmark wrote (toolz `topk` would make toolz 3/6).
* **"Every other compliant row is faster": true in 4 of 4 runs** (hand-written: 1.3-3.3 ms; langchain-core: 6.9-17.9 ms; against 13.8-37.6 ms for contexel and the overlap scorer).
* **"Fairest comparison": factually the only other rescorer, but not a neutral test.**
  * The episode queries are the target docstring's first three words of 5 or more characters, in docstring order (competitors.py:596-603). The target's snippet is that docstring, and rescore runs before truncation (competitors.py:233).
  * contexel's proximity bonus fires exactly when consecutive query terms appear in order within 80 characters (stages.py:483-488). It fires for the target in 100 of 100 episodes.
  * Without it contexel scores 95%, below the overlap scorer's 97%, and it never beats the scorer on any of the ten seeds. The whole published lead is that one feature, on queries built so that it fires. Real agent queries do not come pre-ordered like their target's docstring.
* **"The same under both signals": true by construction.**
  * `_with_score` only swaps the score value; the hit lists keep the same order.
  * contexel, the overlap scorer, langchain-core and toolz all ignore the score, so their two columns are always equal. contexel's entire output is byte-identical under both signals (digest 4983746906415a78).
  * This shows that rescore ignores the tool's score. It does not show robustness to a poor retrieval ranking: the shuffle test does that better, and contexel stays at 100% under five shuffles.
* **"It is the control": true by construction** (the row never reads the terms, so 90 = 90 cannot fail). It detects nothing about inflection. It only confirms that the inflected episodes' hit lists are the unchanged originals.

## 6. Anything wrong, surprising or too good

1. **Proximity leakage** (section 5). It favors contexel over the hand-written rescorer. It does not affect the score-trusting row, toolz, langchain-core or llama-index-core, none of which read the query.
2. **Compliance cannot tell the trimming rows apart.**
   * Pricing each record at ceil(len/4)+2 always covers the serialized list (the list adds 2 characters per record), so any summing trim scores 100%.
   * Measured with a real tokenizer, the same "compliant" contexts are over budget in 91 to 94 of 100 episodes.
3. **Useful % and compliance score an empty context as 100%** (`_useful_tokens([]) / est_tokens("[]") = 1/1`).
   * langchain-core is empty in 31 of 100 episodes, because its first raw record alone exceeds the budget and `trim_messages(strategy="first")` then keeps nothing.
   * Its 89.7% useful share is 85.1% over the 69 non-empty contexts, and its fill (0.52) averages in the 31 empties.
4. **Useful % = 100 is a tautology for any `select(FIELDS)`+dedupe row:** the metric's definition is that same projection. It measures only whether a row projects and dedupes.
5. **The episodes are not trivial, but they are easy for any lexical scorer.**
   * Leaving the incoming order as it is gives 55% recall, and the target sits at position 0 in 14 episodes.
   * Every query term comes from the target's own docstring, so the hand-written whole-word overlap already reaches 97%. The documents state this ("the target's own words").
6. **Seed choice.** Seed 11, the default, gives contexel its largest lead over the overlap scorer among the ten seeds tried, and is the 3rd-worst seed for the score-trusting baseline. I make no claim about intent. A 10-seed mean (99.5 / 98.4 / 96.0) would be a more stable headline.
7. **ms/episode**: the timed loop includes the benchmark's own scoring (section 3). It is a single pass, so load spikes go straight into it; I saw one 2.7x spike in my own loop.
8. **Timing magnitudes in the committed run look load-affected for langchain-core and llama-index-core** (2.6-3.4x the reruns while contexel matched). Orderings were unaffected.
9. **Rounding and ties**: no rounding problems found.
   * Recall is a 100-episode percentage, so 1 point = 1 episode.
   * The strong signal ties heavily (target score 37-39, at most 39): the records scoring at or above the target have a median of 2 and a maximum of 183. The hand-written row's 7 strong misses fall in the 8 episodes with more than 24 such ties.
10. **Positive findings stated plainly:**
    * the dataset pin verifies;
    * all non-timing numbers reproduce bit-for-bit;
    * my independent metric code and my competitor wrappers give identical results;
    * determinism holds across hash seeds, including the rescore pipeline the suite does not test;
    * dependency counts reproduce;
    * the tokenizer and ISON tables reproduce exactly with tiktoken;
    * every README code-example output reproduces.

## 7. Ranked defects and proposed corrected text

1. **D1 (high) — proximity leakage behind the "fairest comparison" (README.md:128-130, README_PYPI.md:106-108, site/benchmarks.html:126-127).** Add: "On these episodes contexel's lead over it (100% vs 97%) comes from rescore's in-order proximity bonus. The episode queries are the target docstring's first words in their original order, which is exactly what that bonus rewards. With `proximity=False` contexel scores 95%. Over ten episode seeds contexel averages 99.5% and the term-overlap baseline 98.4%." Better still: build queries whose word order is independent of the target text, or report several seeds.
2. **D2 (high) — "1,500-token budget in 100% of episodes" is in estimator tokens (README_PYPI.md:102-103, README.md:122-123 and :131, site/index.html:89).**
   * Proposed PyPI text: "It holds a 1,500-token budget, counted with the default ~4-characters-per-token estimate, in 100% of episodes. Counted with tiktoken cl100k_base, the same contexts average about 1,630 tokens: use an exact tokenizer for hard limits."
   * Proposed README text: "**Compliance %** — did the final context fit the budget as the default estimator counts it?"
   * State also that any row which trims by summing record costs scores 100% by construction.
3. **D3 (medium) — site/stages.html:292 cites numbers that do not exist ("49.8 vs 44.4 ms over 10k records in RESULTS.md"), and the checker cannot see that page.**
   * Replace with: "Inactive overhead is a single ContextVar lookup per stage: in an audit run, a pipeline with tracing inactive took within about 3% of the same stages called directly over 10,000 records. Active tracing token-counts every stage boundary and is several times slower (RESULTS.md, section 3)."
   * Add `site/stages.html`, `site/architecture.html`, `site/getting-started.html` and `site/contract.html` to `publish.FILES`.
4. **D4 (medium) — empty contexts count as 100% useful and compliant (competitors.py:675-677).**
   * Score an empty context as 0% useful (or exclude it and report the count).
   * Disclose: "langchain-core returns an empty context in 31 of 100 episodes, because the first raw record alone exceeds the budget."
   * The langchain-core useful share becomes 85.1% over its non-empty contexts.
5. **D5 (medium) — "same under both signals" presented as evidence (README.md:125-126, COMPARISON.md:147, site/benchmarks.html:122-126, README_PYPI.md:103-104).** Replace with: "contexel's two recall columns are identical by construction: rescore replaces the tool's score, and the two signals differ only in that score (the hit lists are in the same order). This shows rescore does not depend on the tool's score; any row that ignores the score has equal columns."
6. **D6 (medium) — "Native ops ... computed ..., not typed" (README.md:112-116, site/benchmarks.html:102-103, COMPARISON.md "Operations" section).** Replace with: "Whether a step enters the library's own code is computed (`benchmarks/opcount.py`). Which steps each implementation has, and which operation each step serves, are written by hand in `benchmarks/competitors.py` (for example, toolz's row does not use `toolz.topk` to rank; with it toolz would count 3/6)."
7. **D7 (medium) — ms/episode definition (README.md:137, site/benchmarks.html:109).** Replace with: "ms/episode — mean wall time per episode for shaping plus the benchmark's own scoring of the result (one pass). For contexel the scoring is under 1% of it; for toolz and llama-index-core, whose contexts are 92x and 129x the budget, the scoring is most (toolz, 78%) or a third (llama-index-core, 30%) of it." Or time the shaping alone.
8. **D8 (medium-low) — "about 20 ms" import (README_PYPI.md:105, site/index.html:78).** Replace with: "an import of about 20 ms on an idle machine (the import statement in a fresh interpreter, median of 5, interpreter start-up excluded)". It doubled under load in this audit (39 ms), and the checker's 25% tolerance then fails.
9. **D9 (low-medium) — ms @28k attribution (README.md:116-119, site/benchmarks.html:97-100).** Add: "For langchain-core and llama-index-core most of this time is the benchmark converting every record into the library's message or node type; `trim_messages` itself takes about 20 ms." Also note that the contexel to langchain-core ratio ranged from 1.6x to 5.9x across runs.
10. **D10 (low) — "−29% on JSON-heavy records" (README.md:195, contexel/tokens.py:106).** Replace with: "−29% on the synthetic JSON sample (search-hit records with hexadecimal ids); −4% to −13% on the CodeSearchNet records of the comparison."
11. **D11 (low) — dead reference to a README section that does not exist, "How much does it cut?"** It appears in suites_report.py:86 (rendered into RESULTS.md:13), suites.py:15 and benchmarks/__init__.py:8. Point it to the README's benchmark section ("What the benchmark shows — and how to read it"), or drop it.
12. **D12 (low) — "Inactive tracing is the "zero cost" claim" (RESULTS.md section 3, site/benchmarks.html:67-69).** The suite measures inactive against active only. Add an untraced baseline (the stages called directly) to suite 3. My measurement: −0.3 to +3.2 ms on about 95 ms.
13. **D13 (low) — "Every number on this page is generated, or checked against the results" (site/benchmarks.html:41-44, README.md:94-97).** Add: "checked against the committed results, which CI does not regenerate". "~30 MB" is not checked.
14. **D14 (low) — "duplicates are real (the same function matching several queries)" (COMPARISON.md:18-19, README.md:85-86).** 7 of the 13,921 records removed are distinct functions from different repositories that share `(path, symbol)`, for example `setup.py:read` from 4 repositories. Add "(all but 7 of the 13,921)", or dedupe on repository, path and symbol.
15. **D15 (low) — site/benchmarks.html:169-171, "Full recall here means the ambiguity clusters resolved once exact-word evidence was used".** Exact-word evidence alone gives 95%. Replace with: "... once exact-word evidence and the in-order proximity bonus were used."
16. **D16 (low) — "*because they do the most work per record*" (README_PYPI.md:109-110).** The overlap scorer does less work and takes as long; the cause is not measured. Use: "the two rows that score each record from the query".
17. **D17 (low) — unmeasured assertions inside the measured report (COMPARISON.md):** "re-derived, slightly differently, every run" and "not a scoring defect". Label them as claims, or remove them.
18. **D18 (low) — suite 6 JSON baseline.** The JSON baseline is contexel's spaced canonical JSON. Add a compact-JSON row: 40.1 tokens/record against ISON's 33.5 and spaced JSON's 50.0.
19. **D19 (low, reproducibility) — tokenizer-accuracy samples include live files** (contexel/stages.py, reference_agent/tools.py, the-context-contract.md). Any edit to them changes RESULTS.json; only the README copy is frozen.
20. **D20 (info) — "Eight pipeline stages" (site/index.html:79, README_PYPI.md:21).** This leaves out the payload stages (`split` is used inside `pipeline` in the README).

## 8. Numbers and claims that nothing checks (drift risk)

`publish.FILES` covers only README.md, README_PYPI.md, site/index.html and site/benchmarks.html. The unit scan ignores MB, seconds, numbers written in words, and qualitative sentences that are not registered. Not checked by anything:

* **site/stages.html** (already wrong, S1); site/stages.html:102 and :160 "128,000"; site/architecture.html:81 and :150; site/getting-started.html:46-47 ("Node >= 18", "net8.0").
* **Downloads and cross-references:** README.md:90 and site/benchmarks.html:74 "~30 MB"; README.md:664 "2026-07".
* **README text-splitting and normalization numbers:** README.md:380-386 ("440 MB", "140 MB", "540 MB", "0.4 to 2 seconds", "50,000-character", "4,000 chunks", "0.6 to 2 seconds"); README.md:472 "128,000".
* **The determinism sentences** (README.md:76-80, README_PYPI.md:120-123, site/index.html:61-63). They are not tied to the RESULTS.json booleans; only the benchmarks.html suite1 block is generated from them.
* **README.md "six operations"** (only the PyPI sentence is registered) and "about four characters per token".
* **Code docstrings:** contexel/tokens.py:106 "~29%".
* **The static prose in the render templates** (competitors.py `render_report`, suites_report.py `render`): "All rows are microseconds per record", "not a scoring defect", "re-derived ... every run", "How much does it cut?". The re-render check proves only that the .md matches its template, not that the static text is true.
* **Whether the published timings can be reproduced:** the checker compares prose with the committed JSON only, CI never regenerates it, and the import claim's 25% tolerance passes or fails depending on machine load.

## 9. What I could not verify, and why

* **Whether a fresh download reproduces the pinned JSONL digest:** no network allowed. The plan document (docs/plans/foundation-hardening.md:120) also records this as not verified. If the Hugging Face export changed, a new user cannot reproduce at all: `fetch()` refuses the file.
* **The "~30 MB" download size:** the parquet file is not present; the derived JSONL is 39.2 MB.
* **Cross-machine byte-identity of the seeded synthetic datasets:** one machine only; verified across interpreters and runs here.
* **TypeScript and C# figures** (140 MB, 540 MB, Node >= 18, net8.0) and the "not run" table rows (haystack, EmbeddingsRedundantFilter, LLMLingua/ColBERT): these are statements about documentation, and nothing here ran them.
* **"context-engineering-toolkit not on PyPI":** needs the network.
* **Whether seed 11 was fixed before results were seen:** history not examined. It is the documented default ("The defaults reproduce the original episodes exactly").
* **The machine state during the committed run:** the langchain-core and llama-index-core timings suggest uneven load, but this cannot be proven after the fact.
