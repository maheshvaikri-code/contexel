# Foundation hardening, Slice 2: G5 QA report

**Branch:** `feat/hardening-s2-errors-strict` · **Role:** QA Engineer (fresh context, verification by execution) · **Date:** 2026-11-20
**Written for:** the maintainer and later reviewers who need to know how the slice was tested and which test gaps the mutation runs found.

Two passes: pass 1 on `c9e1370` (PASS with test gaps), pass 2 on `b85f95b` after the security fixes (returned for six one-line test gaps, since closed in `a0f9152`, `dc045a8`, `8f0623d`).

## Method

Every mutant was applied to a fresh `git archive` extraction and confirmed applied (a diff against the pristine tree; a mutant that did not apply proves nothing); patches were CRLF-aware; Python ran with `python -B`; TypeScript was recompiled per mutant; C# ran `dotnet test` per mutant from an empty `bin`/`obj`, under a wall-clock cap and a memory watchdog (a removed cycle guard can allocate without bound; one run reached 16.8 GB in pass 1). A killed mutant that only "died" by hanging is reported as a gap (the suite must fail, not hang).

## Pass 1 (`c9e1370`)

- **Suites** in a clean copy: Python 398, TypeScript 300 (`tsc` clean), C# 247 (0 warnings). Vectors regenerate byte-identically under Python 3.12 and 3.9; LF-only; 65 cases, 28 error cases.
- **AC 9 independently:** `main`'s own suites against the new library: Python 193 of 194 pass (the carved-out envelope-guard example), TypeScript 71 of 73 (carve-outs a and d), C# 68 of 71 (carve-outs b twice and a); legacy vector sections differ only at `edges.allowlist_bool_int`.
- **Mutation:** Python 72 (64 killed), TypeScript 41 (40), C# 42 (38). 13 non-equivalent survivors, listed below with the test each needed.
- **Black-box probes:** about 280 calls through the public API across the three languages (empty/None items, tuples, huge and deep and cyclic values, unicode separators, bool/int/float/-0.0/NaN allowlist values, every `allowed` shape, zero/negative/huge budgets, strict on/off with pipeline/shaped/trace, nested and threaded strict).
- **README examples:** all six "Errors and strict mode" examples run as a user would (fresh interpreter on 3.12 and 3.9; ESM project consuming the built package with strict `tsc`; a console project): output identical to the README.
- **Error experience:** 18 typical misuse calls give the same code, stage and param in all three languages and a message a developer can act on (one gap: the combined-regex error on Python 3.12 did not name the culprit pattern, removed by the per-pattern fix).

Survivors and the test each needed: dict self-cycle guard untested (the mutant hangs); strict-before-trace test covered only `select` (Python and C#: parametrized over all eight stages); `shaped` dropping `strict` for a list of stages; a bad call under strict misdiagnosed as a shape error; the case-key check in `build_cases`; C# `Pipeline.Run` strict leaking into the caller; C# scope double-dispose; TypeScript error not naming the pattern (V8's own message hid it). New findings: re-entering one Python `strict()` object left strict on (fixed); `dedupe(key=[])` collapses all records, pre-existing, all three languages (follow-up); `strict="no"` turned strict on in Python but not TypeScript (fixed: must be a bool); TypeScript ignores unknown option keys, pre-existing (follow-up).

## Pass 2 (`b85f95b`)

- **Suites:** Python 467, TypeScript 310 (`tsc` clean), C# 277 (0 warnings); vectors 70 cases, 31 error cases, regenerate byte-identically under 3.12 and 3.9.
- **Mutation of the code changed since pass 1:** Python 46 (43 killed), TypeScript 31 (29), C# 26 (25), plus 15 vector-expectation mutants (all killed in all three languages). Every pass-1 survivor was killed. Bounded cycle tests with the guard removed now fail in about 10 s instead of hanging (Python list and dict, C# dict and list).
- **Six survivors, all one-line test gaps, none equivalent:**

| Mutant | Why it matters | Test added |
|---|---|---|
| Python `isinstance(r, Mapping)` to `dict` | non-dict `Mapping` items must stay accepted | `MappingProxyType`, `OrderedDict`, custom `Mapping` items scanned (drop and flag) |
| Python replace mode uses `compiled[:1]` | a second replacement pattern silently ignored (fail-open) | three-pattern `replace_patterns=True` test |
| Python / TypeScript / C# `check_query` accepts bool elements | `rescore(r, [True])` would score the term "True" | `[True]` and `["x", False]` rejected in all three |
| TypeScript user pattern flag `i` to `gi` | stateful `.test()`: a second matching record is kept (fail-open) | two-record test with a user pattern |

- **Black-box probes:** more than 200 executed calls; every kind of non-mapping item in each language, custom patterns of every shape, `rescore` query elements, `pipeline`/`shaped` strict values, strict re-entry, C# scopes. The three ports agree on everything each can represent, except the TypeScript non-plain-object items (fixed).
- **One false sentence found in the docs and corrected:** the READMEs said JavaScript has no inline flags; Node 24 accepts scoped modifiers such as `(?i:foo)` (the global form `(?i)x` is invalid), so validity depends on the engine version.
- **Minor, applied:** the vector `quarantine/backreferences_do_not_cross_patterns` gained a record `{"snippet": "evil-x"}` (kept) so a TypeScript port that joins patterns fails the shared vector (an unmatched backreference matches empty in JavaScript).

## Final state (controller re-verification at the end of the slice)

Python 475 passed, TypeScript 313 of 313 with `tsc` clean, C# 279 passed with 0 warnings; `parity/vectors.json` 70 cases (31 error cases), LF-only, byte-stable on regeneration (also under Python 3.9). Not run anywhere: Linux and macOS CI, Python 3.10, Node 18 and 20. The `tests/test_doctrine_*` tooling tests are git-ignored and unrelated; one of them (`test_doctrine_dashboard`) fails with or without this slice.
