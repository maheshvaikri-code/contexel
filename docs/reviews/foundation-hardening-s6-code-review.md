> Filed 2026-11-24 from the Slice 6 execution workspace for branch `feat/hardening-s6-honest-benchmarks`. Sanitised: no user name, home or temporary path, e-mail address or agent identifier.

# Code review (G4): Slice 6, honest benchmarks

Branch `feat/hardening-s6-honest-benchmarks` at `798ffef` (13 commits on `main` `eddb5c3`). Reviewer: Code Reviewer, fresh context, whole branch. Reviewed against the plan `docs/superpowers/plans/2026-11-22-foundation-hardening-s6-honest-benchmarks.md` (Global Constraints, Review Focus, rulings S6-1 to S6-9) and the brief ACs 23 to 27, and against the controller's ledger.

**Verdict: SHIP AFTER FIXES.** No BLOCKER. Four MAJOR findings (three are prose or predicate problems, one is the order of merge and timing regeneration). The code and tests are sound, and the original episodes reproduce exactly.

## What the reviewer ran
- Whole suite: 953 passed. The two tests that need the libraries and the cache run here (11 passed) and skip in CI, which installs only `.[dev]`.
- `python tools/check_benchmark_numbers.py`: agrees.
- Python 3.9.13 with every benchmark library blocked by an import hook: every benchmark module imports, `publish.check` returns `[]`, the command exits 0, all six test files and the tool compile; no `match`, no runtime `X | Y`, no `zip(strict=)`.
- `mypy` (contexel only): clean. `ruff` on `benchmarks`, `tools`, `tests/test_benchmarks_*.py`: 89 E501 (line length) findings, outside CI's lint scope.
- `git diff --stat main..HEAD -- contexel ts csharp parity`: empty.
- Privacy scan of the whole diff and every commit message: clean; 0 co-author trailers; every subject at most 72 characters.

## Original episodes: reproduced exactly (verified)
Line-by-line comparison of the old and new `competitors.py`: with `term_ok=None, pool=2` the episode builder makes the same random calls; each outcome implementation's step list does what the old functions did, in the same order (contexel with an explicit `match="word"`, which is the default); fill, useful share and compliance are computed the same way; the timed implementations match too. COMPARISON.json against the numbers published on `main`: recall (strong / weak) 100/100, 93/32, 100/100, 30/30, 100/100; compliance 100, 100, 0, 100, 0; fill 0.95, 0.95, 91.62, 0.52, 129.21; useful share 100, 100, 100, 89.75, 74.15; tokens out and records kept unchanged.

