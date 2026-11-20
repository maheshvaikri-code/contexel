# Project/Task Brief — Foundation hardening (sub-project 1 of 4)
<!-- G0 artifact. Part of the "context excellence for all agents" programme. -->

**Date:** 2026-11-19 · **Class:** L (public API change across three language
ports; new stages; behavior changes to security controls) · **Requested by:**
human ("make it a dependable library for context excellence for agents, not
just coding agents, throughout agent use")

**Programme:** 1 Foundation hardening (this brief) → 2 Conversation stages →
3 Context assembler → 4 Presets, evidence, docs. Order and decomposition
approved by the human 2026-11-19.

## Problem

contexel's promise is that the step turning tool output into model context is
deterministic, reviewable and auditable. Today that promise is stronger in the
README than in the code and the evidence:

- Two controls sold as security gates are weaker than configured (verified by
  running them on 2026-11-19): `allowlist(allowed="github")` builds a set of
  characters; `quarantine` misses a phrase inside a nested value containing a
  newline, is a silent no-op with `fields=[]`, and leaks a raw `re.error`.
- Misconfiguration and malformed input fail silently or with accidental
  exceptions: `rescore(match="stem")` quietly runs substring mode;
  `select("path", ["x"])` returns `[{}, {}, {}, {}]`; `shaped` on a tool that
  returns a string returns garbage.
- The audit trail can be wrong: trace under-reports dropped ids when any
  survivor lacks the id field; two different policies (different set contents,
  nested pipelines, tiktoken encodings) share one fingerprint.
- Determinism and invariants are asserted in docs but not enforced in CI: no
  test varies `PYTHONHASHSEED`; input immutability is tested for 2 of 9
  stages; there is no committed property/fuzz test; the parity vectors store
  expected outputs only, so stage arguments are hand-copied into three test
  files and can drift.
- Only list-of-mapping payloads are supported, which excludes the log text,
  web pages and plain strings that non-coding agents mostly receive.
- Exact-word relevance scoring cannot match parse/parsing, and the published
  benchmark cannot show that cost because its queries are the target's own
  words and its hand-written baseline has no scorer.

Who hurts: anyone relying on contexel as a governed context boundary (the
stated target); the author's credibility when the claims are checked. Why now:
the programme extends contexel to whole-prompt assembly, which is only sound
on a foundation whose guarantees are enforced.

## Scope

### In (workstreams; vertical slices are proposed at G2)

**A. Security controls fixed in place** (decision: Hybrid)
`allowlist` and `quarantine` stop being weaker than configured.

**B. Typed errors and validation** (decision: Hybrid)
Configuration errors always raise a typed error. Data-shape errors (non-list
input, non-mapping items) raise a typed error only in an opt-in strict mode.
Default behavior for inputs that work today is byte-identical.

**C. Non-record payload support** (decision: Chunk + adapt)
New stage family `split`, `as_records`, `join` so text and plain items become
records and back; every existing stage then applies unchanged.

**D. Opt-in stemming in `rescore`** (decision: small built-in stemmer)
`match="stem"`; default `match="word"` unchanged.

**E. Enforced determinism and invariants**
Hash-seed test in CI; committed generative property tests; parity vectors that
carry their own inputs and arguments; vectors for `merge`, `shaped`,
`trace.report` in all ports.

**F. Honest benchmarks**
Inflected-query episodes; a fair hand-written baseline with its own scorer;
computed (not hand-typed) capability labels; published numbers tied to the
generated results; checksummed dataset fetch.

**G. Audit and release hygiene**
Trace dropped-id correctness; fingerprint distinguishes distinct policies;
tiktoken special-token crash; `py.typed`, lint/type config; version agreement
checked in CI across all version files.

### Non-goals
- Semantic/embedding relevance. The benchmark in F measures **inflection**
  robustness, not semantic paraphrase; semantic matching stays a documented
  limit.
- Conversation/message stages (sub-project 2), the context assembler
  (sub-project 3), domain presets, non-coding benchmark data and the
  coding-centric docs rewrite (sub-project 4).
- A cross-language canonical policy fingerprint (ADR-001/002 keep it roadmap).
- Any new **runtime** dependency. Python stays zero-dependency, no model calls.
- Changing the output bytes of any call that is valid today (opt-in only).
- Publishing, tagging or pushing anything (§5, human's action).

### Deferred (parked, not built)
- Quarantine cross-field matching (fields are joined with a space, so a phrase
  spanning two fields is flagged). Decide at G1 whether per-field scanning is
  a fix or a behavior regression.
- `shaped` on callable objects with an async `__call__` (reported by the
  explorer, **not yet reproduced**); reproduce first, then decide.
- `rescore` BM25 length normalization and `(k1+1)` factor (changes all scores).
- Trace pricing uses the ambient tokenizer, not the stage's own (reported, not
  yet reproduced).

## Acceptance criteria (numbered, testable)

Each AC maps to at least one named test in the G2 plan. "Vectors" means
`parity/vectors.json` consumed by Python, TypeScript and C#.

**A. Controls**
1. Given `allowlist(recs, "s", "github")` and records with `s="g"` and
   `s="github"`, then `"github"` passes and `"g"` is dropped (a bare string is
   one allowed value, as for `fields`).
2. Given `quarantine` default patterns and a record whose nested value
   (any depth) contains `"ignore all previous\ninstructions"`, then the record
   is dropped (action `drop`) or flagged (action `flag`).
3. Given `quarantine(fields=[])`, then a typed configuration error is raised
   (silent no-op removed), consistent with the existing empty-pattern errors.
4. Given an invalid user regex in `quarantine(patterns=[...])`, then a typed
   configuration error naming the offending pattern is raised, not a raw
   `re.error`.
5. Given `quarantine(action="flag")` and a record that already has the `into`
   key, then `input.field_conflict` is raised (never a silent overwrite;
   decided at G1, 2026-11-19).
5a. Given `allowlist(recs, "s", [1])` and records with `s=True`, `s=1`,
   `s=1.0`, then `True` is dropped and `1` and `1.0` pass: a bool never
   equals a number. int and float keep comparing by numeric value because
   TypeScript cannot distinguish them (documented parity margin). The vector
   set includes `true`/`false` vs `1`/`0` in all three languages. This is a
   deliberate behavior change (the human chose type-strict, 2026-11-19) and is
   listed under "Behavior changes".

**B. Errors and validation**
6. A typed error hierarchy is exported (`ContexelError` base; configuration
   and input-shape subclasses). Both subclasses also derive from `ValueError`
   / `TypeError` respectively, so existing `except ValueError` / `except
   TypeError` handlers keep working.
7. Given `rescore(match=<anything other than "word", "substring", "stem">)`,
   `rescore(fields=[])`, a `max_tokens` that is negative or not an integer
   (`0` stays valid and returns `[]`), or any other wrong-typed configuration
   parameter, then a typed configuration error is raised (always on, not
   strict-only). Amended at G1, 2026-11-19 (was "`<= 0` where invalid").
8. Given strict mode enabled (mechanism chosen at G1) and records that are
   not a list, or items that are not mappings where a stage needs one, then a
   typed input-shape error naming the stage and item index is raised.
9. Given strict mode **off**, then output for every input in the existing
   vectors and existing tests is byte-identical to before (the existing 66
   Python tests, 41 TS tests and 39 C# tests pass), with exactly two
   carve-outs decided at G1: (a) the vector `edges.allowlist_bool_int`
   expectation changes per AC 5a; (b) C# assertions of the exact exception
   type (`Assert.Throws<ArgumentException>`) become `ThrowsAny<…>` because
   the typed errors derive from `ArgumentException` (callers' `catch` clauses
   are unaffected).

**C. Payloads**
10. `split(records, field="text", by=..., size=..., into="chunk")` returns,
    for each record, chunk records carrying the parent's fields, the chunk
    text in `field`, and `into: {index, start, end}` (code-point offsets), for
    modes lines, paragraphs and size. Lines end after `"\n"` only (not
    Python's wider `splitlines` set); paragraphs after `(?:\r?\n){2,}`; so all
    three languages agree. (Reworded at G1 to take records; text enters via
    `as_records`.)
11. Given any text, then joining the chunks with `""` reproduces the original
    text (lossless), and `text[start:end]` equals each chunk (property test).
12. Given `""` then `split` yields no chunks; given text with no separator
    then one chunk; given a 1,000,000-character input then it completes and
    the offsets round-trip. Invalid `by`/`size` combinations raise typed
    configuration errors; an existing `into` key raises `input.field_conflict`.
13. `as_records(x, field="text")` turns a string or a single mapping into one
    record, wraps non-mapping list items as `{field: item}`, keeps mapping
    items unchanged, and raises `input.not_list` for `None` or bytes.
14. `join(records, field="text", sep="")` returns a string; `join(split(
    as_records(t)))` equals `t` for the lossless modes.
15. End to end (vector, all three languages): raw log text → `as_records` →
    `split` → `dedupe` → `rescore` → `rank` → `trim_to_budget` → `join`
    yields identical output and fits the stated token budget.

**D. Stemming**
16. Default `match="word"` output and all existing vectors are unchanged.
17. With `match="stem"`, `parse`, `parsing`, `parsed`, `parses` are scored as
    the same term; `values` matches `value`; words shorter than the documented
    minimum stem length are left unchanged; the stemmer never raises on any
    input string including empty and non-letter text.
18. The stemmer's rule table is committed in `docs/`, and a vector set of at
    least 100 word→stem pairs passes identically in Python, TypeScript, C#.
18a. `rescore(..., normalize="nfc")` and `quarantine(..., normalize="nfc")`
    NFC-normalize query and text before tokenizing and matching. With it, NFC
    and NFD `café` score identically (0.115073 in the verified example);
    default `normalize=None` leaves every existing output unchanged. An
    unknown `normalize` value raises a typed configuration error.
18b. The vector set for `normalize` covers combining marks, precomposed vs
    decomposed Latin, Hangul, and astral characters, and passes identically
    in all three languages. The cross-runtime Unicode-version margin is
    documented in an ADR amendment.

**E. Enforced determinism and invariants**
19. A pytest test runs the standard contract in at least three subprocesses
    with different `PYTHONHASHSEED` values and asserts identical output
    hashes. It runs in CI on all current OS/Python matrix cells.
20. Seeded generative tests (standard library only) cover every stage: input
    not mutated; same input gives same output; idempotence where the stage is
    idempotent; filter stages return a subsequence of the input; order
    preserved where promised. Failures print the seed. No `hypothesis`
    dependency is added.
21. The vector file carries each case's stage name, arguments, input and
    expected output; the TypeScript and C# tests replay cases from the file
    generically. Adding a case requires editing only the generator.
22. `merge`, `shaped` and `trace.report` have vectors or equivalent
    cross-language tests in TypeScript and C#.

**F. Benchmarks**
23. An inflected-query episode set exists (query terms are deterministic
    inflections of the target's terms, so they are not verbatim substrings of
    the target). Recall is reported for `match="word"` and `match="stem"`
    separately from the existing episodes, and the report states it measures
    inflection, not semantic paraphrase.
24. The hand-written baseline gains a hand-written term-overlap scorer and
    budget trimming; the report shows contexel against it with both rescoring.
25. Native-operation counts in `COMPARISON.md` are computed from the code that
    defines each implementation, not hand-typed strings.
26. A check (test or script run in CI) fails when the benchmark numbers on
    `site/benchmarks.html` or `README.md` differ from the generated results.
27. The dataset fetch verifies a committed SHA-256 and fails on mismatch.

**G. Audit and release hygiene**
28. Given a trace with `id_field` where some surviving records lack the id and
    an identified record is dropped, then that record's id appears in
    `dropped_ids`.
29. Two pipelines differing only in a bound set's contents, a nested
    pipeline's stages, or the tiktoken encoding have different fingerprints;
    a pipeline containing none of those has the **same** fingerprint as
    before this change.
30. A policy cannot change behavior without changing its fingerprint
    (bound-container mutation after construction): chosen at G1 as snapshot at
    construction or fingerprint at call time.
31. Counting or truncating text containing `"<|endoftext|>"` under a tiktoken
    tokenizer returns a number instead of raising.
32. `py.typed` ships in the wheel; the lint and type checks are configured and
    pass on the `contexel/` package.
33. A CI check fails when the seven version locations (`pyproject.toml`,
    `contexel/__init__.py`, `ts/package.json`, both entries in
    `ts/package-lock.json`, `ts/src/index.ts`, `csharp/Contexel/Contexel.csproj`)
    disagree, on every push, not only at tag time.

**Cross-cutting**
34. Every behavior change is listed under "Behavior changes" in the
    changelog; every new public stage/parameter has a runnable, tested
    example and is documented in the READMEs and `site/stages.html`.
35. Python, TypeScript and C# suites pass on Linux, Windows and macOS in CI;
    regenerated vectors show no diff against the committed file.
36. (Added at G1, 2026-11-19.) A seeded differential-fuzz corpus generated
    inside the documented parity envelope is replayed by the TypeScript and C#
    suites in CI. Every divergence is either fixed or recorded as an ADR
    margin that narrows the fuzz domain; none is filtered silently. Target
    runtime under 60 seconds.

## Constraints
- Python ≥ 3.9, zero runtime dependencies, no model calls, no network at
  runtime. Dev-only tooling must pass `standards/dependency-policy.md` (G1).
- Valid-today inputs keep byte-identical output and unchanged fingerprints
  unless an AC above says otherwise (AC 5a changes allowlist results for
  bool-vs-number mixes; only AC 29/30 touch fingerprints, and only for the
  listed policy shapes).
- Python is canon; TypeScript and C# must match through the vectors. The
  documented parity envelope (int/float in TS, code points, case-folding
  margins) stays the contract; new stages must live within it.
- Versions follow the project's rule: working code commits may use a working
  number, identifiers change only at release; the next number is assigned at
  release time. Commit author per the repo's identity rule.
- Toolchains available locally: Python 3.12, Node 24, .NET 8.

## Assumptions (chosen defaults — correct me if wrong)
1. All three ports get every capability in this sub-project (the repo's CI
   contract); nothing ships Python-only.
2. Error split: **configuration errors always raise** (unknown option values,
   invalid regex, empty/contradictory config); **data-shape errors raise only
   in strict mode**. This is how I read "Hybrid" for the parts you did not
   name explicitly (rescore match validation, `max_tokens=None`).
3. Property tests use seeded `random` from the standard library, not
   `hypothesis`, to keep the dependency count at zero.
4. `rescore`'s zero-match score stays `int 0` in the no-match path and
   `float 0.0` on the empty-terms path in Python. Changing it would change
   existing output bytes. It is documented, not fixed.
5. The stemmer is English-only and documented as such; the rule table is a
   conservative suffix-stripper (not Porter).
6. A bare string for `allowlist(allowed=...)` means one allowed value
   (matching the `fields` convention), not an error.
7. Slice order (proposed for G2): E first (build the safety net on current
   behavior), then A+B (controls, errors), then G (audit, hygiene), then C,
   then D, then F, then the differential fuzz (AC 36) last.

## Open questions
None blocking. Resolved by the human on 2026-11-19:
1. allowlist equality → **type-strict** (AC 5a; narrowed to bool-vs-number
   because TypeScript cannot distinguish int from float — **please confirm the
   narrowing when you read AC 5a**).
2. Error split → **as written** (Assumption 2).
3. Unicode normalization → **include opt-in NFC** (AC 18a/18b).

**Human confirmed:** decisions yes (scope decomposition, Hybrid compat policy,
Chunk + adapt, opt-in small stemmer, type-strict allowlist, error split,
opt-in NFC) · 2026-11-19. Full-brief read-through pending: the human has not
yet been shown the final text of AC 5a / 18a / 18b.
