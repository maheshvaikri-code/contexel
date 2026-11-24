> Filed 2026-11-24 from the Slice 6 execution workspace for branch `feat/hardening-s6-honest-benchmarks`. Sanitised: no user name, home or temporary path, e-mail address or agent identifier.

# QA report (G5): Slice 6, honest benchmarks

Branch `feat/hardening-s6-honest-benchmarks` at `798ffef`. Reviewer: QA Engineer (adversarial; execute, do not inspect). Method: every mutation, regeneration and experiment ran on copies made with `git archive` (LF, plus one CRLF copy) in a scratch directory with the dataset copied in; the repository working tree was not touched and `git status --short` was empty at the end.

**Verdict: FAIL** (one BLOCKER, three MAJOR; everything else held). The product code works on Python 3.9; the new integrity tests do not (62 of 112 new tests raise `TypeError` on 3.9 because `Path.write_text(..., newline=...)` exists only from 3.10, and CI runs pytest on 3.9 in three legs). With that one call shimmed, 110 pass, 0 fail, 2 skip.

## 1. Suite on a pristine copy
LF copy with `PYTHONPATH=.`: 953 passed; LF copy without `PYTHONPATH`: 953 passed; CRLF `git archive` copy: 953 passed (`python -B -m pytest -q -p no:cacheprovider --ignore-glob='tests/test_doctrine_*'`).

## 2. Mutation testing
Each mutant ran on its own fresh copy and was checked as applied by a unified diff against the pristine copy; `__pycache__` purged, `python -B`. The six `tests/test_benchmarks_*.py` files ran first (baseline 112 passed); survivors were then run against the whole suite.

| # | Mutant | Result |
|---|---|---|
| a | `digest` keeps CRLF | killed (dataset digest line-ending test; committed-checksum test) |
| b | cache used without verify in `fetch`/`load` | killed (mismatch test) |
| c1 | download moved into place before verify | killed |
| c2 | `.part` left behind on mismatch | killed |
| c3 (extra) | download written straight to the cache path | SURVIVED (fail closed anyway: the cache is verified on every use; informational) |
| d1 | upper-case pin accepted | killed |
| d2 | 63-character pin accepted | killed |
| e | `if got != want` made false | killed (2 tests) |
| f1 | plain-word guard removed | killed |
| f2 | "differs" guard removed | SURVIVED, equivalent (`inflect` always changes its input) |
| f3 | same-stem guard removed | killed |
| f4 | not-a-target-word guard removed | killed |
| g1 | `e` rule broken | killed |
| g2a | `ss` exception removed | killed |
| g2b | `us` exception removed | killed |
| g2c | `is` exception removed | **SURVIVED** (no test term ends in `is`) |
| h1 | `term_ok` ignored | killed |
| h2 | widening to path and symbol words reverted | killed |
| i1 | overlap scorer: query not lower-cased | killed |
| i2 | overlap scorer: query not tokenized | **SURVIVED** (moves the term-overlap baseline from 97 to 95 on real data) |
| j1 | every library step native | killed |
| j2 | native inverted | killed |
| j3 | module-frame filter removed | killed |
| j4 | warm-up removed | killed |
| j5 (extra) | warm-up on the shared sample | killed |
| k1 | profiler not restored | killed |
| k2 (extra) | profiler reset to None | killed |
| l1 | unregistered-number guard off | killed (22 tests) |
| l2 | generated-block comparison off | killed |
| l3 | claim values not compared | killed (14 tests) |
| l4 | stale COMPARISON.md not detected | killed |
| l5 | stale RESULTS.md not detected | killed |
| l6 | dataset-pin comparison off | killed |
| l7 | whole match blanked instead of `_blank_group` | killed (12 tests) |
| l8 | claim whose pattern no longer matches treated as fine | killed |
| l9 | "about N ms" tolerance raised to 100% | killed |
| l10 | case-insensitivity removed | killed |
| l11 | entity decoding removed | killed |
| l12 | attribute scan removed | killed |
| l13 | bare-cell guard removed | killed |
| l14 | `_two_slowest_compliant` always true | killed |
| l15 (extra) | NBSP replacement removed | SURVIVED, equivalent (`\s` already matches NBSP) |
| l16 (extra) | underscore lookbehind reverted | killed |
| m1 | RNG order shifted in `build_episodes` | **SURVIVED** (changes the real episodes, hash `61b29d1f` to `d6fabe39`, moves a published figure: inflected recall 35 to 36) |
| m2 | default `pool` 2 to 3 | SURVIVED, equivalent (prefix property of `random.sample`; same real-data episode hash) |
| m3 | default `seed` 11 to 12 | **SURVIVED** |

