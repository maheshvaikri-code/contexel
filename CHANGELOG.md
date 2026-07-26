# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/). Versions follow
`z.y.x` — Mega. Major. minor/patch — and every commit bumps the version.

## [0.1.13] — 2026-07-26

### Changed
- Site getting-started now leads with `pip install contexel` (annotated as
  in-flight until the first release lands), with the from-source block kept
  for the benchmark extras; `README_PYPI.md` gains its missing Install
  section.

## [0.1.12] — 2026-07-26

### Added
- `.github/workflows/release.yml` — tag-gated PyPI publish (a human-created
  `v*` tag or manual dispatch is the release decision): re-runs the full
  suite on the exact tagged commit, enforces tag == `pyproject` version,
  builds + `twine check`s, publishes via `pypa/gh-action-pypi-publish`
  (pinned by commit SHA) using the `PYPI_TOKEN` **secret**, then a clean
  post-publish job installs the published artifact from PyPI and runs the
  quickstart against it.

## [0.1.11] — 2026-07-26

### Added
- Docs site under `site/` (GitHub Pages-ready, wiki-style, bright theme
  with an AA-checked dark variant, fully self-contained — no CDN): home,
  interactive architecture (clickable pipeline explorer + live budget-slider
  demo), getting started, per-stage reference, benchmarks, and the context-
  contract thesis. Root `architecture.html` now redirects there (the old
  dark, CDN-font page is retired).
- `README_PYPI.md` — the PyPI-facing narrative with absolute URLs;
  `pyproject.toml` now points `readme` at it and adds Documentation/
  Changelog/Issues URLs. Repo README links the docs site.
- `.github/workflows/pages.yml` — opt-in Pages publish (recorded in
  `docs/brief.md`): path-scoped to `site/`, actions pinned by full SHA,
  fail-closed on `tools/site_check.py` (link/asset/CDN/secret checks over
  HTML and CSS) before any deploy.
- Doctrine gate artifacts: `docs/brief.md`, `docs/plans/`, `docs/reviews/`,
  `docs/qa/` for this task (G2–G5; 15 review findings, all resolved).

### Changed
- Bundled site logo optimized 197 KB → 9.5 KB.
- Package builds verified: `python -m build` + `twine check` PASSED for
  sdist and wheel. Publishing to PyPI and enabling Pages remain manual,
  human-approved actions.

## [0.1.10] — 2026-07-26

### Changed
- README rewritten mechanics-first: logo + badges header; a "what it does,
  and exactly how" stage table (each stage's precise algorithm); a "what the
  benchmark shows — and how to read it" section that explains every column
  and states plainly that contexel is the slowest budget-compliant row
  *because* it does the most work; "where it is used" (five placements, each
  linked to its runnable example) and "how to use it". Verified by a
  three-judge adversarial review (accuracy vs the committed tables and code,
  overclaim hunting, newcomer usability) — all eight findings fixed,
  including three overclaims and a quickstart syntax error.
- Install instructions switched to git + `pip install -e .` (the package is
  not yet on PyPI — the old instructions failed); PyPI badge replaced by a
  version badge until a release ships.

### Added
- `benchmarks` extra (`pip install -e ".[benchmarks]"`) covering everything
  the benchmark suites import: tiktoken, requests, pyarrow, toolz,
  langchain-core, llama-index-core, packaging.

## [0.1.9] — 2026-07-26

### Changed
- At-a-glance comparison table gains a `ms/episode` column alongside
  `ms @28k` and `Import ms`, with the framing made explicit: contexel's
  per-episode time is the highest of the budget-compliant rows because it
  does the most — deriving relevance from ~1 KB of evidence per record on
  top of the five shaping stages; every cheaper row does less.

## [0.1.8] — 2026-07-26

### Added
- `rescore(..., match="word")` (new default): exact word-occurrence matching
  the way BM25/Lucene tokenize — `value` no longer matches `values`, and
  underscores are boundaries so snake_case splits. Implemented as one
  boundary-guarded alternation regex scanned per record at C speed.
  `match="substring"` keeps the previous behavior.

### Changed
- The comparison's standard contexel contract now includes `rescore`
  (relevance derived from the query, never trusted from the tool); the
  separate "contexel + rescore" row is gone. Outcome benchmark: **100%
  recall under both retrieval signals**, 100% budget compliance, 100%
  useful-token share. The report also states the ceiling no shaper escapes:
  when a query legitimately describes more records than the budget holds,
  some valid record must be cut — semantic or not.

## [0.1.7] — 2026-07-26

