Filed 2026-11-26 from the Slice 7 execution workspace for branch `feat/hardening-s7-differential-fuzz`. Sanitised: no user name, home or temporary path, e-mail address or agent identifier.

# QA report (G5): Slice 7, differential fuzz

**QA Engineer** (fresh context, G5) · **Date:** 2026-11-26
**Build under test:** `a1877f4db2e7d30a578dfbd31f57c219314e19bf` (branch `feat/hardening-s7-differential-fuzz`), checked out detached in a scratch worktree, called `<wt>` below. `git rev-parse HEAD` = a1877f4db2e7d30a578dfbd31f57c219314e19bf; `git status -sb` = `## HEAD (no branch)`, clean.
**Toolchain:** Python 3.12.7, Node v24.18.0, .NET SDK 8.0.403. Python always run as `PYTHONPATH=<wt> python` (`contexel.__file__` resolves to `<wt>/contexel/__init__.py`). No network access was used.

**QA verdict: PASS.** All six acceptance criteria pass, with evidence below. Ten mutants were run: 8 caught, 1 caught but slow to report, 1 survived (an informational gap). One Low test-ergonomics defect, one Low repo-hygiene defect and several informational notes. None blocks G5.

---

## Acceptance criteria verification

| # | Criterion | How executed | Evidence (real output, trimmed) | Pass |
|---|-----------|--------------|------------------------|------|
| 1 | Seeded corpus exists, is deterministic, has 20000 cases at seed 20261126, `_meta` agrees | generated 4 times (plain, again, `PYTHONHASHSEED=0`, `=1`); `cmp`; an independent checker script recomputed every `_meta` field; `--show` compared with corpus cases 0, 5000, 19999 | see 1 below | PASS |
| 2 | Both ports replay with zero divergences; pass/skip when unset | `npm test` and `dotnet test`, variable set and unset | TS 684/684 pass (set); 681 pass + 1 skipped (unset). C# 623 passed (set and unset) | PASS |
| 3 | Fails closed (CI and unset, missing, truncated, empty, dup id, case_count, no error cases) | 7 bad inputs x 2 ports | every scenario fails in both ports (table in 3) | PASS |
| 4 | Runtime under 60 s each | `time` | generator 9.3 s; TS `npm test` total 7.4 s (fuzz test 2.7 s); C# `dotnet test` total 20.2 s including the build (fuzz Facts about 11 s) | PASS |
| 5 | Three shared suffix cases run in TS and C#; vectors regenerate with no diff | TS log, C# filtered run, `generate_vectors.py` + `git diff --ignore-cr-at-eol --exit-code` | all 3 pass in both ports; diff exit=0 | PASS |
| 6 | Python suite + ruff/mypy/tools | as specified | 1085 passed, 3 skipped (dataset cache absent: the allowed alternative); all tools OK | PASS |

### 1. Corpus determinism and metadata
```
$ time (PYTHONPATH=. python parity/generate_fuzz.py --out parity/fuzz-corpus.json)
wrote 20000 cases (seed 20261126) to parity/fuzz-corpus.json; 2209 error cases, 3115 strict, 24 redrawn
real	0m9.259s
$ sha256sum parity/fuzz-corpus.json parity/qa-fz-*.json      # again, PYTHONHASHSEED=0, PYTHONHASHSEED=1
d7554a374b598fbc71d6ee81be7165e5e4cd15ce53ebaa4e5262bdf424a57413 *parity/fuzz-corpus.json
d7554a374b598fbc71d6ee81be7165e5e4cd15ce53ebaa4e5262bdf424a57413 *parity/qa-fz-b.json
d7554a374b598fbc71d6ee81be7165e5e4cd15ce53ebaa4e5262bdf424a57413 *parity/qa-fz-h0.json
d7554a374b598fbc71d6ee81be7165e5e4cd15ce53ebaa4e5262bdf424a57413 *parity/qa-fz-h1.json
IDENTICAL                                                    # cmp of all three against the first
size: 36739827 bytes
```
Independent metadata check (my own script, recomputing from `cases`):
```
{'format': 1, 'seed': 20261126, 'case_count': 20000, 'strict_cases': 3115}
redrawn {'expect: integer-valued float 0.0': 17, 'intermediate: integer-valued float 0.0': 7}
len(cases) 20000 == case_count True
kind_counts agree True
error_codes agree True errors 2209
strict agree True
ids unique True
ids match index True            # id == fuzz/<seed>/<%05d index>/<stage> for every case
each has exactly one of expect/expect_error True
kinds {'allowlist': 1108, 'as_records': 1093, 'dedupe': 1151, 'join': 1199, 'merge': 1155, 'pipeline': 1659,
 'quarantine': 1114, 'rank': 1164, 'rescore': 1112, 'select': 1134, 'shaped': 539, 'split': 1199, 'stem': 1181,
 'text_pipeline': 1183, 'trace_dropped_ids': 1109, 'trace_report': 573, 'trim_to_budget': 1169, 'truncate_field': 1158}
codes {'config.contradictory': 71, 'config.empty': 76, 'config.invalid_pattern': 61, 'config.invalid_value': 925,
 'input.field_conflict': 73, 'input.not_mapping': 1003}
```
`--show` reproduces the stored case exactly: `0 fuzz/20261126/00000/quarantine True`, `5000 fuzz/20261126/05000/join True`, `19999 fuzz/20261126/19999/quarantine True`.

