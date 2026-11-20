<!-- Filed copy of the Slice 1 workspace file `fix-wave-report.md` (2026-11-20), sanitized for a public
repository: user and temp-directory path prefixes are replaced by `<scratch>`. Workspace
names used inside map to: `qa-report.md` -> `docs/qa/foundation-hardening-s1-qa-pass-1.md`; `qa-report-2.md` -> `docs/qa/foundation-hardening-s1-qa-pass-2.md`; `fix-wave-findings.md` -> `docs/reviews/foundation-hardening-s1-fix-wave-findings.md`; `fix-wave-report.md` -> `docs/reviews/foundation-hardening-s1-fix-wave-report.md`. -->

# Slice 1 final fix wave: report

**Branch:** `feat/hardening-s1-safety-net` · **Start:** `827750a` · **Final HEAD:** `f44d006` (6 new commits, nothing pushed, no version bump)
**Status:** DONE_WITH_CONCERNS (all findings fixed; all 17 QA survivors now caught; the concerns in section 9 are minor)

## 1. What changed, per finding

### A. Property tests (`tests/_gen.py`, `tests/test_properties.py`)

| Finding | Change |
|---|---|
| I1 / F-6 rank stability + positional correspondence | `indexed()` tags each record with its input index `_i`. `check_rank` asserts: a permutation (canonical JSON), missing scores last, scores descending, equal scores in ascending `_i` order, and missing-score records in ascending `_i` order. New `test_transform_stage_keeps_input_positions` over `ORDER_KEEPING = [select, quarantine_flag, rescore, truncate]` (rank reorders, so it is excluded) asserts `(out[i]._i, out[i].path) == (i, in[i].path)`. The `select` stage now also keeps `_i`, so it keeps what is compared. |
| I2 every check has a canary | Checks are now named functions. A `CANARIES` table gives 15 canaries, each a broken stage that its check must reject with the check's own message: subsequence (reverse), count (drop first), positions (reverse), rank permutation (drop), rank missing-last (missing first), rank descending (ascending), rank ties (QA mutation 7 exactly: tie-break by `(score, str(path))`), trim budget (identity), `min_records` count (ignores `min_records`), `min_records` prefix (reverse), and the five filter effects (identity, or `_flag_nothing` for flag). Plus `test_canary_subsequence_helper_respects_order_and_multiplicity` (shared-iterator logic: `[3,1]` vs `[1,2,3]` is False; `[1,1]` vs `[1,2]` is False) and the M3 test. The three original canaries are untouched. Docstring and CHANGELOG were re-read and reworded so the claim stays true. |
| F-7 effects | `test_filter_stage_has_its_effect` over `dedupe_key` (no two outputs share `(path, line)`), `dedupe_whole` (no two outputs canonically equal), `allowlist` (every `source` in `["repo", "docs"]`), `quarantine_drop` (no output snippet contains the marker), `quarantine_flag` (`quarantined is (marker in snippet)` for every record; an equality, since no other generated word forms a built-in pattern). The generator now emits exact duplicates (15% of records after the first are deep copies of an earlier one), so the dedupe effects are not vacuous. |
| M3 seed on exception | `reporting(seed)` context manager plus `for_each_case(check, seed_source)`: any exception without `(seed=N)` in its message is re-raised as `AssertionError("<Type>: <msg> (seed=N)") from exc` (3.9-compatible, no `add_note`). Proven by `test_canary_a_stage_that_raises_still_reports_its_seed` (a stage raising `KeyError`; asserts the seed text and `__cause__` is `KeyError`). |
| F-10 extra keys | 50% of generated records get a `junk` key and 0-2 `extra_<n>` keys with varied values (None, ints, a non-integer float, strings, bools, lists, a nested dict, accented text written as escapes). Goldens do not use the generator (unaffected). |
| M6 | `test_trim_min_records_keeps_the_best_records` renamed `test_trim_min_records_keeps_a_prefix_of_at_least_min_records`; the IDEMPOTENT comment now cites the design spec section 3 error table and brief AC 5 instead of ADR-003. |
| (found during the work) | With the reproduction recipe `CONTEXEL_PROP_CASES=1` two table canaries failed (the single case had no duplicate / no tie). Commit `190c511`: table canaries and the raise test now draw from `_gen.canary_seeds()` (the run's seeds, then the 200 default seeds). The three original canaries are unchanged and still fail loudly with `CONTEXEL_PROP_CASES=0` (verified: `3 failed, 58 passed`). |

`tests/_gen.py` non-ASCII literals were rewritten as `\u` escapes (same values). 0 non-ASCII bytes, 0 CR bytes.

### B. Golden fingerprints (`tests/test_fingerprint_golden.py`)
- New shape `dict_with_mixed_keys_and_nesting`: a named custom stage `annotate` bound to `mapping={"b": [1, None, {"z": 2.5}], 1: "one", 2.5: {"k": None}, None: [], (1, "t"): False}`, `empty={}`, `label="m"`. Its stable repr is `{None:[],2.5:{'k':None},1:'one','b':[1,None,{'z':2.5}],(1, 't'):False}` (sorted by type name and then repr; sorting by repr alone would give a different order, which is why row 15 is caught).
- New shape `opaque_object`: `stage(annotate, marker=Opaque(), n=3)` with a module-level `class Opaque`; repr `('marker', 'Opaque')`.
- M4: `contract` is now an inline copy of today's `generate_vectors.contract()` (same 8 stages and parameters); the `generate_vectors` import and the `sys.path` edit were removed; the hex is unchanged.
- The misnamed `nested_dict_and_none` was renamed `list_of_mixed_scalars_and_none` (same hex). All 8 pre-existing hex values are still present, byte for byte.

### C. Parity cases (`parity/parity_cases.py`, `tests/test_parity_cases.py`, regenerated `parity/vectors.json`)
Six cases were appended after the existing 22 (section 2 has the arithmetic):
`merge/two_candidates_first_in_schema_order_wins`, `truncate_field/fits_by_code_points_not_bytes_or_utf16`, `quarantine/marker_in_second_field_is_dropped`, `quarantine/marker_in_second_field_is_flagged`, `trim_to_budget/budget_is_the_exact_cost_of_three`, `rescore/proximity_window_is_80_characters`.
M1: `test_build_cases_runs_the_envelope_guard_on_every_part` (monkeypatches `_raw_cases`; one integer-valued float reaches only the input, only the args, or only the expectation; each asserts the matching `bad/in.<part>` message). `test_committed_cases_equal_what_the_case_table_builds_today` makes the module docstring's "same check CI does with git diff" claim true. The envelope guard itself was not touched.

### D. Runner floors
TS `ts/test/cases.test.ts`: `assert.ok(vectors.cases.length > 0, ...)`. C# `CaseTests.cs`: `Assert.NotEmpty(cases)`. These are one line each. Strict `args` validation and the M2 default shadowing were not started (still parked for Slice 2).

### E. Docs (`f44d006`)
- `docs/plans/foundation-hardening.md`: header status; the Slice 1 row is now **done** with branch, commit range `b986dcb`…`190c511`, totals and this report's path, and its "Proven by" list is updated to 28 cases; F-11 is a new Execution-rules bullet, and the done-rule command now uses `PYTHONPATH=.`; the risks row gives both baselines (72/41/39 and 197/70/68); the Deviation log has M5 (AC 19 contract-shaped variant: `dedupe` on `tags`, `select` keeps `tags`, `rescore` query `retry backoff jitter` on `snippet` only, `truncate_field` 10, `trim_to_budget` 200; checked against `tests/test_determinism_processes.py` lines 33-40), the fix wave, and the stale-bytecode lesson; the Status snapshot is refreshed.
- Slice plan: an F-11 bullet in Global Constraints; Review Focus item 3, the File Structure row, the Task 1 interfaces and canary prose, the ADR-003 citation fix, and the Task 3 interfaces and golden prose are updated. Every count is updated with the old value kept in parentheses where it was history (61, 12, 49, 197 = 72 + 61 + 3 + 12 + 49, TS 70, C# 29 / 68, 28 + 1 = 29). `PYTHONPATH=.` is added to the generator commands. A "G4/G5 fix wave" paragraph is appended after the unchanged "Verified before writing" history.
- Code blocks were replaced by a script outside the repo (`fixwave-tools/sync_plan.py`) and verified as exact substrings. All eight are `OK`: `tests/_gen.py`, `tests/test_properties.py`, `tests/test_fingerprint_golden.py`, `tests/test_parity_cases.py`, `parity/parity_cases.py`, `ts/test/cases.test.ts`, `csharp/Contexel.Tests/CaseTests.cs`, and the CHANGELOG `[Unreleased]` section. That last block had already drifted before this wave (it lacked the seed-took-effect and NFC/NFD sentences) and is now exact. The unchanged `tests/test_determinism_processes.py` block was also verified in sync.
- CHANGELOG `[Unreleased]`: the property list (input order, rank tie stability, filter effects; every check with a canary; seed printed even when a stage raises), dict and opaque goldens, the boundary cases, and the runner floors.

## 2. Discrimination arithmetic for the new parity cases

Heuristic token count: `max(1, ceil(n / 4))` where n is code points (canon), UTF-16 units (TS/C# rows 32/41), or UTF-8 bytes (Python rows 24/26).

**truncate_field, max_tokens = 4** (fits when count <= 4, i.e. n <= 16). Suffix `\u2026` counts 1 under every rule, so a truncation keeps `4 * (4 - 1) = 12` code points + `\u2026`. Measured (real output):
```
'\u65e5\u672c\u8a9e' * 4   cp 12 tok 3 | utf16 12 tok 3 | bytes 36 tok 9
'a'*15 + U+1F600           cp 16 tok 4 | utf16 17 tok 5 | bytes 19 tok 5
U+1F600 * 9                cp  9 tok 3 | utf16 18 tok 5 | bytes 36 tok 9
'a'*17                     cp 17 tok 5 | utf16 17 tok 5 | bytes 17 tok 5
```
- Canon: inputs 1-3 are unchanged; input 4 becomes `'a'*12 + '\u2026'`.
- Bytes rule (rows 24, 26): inputs 1, 2, 3 are truncated (1 and 3 keep all 12 or 9 code points but gain the suffix; 2 becomes `'a'*12 + '\u2026'`), so the case differs.
- UTF-16 rule (rows 32, 41): inputs 2 and 3 are truncated, so the case differs. Input 1 does not discriminate UTF-16 (BMP only); it is the bytes discriminator.
- Input 4 is over budget under every rule (the boundary control: 16 fits, 17 does not).

**trim_to_budget, max_tokens = 12**, input `{"a": 1}` … `{"a": 5}`. Each serializes to `{"a": N}`: 8 chars, 2 tokens.
- Canon `+2`: cost 4 each, cumulative 4, 8, 12 (12 <= 12 kept), 16 > 12 → **3 kept**.
- `+1` (rows 9, 29, 36): cost 3, cumulative 3, 6, 9, 12 → 4 kept, then 15 > 12 → **4 kept**.
- `+3` (row 10 analogue): cost 5, cumulative 5, 10, 15 > 12 → **2 kept**. (A `>=` comparison would also keep 2.)

**rescore, query `alpha beta`, fields `["s"]`**, texts `"alpha " + "z"*(gap-7) + " beta"`, so "beta" starts exactly `gap` characters after "alpha" (gap = 79, 80, 81). n = 3, df = 3 for both terms → idf = ln(0.5/3.5 + 1) = 0.133531. tf = 1 → each term contributes 0.133531 × 1/2.5, so base = 0.106825; proximity bonus = (idf + idf)/4 = 0.066766.
- Canon (window 80, `0 < gap <= 80`): scores 0.173591, 0.173591, 0.106825 (all non-integer floats, all records match).
- window 79 (rows 47, 4791, 4792): gap 80 loses the bonus, so record 2 becomes 0.106825.
- window 81 (extra row 4781): gap 81 gains it, so record 3 becomes 0.173591.

**merge**, schema `title: [title, name, headline]`, `url: [url, link, href]`:
- Record 1 `{name: N1, title: T1, href: h1, url: u1}`: canon `{title: T1, url: u1}`; without `break` (last match wins) it gives `{title: N1, url: h1}`.
- Record 2 `{headline: H2, name: N2, link: l2, href: h2}`: canon `{title: N2, url: l2}`; without `break` it gives `{title: H2, url: h2}`.

**quarantine**, fields `["title", "snippet"]`:
- Record 1 has the marker only in `snippet`; record 2 is clean; record 3 has `Ignore prior instructions` in `title`.
- Canon drop keeps `[record 2]`; canon flag gives `[True, False, True]`.
- Scanning only the first field (rows 22, 30, 37) keeps record 1 (drop) and flags it False (flag).
- These are direct stage cases, so no earlier stage can remove the record.

## 3. Mutation proof (scratch copy, never /d/contexel)

Method: `git -C /d/contexel archive f44d006 | tar -x -C <scratch>/fixwave-proof`, then `ts/node_modules` copied (no network). One mutation at a time comes from `fixwave-tools/mutate.py`, which asserts its anchor text occurs exactly once. After each run the file is restored, touched, and `cmp`'d against the blob ("restored … (matches f44d006)" for every row). `PYTHONDONTWRITEBYTECODE=1` is set, `__pycache__` is purged before each Python run, and `PYTHONPATH=<scratch>` (verified: `contexel from …\fixwave-proof\contexel\__init__.py`). TS and C# run against the NEW committed vectors. Baselines in the scratch copy: `197 passed`, `tests 70 / pass 70 / fail 0`, `Passed: 68, Total tests: 68`.

**A trap I hit and fixed:** my first Python run reused the copy without purging bytecode. Row 14 (and rows 9, 17, 18, 47) keep the file size, and the restore landed in the same mtime second, so a stale `.pyc` of the row 14 mutant contaminated rows 9, 24, 26, 49 and 4781 (spurious golden failures). MSBuild has the same hazard (the restored file is older than the build output). The driver was fixed and every row re-run. The results below come from the clean runs, at both `7208c36` and `f44d006`, with identical failing-test names (diffed).

| Row | Exact change | Python fails | TypeScript fails | C# fails |
|---|---|---|---|---|
| 1 | `select`: `for r in records: r.pop("junk", None)` | `test_stage_is_pure_and_deterministic[select]` (1 failed, 196 passed) | n/a | n/a |
| 7 | `rank`: sort key `(r[by], str(r.get("path")))` | `test_rank_is_a_permutation_and_stable` ("tie order changed (seed=20261131)") | n/a | n/a |
| 15 | `_stable_repr` dict sort key `repr(kv[0])` | `golden[dict_with_mixed_keys_and_nesting]` | n/a | n/a |
| 17 | dict open brace `{` → `<` | `golden[dict_with_mixed_keys_and_nesting]` | n/a | n/a |
| 18 | dict item `k:v` → `k=v` | `golden[dict_with_mixed_keys_and_nesting]` | n/a | n/a |
| 19 | opaque fallback → `"obj"` | `golden[opaque_object]` | n/a | n/a |
| 22 | `quarantine`: `_field_list(fields)[:1]` | `case[quarantine/marker_in_second_field_is_dropped]`, `case[…_is_flagged]`, `test_committed_cases_equal_what_the_case_table_builds_today` | n/a | n/a |
| 29 | TS trim `+ 2` → `+ 1` | n/a | `case trim_to_budget/budget_is_the_exact_cost_of_three` (fail 1 / pass 69) | n/a |
| 30 | TS quarantine `fieldList(...).slice(0, 1)` | n/a | `case quarantine/marker_in_second_field_is_dropped`, `…_is_flagged` (fail 2) | n/a |
| 32 | TS `codePointLength` → `return text.length` | n/a | `case truncate_field/fits_by_code_points_not_bytes_or_utf16` (fail 1) | n/a |
| 33 | TS merge: remove `break` | n/a | `case merge/two_candidates_first_in_schema_order_wins` (fail 1) | n/a |
| 36 | C# TrimToBudget `+ 2` → `+ 1` | n/a | n/a | `CaseMatchesPython("trim_to_budget/budget_is_the_exact_cost_of_three")` (Failed 1, Passed 67) |
| 37 | C# Quarantine `FieldList(...).Take(1).ToList()` | n/a | n/a | `CaseMatchesPython("quarantine/marker_in_second_field_is_dropped")`, `(…_is_flagged)` (Failed 2) |
| 39 | C# Merge: remove `break` | n/a | n/a | `CaseMatchesPython("merge/two_candidates_first_in_schema_order_wins")` (Failed 1) |
| 41 | C# `CodePointLength` → `return text.Length` | n/a | n/a | `CaseMatchesPython("truncate_field/fits_by_code_points_not_bytes_or_utf16")` (Failed 1) |
| 42 | Python merge: remove `break` | `case[merge/two_candidates_first_in_schema_order_wins]`, `test_committed_cases_equal_…` | n/a | n/a |
| 47 | Python rescore `window = 79` | `case[rescore/proximity_window_is_80_characters]`, `test_committed_cases_equal_…` | n/a | n/a |
| **Regression checks (were already caught)** | | | | |
| 6 | rank ascending sort then `reverse()` if desc | `case[rank/missing_field_goes_last_desc]`, `test_committed_cases_equal_…`, `idempotent[rank]`, `test_rank_is_a_permutation_and_stable` (4 failed) | n/a | n/a |
| 14 | list brackets `[ ]` → `( )` | golden `[contract]`, `[dict_with_mixed_keys_and_nesting]`, `[list_of_mixed_scalars_and_none]`, `[primitives]`, `[rescore_defaults]` (5 failed) | n/a | n/a |
| 27 | TS dedupe keeps the LAST duplicate | n/a | `case dedupe/nfc_and_nfd_stay_distinct`, `case merge/schema_first_present_wins_and_dedupes`, `edge: dedupe keeps {} and [] distinct` (fail 3) | n/a |
| **Extras (beyond the required rows)** | | | | |
| 9 | Python trim `+ 2` → `+ 1` | `case[trim_to_budget/budget_is_the_exact_cost_of_three]`, `test_committed_cases_equal_…`, `test_trim_never_exceeds_budget_without_min_records` | n/a | n/a |
| 24 | tokens heuristic counts bytes | `case[trace_report/contract_on_fixture]`, `case[truncate_field/fits_by_code_points_not_bytes_or_utf16]`, `test_committed_cases_equal_…`, `idempotent[truncate]` | n/a | n/a |
| 26 | truncate guard also needs `len(text.encode()) <= 4*max_tokens` | `case[truncate_field/fits_by_code_points_not_bytes_or_utf16]` (now the named case catches it), `test_committed_cases_equal_…`, `idempotent[truncate]` | n/a | n/a |
| 49 | dedupe never dedupes | 20 failed, now including `test_filter_stage_has_its_effect[dedupe_key]` and `[dedupe_whole]` (F-7) | n/a | n/a |
| 4781 | Python rescore `window = 81` | `case[rescore/proximity_window_is_80_characters]`, `test_committed_cases_equal_…` | n/a | n/a |
| 4791 | TS `window = 79` | n/a | `case rescore/proximity_window_is_80_characters` (fail 1) | n/a |
| 4792 | C# `window = 79` | n/a | n/a | `CaseMatchesPython("rescore/proximity_window_is_80_characters")` (Failed 1) |

**Result: all 17 of 17 former survivors are caught; rows 6, 14 and 27 are still caught; no survivors.** (Python mutations can only be caught by the Python suite: TS/C# test the ports against committed vectors, as QA noted.)

Further negative controls, all in the scratch copy:
- `cases: []` with `case_count: 0`: TS `✖ the cases section is present and complete`, `ℹ fail 1 / pass 41` (previously a silent pass). C# `Failed CasesSectionIsPresentAndComplete`, `Failed CaseMatchesPython`, `Failed: 2, Passed: 39`. Python `test_unicode_normalization_case_has_two_distinct_keys` and `test_committed_cases_equal_what_the_case_table_builds_today` fail (`2 failed, 19 passed, 1 skipped`).
- The plan's Task 5/6 tamper script (one reversed expectation, one unknown key, wrong case_count): TS `ℹ fail 3 / pass 68` (completeness, `rank/missing_field_goes_last_desc`, `bad/extra_key`); C# CaseTests `Failed! - Failed: 3, Passed: 27, Total: 30`; after restore, C# CaseTests `Passed: 29`.
- Deleting the three `assert_in_envelope` calls in `build_cases` (M1): `3 failed, 46 passed` (`test_build_cases_runs_the_envelope_guard_on_every_part[input-case0]`, `[args-case1]`, `[expect-case2]`).
- Seed reproduction at f44d006 with row 7 applied: `CONTEXEL_PROP_SEED=20261131 CONTEXEL_PROP_CASES=1` gives `E AssertionError: tie order changed (seed=20261131)`, `FAILED …test_rank_is_a_permutation_and_stable`, `1 failed, 60 passed` (only the real failure).

## 4. Suite totals (from /d/contexel at f44d006, real output)

```
== HEAD f44d006
== Python
197 passed in 2.84s
== TypeScript
ℹ tests 70
ℹ pass 70
ℹ fail 0
== C#
Passed!  - Failed:     0, Passed:    68, Skipped:     0, Total:    68, Duration: 57 ms - Contexel.Tests.dll (net8.0)
== generator
d:\contexel\contexel\__init__.py
wrote D:\contexel\parity\vectors.json (21652 bytes)
vectors fresh (git diff --exit-code clean)
== library diff vs main
(end library diff)
== co-authored trailers on branch: 0
== unpushed/upstream:
fatal: no upstream configured for branch 'feat/hardening-s1-safety-net'
0
== status
(end status)
```
Per file: properties 61 (was 35), golden 12 (was 10), parity 49 (was 39), determinism 3 (unchanged): 72 + 61 + 3 + 12 + 49 = 197. TS 70 = 41 + 28 cases + 1 completeness. C# 68 = 39 + 28 + 1. Parity cases: 28 (was 22).
Other interpreters: Python 3.11 `197 passed in 2.31s`. Python 3.9.13 and 3.8.10 compile the 5 changed Python files. Under 3.9.13 (no pytest installed, no network), the property, golden and parity test functions ran through a 50-line pytest shim kept outside the repo: `122 passed, 0 failed` (61 + 12 + 49). Property runs: `PYTHONHASHSEED` 0/1/2 each `61 passed`; `CONTEXEL_PROP_SEED=1 CONTEXEL_PROP_CASES=1000` `61 passed in 9.07s`; `CONTEXEL_PROP_CASES=0` gives the 3 original canaries failing (`3 failed, 58 passed`, loud by design).

## 5. Golden hex values and their verification

| Shape | Hex | Status |
|---|---|---|
| `dict_with_mixed_keys_and_nesting` | `5d865072cb72afe5` | NEW |
| `opaque_object` | `79dab73b8b021852` | NEW |
| `contract` (now inline) | `0a312755f913d64b` | unchanged |
| `list_of_mixed_scalars_and_none` (renamed) | `3e55e84d283957fb` | unchanged |
| `primitives`, `named_callable`, `bare_named_function`, `rescore_defaults`, `empty_pipeline`, keyword-order test | `24b66acf41ad058f`, `c0528eaa77a2360e`, `0841f22ac0700431`, `11b53020d9d935bb`, `2e38e77b22c314a4`, `4576e85b3ab2efb1` | unchanged |

Verification: `fixwave-tools/golden_values.py` computes (does not read) each shape's fingerprint with a given library root first on `sys.path`, and asserts that contexel was imported from that root. It ran for the checkout (`D:\contexel\contexel`) and for a `git archive main` copy (`…\fixwave-main\contexel`), each under `PYTHONHASHSEED` 0, 1 and 2. That is 6 runs, and `sort | uniq -c` printed every shape with count 6 and `computed == recorded`, for example `6 dict_with_mixed_keys_and_nesting computed=5d865072cb72afe5 recorded=5d865072cb72afe5` and `6 opaque_object computed=79dab73b8b021852 recorded=79dab73b8b021852`. `pytest tests/test_fingerprint_golden.py` under seeds 0/1/2 gave `12 passed` each time. Every pre-existing hex was grep-confirmed present. The library is unchanged (`git diff --stat main -- contexel ts/src csharp/Contexel` is empty), so these are pre-Slice-2/3 baselines.

## 6. Vectors integrity

The generator was run with `PYTHONPATH=/d/contexel` (verified `d:\contexel\contexel\__init__.py`). It ran twice and the outputs were `cmp`-identical (BYTE-STABLE). `fixwave-tools/check_vectors.py` on the committed blobs (`main`, `827750a`, `HEAD`) printed:
```
legacy sections identical to main (8 sections + _meta minus case_count)
previous 22 cases unchanged; appended 6: merge/two_candidates_first_in_schema_order_wins, truncate_field/fits_by_code_points_not_bytes_or_utf16, quarantine/marker_in_second_field_is_dropped, quarantine/marker_in_second_field_is_flagged, trim_to_budget/budget_is_the_exact_cost_of_three, rescore/proximity_window_is_80_characters
case_count 22 -> 28; LF only; UTF-8 OK
HEAD blob CR bytes: 0
```
It also asserts that the top-level key order is unchanged and that `_meta` differs only in `case_count`. `git diff` of the regeneration showed exactly one removed line, `-    "case_count": 22`; everything else was additions. All new case data passed the unchanged envelope guard (strings, ints, bools; the rescore outputs are non-integer floats). `git diff --exit-code parity/vectors.json` after regeneration at f44d006 is clean. Every committed blob of the changed files has 0 CR bytes; the new Python sources have no non-ASCII bytes, and the only non-ASCII in `parity/parity_cases.py` is the pre-existing line 98 (`日本語` CJK, unchanged).

## 7. Commits (`main..HEAD`, new in this wave; author the configured author, no trailers)

| SHA | Subject |
|---|---|
| `59b569b` | test(props): pin tie order, filter effects and a canary per check |
| `aed3ae5` | test(golden): pin dict and opaque-object fingerprints |
| `0453446` | test(parity): boundary cases for merge, truncate, quarantine, trim |
| `7208c36` | test(runners): fail when the cases array is empty |
| `190c511` | test(props): keep table canaries independent of the run size |
| `f44d006` | docs: record the Slice 1 fix wave and sync the plans |

Each commit was green when made (Python 185 → 187 → 197 → 197 → 197; TS/C# 70/68 from `0453446` on).

## 8. Files

Tests: `tests/_gen.py`, `tests/test_properties.py`, `tests/test_fingerprint_golden.py`, `tests/test_parity_cases.py`. Cases: `parity/parity_cases.py`, `parity/vectors.json`. Runners: `ts/test/cases.test.ts`, `csharp/Contexel.Tests/CaseTests.cs`. Docs: `CHANGELOG.md`, `docs/plans/foundation-hardening.md`, `docs/superpowers/plans/2026-11-19-foundation-hardening-s1-safety-net.md`. Throwaway tooling (outside the repo): `<scratch>/fixwave-tools/` (`mutate.py`, `proof.sh`, `golden_values.py`, `check_vectors.py`, `sync_plan.py`, `escape_*.py`, `shim/`, and raw logs `final-py.txt`, `final-tscs.txt`, `proof-py.txt`, `proof-ts.txt`, `proof-cs.txt`).

## 9. Concerns (none blocking)

1. **Mutation-driver hazard.** Restoring a same-size file within one mtime second runs a stale `.pyc`, and MSBuild can skip the rebuild. My first pass was contaminated and has been fully re-run. QA's results looked consistent with fresh copies per mutation, but any future mutation work should purge bytecode and touch restored files. This is recorded in the master plan's Deviation log.
2. **The Write/Edit tools turned `\uXXXX` escapes into literal characters** (but not `\U0001F600`). I caught this with a byte check and re-escaped via scripts. The only non-ASCII left in changed sources is the pre-existing CJK on `parity_cases.py` line 98.
3. **The `quarantine_flag` effect check asserts equality** (`flag is marker-present`), which relies on no other generated word forming a built-in pattern. That holds for today's `WORDS`; anyone who adds words like "system prompt" must update it.
4. **Row 22 (Python quarantine first-field-only) is caught only by the parity cases**, not by a property: the property stages use the default single field. This is deliberate, because the parity case pins it in all three languages.
5. **The original three canaries still depend on run size** (they fail at `CASES=0` by design and, if the chosen seed's case is empty, at `CASES=1`). Left unchanged so no existing test is altered.
6. **The plans cite this report's path, but `.superpowers/` is excluded via `.git/info/exclude`**, so that evidence is local, not committed.
7. **Cosmetic:** the M1 parametrize ids read `input-case0` etc.; the C# console truncates one long case id in output (display only).
8. **Not verified:** the CI matrix (Linux/macOS, Python 3.10/3.13). Real pytest ran on 3.12 and 3.11 only; 3.9 ran through the shim and 3.8 compile-only.

## 10. Not done (by instruction)
Strict `args`-key validation in the runners and the C# runner's default shadowing (M2) stay parked for Slice 2. No push, no version bump, no branch change.
