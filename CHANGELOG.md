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

### Added — audit truthfulness and release hygiene (ADR-008)
- The audit no longer says something false: a trace's `dropped_ids` reports a
  drop that an unrelated id-less record used to hide, a policy fingerprint
  covers sets, nested pipelines and the tiktoken encoding, and a stage keeps a
  private copy of what is bound to it (Behavior changes 8 to 10). The shared
  parity vectors gain a case kind, `trace_dropped_ids`, that asserts each
  stage's dropped ids in all three languages (79 cases in all).
- `tools/check_versions.py` (standard library) fails when the seven version
  locations of the three packages disagree (`pyproject.toml`,
  `contexel/__init__.py`, `ts/package.json`, both entries of
  `ts/package-lock.json`, `ts/src/index.ts`, `csharp/Contexel/Contexel.csproj`),
  naming the file. It runs on every push to main and every pull request in the
  new CI job `hygiene`, and in the release gate before any package is
  published.
- `contexel/py.typed` ships in the wheel (the package is typed), and `ruff` and
  `mypy` are configured and pass on `contexel/`. They live in a new dev-only
  extra, `pip install "contexel[lint]"` (MIT, never a runtime dependency); the
  CI job `hygiene` runs them on Python 3.12 and checks the built wheel. mypy
  2.x cannot target Python 3.9, so it checks against 3.10 and the Python 3.9
  test legs prove the runtime.

### Added — payload stages (ADR-005, all three languages)
- `as_records`, `split` and `join` (TypeScript `asRecords`, `split`, `join`; C#
  `Text.AsRecords`, `Text.Split`, `Text.Join`) carry a log, a web page or a plain
  string through every existing stage and back. `as_records` turns a string, a
  mapping or a list into records; `split` cuts the text of each record into chunk
  records by lines, paragraphs or code points, keeping the trailing separator,
  the parent's fields and an `{index, start, end}` offset, so joining the chunks
  rebuilds the text byte for byte; `join` turns records back into one string.
  The boundaries are the same in all three languages: a line ends after `\n`
  only, a paragraph after a run of two or more newlines, and offsets and sizes
  count code points.
- They are new, so they check their input in every mode, not only in strict
  mode: a non-list raises `input.not_list`, a non-mapping item
  `input.not_mapping`, and a record whose text is a string and that already has the `into` key
  raises `input.field_conflict`. `as_records` and `join` are the entry and exit
  points: call them outside `pipeline` (a strict pipeline rejects a stage that
  returns a string, naming it); `split` is an ordinary traced stage.
- Under `trace(id_field=...)`, `split` is attributed exactly per distinct id
  value (two limits are under Known limitations): it keeps every id,
  so an empty-text record that vanishes is reported as dropped even beside
  id-less records that `split` expanded. (Without this the id-less allowance of
  Behavior change 8 would have hidden that drop.) The shared vectors pin it in
  all three languages.
- The shared vectors gain `as_records`, `join` and `text_pipeline` cases and
  accept `split` as a stage: 51 new cases (130 in all), among them raw log text
  through `as_records`, `split`, `dedupe`, `rescore`, `rank`, `trim_to_budget`
  and `join`, identical in all three languages and inside its token budget.