### 2. Replays
```
# TS, CONTEXEL_FUZZ_CASES=parity/fuzz-corpus.json npm test   (cwd ts/, CI unset)
✔ the fuzz corpus is present and complete (11.2215ms)
✔ every fuzz case matches the Python canon (seed 20261126) (2661.6354ms)
✔ the replay can fail: a corrupted expectation is refused (118.3636ms)
ℹ tests 684  ℹ pass 684  ℹ fail 0  ℹ skipped 0
# TS, variable and CI unset
﹣ differential fuzz replay (1.1585ms) # CONTEXEL_FUZZ_CASES is not set
ℹ tests 682  ℹ pass 681  ℹ fail 0  ℹ skipped 1
# C#, variable set
Passed!  - Failed:     0, Passed:   623, Skipped:     0, Total:   623, Duration: 16 s
  Passed Contexel.Tests.FuzzTests.FuzzCorpusIsPresentAndComplete [3 s]
  Passed Contexel.Tests.FuzzTests.EveryFuzzCaseMatchesPython [6 s]
  Passed Contexel.Tests.FuzzTests.TheReplayCanFailACorruptedExpectationIsRefused [2 s]
# C#, variable and CI unset
Passed!  - Failed:     0, Passed:   623, Skipped:     0, Total:   623, Duration: 7 s
```
Final regression on the clean tree after all mutants (rebuilt): TS `ℹ tests 684 ℹ pass 684 ℹ fail 0`; C# `Passed! - Failed: 0, Passed: 623`.

### 3. Fail closed
CI and unset:
```
# TS: CI=true, variable unset -> exit=1
✖ the fuzz corpus is configured in CI (1.9801ms)
  AssertionError [ERR_ASSERTION]: CONTEXEL_FUZZ_CASES is not set: generate the corpus and point the variable at it
# C#: CI=true, variable unset -> exit=1
  Failed Contexel.Tests.FuzzTests.FuzzCorpusIsPresentAndComplete [5 ms]
   CONTEXEL_FUZZ_CASES is not set: generate the corpus and point the variable at it
  Failed Contexel.Tests.FuzzTests.EveryFuzzCaseMatchesPython [< 1 ms]   (same message)
  Failed Contexel.Tests.FuzzTests.TheReplayCanFailACorruptedExpectationIsRefused [< 1 ms]   (same message)
Failed!  - Failed:     3, Passed:   620, Skipped:     0, Total:   623
```
Bad corpora: scratch copies `parity/qa-*.json`, removed afterwards. "dup id" = case 1 given case 0's id, count unchanged. "no error" = all 2209 `expect_error` cases removed, with `case_count` and `kind_counts` rewritten to match, so that only the error-case guard can trip. "empty" was tried with `_meta` unchanged and with `_meta` made consistent.

