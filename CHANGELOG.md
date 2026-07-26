# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/). Versions follow
`z.y.x` — Mega. Major. minor/patch — and every commit bumps the version.

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
