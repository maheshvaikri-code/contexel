# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/). Versions follow
`z.y.x` — Mega. Major. minor/patch — and every commit bumps the version.

## [0.1.17] — 2026-07-28

### Added — C# parity package (`csharp/`, NuGet: `Contexel`)
- A C# port of the full public surface for .NET agents (net8.0, zero
  runtime dependencies): all eight stages plus `Merge`,
  `Pipeline`/`Stage` with policy fingerprints, `Shaped` (async tools
  awaited, then shaped), `Trace`/`Audit`, and `Tokens` with code-point
  counting, canonical Python-`json` serialization, and
  `AsyncLocal`-scoped per-tenant overrides. Same golden-vector contract
  (ADR-002); because .NET preserves the int/float distinction, the C#
  parity envelope is *stricter* than the TS one — a JSON `1.0`
  serializes as `"1.0"` exactly like Python, and a no-match rescore
  keeps Python's int `0`. CI runs the C# suite against
  canon-regenerated vectors on Linux/Windows/macOS; the release
  pipeline gains tag-guarded `nuget-publish` + 3-OS `nuget-smoke` jobs
  using NuGet Trusted Publishing (OIDC via `NuGet/login` — no
  long-lived secret; all three registries are now token-free or
  short-lived-token only).

### Fixed
- **TS `rescore(match: "substring")` counted overlapping occurrences**
  where Python's `str.count` is non-overlapping (`"aaaa"` contains two
  `"aa"`, not three) — scores diverged on self-bordered terms over
  repeated text, changing ranking. Found by the C# port's G4 review; the
  substring path had no golden vector, which is why two prior TS reviews
  missed it. Fixed in both ports and locked by a new
  `rescore_substring` vector.

### Changed
- **`quarantine(patterns=...)` now EXTENDS the built-in marker list**
  instead of replacing it (user field report: passing domain-specific
  markers silently disabled "ignore all previous instructions" detection —
  the control looked configured and was weaker than the default).
  Replacement is an explicit opt-in via `replace_patterns=True`
  (TS: `replacePatterns`), and an empty replacement list raises instead of
  matching nothing. Anyone relying on the old replace semantics gets
  strictly MORE detection until they opt out — the fail-safe direction.
  `patterns` also accepts a bare string as one pattern, and empty
  fragments raise (an empty regex alternative silently matches EVERY
  record). Docs gained a regex-pitfall note (`\b\.env\b` can never match;
  use `(^|[\s"'([/])\.env\b` — the `/` covers `config/.env` paths).

## [0.1.16] — 2026-07-28

### Added — TypeScript parity package (`ts/`, npm: `contexel`)
- A TypeScript port of the full public surface for TS/JS agents: all eight
  stages plus `merge`, `pipeline`/`stage` composition with policy
  fingerprints, `shaped` (async tools awaited, then shaped), `trace`/
  `audit`, and `tokens` with code-point counting, canonical Python-`json`
  serialization, and `AsyncLocalStorage`-scoped per-tenant overrides.
  Zero runtime dependencies, ESM, Node >= 18, strict TypeScript with
  bundled declarations.
- **Cross-language parity is enforced, not asserted:**
  `parity/generate_vectors.py` runs every stage and a composed
  8-stage contract through the canonical Python implementation and writes
  `parity/vectors.json`; the TS suite asserts byte-parity against those
  golden vectors (18 tests: per-stage outputs, contract output, audit
  drops, serializer string equality, token counts). Deliberate boundaries
  (JS float collapse `1.0`→`"1"`, Unicode word classes, language-local
  fingerprints) are recorded in `docs/adr/001-typescript-parity.md`.
- README/README_PYPI: npm install route and a "TypeScript parity" section.
- Release automation for npm: one `v*` tag now ships BOTH packages.
  `release.yml` gates each publish on the full suites passing on Linux,
  Windows, and macOS (both artifacts are pure/platform-independent — OS
  coverage is enforced by test gates, not per-OS builds), requires
  `pyproject.toml` and `ts/package.json` to equal the tag so the
  registries cannot drift, publishes npm with provenance attestations
  (PyPI stays on Trusted Publishing/OIDC), and smoke-tests both published
  artifacts on all three OSes. CI gains Windows/macOS legs and runs the
  parity job on all three OSes.
- `trim_to_budget(..., min_records=0)` (Python and TS): guards the
  silent-failure edge where a too-small budget returns `[]`,
  indistinguishable from "nothing matched" — the first `min_records`
  (best-ranked) records are kept even over budget; the overrun stays
  visible in the trace/audit. Default unchanged. (User field report.)
- `fields` params (`select`, `quarantine`, `rescore`) now accept a bare
  string as ONE field name, mirroring `dedupe(key=str)` — previously a
  string was silently iterated as characters. Lists and tuples were always
  accepted (`Sequence[str]`); JSON arrays need no coercion.

### Fixed
- `dedupe`: `{}` and `[]` no longer share a fingerprint — container
  fingerprints are now type-tagged (`dict` vs sequence). `[1, 2]` and
  `(1, 2)` still dedupe as the same JSON data.
