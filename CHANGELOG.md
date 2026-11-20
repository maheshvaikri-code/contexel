# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/). Versions follow
`z.y.x` — Mega. Major. minor/patch — and every commit bumps the version.

## [Unreleased]

### Added — typed errors and strict mode (ADR-003, all three languages)
- `ContexelError` with `ConfigError` (a wrong *call*) and `InputShapeError`
  (wrong *data*), each carrying a stable `code` — `config.invalid_value`,
  `config.empty`, `config.contradictory`, `config.invalid_pattern`,
  `input.not_list`, `input.not_mapping`, `input.field_conflict` — the
  cross-language contract (messages are not). Python: `ConfigError` is also a
  `ValueError` and `InputShapeError` a `TypeError`; C#: both derive from
  `ArgumentException`. Handlers for the shape errors keep working, but they do
  not all carry over: a configuration mistake that used to raise a raw
  `TypeError` (`select(r, None)`, `dedupe(r, key=5)`, `max_tokens=None`, ...)
  now raises a `ConfigError`, which is a `ValueError`, so an `except TypeError`
  no longer catches it (catch `ValueError` or `ContexelError`); a bad
  `quarantine` regex raises `ConfigError`, not `re.error`; in C#
  `catch (ArgumentException)` still works but a handler for the framework's
  `RegexParseException` no longer sees a bad `quarantine` pattern; and in
  TypeScript a bad `quarantine` regex used to throw a `SyntaxError` and a
  wrong-typed or `null` argument a raw `TypeError`, and both are now a
  `ConfigError`, which extends only `Error`, so `e instanceof SyntaxError` and
  `e instanceof TypeError` no longer match (catch `ContexelError` or
  `ConfigError`). The shared
  parity vectors gain error cases that assert the code in all three languages
  (70 cases in all, 31 of them error cases).