### Added
- `rescore(..., proximity=True)`: consecutive query terms co-occurring in
  order within an 80-char window earn a bonus, breaking lexical ties in
  favor of the record the query was phrased from. Outcome recall rises from
  94% to 98% under both retrieval signals.

### Changed (performance; outputs identical)
- `truncate_field`: closed-form prefix cut when the built-in heuristic
  tokenizer is in effect (`ceil(len/4)` is invertible) — 2.9x faster at
  100k records; the generic binary search remains for custom tokenizers.
- `dedupe`: type-qualified hashable fingerprints with a canonical-JSON
  fallback for unhashable values; JSON semantics preserved (1, 1.0, True,
  "1" stay distinct).
- `rescore`: single-pass term-frequency scan (df derived, not rescanned).
- Net: the 28k-record canonical comparison task runs in 60 ms (was 109).

## [0.1.6] — 2026-07-26

### Added
- `rescore(records, query, fields=..., into="score")` — deterministic
  lexical relevance computed within the batch (BM25-style: per-term IDF x
  saturating term frequency), so `rank` no longer has to trust the search
  tool's score. In the outcome benchmark this lifts weak-signal recall from
  32% to 94% (identical under both signals) at unchanged 100% budget
  compliance, leaving ~6 points as the measured cost of true semantic
  (paraphrase/synonym) mismatch.

## [0.1.5] — 2026-07-26

### Added
- "At a glance" section in `COMPARISON.md` clubbing the three benchmark
  tables — native operations, 28k-record timing, ground-truth outcomes
  (recall, compliance, fill, useful share), and footprint — into one row
  per implementation.

## [0.1.4] — 2026-07-26

### Added
- Ground-truth outcome benchmark in the comparison (`COMPARISON.md` → "What
  each achieves natively"): 100 CodeSearchNet episodes with a known needed
  record, each library restricted to its own operations, scored on
  recall@budget under two retrieval signals, budget compliance, context
  fill, and useful-token share. Key results: contexel (and the equivalent
  hand-written policy) is the only configuration with recall + compliance +
  all-useful context together (93% recall, strong signal); a weak retrieval
  signal drops that to 32% — the measured cost of conceding semantic
  reranking; competitors reach 100% recall only at 92-129x budget, or hold
  the budget while filling it with bloat (30% recall).

## [0.1.3] — 2026-07-26

### Changed
- Comparative benchmark scaled to the full CodeSearchNet python/test split
  (22,176 rows via the Hugging Face parquet export, replacing the 2,000-row
  paged sample) and a 16-query workload — 28,047 tool-output records with
  real duplicates. At this scale contexel's wall time sits at parity with
  langchain-core and ahead of llama-index-core's node round-trip.

## [0.1.2] — 2026-07-26

### Added
- Comparative benchmark vs prior art (`python -m benchmarks.competitors` →
  `benchmarks/COMPARISON.md`): capability matrix + timed canonical task +
  footprint (import time, dependency closure) for toolz, langchain-core,
  llama-index-core, and a hand-written baseline, on real CodeSearchNet
  records fetched via the Hugging Face datasets-server
  (`benchmarks/fetch_dataset.py`, cached and gitignored).
- README: link the comparison; note `context-engineering-toolkit` was not on
  PyPI as of 2026-07 (prior-art claim did not verify).

## [0.1.1] — 2026-07-26

### Added
- Pluggable serialization for token counting: `tokens.set_serializer(fn)` and
  `tokens.serialize(value)`. Budgets are encoding-relative — plug in the
  encoding your boundary actually emits (e.g. an ISON table) so
  `trim_to_budget` prices records in that encoding. Default remains
  canonical JSON; strings always bypass the serializer.
- `examples/ison_boundary.py` — the shape-then-encode pattern with ISON.
- Benchmark suites (`python -m benchmarks`): determinism, budget tightness,
  speed, tokenizer accuracy, reduction characterization, encoding pairing.

## [0.1.0] — 2026-06-07

### Added
- Deterministic context-economy stages: `select`, `dedupe`, `rank`,
  `truncate_field`, `trim_to_budget`, `merge`.
- Pluggable token counting (`tokens`) — dependency-free heuristic by default,
  optional `tiktoken` backend via the `accurate` extra.
- Opt-in, zero-cost `trace()` for per-stage observability.
- In-language composition: `pipeline` and `stage`.
- `@shaped` decorator for applying a pipeline at the tool boundary.
- Reference agent (`reference_agent/`): a runnable code-execution agent using
  contexel as the deterministic context-economy layer at the tool -> context
  boundary, with scripted and live (Anthropic) model clients.