### Added — stemming and Unicode normalization (ADR-006, all three languages)
- `rescore(match="stem")` (TypeScript `match: "stem"`, C# `match: "stem"`) reduces
  every word of the query and of the text to its stem before counting, so `parse`,
  `parses`, `parsed` and `parsing` are one term and `values` matches `value`. The
  stemmer is a small English suffix stemmer (plurals `sses`, `ies`, `ied` and `s`;
  `ing` and `ed` with a vowel-bearing base of at least three code points and consonant
  undoubling; a final `e`), identical in all three languages, **frozen** (an
  improvement ships under a new `match` name) and documented rule by rule, with
  worked examples that a test runs, in `docs/stemmer-rules.md`. Scoring, IDF, the
  proximity bonus and the rounding are those of `match="word"`. The default
  `match="word"` and every existing output are unchanged.
- `normalize="nfc"` on `rescore` and `quarantine` applies Unicode NFC. In `rescore`
  it applies to the query and the text before lower-casing, so precomposed and
  decomposed spellings of the same word match. In `quarantine` the text is scanned
  as given and also in its NFC form, so a precomposed pattern also finds a decomposed
  spelling; the patterns are never normalized, and the option can only widen
  detection. The default `None` (TypeScript and C# `null`) changes nothing, and any
  other value raises `config.invalid_value`. In C#, `string.Normalize` throws on a
  lone surrogate and on U+FFFE where Python and JavaScript pass them through;
  contexel normalizes the text around such a character, so no input raises.
- The shared vectors gain a `stem` case kind (223 word-to-stem pairs in 16
  groups, one per rule and edge: code-point lengths, ignorable characters, case,
  every undoubling letter) and rescore and quarantine cases for `match="stem"` and
  `normalize` (174 cases in all), identical in all three languages. `stem` itself is not part of the
  public API: it is internal in TypeScript and C#, and in Python `contexel.stem`
  is the module.

### Added — honest benchmarks (brief AC 23 to 27)
- **Inflected-query episodes.** A second set of ground-truth episodes keeps the
  hit lists (the retrieval tool searched with the target's own words) but hands
  the shaper a deterministic inflection of each term (`parse` becomes `parsing`,
  `returns` becomes `return`, anything else gets `ing`;
  `benchmarks/inflection.py`), so exact-word matching fails by construction and
  `rescore(match="stem")` is measured, not assumed. A term is used only when it
  is a plain lower-case word, the frozen stemmer maps it and its inflection to
  one stem, and the inflection is not a word of the target's own text. The
  report says what it measures: inflection robustness, not semantic paraphrase.
  Exact-word matching drops sharply on these episodes and `match="stem"`
  recovers it (the table is in `benchmarks/COMPARISON.md`).
- **A fair hand-written baseline.** The hand-written row exists in two forms:
  one that trusts the tool's score (as before) and one with its own
  term-overlap scorer (lower-cased whole words, ties keep the incoming order)
  and the same budget trimming, so contexel's `rescore` is compared with another
  rescorer, not only with none.
- **Native-operation counts are computed, not typed.** Each implementation is an
  ordered list of steps (the lists are in `benchmarks/competitors.py`;
  `benchmarks/opcount.py` holds the step type and the counter). A step counts as native when
  running it enters the library's own code (`sys.setprofile` over a small fixed
  sample), as glue when it is hand-written; an operand conversion, or a library
  feature that serves none of the six operations, is reported but never counted.
  The comparison gains an "Operations" table (native, glue, not done, other
  native steps, conversions); the old hand-typed capability matrix survives only
  for the libraries the benchmark does not run, labelled as documentation.
- **Published numbers are generated and checked.** `python -m benchmarks.competitors`
  and `python -m benchmarks` write `benchmarks/COMPARISON.json` and
  `benchmarks/RESULTS.json` and render `COMPARISON.md` and `RESULTS.md` from
  them. The tables in the README and on the site are generated blocks
  (`<!-- benchmark:NAME:start -->`), the remaining prose numbers and qualitative
  sentences ("the only row with full marks in every outcome column", "the two
  slowest budget-compliant rows are contexel and the hand-written term-overlap
  scorer") are registered claims, and `tools/check_benchmark_numbers.py` (also a
  test, so CI runs it) fails when anything published differs from the results,
  when a number with a benchmark unit (ms, msec, milliseconds, %, percent, a
  multiplication sign or a trailing x), also inside the title, alt, aria-label
  or content attribute of an HTML element or inside an entity, or a bare numeric table cell appears outside a generated block or a
  registered claim, when a report is not what its JSON renders, or when the
  results were produced with a dataset other than the pinned one. `--write`
  regenerates the blocks.
- **Checksummed dataset.** `benchmarks/fetch_dataset.py` verifies the SHA-256
  committed in `benchmarks/dataset.sha256` every time the cache is used, and
  writes a download to a temporary name that is moved into place only after the
  check; a mismatch raises `DatasetChecksumError` and nothing is read. The
  digest reads every line ending as LF so that it does not depend on the
  operating system and still verifies a cache that an earlier version wrote with
  CRLF on Windows. New downloads are written with LF line endings on every
  operating system.

### Changed — benchmark claims (documentation only)
- "sub-20 ms import" (PyPI README, home page) is now "about 20 ms": contexel's
  import measured between 19.3 and 20.8 ms across runs, so "sub-20" held only on
  some of them. The check accepts a stated figure within 25% of the measured one.
- The benchmark tables gain a "Fill" column, the hand-written (term overlap) row
  and computed "Native ops"; "hand-written glue" is now "hand-written". The home
  page's "the only row green across every column" is now "the only row with full
  marks in every outcome column", and is checked against the results.
- "contexel is the slowest budget-compliant row" is now "the two slowest
  budget-compliant rows are contexel and the hand-written term-overlap scorer,
  in an order that can change from run to run": the margin between the two rows
  was small, so a sentence naming one of them as the slowest flipped with
  run-to-run noise. The benchmark prose also no longer says the timings "vary by a few
  percent": they vary with machine load and from run to run.
- The PyPI README now names the hand-written term-overlap baseline with its
  figures, says that exact-word matching drops on inflected queries and that
  match="stem" recovers them (on a second set of episodes built only from terms
  the stemmer maps to one stem, so this is not a coverage figure for the
  stemmer), and says the comparison is one corpus and one task.

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
   (it silently ran substring matching; `"stem"` is now a real mode, see Added),
   `fields=[]` for `rescore`, a `max_tokens` or
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
8. `trace(id_field=...)` no longer under-reports `dropped_ids`. A record dropped
   while some other surviving record never had the id field used to be
   reported as not dropped (the id-less survivor was assumed to be the one that
   lost its id). Now only as many unmatched ids as the stage produced extra
   id-less survivors (beyond the id-less records it was given) are explained
   away, the first ones in input order, and every other unmatched id is
   reported dropped. All three languages, identical up to id-key equality
   (see Known limitations); the audit keys are unchanged. In C#, a null record
   in the input of a traced stage is now counted as id-less instead of
   throwing a `NullReferenceException` (the built-in stages still throw on a
   null item). An
   audit recorded before this change may have under-reported. A stage that
   ADDS id-less records can still hide up to that many drops: a black-box stage
   leaves that ambiguity, and the bound is the number it added. The rule
   counts id-less records, so it is an approximation in both directions: a
   black-box stage that both strips an id from a survivor AND drops an id-less
   record can now cause that survivor to be reported in `dropped_ids` although
   it survived (the built-in stages never do either; `select` strips ids but
   never drops id-less records). That is deliberate: a reported drop is the safe
   side of the audit. A stage that adds or removes id-less records should keep
   its ids.
9. Policy fingerprints cover more, so a pipeline that binds one of these has a
   new fingerprint: a `set` or `frozenset` in Python (it used to hash as the
   type name `set`, so every set collided), a `Set` in TypeScript (it used to
   hash as `{}`) and any `ISet<T>` or `IReadOnlySet<T>` in C# (it used to hash
   as a list in enumeration order) are hashed by their sorted contents, at any
   depth; a nested pipeline contributes its own fingerprint (Python and
   TypeScript: a pipeline that IS the stage, used directly in a stage list as
   in `pipeline([..., inner, ...])`; C#: a stage built from `inner.Run`), where
   it used to contribute only the word `run` (a pipeline wrapped by
   `stage(inner)` in Python or `stage(inner, {})` in TypeScript, or passed as
   a keyword argument or parameter, still hashes as its name `run`); and a Python
   tiktoken tokenizer is named `tiktoken:<encoding or model>` instead of
   `<lambda>`. A pipeline that binds none of these keeps its exact fingerprint
   (golden tests in all three languages). Fingerprints recorded earlier for the
   changed shapes no longer match.
10. `stage()` copies the plain containers bound to it, and `pipeline()` copies
    its list of stages, in Python and TypeScript, so changing your own list,
    dict or set afterwards no longer changes the behavior (it used to, with the
    fingerprint unchanged). Code that relied on editing a bound list after
    building the stage must build the stage again. Only plain containers are
    copied: a subclass, a custom object, a function, a TypeScript class
    instance or `Map`, and the elements of a TypeScript `Set` stay live. C#
    cannot copy a closure: its fingerprint is computed once when the pipeline
    is constructed. Further facts:
    - A stage that writes results into a bound list or dict for the caller to
      read now writes into its own copy, and two parameters bound to the SAME
      object are no longer the same object inside the stage. Bind a custom
      object (it is not copied) to collect output or to share state.
    - Python `pipeline()` now copies its list of stages, so a pipeline built
      from a generator of stages runs its stages (before, building the
      fingerprint consumed the generator and the pipeline silently ran
      nothing).
    - Copying is by EXACT type. Python: only an exact list, tuple, dict and set
      (a frozenset is immutable and returned as it is). TypeScript: only an
      exact Array, Set (the shell; its elements are not copied) and plain or
      null-prototype object; a Set or Array SUBCLASS stays live. An own
      `__proto__` key (as `JSON.parse` produces) is kept as an own key in the
      copy.
    - A subclass is hashed by its contents at build time but not copied, so
      changing it later still changes behavior without changing the
      fingerprint.
    - TypeScript: getters on a bound plain object are read once at build, and
      symbol keys and non-enumerable properties are not copied (they were never
      hashed either).
11. Python `tokens.tiktoken_tokenizer()` counts text such as `"<|endoftext|>"`
    as ordinary text (`disallowed_special=()`) instead of raising `ValueError`;
    counts for text without such literals are unchanged.

### Compatibility
C#: the `Shaped.Wrap` overloads gained an optional `strict` parameter. That is
source-compatible, but a caller compiled against the previous release must be
recompiled (the method signatures changed). The new
`Allowlist(records, field, string allowed)` overload makes a call with a
literal `null` third argument, `Stages.Allowlist(r, "f", null)`, ambiguous
(compile error CS0121) where it compiled before; cast it
(`(IEnumerable<object?>)null`) or pass a real list.

C#: `Stages.Rescore` and `Stages.Quarantine` gained a trailing optional `normalize`
parameter; callers recompile unchanged, but an assembly compiled against an
earlier version must be recompiled (binary compatibility is not preserved).

### Known limitations
Documented, not fixed in this slice. `quarantine` is a tripwire for literal
markers, not a security boundary, and the three ports do not catch exactly the
same obfuscations.
- The stemmer is English only and not a lemmatizer: `configure` and `config` do
  not meet, `speed` becomes `spe`, `news` becomes `new`, `series` becomes `sery`,
  `using` is left alone, and irregular forms (`ran`, `mice`) are not handled; it
  expects lower-case input. These are frozen on purpose: a better stemmer is a new
  `match` name, not an edit.
- `normalize="nfc"` depends on each runtime's Unicode database (Python's
  `unicodedata`, the JavaScript engine's, .NET's): text that uses characters added
  to Unicode recently can normalize differently. The shared vectors use accented
  Latin, Hangul, combining marks and an astral compatibility ideograph, which
  normalize the same in every version in use. Only NFC is offered (no NFKC).
- Cost. Each runtime's own NFC reorders a run of combining marks in time that
  grows with the square of the run: a text made of a long alternating run of two
  kinds of combining marks (for example 128,000 of U+0301 and U+0323) takes
  seconds with `normalize="nfc"` on, in Python, TypeScript and C# alike, where
  the default takes milliseconds. Real text does not contain such runs.
  `normalize="nfc"` is opt-in; if you pass text you do not control, cap its size
  first.
- In C#, a letter outside the Basic Multilingual Plane (a surrogate pair, such as
  a mathematical script letter) is not a word character for .NET's regular
  expressions, so a word is split at it wherever `rescore` tokenizes (the query in
  every `match` mode, the text in `"word"` and `"stem"`), where Python and
  TypeScript keep it in the word. This is the word pattern's existing margin,
  found again by a randomized comparison of the ports; the stemmer itself counts
  code points identically in all three languages.
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
- Fingerprint scope (ADR-008): the ambient tokenizer and serializer
  (`set_tokenizer`, `scoped`) are not part of a pipeline's fingerprint; a
  pipeline bound as a parameter value (not as a stage) hashes as the word `run`
  in Python; a Python container subclass is hashed by value but not copied; a
  C# lambda that calls another pipeline's `Run` is opaque; and nothing hashes
  the code inside a stage function, only its name, so two lambdas share
  `<lambda>`. The fingerprints stay language-local.
