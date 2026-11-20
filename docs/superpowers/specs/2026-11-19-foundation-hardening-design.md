# Foundation hardening — design (G1)

**Date:** 2026-11-19 · **Status:** design approved in conversation by the human
2026-11-19; **written spec awaiting the human's review** · **Role:** Chief
Architect · **Brief:** `docs/briefs/foundation-hardening.md` · **ADRs:**
003–008 (`docs/adr/`)

This is sub-project 1 of 4 of the "context excellence for all agents"
programme. It makes the existing guarantees *enforced* and widens the input
model to text. It adds no conversation or assembler concepts (sub-projects 2–3).

## 1. Principles that decide every trade-off here

1. **Valid-today input keeps byte-identical output** and an unchanged
   fingerprint. Exceptions are enumerated (§9) and listed under "Behavior
   changes" in the changelog.
2. **Python is canon; the ports match through vectors.** Anything a vector
   cannot express is a documented margin, never a silent difference.
3. **A control must never be weaker than it looks.** Misconfiguration raises.
4. **Legacy stages gate *shape* validation behind strict mode** (compat);
   **new stages validate always** (no compat burden).
5. **Zero runtime dependencies, no model calls.** Dev-only tools are the sole
   additions (§8).

## 2. Architecture

```
 on-ramp                  record stages                         off-ramp
 as_records ─┐   select dedupe allowlist quarantine rescore     join ──► str
 split ──────┴─► rank truncate_field trim_to_budget merge ─────►
                    ▲ checked (strict) ▲ traced (audit) ▲ config validation
 cross-cutting:  errors · strict · trace · fingerprint · tokens(unchanged)
 enforcement:    vectors v2 · property tests · hash-seed CI · differential fuzz
```

A record remains "a mapping with string keys". Text becomes records at the
on-ramp, so every existing stage works on it unchanged.

### Module layout (mirrored in all three languages)

| Python | TypeScript | C# | Responsibility |
|---|---|---|---|
| `contexel/errors.py` | `ts/src/errors.ts` | `Errors.cs` | error types, `code`, config-validation helpers |
| `contexel/validate.py` | `ts/src/validate.ts` | `Validate.cs` | strict switch, `checked` decorator, shape checks |
| `contexel/text.py` | `ts/src/text.ts` | `Text.cs` | `as_records`, `split`, `join` |
| `contexel/stem.py` | `ts/src/stem.ts` | `Stem.cs` | pure, frozen `stem()` |
| existing | existing | existing | stages, pipeline, trace, tokens, shaped |

Dependency direction (no cycles): `errors ← validate ← stages, text`;
`stem ← stages`; `tokens`, `trace` unchanged and below `stages`.

## 3. Errors and strict mode (ADR-003)

### Types
`ContexelError` (base; fields `code`, `stage`, optional `param`, message).
`ConfigError` and `InputShapeError` derive from it **and** from what the
language already raises, so existing `catch` clauses keep working:

| | `ContexelError` base is | `ConfigError` also is | `InputShapeError` also is |
|---|---|---|---|
| Python | `Exception` | `ValueError` | `TypeError` |
| TypeScript | `Error` | — | — |
| C# | `ArgumentException` (types `ContexelException`, `ConfigException`, `InputShapeException`) | `ArgumentException` (via base) | `ArgumentException` (via base) |

### Codes (the cross-language contract; messages are not)

| code | meaning |
|---|---|
| `config.invalid_value` | unsupported option value or wrong-typed parameter (`match`, `action`, `normalize`, `by`, `max_tokens` negative or non-integer, `size`) |
| `config.empty` | would silently do nothing/everything: empty pattern fragment, empty replacement list, `fields=[]` for `quarantine` and `rescore` |
| `config.contradictory` | `replace_patterns` without `patterns`; `size` given with `by` ≠ `"size"` |
| `config.invalid_pattern` | a user regex fails to compile (message names the pattern) |
| `input.not_list` | records are not a list/array |
| `input.not_mapping` | an item is not a mapping (message names stage and index) |
| `input.field_conflict` | an output field already exists (`quarantine` flag `into`; `split` `into`) |