| Scenario | TS (`node --test dist-test/test/fuzz.test.js`) | C# (`--filter FuzzTests`) |
|---|---|---|
| nonexistent path | exit 1: file-level `✖ dist-test\test\fuzz.test.js`, `Error: ENOENT: no such file or directory, open '<wt>\parity\qa-missing-nonexistent.json'` | exit 1: all 3 Facts fail, `System.IO.FileNotFoundException : Could not find file '<wt>\parity\qa-missing-nonexistent.json'` |
| truncated JSON (first half of the bytes) | exit 1: file-level, `SyntaxError: Unterminated string in JSON at position 18369913` | exit 1: all 3 fail, `System.Text.Json.JsonReaderException : Expected end of string, but instead reached end of data. ... BytePositionInLine: 18369913.` |
| empty `cases` (meta unchanged / consistent) | exit 1: `✖ the fuzz corpus is present and complete` (`only 0 cases (a replay must never pass vacuously)`) and `✖ the replay can fail` (`The expression evaluated to a falsy value`); `every fuzz case` passes vacuously | exit 1: `Failed FuzzCorpusIsPresentAndComplete`, `only 0 cases (a replay must never pass vacuously)`; the other 2 Facts pass vacuously (Failed: 1, Passed: 2) |
| duplicated id | exit 1: `✖ the fuzz corpus is present and complete`, `duplicate case ids` | exit 1: `Failed FuzzCorpusIsPresentAndComplete`, `Assert.Equal() Failure: Values differ Expected: 20000 Actual: 19999` |
| `case_count` + 1 | exit 1: `case_count disagrees with the cases array` | exit 1: `Assert.Equal() Failure: Values differ Expected: 20001 Actual: 20000` |
| all `expect_error` removed | exit 1: `no error case in the corpus` | exit 1: `Assert.Contains() Failure: Filter not matched in collection` |

### 4. Runtime
- Generator: `real 0m9.259s` (20000 cases); seed 7 / 3000 cases: `real 0m1.657s`.
- TS: whole `npm test` (tsc + 684 tests) `real 0m7.427s`; the fuzz test itself `2661.6354ms`.
- C#: whole `dotnet test` with build `real 0m20.178s`; FuzzTests alone `Total time: 13.2804 Seconds` (Complete 3 s, Every 6 s, Corrupted 2 s; each Fact parses the 37 MB corpus again).

### 5. Shared suffix vectors and vectors.json
```
# TS (npm test log)
✔ case truncate_field/custom_suffix_is_counted_before_the_cut (0.1572ms)
✔ case truncate_field/empty_suffix_leaves_the_whole_budget (0.1192ms)
✔ case truncate_field/astral_suffix_is_one_code_point (0.1061ms)
# C# (--filter CaseTests, normal verbosity)
  Passed Contexel.Tests.CaseTests.CaseMatchesPython(id: "truncate_field/custom_suffix_is_counted_before_the"···)
  Passed Contexel.Tests.CaseTests.CaseMatchesPython(id: "truncate_field/astral_suffix_is_one_code_point")
  Passed Contexel.Tests.CaseTests.CaseMatchesPython(id: "truncate_field/empty_suffix_leaves_the_whole_budge"···)
Total tests: 178  Passed: 178
$ PYTHONPATH=. python parity/generate_vectors.py
wrote <wt>\parity\vectors.json (69346 bytes)
$ git diff --ignore-cr-at-eol --exit-code parity/vectors.json ; echo $?
0
```
(`git status` then showed ` M parity/vectors.json` from LF/CRLF only: `git diff --ignore-all-space --stat` was empty. Restored with `git checkout`.)

### 6. Python suite and tools
```
$ PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
1085 passed, 3 skipped in 66.95s (0:01:06)
SKIPPED [1] tests\test_benchmarks_competitors.py:70: the dataset cache is not downloaded (CI never downloads it)
SKIPPED [1] tests\test_benchmarks_dataset.py:99: the dataset cache is not downloaded (CI never downloads it)
SKIPPED [1] tests\test_benchmarks_integrity.py:530: symbolic links cannot be created here
$ python -m pytest -q tests/test_fuzz_generator.py          -> 8 passed in 3.62s
$ python -m ruff check contexel                            -> All checks passed!
$ python -m mypy                                           -> Success: no issues found in 10 source files
$ python tools/check_versions.py                           -> check_versions: all 7 version locations say 0.1.17
$ python tools/site_check.py                               -> checked 6 pages under site/ -> OK
$ python tools/check_benchmark_numbers.py                  -> benchmark numbers: README, PyPI README and site agree with the generated results
```

---

## Mutation testing