- Nested pipelines in Python and TypeScript fingerprints: only a pipeline that
  IS the stage (used directly in a stage list, `pipeline([..., inner, ...])`)
  contributes its own fingerprint. A pipeline wrapped by `stage(inner)`
  (Python) or `stage(inner, {})` (TypeScript), or passed as a keyword argument
  or parameter, is still hashed by its name `run`, so two different inner
  pipelines bound that way share a fingerprint.
- TypeScript `stage()` copies only an exact array, plain or null-prototype
  object and `Set` shell: typed arrays, `Buffer`, objects from another realm
  (`node:vm`) and any other non-plain object are not copied, so changing them
  later changes the behavior without changing the fingerprint.
- Trace attribution compares ids by equality, and the languages differ on what
  is equal: Python and C# treat 1, 1.0 and True as one id (and 0 and False),
  TypeScript keeps them apart, and a list-valued id collides with the string
  of its `repr` (Python) or JSON (TypeScript). A crafted id can therefore make
  the audit name a different record than the one dropped; the number of
  dropped records is still right.
- Python: ids that all hash to the same value make `trace` attribution (and
  `dedupe`) quadratic (4000 colliding integer ids took about 0.26 s, 8000
  about 1.0 s). Do not feed untrusted, attacker-chosen id values to a pipeline
  without a bound on the input size.