What m1 and m3 leave unpinned: the default (original) episodes; `test_the_default_episodes_are_not_changed_by_the_new_options` compares the defaults with the defaults and its fixture gives every row the same docstring, so only the targets can change and the targets are never asserted. What i2 leaves unpinned: query tokenization (the scorer test's punctuation case is masked by a duplicate). What g2c leaves unpinned: the documented `is` exception.

## 3. Determinism
`python -m benchmarks.competitors` then `python -m benchmarks`, twice, all runs rc=0. With timing keys excluded: COMPARISON run 1 equals run 2; RESULTS run 1 equals run 2; COMPARISON run 1 equals the committed COMPARISON.json. RESULTS run 1 differs from the committed RESULTS.json in 3 values: `accuracy[0]` (the sample "prose (README.md)"): actual 10509 vs 10358, error -2.86% vs -3.01%, heuristic 10208 vs 10046. The suite measures the live README, which was edited at `0ca0701` after RESULTS.json was generated at `f88c103`; `site/benchmarks.html` publishes -3.0% while HEAD regenerates -2.9%. On the regenerated copy (the machine was loaded by parallel runs) the "two slowest" claim held and the check correctly reported the import claim ("about 20 ms") broken at 52.7 ms: any regeneration on a loaded machine breaks that claim.

## 4. Check robustness
LF checkout, CRLF checkout (git archive) and a fully converted CRLF tree: exit 0. A README glance block edited by one character; markers removed (both, only start, only end), duplicated, nested (other and same block), an unknown block: exit 1 with a message naming file and reason. 32 cases (four files times {`2.5x`, `12&nbsp;ms`, `40&#37;`, `3&times;`, `title="takes 12 ms"`, `12  ms`, `12 MS`, `10X`}): exit 1 every time. A bare numeric cell in each of the four files; a reworded registered claim (two cases); a changed claim value; COMPARISON.json with a recall edited and the report not regenerated; a changed dataset digest; a missing README or benchmarks page; a missing or invalid results JSON: all exit 1 with a clear message. Not clean (exit 1, fail closed, but a Python traceback): a missing `benchmarks/COMPARISON.md` or `RESULTS.md`; a results JSON missing a key (`KeyError: 'inflected'`); a published file that is not valid UTF-8. An empty `dataset.sha256` reports `list index out of range`. Not caught (pass): a zero-width space, soft hyphen or word joiner between number and unit; a fullwidth `%`; `12 µs`; `placeholder="12 ms"` and `data-*` attributes; a `| a | _12_ |` cell. Caught: fullwidth digits, thin space, a unit split by a tag or comment, `&#x6D;`, Markdown link and alt text, `<TD>`, `1,234`, the minus sign.

## 5. Python 3.9
`py -3.9` and the Visual Studio Python 3.9 are the same 3.9.13. Compiled 15 files; imported all; `check_benchmark_numbers.py` rc=0. `pytest` is not installed for 3.9 (nothing was installed), so the six new test files ran under a minimal stand-in runner (fixtures, parametrize, raises, importorskip): 48 passed, 62 failed, 2 skipped, all 62 with `TypeError: write_text() got an unexpected keyword argument 'newline'`; with `Path.write_text` shimmed to accept `newline`: 110 passed, 0 failed, 2 skipped.

## 6. Adversarial inputs (selected)
`inflect('')` returns `'ing'`, `inflect('s')` returns `''` and neither is inflectable; unicode, digits, upper case and a 100,000-character input are handled (0.000 s). `digest`: an empty file equals plain SHA-256; an all-CRLF file equals SHA-256 of the LF version; a lone CR is kept; CRCRLF normalizes the pair only. `expected_digest`: a two-line pin uses the first word; a BOM raises `DatasetChecksumError`; trailing space, tabs, CRLF and a leading blank line are accepted. `opcount.count` with no steps reports 0 of 6; a raising step re-raises and the profiler is restored; a mutating step changes the caller's sample (the measured pass runs on the caller's object; `operations()` passes a fresh sample); an empty-string root counts nothing as native. `build_episodes([])` returns an empty list; with fewer eligible rows than requested it returns fewer; `inflected_outcomes([])` and `native_outcomes([])` raise `ZeroDivisionError`; `verify` of a missing file raises `FileNotFoundError`. Time for the check on 5 MB documents of prose, table rows, titles or unit runs: 0.4 to 2.5 s; on a 5 MB run of digits, or 4 MB of `1,`, it did not finish in 180 s (quadratic: 10,000 digits 0.50 s, 20,000 2.02 s, 40,000 8.38 s for the records, episodes and budget claims; unclosed `<td>` cells 28.56 s at 40,000; unclosed block start markers 13.86 s at 10,000).