- Opt-in strict mode that validates the shape of stage input and names the
  stage and item index: `with strict():` (Python), `strict(fn)` (TypeScript),
  `Strict.Begin()` (C#), and `pipeline(..., strict=True)` /
  `shaped(..., strict=True)`, which enter it inside their own run so it holds
  on worker threads and also check that every stage (or the tool) returns a
  list. Strict never changes a successful result and is not part of the
  fingerprint. Two shape errors are raised without it: `input.field_conflict`
  and `quarantine`'s `input.not_mapping` (see Behavior changes, item 3).
- Public surface, each exposed as the code has it: TypeScript exports
  `isStrict`, `ERROR_CODES` and the `ErrorCode` type; C# has `Strict.IsActive`,
  `ContexelException.Codes` and `Pipeline.IsStrict`; Python keeps `is_strict`
  and `CODES` out of `__all__` (import them from `contexel.validate` and
  `contexel.errors`).
- The parity runners reject unknown option names inside a case's `args`.

### Behavior changes
Valid input with strict mode off keeps byte-identical output; these are the
exceptions, all intentional:
1. `allowlist` is type-strict for bool versus number: `True` no longer passes
   `allowed=[1]` and `1` no longer passes `allowed=[True]` (`1` and `1.0` still
   compare equal — TypeScript cannot tell them apart). The parity vector
   `edges.allowlist_bool_int` changes from `[true, 1, 1.0]` to `[1, 1.0]`.
2. `allowlist(allowed="github")` is one allowed value, not its characters.
3. `quarantine` now finds a marker inside a nested dict or list value (a
   newline in the value used to defeat the match). A nested value is scanned as
   its dict keys (in sorted order, not insertion order) and its leaves, joined
   by single spaces (strings as they are; numbers, booleans and null as their
   text), so a custom pattern written against the Python `repr` punctuation of
   a nested value (quotes, braces) no longer matches it, and a phrase can now
   match across adjacent items: `[{"snippet": ["system", "prompt"]}]` and
   `[{"snippet": ["ignore", "all previous instructions"]}]` are now dropped
   (they were kept).
   `fields=[]` now raises instead of silently doing nothing, and an invalid
   regex raises a `ConfigError` (see item 4 and the handlers note above). In
   flag mode, a record that already has the `into` key raises
   `input.field_conflict` instead of being silently overwritten; this is raised
   whether or not strict mode is on and whether or not the record is clean, so
   re-running a flag pipeline on its own output raises (pass a different `into`).
   An item that is not a mapping (a string, list, tuple, number, boolean or
   null) always raises `input.not_mapping`, in drop and flag mode, strict mode
   or not, because a screen that skips what it cannot read would keep the
   attack. In TypeScript this covers every object that is not a plain record
   too: a `Map`, `Set`, `Date`, `RegExp`, typed array or boxed `String`,
   `Number` or `Boolean` raises, while plain objects, class instances and
   null-prototype objects are scanned. Before, Python raised a raw
   `AttributeError`; during this slice a string, list or tuple was silently
   kept in drop mode, and TypeScript in flag mode spread a string into
   per-character keys; C# threw a
   `NullReferenceException` for a null item. This is the one other exception
   (besides `input.field_conflict`) to "shape errors only in strict mode";
   `allowlist` does not share it (see Known limitations).
   The built-in markers are compiled once and each custom pattern is compiled
   and matched on its own; a record is dropped or flagged when any of them
   matches (they used to be joined into one regex). So a global inline flag in
   a custom pattern (`(?a)zzz`, `(?i)foo`) is valid on its own where the
   engine supports it and affects only that pattern (on Python 3.9 and 3.10
   `patterns=["(?a)zzz"]` no longer weakens the built-in markers), numbered
   backreferences and named groups stay inside their pattern
   (`["(zz)q", "(evil)-\1"]` drops `"zz evil-evil"`), a .NET option such as
   `(?-i)` no longer leaks into later patterns, and the "cannot be combined"
   error no longer exists: an invalid pattern is always named,
   `config.invalid_pattern`. This also NARROWS some pattern lists that worked
   before: a few records that were dropped only because of the leak are now
   kept. On Python 3.9 `patterns=["(?s)zz", "c.d"]` dropped `"c\nd"` and
   `["(?m)zz", "^evil"]` dropped `"x\nevil"` (the first pattern's flag was
   applying to the second); in Python (3.9 and 3.12) `replace_patterns=True`
   with `["(?m)^admin:", "^ignore"]` dropped `"hello\nignore"`; in C#
   `["(?s)zz", "c.d"]` dropped `"c\nd"` and `["(?m)zz", "^evil"]` dropped
   `"x\nevil"`; in TypeScript an unmatched
   numbered back-reference matched the empty string in the joined regex, so
   `["(zz)q", "(evil)-\1"]` dropped `"evil-x"`. All of these are now kept: only
   text that really matches a pattern on its own is dropped. This is the
   intended behaviour (a pattern means what it says on its own, and the
   built-ins can no longer be weakened or silently disabled by a custom
   pattern), but a custom pattern list that relied on the leak must be
   rewritten, giving each pattern its own flags and groups.
4. Misconfiguration raises a typed `ConfigError`: an unknown `rescore` `match`
   (it silently ran substring matching; `match="stem"` is reserved and raises
   until the stemmer ships), `fields=[]` for `rescore`, a `max_tokens` or
   `min_records` that is negative or not an integer (`0` stays valid; `None` used
   to raise a raw `TypeError` and is now a `ConfigError`, a `ValueError`), and
   any wrong-typed parameter, for example `rank(r, by=5)`,
   `rank(r, "score", desc="yes")`, `rescore(r, "q", into=5)`,
   `truncate_field(r, "a", 3, suffix=5)` or `allowlist(r, "f", None)`; this
   covers `fields`, `key`, `by`, `desc`, `into`, `proximity`, `query`,
   `allowed`, `field`, `suffix`, `patterns`, `replace_patterns`, `action` and
   `match`. In Python `fields`, `key` and `query` must now be a string or a
   list/tuple of strings (a set or generator is rejected; `allowed` still takes
   a set, but not a generator, dict, range or `None`), and `max_tokens` and
   `min_records` must be a real `int`: `1000.0` and `True` are rejected, where
   they used to be accepted. TypeScript has one number type, so `1000.0` is
   just `1000` there and is accepted.
5. TypeScript `null` is no longer "use the default". The old code treated an
   omitted option and `null` alike (`??`); now only `undefined` selects the
   default, for `fields` (`quarantine`, `rescore`), `into`, `proximity`,
   `match`, `desc`, `suffix`, `minRecords` and `action`, and `null` raises
   `config.invalid_value`; so does `replacePatterns: null` (it used to be
   falsy and was treated as false). `key: null` (`dedupe`) and
   `tokenizer: null` still mean "default", as `None` does in Python, and
   `patterns: null` now means "no extra patterns" (it used to crash with a raw
   `TypeError`). C# is different on purpose: `fields: null` (`quarantine`,
   `rescore`) still means "use the default `snippet` field": C# cannot tell an
   omitted optional argument from an explicit `null` without changing the
   public API to overloads, and it is left as is to avoid changing the public
   API.