- The `lint` extra's version ranges float, so a new ruff rule or mypy release
  can turn the `hygiene` job red without a code change (pin them if
  reproducibility matters more than freshness).
- No test or check guards the CI workflow steps themselves: removing the
  `check_versions` step from `ci.yml` or `release.yml` would fail no test. The
  first CI run and code review are the guard.
- Python fingerprints: a dict KEY is still rendered by `repr`, so a frozenset
  used as a dict key is hash-seed dependent and a custom-object key embeds a
  memory address (pre-existing). The elements of a list, tuple or set are
  joined by a plain comma, so a callable named "1,2" collides with the elements
  1 and 2 (pre-existing, contrived).
- TypeScript fingerprints: a `Map`, `Date` or `RegExp` has no own enumerable
  entries and renders as `{}`, so they collide with each other and with an
  empty object. A `Set` that contains a cyclic structure now throws
  `RangeError` when the stage is built (arrays and objects already did).
  TypeScript keeps `1` and `true` (and `0` and `false`) as different
  dropped-id keys where Python and C# treat 1, 1.0 and True as one key (and 0
  and False) (outside the shared vectors).
- C# fingerprints: a set renders as text and so collides with the literal
  string of the same text (a `HashSet<string>` {"a"} and the string
  `set{"a"}`; Python does not). A delegate INSIDE a list or dictionary is named
  by its CLR type, not its method, so different delegates there collide (a
  delegate as a top-level parameter or inside a set is named by its method). A
  nested pipeline is detected for any delegate bound to a Pipeline (for example
  `inner.Run`), a multicast delegate reports only its last target, and a list
  or set that contains itself overflows the stack (before this slice as well).