## Findings
| # | Severity | Location | Finding | Smallest fix |
|---|---|---|---|---|
| 1 | MAJOR | README.md ~138-151, site/benchmarks.html ~113-114, competitors.py ~966-968 and ~1104-1107 (rendered into COMPARISON.md) | The explanation of the speed gap rests on a false contrast. The text says the term-overlap scorer "cuts by characters instead of tokens, and trims with a heuristic" and that contexel "clips to a token-accurate cap". The benchmark runs contexel with the default tokenizer, a `ceil(len/4)` estimate, and `trim_to_budget` prices with the same estimator, so contexel also cuts by characters. A probe: on the same snippet with `max_tokens=24` contexel clips to 93 characters and the glue to 96. The generated report also says `truncate_field` "binary-searches to a true token cap", which contradicts the README's own stage table ("closed-form for the built-in estimator"). | Delete the character/heuristic contrast; say "a cap computed with the active tokenizer (here the default ~4 chars/token estimator)"; reword competitors.py to match and re-render COMPARISON.md from the committed JSON. |
| 2 | MAJOR | publish.py ~314-333 (`_full_marks`, `_only_contexel_full`) vs site/index.html ~108-109 | The check is weaker than the sentence it guards. The sentence says "the only row with full marks in every **outcome** column"; the predicate also requires full marks in the operations column. A probe on a scratch copy set the term-overlap row to 100/100 recall: the predicate still passed although two rows then had full outcome marks; the check fired only by coincidence on the PyPI "97% recall" number claim. | Make the predicate test only recall, compliance and useful share; add a drift test that sets term overlap to 100/100. |
| 3 | MAJOR | README.md ~145-146, site/benchmarks.html ~116-117, CHANGELOG.md ~577-578 | "The best of three runs of the command" becomes false after the human's single-run regeneration; nothing checks it. | Say "one run of the command on one machine" in all three places. |
| 4 | MAJOR (merge gate) | `.github/workflows/pages.yml` (push to main, paths `site/**`) | Merging deploys the site and publishes the README, so the loaded-machine timing columns (about 2.5 times a quiet run) would go live. | Regenerate the timing columns on a quiet machine before merge; the hand-off must say "before merge", not "before publishing". |
| 5 | MINOR | competitors.py ~1043-1046 (generated) | "Any recall short of 100% below is that ambiguity ... not a scoring defect" now sits above the inflected section (35% is a matching failure by construction) and the langchain bullet. | Scope it to contexel's recall. |
| 6 | MINOR | competitors.py ~26-27, ~507-512 | The module docstring says a missing library becomes a report note, never an error; with toolz blocked, `operations()` and `time_task` raise ImportError; `count()` runs outside the try, so the except block cannot be reached. | Say a missing library is an error (install the `benchmarks` extra); drop the dead try/except or move `count()` inside it. |
| 7 | MINOR | site/index.html ~133-134, publish.py ~497-500, CHANGELOG.md ~583-586 | "Costs ~2.4 µs per record on token-counting paths" is a hand-typed performance number on a checked page that nothing checks (the scan has no µs/us/ns unit; the figure is not in RESULTS.json). The changelog's limitation names only the "seconds" figures. | Add µs/us/ns to the unit scan, then generate or register the figure, or drop it, and amend the changelog sentence. |
| 8 | MINOR | README.md ~155-156, site/benchmarks.html ~130-131 | "A second set of episodes keeps the hit lists" reads as if the same 100 episodes are reused; the terms are filtered (`pool=4`) so targets and hit lists differ, which is why contexel shows 99% "original terms" there and 100% in the main table. | "... a second set of episodes, chosen so every term can be inflected, whose hit lists come from the original terms ...". |
| 9 | MINOR | tests/test_benchmarks_competitors.py ~46-50 | Nothing protects the original episodes after this slice: the default-episodes test compares defaults with defaults. | Pin a golden value on the fixture corpus (first episode's target, terms and `len(hits)`, or a SHA-256 of `json.dumps(build_episodes(_corpus(), n=5))`). |
| 10 | MINOR | README_PYPI.md ~112-117 | The PyPI README never says the inflections are synthetic. | Add "synthetic" (mind the registered claim pattern). Can wait for the release. |
| 11 | MINOR (design) | competitors.py (1,134 lines), competitors.py ~815-836 vs publish.py ~71-91 | About 300 lines are report rendering; `glance_rows` and `publish.glance` repeat the same join. | Later: split out `competitors_report.py`. Not needed before merge. |
| 12 | NIT | publish.py ~574 | `check()` re-parses `dataset.sha256` with weaker validation than `expected_digest()`. | Reuse `expected_digest()`. |
| 13 | NIT | competitors.py ~750 | `collect()` records the pin, not the digest it verified (equal through `load()`). | Record `fetch_dataset.verify()`. |
| 14 | NIT | benchmarks/*.py, tests | 89 E501 findings outside CI's lint scope; 3 changelog lines over 80 columns. | Re-wrap. |
| 15 | NIT | README.md ~114 | Names `benchmarks/opcount.py` as where each implementation's code is defined; the step lists are in competitors.py. | Name both files. |

## Scope check
Every AC is covered: AC 23 (`inflection.py`, `build_inflected_episodes`, the guard covers code, docstring, path and symbol), AC 24 (`g_score_overlap`, the term-overlap row everywhere), AC 25 (`opcount.count` with the module-frame filter and the warm-up), AC 26 (`publish.check`, run in CI through a test), AC 27 (`fetch_dataset.verify`, `.part` then replace, LF-normalised digest). Nothing extra changed. The CHANGELOG is accurate sentence by sentence apart from findings 3 and 7.

## Done well
The generated-block, registered-claim and unit-scan design is sound and tested in both directions; opcount really is computed and has a good fix for first-import false positives; the episode-builder extension keeps the old random path byte-identical; the honesty improvements are real ("sub-20 ms" became a checked "about 20 ms"; "the slowest" became a checked "two slowest, order can change"; the scored baseline is published with its small margin; the stem caveat appears everywhere; an old apples-to-oranges "untraced baseline" comparison was removed); the round-trip test of the pure renderers is a good test of "rendered from the dictionary alone".

## Triage of the ledger's deferred minors
- **Fix before merge:** Task 5 default-episodes tautology (finding 9); Task 5 missing library crash vs docstring (finding 6); Task 6 no us/ns unit (finding 7).
- **Fix before release:** Task 6 PyPI "synthetic" (finding 10).
- **Defer:** Task 1 (download before pin read; `.part` left on non-checksum failures, but reword the comment; mismatch test; `verify()` FileNotFoundError; real-pin test duplicate); Task 2 (all); Task 3 (all; G5 mutation will probe the prefix and other-step tests); Task 4 (all); Task 5 (no unit tests for `inflected_outcomes` and the others, recommended for G5; `INFLECTION_SHAPERS` by position; ERROR-row wording; `max()` ValueError; `TIMED_OPS` denominator; file size; `fetch()` on a missing cache); Task 6 (tokenizer sample measures the README itself; LF on `--write`; "zero cost" with no baseline; competitor versions only in COMPARISON.md; other predicate drift tests; `_zero_compliance` ignores weak recall; strong-signal wording; weak disclaimer predicates; comment alignment; italics in cells; "version 2x"); Task 7 (long changelog lines; "best of 5" vs "best of three").

## The controller's rulings
Task 2 (positive pin test), Task 3 (module-frame filter and warm-up), Task 5 (guard covers path and symbol) and rulings 1 to 6 of Task 6: correct. Ruling 7 (seconds out of scope): acceptable but incomplete (the µs figure, finding 7). Ruling 8: right for COMPARISON.md's conditional sentence, wrong to accept "best of three" in the README and site as true of the committed set because the set is about to be replaced by a single run (finding 3). Task 6 selection: the rule selected on the sum over all rows, not contexel's own timing (ledger wording to be corrected). Task 7 (no machine-load statement in the changelog): acceptable only if the regeneration happens before merge (finding 4).

## Fix list before merge
MAJOR 1, 2, 3 and 4, plus MINOR 6, 7 and 9; MINOR 5 and 8 are cheap and belong in the same wave; MINOR 10 can wait for the release.

## What happened to the findings (filed with the branch)

The branch head the review ran on was `798ffef`. A first fix wave (six commits, `e71477a` to `406e52d`) and a short second wave (two commits, `eaff128` and `53246a8`) answered the three gates together; the scoped re-reviews found every finding of this report ADDRESSED:

- **1** (false "token-accurate against characters" contrast): removed from the README, the site, the report text and `COMPARISON.md`; the statement about `truncate_field` now matches `contexel/stages.py` and the README stage table.
- **2** (`_only_contexel_full` weaker than its sentence): it tests only the outcome columns; drift test added.
- **3** ("best of three"): replaced everywhere by "one run of the command on one machine".
- **4** (merge deploys the site): the timing columns come from a busy machine; the human regenerates `COMPARISON.json` and `RESULTS.json` on a quiet machine before merging (recorded in the ledger and the plan).
- **5, 6, 7, 8, 9, 10, 12, 13, 15:** fixed as described in the findings (scoped sentence; docstring made true and `ValueError` on empty episode lists; the hand-typed microsecond figure cut and the unit scan extended; second-set wording; golden episodes pinned; "synthetic" on the PyPI page; `check()` reuses `expected_digest()`; the recorded digest is the one `verify()` returned; both files named).
- **11** (`competitors.py` is 1,100+ lines, report rendering duplicated in `publish.py`): deferred to a later slice.
- Deferred minors of the task reviews: triaged as listed in the findings above; the three the reviewer marked "before merge" were fixed.

Result after both waves: Python 1073 passed, 1 skipped (a symlink test that needs a privilege on Windows); TypeScript 678 and C# 617 untouched; `ruff`, `mypy`, the version check, the site check and the benchmark-number check clean.
