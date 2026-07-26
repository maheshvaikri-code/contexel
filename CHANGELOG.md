# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project
adheres to [Semantic Versioning](https://semver.org/).

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