Existing quarantine errors keep their **message text** and map: bad `action` →
`invalid_value`; empty fragment / empty replacement → `empty`;
`replace_patterns` without patterns → `contradictory`.

### Always-on vs strict-only

| class | legacy stages | new stages (`split`, `as_records`, `join`) |
|---|---|---|
| config errors | always raise | always raise |
| `input.not_list` / `input.not_mapping` | raise only in strict mode | always raise |
| `input.field_conflict` | always raise (data-loss prevention) | always raise |

`max_tokens` rule: must be an integer (not bool) ≥ 0; `0` stays valid and
returns `[]` (a legitimate "no budget left"). `None`, floats, strings, negatives
raise `config.invalid_value`.

### Strict mode mechanism
- Ambient flag in a context-local (`ContextVar` / `AsyncLocalStorage` /
  `AsyncLocal`), exposed as `strict()` (context manager / callback / using).
- `pipeline(stages, strict=True)` and `shaped(pipe, strict=True)` enter strict
  **inside their own run**, so it also applies on threads/workers where the
  ambient flag is not inherited. Bare `with strict():` is documented with that
  caveat.
- `shaped(strict=True)` additionally validates the tool's return is a list
  (`input.not_list`, stage `"shaped"`). `pipeline(strict=True)` validates each
  stage's *output* is a list, naming the stage index (catches a custom stage
  returning `None`).
- A `checked(mapping=bool)` decorator sits **outside** `traced` on each legacy
  stage, so the check runs before `traced` calls `len(records)` (otherwise a
  non-list raises a raw error under trace). Item mapping required for: select,
  rank, allowlist, quarantine, rescore, truncate_field, dedupe **when `key` is
  given**. Not required: dedupe(`key=None`), trim_to_budget.
- Strict never changes a successful result, so it is **not** part of the
  fingerprint.

## 4. Security-control fixes

### allowlist (ADR-004)
- Match key `(is_bool, value)`; a bool never equals a number; int and float keep
  numeric equality because TypeScript cannot distinguish them (documented
  margin). Unhashable record values fail closed (unchanged); unhashable
  `allowed` entries raise as today.
- A bare string for `allowed` is **one** allowed value (TS: explicit `typeof`
  check, since iterating a string yields characters; C#: add a `string`
  overload).
- Vector `edges.allowlist_bool_int` changes expected output from
  `[{v:true},{v:1},{v:1.0}]` to `[{v:1},{v:1.0}]`. This is the **only** existing
  vector expectation that changes.

### quarantine
- **Nested values:** instead of `str(value)` (a Python `repr` in which a newline
  becomes the two characters `\n` and defeats `\s+`), collect string leaves
  recursively and join with a space. Dict keys iterate in code-point order;
  lists in order; scalars render with the existing `str` rule (`None` →
  `"None"`, numbers as today). A top-level string field is unchanged.
- `fields=[]` → `config.empty`. Invalid user regex → `config.invalid_pattern`
  (each user pattern compiled alone to name the culprit, then the combined
  matcher).
- Flag mode: if a record already has the `into` key → `input.field_conflict`
  (previously silently overwritten; two chained flag passes with the default
  `into` clobbered each other).
- `normalize` (§6) applies to the scanned text only, not to patterns.
- Cross-field joining (a phrase spanning two fields) is **kept as is** and
  documented; deferred.

## 5. Payload stages (ADR-005)

All three are plain stages. `as_records` and `join` are entry/exit points and
are not traced (as `merge`); `split` is traced.

**`as_records(x, field="text") -> Records`**
- `str` → `[{field: x}]`; a mapping → `[x]`; a list/tuple → each mapping item is
  kept, each other item becomes `{field: item}` (nested JSON values allowed).
