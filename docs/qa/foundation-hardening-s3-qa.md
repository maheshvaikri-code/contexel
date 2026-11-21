> Filed 2026-11-20 from the Slice 3 review workspace for branch `feat/hardening-s3-audit-release` (head `c8bc7f3` after the fix wave; commit hashes in this document are those of the branch after one subject was reworded). Sanitised: no user name, home or temporary path, e-mail address or agent identifier. Gate G5 QA (executed: mutation testing, adversarial scenarios).

# G5 QA Report - Foundation hardening Slice 3 (audit truthfulness and release hygiene) @ 5f4e444

**QA Engineer** (fresh-context verifier, G5) - **Date:** 2026-11-20
**Build under test:** branch feat/hardening-s3-audit-release, head 5f4e444 (base 0f09d36 = main). Every run used a fresh `git archive HEAD` copy under <tmp> (one per mutant); the repository itself was never written (`git status --short` on it is empty at the end). No packages installed, no network.

## Verdict

**G5 QA: PASS WITH CONDITIONS**

Every acceptance criterion AC28-AC33 was demonstrated by execution; no defect in the shipped code was found. Mutation kill rate **36/44 = 81.8%** (36/42 = 85.7% excluding the 2 equivalent mutants; 36/40 = 90.0% also excluding the 2 workflow-YAML mutants that no repo test can see by design).

Condition: add the missing regression for the `max(0, ...)` clamp of AC28 (survivor M3, MAJOR test gap: a regression that silently removes a real drop from the audit passes every Python and TypeScript test). The other gaps below are MINOR and recommended.

## 1. Baselines (clean copy, real output)

PYTHONPATH pointed at the copy; `contexel.__file__` resolved inside it (`<tmp>/base/contexel/__init__.py`).

~~~
$ PYTHONPATH=. python -B -m pytest -q -p no:cacheprovider --ignore-glob='tests/test_doctrine_*'      (Python 3.12.7)
531 passed in 3.28s
$ cd ts && npm run build && npm test                                                                  (Node v24.18.0)
i tests 351 | i pass 351 | i fail 0
$ dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo                                    (SDK 8.0.403)
Passed!  - Failed:     0, Passed:   312, Skipped:     0, Total:   312, Duration: 34 ms - Contexel.Tests.dll (net8.0)
(grep -ci warn on the full dotnet log: 0)
$ PYTHONPATH=. py -3.11 -B -m pytest -q -p no:cacheprovider --ignore-glob='tests/test_doctrine_*'     (Python 3.11.9)
529 passed, 2 skipped in 3.78s
SKIPPED [1] tests/test_audit_truth.py:287: could not import 'tiktoken': No module named 'tiktoken'
SKIPPED [1] tests/test_packaging.py:22: could not import 'hatchling.build': No module named 'hatchling'
~~~
Python 3.9.13: pytest is NOT installed for 3.9. Done instead: all 15 new/changed Python files compile on 3.9; a minimal pytest stand-in (importorskip / raises / mark / fixture) ran every zero-fixture test of test_audit_truth, test_fingerprint_golden, test_check_versions, test_packaging, test_parity_cases:
~~~
3.9.13 {'pass': 26, 'fail': 0, 'skip': 1, 'needs-fixture': 20}      (the 20 fixture-using tests were not run on 3.9)
~~~
plus the trace, fingerprint and check_versions scenario scripts below, all run on 3.9 with the same results as on 3.12.

## 2. Acceptance criteria

| AC | How executed | Evidence | Pass |
|----|--------------|----------|------|
| 28 trace attribution | Python and TS scenario scripts; the 7 `trace_dropped_ids` vectors through all three runners; mutants M1-M6, T1-T2, C1-C3 | drop beside an id-less record reported; select stripping ids is not a drop; probe case gives ['a','b'] in Python and TS; M1, M2, M4, M5, M6, T1, T2, C1, C2, C3 killed | yes (test gap: M3) |
| 29 fingerprint coverage | fingerprint scenarios on HEAD and main; TS scenario; mutants M7, M11, M12, T3, C4, C5, O2 | set fingerprint identical under PYTHONHASHSEED 0/1/2/99; a change only in the innermost of three nested pipelines changes the fingerprint on HEAD (collides on main); a plain pipeline keeps 1c2c20c9aa204c96 on main and HEAD; golden tests pass in all three languages | yes |
| 30 snapshot at build | mutants M8, M9, M13a, M13b, T4, T5, T6, O3, O6; TS scenario (caller mutates a bound array afterwards; JSON `__proto__` key) | all killed except M13b (frozenset identity, MINOR gap); TS fingerprint and behaviour unchanged after caller mutation | yes |
| 31 tiktoken special text | mutant M10 | killed by the fake-module test AND by the real tiktoken 0.8.0 test (cached encoding, 3.12) | yes |
| 32 py.typed, ruff, mypy | ruff, mypy, hatchling wheel build (section 4.6); mutant O5 | clean; the wheel has contexel/py.typed and nothing outside contexel/ and dist-info; O5 killed | yes |
| 33 check_versions + CI | scenario matrix on copies of the real tree (3.12 and 3.9); mutants M14-M21b | each of the 7 locations mutated gives exit 1 naming the file; missing / non-UTF-8 / empty give exit 2 naming the file, no traceback | yes (the CI wiring itself is unguarded: M22/M23) |
| 34 changelog/docs | only through the doc-example tests in the suites | not independently re-verified | n/a here |

## 3. Mutation testing

One fresh archive copy per mutant, exactly one logical change, the change verified by diff (all applied diffs are listed after the table), suites rerun: Python with `python -B`; TS rebuilt with `npm run build` then `npm test`; C# `dotnet test` under a 10-minute cap (every C# run finished in under 10 s; no memory growth seen). Python mutants also regenerated the vectors and compared them with the committed blob (what the CI staleness check does).

