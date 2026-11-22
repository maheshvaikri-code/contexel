> Filed 2026-11-22 from the Slice 4 review workspace for branch `feat/hardening-s4-payload-stages` (QA ran on head `d5eebcb`, before the fix wave; the controller's checks after the fix wave are in section 6). Sanitised: no user name, home or temporary path, e-mail address or agent identifier. Gate G5 QA (executed: mutation testing, a randomized differential check, adversarial probes).

# G5 QA Report - Foundation hardening Slice 4 (payload stages: `as_records`, `split`, `join`) @ d5eebcb

**QA Engineer** (fresh-context verifier, G5) - **Date:** 2026-11-22
**Build under test:** branch `feat/hardening-s4-payload-stages`, head `d5eebcb` (base `7b1a507` = main). Every mutant ran in a fresh `git archive d5eebcb` copy under `<tmp>` (build outputs stripped, `ts/node_modules` copied in); the repository itself was never written (`git status --short` empty before, during and after). No packages installed, no network.

## Verdict

**G5 QA: PASS.** No behavior defect was found in the Python canon, the TypeScript port or the C# port.

- Mutation testing: 79 mutants applied cleanly (0 apply failures). **75 killed, 4 survived: 3 equivalent mutants (P22, T6b, XC15) and 1 real test gap (XT24, TypeScript only).**
- Randomized differential check (TypeScript and C# against the Python canon): **0 mismatches** on every section for seeds 424242 and 7 (4,000 `split`, 1,500 `join`, 600 `as_records` cases each, per port). The controller later added seeds 20261121 and 99 and, after the fix wave, 20261121, 424242 and 99 again: 0 mismatches each time.
- Exploratory probes (inputs up to 5,000,000 characters in every mode, separator-only texts, `into`/`field` edge cases, nested lists, surrogates): everything matched the contract; nothing came near 20 seconds.

## 1. Baselines (untouched head copy)

~~~
Python (PYTHONPATH pointed at the copy; contexel.__file__ confirmed inside it)   678 passed
TypeScript (npm run build && npm test)                                          533 pass / 0 fail
C# (dotnet test, offline restore)                                               469 passed / 0 failed
parity/vectors.json regenerated on the copy                                      byte-identical to the committed file
~~~

## 2. Mutation testing

Each mutation was applied by a script that asserts the target text is found exactly once and keeps the file's line endings; every `diff -u` was kept. A mutant counts as SURVIVED only if the complete suite of its language is green (and, for Python canon mutants, a regeneration of `parity/vectors.json` was also compared with the committed file). "chg" means the regenerated vectors would change (so the shared vectors can see the mutant too).

### Python canon (42 mutants: 41 killed, 1 equivalent survivor)

| id | mutation | result |
|---|---|---|
| P1 | lines: chunk end without its separator | KILLED (26 failures; doc example + vectors chg) |
| P2 | a lone CR is a line boundary | KILLED (8; vector `split/lines_crlf_is_one_boundary_and_a_lone_cr_is_not`) |
| P3 | the wider `splitlines` separators are boundaries | KILLED (10) |
| P4 | paragraph run `{2,}` becomes `{1,}` | KILLED (11; `split/paragraphs_mixed_newlines`) |
| P5 | `{2,}` becomes `{3,}` | KILLED (11) |
| P6 | the `\r?` dropped from the run pattern | KILLED (5) |
| P7 | size cut at `size - 1` | KILLED (12; `split/size_astral`) |
| P8 | remainder chunk missing | KILLED (43) |
| P9 | remainder chunk doubled | KILLED (37) |
| P10 | empty text yields one empty chunk (lines/paragraphs) | KILLED (7) |
| P11 | `index` starts at 1 | KILLED (21) |
| P12 | `start` and `end` swapped | KILLED (26) |
| P13 | `into` conflict check removed | KILLED (4) |
| P14 | conflict check skipped for empty text | KILLED (3) |
| P15 | conflict check applied to non-string records | KILLED (3) |
| P16 | a non-string field raises | KILLED (4) |
| P17 | a non-string field is dropped | KILLED (4) |
| P18 | `always` ignored in `checked` | KILLED (12; `split/null_input_is_not_a_list`) |
| P19 | `keeps_ids` ignored in `traced` | KILLED (4; `trace_dropped_ids/an_expanding_split_never_hides_a_dropped_id`) |
| P20 | `join` appends the separator after the last part | KILLED (8) |
| P21 | `join` skips None | KILLED (3) |
| P22 | `join` routes strings through `tokens.serialize` | SURVIVED, **equivalent**: `serialize` returns a string unchanged |
| P22b | closest faithful form: `json.dumps` for string values | KILLED (20) |
| P23 | `as_records` copies the mapping | KILLED (1; unit test only, vectors same) |
| P24 | `as_records` wraps mapping items | KILLED (3) |
| P25 | `as_records` accepts bytes | KILLED (1; unit test only) |
| X1 | size mode drops its remainder | KILLED (13) |
| X2 | size mode yields one empty chunk for empty text | KILLED (2; unit test only) |
| X3a-f | one `splitlines` separator at a time is a boundary (0x85, U+2028, 0x0B, 0x0C, 0x1C, U+2029) | all KILLED (3 each) |
| X3g, X3h | 0x1D, 0x1E (splitlines separators outside the contract list) | KILLED (1 each; unit tests only) |
| X6 | `size=True` accepted | KILLED (3; vector `split/size_true_is_not_an_integer`) |
| X8 | `join` renders a missing field as the empty string | KILLED (5) |
| X9 | a pass-through record is copied instead of returned as the same object | KILLED (1; unit test only) |
| X10 | `as_records` ignores `field` for strings | KILLED (4) |
| X11 | empty `field` check removed | KILLED (3) |
| X15 | contradictory-size check removed | KILLED (6) |

### TypeScript (21 mutants: 19 killed, 1 equivalent, 1 real gap)

| id | mutation | result |
|---|---|---|
| T1 | size counted in UTF-16 units | KILLED (10; `case split/size_astral`) |
| T2 | offsets in UTF-16 units | KILLED (10) |
| T3 | a surrogate pair cut in half by the size mode | KILLED (10) |
| T4 | a paragraph run of one newline counts | KILLED (11) |
| T5a-c | `Object.hasOwn` replaced by `in` (split read, join read, conflict check) | all KILLED (1-2 each; own-properties-only tests) |
| T6a | chunk `into` set by plain assignment (`__proto__`) | KILLED (1) |
| T6b | chunk `field` set by plain assignment | SURVIVED, **equivalent**: the spread `{...r}` has already made `field` an own writable data property, so assignment overwrites it even for `__proto__` (confirmed in node) |
| T7 | `always` ignored in `checked` | KILLED (14) |
| T8 | `keepsIds` ignored in `traced` | KILLED (3) |
| T9 | a lone CR is a line boundary | KILLED (7) |
| T10 | `join` skips null | KILLED (2) |
| XT11 | `asRecords` keeps any object list item | KILLED (3) |
| XT12 | `asRecords` accepts Uint8Array | KILLED (2) |
| XT14 | remainder chunk dropped | KILLED (53) |
| XT17 | pass-through record copied | KILLED (3) |
| XT18 | fractional size accepted | KILLED (4) |
| XT19 | contradictory-size check removed | KILLED (5) |
| XT23 | the `\r\n` unit dropped from the paragraph scan | KILLED (8) |
| **XT24** | `isPair` accepts a high surrogate followed by another high surrogate | **SURVIVED: real test gap** (533 pass, 0 fail). Fixed after QA, see section 6 |

### C# (16 mutants: 15 killed, 1 equivalent)

| id | mutation | result |
|---|---|---|
| C1 | size counted in UTF-16 units | KILLED (10) |
| C2 | offsets in UTF-16 units | KILLED (10) |
| C3 | a paragraph run of one newline counts | KILLED (12) |
| C4 | `IndexOf('\n')` (char, ordinal) replaced by the culture-sensitive `IndexOf("\n")` | KILLED (4), **only by the wall-clock linearity tests** (the whole suite took 5m46s); every functional test passed. Do not remove those tests |
| C5 | `keepsIds` ignored | KILLED (3) |
| C6 | `always` ignored | KILLED (13) |
| C7 | a lone CR is a line boundary | KILLED (7) |
| C8 | `join` skips null | KILLED (2) |
| C9 | `byte[]` accepted as a list | KILLED (1) |
| XC11 | `join` puts the separator before every part | KILLED (8) |
| XC12 | remainder chunk dropped | KILLED (43) |
| XC13 | pass-through record copied | KILLED (2) |
| XC14 | `into` conflict check removed | KILLED (3) |
| XC15 | `size is bool ||` removed | SURVIVED, **equivalent**: `bool` is neither `long` nor `int`, so the next clause rejects it |
| XC16 | contradictory-size check removed | KILLED (7) |
| XC20 | `size` cast unchecked instead of clamped at `int.MaxValue` | KILLED (1) |

### Totals and weak spots

Listed mutants P1-P25, T1-T10, C1-C9 were all mapped and applied (T5 and T6 were split into five sub-mutants); every one of them is killed except the equivalent P22 (its faithful form P22b is killed) and T6b. QA added 32 mutants of its own (P22b and the X series). Per language: Python 41 of 42 killed, TypeScript 19 of 21, C# 15 of 16; the four survivors are P22, T6b and XC15 (equivalent) and XT24 (real gap). Mutants killed only by Python unit tests and not by the shared vectors: P23, P25, X2, X3g, X3h, X9 (TypeScript and C# equivalents of P23 and P25 were mutated and killed by their own unit tests; the remaining ones were not checked in TypeScript and C#).

## 3. Survivors and proposed kills

- **XT24 (TypeScript, real):** `isPair` accepting high+high is caught by no test or vector, and the differential alphabet has no lone surrogates. Proposed test: `split([{text: HIGH + HIGH + LOW}], {by: "size", size: 1})` must give a lone high surrogate at offsets 0-1 and then the astral character at 1-2 (the mutant gives `[HIGH+HIGH]`, then `[LOW]`). C# uses the strict `char.IsSurrogatePair`, so only TypeScript is exposed. **Added after QA** (section 6).
- P22, T6b, XC15: equivalent mutants, no test needed (arguments above).

## 4. Randomized differential check

Scratch tool (not part of the repository): seeded generators produce `split` texts over an alphabet of newlines, carriage returns, astral and accented characters, the `splitlines` separators and a zero-width joiner (lengths up to 4,000, all three modes), `join` cases over random JSON values, fields and separators, and `as_records` payloads; the Python canon answers; TypeScript and C# answer the same cases; the results are compared as canonical JSON.

| seed | split | join | as_records | TypeScript | C# |
|---|---|---|---|---|---|
| 424242 | 4,000 | 1,500 | 600 | 0 mismatches | 0 mismatches |
| 7 | 4,000 | 1,500 | 600 | 0 mismatches | 0 mismatches |

## 5. Exploratory probes (Python canon and TypeScript build)

Everything matched the contract and the README. Examples:

- Separator-only texts: `"\n\n\r\n\r"` by lines gives `"\n"`, `"\n"`, `"\r\n"`, `"\r"` at 0-1, 1-2, 2-4, 4-5; `"\n\n\n"` by paragraphs is one chunk; `"\r\r\n\n"` by paragraphs is one chunk (0-4), by lines `"\r\r\n"` then `"\n"`.
- `size` larger than the text gives one chunk; a huge size with `lines` raises `config.contradictory`; `True`, 0 or a missing size with `by="size"` raises `config.invalid_value`.
- `into` already present: a non-string field passes through; a string field raises `input.field_conflict`, also when the text is empty; `into == field` raises for a string field and passes through otherwise.
- `split` then `join` with `sep="|"` round-trips as `"a\n|b\n"`.
- `as_records` of a nested list wraps nested lists and null as `{text: ...}` and keeps mappings; sets, bytearrays and typed arrays raise `input.not_list`; `field=""` or a null field raises `config.invalid_value`; shape errors win over a bad `by`.
- 5,000,000 characters: Python lines 1.89 s, paragraphs 0.42 s, size 0.65 s; TypeScript lines 0.86 s, paragraphs 0.16 s, size 0.25 s; nothing hung.
- TypeScript record shapes: frozen, null-prototype and class-instance records work with `split` and `join`; an own `__proto__` field or `into` becomes an own data property with the prototype intact.

Minor observations (none contradicts the contract): `size=2.0` is rejected by Python but accepted by TypeScript (JavaScript cannot tell 2.0 from 2; documented); `join` of a value nested 5,000 deep raises a raw `RecursionError` in Python and 20,000 deep a `RangeError` in TypeScript (pre-existing `tokens.serialize`, see the security review); `join` of Python bytes renders `"b'hi'"` (existing serializer behavior).

## 6. After the fix wave (controller's own checks on head `520ab28`)

The code-review and security gates produced one fix wave (see the code review and security review). The QA mutants were NOT re-run on the new head; instead:

- XT24's test was added and shown RED under the mutation by the implementer, and re-verified by the re-reviewer by reading `isPair`.
- Totals: Python 685, TypeScript 536, C# 475 (0 warnings on a clean rebuild), 130 shared vector cases (the first 128 equal `d5eebcb`'s, the 79 original cases and every other section equal main's, regeneration stable); ruff, mypy, site and version checks clean.
- Differential check re-run on the final head, seeds 20261121, 424242 and 99: 0 mismatches in every section, for TypeScript and C#.
- The Python paragraph cut was replaced by a hand-written one-pass scanner: peak memory on 4,000,000 newlines went from 587 MB (the regex, measured) to 0.0 MB, and it is faster than the regex on every input measured (0.02 s against 0.09 s on prose, 0.19 s against 0.57 s on 4M newlines). The re-reviewer proved it equivalent to `(?:\r?\n){2,}` by exhaustive comparison over all 29,524 strings of length 0 to 9 over {a, newline, carriage return} and 200,000 random texts.

## 7. Not verified

Linux and macOS, Python 3.9 and 3.10, Node 18 and 20 (the first CI run of this branch is the human's push); `pip-audit` and `npm audit` (no network; no dependency was added).