6. Other changes: `rescore` `query` elements must be strings in all three
   languages (`rescore(r, [None])` was accepted and searched for the term
   "none"); `pipeline(..., strict=...)` and `shaped(..., strict=...)` must be a
   bool (`strict="no"` used to turn strict mode ON in Python, TypeScript tested
   `=== true`); Python `quarantine` scans the `repr()` as well as the `str()`
   of an in-process object leaf when they differ (an object may show text in
   only one of them), for a top-level field value as well as a nested one: a
   `Decimal`, `datetime`, `Enum` or `UUID` field now matches a custom pattern
   against its `repr()` (`Decimal("5")` is kept by a pattern `Decimal` before
   and dropped now), while an anchored pattern such as `^5$` no longer matches
   a `Decimal("5")` field (the scanned text is `5 Decimal('5')`); an object
   whose `__repr__` raises makes `quarantine` raise that exception unchanged
   (it fails closed, but it is not a `ContexelError`) and side effects in
   `__repr__` run; exact `int`, `float`, `bool` and `None` leaves skip the
   `repr()` call and dict keys are scanned with `str()` only; the Python
   `strict()` context object can be re-entered (nested or sequential reuse
   restores the previous state correctly), but one object shared between
   asyncio tasks or threads whose uses overlap can fail with `ValueError: ...
   was created in a different Context`: call `strict()` for each use; in C#
   disposing two `Strict.Begin()` scopes out of order leaves strict mode on:
   use `using`.
7. C#: a `HashSet` or `SortedSet` passed as `fields`, `key`, `patterns` or
   `query` used to be accepted and now throws `ConfigException`
   (`config.invalid_value`; the message says "got list" for a set). Python and
   TypeScript reject sets there as well.

### Compatibility
C#: the `Shaped.Wrap` overloads gained an optional `strict` parameter. That is
source-compatible, but a caller compiled against the previous release must be
recompiled (the method signatures changed). The new
`Allowlist(records, field, string allowed)` overload makes a call with a
literal `null` third argument, `Stages.Allowlist(r, "f", null)`, ambiguous
(compile error CS0121) where it compiled before; cast it
(`(IEnumerable<object?>)null`) or pass a real list.

### Known limitations
Documented, not fixed in this slice. `quarantine` is a tripwire for literal
markers, not a security boundary, and the three ports do not catch exactly the
same obfuscations.
- C# `JsonElement` and `JsonNode`: `quarantine` and `allowlist` do not read
  `System.Text.Json` values (what `JsonSerializer.Deserialize<Dictionary<string,
  object?>>` produces by default). A marker split by a newline inside a nested
  `JsonElement` or `JsonNode` is kept, and `Allowlist` drops a `"github"`
  `JsonElement`. Records must hold ordinary CLR values (`Dictionary`, `List`,
  `string`, numbers, `bool`, `null`); convert first. An `ExpandoObject` holding
  a nested dictionary is not scanned either.
- The built-in markers differ per engine: U+0085 is caught by Python and C#
  and kept by TypeScript; U+001C to U+001F are caught by Python only; U+FEFF by
  TypeScript only; dotless i and dotted I (U+0131, U+0130) and long s (U+017F,
  in "system prompt") by Python only. In custom patterns `\Z` is a literal
  `Z` in TypeScript and an end anchor in Python and C#, and the Kelvin sign
  (U+212A) is folded to `k` by Python and C# but not by TypeScript. A lone
  `\1` (a back-reference with no group of its own) is a legacy octal escape in
  TypeScript (valid, it matches U+0001) but `config.invalid_pattern` in Python
  and C#. TypeScript rejects the global inline flag `(?i)x`; the scoped
  modifiers `(?i:...)` and `(?-i:...)` are accepted only by newer engines (Node
  24 accepts them; older Node versions were not tested here), so their validity
  there depends on the Node version, while Python accepts a leading `(?i)` and
  `(?i:...)` and C# the flags .NET supports.
- None of the ports catches: zero-width characters (U+200B, U+2060), RLM and
  RLO marks, a soft hyphen (U+00AD), combining marks, homoglyphs (Cyrillic
  U+0430 for `a`), fullwidth forms, `&nbsp;`, a marker split across two
  sibling dict values (the key sits between them), `< /system >`.
