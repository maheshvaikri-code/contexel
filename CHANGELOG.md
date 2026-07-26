# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/). Versions follow
`z.y.x` — Mega. Major. minor/patch — and every commit bumps the version.

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