| id | file:line | change | result | verdict |
|----|-----------|--------|--------|---------|
| M1 | contexel/trace.py:196 | lost = unidentified_out (no subtraction) | KILLED by py: 6 failed, 525 passed in 3.31s; tests/test_audit_truth.py::test_trace_reports_a_drop_when_another_survivor_never_had_the_id; tests/test_audit_truth.py::test_trace_dropped_ids_are_reported_in_input_order; tests/test_parity_cases.py::test_committed_case_matches_canon[trace_dropped_ids/drop_beside_a_record_without_the_id] [CI vector-staleness check: vectors DIFFER] | killed |
| M2 | contexel/trace.py:196 | lost = unidentified_in | KILLED by py: 12 failed, 519 passed in 3.49s; tests/test_audit_truth.py::test_trace_reports_a_drop_when_another_survivor_never_had_the_id; tests/test_audit_truth.py::test_trace_select_stripping_ids_is_not_a_drop; tests/test_audit_truth.py::test_trace_mixed_input_with_select_stripping_ids_is_not_a_drop [CI vector-staleness check: vectors DIFFER] | killed |
| M3 | contexel/trace.py:196 | no max(0, ...) | SURVIVED (py: 531 passed in 3.17s) [vectors unchanged] | SURVIVED - REAL GAP (MAJOR test gap). No test has a stage that outputs fewer id-less records than it was given while more than one identified record is unmatched. Probe: input [{t:x},{id:a,t:x},{id:b,t:x},{id:c,t:y}], allowlist t in [y]: HEAD reports ['a','b'], M3 reports ['b'] (a real drop vanishes from the audit). Needed: a Python test plus a trace_dropped_ids vector of this shape |
| M4 | contexel/trace.py:197 | unmatched[lost:] -> unmatched[:lost] | KILLED by py: 19 failed, 512 passed in 3.49s; tests/test_audit_truth.py::test_trace_reports_a_drop_when_another_survivor_never_had_the_id; tests/test_audit_truth.py::test_trace_select_stripping_ids_is_not_a_drop; tests/test_audit_truth.py::test_trace_mixed_input_with_select_stripping_ids_is_not_a_drop [CI vector-staleness check: vectors DIFFER] | killed |
| M5 | contexel/trace.py:197 | dropped = whole unmatched | KILLED by py: 8 failed, 523 passed in 3.43s; tests/test_audit_truth.py::test_trace_select_stripping_ids_is_not_a_drop; tests/test_audit_truth.py::test_trace_mixed_input_with_select_stripping_ids_is_not_a_drop; tests/test_audit_truth.py::test_trace_ambiguity_is_bounded_by_the_lost_count [CI vector-staleness check: vectors DIFFER] | killed |
| M6 | contexel/trace.py:173, contexel/trace.py:181 | id presence by truthiness (both loops) | KILLED by py: 2 failed, 529 passed in 3.37s; tests/test_parity_cases.py::test_committed_case_matches_canon[trace_dropped_ids/falsy_ids_are_reported]; tests/test_parity_cases.py::test_committed_cases_equal_what_the_case_table_builds_today [CI vector-staleness check: vectors DIFFER] | killed |
| M7 | contexel/pipeline.py:58 | set rendering without sorted | KILLED by py: 1 failed, 530 passed in 3.77s; tests/test_audit_truth.py::test_fingerprint_of_a_set_is_the_same_under_every_hash_seed [vectors unchanged] | killed |
| M8 | contexel/pipeline.py:94 | stage() binds caller's objects (no snapshot) | KILLED by py: 3 failed, 528 passed in 3.28s; tests/test_audit_truth.py::test_bound_container_mutation_cannot_change_behavior; tests/test_audit_truth.py::test_nested_bound_containers_are_copied_at_every_depth; tests/test_audit_truth.py::test_a_stage_gets_the_same_private_copy_on_every_call [vectors unchanged] | killed |
| M9 | contexel/pipeline.py:120 | pipeline() does not copy stage list | KILLED by py: 1 failed, 530 passed in 3.90s; tests/test_audit_truth.py::test_pipeline_copies_its_list_of_stages [vectors unchanged] | killed |
| M10 | contexel/tokens.py:116 | disallowed_special=() removed | KILLED by py: 2 failed, 529 passed in 3.57s; tests/test_audit_truth.py::test_tiktoken_tokenizer_asks_for_special_tokens_to_be_ordinary_text; tests/test_audit_truth.py::test_tiktoken_counts_special_token_literals [vectors unchanged] | killed |
| M11 | contexel/tokens.py:119 | tiktoken tokenizer name reverted to <lambda> | KILLED by py: 1 failed, 530 passed in 3.55s; tests/test_audit_truth.py::test_fingerprint_differs_for_tiktoken_encodings [vectors unchanged] | killed |
| M12 | contexel/pipeline.py:143 | nested pipeline __contexel_desc__ not set | KILLED by py: 1 failed, 530 passed in 5.22s; tests/test_audit_truth.py::test_fingerprint_differs_for_nested_pipelines [vectors unchanged] | killed |
| M13a | contexel/pipeline.py:72, contexel/pipeline.py:74, contexel/pipeline.py:76, contexel/pipeline.py:78 | _snapshot exact-type check weakened to isinstance (subclasses copied) | KILLED by py: 1 failed, 530 passed in 6.22s; tests/test_audit_truth.py::test_a_callable_a_custom_object_and_a_list_subclass_are_not_copied [vectors unchanged] | killed |
| M13b | contexel/pipeline.py:78 | frozenset treated as copied (converted to set) | SURVIVED (py: 531 passed in 3.99s) [vectors unchanged] | SURVIVED - REAL GAP (MINOR). Not equivalent: the stage receives a mutable, unhashable set instead of the caller's frozenset (probe: HEAD same_object=True, frozenset, hashable; M13b False, set, unhashable). Needed: assert a bound frozenset is passed through by identity |
| M14 | tools/check_versions.py:99 | check_versions skips location 'Python package (pyproject)' | KILLED by py: 3 failed, 528 passed in 3.33s; tests/test_check_versions.py::test_agreeing_versions_pass; tests/test_check_versions.py::test_disagreeing_versions_fail_naming_the_file[pyproject]; tests/test_check_versions.py::test_a_file_without_a_readable_version_fails_loudly[pyproject.toml-[project]\nname | killed |
| M15 | tools/check_versions.py:99 | check_versions skips location 'Python module' | KILLED by py: 4 failed, 527 passed in 3.61s; tests/test_check_versions.py::test_agreeing_versions_pass; tests/test_check_versions.py::test_disagreeing_versions_fail_naming_the_file[init]; tests/test_check_versions.py::test_a_file_without_a_readable_version_fails_loudly[contexel/__init__.py-__all__ | killed |
| M16 | tools/check_versions.py:99 | check_versions skips location 'npm package' | KILLED by py: 5 failed, 526 passed in 3.26s; tests/test_check_versions.py::test_agreeing_versions_pass; tests/test_check_versions.py::test_disagreeing_versions_fail_naming_the_file[package]; tests/test_check_versions.py::test_a_file_without_a_readable_version_fails_loudly[ts/package.json-{}] | killed |
| M17 | tools/check_versions.py:99 | check_versions skips location 'npm lockfile (root)' | KILLED by py: 2 failed, 529 passed in 3.31s; tests/test_check_versions.py::test_agreeing_versions_pass; tests/test_check_versions.py::test_disagreeing_versions_fail_naming_the_file[lock_root] | killed |
| M18 | tools/check_versions.py:99 | check_versions skips location 'npm lockfile (package entry)' | KILLED by py: 3 failed, 528 passed in 3.45s; tests/test_check_versions.py::test_agreeing_versions_pass; tests/test_check_versions.py::test_disagreeing_versions_fail_naming_the_file[lock_entry]; tests/test_check_versions.py::test_a_file_without_a_readable_version_fails_loudly[ts/package-lock.json-{"version": | killed |
| M19 | tools/check_versions.py:99 | check_versions skips location 'TypeScript constant' | KILLED by py: 3 failed, 528 passed in 4.30s; tests/test_check_versions.py::test_agreeing_versions_pass; tests/test_check_versions.py::test_disagreeing_versions_fail_naming_the_file[index_ts]; tests/test_check_versions.py::test_a_file_without_a_readable_version_fails_loudly[ts/src/index.ts-export | killed |
| M20 | tools/check_versions.py:99 | check_versions skips location 'NuGet package (csproj)' | KILLED by py: 5 failed, 526 passed in 3.51s; tests/test_check_versions.py::test_agreeing_versions_pass; tests/test_check_versions.py::test_disagreeing_versions_fail_naming_the_file[csproj]; tests/test_check_versions.py::test_a_missing_file_fails_loudly_naming_it | killed |
| M21 | tools/check_versions.py:122 | Unreadable -> exit 1 instead of 2 | KILLED by py: 10 failed, 521 passed in 3.48s; tests/test_check_versions.py::test_a_missing_file_fails_loudly_naming_it; tests/test_check_versions.py::test_a_file_without_a_readable_version_fails_loudly[pyproject.toml-[project]\nname; tests/test_check_versions.py::test_a_file_without_a_readable_version_fails_loudly[contexel/__init__.py-__all__ | killed |
| M21b | tools/check_versions.py:103 | UnicodeDecodeError not caught (pre-ac62956) | KILLED by py: 2 failed, 529 passed in 3.79s; tests/test_check_versions.py::test_a_file_that_is_not_utf8_fails_loudly_naming_it[contexel/__init__.py]; tests/test_check_versions.py::test_a_file_that_is_not_utf8_fails_loudly_naming_it[ts/package.json] | killed |
| M22 | .github/workflows/ci.yml:52 | ci.yml hygiene version step removed | SURVIVED (py: 531 passed in 3.23s) | SURVIVED-BY-DESIGN: no test or script reads .github/workflows/ci.yml; nothing in the repo would notice the hygiene version step being removed |
| M23 | .github/workflows/release.yml:44 | release.yml version step removed | SURVIVED (py: 531 passed in 3.14s) | SURVIVED-BY-DESIGN: same for release.yml; nothing in the repo would notice |
| T1 | ts/src/trace.ts:148 | lost as unidentifiedOut | KILLED by ts: pass 346 fail 5; trace reports a drop when another survivor never had the id; trace: dropped ids are reported in input order; case trace_dropped_ids/drop_beside_a_record_without_the_id | killed |
| T2 | ts/src/trace.ts:149 | slice(lost) -> slice(0, lost) | KILLED by ts: pass 336 fail 15; trace reports a drop when another survivor never had the id; trace: select stripping ids is not a drop; trace: a mixed input with select stripping ids is not a drop | killed |
| T3 | ts/src/pipeline.ts:40 | Set rendering without sort | KILLED by ts: pass 349 fail 2; the fingerprint of a set ignores insertion order; a Set nested in an array or an object is covered too | killed |
| T4 | ts/src/pipeline.ts:58, ts/src/pipeline.ts:59 | snapshot exact-prototype check -> Array.isArray / instanceof Set | KILLED by ts: pass 350 fail 1; a Set subclass and an Array subclass are passed through by identity | killed |
| T5 | ts/src/pipeline.ts:65 | defineProperty -> plain assignment | KILLED by ts: pass 349 fail 2; a JSON-parsed __proto__ param key stays an own key and re-parents nothing; a poisoned __proto__ policy behaves as it did unbound and fingerprints differently | killed |
| T6 | ts/src/pipeline.ts:85 | snapshot removed in stage() | KILLED by ts: pass 346 fail 5; a bound array changed afterwards cannot change behavior; nested bound containers are copied at every depth; a function, a class instance, a Map and the elements of a Set are not copied | killed |
| C1 | csharp/Contexel/Trace.cs:134 | lost as unidentifiedOut | KILLED by cs: ('Failed!', '6', '306') (2s); Contexel.Tests.CaseTests.CaseMatchesPython(id:; Contexel.Tests.AuditTruthTests.TraceReportsADropWhenAnotherSurvivorNeverHadTheId; Contexel.Tests.AuditTruthTests.TraceDroppedIdsAreReportedInInputOrder | killed |
| C2 | csharp/Contexel/Trace.cs:135 | Skip(lost) -> Take(lost) | KILLED by cs: ('Failed!', '17', '295') (2s); Contexel.Tests.CaseTests.CaseMatchesPython(id:; Contexel.Tests.ParityTests.AuditRecordMatchesPython; Contexel.Tests.AuditTruthTests.TraceAmbiguityIsBoundedByTheLostCount | killed |
| C3 | csharp/Contexel/Trace.cs:109, csharp/Contexel/Trace.cs:120 | null record null-check removed (null treated as an id-bearing dict) | KILLED by cs: ('Failed!', '1', '311') (2s); Contexel.Tests.AuditTruthTests.TraceCountsANullItemAsIdlessInsteadOfFailing | killed |
| C4 | csharp/Contexel/Pipeline.cs:99 | Set rendering without ordinal sort | KILLED by cs: ('Failed!', '1', '311') (2s); Contexel.Tests.FingerprintTests.TheFingerprintOfASetIgnoresInsertionOrderAndSetType | killed |
| C5 | csharp/Contexel/Pipeline.cs:68 | nested-pipeline detection removed | KILLED by cs: ('Failed!', '2', '310') (2s); Contexel.Tests.FingerprintTests.FingerprintDiffersForNestedPipelines; Contexel.Tests.FingerprintTests.ANestedPipelineWithItsOwnParametersStillContributesItsFingerprint | killed |
| O1 (own) | contexel/trace.py:166 | py id_key: str(value) so 1 and '1' collide | SURVIVED (py: 531 passed in 3.12s) [vectors unchanged] | SURVIVED - REAL GAP (MINOR): ids 1 and '1' collide under the mutant; no test mixes an int id with its string form. Needed: [{id:1 keep},{id:'1' drop}] gives dropped ['1'] |
| O2 (own) | contexel/pipeline.py:58 | py set rendered like a list ('[' prefix) | KILLED by py: 1 failed, 530 passed in 3.43s; tests/test_audit_truth.py::test_fingerprint_of_a_set_is_not_that_of_a_list_or_a_dict [vectors unchanged] | killed |
| O3 (own) | contexel/pipeline.py:79 | py _snapshot does not copy sets | KILLED by py: 1 failed, 530 passed in 3.48s; tests/test_audit_truth.py::test_nested_bound_containers_are_copied_at_every_depth [vectors unchanged] | killed |
| O4 (own) | tools/check_versions.py:48 | check_versions [project] header regex not CRLF tolerant | SURVIVED (py: 531 passed in 3.24s) | EQUIVALENT: Path.read_text uses universal newlines, so CRLF and CR-only text reach the regex as LF; the \s* before $ is never needed for line endings |
| O5 (own) | pyproject.toml:52 | wheel excludes py.typed (pyproject) | KILLED by py: 1 failed, 530 passed in 3.86s; tests/test_packaging.py::test_the_wheel_ships_py_typed | killed |
| O6 (own) | ts/src/pipeline.ts:103 | ts pipeline() does not copy stage array | KILLED by ts: pass 350 fail 1; pipeline copies its array of stages | killed |
| O7 (own) | csharp/Contexel/Pipeline.cs:103 | cs Settle does not recurse into dictionary values | SURVIVED (cs: ('Passed!', '0', '312') (3s)) | SURVIVED - REAL GAP (MINOR): a set nested in a dictionary parameter loses insertion-order independence. Confirmed with a probe xunit test (HashSet {c,a,b} vs {a,b,c} under a Rec key): passes on HEAD, fails on O7 (a96af6b821c0554a vs 963d23a0f1e77523). The existing test only checks that different contents differ |
| O8 (own) | ts/test/runner.ts:157 | ts vector runner: unknown kind returns undefined instead of throwing | SURVIVED (ts: pass 351 fail 0) | EQUIVALENT: validateSpec (runner.ts:170) rejects every kind not in ARG_NAMES before execute(), and every ARG_NAMES kind has a case, so the default branch is unreachable |

Uncounted probes, run to locate the M3 gap in the ports: **P-T** `ts/src/trace.ts:148` with `Math.max(0, ...)` removed: SURVIVED (pass 351, fail 0), the same real gap as M3. **P-C** `csharp/Contexel/Trace.cs:134` with `Math.Max(0, ...)` removed: SURVIVED (312/312), EQUIVALENT in C# because `Enumerable.Skip` of a negative count behaves as `Skip(0)`.

Survivors: M3 (real gap, MAJOR), M13b (real gap, MINOR), O1 (real gap, MINOR), O7 (real gap, MINOR), M22 and M23 (by design: no repo test reads workflow YAML), O4 and O8 (equivalent).

Applied diffs:
~~~
M1:
contexel/trace.py: @@ -196 +196 @@
contexel/trace.py: -            lost = max(0, unidentified_out - unidentified_in)
contexel/trace.py: +            lost = max(0, unidentified_out)

M2:
contexel/trace.py: @@ -196 +196 @@
contexel/trace.py: -            lost = max(0, unidentified_out - unidentified_in)
contexel/trace.py: +            lost = max(0, unidentified_in)

M3:
contexel/trace.py: @@ -196 +196 @@
contexel/trace.py: -            lost = max(0, unidentified_out - unidentified_in)
contexel/trace.py: +            lost = unidentified_out - unidentified_in

M4:
contexel/trace.py: @@ -197 +197 @@
contexel/trace.py: -            dropped = unmatched[lost:]
contexel/trace.py: +            dropped = unmatched[:lost]

M5:
contexel/trace.py: @@ -197 +197 @@
contexel/trace.py: -            dropped = unmatched[lost:]
contexel/trace.py: +            dropped = unmatched

M6:
contexel/trace.py: @@ -173 +173 @@
contexel/trace.py: -                if isinstance(r, dict) and fid in r:
contexel/trace.py: +                if isinstance(r, dict) and r.get(fid):
contexel/trace.py: @@ -181 +181 @@
contexel/trace.py: -                if isinstance(r, dict) and fid in r:
contexel/trace.py: +                if isinstance(r, dict) and r.get(fid):

M7:
contexel/pipeline.py: @@ -58 +58 @@
contexel/pipeline.py: -        return "set{" + ",".join(sorted(_stable_repr(v) for v in value)) + "}"
contexel/pipeline.py: +        return "set{" + ",".join([_stable_repr(v) for v in value]) + "}"

M8:
contexel/pipeline.py: @@ -94 +94 @@
contexel/pipeline.py: -    bound = {k: _snapshot(v) for k, v in kwargs.items()}
contexel/pipeline.py: +    bound = dict(kwargs)

M9:
contexel/pipeline.py: @@ -120 +119,0 @@
contexel/pipeline.py: -    stages = list(stages)  # a later change to the caller's list is not ours

M10:
contexel/tokens.py: @@ -116 +116 @@
contexel/tokens.py: -        return len(enc.encode(text, disallowed_special=()))
contexel/tokens.py: +        return len(enc.encode(text))

M11:
contexel/tokens.py: @@ -119 +119 @@
contexel/tokens.py: -    count_tokens.__name__ = f"tiktoken:{model or encoding}"
contexel/tokens.py: +    count_tokens.__name__ = "<lambda>"

M12:
contexel/pipeline.py: @@ -143 +142,0 @@
contexel/pipeline.py: -    run.__contexel_desc__ = ("pipeline", (fingerprint,))  # type: ignore[attr-defined]

M13a:
contexel/pipeline.py: @@ -72 +72 @@
contexel/pipeline.py: -    if kind is list:
contexel/pipeline.py: +    if isinstance(value, list):
contexel/pipeline.py: @@ -74 +74 @@
contexel/pipeline.py: -    if kind is tuple:
contexel/pipeline.py: +    if isinstance(value, tuple):
contexel/pipeline.py: @@ -76 +76 @@
contexel/pipeline.py: -    if kind is dict:
contexel/pipeline.py: +    if isinstance(value, dict):
contexel/pipeline.py: @@ -78 +78 @@
contexel/pipeline.py: -    if kind is set:
contexel/pipeline.py: +    if isinstance(value, (set, frozenset)):

M13b:
contexel/pipeline.py: @@ -78 +78 @@
contexel/pipeline.py: -    if kind is set:
contexel/pipeline.py: +    if kind in (set, frozenset):

M14:
tools/check_versions.py: @@ -99,0 +100,2 @@
tools/check_versions.py: +        if loc.label == 'Python package (pyproject)':
tools/check_versions.py: +            continue

M15:
tools/check_versions.py: @@ -99,0 +100,2 @@
tools/check_versions.py: +        if loc.label == 'Python module':
tools/check_versions.py: +            continue

M16:
tools/check_versions.py: @@ -99,0 +100,2 @@
tools/check_versions.py: +        if loc.label == 'npm package':
tools/check_versions.py: +            continue

M17:
tools/check_versions.py: @@ -99,0 +100,2 @@
tools/check_versions.py: +        if loc.label == 'npm lockfile (root)':
tools/check_versions.py: +            continue

M18:
tools/check_versions.py: @@ -99,0 +100,2 @@
tools/check_versions.py: +        if loc.label == 'npm lockfile (package entry)':
tools/check_versions.py: +            continue

M19:
tools/check_versions.py: @@ -99,0 +100,2 @@
tools/check_versions.py: +        if loc.label == 'TypeScript constant':
tools/check_versions.py: +            continue

M20:
tools/check_versions.py: @@ -99,0 +100,2 @@
tools/check_versions.py: +        if loc.label == 'NuGet package (csproj)':
tools/check_versions.py: +            continue

M21:
tools/check_versions.py: @@ -122 +122 @@
tools/check_versions.py: -        return 2
tools/check_versions.py: +        return 1

M21b:
tools/check_versions.py: @@ -103 +103 @@
tools/check_versions.py: -        except (OSError, UnicodeDecodeError) as exc:
tools/check_versions.py: +        except OSError as exc:

M22:
.github/workflows/ci.yml: @@ -52,2 +51,0 @@
.github/workflows/ci.yml: -      - name: The seven version locations agree
.github/workflows/ci.yml: -        run: python tools/check_versions.py

M23:
.github/workflows/release.yml: @@ -44,2 +43,0 @@
.github/workflows/release.yml: -      - name: The seven version locations must agree
.github/workflows/release.yml: -        run: python tools/check_versions.py

T1:
ts/src/trace.ts: @@ -148 +148 @@
ts/src/trace.ts: -      const lost = Math.max(0, unidentifiedOut - unidentifiedIn);
ts/src/trace.ts: +      const lost = Math.max(0, unidentifiedOut);

T2:
ts/src/trace.ts: @@ -149 +149 @@
ts/src/trace.ts: -      dropped = unmatched.slice(lost);
ts/src/trace.ts: +      dropped = unmatched.slice(0, lost);

T3:
ts/src/pipeline.ts: @@ -40 +40 @@
ts/src/pipeline.ts: -  if (value instanceof Set) return "set{" + [...value].map(stableRepr).sort().join(",") + "}";
ts/src/pipeline.ts: +  if (value instanceof Set) return "set{" + [...value].map(stableRepr).join(",") + "}";

T4:
ts/src/pipeline.ts: @@ -58 +58 @@
ts/src/pipeline.ts: -  if (proto === Array.prototype) return (value as unknown[]).map(snapshot) as T;
ts/src/pipeline.ts: +  if (Array.isArray(value)) return (value as unknown[]).map(snapshot) as T;
ts/src/pipeline.ts: @@ -59 +59 @@
ts/src/pipeline.ts: -  if (proto === Set.prototype) return new Set(value as unknown as Set<unknown>) as T;
ts/src/pipeline.ts: +  if (value instanceof Set) return new Set(value as unknown as Set<unknown>) as T;

T5:
ts/src/pipeline.ts: @@ -65,6 +65 @@
ts/src/pipeline.ts: -      Object.defineProperty(copy, k, {
ts/src/pipeline.ts: -        value: snapshot(v),
ts/src/pipeline.ts: -        enumerable: true,
ts/src/pipeline.ts: -        writable: true,
ts/src/pipeline.ts: -        configurable: true,
ts/src/pipeline.ts: -      });
ts/src/pipeline.ts: +      copy[k] = snapshot(v);

T6:
ts/src/pipeline.ts: @@ -85 +85 @@
ts/src/pipeline.ts: -  const bound = snapshot(params);
ts/src/pipeline.ts: +  const bound = params;

C1:
csharp/Contexel/Trace.cs: @@ -134 +134 @@
csharp/Contexel/Trace.cs: -            int lost = Math.Max(0, unidentifiedOut - unidentifiedIn);
csharp/Contexel/Trace.cs: +            int lost = Math.Max(0, unidentifiedOut);

C2:
csharp/Contexel/Trace.cs: @@ -135 +135 @@
csharp/Contexel/Trace.cs: -            dropped.AddRange(unmatched.Skip(lost));
csharp/Contexel/Trace.cs: +            dropped.AddRange(unmatched.Take(lost));

C3:
csharp/Contexel/Trace.cs: @@ -109 +109 @@
csharp/Contexel/Trace.cs: -                if (r is not null && r.TryGetValue(fid, out var v))
csharp/Contexel/Trace.cs: +                if (r!.TryGetValue(fid, out var v))
csharp/Contexel/Trace.cs: @@ -120 +120 @@
csharp/Contexel/Trace.cs: -                if (r is not null && r.TryGetValue(fid, out var original))
csharp/Contexel/Trace.cs: +                if (r!.TryGetValue(fid, out var original))

C4:
csharp/Contexel/Pipeline.cs: @@ -99 +99 @@
csharp/Contexel/Pipeline.cs: -                .Select(StableRepr).OrderBy(s => s, StringComparer.Ordinal)) + "}";
csharp/Contexel/Pipeline.cs: +                .Select(StableRepr)) + "}";

C5:
csharp/Contexel/Pipeline.cs: @@ -68 +68 @@
csharp/Contexel/Pipeline.cs: -            if (s.Fn.Target is Pipeline inner)
csharp/Contexel/Pipeline.cs: +            if (s.Fn.Target is Pipeline inner && s.Name == "<NUL>never")

O1:
contexel/trace.py: @@ -166 +166 @@
contexel/trace.py: -                    return value
contexel/trace.py: +                    return str(value)

O2:
contexel/pipeline.py: @@ -58 +58 @@
contexel/pipeline.py: -        return "set{" + ",".join(sorted(_stable_repr(v) for v in value)) + "}"
contexel/pipeline.py: +        return "[" + ",".join(sorted(_stable_repr(v) for v in value)) + "]"

O3:
contexel/pipeline.py: @@ -79 +79 @@
contexel/pipeline.py: -        return set(value)  # elements are hashable, so already immutable
contexel/pipeline.py: +        return value

O4:
tools/check_versions.py: @@ -48 +48 @@
tools/check_versions.py: -    section = re.search(r"^\[project\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
tools/check_versions.py: +    section = re.search(r"^\[project\]$(.*?)(?=^\[|\Z)", text, re.M | re.S)

O5:
pyproject.toml: @@ -52,0 +53 @@
pyproject.toml: +exclude = ["contexel/py.typed"]

O6:
ts/src/pipeline.ts: @@ -103 +103 @@
ts/src/pipeline.ts: -  const stages = [...stageList]; // a later change to the caller's array is not ours
ts/src/pipeline.ts: +  const stages = stageList; // a later change to the caller's array is not ours

O7:
csharp/Contexel/Pipeline.cs: @@ -103 +103 @@
csharp/Contexel/Pipeline.cs: -            foreach (DictionaryEntry e in dict) copy[(string)e.Key] = Settle(e.Value);
csharp/Contexel/Pipeline.cs: +            foreach (DictionaryEntry e in dict) copy[(string)e.Key] = e.Value;

O8:
ts/test/runner.ts: @@ -157 +157 @@
ts/test/runner.ts: -      throw new Error(`unknown case kind ${c.stage}`);
ts/test/runner.ts: +      return undefined;
~~~
(The C5 sentinel string holds a NUL character, shown as <NUL>; the added condition can never be true, which is the point.)

## 4. Adversarial scenarios (real output)

### 4.1 Trace (Python 3.12, HEAD copy)
~~~
contexel from: copy
== timing (lost = n/10 id-less added; first n/10 of the n/2 unmatched absorbed)
n=10000  t=0.0070s dropped=4000 first=[2000, 2002, 2004]
n=100000 t=0.0739s dropped=40000 first=[20000, 20002, 20004]
ratio = 10.6
== odd records through every built-in stage under trace(id_field='id')
select          RAISED TypeError: argument of type 'NoneType' is not iterable
dedupe          RAISED AttributeError: 'NoneType' object has no attribute 'get'
rank            RAISED TypeError: argument of type 'NoneType' is not iterable
allowlist       RAISED AttributeError: 'NoneType' object has no attribute 'get'
quarantine      RAISED InputShapeError: quarantine: item 1 must be a mapping, got NoneType
rescore         RAISED AttributeError: 'NoneType' object has no attribute 'get'
truncate_field  RAISED AttributeError: 'NoneType' object has no attribute 'get'
trim_to_budget  OK out=7 dropped=[]
== mixed-type ids 1, 1.0, True, '1'
kept: [1.0] dropped_ids: [1.0, True, '1']
[1 keep,'1' drop] dropped_ids: ['1']
[1 drop, True keep] dropped_ids: [True] (Python 1 == True: same key)
== id-less input record + a stage that strips ids
select strip: out 3 dropped []
allowlist(drop B)+select: [['b'], []]
== M3 probe: a stage that drops an id-less record AND two identified records
dropped_ids: ['a', 'b'] (expected ['a', 'b'])
~~~
Timing: 10x the input took 7.3x the time on 3.12 (9.1x on 3.9: 0.0106 s to 0.0968 s): linear, not quadratic. The stage that adds n/10 unrelated id-less records absorbs the first n/10 real drops (4,000 of 5,000 reported): that is the documented AC28 approximation, not a defect.

The None-record failures come from the stages themselves and are identical with and without a trace; the trace itself copes with None, strings, ints, lists and unhashable ids:
~~~
select          untraced="TypeError: argument of type 'NoneType' is not iterable"               traced=SAME
dedupe          untraced="AttributeError: 'NoneType' object has no attribute 'get'"             traced=SAME
rank            untraced="TypeError: argument of type 'NoneType' is not iterable"               traced=SAME
allowlist       untraced="AttributeError: 'NoneType' object has no attribute 'get'"             traced=SAME
quarantine      untraced='InputShapeError: quarantine: item 1 must be a mapping, got NoneType'  traced=SAME
rescore         untraced="AttributeError: 'NoneType' object has no attribute 'get'"             traced=SAME
truncate_field  untraced="AttributeError: 'NoneType' object has no attribute 'get'"             traced=SAME
trim_to_budget  untraced='OK'                                                                   traced=SAME
passthrough_weird 8 -> 13 dropped []
drop_all 13 -> 0 dropped [1, [1, {'z': 2}], {'nested': [1]}, None, [1, {'z': 2}]]
~~~
Mixed-type ids: Python treats 1, 1.0 and True as one key (dict equality), so `[1 drop, 1.0 keep, True drop, '1' drop]` reports `[1.0, True, '1']` although 1.0 was kept and 1 was dropped: misattribution among Python-equal ids, inherent to the canon and not changed by this slice.

### 4.2 Fingerprints (Python)
~~~
PYTHONHASHSEED=0: c0abda5875be2d03 29e570d8007d20a9
PYTHONHASHSEED=1: c0abda5875be2d03 29e570d8007d20a9
PYTHONHASHSEED=2: c0abda5875be2d03 29e570d8007d20a9
PYTHONHASHSEED=99: c0abda5875be2d03 29e570d8007d20a9
--- HEAD
set {'b','a'} vs {'a','b'} equal: True
mixed-type set {1,'1',2.5,None,True?,(1,2)}: 56dee79d1b21ee70
set {1, True} collapses (Python: 1 == True): 1
nested frozenset in set: 9af5694dd23b51c9
nested frozensets order-insensitive: True
triple-nested fp(a): f6205040b5c60375
triple-nested fp(b) differs: True
triple-nested run: [{'a': 2}]
self-referencing list bound: RAISED RecursionError: maximum recursion depth exceeded
self-referencing dict bound: RAISED RecursionError: maximum recursion depth exceeded
plain no-set pipeline fp (AC29 unchanged): 1c2c20c9aa204c96
HEAD innermost-only change: fp(a)=dcd39ca455a092bd fp(b)=7c41ba9015a3076a differ=True
--- main (0f09d36)
set {'b','a'} vs {'a','b'} equal: True
mixed-type set {1,'1',2.5,None,True?,(1,2)}: 022d2fed118243ad
set {1, True} collapses (Python: 1 == True): 1
nested frozenset in set: 022d2fed118243ad
nested frozensets order-insensitive: True
triple-nested fp(a): be8fb4e8d27427d6
triple-nested fp(b) differs: True
triple-nested run: [{'a': 2}]
self-referencing list bound: RAISED RecursionError: maximum recursion depth exceeded
self-referencing dict bound: RAISED RecursionError: maximum recursion depth exceeded
plain no-set pipeline fp (AC29 unchanged): 1c2c20c9aa204c96
main innermost-only change: fp(a)=c1b41fb39472fd3d fp(b)=c1b41fb39472fd3d differ=False
~~~
The self-referencing list and dict raise RecursionError on HEAD and on main alike (unchanged). Main confirms the pre-slice defects: different sets collided (rendered by type name only) and a change only in the innermost of three nested pipelines did not change the fingerprint.

### 4.3 TypeScript (built dist of the HEAD copy)
~~~
Set insertion order ignored: true
Set contents differ: true
Set vs Array differ: true
triple-nested innermost-only change differs: true
bound array mutated later: fp unchanged true | behaviour unchanged: [{"k":"keep"}]
__proto__ own key kept; result: [{"k":"keep"}]
M3-probe case dropped_ids: ["a","b"] (expected ["a","b"])
[1 drop, true keep] dropped_ids (Python says [True]): [1]
~~~

### 4.4 check_versions against copies of the real tree (Python 3.12)
~~~
[real tree, CRLF (Windows checkout)] exit=0: check_versions: all 7 version locations say 0.1.17
[real tree, LF] exit=0: check_versions: all 7 version locations say 0.1.17
[pyproject.toml -> 0.1.99] exit=1: check_versions: the version locations disagree: |   0.1.99       pyproject.toml  (Python package (pyproject)) |   0.1.17       contexel/__init__.py  (Python module) |   0.1.17       ts/package.json  (npm package) |   0.1.17       ts/package-lock.json  (npm lockfile (root)) |   0.1.17       ts/package-lock.json  (npm lockfile (pa
[contexel/__init__.py -> 0.1.99] exit=1: check_versions: the version locations disagree: |   0.1.17       pyproject.toml  (Python package (pyproject)) |   0.1.99       contexel/__init__.py  (Python module) |   0.1.17       ts/package.json  (npm package) |   0.1.17       ts/package-lock.json  (npm lockfile (root)) |   0.1.17       ts/package-lock.json  (npm lockfile (pa
[ts/package.json -> 0.1.99] exit=1: check_versions: the version locations disagree: |   0.1.17       pyproject.toml  (Python package (pyproject)) |   0.1.17       contexel/__init__.py  (Python module) |   0.1.99       ts/package.json  (npm package) |   0.1.17       ts/package-lock.json  (npm lockfile (root)) |   0.1.17       ts/package-lock.json  (npm lockfile (pa
[ts/src/index.ts -> 0.1.99] exit=1: check_versions: the version locations disagree: |   0.1.17       pyproject.toml  (Python package (pyproject)) |   0.1.17       contexel/__init__.py  (Python module) |   0.1.17       ts/package.json  (npm package) |   0.1.17       ts/package-lock.json  (npm lockfile (root)) |   0.1.17       ts/package-lock.json  (npm lockfile (pa
[csharp/Contexel/Contexel.csproj -> 0.1.99] exit=1: check_versions: the version locations disagree: |   0.1.17       pyproject.toml  (Python package (pyproject)) |   0.1.17       contexel/__init__.py  (Python module) |   0.1.17       ts/package.json  (npm package) |   0.1.17       ts/package-lock.json  (npm lockfile (root)) |   0.1.17       ts/package-lock.json  (npm lockfile (pa
[lockfile ROOT version -> 0.1.99] exit=1: check_versions: the version locations disagree: |   0.1.17       pyproject.toml  (Python package (pyproject)) |   0.1.17       contexel/__init__.py  (Python module) |   0.1.17       ts/package.json  (npm package) |   0.1.99       ts/package-lock.json  (npm lockfile (root)) |   0.1.17       ts/package-lock.json  (npm lockfile (pa
[lockfile packages[''] version -> 0.1.99] exit=1: check_versions: the version locations disagree: |   0.1.17       pyproject.toml  (Python package (pyproject)) |   0.1.17       contexel/__init__.py  (Python module) |   0.1.17       ts/package.json  (npm package) |   0.1.17       ts/package-lock.json  (npm lockfile (root)) |   0.1.99       ts/package-lock.json  (npm lockfile (pa
[missing contexel/__init__.py] exit=2: check_versions: contexel/__init__.py (Python module): cannot read it (No such file or directory)
[missing ts/package-lock.json] exit=2: check_versions: ts/package-lock.json (npm lockfile (root)): cannot read it (No such file or directory)
[non-UTF-8 bytes appended to pyproject.toml] exit=2: check_versions: pyproject.toml (Python package (pyproject)): cannot read it ('utf-8' codec can't decode byte 0xff in position 2168: invalid start byte)
[non-UTF-8 bytes appended to csharp/Contexel/Contexel.csproj] exit=2: check_versions: csharp/Contexel/Contexel.csproj (NuGet package (csproj)): cannot read it ('utf-8' codec can't decode byte 0xff in position 1139: invalid start byte)
[UTF-8 BOM on pyproject.toml] exit=0: check_versions: all 7 version locations say 0.1.17
[UTF-8 BOM on contexel/__init__.py] exit=0: check_versions: all 7 version locations say 0.1.17
[UTF-8 BOM on ts/package.json] exit=2: check_versions: ts/package.json (npm package): no version in the JSON (JSONDecodeError('Unexpected UTF-8 BOM (decode using utf-8-sig): line 1 column 1 (char 0)'))
[UTF-8 BOM on ts/src/index.ts] exit=0: check_versions: all 7 version locations say 0.1.17
[UTF-8 BOM on csharp/Contexel/Contexel.csproj] exit=0: check_versions: all 7 version locations say 0.1.17
[UTF-8 BOM on ts/package-lock.json] exit=2: check_versions: ts/package-lock.json (npm lockfile (root)): no version in the JSON (JSONDecodeError('Unexpected UTF-8 BOM (decode using utf-8-sig): line 1 column 1 (char 0)'))
[pyproject with old-Mac CR-only endings] exit=0: check_versions: all 7 version locations say 0.1.17
[package.json version with leading space] exit=1: check_versions: the version locations disagree: |   0.1.17       pyproject.toml  (Python package (pyproject)) |   0.1.17       contexel/__init__.py  (Python module) |    0.1.17      ts/package.json  (npm package) |   0.1.17       ts/package-lock.json  (npm lockfile (root)) |   0.1.17       ts/package-lock.json  (npm lockfile (pa
~~~
Python 3.9.13:
~~~
[real tree, CRLF (Windows checkout)] exit=0: check_versions: all 7 version locations say 0.1.17
[real tree, LF] exit=0: check_versions: all 7 version locations say 0.1.17
[pyproject.toml -> 0.1.99] exit=1: (disagree list, as on 3.12)
[contexel/__init__.py -> 0.1.99] exit=1: (disagree list, as on 3.12)
[ts/package.json -> 0.1.99] exit=1: (disagree list, as on 3.12)
[ts/src/index.ts -> 0.1.99] exit=1: (disagree list, as on 3.12)
[csharp/Contexel/Contexel.csproj -> 0.1.99] exit=1: (disagree list, as on 3.12)
[lockfile ROOT version -> 0.1.99] exit=1: (disagree list, as on 3.12)
[lockfile packages[''] version -> 0.1.99] exit=1: (disagree list, as on 3.12)
[missing contexel/__init__.py] exit=2: check_versions: contexel/__init__.py (Python module): cannot read it (No such file or directory)
[missing ts/package-lock.json] exit=2: check_versions: ts/package-lock.json (npm lockfile (root)): cannot read it (No such file or directory)
[non-UTF-8 bytes appended to pyproject.toml] exit=2: check_versions: pyproject.toml (Python package (pyproject)): cannot read it ('utf-8' codec can't decode byte 0xff in position 2168: invalid start byte)
[non-UTF-8 bytes appended to csharp/Contexel/Contexel.csproj] exit=2: check_versions: csharp/Contexel/Contexel.csproj (NuGet package (csproj)): cannot read it ('utf-8' codec can't decode byte 0xff in position 1139: invalid start byte)
[UTF-8 BOM on pyproject.toml] exit=0: check_versions: all 7 version locations say 0.1.17
[UTF-8 BOM on contexel/__init__.py] exit=0: check_versions: all 7 version locations say 0.1.17
[UTF-8 BOM on ts/package.json] exit=2: check_versions: ts/package.json (npm package): no version in the JSON (JSONDecodeError('Unexpected UTF-8 BOM (decode using utf-8-sig): line 1 column 1 (char 0)'))
[UTF-8 BOM on ts/src/index.ts] exit=0: check_versions: all 7 version locations say 0.1.17
[UTF-8 BOM on csharp/Contexel/Contexel.csproj] exit=0: check_versions: all 7 version locations say 0.1.17
[UTF-8 BOM on ts/package-lock.json] exit=2: check_versions: ts/package-lock.json (npm lockfile (root)): no version in the JSON (JSONDecodeError('Unexpected UTF-8 BOM (decode using utf-8-sig): line 1 column 1 (char 0)'))
[pyproject with old-Mac CR-only endings] exit=0: check_versions: all 7 version locations say 0.1.17
[package.json version with leading space] exit=1: (disagree list, as on 3.12)
~~~
CRLF: the real tree as checked out on Windows (CRLF) and as LF both pass; the unit test covers CRLF too. While building the BOM cases my first script truncated each file before reading it, so those files were EMPTY: every empty location gave exit 2 naming the file, no traceback (a bonus empty-file result; the corrected BOM results are the ones above).

### 4.5 Vectors
~~~
$ PYTHONPATH=. python parity/generate_vectors.py      (run twice in one copy)
wrote <tmp>/vec/parity/vectors.json (33515 bytes)
wrote <tmp>/vec/parity/vectors.json (33515 bytes)
cmp vectors.blob.json vectors.run1.json -> run1 == committed blob
cmp vectors.run1.json vectors.run2.json -> run1 == run2
77 cases, 7 of kind trace_dropped_ids
~~~
On this Windows host core.autocrlf=true gives the archive copy CRLF, so the comparison is with `git show HEAD:parity/vectors.json`; the generator writes LF and equals the committed blob byte for byte.

### 4.6 Lint, types, wheel
~~~
$ python -m ruff check contexel --no-cache
All checks passed!                                    (exit 0, ruff 0.15.15)
$ python -m mypy contexel --python-version 3.10 --no-incremental --cache-dir <tmp>/mypycache
Success: no issues found in 8 source files            (exit 0, mypy 2.3.0; same with the pyproject [tool.mypy] config alone)
$ hatchling.build.build_wheel(<tmp>/wheel)
wheel: contexel-0.1.17-py3-none-any.whl
entries: 13
py.typed: True
outside contexel/ and dist-info: []
~~~
A first mypy attempt with `--cache-dir=NUL` crashed inside mypy; that was my flag, not the package.

## 5. Defects and gaps

No defect in the shipped behaviour. Test gaps and minor findings:

| # | Severity | Kind | Reproduction | Needed |
|---|----------|------|--------------|--------|
| 1 | MAJOR | test gap on the AC28 core invariant | In a fresh copy change `contexel/trace.py:196` to `lost = unidentified_out - unidentified_in` (or drop `Math.max` at `ts/src/trace.ts:148`): Python 531/531 and TS 351/351 still pass. Then `with trace(id_field="id"): allowlist([{"t":"x"},{"id":"a","t":"x"},{"id":"b","t":"x"},{"id":"c","t":"y"}], "t", ["y"])` reports `['b']` instead of `['a','b']` | one Python test plus one `trace_dropped_ids` vector of this shape (the vector covers TS and C# through their runners) |
| 2 | MINOR | test gap | O7: `csharp/Contexel/Pipeline.cs:103` without `Settle` on dictionary values; 312/312 pass; the probe test (a set inside a dictionary parameter, two insertion orders) fails | a C# test that a set nested in a dictionary is insertion-order independent |
| 3 | MINOR | test gap | M13b: `contexel/pipeline.py:78` as `kind in (set, frozenset)`; 531/531 pass; the stage then gets a mutable, unhashable set instead of the caller's frozenset | assert a bound frozenset is passed through by identity |
| 4 | MINOR | test gap | O1: `contexel/trace.py:166` returns `str(value)`; 531/531 pass | a trace test with ids 1 and "1" |
| 5 | MINOR | robustness, fails closed | Prefix ts/package.json or ts/package-lock.json with a UTF-8 BOM: exit 2, `JSONDecodeError('Unexpected UTF-8 BOM ...')`, file named. A BOM on the other five files is accepted | optional: read with `utf-8-sig`; acceptable as is |
| 6 | MINOR | CI wiring unguarded | M22/M23: deleting the check_versions step from ci.yml or release.yml is invisible to every repo test | optional: a test asserting both workflows run `tools/check_versions.py` |
| 7 | MINOR, pre-existing, outside this slice | parity | ids `1` (dropped) and `true` (kept): Python reports `[True]`, TypeScript reports `[1]` (the TS `idKey` keeps booleans and numbers apart; C# uses PyEqKey like Python). `idKey` is unchanged by this slice | log for a later slice |

## 6. Not verified

- Three-OS CI (Linux, macOS, Windows runners): only Windows 11 locally.
- Python 3.10 (no interpreter here). Python 3.9 without pytest: only compilation, the zero-fixture tests through a stand-in, and the scenario scripts. On 3.11 tiktoken and hatchling are absent (2 tests skipped).
- Node 18 and 20 (only Node 24 here).
- pip-audit or any dependency audit (no network).
- The first real run of the new `hygiene` CI job (pinned actions, `pip install -e .[lint]`, `pip wheel`) and of the release.yml gate.
- AC34 documentation completeness beyond what the doc-example tests execute.