Every mutant was applied to the source, run, and restored with `git checkout -- <file>`, and `git status --porcelain` was clean afterwards (apart from my scratch `parity/qa-*.json`, removed at the end). **A process error I made, and how I handled it:** my first M3 run used binaries still compiled from the M1 (TS `dist-test`) and M2 (C# `--no-build`) mutants, and reported 113 and 756 divergences. I rebuilt both from clean sources (`tsc -p tsconfig.test.json`, `dotnet build`), confirmed green (TS fuzz 3/3, C# 623/623), and reran M3. Every result below comes from a build that matches its stated source. All probes in this report ran before M1 or after a rebuild.

| # | File | Exact change | Command | Result | Restored |
|---|------|--------------|---------|--------|----------|
| M1-TS | `ts/src/stages.ts:531` | `Math.max(1, maxTokens - tokens.count(...))` -> `Math.max(0, ...)` | `CONTEXEL_FUZZ_CASES=parity/fuzz-corpus.json npm test` | **CAUGHT** by the fuzz only: `ℹ pass 683 ℹ fail 1`; `✖ every fuzz case matches the Python canon`; `112 of 20000 fuzz cases diverge from the canon`; `Reproduce one: python parity/generate_fuzz.py --seed 20261126 --show 294` (a pipeline rescore -> rank -> truncate_field max_tokens 1). Shared vectors stayed green. | yes |
| M1-C# | `csharp/Contexel/Stages.cs:513` | `Math.Max(1, maxTokens - ...)` -> `Math.Max(0, ...)` | `CONTEXEL_FUZZ_CASES=... dotnet test ...` | **CAUGHT** by the fuzz only: `Failed EveryFuzzCaseMatchesPython`, `112 of 20000 fuzz cases diverge`, `--show 294`; `Failed: 1, Passed: 622` | yes |
| M2 | `csharp/Contexel.Tests/CaseTests.cs` | removed `"suffix"` from the truncate_field allowed-args list, and `suffix: Str(a, "suffix", "…")` from the call | `dotnet test` with corpus | **CAUGHT**: the 3 shared suffix cases fail (`custom_suffix_is_counted_before_the…`, `astral_suffix_is_one_code_point`, `empty_suffix_leaves_the_whole_budge…`), and `EveryFuzzCaseMatchesPython` fails with `755 of 20000`, `--show 144`; `Failed: 4, Passed: 619` | yes |
| M3 | copy of the corpus (`parity/qa-m3.json`) | case 5000 (`fuzz/20261126/05000/join`): first character of `expect` `a` -> `Z` | TS and C# fuzz replays | **CAUGHT** in both: `1 of 20000 fuzz cases diverge from the canon. First 1:` / `fuzz/20261126/05000/join` / `Reproduce one: python parity/generate_fuzz.py --seed 20261126 --show 5000`. TS shows the actual `'a\x85b\r\n' +` against the expected `'Z\x85b\r\n' +`; C# shows expected/actual strings | n/a (copy deleted) |
| M4 | `parity/generate_fuzz.py` `make_case` | `if reason is None:` -> `if True:` (accept the first draw) | `pytest -q tests/test_fuzz_generator.py` | **CAUGHT** (1 of 8): `FAILED test_a_redraw_is_counted_and_a_hopeless_case_is_an_error` (`assert {} == {'input: integer-valued float 1.0': 2}`). Extra: a 20000 corpus built by this mutant (`0 redrawn`) diverges in TS (`1 of 20000 ... --show 2389`) and passes in C#, which confirms the TS-only integer-valued-float margin that the redraw protects | yes |
| M5a | `parity/generate_fuzz.py` `Gen.__init__` | `random.Random(seed).random` -> `random.random` (global RNG) | `pytest tests/test_fuzz_generator.py` | **CAUGHT** (`--assert=plain`: 3 failed: `test_fuzz_corpus_is_deterministic_and_inside_the_envelope`, `test_the_generator_and_the_first_cases_are_pinned`, `test_a_case_depends_on_its_seed_and_index_alone`). **With default assertion rewriting the run did not finish in over 5 minutes** (defect D1) | yes |
| M5b | `parity/generate_fuzz.py` `Gen.sample` | `pool = list(seq)` -> `list(set(seq)) if all strings else list(seq)` (hash-order iteration) | same, 3 runs (random hash seed twice, `PYTHONHASHSEED=0`) | **CAUGHT** every time: `FAILED ..._deterministic_and_inside_the_envelope`, `FAILED ..._first_cases_are_pinned` (2 failed, 6 passed); default asserts with `-x`: `1 failed in 1.62s` | yes |
| M6 | `ts/test/fuzz.test.ts` | `test("the fuzz corpus is configured in CI", () => {` -> `..., { skip: "QA M6" }, () => {` | `CI=true npm test`, variable unset | **SURVIVED**: exit=0, `﹣ the fuzz corpus is configured in CI # QA M6`, `ℹ pass 681 ℹ fail 0 ℹ skipped 1`. No test, tool or workflow check covers the guard (grep for `configured in CI`/`CONTEXEL_FUZZ_CASES` finds only the two test files and the two workflows). The same holds for the C# `Assert.False(...)` guard. Informational coverage gap (G1) | yes, recompiled |
| M7a | `csharp/Contexel/Stages.cs:569` TrimBody | `used + cost > maxTokens` -> `>=` | `dotnet test` without and with corpus | **CAUGHT by shared vectors alone**: `trim_to_budget/budget_is_the_exact_cost_of_three`, `text_pipeline/log_text_end_to_end` (Failed: 2). With corpus the fuzz also fails: `11 of 20000`, `--show 912` | yes, rebuilt |
| M7b | `csharp/Contexel/Stages.cs:78` Dedupe | a missing key reads as `""` instead of `null` (`? v : null` -> `? v : ""`) | same | **Shared vectors MISS it** (no corpus: `Passed! Failed: 0, Passed: 623`). **The fuzz CATCHES it**: `103 of 20000 fuzz cases diverge`, `--show 530` | yes, rebuilt |
| M7c | `csharp/Contexel/Stages.cs:31` TypedKey | `PyNumber(d == 0 ? 0.0 : d)` -> `PyNumber(d)` (no -0.0 normalization) | same | Caught by `BehaviorTests.NegativeZeroEqualsPositiveZeroLikePython`. **The fuzz does not catch it**: no -0.0 is generated (note N5) | yes, rebuilt |

---

## Adversarial probes

| Input/scenario | Expected | Observed | Pass |
|---|---|---|---|
| `--seed 7 --cases 3000 --out parity/fuzz-seed7.json`, replayed in both ports | no divergence (informational only) | `wrote 3000 cases (seed 7) ...; 315 error cases, 466 strict, 8 redrawn`; `_meta` checker all True; TS `ℹ pass 3 ℹ fail 0` `(seed 7)`; C# `Passed: 3` | yes |
| extra: seeds 1, 99, 31337 at 20000 cases each | no divergence | TS `pass 3 fail 0` and C# `Passed: 3` for all three (27/31/36 redrawn) | yes |
| TS replay, absolute path (Windows form via `cygpath -w`, and msys form) | pass | `ℹ pass 3 ℹ fail 0` both | yes |
| TS replay from the repo root as cwd, relative `parity/fuzz-corpus.json` (`node --test ts/dist-test/test/fuzz.test.js`) | pass | `ℹ pass 3 ℹ fail 0` | yes |
| TS from `ts/` with a cwd-relative `../parity/fuzz-corpus.json` | resolved against the repo root (as documented), so fails closed | `ENOENT ... '<parent of wt>\parity\fuzz-corpus.json'`, `ℹ pass 0` (fails closed; the documented behavior) | yes |
| C# replay with an absolute path | pass | `Passed! - Failed: 0, Passed: 3` | yes |
| `git status --porcelain` with the corpus present | corpus not listed | `0` matching lines; `git check-ignore -v`: `.gitignore:19:parity/fuzz-corpus.json` | yes |
| U+0131 and U+01C5 (in `EXCLUDED`, not named in ADR-007): allowed in a temporary generator copy, seed 5 / 6000 cases (3345 and 3332 cases carry them, about 455 with `rescore` and about 450 with `quarantine`) | margin measured | 0 divergences in TS and C# (`pass 3` / `Passed: 3`). The exclusion is conservative, not a divergence filtered silently (note N3) | yes |

---

## Bugs found

| # | Repro steps (minimal) | Severity | Fixed @ | Re-verified | Regression test |
|---|----------------------|----------|---------|-------------|-----------------|
| D1 | A determinism regression makes the generator test take minutes to report: in `<wt>` change `parity/generate_fuzz.py` `Gen.__init__` to `self._random = random.random`, then run `PYTHONPATH=. python -m pytest -v -o faulthandler_timeout=40 tests/test_fuzz_generator.py`. `test_fuzz_corpus_is_deterministic_and_inside_the_envelope` stalls at line 51 (`assert gf.dumps(small) == gf.dumps(again)`). The faulthandler dump shows `difflib.find_longest_match` <- `_pytest/assertion/util.py _diff_text`, because pytest diffs two ~700 KB single-line strings. It did not finish in over 5 minutes, and a CI job would sit until its timeout. With `--assert=plain` it fails in 2.6 s. Suggested fix (G3): compare `hashlib.sha256` digests (or lengths first) instead of the raw dumps in lines 51 and 57. | Low (the test does detect; only reporting is pathological) | open | n/a | n/a |
| D2 | `.gitignore` ignores only the exact name `parity/fuzz-corpus.json`. `PYTHONPATH=. python parity/generate_fuzz.py --seed 7 --cases 3000 --out parity/fuzz-seed7.json` (the plan's own probe) followed by `git status --porcelain` gives `?? parity/fuzz-seed7.json` (several MB; 37 MB at 20000 cases), so it can be committed by accident. Suggest `parity/fuzz-*.json`. | Low | open | n/a | n/a |

### Informational notes (no action required for G5)
- **G1 (coverage gap, from M6):** no test guards the fail-closed CI branches themselves (TS `if (process.env.CI)` and C# `Assert.False(...)`). Weakening either to skip leaves the suites green under `CI=true`. Possible coverage: a TS test that spawns `node --test dist-test/test/fuzz.test.js` with `CI=1` and no variable and asserts a non-zero exit, and the same for C#.
- **N1:** with an empty `cases` list, C# fails only `FuzzCorpusIsPresentAndComplete`. `EveryFuzzCaseMatchesPython` and `TheReplayCanFail...` pass vacuously (TS's corrupted-replay test asserts `sample.length > 0`; the C# one does not). The suite still fails, so AC 3 is met.
- **N2:** the C# completeness assertions have no messages. The duplicate-id failure reads `Values differ Expected: 20000 Actual: 19999`, which looks like a count failure. TS messages are specific (`duplicate case ids`, `case_count disagrees ...`, `no error case in the corpus`).
- **N3:** `EXCLUDED` contains U+0131 and U+01C5, but ADR-007's margin 3 lists only U+017F, U+00DF, U+212A, U+212B, U+1E9E and "the sigmas", and says each margin "was measured by allowing the character class". My probe measured 0 divergences for these two characters. This is a doc wording nit, not silent filtering.
- **N4:** when the variable is unset locally, C# reports the three FuzzTests as Passed rather than Skipped (623 either way). This is by design, but a local run cannot show that no replay happened.
- **N5:** the fuzz `NUMBERS` pool has no -0.0, so a -0.0 regression in the dedupe key (M7c) is invisible to the fuzz. It is covered by a C# behavior test.
- **N6:** `ruff check parity tests/test_fuzz_generator.py` reports 36 E501 (line > 100). 13 were already in `parity/parity_cases.py` on `main`. CI lints only `contexel` (`ci.yml:58`), which is clean.
- **N7:** `docs/plans/foundation-hardening.md` at this commit still says Slice 7 is "planned ... awaiting the human's review" (line 6) and "Blocked on: the human's review of the Slice 7 plan" (line 142). The status is stale if it is not updated at merge.
- CI wiring checked by reading: both parity jobs in `ci.yml` and the 4 jobs in `release.yml` run `python parity/generate_fuzz.py --out parity/fuzz-corpus.json` after `pip install -e .` and set `CONTEXEL_FUZZ_CASES: parity/fuzz-corpus.json`. I did not execute it (no network or CI here).

## Security sweep
Secrets scan of `git diff main...HEAD` (api key, password, token, private-key headers, `ghp_`, `AKIA`): none. The only match for dangerous constructs is `subprocess.run([sys.executable, ...generate_fuzz.py, *args])` in `tests/test_fuzz_generator.py`, which uses list arguments and no shell. "secret" and "ignore all previous instructions" appear only as fuzz vocabulary. The corpus is generated locally from a fixed seed and only parsed as JSON; nothing is fetched. No new dependencies. Fail-closed behavior was verified in section 3.

**Security verdict:** no findings from QA's sweep (the formal Security Reviewer sign-off is separate).
**QA verdict:** **PASS**. AC 36 is met on `a1877f4`: a deterministic 20000-case corpus (sha256 `d7554a37...a57413`), zero divergences in both ports, fail-closed in both ports, every timing well under 60 s, and the fuzz demonstrably catches defects the shared vectors miss (M1, M7b). D1 and D2 (Low) and G1 are handed back to G3 as non-blocking follow-ups.

Worktree left clean: `git status --porcelain` -> 0 lines (the git-ignored `parity/fuzz-corpus.json` remains). Nothing was committed or pushed, and the main checkout was not modified.