- `None`, bytes, and other types raise `input.not_list` (always). `field` must
  be a non-empty string (`config.invalid_value`).

**`split(records, field="text", by="lines", size=None, into="chunk") -> Records`**
Offsets and sizes are in **code points** (all ports already have code-point
helpers). Each chunk **keeps its trailing separator**, so
`join(split(...), sep="")` reproduces the original text.

| `by` | chunk boundary |
|---|---|
| `"lines"` | after each `"\n"` (so `"\r\n"` is one boundary; a lone `"\r"` is not). Not Python's wider `splitlines` set. |
| `"paragraphs"` | after each maximal run matching `(?:\r?\n){2,}` |
| `"size"` | every `size` code points (`size` a positive integer, required) |

- The remainder after the last boundary is a chunk if non-empty. Empty text
  yields no chunks (that parent record disappears; documented).
- Each chunk = `{**parent, field: chunk_text, into: {"index": i, "start": s, "end": e}}`
  with `index` 0-based within its parent and `[start, end)` code-point offsets
  into the original, so `text[start:end] == chunk_text`.
- A non-string `field` value passes through untouched (like `truncate_field`).
- A parent that already has the `into` key → `input.field_conflict`.
- `size` with `by != "size"` → `config.contradictory`; `by="size"` without a
  positive integer `size` → `config.invalid_value`; unknown `by` →
  `config.invalid_value`.
- Overlapping windows and token-sized chunks are deferred (they break
  losslessness / need a cross-language tokenizer).

**`join(records, field="text", sep="") -> str`**
Records lacking `field` are skipped; a string value is used as is; any other
value is rendered with `tokens.serialize` (the text the budget priced); parts
are joined with `sep`.

**Ordering note (docs, not code):** `rank` reorders chunks by score; to restore
reading order before `join`, rank again by `chunk.start` with a named key
function. A dotted-path `rank` is deferred.

## 6. rescore matching modes (ADR-006)

- `match ∈ {"word", "substring", "stem"}`; anything else →
  `config.invalid_value`. Default stays `"word"`.
- **`stem`:** tokens come from the existing `_TOKEN` regex over lower-cased
  text; each token is stemmed; terms are the de-duplicated stems of the query in
  first-occurrence order; scoring, IDF, proximity and rounding are unchanged
  (positions are token starts).
- **Frozen rule order** for `stem(w)` (input already lower-case; lengths and
  comparisons in code points; `w` of length ≤ 3 is returned unchanged):
  1. `sses` → drop the last 2 chars.
  2. else `ies` and length > 4 → replace with `y`.
  3. else `ied` and length > 4 → replace with `y`.
  4. else ends with `s` but not `ss`, `us`, `is` → drop the `s`.
  5. then: if the word ends with `ing` only that suffix is considered; else if
     it ends with `ed` only that suffix is considered (no fallback from one to
     the other). Strip the suffix only if the remaining base is ≥ 3 code points
     and contains one of `aeiouy`; if stripped and the base ends in a doubled
     letter from `bcdfghjkmnpqrtvwx`, drop one of the two.
  6. finally, if it ends with `e` and length > 3, drop the `e`.
- Verified by prototype: 16 of 16 word families unify (parse/parses/parsed/parsing
  → `pars`; value/values/valued → `valu`; query/queries/queried/querying →
  `query`; try/tries/tried/trying → `try` …) and 200,000 random strings raised
  nothing. **Documented limits:** `configure` ≠ `config`; `speed` → `spe`;
  `news` → `new`; `using` unchanged; English only.
- **Frozen:** a future improvement ships under a new mode name (e.g.
  `stem2`). The rule table is committed in `docs/` and pinned by ≥ 100 vector
  pairs.
