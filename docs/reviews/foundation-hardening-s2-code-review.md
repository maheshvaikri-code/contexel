# Foundation hardening, Slice 2: G4 code review

**Branch:** `feat/hardening-s2-errors-strict` · **Role:** Code Reviewer (fresh context, adversarial) · **Date:** 2026-11-20
**Written for:** the maintainer and later reviewers who need to know what was reviewed, what was found and how each finding was resolved.

Per-task reviews (Tasks 1 to 10, an independent reviewer per task, severity-ranked) are in [the subagent-driven ledger](foundation-hardening-s2-sdd-ledger.md). This file covers the whole-branch review and its re-gate.

## Round 1 (`22f82db..c9e1370`): REQUEST-CHANGES

Method: acceptance-criteria walk (brief AC 1 to 9, 34), cross-language parity audit, a 7,931-call Python differential battery old versus new (all eight stages, `merge`, `pipeline` with `trace`/audit, `shaped`, 21 pipeline fingerprints, seeded random records), 44 cross-language probes (Python 3.12 and 3.9, TypeScript old and new, a C# console against the old and new library), 25 Python and 10 TypeScript mutants (24 and 10 killed), pre-slice tests run against the new library (Python: 1 failure, the carved-out envelope-guard example; confirmed independently by QA for all three languages).

**Blocker F1:** Python `quarantine` in default mode kept non-mapping items (see the security review, S-1). Reproduced by the controller across all ten stages: only `quarantine` regressed.

| # | Severity | Finding | Resolution |
|---|---|---|---|
| F1 | Blocker | quarantine fails open on non-mapping items (Python regression; TypeScript pre-existing) | Fixed: always raises `input.not_mapping` in all three ports; vectors added |
| F2 | Major | C# `HashSet`/`SortedSet` for `fields`/`key`/`patterns`/`query` now throws; unlisted | Documented (changelog Behavior changes) |
| F3 | Major | C# does not deep-scan `System.Text.Json` `JsonElement` values (default of `Deserialize<Dictionary<string, object?>>`); pre-existing, AC 2 promises any depth | Documented as a known limitation (human decision), follow-up planned |
| F4 | Minor | Python canon had no test of dict-key scan order | Shared vector `quarantine/dict_keys_are_scanned_in_sorted_order` |
| F5 | Minor | `query` elements unvalidated (`rescore(q=[None])`: "none" in Python/C#, "null" in TypeScript) | All three reject non-string elements |
| F6 | Minor | C# `Allowlist(r, "f", null)` is now ambiguous (CS0121) | Documented under Compatibility |
| F7 | Minor | Undocumented regex dialect differences (`\Z`, Kelvin sign, joined backreferences) | Joined-regex part fixed in code; the rest documented |
| F8 | Minor | New public surface undocumented and uneven (`isStrict`, `ERROR_CODES`, `Strict.IsActive`, `ContexelException.Codes`, `Pipeline.IsStrict`) | Documented per README |
| F9-F13 | Nit | `quarantine` docstring said "string leaves"; TypeScript message for a Promise stage output; C# subclasses enforce the code prefix but Python/TypeScript do not; strict around a `yield`; item index only in the message | Docstring fixed; strict-around-`yield` documented; rest left (nits) |

Parked items adjudicated: P12 fix now (done); P23/P35 follow-up plus docs (done); P14 accept (re-expanding shared structure brings back exponential blow-up: a 2^22 diamond took 2.34 s before and 0.000 s after); P15, P16, P18, P36, P37 follow-up; P2 and P4 fix now (done).

## Round 2 (`c9e1370..b85f95b`): APPROVE WITH CONDITIONS

Blocker resolved; no new Critical or Important defect. Evidence: 16,500 Python, 13,500 TypeScript and 3,000 C# differential calls old versus new; every strict-off difference falls under a listed behavior change and **fingerprints and trace reports did not change**; 29 mutants (28 killed; the survivor is N6 below); four conflicting pre-existing assertions replaced because the behavior they pinned (the "cannot be combined" union error) no longer exists, each replaced by a test of what is now true, none weakened. The `ctypes` bounded-thread test helper (Python) was judged acceptable (stable since 3.7, runs only after a timeout, PyPy lacks `ctypes.pythonapi`; subprocess is the robust alternative).

Conditions and their resolution:

| # | Condition | Resolution |
|---|---|---|
| N1 | One Python `strict()` object shared across asyncio tasks or threads fails (token stack lives on the object) | Documented: call `strict()` per use (a per-instance `ContextVar` would leak) |
| N2 | TypeScript non-plain-object items kept by `quarantine` | Fixed (`dc045a8`) |
| N3 | Python `repr()` scan: applies to top-level values, raises raw exceptions from `__repr__`, costs on non-str leaves | `repr` skipped for exact int/float/bool/None (`a0f9152`); effects documented |
| N4 | C# out-of-order scope disposal leaves strict on | Documented (use `using`) |
| N5 | Docs: per-pattern matching can also drop fewer records; TypeScript legacy octal `\1` | Documented (`299099d`) |
| N6 | Test gap: TypeScript user-pattern `gi` mutant survives | Test added (`dc045a8`) |
| N7 | Duplicate private `_kind` helper | One definition (`a0f9152`) |
| N8 | C# `Check.Query` enumerates a lazy sequence twice (one-shot sequence arrives empty) | Fixed: materialized once (`8f0623d`) |
| N9 | C# runner converts any non-object item to null | Restricted to scalars and null (`8f0623d`) |

## Acceptance criteria at HEAD

AC 1 bare string is one value: met. AC 2 nested values at any depth: met in Python and TypeScript; C# for ordinary CLR values (`JsonElement` documented). AC 3 `fields=[]`: met. AC 4 bad regex named: met. AC 5 flag over `into`: met. AC 5a bool is not a number: met. AC 6 error hierarchy: met (pickling verified on 3.9 and 3.12). AC 7 configuration validation: met. AC 8 strict shape errors: met (item index in the message). AC 9 strict-off byte identity: met, proved by running `main`'s own test suites against the new library (Python 1 failure, TypeScript 2, C# 3: exactly the carve-outs) and by the differential batteries. AC 34 changes documented: met after the docs rounds.
