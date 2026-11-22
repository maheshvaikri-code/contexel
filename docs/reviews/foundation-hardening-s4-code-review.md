> Filed 2026-11-22 from the Slice 4 review workspace for branch `feat/hardening-s4-payload-stages` (per-task reviews on the task commits, G4 whole-branch review at head `d5eebcb`, scoped re-review of the fix wave at head `520ab28`; commit hashes in this document are those of the branch after three subjects of the fix wave were reworded to fit the 72-character limit). Sanitised: no user name, home or temporary path, e-mail address or agent identifier. Gate G4 (fresh-context, severity-ranked, adversarial review).

# G4 Code Review - Foundation hardening Slice 4 (payload stages: `as_records`, `split`, `join`)

**Plan:** `docs/superpowers/plans/2026-11-21-foundation-hardening-s4-payload-stages.md` - **Brief:** ACs 10 to 15 and 34 of `docs/briefs/foundation-hardening.md` - **ADRs:** 005 (accepted by this slice), 008 (amended)
**Range:** `7b1a507` (main, Slice 3 merged) to `520ab28`; 12 commits: five tasks (`1ba0d45`, `f639fa9`, `8629c36`, `b6405f3`, `c7e36ca`), two per-task fix commits (`55dc59a`, `d5eebcb`), five fix-wave commits (`619d94d`, `567c9d5`, `125f3a1`, `97d5590`, `520ab28`).

## Outcome

**Ready to merge: yes, after the fix wave, which is done.** The whole-branch review found no Critical finding and no defect in any of the three implementations, and confirmed that no existing behavior changed. It reported one Important finding (a gap in the shared vectors) and a set of Minor findings; the fix wave resolved the Important finding and the Minor findings the reviewer recommended, and a scoped re-review of the fix wave verdicted all 13 findings ADDRESSED with no Critical or Important breakage.

## 1. How the work was reviewed

| Gate | Who | Result |
|---|---|---|
| Per-task review (spec compliance and quality), tasks 1 to 5 | fresh reviewers, one per task | Tasks 1, 2, 3 approved first time (16 Minor findings and observations deferred); Task 4 needed one fix round (2 Important); Task 5 approved with 2 Important (documentation wording) fixed in one round |
| G4 whole-branch review at `d5eebcb` | most capable model, read the plan, the brief and the full diff | With fixes: 1 Important, 9 Minor items |
| G5 QA (mutation, differential) | see `docs/qa/foundation-hardening-s4-qa.md` | Pass: 75 of 79 mutants killed, 3 equivalent survivors, 1 real gap (fixed) |
| G5 security | see `docs/reviews/foundation-hardening-s4-security-review.md` | Approve with conditions (met) |
| Fix wave, then one scoped re-review at `520ab28` | most capable model | All 13 findings addressed; 3 Minor wording nits parked |

The controller checked every task itself before dispatching its review: the changed files were compared byte for byte with the plan's code blocks (a replay tool applied the plan's blocks to a fresh copy of main), the three suites were run, vectors were regenerated and compared, and the commit was checked for subject length, trailers and personal data.

## 2. Per-task review results