- **`normalize ∈ {None, "nfc"}`** on `rescore` and `quarantine`, applied to
  query and text *before* lower-casing. Unknown value → `config.invalid_value`.
  Documented margin: each runtime's Unicode database version may differ;
  vectors use ASCII/BMP/Hangul/astral text without case-special characters.

## 7. Audit truthfulness (ADR-008)

- `stage()` snapshots bound containers (lists, tuples, dicts, sets) at build
  time; `pipeline()` copies its stage list. A policy cannot change after it is
  fingerprinted.
- Fingerprint coverage additions: set/frozenset by sorted content (rendered
  `set{…}`, distinct from the dict form); a nested pipeline contributes its
  fingerprint via a `("pipeline", (fp,))` descriptor; a tiktoken tokenizer
  carries `__name__ = "tiktoken:<encoding|model>"`. **A pipeline with none of
  these keeps its exact current fingerprint.**
- tiktoken counting uses `disallowed_special=()`, so `"<|endoftext|>"` counts as
  ordinary text.
- **Trace dropped ids:** compute `lost = unidentified_out − unidentified_in`
  (survivors without the id minus input records that never had it). Only up to
  `lost` unmatched ids are treated as "survivor lost its id" (select stripped
  it); every other unmatched input id is reported dropped. Audit keys are
  unchanged.
- **Reported but not reproduced, deferred:** async `__call__` objects in
  `shaped`; trace pricing with the ambient tokenizer.

## 8. Enforcement (ADR-007) and release hygiene