## 7. Regression
TypeScript 678 pass, 0 fail; C# 617 passed, 0 failed (only git-ignored build output written); `parity/generate_vectors.py` on a copy reproduces `parity/vectors.json` byte for byte.

## Findings
**BLOCKER B1.** The new integrity tests call `Path.write_text(..., newline="\n")` (a keyword added in Python 3.10) at nine places in `tests/test_benchmarks_integrity.py`; CI runs pytest on 3.9 in three legs and `requires-python = ">=3.9"`, so 62 tests fail with `TypeError` on 3.9. Fix: a helper writing `text.encode("utf-8")` through `write_bytes` at all nine call sites; add a 3.9 run of the new tests to the close-out checks.

**MAJOR M1.** The default (original) episodes are not pinned (mutants m1 and m3 pass 953). Fix: assert the exact first five targets on the fixture corpus (QA verified the list `p/f28.py fn28, p/f35.py fn35, p/f29.py fn29, p/f39.py fn39, p/f32.py fn32` kills both mutants); optionally a cache-gated test comparing a hash of the 100 real (target, terms) pairs.

**MAJOR M2.** The overlap scorer's query tokenization is not pinned (mutant i2). Fix: `assert competitors.g_score_overlap([records[0]], ["value."])[0]["score"] == 1` (returns 0 under the mutant).

**MAJOR M3.** The committed RESULTS.json cannot be reproduced from HEAD because the "prose (README.md)" sample is the live README. Fix: regenerate after the last README edit; durable fix: measure a frozen prose sample.

**MINOR.** (1) The checker crashes with a traceback (still exit 1) on a missing report file, a key missing from the results JSON and a non-UTF-8 published file. (2) An empty pin gives an unclear message. (3) Quadratic regexes (see the security report L1). (4) The `is` exception of `inflect` is not tested (add `("analysis", "analysising")`). (5) Unit-scan gaps: zero-width characters, soft hyphen, word joiner, fullwidth percent sign, microseconds and nanoseconds, `placeholder` and `data-*` attributes, `_12_` cells. (6) The "about 20 ms" import claim fails on any loaded machine (expected, but the human's regeneration step must run on a quiet one). (7) `native_outcomes([])` and `inflected_outcomes([])` raise `ZeroDivisionError`; `verify(missing)` raises `FileNotFoundError`.

## Acceptance criteria
AC 23 met (inflected episodes reported separately; guards killed f1, f3, f4, h1, h2). AC 24 met, with test gap M2. AC 25 met (j1 to j5, k1, k2 killed). AC 26 met, but the tests break on Python 3.9 (B1) and four crash paths. AC 27 met (a, b, c1, c2, d1, d2, e killed).

## Outcome after the fix waves (filed with the branch)

**BLOCKER B1** (Python 3.9): fixed (a helper writes bytes; no 3.10-only call remains in the new modules and tests). The QA stand-in runner on Python 3.9.13 then gave 231 passed, 0 failed, 2 skipped on the six new test files (CI's real pytest on 3.9 is the first CI run of the branch). **M1** (default episodes unpinned): the exact first five targets of the fixture corpus and a cache-gated hash of the 100 real (target, terms) pairs are now asserted. **M2** (scorer tokenization): pinned. **M3** (RESULTS.json not reproducible): the prose sample is now a frozen copy in `benchmarks/prose_sample.md`; `python -m benchmarks` run twice on copies reproduces the committed `RESULTS.json` apart from timings. **Minors:** the checker reports instead of crashing (a missing report file, a missing key, a wrong type, an empty list, a zero divisor, an unreadable or oversized file); an empty pin has its own message; the patterns are linear; the `is` exception of `inflect` is tested; the unit scan covers entities, zero-width characters, microsecond and nanosecond units and more attributes; `native_outcomes([])` and `inflected_outcomes([])` raise `ValueError`; `verify()` of a missing file raises `DatasetChecksumError`. **Still true:** the "about 20 ms" import claim fails on any loaded machine, so the human's regeneration must run on a quiet one.

Final state: Python 1073 passed, 1 skipped; TypeScript 678, C# 617, parity vectors byte-identical. Both scoped re-reviews found the findings addressed.