- A misspelled field name in `fields` (`"snipet"`) scans nothing and keeps
  everything, strict mode or not, in all three languages; so does `fields=""`.
  Check the field names against your records.
- `allowlist`: a `None`/`null`/`undefined` entry in `allowed` admits records
  that lack the field (a trap with `os.environ.get(...)` or an unset config
  value; TypeScript sparse array literals too). `NaN` in `allowed` matches
  `NaN` in TypeScript and C#, and in Python only the same object. `allowlist`
  does not raise `input.not_mapping` for a non-mapping item: Python raises a
  raw `AttributeError`, C# a `NullReferenceException` for a null item, and
  TypeScript drops it (a string reads as a missing
  field), except when `allowed` contains `null`, where it keeps it
  (`allowlist(["text"], { field: "a", allowed: [null] })`). A follow-up is
  planned.
- Custom patterns run against attacker-controlled text and no port sets a
  match timeout: a pattern with nested quantifiers such as `(a+)+$` is
  exponential on crafted input (the built-ins are linear). Do not accept
  patterns from untrusted sources.
- A shared in-process container is expanded once, so a marker that needs the
  same list twice is not found (JSON-decoded input never shares structure).
  In Python a `set`, `frozenset`, `deque` or dict view is not expanded (it is
  scanned as its `str()` text, so a newline-split marker inside one is kept);
  in TypeScript `Map`, `Set`, `Date` and typed arrays are not read inside a
  nested value either (as an item they raise `input.not_mapping`); C#
  enumerates any `IEnumerable`. In Python a `collections.abc.Mapping` that is
  not a `dict` (a `MappingProxyType`) is scanned as a field value only through
  its `str()` and `repr()`, so one holding a newline-split marker is kept.
- TypeScript reads a class instance through its own properties only: a field
  that is inherited from the prototype or defined as a prototype getter (not an
  own property) is read as if the record had no such field, and the record is
  kept (own accessor properties are read).
- `dedupe(key=[])` and `dedupe(key="")` keep only the first record in all three
  languages. A very deep value under an active `trace()` raises `RecursionError`
  in Python and `RangeError` in TypeScript (both catchable) and overflows the
  stack, which ends the process, in C#. A custom pattern that matches the empty
  string (`a*`) drops every record. TypeScript ignores unknown option keys (a
  typo such as `{ field: "body" }` is silently ignored; the compile-time
  excess-property check only covers object literals).

### Tests
C# tests that asserted the exact exception type
(`Assert.Throws<ArgumentException>`) became `Assert.ThrowsAny<…>`, because the
typed errors derive from `ArgumentException`. This is a test change only: a
caller's `catch (ArgumentException)` is unaffected.

### Added — test infrastructure (no library behavior change)
- Seeded stdlib property tests for every stage (purity, determinism,
  idempotence, subsequence, count, input order, rank tie stability and
  budget invariants, and each filter stage's effect), every check with a
  canary proving it can fail; failures print their seed, including when a
  stage raises.
- A cross-process determinism test that sweeps `PYTHONHASHSEED` over a
  pipeline whose data contains sets, mixed types and non-ASCII text, and
  asserts that the requested seed actually took effect in each child process.
- Golden policy-fingerprint tests pinning today's values (the compatibility
  baseline for the audit-truthfulness work, ADR-008), including dict-valued
  and opaque-object parameters.
- Data-driven parity cases (ADR-007): `parity/parity_cases.py` is the single
  case table; `vectors.json` gains a `cases` array and `_meta.case_count`;
  the TypeScript and C# suites replay every case through one adapter per
  stage. First coverage of `merge`, `shaped`, `trace.report()` and the
  empty-input class in all three languages. A generator-side envelope guard
  rejects data TypeScript cannot represent (integer-valued floats, NaN/Inf,
  integers beyond 2^53), and a pinning test keeps the NFC/NFD case holding
  two distinct keys. Boundary cases pin the first-present `merge`
  candidate, code-point (not byte or UTF-16) token counting, multi-field
  `quarantine`, the exact `trim_to_budget` cost, the 80-character
  `rescore` proximity window, `rank` ties kept in input order, a missing
  `allowlist` field read as `None`, and whitespace stripped before the
  truncation suffix; both runners fail on an empty case list.

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
