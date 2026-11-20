<!-- Filed copy of the Slice 1 workspace file `qa-report.md` (2026-11-20), sanitized for a public
repository: user and temp-directory path prefixes are replaced by `<scratch>`. Workspace
names used inside map to: `qa-report.md` -> `docs/qa/foundation-hardening-s1-qa-pass-1.md`; `qa-report-2.md` -> `docs/qa/foundation-hardening-s1-qa-pass-2.md`; `fix-wave-findings.md` -> `docs/reviews/foundation-hardening-s1-fix-wave-findings.md`; `fix-wave-report.md` -> `docs/reviews/foundation-hardening-s1-fix-wave-report.md`. -->

# QA Report - Slice 1 "safety net" @ 827750a2ff2c0bb4383370337917546b57cec1a6

**QA Engineer (fresh context, G5)** - 2026-11-19
**Build under test:** branch `feat/hardening-s1-safety-net`, HEAD `827750a` (12 commits over `main` @ fdaaaf1).
**Method:** every experiment ran in a scratch copy outside the repo
(`<scratch>\qa-s1-1720409\`, from `git archive HEAD`; `ts/node_modules`
copied, no network). `/d/contexel` was never modified (`git status --short` empty after the run;
`git diff main..HEAD --name-only | grep -c '^contexel/'` = 0, i.e. no library file changed by the slice).
Only this report was written inside the repo.

## 1. Summary verdict: PASS WITH FINDINGS

- All baseline suites are green, the vectors regenerate byte-identically, AC 19-22 and the fingerprint
  baseline are functionally met, and the slice changes no library file.
- The safety net catches most real regressions: 37 of 54 mutations were caught.
- But 17 mutations SURVIVED. Several survivors are cases/tests whose NAME promises coverage they do not deliver
  (a "stable" rank property that never checks tie order, a "counts code points not bytes" case that cannot tell
  bytes/UTF-16 from code points, a "first present wins" merge case in which no record has two candidates, a
  golden "nested_dict_and_none" that contains no dict). These are test-quality defects (Medium), not blockers
  for the slice's stated ACs, but should be strengthened before Slices 2+ lean on this net (ADR-008 will edit
  exactly the fingerprint code whose dict/opaque branches are unpinned).
- No Critical/High defect. 6 Medium, 3 Low, 2 Info findings (section 5).

## 2. Baseline (scratch copy, Windows 11, Python 3.12.7, Node, .NET 8)

NOTE: `git archive` honours this machine's `core.autocrlf=true`, so the scratch working tree is CRLF. Committed
blobs are LF/UTF-8 (section 4). All suites passed on the CRLF checkout too.

```
$ python -m pytest -q -p no:cacheprovider
159 passed in 2.59s
$ cd ts && npm test        (tail)
ℹ tests 64
ℹ suites 0
ℹ pass 64
ℹ fail 0
$ dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo -v q
Passed!  - Failed:     0, Passed:    62, Skipped:     0, Total:    62, Duration: 47 ms - Contexel.Tests.dll (net8.0)
```
(159 = 153 in `tests/` + 6 in `reference_agent/`; the slice's own Python tests: 35 properties + 3 determinism +
10 golden + 39 parity = 87.)

Vector regeneration:
```
$ PYTHONPATH=<scratch> python parity/generate_vectors.py
wrote ...\base\parity\vectors.json (18497 bytes)
$ git show HEAD:parity/vectors.json | cmp - parity/vectors.json && echo BYTE-IDENTICAL-TO-HEAD-WITH-SCRATCH-LIB
BYTE-IDENTICAL-TO-HEAD-WITH-SCRATCH-LIB
```
Same result under Python 3.9.13 (`BYTE-IDENTICAL-on-3.9`). Full pytest under Python 3.11.9: `159 passed in 2.15s`.

ENVIRONMENT TRAP (not a slice defect, F-11): a stale non-editable `contexel 0.1.17` is installed in
`<user-profile>\Python\Python312\site-packages`. `python parity/generate_vectors.py` puts `parity/` (not the cwd) first
on `sys.path`, so it silently imports the INSTALLED package, not the checkout. My first diff run therefore compared
against the wrong library (and showed a CRLF diff). With `PYTHONPATH=<checkout>` it is correct. CI uses
`pip install -e`, so CI is fine.

## 3. Mutation testing

Each mutation was applied to a fresh scratch copy, the relevant suites run, then reverted from a pristine archive.
"Py" = full pytest (159). TS/C# suites test the ports against the committed vectors, so a mutation to the PYTHON
library cannot fail them unless vectors are regenerated (row 12).

| # | File | Exact change | Caught by | Result |
|---|------|--------------|-----------|--------|
| 1 | contexel/stages.py `select` | `for r in records: r.pop("junk", None)` | nothing (generator never emits a `junk` key; no-op on generated data) | SURVIVED (vacuous) |
| 2 | stages.py `select` | `r.pop("source", None)` on input | properties purity[select]; 2 parity cases | caught |
| 3 | stages.py `select` | `r["tags"].append("x")` on input | properties purity[select]; hash-seed sweep | caught |
| 4 | stages.py `dedupe` | `return sorted(out, key=lambda r: hash(_fingerprint(r)))` | 12 tests: hash-seed sweep, properties subsequence[dedupe_key/whole], 3 parity cases, 5 pre-existing | caught |
| 5 | stages.py `rescore` | `terms = list(set(terms))` (hash order) | hash-seed sweep 3/3 runs; rest of suite only 5 of 6 runs (random in-process seed) | caught (sweep is the reliable catcher) |
| 6 | stages.py `rank` | ascending sort then `reverse()` if desc | properties idempotent[rank]; parity rank/missing_field_goes_last_desc | caught |
| 7 | stages.py `rank` | tie-break by `(r[by], str(r.get("path")))` (ties leave input order; still idempotent) | NOTHING (Py, TS, C#) | **SURVIVED** |
| 8 | stages.py `rank` | tie-break by `str(r.get("snippet", r.get("t")))` | only parity rank/missing_field_goes_last_desc (NOT the property named `..._and_stable`) | caught (parity only) |
| 9 | stages.py `trim_to_budget` | `+ 2` -> `+ 1` | only properties::test_trim_never_exceeds_budget_without_min_records; no golden/parity case sits on a budget boundary | caught (1 test) |
| 10 | stages.py `trim_to_budget` | `+ 2` -> `+ 3` | pre-existing test_contexel::test_trim_to_budget_keeps_prefix_within_budget only | caught (pre-existing) |
| 11 | stages.py `rescore` | `k1 = 1.5` -> `1.4` (Py suites, vectors unchanged) | parity trace_report/contract_on_fixture only | caught (1 test) |
| 12 | same k1 change, then generate_vectors.py regenerated, TS+C# run | (vectors regenerated from mutated canon) | TS: 7 failed (case trace_report/contract_on_fixture; rescore matches Python; composed contract matches Python golden vectors; audit record matches Python; edge non-string fields feed rescore; edge substring mode; edge bare string names one field). C#: `Failed: 7, Passed: 55`. 52 changed lines in vectors.json. Python replay on regenerated vectors stays 159 passed (self-consistent by design) | caught |
| 13 | pipeline.py | `hexdigest()[:16]` -> `[:15]` | 8 tests in test_fingerprint_golden.py | caught |
| 14 | pipeline.py `_stable_repr` | list/tuple brackets `[`,`]` -> `(`,`)` | golden [contract], [nested_dict_and_none], [primitives], [rescore_defaults] | caught |
| 15 | pipeline.py `_stable_repr` | dict sort key `(type name, repr)` -> `repr(kv[0])` | NOTHING (`159 passed`) | **SURVIVED** |
| 16 | pipeline.py `stage` | remove `sorted(...)` over kwargs | golden x3 + test_keyword_order_does_not_change_the_fingerprint | caught |
| 17 | pipeline.py `_stable_repr` | dict open brace -> `<` | NOTHING (`159 passed`) | **SURVIVED** |
| 18 | pipeline.py `_stable_repr` | dict item `k:v` -> `k=v` | NOTHING (`159 passed`) | **SURVIVED** |
| 19 | pipeline.py `_stable_repr` | opaque-object fallback `type(value).__name__` -> constant `obj` | NOTHING (`159 passed`) | **SURVIVED** |
| 20 | pipeline.py `_stable_repr` | callable name -> constant `fn` | golden [named_callable]; test_plane::test_fingerprint_distinguishes_named_key_functions | caught |
| 21 | pipeline.py `_stable_repr` | `(list, tuple)` -> `list` only | golden [contract], [nested_dict_and_none], [rescore_defaults] | caught |
| 22 | stages.py `quarantine` | `_field_list(fields)[:1]` (scan only the first field) | NOTHING | **SURVIVED** |
| 23 | stages.py `quarantine` | `text = ""` (control fully off) | 7 PRE-EXISTING tests; none of the new properties/parity cases | caught (pre-existing only) |
| 24 | tokens.py | `len(text)` -> `len(text.encode())` in heuristic count | properties idempotent[truncate]; parity trace_report/contract_on_fixture; NOT the named truncate case | caught |
| 25 | stages.py `_truncate_text` | slice by bytes: `text.encode()[:4*budget].decode(errors="ignore")` | parity truncate_field/counts_code_points_not_bytes | caught (named case) |
| 26 | stages.py `_truncate_text` | guard `... and len(text.encode()) <= 4*max_tokens` | only properties idempotent[truncate]; named case green | caught (property only) |
| 27 | ts/src/stages.ts `dedupe` | keep LAST duplicate (reverse iterate + unshift) | TS: case dedupe/nfc_and_nfd_stay_distinct, case merge/schema_first_present_wins_and_dedupes, edge "dedupe keeps {} and [] distinct" (3 fail / 61 pass) | caught |
| 28 | csharp/Contexel/Stages.cs `Dedupe` | keep LAST (Enumerable.Reverse + Insert(0)) | C# `Failed: 3, Passed: 59` | caught |
| 29 | ts stages.ts `trim_to_budget` | `+ 2` -> `+ 1` | NOTHING (`tests 64 / pass 64`) | **SURVIVED** |
| 30 | ts stages.ts `quarantine` | `fieldList(...).slice(0, 1)` | NOTHING (`pass 64`) | **SURVIVED** |
| 31 | ts stages.ts `rescore` | `k1 = 1.5` -> `1.4` (vs unchanged vectors) | TS: same 7 names as row 12 | caught |
| 32 | ts/src/tokens.ts `codePointLength` | `return text.length` (UTF-16 units) | NOTHING (`pass 64`), including the pre-existing test "token counts match Python (code points, not UTF-16 units)" and the new truncate case | **SURVIVED** |
| 33 | ts stages.ts `merge` | remove `break` (last matching candidate wins) | NOTHING (`pass 64`) | **SURVIVED** |
| 34 | ts/src/trace.ts `report` | `->` -> `=>` in entry line | TS: case trace_report/contract_on_fixture, case trace_report/empty_pipeline_input | caught |
| 35 | ts stages.ts `rank` | ascending sort + `.reverse()` for desc | TS: case rank/missing_field_goes_last_desc, edge "rank with callable key + desc keeps ties stable" | caught |
| 36 | csharp Stages.cs `TrimToBudget` | `Tokens.Count(...) + 2` -> `+ 1` | NOTHING (`Passed: 62`) | **SURVIVED** |
| 37 | csharp Stages.cs `Quarantine` | `FieldList(...).Take(1)` | NOTHING (`Passed: 62`) | **SURVIVED** |
| 38 | csharp Stages.cs `Rescore` | `k1 = 1.4` | C# `Failed: 7, Passed: 55` | caught |
| 39 | csharp Stages.cs `Merge` | remove `break` (last candidate wins) | NOTHING (`Passed: 62`) | **SURVIVED** |
| 40 | csharp Trace.cs `Report` | `->` -> `=>` | C# `Failed: 2, Passed: 60` | caught |
| 41 | csharp PyCompat.cs `CodePointLength` | `return text.Length` (UTF-16) | NOTHING (`Passed: 62`) | **SURVIVED** |
| 42 | stages.py `merge` | remove `break` (last candidate wins) | NOTHING (`159 passed`) | **SURVIVED** |
| 43 | stages.py `allowlist` | `except TypeError: ok = True` (fail open) | pre-existing test_allowlist_keeps_only_approved_sources only | caught (pre-existing) |
| 44 | stages.py `allowlist` | `in` -> `not in` | 4 tests incl. 2 new parity cases | caught |
| 45 | stages.py `select` | `r.get(k)` instead of skipping missing keys | parity select/missing_and_nested_fields + 1 pre-existing | caught |
| 46 | stages.py `_typed_tuple` | drop the type tag (1 == 1.0 == True) | pre-existing test_fast_paths::test_dedupe_mixed_types_stay_distinct only | caught (pre-existing) |
| 47 | stages.py `rescore` | proximity `window = 80` -> `79` | NOTHING (`159 passed`) | **SURVIVED** |
| 48 | stages.py `rank` | `present + missing` -> `missing + present` | 4 tests incl. both rank parity cases and properties::test_rank_is_a_permutation_and_stable | caught |
| 49 | stages.py `dedupe` | `if False: continue` (never dedupes) | 17 tests incl. 4 parity cases; NONE of the new properties (identity is a valid subsequence) | caught |
| 50 | stages.py `trim_to_budget` | `if False:` (never trims) | 8 tests incl. properties trim_never_exceeds_budget and parity pipeline/allowlist_then_trim_on_fixture | caught |
| 51 | stages.py `trim_to_budget` | ignore `min_records` | properties::test_trim_min_records_keeps_the_best_records + 1 pre-existing | caught |
| 52 | stages.py `merge` | `r["seen"] = True` on input records | parity merge/concat_without_schema + 2 pre-existing (no property covers merge) | caught |
| 53 | stages.py `rescore` | mutate input (`r[into] = ...`) | properties purity[rescore] + 1 pre-existing | caught |
| 54 | stages.py `truncate_field` | mutate input (`r[field] = ...`) | properties purity[truncate] + 1 pre-existing | caught |

TOTAL: 54 mutations. CAUGHT 37, SURVIVED 17 (rows 1, 7, 15, 17, 18, 19, 22, 29, 30, 32, 33, 36, 37, 39, 41, 42, 47).

Pasted evidence (real output):
```
# rows 17/19 (dict brace / opaque-object name changed in pipeline.py)
mutated contexel/pipeline.py
--- PY
159 passed in 2.44s

# row 29 (TS trim +1)
ℹ tests 64
ℹ pass 64
ℹ fail 0
# row 36 (C# trim +1)
Passed!  - Failed:     0, Passed:    62, Skipped:     0, Total:    62, Duration: 54 ms - Contexel.Tests.dll (net8.0)

# row 25 vs 26: the named case sees only byte-SLICING, not byte-COUNTING
FAILED tests/test_parity_cases.py::test_committed_case_matches_canon[truncate_field/counts_code_points_not_bytes]   (row 25)
FAILED tests/test_properties.py::test_stage_is_idempotent[truncate]                                                   (row 26)

# row 5 without the sweep (6 runs), then the sweep alone (3 runs)
156 passed, 3 deselected   (run 1; runs 2-6: 1 failed, 155 passed, 3 deselected)
1 failed, 2 passed in 1.18s / 1.20s / 1.22s
```

## 4. Adversarial checks of the harness

| Check | Result |
|-------|--------|
| Property seeds, 3 runs each: SEED=1 CASES=1000 / SEED=987654321 CASES=500 / default | `35 passed in 4.95s, 4.66s, 4.69s` / `35 passed in 1.42s, 1.42s, 1.44s` / `35 passed in 0.70s, 0.70s, 0.69s`. No flake. SEED=-5 CASES=50: 35 passed |
| CONTEXEL_PROP_CASES=0 | the 3 canary tests FAIL loudly (`3 failed, 32 passed`): not a silent vacuous pass |
| CONTEXEL_PROP_SEED=abc | `35 failed` (ValueError, loud) |
| Failure prints the seed and reproduces | with row-2 mutation: `E AssertionError: input mutated (seed=20261119)`; re-run with CONTEXEL_PROP_SEED=20261119 CONTEXEL_PROP_CASES=1 gives `1 failed, 34 passed` (reproduced) |
| tests/test_determinism_processes.py x3 | `3 passed in 1.14s`, `3 passed in 1.15s`, `3 passed in 1.17s`. No flake |
| Hash-seed sweep is not vacuous | row 5: sweep failed 3 of 3 runs; same-process suites caught it 5 of 6 runs. test_child_really_sees_the_requested_hash_seed and the set-order canary pass |
| No hypothesis, no dependency change | `git diff main..HEAD -- pyproject.toml` is empty; grep for hypothesis finds nothing in pyproject/tests |
| Tamper: change one expected value | Py FAILED `...[select/missing_and_nested_fields]`; TS `✖ case select/missing_and_nested_fields` (fail 1 / pass 63); C# `Failed: 1, Passed: 61`. All loud |
| Tamper: unknown key added to a case | Py FAILED that case; TS `has unsupported key bogus`; C# Failed 1. All loud |
| Tamper: `_meta.case_count` 22 -> 23 | Py test_case_count_matches_meta_and_ids_are_unique FAILED; TS `case_count disagrees with the cases array`; C# Failed 1. All loud |
| Tamper: delete a case, keep case_count | Py + TS + C# all fail on the count check (TS `tests 63 / fail 1`; C# `Total: 61, Failed: 1`) |
| Tamper: unknown stage kind | Py FAILED; TS `Error: unknown case kind frobnicate`; C# Failed 1 |
| Tamper: remove the `cases` key entirely (with or without case_count) | LOUD everywhere: Py `1 error during collection`; TS `TypeError: vectors.cases is not iterable` (`tests 42, fail 1`); C# `Failed: 2, Passed: 39, Total: 41`. No silent pass |
| Tamper: `cases: []` with case_count 0 | Py `1 failed, 16 passed, 1 skipped` (an empty parametrize set is skipped, but a sibling test fails); C# `Failed: 1`; TS `fail 0 / pass 42`, a SILENT PASS (F-9) |
| Tamper: delete a case AND decrement case_count consistently | all three PASS (TS 63/63, C# Passed 61, Py 38 passed). Only CI regenerate-and-diff guards this (by design) |
| AC 21 end to end: add a case editing ONLY parity/parity_cases.py, regenerate | case_count became 23; Py `40 passed`; TS `✔ case qa/rank_ties_stay_in_input_order`, `tests 65 / pass 65`; C# `Passed: 63`. No TS/C# edit needed. AC 21 demonstrated |
| Python 3.9 / 3.8 syntax | compile() of all 7 new/changed Python files under 3.9.13 and 3.8.10: ok. 3.9 has no pytest and there is no network, so I ran test_determinism_processes directly under 3.9.13 (3 tests OK) and the 35 property + 10 golden test functions through a 20-line pytest shim kept OUTSIDE the repo: `3.9 property+golden checks passed: 45`. Real pytest only on 3.12 and 3.11 |
| CR / encoding | committed blobs of all 11 new/changed files: 0 CR bytes (counted with tr -cd and wc -c), all decode as UTF-8; `git ls-files --eol` shows `i/lf`. The CRLF seen in the scratch tree is this machine autocrlf checkout. (An earlier grep-based count in my session printed line counts because of a shell quoting slip; the byte count is authoritative.) |
| Tracked / not ignored | `git ls-files --error-unmatch` on all new files: ALL-TRACKED; `git check-ignore -v` on the new paths exits 1 (none ignored) |

## 4b. Cross-language drift (test plan D)

The 22 vector case ids: select/empty_input, dedupe/empty_input, allowlist/empty_input, quarantine/empty_input,
rescore/empty_input, rank/empty_input, truncate_field/empty_input, trim_to_budget/empty_input,
merge/empty_sources, pipeline/empty_input, merge/concat_without_schema,
merge/schema_first_present_wins_and_dedupes, merge/schema_unmatched_record_becomes_empty,
rank/missing_field_goes_last_desc, rank/missing_field_goes_last_asc, dedupe/nfc_and_nfd_stay_distinct,
truncate_field/counts_code_points_not_bytes, select/missing_and_nested_fields,
shaped/select_then_dedupe_on_fixture, pipeline/allowlist_then_trim_on_fixture,
trace_report/contract_on_fixture, trace_report/empty_pipeline_input.

```
TS: npm test, "case <id>" pass lines, sorted -> 22 lines; diff vs vector ids: identical (TS executes exactly the 22 vector ids)
C#: dotnet test -v n, CaseMatchesPython(id: ...) pass lines -> 22 lines; diff vs vector ids: identical (C# executes exactly the 22 vector ids)
```
AC 22: merge (3 cases), shaped (1) and trace_report (2) are replayed in TS and C#. Met.

## 5. Defects / findings

Severity: Medium = the safety net has a hole in something it claims to cover; Low = weak but mitigated; Info = note.

**F-1 (Medium) merge/schema_first_present_wins_and_dedupes cannot detect "first present wins" (rows 33, 39, 42).**
Repro: scratch copy; in merge (Py stages.py, TS stages.ts, C# Stages.cs) remove the `break` after the first matching
candidate; run all three suites. Expected: the case fails. Actual: all green (`159 passed`, `pass 64`, `Passed: 62`).
Cause: in the case input every record carries exactly ONE candidate name, so first-wins and last-wins are
indistinguishable. Fix: add a record holding two candidates (for example title and name together).

**F-2 (Medium) truncate_field/counts_code_points_not_bytes does not discriminate counting by bytes or UTF-16 (rows 24, 26, 32, 41).**
Repro: TS codePointLength changed to `return text.length`, or C# CodePointLength changed to `return text.Length`; run TS/C#.
Expected: this case fails. Actual: TS `pass 64`, C# `Passed: 62`. The pre-existing TS test "token counts match Python
(code points, not UTF-16 units)" is also green because its strings are ASCII or BMP only. In Python, counting by bytes
(row 26) is caught only by the property idempotent[truncate], not by the case. Cause: both inputs (30 and 36 code
points, max_tokens=4) exceed the budget under every counting rule, and truncation then slices by 4*budget code
points regardless. Fix: add an input whose code-point count is within budget but whose byte or UTF-16 count is not
(for example 12 CJK characters at max_tokens=4, and an astral-emoji string sized to straddle the boundary).

**F-3 (Medium) the golden fingerprint baseline does not pin the dict and opaque-object branches of _stable_repr (rows 15, 17, 18, 19).**
Repro: in contexel/pipeline.py change the dict open brace to `<` (or `k:v` to `k=v`, or the dict sort key, or the final
`type(value).__name__`); run pytest. Expected: a golden test fails (the slice purpose is the EXACT current
fingerprint). Actual: `159 passed`. The shape named nested_dict_and_none contains no dict. This matters because
ADR-008 (next slice) rewrites this function; a dict regression there would be invisible. Fix: add shapes that bind
a dict-valued parameter (mixed-type keys and a nested dict) and an opaque object parameter, recording the current
fingerprints from this canon.

**F-4 (Medium) quarantine multi-field scanning is unprotected in all three languages (rows 22, 30, 37).**
Repro: scan only the first of several fields (Py `_field_list(fields)[:1]`, TS `.slice(0, 1)`, C# `.Take(1)`).
Expected: a case or property fails. Actual: all green. Also (row 23) disabling quarantine entirely is caught only by
PRE-EXISTING tests: no new property asserts that an injection record is dropped or flagged, and no new parity case
has a non-empty quarantine input (trace_report/contract_on_fixture allowlists the injected record away first).
Fix: a case with two fields where only the second carries the marker, plus a property or case asserting a seeded
"ignore all previous instructions" record is dropped or flagged.

**F-5 (Medium) no cross-language test pins the trim_to_budget per-item overhead (rows 29, 36; Python row 9).**
Repro: TS `+ 2` changed to `+ 1`, or C# `Tokens.Count(...) + 2` changed to `+ 1`. Expected: a case fails. Actual: green.
In Python only properties::test_trim_never_exceeds_budget_without_min_records catches it; the golden and parity
cases do not sit on a budget boundary. Fix: a trim_to_budget case whose budget equals the exact cumulative cost of
N records, so a change of one per item changes the kept count.

**F-6 (Medium) test_rank_is_a_permutation_and_stable does not test stability (row 7).**
Repro: change the rank tie-break to `(r[by], str(r.get("path")))`; run everything. Expected: the stability test fails.
Actual: all green in Py/TS/C#. The test checks permutation, descending scores and missing-last only; equal-score
ties are never compared with input order. (A tie-reversing mutation, row 6, IS caught, but through idempotence and a
parity case.) Fix: assert that for equal scores the output order equals the input order.

**F-7 (Low) the new filter-stage properties are satisfied by a no-op (row 49).** Subsequence and idempotence hold for
the identity function, so a dedupe that never dedupes passes ALL new properties (it is caught by new parity cases
and pre-existing tests). Suggest: no duplicates remain for dedupe, no disallowed source remains for allowlist,
no marker remains for quarantine_drop.

**F-8 (Low) proximity window boundary untested (row 47).** `window = 80` changed to `79` survives everywhere in Python
(TS/C# analogues not run). Add a rescore case with terms exactly 79, 80 and 81 characters apart.

**F-9 (Low) the TS runner silently passes with an empty cases array and case_count 0** (Python skips one test and a
sibling fails; C# fails). Add a non-empty or minimum-count assertion to ts/test/cases.test.ts. Consistent deletion
of a case is caught only by CI regenerate-and-diff (by design).

**F-10 (Info) generator realism.** Records have a fixed key set (path, line, snippet, score, source, tags, meta), so a
stage that mutates only an unexpected key (row 1) cannot be caught. merge has no property test (it is a combiner,
outside "every stage" in AC 20 as read). The hash-seed sweep uses 4 seeds (0, 1, 2, 4242); a hash-order bug with a
low trigger probability could slip past it.

**F-11 (Info) environment trap:** a stale installed contexel 0.1.17 shadows the checkout for
`python parity/generate_vectors.py` when run without PYTHONPATH or an editable install (section 2).

No defect found in what the slice claims for AC 19, 20 (no hypothesis, seeds printed and reproducible, canaries
present), 21, 22, or the fingerprint goldens for the pinned shapes: every mutation of a pinned shape (rows 13, 14,
16, 20, 21) was caught.

## 6. Acceptance criteria

| AC | Evidence | Met |
|----|----------|-----|
| 19 subprocess hash-seed sweep, identical hashes, in CI matrix | test_same_output_across_hash_seeds over seeds 0, 1, 2, 4242; 3x green; catches rows 4 and 5; ci.yml runs `python -m pytest -q` in every matrix cell (read from the file, NOT executed by me) | Yes (CI cells not executed) |
| 20 seeded stdlib generative tests, failures print seed | 35 tests; seed printed (`input mutated (seed=20261119)`) and reproduced; no hypothesis | Yes, with F-6 and F-7 strength caveats |
| 21 vector file carries stage/args/input/expect; TS and C# replay generically; adding a case edits only the generator | demonstrated end to end (section 4) | Yes |
| 22 merge, shaped, trace.report covered in TS and C# | 3 + 1 + 2 cases executed in both; both catch report-format mutations (rows 34, 40) | Yes, with F-1 caveat |
| Baseline: unchanged fingerprints for pipelines without sets, nested pipelines, tiktoken | 10 golden tests green on 3.12 and 3.9; mutations of pinned shapes caught | Yes for pinned shapes; F-3 for dict and opaque parameters |

## 7. What I could not verify

- CI itself (GitHub Actions matrix; macOS, Linux; Python 3.10 and 3.13). Only Windows 11 was used: Python 3.12 (full), 3.11 (full pytest), 3.9 (compile, determinism tests, property and golden via a shim; no real pytest) and 3.8 (compile only).
- TS/C# analogues of row 47 (window) and of rows beyond those listed; only the 54 mutations above were run.
- C# failing test NAMES for rows 12 and 38 (quiet verbosity prints only the count `Failed: 7`); the TS names are listed in row 12.
- Security sweep: out of scope for this task (test and vector infrastructure only; no new dependencies, no secrets added; pyproject.toml untouched).

## 8. QA verdict

PASS WITH FINDINGS. Slice 1 meets its stated acceptance criteria and changes no library behavior (verified). F-1 to
F-6 (Medium) are recommended to be fixed on this branch, or at the latest before Slice 2 relies on these cases,
because each is a case or property whose name overstates what it detects. No Critical or High defect.