| Task | Commit | Result | Findings |
|---|---|---|---|
| 1 Python canon | `1ba0d45` | approved, no Important | 5 Minor deferred (duplicate-id wording of `keeps_ids`, an unused test helper, the lines-mode property check accepting an unsplit last chunk, a missing-field passthrough case, `traced` returning `Any`) |
| 2 TypeScript port | `f639fa9` | approved, no Important | 4 Minor and 2 observations deferred (paragraph wide-separator coverage, no literal `constructor` test, wall-clock bounds, cross-realm plain objects) |
| 3 C# port | `8629c36` | approved, no Important | 4 Minor and 1 observation deferred (`ExpandoObject`, theory coverage, wall-clock bounds, canary shape) |
| 4 shared vectors and runners | `b6405f3`, fix `55dc59a` | 2 Important, fixed in one round | no shared case pinned shape-before-configuration for `split` and `as_records`; `size` of `true` and `"3"` was pinned only by per-language unit tests. Five error cases were appended (49 new cases, 128 in all instead of the plan's 44 and 123): ruling below |
| 5 documentation | `c7e36ca`, fix `d5eebcb` | 2 Important (plan-mandated wording), fixed in one round | the `into` conflict applies only when the record's text is a string; the `keeps_ids` declaration is public only in Python. Both verified against the code before fixing |

## 3. G4 whole-branch review (head `d5eebcb`)

**Method.** The reviewer read the plan, the brief and the ledger, then every changed implementation file at head (`contexel/text.py`, `trace.py`, `validate.py`, `__init__.py`; `ts/src/text.ts`, `trace.ts`, `validate.ts`, `index.ts`; `csharp/Contexel/Text.cs`, `Strict.cs`, `Trace.cs`) and the full diffs of the case table, both runners, the doc-example tests, the READMEs, the site, the CHANGELOG and both ADRs; it sampled the per-language test files. It executed (read-only): 266 Python tests (text stages, doc examples, parity cases, golden fingerprints), ruff, mypy, a structural vector diff (79 to 128 cases, first 79 identical, other sections identical, ids unique), and Python and Node probes. It did not run npm or dotnet.

**Strengths.** The canon is small and right (shape checked before configuration through `checked(..., always=True)`, the `into` conflict before the empty-text exit, a linear `_ends`). The ports were re-derived rather than transliterated: the TypeScript `cut` and the C# `Ends` replace the regex with a one-pass unit scan that the reviewer hand-checked against `(?:\r?\n){2,}` leftmost-greedy semantics on `\n\r\r\n\n`, `x\r\r\n\ny` and `\n\r\n`. TypeScript own-property discipline is real (`defineField`, `Object.hasOwn`, spread via CreateDataProperty, so `__proto__` and `constructor` are ordinary keys). No existing behavior changed: every existing `checked`/`traced` call site passes no new argument, the defaults are `always=False` and `keeps_ids=False`, the golden fingerprint file is untouched and green, the vectors are byte-identical apart from `case_count`. The `keeps_ids` mechanism is one changed line per language and is pinned by a shared vector in all three ports. The runners reject typos in nested specs, and the C# runner routes `size` through `SplitCore(object?)` so `true` and `"3"` reach the library's own validation. The README examples are executed.

### Critical

None.

### Important

**I-1. The shared vectors never pinned code-point offsets in `lines` or `paragraphs` mode** (`parity/parity_cases.py`, the `split/lines_*` and `split/paragraph*` cases). No `split` vector in those modes contained a character above U+FFFF; the only astral case was `split/size_astral`. The plan's Review Focus 2 claims the `lines_*` cases pin this class, and the classic port bug is counting offsets in UTF-16 units. Failure scenario: a later refactor of the TypeScript `cut` or the C# `CodePoints` reporting `start` and `end` in UTF-16 units for lines or paragraphs would replay all 128 vectors green (only per-language tests would catch it). **Resolved** by two appended cases, `split/lines_offsets_count_code_points` and `split/paragraphs_offsets_count_code_points` (130 cases).

### Minor

- **M-1** The 1M-character tests assert wall-clock under 2 s in TypeScript and C# (about 5x headroom measured in TypeScript; C# allocates about 2M dictionaries for 1M `\n` chunks under parallel xunit): flake risk on a slow CI runner. **Resolved**: bound raised to 20 s, tests kept (a culture-sensitive `IndexOf` mutant in C# is killed only by them).
- **M-2** C# `AsRecords` treated generic-only dictionaries (`ExpandoObject`) as a list although the README says they throw `input.not_list`. **Resolved** (same finding as SEC-4).
- **M-3** TypeScript `split` and `join` accept a `Map`, `Set`, `Date` or class instance as a record item (the shared `isMapping` is any non-array object), against the documented plain-object "mapping"; Python raises `input.not_mapping`. **Resolved by documentation** (ruling below).
- **M-4** "Attributed exactly" over-promises: with duplicate input ids a vanished record is masked by a sibling's chunks, and when the trace `id_field` equals the split `field` the chunks rewrite the id so the parent is reported dropped. **Resolved** (wording).
- **M-5** ADR-008 called `traced` "public only in Python", but it is not in `contexel.__all__` nor documented. **Resolved** (wording).
- **M-6** The AC 15 budget test could not fail (it measured the joined text, 62 tokens, against a budget that limits records with metadata, 142 of 150) and its comment about dedupe was wrong. **Resolved**: the test now proves that the budget bites (8 records before, 4 after) and the comment is true.
- **M-7** Stale documentation: "all eight stages plus `merge`", parity bullets omitting the new stages, a site lead paragraph describing every stage as `(records, **params) -> records`, a site error-table row not saying that `split` and `join` raise `input.not_mapping` in every mode. **Resolved**.
- **M-8** Property-test weaknesses: the lines check accepts an unsplit last chunk; the paragraphs check never verifies maximal runs. The example tests and vectors catch both. **Deferred.**
- **M-9** Nits: an unused helper; no shared case for a record that lacks the field but has `into`; no TypeScript test for wide separators in paragraphs or size mode. **Deferred.**

### Triage of the deferred per-task minors

Recommended and done in the fix wave: the duplicate-id wording (T1), the wall-clock bounds (T2, T3), `ExpandoObject` (T3), the budget test (T4), the stale documentation lines (T5). Can wait (no effect on correctness or on a claim's truth): the remaining Minor findings and observations of the five tasks, listed in the SDD ledger.

### Judgment of the two plan deviations

1. **Five extra shared error cases (49 new, 128 in all, instead of 44 and 123).** Correct. They pin plan ruling S4-2 (shape before configuration) and AC 12's typed size errors, which only the vectors can hold across languages; they were appended after the 44 plan cases and the 79 originals and every other section are unchanged.
2. **Two documentation corrections against the plan's wording.** Correct and accurate against the code (a non-string field passes through `split` before the `into` conflict check; `traced` is not exported from the TypeScript index and the C# method is `internal`); AC 34 outranks the plan's wording.

### Declined to judge (set aside by the reviewer, none blocks)

TypeScript accepts `size: 2.0` where Python rejects it (one number type in JavaScript; documented); a lone surrogate counts as one code point (outside the parity envelope; documented); C# `AsRecords` accepts any lazy or infinite `IEnumerable` and treats `ArraySegment<byte>` and `List<byte>` as lists, not "bytes" (ruling S4-5 names only `byte[]`); `split` and `join` accept `field=""` and `into=""` while `as_records` rejects an empty field (same in all three ports; the spec is silent); a `null` options object in TypeScript gives a raw `TypeError` (the convention of every TypeScript stage); Python `join` renders a `bytes` value as `"b'abc'"` (existing `tokens.serialize`); the trace counts non-`dict` `Mapping` parents as id-less (Slice 3 behavior); tracing `split` on 1M characters counts tokens twice; C# `new Rec(r)` dropped a custom comparer (fixed by the security finding S4-SEC-5); a lenient pipeline with `join` as a stage returns a string (ruling S4-1: the ramps go outside `pipeline`, and strict mode catches it); error message texts differ between ports (codes are the contract); the author e-mail in git metadata is the owner's standing identity.

## 4. Rulings made during execution

1. **Task 4 (+5 cases).** Both Important findings accepted although they change the plan's case count: the brief and design do not name the error order as an acceptance criterion (it is plan ruling S4-2), and all three ports pin it in their unit tests, but the shared vectors are the only thing that holds the three ports to one error precedence, AC 12 requires typed errors for an invalid `size`, and the order had been named as a risk in the review brief. Cost: totals shift by +5 per language, plan prose with "44" and "123" goes stale, the replay tool had to exempt two files.
2. **Task 5 (two wording fixes against the plan's blocks).** AC 34 (documentation cannot drift from behavior) is the binding authority; verified against the code first.
3. **TypeScript record check (M-3): document only.** The shared `isMapping` is the rule of every legacy stage in strict mode and must not change in this slice (nothing that works today changes); tightening only the new stages to plain objects is a public-behavior decision (see "Open" below).
4. **Fix wave scope.** Done: I-1, XT24, M-1, M-2/SEC-4, M-4, M-5, M-6, M-7, SEC-1, SEC-2, SEC-3, SEC-5. Deferred: M-8, M-9, the per-task minors not listed above, SEC-6 (pre-existing, Slice 7), a `max_chunks` or inherited-field option (a future slice).
5. **Three Minor wording items of the re-review parked** (no second fix wave): see section 6.

## 5. The fix wave and its re-review (`d5eebcb..520ab28`)

Five commits: `619d94d` (two vector cases for astral offsets in lines and paragraphs, and the TypeScript lone-high-surrogate test), `567c9d5` (20 s bounds, the budget test that bites), `125f3a1` (C# `AsRecords` excludes generic dictionaries, chunks keep the key comparer), `97d5590` (the Python paragraph cut as a one-pass scanner, a seeded comparison test against a regex oracle and a memory assertion), `520ab28` (documentation of the resource behavior, the exactness limits, the ADR wording, stale lines).

The scoped re-review verdicted all 13 findings ADDRESSED, proved the Python scanner equivalent to `(?:\r?\n){2,}` (an exhaustive comparison over all 29,524 strings of length 0 to 9 over {a, newline, carriage return}, 200,000 random texts, and six scanner mutants all caught by the new test; the new memory test fails on the old regex at 556 MB and 285 MB against a 100 MB bound), and checked every reworded documentation claim against the code, including two places where the implementer's measurements contradicted the brief (an id field equal to `into` never reports the parent dropped, so only the `field` case is documented; a TypeScript class instance with its own `text` is split rather than passed through, so only `Map` and `Date` are named as passed through).

State at `520ab28`: Python 685 passed, TypeScript 536 pass, C# 475 passed with 0 warnings on a clean rebuild; 130 vector cases (first 128 equal `d5eebcb`'s; the 79 original cases and every other section equal main's; regeneration stable); ruff, mypy, site and version checks clean; differential check on three seeds with 0 mismatches.

## 6. Parked and open

**Parked Minor items of the re-review (wording only, no behavior):**

- `site/stages.html` lead lists `as_records` and `join` as the only exceptions to "Every record stage ... auto-traced" but omits `merge` (a pre-existing gap now made explicit; the page already says elsewhere that `merge` is the one stage that is not auto-traced).
- "`split` keeps every id" opens the paragraph in the README, the CHANGELOG and the site without a qualifier (the qualifier follows in the same paragraph; the phrase is false only when the trace `id_field` equals the split field).
- A comment in `tests/test_text_stages.py` says the text and chunk are about 8 MB; the text is 4 MB, built before `tracemalloc` starts (no effect on the test).

**Out of scope, pre-existing:** E501 on seven lines of `parity/parity_cases.py` and one of `tests/test_parity_cases.py` (CI lints `contexel/` only).

**Open for the human:** (1) whether TypeScript `split` and `join` should reject non-plain objects (`Map`, `Date`, class instances) as record items, as Python rejects non-mappings, instead of the documented known limitation; (2) the deferred items above and the C# serializer depth cap (Slice 7); (3) the first three-operating-system CI run of this branch, `pip-audit` on the dev extras and the merge.