**Vectors v2.** `parity/vectors.json` gains a `cases` array:
`{id, stage, args, input, expect | expect_error:{code}}`, plus pipeline cases
`{id, pipeline:[{stage,args}…], input, expect}`. The Python generator holds the
single case table; TypeScript and C# replay it through **one adapter per
stage** (args mapped to the port's call shape). Adding a case touches only the
generator. Callable-valued args remain hand-written edges. Existing sections
keep passing unchanged except the one vector in §4. `merge`, `shaped`,
`trace.report` gain cases (AC 22). C# keeps the int/float distinction from raw
JSON text; TypeScript cannot, so integer-valued floats stay out of v2 outputs.

**Hash-seed test.** `tests/test_determinism_processes.py` spawns ≥ 3
subprocesses with `PYTHONHASHSEED` 0, 1, 2 (never `python -I`, which drops
`PYTHON*` variables) over data containing sets, mixed types and unicode, and
asserts identical output hashes. Runs on the whole CI matrix.

**Generative property tests** (`tests/test_properties.py`, stdlib `random`):
purity (input deep-equal before/after), determinism, idempotence where it
holds, filter stages return a subsequence, `trim_to_budget` never exceeds the
budget except via `min_records`, `split`/`join` lossless with round-tripping
offsets. Seeds and case counts via env vars; failures print the seed; a
regression-seed list is committed. **Each property has a canary**: a
deliberately mutating/non-deterministic stage that the harness must catch, so
the tests are known able to fail.

**Differential fuzz.** `parity/generate_fuzz.py` emits a seeded random corpus
inside the documented parity envelope (ASCII plus BMP/astral letters; no
integer-valued floats, NaN, Inf, `-0`, ints > 2^53, case-special characters)
in the same `cases` format; CI generates it, TypeScript and C# replay it
(env var `CONTEXEL_FUZZ_CASES`; skipped locally when unset). Fixed seeds, bounded
(target < 60 s). Every divergence found is triaged to a port fix or an ADR-
recorded margin that narrows the domain — **never filtered silently**.

**Benchmarks (workstream F).** Inflected-query episodes: hit lists still come
from the target's original terms (the retrieval tool), while `rescore` receives
deterministic inflections of those terms (`…e→…ing`, `…s→…`, else `…ing`), so
exact-word matching fails by construction and stem matching is *measured*, not
assumed. The report states this measures inflection, not semantic paraphrase.
A hand-written baseline gains its own term-overlap scorer. Native-op counts are
computed; a check compares `site/benchmarks.html` and `README.md` numbers with
the generated results; the dataset fetch verifies a committed SHA-256.

**Release hygiene.** `tools/check_versions.py` (stdlib) asserts the seven
version locations agree (`pyproject.toml`, `contexel/__init__.py`,
`ts/package.json`, both entries of `ts/package-lock.json`, `ts/src/index.ts`,
`csharp/Contexel/Contexel.csproj`) and runs in CI on every push and in the
release gate. `contexel/py.typed` ships. `ruff` and `mypy` are **dev-only**
extras: need (lint/type gate CI lacks today; the Makefile that lints is
gitignored and skips `contexel/`), license MIT/MIT, never shipped, no runtime
weight; verify with `pip-audit` at slice time. The mypy error count is unknown
until measured; if clearing it is disproportionate, the slice reports it rather
than loosening the config silently.

## 9. Behavior changes (changelog "Behavior changes" list)

1. `allowlist` type-strict for bool vs number (vector change, §4).
2. `allowlist(allowed="str")` is one value, not characters.
3. `quarantine` now catches nested values containing newlines; `fields=[]`,
   invalid regex and an `into` collision now raise.
4. `rescore` unknown `match`, `fields=[]`; `max_tokens` negative/non-integer;
   other config errors now raise typed errors (a `None`/non-integer
   `max_tokens` raised a raw `TypeError` before and is now a `ConfigError`).
5. Fingerprints change only for pipelines binding sets, nested pipelines or a
   tiktoken tokenizer; post-construction mutation of bound containers no longer
   alters behavior.
6. Trace `dropped_ids` no longer under-reports; tiktoken no longer crashes on
   special-token literals.
7. **Tests:** C# assertions of the exact exception type
   (`Assert.Throws<ArgumentException>`) become `ThrowsAny<…>`; callers'
   `catch (ArgumentException)` is unaffected.

## 10. Failure modes

| failure | behavior | detection |
|---|---|---|
| bad shape, strict off | unchanged (compat) | docs; strict opt-in |
| strict flag on another thread | `pipeline`/`shaped` set it inside run | thread test |
| regex valid in Python, invalid in JS/.NET | `config.invalid_pattern` in that port | documented dialect margin |
| NFC differs across Unicode versions | margin | vectors limited to stable ranges; ADR-002 amendment |
| stemmer needs improvement | new mode name | frozen-mode policy |
| fuzz finds a port divergence | fix or ADR margin | CI red until triaged |
| a custom stage returns non-list | strict pipeline names the stage | strict test |

Blast radius: errors/validate touch every stage (mechanical, vector-covered);
text/stem are additive modules; fingerprint changes are limited to listed shapes.

## 11. Requirement traceability

| AC | Design element |
|---|---|
| 1, 5a | §4 allowlist, ADR-004 |
| 2–5 | §4 quarantine |
| 6–9 | §3, ADR-003 |
| 10–15 | §5, ADR-005 |
| 16–18b | §6, ADR-006 |
| 19–22 | §8 enforcement, ADR-007 |
| 23–27 | §8 benchmarks |
| 28–30 | §7, ADR-008 |
| 31–33 | §7, §8 release hygiene |
| 34–35 | §9, CI matrix |

## 12. Proposed slice order (finalized at G2)

S1 safety net (hash-seed test, property tests + canaries, vectors v2 + generic
runners, `merge`/`shaped`/`trace.report` vectors; **no behavior change**) →
S2 errors, strict, config validation, security-control fixes → S3 audit fixes +
tiktoken + release hygiene → S4 payload stages → S5 stemmer + normalize → S6
benchmarks → S7 differential fuzz. Each slice is independently green across all
three languages.

## 13. Out of scope (unchanged from the brief)
Semantic scoring; conversation stages; the assembler; presets and the
non-coding benchmark; cross-language fingerprints; new runtime dependencies;
publishing.
