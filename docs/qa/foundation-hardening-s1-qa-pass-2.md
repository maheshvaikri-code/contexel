<!-- Filed copy of the Slice 1 workspace file `qa-report-2.md` (2026-11-20), sanitized for a public
repository: user and temp-directory path prefixes are replaced by `<scratch>`. Workspace
names used inside map to: `qa-report.md` -> `docs/qa/foundation-hardening-s1-qa-pass-1.md`; `qa-report-2.md` -> `docs/qa/foundation-hardening-s1-qa-pass-2.md`; `fix-wave-findings.md` -> `docs/reviews/foundation-hardening-s1-fix-wave-findings.md`; `fix-wave-report.md` -> `docs/reviews/foundation-hardening-s1-fix-wave-report.md`. -->

# QA Report 2 (second G5 pass) - Slice 1 "safety net" @ f44d006

**QA Engineer (fresh context, G5)** - 2026-11-20
**Build under test:** branch `feat/hardening-s1-safety-net`, HEAD `f44d006487870c87e847ca985d42e5e30e7e7450` (fix wave over 827750a).
**Method:** every experiment ran in a scratch copy OUTSIDE the repo under
`<scratch>\qa-s1-2\<name>` (fresh `git archive HEAD | tar -x` for EACH mutation; `ts/node_modules`
copied, no network; C# restored offline). Python ran as `python -B` with `PYTHONDONTWRITEBYTECODE=1`, every `__pycache__` purged before
each run, `PYTHONPATH=<scratch>`. Proof the scratch library is the one under test:
`<scratch>\qa-s1-2\base\contexel\__init__.py`. Tools (my scripts, outside the repo):
`...\Temp\qa-s1-2-tools\*.sh`. Each mutation script asserts its anchor text occurs exactly once (`MUTATION NOT APPLIED` otherwise; one
early TS batch hit that and was discarded and re-run). Doctrine tests (`tests/test_doctrine_*`) excluded. `/d/contexel` was never modified
(`git status --short | wc -l` = 0 at the end). Only this file was written inside the repo.

## 1. Summary verdict: PASS

- All 17 first-pass survivors are now CAUGHT (0 survivors), in every language where the mutation exists. Rows 6, 14, 27 (and C# 28) did not regress.
- The extra boundary mutants (window 79 and 81 in Python, TypeScript and C#) are caught.
- About 29 new adversarial mutants (plus 4 extra `_stable_repr` variants): all caught by the suites except 2 Python-only gaps
  (P5: no `rstrip()` on the heuristic truncation path; P7: allowlist treats a missing field as not-None). Both are PRE-EXISTING behavior
  that the Slice 1 cases do not pin; TS and C# do pin them (edge tests), and the CI regenerate-and-diff of `vectors.json` pins them for
  Python (verified: both change the regenerated vectors). Low severity, not a Slice 1 regression.
- Property harness: no flake; canaries are not vacuous at CASES=1; CASES=0 (and -1) fails loudly.
- Tamper tests: all loud in all three runners, including the previously silent TS empty-`cases` case (fixed in BOTH TS and C#).
- Adding a case by editing only `parity/parity_cases.py` runs in all three languages with no runner edit.
- Golden fingerprints: the two new hex values equal what `main`'s library computes under PYTHONHASHSEED 0, 1, 2; all `_stable_repr`
  dict/opaque mutations fail the golden test.
- No Critical/High/Medium defect. 1 Low finding, 3 Info notes (section 7).

## 2. A. Baseline (unmutated scratch copy of HEAD, Windows 11, Python 3.12.7, Node v24.18.0, .NET 8.0.403)

```
python -B -c "import contexel;print(contexel.__file__)"
<scratch>\qa-s1-2\base\contexel\__init__.py
python -B -m pytest -q -p no:cacheprovider --ignore-glob="tests/test_doctrine_*"
197 passed in 3.66s
cd ts && npm test        (tail)
ℹ tests 70
ℹ pass 70
ℹ fail 0
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo -v q   (tail)
Passed!  - Failed:     0, Passed:    68, Skipped:     0, Total:    68, Duration: 43 ms - Contexel.Tests.dll (net8.0)
PYTHONPATH=<scratch> python -B parity/generate_vectors.py
wrote <scratch>\qa-s1-2\base\parity\vectors.json (21652 bytes)
git -C /d/contexel show HEAD:parity/vectors.json | cmp - parity/vectors.json && echo BYTE-IDENTICAL-TO-HEAD
BYTE-IDENTICAL-TO-HEAD
cases: 28   _meta.case_count: 28
```
Also: `git diff --stat main HEAD -- contexel ts/src csharp/Contexel` is empty (no library file changed); no `Co-Authored-By` in
`git log main..HEAD`; 0 CR bytes in every file changed since 827750a (committed blobs are LF). The scratch tree from `git archive` is CRLF on
this machine because of `core.autocrlf=true`; all suites pass on it, and the regenerated vectors are LF.

## 3. B. First-pass survivors re-run (each in a fresh scratch copy)

"n/a" = the mutation exists only in the other language's library. Python mutants can only be caught by the Python suite (TS/C# test their own
ports against the committed vectors). Counts are the final lines of the runs.

| Row | Mutation (exact) | Suite | Failing test names | Result |
|---|---|---|---|---|
| 1 | Py `select`: `for r in records: r.pop("junk", None)` | Py | `test_properties.py::test_stage_is_pure_and_deterministic[select]` (1 failed, 196 passed) | CAUGHT |
| 7 | Py `rank`: key `(r[by], str(r.get("path")))` | Py | `test_properties.py::test_rank_is_a_permutation_and_stable` (1 failed, 196 passed) | CAUGHT |
| 15 | `_stable_repr` dict sort key `repr(kv[0])` | Py | `test_fingerprint_golden.py::test_fingerprint_matches_the_recorded_baseline[dict_with_mixed_keys_and_nesting]` | CAUGHT |
| 17 | dict open brace `{` to `<` | Py | `...[dict_with_mixed_keys_and_nesting]` | CAUGHT |
| 18 | dict item `k:v` to `k=v` | Py | `...[dict_with_mixed_keys_and_nesting]` | CAUGHT |
| 19 | opaque fallback `type(value).__name__` to `"obj"` | Py | `...[opaque_object]` | CAUGHT |
| 22 | Py `quarantine`: `_field_list(fields)[:1]` | Py | `test_parity_cases.py::test_committed_case_matches_canon[quarantine/marker_in_second_field_is_dropped]`, `[quarantine/marker_in_second_field_is_flagged]`, `test_committed_cases_equal_what_the_case_table_builds_today` (3 failed) | CAUGHT |
| 29 | TS trim `+ 2` to `+ 1` | TS | `case trim_to_budget/budget_is_the_exact_cost_of_three` (fail 1 / pass 69) | CAUGHT |
| 30 | TS `quarantine` `fieldList(...).slice(0, 1)` | TS | `case quarantine/marker_in_second_field_is_dropped`, `case quarantine/marker_in_second_field_is_flagged` (fail 2) | CAUGHT |
| 32 | TS `codePointLength`: `n = text.length` (UTF-16) | TS | `case truncate_field/fits_by_code_points_not_bytes_or_utf16` (fail 1) | CAUGHT |
| 33 | TS `merge`: remove `break` | TS | `case merge/two_candidates_first_in_schema_order_wins` (fail 1) | CAUGHT |
| 36 | C# `TrimToBudget` `+ 2` to `+ 1` | C# | `CaseTests.CaseMatchesPython(id: "trim_to_budget/budget_is_the_exact_cost_of_three")` (Failed 1, Passed 67) | CAUGHT |
| 37 | C# `Quarantine`: `fieldNames.Take(1)` on the scanned list | C# | `CaseMatchesPython("quarantine/marker_in_second_field_is_dropped")`, `("quarantine/marker_in_second_field_is_flagged")` (Failed 2) | CAUGHT |
| 39 | C# `Merge`: remove `break` | C# | `CaseMatchesPython("merge/two_candidates_first_in_schema_order_wins")` (Failed 1) | CAUGHT |
| 41 | C# `PyCompat.CodePointLength`: `n = text.Length` | C# | `CaseMatchesPython("truncate_field/fits_by_code_points_not_bytes_or_ut"...)` (name truncated by the logger; Failed 1) | CAUGHT |
| 42 | Py `merge`: remove `break` | Py | `...[merge/two_candidates_first_in_schema_order_wins]`, `test_committed_cases_equal_...` (2 failed) | CAUGHT |
| 47 | Py `rescore` `window = 80` to `79` | Py | `...[rescore/proximity_window_is_80_characters]`, `test_committed_cases_equal_...` (2 failed) | CAUGHT |
| 47b | Py `window = 81` | Py | `...[rescore/proximity_window_is_80_characters]`, `test_committed_cases_equal_...` (2 failed) | CAUGHT |
| 47c | TS `window = 79` | TS | `case rescore/proximity_window_is_80_characters` (fail 1) | CAUGHT |
| 47d | TS `window = 81` | TS | `case rescore/proximity_window_is_80_characters` (fail 1) | CAUGHT |
| 47e | C# `window = 79` | C# | `CaseMatchesPython("rescore/proximity_window_is_80_characters")` (Failed 1) | CAUGHT |
| 47f | C# `window = 81` | C# | `CaseMatchesPython("rescore/proximity_window_is_80_characters")` (Failed 1) | CAUGHT |
| **Regression checks (were caught before)** | | | | |
| 6 | Py `rank`: ascending sort, `reverse()` if desc | Py | `[rank/missing_field_goes_last_desc]`, `test_committed_cases_equal_...`, `test_stage_is_idempotent[rank]`, `test_rank_is_a_permutation_and_stable` (4 failed) | CAUGHT |
| 14 | `_stable_repr` list brackets to parentheses | Py | golden `[contract]`, `[dict_with_mixed_keys_and_nesting]`, `[list_of_mixed_scalars_and_none]`, `[primitives]`, `[rescore_defaults]` (5 failed) | CAUGHT |
| 27 | TS `dedupe` keeps LAST duplicate | TS | `case merge/schema_first_present_wins_and_dedupes`, `case dedupe/nfc_and_nfd_stay_distinct`, `edge: dedupe keeps {} and [] distinct` (fail 3 / pass 67) | CAUGHT |
| 28 | C# `Dedupe` keeps LAST (analogue of 27) | C# | `CaseMatchesPython("dedupe/nfc_and_nfd_stay_distinct")`, `ParityTests.EdgeDedupeEmptyContainersDistinct`, `CaseMatchesPython("merge/schema_first_present_wins_and_dedupes")` (Failed 3) | CAUGHT |

**Result: 17 of 17 former survivors caught; 0 survive. Rows 6, 14, 27, 28 still caught.**

Representative pasted output (real):
```
=== ROW 7: rank tie-break by path
FAILED tests/test_properties.py::test_rank_is_a_permutation_and_stable
1 failed, 196 passed in 3.57s
=== ROW 29: TS trim +1
✖ case trim_to_budget/budget_is_the_exact_cost_of_three (1.1592ms)
ℹ tests 70 / ℹ pass 69 / ℹ fail 1
=== ROW 41: C# CodePointLength utf16
Failed Contexel.Tests.CaseTests.CaseMatchesPython(id: "truncate_field/fits_by_code_points_not_bytes_or_ut"···)
Passed: 67 / Failed: 1
=== ROW 47 (window 79) and ROW 4781 (window 81), Python
FAILED tests/test_parity_cases.py::test_committed_case_matches_canon[rescore/proximity_window_is_80_characters]
2 failed, 195 passed in 3.72s  /  2 failed, 195 passed in 3.78s
```

## 4. C. New adversarial mutants (fresh scratch copy each)

| # | Mutation | Py | TS | C# |
|---|---|---|---|---|
| C1 | `trim_to_budget` per-item overhead `+2` to `+3` | `test_contexel::test_trim_to_budget_keeps_prefix_within_budget`, `case[trim_to_budget/budget_is_the_exact_cost_of_three]`, `test_committed_cases_equal_...` | `case trim_to_budget/budget_is_the_exact_cost_of_three` | `CaseMatchesPython("trim_to_budget/budget_is_the_exact_cost_of_three")` |
| C2 | `trim_to_budget` `>` to `>=` | same 3 as C1 | `case trim_to_budget/budget_is_the_exact_cost_of_three` | `CaseMatchesPython("trim_to_budget/budget_is_the_exact_cost_of_three")` |
| C3 | token count by UTF-8 bytes (Py `len(text.encode())`, TS `TextEncoder`, C# `Encoding.UTF8.GetByteCount`) | `case[trace_report/contract_on_fixture]`, `case[truncate_field/fits_by_code_points_not_bytes_or_utf16]`, `test_committed_cases_equal_...`, `test_stage_is_idempotent[truncate]` | `case trace_report/contract_on_fixture`, `case truncate_field/fits_by_code_points_not_bytes_or_utf16`, `audit record matches Python`, `token counts match Python (code points, not UTF-16 units)` | `CaseMatchesPython("truncate_field/fits_by_code_points_not_bytes_or_ut"...)`, `TokenCountsMatchPython`, `CaseMatchesPython("trace_report/contract_on_fixture")`, `AuditRecordMatchesPython` |
| C4 | token count by UTF-16 units (Py `len(text.encode("utf-16-le"))/2`) | `case[truncate_field/fits_by_code_points_not_bytes_or_utf16]`, `test_committed_cases_equal_...` | (row 32 above) | (row 41 above) |
| C5 | `truncate_field` slices by bytes (Py) / UTF-16 units (TS `text.slice`, C# `Substring`) | `case[truncate_field/counts_code_points_not_bytes]`, `test_committed_cases_equal_...` | `case truncate_field/counts_code_points_not_bytes` | `CaseMatchesPython("truncate_field/counts_code_points_not_bytes")` |
| C6 | `merge` picks the LAST candidate (iterate reversed names) | `case[merge/two_candidates_first_in_schema_order_wins]`, `test_committed_cases_equal_...` | `case merge/two_candidates_first_in_schema_order_wins` | `CaseMatchesPython("merge/two_candidates_first_in_schema_order_wins")` |
| C7 | `quarantine` scans only the LAST field | `case[quarantine/marker_in_second_field_is_dropped]`, `[..._is_flagged]`, `test_committed_cases_equal_...` | `case quarantine/marker_in_second_field_is_dropped`, `..._is_flagged` | `CaseMatchesPython("quarantine/marker_in_second_field_is_dropped")`, `("..._is_flagged")` |
| C8 | `rank` ties broken in REVERSE input order | `case[rank/missing_field_goes_last_desc]`, `[..._asc]`, `test_committed_cases_equal_...`, `test_stage_is_idempotent[rank]`, `test_rank_is_a_permutation_and_stable` (5 failed) | `case rank/missing_field_goes_last_desc`, `..._asc`, `edge: rank with callable key + desc keeps ties stable` | `CaseMatchesPython("rank/missing_field_goes_last_asc")`, `("..._desc")`, `ParityTests.EdgeRankCallableDescStableTies` |
| C9 | `dedupe` never dedupes | 20 failed, 177 passed (first listed: `test_run_code_returns_result_using_stages`, `test_dedupe_by_key_preserves_order`, `test_dedupe_full_record`, `test_dedupe_multi_key`, `test_pipeline_composes_stages`, ...) | 9 failed (e.g. `case dedupe/nfc_and_nfd_stay_distinct`, `case shaped/select_then_dedupe_on_fixture`, `case merge/schema_first_present_wins_and_dedupes`) | 10 failed (e.g. `CaseMatchesPython("dedupe/nfc_and_nfd_stay_distinct")`, `("shaped/select_then_dedupe_on_fixture")`) |
| C10 | `allowlist` fails OPEN on unhashable | `test_injection_controls::test_allowlist_keeps_only_approved_sources` (1 test) | `edge: allowlist, missing field reads as null; unhashable fails closed` | `ParityTests.EdgeAllowlistNullAndUnhashable` |
| C11 | `select` pops an unexpected key (`extra_0`) from its input | `test_properties::test_stage_is_pure_and_deterministic[select]` | n/a | n/a |
| C12 | hash-order dependence: `rescore` terms from `set()` | `test_determinism_processes::test_same_output_across_hash_seeds`, `case[trace_report/contract_on_fixture]`, `test_committed_cases_equal_...` | n/a | n/a |
| C12b | hash-order dependence: `dedupe` returns `sorted(out, key=hash(...))` | 11 failed incl. `test_same_output_across_hash_seeds`, `test_filter_stage_returns_a_subsequence[dedupe_key]`, `[dedupe_whole]` | n/a | n/a |
| C13 | `truncate_field` does not reserve room for the suffix | 5 failed incl. `case[truncate_field/counts_code_points_not_bytes]`, `case[truncate_field/fits_by_code_points_not_bytes_or_utf16]` | 7 failed incl. `case truncate_field/counts_code_points_not_bytes` | 7 failed incl. `CaseMatchesPython("truncate_field/counts_code_points_not_bytes")` |
| C14 | `trim_to_budget` ignores `min_records` | `test_trim_min_records_never_returns_empty`, `test_trim_min_records_keeps_a_prefix_of_at_least_min_records` | `edge: minRecords keeps the best record at a too-small budget` | `ParityTests.EdgeTrimMinRecords` |
| C15 | `quarantine` flag always False | `test_quarantine_flag_mode_marks_instead_of_dropping`, `case[quarantine/marker_in_second_field_is_flagged]`, `test_filter_stage_has_its_effect[quarantine_flag]` | `case quarantine/marker_in_second_field_is_flagged`, `quarantine drop + flag match Python` | `CaseMatchesPython("quarantine/marker_in_second_field_is_flagged")`, `QuarantineDropAndFlagMatchPython` |
| C16 | `rescore` rounds to 5 places | `case[trace_report/contract_on_fixture]`, `case[rescore/proximity_window_is_80_characters]` | not run | not run |
| P1 | `merge` ignores `dedupe_key` | `test_merge_dedupe_key`, `case[merge/schema_first_present_wins_and_dedupes]` | not run | not run |
| P2 | `dedupe` multi-key uses first key only | `test_dedupe_multi_key` (only 1) | not run | not run |
| P3 | `rescore` proximity bonus `/4` to `/3` | `case[rescore/proximity_window_is_80_characters]`, `test_committed_cases_equal_...` | not run | not run |
| P4 | `quarantine` drops `re.IGNORECASE` | 7 failed incl. `case[quarantine/marker_in_second_field_is_dropped]` | not run | not run |
| P6 | `rank` default `desc` flipped | `case[rank/missing_field_goes_last_desc]`, `test_rank_is_a_permutation_and_stable` | not run | not run |
| P8 | `trim_to_budget` drops the best record before stopping | 7 failed incl. `case[pipeline/allowlist_then_trim_on_fixture]`, `case[trim_to_budget/budget_is_the_exact_cost_of_three]` | not run | not run |
| **P5** | **heuristic truncation without `rstrip()`** | **SURVIVED (197 passed)** | the TS edge test on the Python whitespace set (`edge: truncate strips ... whitespace set, keeps U+FEFF`) | `ParityTests.EdgeTruncateWeirdWhitespace` |
| **P7** | **allowlist: missing field dropped even when None is allowed** (`ok = field in r and ...`) | **SURVIVED (197 passed)** | `edge: allowlist, missing field reads as null; unhashable fails closed` | `ParityTests.EdgeAllowlistNullAndUnhashable` |
| E5-E8 | `_stable_repr` dict values via `repr`; unsorted dict; key via `str`; dict close brace | each: `test_fingerprint_matches_the_recorded_baseline[dict_with_mixed_keys_and_nesting]` (1 failed, 196 passed) | n/a | n/a |

Every row is caught except the two Python-only rows P5 and P7 (Finding F-1). For P5 and P7 I regenerated the vectors from the mutated Python library:
```
P5-VECTORS-CHANGED  (cmp: parity/vectors.json differ: char 15745, line 627)
P7-VECTORS-CHANGED  (cmp: parity/vectors.json differ: char 15158, line 583)
```
so the CI regenerate-and-diff (`git diff --exit-code parity/vectors.json`) would catch both; only the in-process Python pytest run does not. I did not execute CI.

(Test names above containing a dash or an apostrophe are abbreviated: the TS edge tests are `edge: allowlist <em dash> missing field reads as null; unhashable fails closed` and the one on the Python whitespace set.)

## 5. D. Harness adversarial checks

**Property tests** (`tests/test_properties.py`, 61 tests in the file at HEAD), three runs each:
```
SEED=1 CASES=1000:          61 passed in 8.00s / 8.26s / 8.11s
SEED=987654321 CASES=500:   61 passed in 2.77s / 2.69s / 2.78s
default:                    61 passed in 0.96s / 0.97s / 0.97s
full suite with SEED=1 CASES=1000: 197 passed in 11.32s
tests/test_determinism_processes.py x3: 3 passed in 1.16s / 1.07s / 1.06s
```
No flake.

**Run size edge cases**:
```
CONTEXEL_PROP_CASES=1:           61 passed in 0.25s   (all canaries, including the table canaries, still pass: not vacuous)
CONTEXEL_PROP_CASES=2 SEED=7:    61 passed in 0.22s
CONTEXEL_PROP_CASES=0:           FAILED test_canary_purity_check_detects_mutation
                                 FAILED test_canary_determinism_check_detects_nondeterminism
                                 FAILED test_canary_idempotence_check_detects_non_idempotence
                                 3 failed, 58 passed
CONTEXEL_PROP_CASES=-1:          the same 3 canaries fail: 3 failed, 58 passed
```
With CASES=0 the 58 other property tests run zero iterations and pass, but the three seed-loop canaries fail, so the run as a whole fails loudly. Not silent.

**Vector tamper** (each in a fresh scratch copy; Python = `tests/test_parity_cases.py`):

| Tamper | Python | TypeScript | C# |
|---|---|---|---|
| reverse one `expect` (rank/missing_field_goes_last_desc) | `[rank/missing_field_goes_last_desc]`, `test_committed_cases_equal_...` (2 failed) | `case rank/missing_field_goes_last_desc` (fail 1) | `CaseMatchesPython("rank/missing_field_goes_last_desc")` (Failed 1) |
| unknown key `bogus` on a case | `[quarantine/empty_input]`, `test_committed_cases_equal_...` (2 failed) | `case quarantine/empty_input` (fail 1) | `CaseMatchesPython("quarantine/empty_input")` (Failed 1) |
| `case_count` 28 to 29 | `test_case_count_matches_meta_and_ids_are_unique` | `the cases section is present and complete` | `CasesSectionIsPresentAndComplete` |
| delete a case, keep `case_count` 28 | `test_case_count_matches_meta_and_ids_are_unique`, `test_committed_cases_equal_...` | `the cases section is present and complete` (tests 69 / fail 1) | `CasesSectionIsPresentAndComplete` |
| `cases: []`, `case_count: 0` | `test_unicode_normalization_case_has_two_distinct_keys`, `test_committed_cases_equal_...` (2 failed, 19 passed, 1 skipped) | `the cases section is present and complete` (tests 42 / pass 41 / fail 1) | `CasesSectionIsPresentAndComplete`, `CaseMatchesPython` (Failed 2) |
| `cases` key removed | `1 error during collection` | `dist-test\test\cases.test.js` (fail 1) | `CasesSectionIsPresentAndComplete`, `CaseMatchesPython` (Failed 2) |
| delete a case AND decrement `case_count` (consistent) | `test_committed_cases_equal_what_the_case_table_builds_today` FAILS | PASS (69/69) | PASS (Passed: 67) |

The empty-cases silent pass is FIXED in TS (`the cases section is present and complete` now fails; case_count and cases agree at 0, so it is the new
non-empty floor that fires) and in C# (`CasesSectionIsPresentAndComplete` fails). The consistent-deletion tamper passes silently in TS/C# (a
by-design limit: only a regeneration comparison sees it) but is caught in Python by `test_committed_cases_equal_what_the_case_table_builds_today`.

**AC 21 end to end:** in a scratch copy I edited ONLY `parity/parity_cases.py` (added a `qa2/rank_ties_stay_in_input_order` case) and ran
`python parity/generate_vectors.py`; cases 29, case_count 29; `ts/test/cases.test.ts`, `csharp/Contexel.Tests/CaseTests.cs` and
`tests/test_parity_cases.py` compared identical to HEAD (CR-insensitive `cmp`).
```
Python: 198 passed in 2.86s
TS:     ✔ case qa2/rank_ties_stay_in_input_order (0.0591ms)   tests 71 / pass 71 / fail 0
C#:     Passed Contexel.Tests.CaseTests.CaseMatchesPython(id: "qa2/rank_ties_stay_in_input_order")   Passed: 69
```

## 6. E. Golden fingerprints

Second scratch copy from `git archive main` (library identical to HEAD: `git diff main HEAD --stat -- contexel` is empty). The HEAD
`tests/test_fingerprint_golden.py` was run against the library of `main`:
```
PYTHONHASHSEED=0: 12 passed in 0.17s   PYTHONHASHSEED=1: 12 passed in 0.17s   PYTHONHASHSEED=2: 12 passed in 0.17s
```
Independent computation of the two new shapes (my own script, not the test expectations), from the library of `main` AND of HEAD:
```
lib=mainlib HASHSEED=0/1/2: dict 5d865072cb72afe5  opaque 79dab73b8b021852   (identical in all three)
lib=base    HASHSEED=0/1/2: dict 5d865072cb72afe5  opaque 79dab73b8b021852   (identical in all three)
```
These are exactly the two new hex values in the test file. The 8 pre-existing hex values are unchanged from the commit that introduced the file
(4adc2bf), through 827750a, to HEAD (the sorted set of 16-hex literals is the same plus exactly the two new ones).

`_stable_repr` mutations (each: `1 failed, 196 passed`, the only failure being the new golden):
```
dict sort key repr only (row 15), dict brace "<" (17), dict "k=v" (18)       -> [dict_with_mixed_keys_and_nesting]
opaque name -> "obj" (19)                                                      -> [opaque_object]
dict values via repr / dict items unsorted / key via str / dict close ")"      -> [dict_with_mixed_keys_and_nesting]
```

## 7. Defects / findings

No defect against the Slice 1 acceptance criteria.

**F-1 (Low) Python in-process tests do not pin two documented behaviors (mutants P5, P7).** Pre-existing behavior, not a regression.
Repro P5: in a scratch copy of HEAD change `contexel/stages.py` `_truncate_text`: `return text[: 4 * budget].rstrip() + suffix` to
`return text[: 4 * budget] + suffix`; `python -B -m pytest -q` prints `197 passed`. Repro P7: change `ok = r.get(field) in allowed_set` to
`ok = field in r and r.get(field) in allowed_set`; `197 passed`. Expected: a Python test fails. Actual: green. Mitigation: TS and C# pin both
(TS edge tests, `EdgeTruncateWeirdWhitespace`, `EdgeAllowlistNullAndUnhashable`) and the regenerated vectors differ (so the CI diff catches both).
Optional follow-up for Slice 2: a parity case whose 4*budget cut ends on whitespace, and an allowlist case with a record missing the field while
`None` is allowed.

**I-1 (Info)** `CONTEXEL_PROP_CASES=0` makes the 58 generative tests pass with zero iterations; the run still fails because three canaries fail.
Acceptable (loud overall), but someone reading only the non-canary results could be misled.

**I-2 (Info)** Consistent deletion of a case plus a `case_count` decrement is invisible to the TS and C# runners; the Python
`test_committed_cases_equal_...` and the CI regenerate-and-diff catch it.

**I-3 (Info, environment)** `core.autocrlf=true` here, so `git archive` extracts CRLF; all suites pass on CRLF, the regenerated vectors are LF and
byte-identical to the HEAD blob. A stale installed contexel can shadow the checkout for `parity/generate_vectors.py` (first-pass F-11); I used
`PYTHONPATH` and printed `contexel.__file__`.

## 8. What I could not verify

- CI itself (GitHub Actions matrix, macOS/Linux, other Python versions): only Windows 11 with Python 3.12.7 was run in this pass.
- TS and C# versions of mutants C16, P1-P4, P6, P8 (run only in Python).
- C9 Python: I captured only the first failing names and the total (`20 failed, 177 passed`). The two new effect tests
  (`test_filter_stage_has_its_effect[dedupe_key|dedupe_whole]`) are listed in the fix-wave report, not in my own output.
- Python 3.8/3.9 syntax compatibility of the fix-wave files (not re-checked this pass).
- Security sweep: out of scope (test and vector infrastructure only; no new dependency).

## 9. QA verdict

PASS. All 17 first-pass survivors are caught in every language, the regression rows still hold, the harness seed and tamper checks are loud,
the golden baselines match `main`, and no library file changed. One Low finding (Python-only coverage of two pre-existing behaviors) is
optional follow-up.