- TS parity hardening after adversarial review (all golden-vector
  enforced): Python-`str()` replication for non-string field values in
  `rescore`/`quarantine` (a nested injection payload is caught in both
  languages); Python float repr thresholds in serialization (`1e-05`, not
  `0.00001`); CPython `round()` half-to-even in audit/report/rescore;
  stable descending sort for callable `rank` keys; nested `tokens.scoped`
  composition; own-property semantics everywhere (`Object.hasOwn` +
  define — a `"__proto__"` key is ordinary data, inherited properties are
  never read); code-point match positions, key sort, and string
  comparison; Python `rstrip()` whitespace set in `truncate_field`;
  Python-equality `allowlist` membership (`True == 1`, missing field reads
  as `None`, unhashable fails closed).

## [0.1.15] — 2026-07-26

### Added — toward a governed "context shaping plane" (readiness audit, gaps 2/3/4/5)
- `@shaped` now wraps **async** tools: a coroutine function is awaited and
  its records shaped, instead of `TypeError: 'coroutine' object is not
  iterable`.
- `tokens.scoped(tokenizer=..., serializer=...)` — context-local token
  accounting for concurrent tenants: isolates async tasks and
  context-copying threads (bare threads fall back to the process default);
  resolution: explicit arg → scoped → process default → built-in.
- `tokens.tiktoken_tokenizer(encoding=..., model=...)` and
  `use_tiktoken(model=...)` — model-specific encodings, exact where
  tiktoken covers the model (other providers plug their own counter); docs
  now state hard token limits require an exact tokenizer (the estimator is
  for soft budgeting only).
- `pipeline(...).fingerprint` — a stable policy hash of stage names and
  bound parameters, recorded into any active trace.
- `trace(id_field=...)` + `Trace.audit()` — the governance record: policy
  fingerprints, per-stage dropped record IDs (stage = removal reason),
  token movement.
- **Injection controls (gap 6, now implemented, not just documented):**
  `allowlist(records, field, allowed)` — a fail-closed provenance gate
  (the strong control; apply before relevance logic) — and
  `quarantine(records, fields=..., action="drop"|"flag")` — a
  deterministic tripwire for literal injection markers ("ignore all
  previous instructions", role resets, system tags). Both traced and
  audited; honestly scoped: paraphrase passes the tripwire, and neither is
  a semantic guardrail. The audit's probe (an adversarial record
  outranking the legitimate one) is now a regression test.

### Changed
- Benchmarks re-run after the plane changes: **shaped outputs are
  byte-identical** (determinism hash unchanged, `6c9fd99fc2f01c4b`) and
  every outcome metric (recall/compliance/fill/useful) is unchanged for all
  implementations. Cost of the tenant-isolation plumbing: two ContextVar
  lookups per `tokens.count()` ≈ +2.4 µs/record on token-counting hot paths
  — ~8–10% on the 28k canonical task after correcting for machine drift
  (59 → ~68 ms; the hand-written baseline drifted +7% in the same session).
  Accepted: isolation is worth microseconds; all rows remain noise next to
  a model call.
- Release workflow publishes via **PyPI Trusted Publishing (OIDC) with
  provenance attestations** — no long-lived token (gap 7). One-time PyPI
  publisher registration required before the next tag; see the workflow
  header.
- Threat model stated in README / PyPI readme / site (gap 6): shaping is
  not an injection defense — the new boundary controls make hostile
  records excluded or visible, but content authentication belongs
  upstream; records are data, never instructions.
- Comparison labels made consistent: the at-a-glance "Native ops" column
  now uses the /6 denominator (the outcome task's six operations) for
  every row, and the capability matrix gains the missing
  `rescore(lexical)` column. Labels only — measurements retained from the
  canonical run; README/site quote that run (contexel 69 ms @28k, 15.5
  ms/episode, sub-20 ms import).

## [0.1.14] — 2026-07-26

### Fixed
- Pages workflow: first deploy failed at `configure-pages` because the
  repository had no Pages site yet; `enablement: true` now creates it on
  first run (implements the opt-in recorded in `docs/brief.md`).
- README PyPI badge appeared broken on GitHub: the camo image proxy had
  cached the pre-publish "package not found" response. Badge URL changed
  (query form, `?label=pypi`) so camo fetches fresh; shields.io verified
  serving `pypi: v0.1.13`. (Docs-only fix — no version bump, per policy.)
- `dedupe`: equal sets could fail to dedupe — set iteration order
  (insertion-history and hash-seed dependent) leaked into the fallback
  fingerprint. Sets/frozensets now fingerprint as sorted, type-qualified
  tuples; deterministic across interpreters and seeds (suite verified on
  PYTHONHASHSEED 0/1/2/3/42). Found by CI on Python 3.10; the same bug
  explains the previously unexplained local one-off failure.

### Changed
- Release-day cleanup after v0.1.13 shipped to PyPI: live PyPI version
  badge, `pip install contexel` restored as the primary install in the
  README and docs site (in-flight notes removed), `README_PYPI.md` install
  section live, release record filed at `docs/releases/v0.1.13.md` with
  the clean-venv post-publish verification output.

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