- `tools/check_versions.py` reads the first `<Version>` element of the csproj
  and the first line-start `__version__` of `contexel/__init__.py`; a
  commented-out `<Version>` or a `<PackageVersion>`/`<VersionPrefix>` override
  is not detected (none exist today).
- Payload stages: the chunks of one parent share its id, so under
  `trace(id_field=...)` a chunk dropped by a later stage is reported under its
  parent's id and one stage's `dropped_ids` can list the same id more than once.
  `rank` reorders chunks by score; restoring reading order needs a key function
  over `chunk.start` (a dotted `rank` path is not supported). There are no
  overlapping windows and no token-sized chunks: they break losslessness or need
  a tokenizer all three languages share.
- Payload stages, per language: a "mapping" is a `Mapping` in Python, a plain
  object in TypeScript (a `Map`, `Set`, `Date`, typed array or class instance
  is `input.not_list` for `as_records`) and a `Dictionary<string, object?>` in
  C#; TypeScript has one number type, so it accepts `size: 2.0` as 2 where
  Python rejects the float; a lone surrogate counts as one code point in every
  language but lies outside the parity vectors.
- Payload stages, trace: `split` is attributed exactly per distinct id value
  only. Ids are counted by value, so with duplicate input ids a record that
  vanished can be hidden by a sibling's chunks of the same id (an empty-text
  record next to a two-line record with the same id reports nothing dropped);
  and an `id_field` that is the split `field` itself is rewritten by the split,
  so a parent cut into several chunks is reported dropped (the safe side).
