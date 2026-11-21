> Filed 2026-11-20 from the Slice 3 review workspace for branch `feat/hardening-s3-audit-release` (head `c8bc7f3` after the fix wave; commit hashes in this document are those of the branch after one subject was reworded). Sanitised: no user name, home or temporary path, e-mail address or agent identifier. The single fix wave that closed the G4, G5 QA and G5 Security findings (the implementer's report).

# Fix wave report: Slice 3 whole-branch gate findings

Branch feat/hardening-s3-audit-release, from 5f4e444. Four commits, not pushed, no version bump, no Co-Authored-By trailer.

| Group | Commit | Subject |
|-------|--------|---------|
| A | bd7fc52 | test: pin the trace clamp, frozenset identity and id types |
| B | 0170fd8 | fix(tools): exit 2 when a version file nests too deeply |
| C | c4679e5 | ci: restrict the default token of ci.yml to read-only contents |
| D | c8bc7f3 | docs: qualify the fingerprint claims and list the audit limits |

Status: DONE_WITH_CONCERNS. A6 was not done because its premise is false (see A6).

## How the mutation runs were done
I made a snapshot of HEAD plus the uncommitted Group A changes with `git stash create`. This creates a commit object and does not touch the working tree or the stash list. I ran `git archive` on it into a throwaway directory under my session scratchpad, copied that tree once per mutant and applied the mutation to the copy only. The TypeScript copies used a directory junction to the repo's `ts/node_modules`. The C# copy was restored offline from the local NuGet global-packages folder. <repo> was never mutated. I also archived plain `HEAD` (5f4e444) and applied the three Python mutants there, to confirm that each one survives the old suite: 531 passed for each.

## Group A (bd7fc52)
- **A1 trace clamp.** Added `test_a_dropped_idless_record_never_absorbs_an_identified_drop` to tests/test_audit_truth.py, and the vector case `trace_dropped_ids/a_dropped_idless_record_never_absorbs_an_identified_drop` to parity/parity_cases.py. It uses the brief's scenario and the same stage vocabulary as the other cases.
  - Python mutant (`lost = unidentified_out - unidentified_in`): 3 failed, 533 passed. The new test fails with `assert ['b'] == ['a', 'b']`, plus the two parity-case tests. At plain HEAD the same mutant gave 531 passed (it survives).
  - TypeScript mutant (no `Math.max(0, ...)` in ts/src/trace.ts): 354 tests, 1 fail. The failing test is `case trace_dropped_ids/a_dropped_idless_...`: actual `[ [ 'b' ] ]`, expected `[ [ 'a', 'b' ] ]`. The replayed vector kills it.
  - C# passes the vector on the real code. No mutant was run there, as the brief said.
- **A2 frozenset identity.** Added `test_a_bound_frozenset_is_passed_as_the_same_object` after the existing "not copied" test. Mutant (a frozenset converted to a set in `_snapshot`): 1 failed, 535 passed, with `assert {'a', 'b'} is frozenset({'a', 'b'})`. Survives at HEAD: 531 passed.
- **A3 ids 1 vs "1".** Added `test_ids_1_and_the_string_1_are_different_ids`. The input is `[{"id": "1", drop}, {"id": 1, keep}]`. This order matters: with the survivor first, the str() mutant still gives the right answer. Also added the second vector case `trace_dropped_ids/the_integer_1_and_the_string_1_are_different_ids`.
  - Python mutant (`id_key` returns `str(value)`): 3 failed, 533 passed, with `assert [1] == ['1']`. Survives at HEAD: 531 passed.
  - All three languages agree on the real code. TypeScript Map keys 1 and "1" are distinct. C# keys them `num:1` and `str:1`. Both replay the vector green.
- **Vectors.** Regenerated twice with `PYTHONPATH=. python parity/generate_vectors.py`: byte-identical, `case_count` 77 -> 79.
  - **Count pins:** none of the test suites hard-codes 77. tests/test_parity_cases.py:21, ts/test/cases.test.ts:22 and csharp/Contexel.Tests/CaseTests.cs:228 all compare against `_meta.case_count`, so no test needed a change.
  - The one literal was CHANGELOG.md "(77 cases in all)". I changed it to 79 in this commit.
- **A4 C# set in a dictionary parameter.** Added `ASetInADictionaryParameterIgnoresInsertionOrder` to csharp/Contexel.Tests/FingerprintTests.cs, after the set tests. Mutant (`copy[(string)e.Key] = e.Value;`, so no Settle on dictionary values): 1 failed, 314 passed, with expected `963d23a0f1e77523` and actual `a96af6b821c0554a`.
- **A5.** tests/test_check_versions.py now asserts `out == "check_versions: all 7 version locations say 1.2.3" + NL`. Mutant (the printed count is `len(found) + 10`): the new assertion fails ("all 17 ..."). The old `"7" in out` assertion passes against the same mutant.
- **A6. NOT DONE: the brief's premise is false.** The C# library does not hash `GetType().Name` for an opaque object.
  - Tokens.PythonJson falls back to `Convert.ToString(value)` (csharp/Contexel/Tokens.cs, the `default:` branch of WriteJson), which calls `ToString()`.
  - So `Opaque.ToString() => "Opaque"` is what produces the golden value. Removing it changed `opaque_object` from `704c1b356f69617b` to `3a32ba7d49234db8`: 1 failed.
  - I reverted the removal. The file is unchanged apart from A4, and no expected hash was edited.
  - Suggestion for the human or controller: add a one-line comment saying the override is load-bearing (the library renders an opaque object with Convert.ToString). One more fact: the default ToString is the full type name, unlike Python's bare `type(value).__name__`.
- **A7.** In ts/test/runner.ts, a `trace_dropped_ids` case whose `id_field` is not a non-empty string now throws `Error("case <id>: trace_dropped_ids needs a non-empty string id_field")`. Added a test to ts/test/runner.test.ts covering a missing id_field, `""` and `1`. Against the old runner (mutant) the test fails with "Missing expected exception", because `[[]]` passed vacuously.
- Totals after A: Python 536, TypeScript 354, C# 315.

## Group B (0170fd8)
- **B1.** tools/check_versions.py `_json_version` now catches `RecursionError` and raises `Unreadable("the JSON is nested too deeply to read")`. `collect` prefixes that with the file and the label.
  - New test `test_json_nested_too_deeply_fails_loudly_naming_it` writes `"[" * 100000 + "]" * 100000` to ts/package.json and runs the script as CI does. It asserts exit 2, `ts/package.json (npm package)` in stderr, "nested too deeply", and no Traceback.
  - RED before the fix: exit 1 with a traceback ending `RecursionError: maximum recursion depth exceeded while decoding a JSON array from a unicode string`.
  - GREEN after: 23 passed in test_check_versions.py.
  - Real output: `check_versions: ts/package.json (npm package): the JSON is nested too deeply to read`, exit 2. It behaves the same under Python 3.9 (`py -3.9`, script run directly; pytest is not installed for 3.9).

## Group C (c4679e5)
- **C1.** Added a top-level `permissions: contents: read` block to ci.yml, right after `on:`, in the same style as release.yml (lines 25-26). Nothing else changed.
  - PyYAML was already installed and parses the file: `{'contents': 'read'}`, jobs cs-parity, hygiene, test, ts-parity.
  - Every job uses only actions/checkout, setup-python, setup-node (the npm cache uses the Actions cache service, not GITHUB_TOKEN scopes) and setup-dotnet, plus `run` steps. No job needs more than contents: read.

## Group D (c8bc7f3). Docs, comments and docstrings only
`git diff HEAD~1 -- '*.py' '*.ts' '*.cs'` contains only docstring and comment lines (pipeline.py docstring, check_versions.py docstring, pipeline.ts comments).
- **D1.**
  - README now says "a nested pipeline used directly as a stage".
  - CHANGELOG Behavior change 9 now says: a pipeline that IS the stage, used directly in a stage list; one wrapped by `stage(inner)` or `stage(inner, {})`, or passed as an argument, still hashes as `run`. A Known limitations bullet says the same.
  - contexel/pipeline.py docstring updated the same way.
  - Before writing, I checked in both Python and TypeScript that a direct pipeline differs, while `stage(inner)` / `stage(inner, {})` / a keyword parameter give the same fingerprint.
  - Beyond the brief, flagged: the same "used directly as a stage" wording in the ts/src/pipeline.ts module header comment, ADR-008's TypeScript bullet and site/stages.html, for consistency.
- **D2.** site/stages.html now reads: "For the exact containers it copies, the fingerprint cannot go stale: stage() keeps a private copy of the exact lists, tuples, dicts and sets bound to it (not of a container subclass or a custom object, nor of the elements of a TypeScript Set; C# copies no bound parameter)." `python tools/site_check.py`: `checked 6 pages under site/ -> OK`.
- **D3.** "on every push to main and every pull request" in CHANGELOG.md, in the ci.yml comment (comment reflowed, no trigger change) and in the check_versions.py docstring.
- **D4.**
  - ADR-008 Trace bullet: "identical in all three, up to id-key equality". It adds the equality differences, and that 1 and "1" are distinct in all three.
  - CHANGELOG Behavior change 8: "identical up to id-key equality".
  - The CHANGELOG bullet that names 1 and true now adds 0 and false.
  - The brief's CHANGELOG "~line 334 identical in all three" does not exist verbatim. The matching text was BC8's "All three languages".
- **D5.** The ts/src/pipeline.ts stage() doc comment now says "exact array, plain object or Set" and "(a Set's elements are not copied)".
- **D6.** "(MIT, never a runtime dependency)". I dropped the now-redundant "no runtime dependency".
- **D7.** BC8 clause added about the C# null record. I checked it against main's Trace.cs, which called `r.TryGetValue` without a null check.
- **D8.** New Known limitations bullets: (i) TypeScript copy scope (typed arrays, Buffer, other realm, non-plain); (ii) crafted ids and equality; (iii) quadratic colliding hashes, with the figures from the security report (256.8 ms for 4000 ids, 1034.9 ms for 8000); (iv) floating lint ranges. ADR-008 TypeScript bullet: typed arrays, Buffer and other-realm objects are not copied.
- **D9.** Known limitations bullet: no test guards the CI workflow steps; the first CI run and code review are the guard.

## Final checks (at c8bc7f3)
- Python: 537 passed (`PYTHONPATH=. python -m pytest -q -p no:cacheprovider --ignore-glob='tests/test_doctrine_*'`). That is 531 + 3 audit tests + 2 vector-replay cases + 1 check_versions test.
- TypeScript: `npm run build` clean; tests 354, pass 354, fail 0. That is 351 + 2 vectors + 1 runner test.
- C#: 315 passed, 0 failed; `dotnet build --no-incremental` gave 0 Warning(s), 0 Error(s). That is 312 + 2 vectors + 1 A4 test.
- Vectors: 79 cases (`_meta.case_count` 79). Regenerated twice, byte-identical, and equal to the committed blob (`git cat-file blob HEAD:parity/vectors.json`).
- `ruff check contexel --no-cache`: All checks passed. `mypy contexel --python-version 3.10 --no-incremental`: Success, 8 source files.
- `python tools/check_versions.py`: all 7 version locations say 0.1.17. Site check: OK.
- `git status --short` is clean. The privacy grep of `git diff main..HEAD` printed nothing. The longest subject in main..HEAD is 70 characters. Co-Authored-By count is 0.
- Line endings: every edited file keeps its working-copy endings. My `git checkout --` of FingerprintTests.cs had rewritten it as CRLF; I restored it to LF before committing. Committed content was not affected, because the index is LF either way.

## Concerns
1. A6 is not done: the override is load-bearing, and the G4 #13 "dead override" premise is wrong. This needs a decision: leave it, or add an explanatory comment.
2. I fixed the same nested-pipeline wording in four places beyond the brief's list: the TypeScript module header, ADR-008's TypeScript bullet, the site and the ci.yml comment reflow. All are docs or comments only.