- Payload stages, resources (measured on a development machine; orders of
  magnitude, not guarantees): `split` has no cap and makes one record per
  boundary. At one chunk per input character a 1,000,000-character text retains
  roughly 440 MB in Python, 140 MB in TypeScript and 540 MB in C#, and time is
  linear (about 0.4 to 2 seconds per million chunks). Each chunk is a copy of its
  parent record, so anything that prices or serializes each chunk in full (a
  `trace`, `trim_to_budget`) costs about the number of chunks times the size of
  the parent's other fields: with a 50,000-character side field and 4,000 chunks
  a traced `split` took about 0.6 to 2 seconds, and the cost grows with both.
  Cap the input size before `split` when the text is untrusted, and keep only
  the fields you need (`select`) before it. The memory of the Python paragraph
  cut no longer grows with the length of a newline run (it used a backtracking
  regex earlier in this slice). A cap option may be considered later.
- TypeScript `split` and `join` check their items as every TypeScript stage
  does: any object that is not an array counts as a record and is read through
  its own properties, so a `Map` or `Date` item makes `split` pass it through
  untouched and `join` skip it, while `asRecords` accepts only plain objects as
  the whole input (a `Map` there raises `input.not_list`). Typed callers are
  protected by the type system.
- The benchmark's inflected episodes are synthetic: the rule produces words
  nobody writes (`partialing`), so the figures show what the stemmer reaches on
  inflection and say nothing about synonyms, paraphrase or real queries. The
  episodes come from one corpus, and the timings are the best of three runs on
  one machine and vary with machine load and from run to run (the other columns
  do not vary). The dataset check pins the JSONL cache derived from the Hugging
  Face parquet export, so the parquet file is parsed before it is verified;
  pinning the parquet digest too needs a one-time download and is recorded as a
  follow-up. The number check is unit-based: it covers the generated blocks, the
  registered claims, any number with a benchmark unit (ms, µs, ns, %, x) and any
  bare numeric table cell. It does not check other prose: figures in seconds
  (the hand-typed cost figures for very long inputs in the README's Limits
  paragraph about `split`), numbers without a unit and numbers in words. The
  home page's hand-typed "~2.4 µs per record" cost of the tenant-isolation
  plumbing, which no benchmark measures, is removed. The stemmer, the inflection and the scorer are measured on
  English technical text only.

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
