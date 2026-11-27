Filed 2026-11-26 from the Slice 7 execution workspace for branch `feat/hardening-s7-differential-fuzz`. Sanitised: no user name, home or temporary path, e-mail address or agent identifier.

# SDD ledger, Slice 7 (differential fuzz)

Branch feat/hardening-s7-differential-fuzz from main 247d11a (plan merged, PR #11). Spec: brief AC 36 + ADR-007 (reachable).
Task 0 baseline (controller, no commit): Python 1076 passed 1 skipped; TS 678/0 fail; C# 617; ruff, mypy, check_versions, site_check, check_benchmark_numbers clean. Matches plan.

## Pre-flight scan (plan conflicts)
| Pair / task | Shared file or interface | Finding |
|---|---|---|
| T1 -> T3, T4 | corpus file from `generate_fuzz.py --out`; `_meta` + case format | T3/T4 read the file by path via CONTEXEL_FUZZ_CASES; consistent |
| T1 -> T5 | CLI `--out` in CI step | consistent |
| T2 -> T4 | csharp/Contexel.Tests/CaseTests.cs (T2 edits ArgNames/suffix); T4 FuzzTests.cs calls CaseTests.AssertCase | T4 runs after T2, so the adapter already passes suffix; consistent |
| T2 -> T1 tests | parity_cases.py/vectors.json vs tests/test_fuzz_generator.py | generator tests use canon only; independent |
| T3 vs T5 | ts/package.json (T3) vs workflows (T5) | disjoint files |
| T6 vs all | ADR-007/002, README, CHANGELOG | docs only, after code |
| each task self-agreement | plan was built by script from verified worktree and replayed onto a fresh worktree (15 paths identical) | tests match code; created files match later touched files |
Scan result: no conflicts. Plan-mandated items rubric might flag: none noted.
Model plan: implementers sonnet (byte-exact transcription + multi-suite checks), T1 reviewer opus, other task reviewers sonnet, final review opus.
Task 1: dispatched implementer (sonnet); BASE 247d11a
Task 1: implementer DONE, commit 8d00fbb (1084 passed 1 skipped; pins reproduced; 2209 err/3115 strict/24 redrawn; ruff E501 on new files outside CI scope, minor). Reviewer (opus) dispatched <id>.
Task 1: minor (deferred): astral-coverage test counts emoji too, weaker than its comment (tests/test_fuzz_generator.py ~87)
Task 1: minor (deferred): as_records call and second outcome() in make_case not wrapped; 'except ContexelError: raise' no-op; canon crash becomes counted redraw (none occur)
Task 1: minor (deferred): comment 'no backslash escapes' inaccurate; dead counter in a test; private _pipe import; usage line omits PYTHONPATH; E501 on new files outside CI scope
Task 1: complete (commits 247d11a..8d00fbb, review clean; minors deferred, plan-mandated verbatim code)
Task 2: dispatched implementer (sonnet); BASE 8d00fbb
Task 2: implementer DONE_WITH_CONCERNS, commit 47a0a8c (C# 620, TS 681, vectors 177). Concern: pre-existing tests/test_doctrine_dashboard failure (missing openapi file; doctrine tests excluded from baseline) and one unidentified non-reproducing failure in a first full Python run -> re-check on final whole-branch run. Reviewer (sonnet) dispatched.
Task 2: minor (deferred): astral_suffix case cannot distinguish code-point from UTF-16 counting (1 astral char = 1 token either way); '...' suffix is 1 token like the default, so 'counted before the cut' shown only by contrast. Plan-mandated.
Task 2: complete (commits 8d00fbb..47a0a8c, review clean)
Task 3: dispatched implementer (sonnet); BASE 47a0a8c
Task 3: implementer DONE, commit 5e85ff9 (TS 681+1 skipped unset, 684 set, CI=1 unset fails closed). Env note: stale pip-installed contexel in local site-packages shadows repo (needs PYTHONPATH locally; CI uses pip install -e . like generate_vectors steps) - not a plan defect. Reviewer (sonnet) dispatched.
Task 3: minor (deferred): corpus read/parse at module load (fails closed anyway); canary assert.throws(Error) accepts any Error; id index recovered by splitting id string. Plan-mandated.
Task 3: complete (commits 47a0a8c..5e85ff9, review clean)
Task 4: dispatched implementer (sonnet); BASE 5e85ff9
Task 4: implementer DONE, commit a0d9fdc (C# 623 set/unset; CI=true unset fails closed). Reviewer (sonnet) next.
Task 4: minor (deferred): canary ThrowsAny<Exception> with Corrupted() inside lambda could count a helper bug as refusal; corpus parsed 3x (time only); catch handler casts id; Assert.False double negative. Plan-mandated.
Task 4: complete (commits 5e85ff9..a0d9fdc, review clean)
Task 5: dispatched implementer (sonnet); BASE a0d9fdc
Task 5: implementer DONE_WITH_CONCERNS, commit 8ccf0d4. Concern: reported two brief old-strings not matching verbatim; controller inspected resulting diff: final file content equals verbatim application of the brief (trailing-newline / prefix-match readings), so no real deviation. First CI run unverified. Reviewer next.
Task 5: review NEEDS FIXES (spec ok for the 4 listed sites; plan defect confirmed by controller reading release.yml): nuget-publish 'Test, pack' runs dotnet test and npm-publish's `npm publish` runs prepublishOnly->npm test, both under CI=true with no corpus -> fail closed AFTER pypi-publish succeeded.
Task 5: Ruling: give both publish jobs the corpus (job-level CONTEXEL_FUZZ_CASES + existing pinned setup-python + pip install -e . + generate step) rather than dropping tests/--ignore-scripts — dropping would disable a gate (§5) — costs ~30-60 s per publish job; if wrong, revert the fix commit and instead make the guard skip for publish jobs.
Task 5: fix round 1/5 dispatched (resumed the implementer); FIX_BASE 8ccf0d4
Task 5: fix round 1/5 implemented, commit 9ff6ee9 (release.yml +16; both publish jobs get job-level env + setup-python + pip install + generate). Scoped re-review (sonnet) dispatched.
Task 5: fix round 1/5 (2 addressed, 0 open; commits 8ccf0d4..9ff6ee9)
Task 5: complete (commits a0d9fdc..9ff6ee9, re-review clean). Plan defect found+fixed: publish jobs (npm-publish, nuget-publish) also need the corpus. Task 6 docs must mention it (S7-11 text says release gate only).
Task 6: dispatched implementer (sonnet); BASE 9ff6ee9; carried ruling: ADR-007 "as built" sentence names the publish jobs too.
Task 6 dispatch: Ruling: ADR-007 text says every replay-running job (ci parity jobs, release ts/cs-test, npm-publish, nuget-publish) generates the corpus — corrects plan text that only named CI and the release gate — costs nothing if wrong (docs).
Task 6: implementer DONE_WITH_CONCERNS, commit a1877f4 (docs only; pytest 1087+1 skipped, TS 684, C# 623). CHANGELOG old-anchor trailing blank absent -> heading-only anchor. Reviewer next.
Task 6: minor (deferred): ADR-007 margin 3 list of excluded case-special chars omits U+0131 and U+01C5 (generator EXCLUDED has them) -> triage at final review; two over-wide lines; ADR-007 margin 2 does not cross-reference ADR-002.
Task 6: complete (commits 9ff6ee9..a1877f4, review clean)
Final gates dispatched in parallel on a1877f4 (base 247d11a): code review (opus), security review (opus), QA with mutation testing (opus, worktree isolation). Outputs: final-code-review.md, final-security-review.md, final-qa-report.md in this workspace.
QA gate: worktree isolation param failed (stray locked worktree removed with its branch, nothing in it); re-dispatched QA (opus) against a scratch worktree of a1877f4 outside the repo.
Final security review: APPROVE WITH CONDITIONS, no veto. F1 LOW: publish jobs' new `pip install -e .` runs unpinned hatchling from PyPI in jobs with id-token:write (consequence of Task 5 fix round ruling); remedy = drop the install in npm-publish/nuget-publish and set PYTHONPATH for the generate step (dependencies = []). F2 LOW: .gitignore entry anchored to parity/fuzz-corpus.json only. F3-F6 INFO.
Pending: final code review, QA. Then ONE fix dispatch with all findings (F1 expected to be applied).
Final code review: ready with fixes, nothing critical. IMPORTANT 1 (plan defect, controller-verified): U+0130 margin is NOT new: ADR-002 already records it since Slice 5 (bullet at ~line 85, 'older than Slice 5 and is now recorded', commit e3c4c80); Task 6 added a duplicate bullet at ~67-69 claiming 'found by the differential fuzz'; CHANGELOG says 'one margin that was not recorded'; ADR-007 margin 2 lacks a cross-reference; ADR-007 margin 1 and generator docstring cite ADR-006 for the astral margin which ADR-002 7 records. The plan and master plan call it new: plan text wrong. IMPORTANT 2: drop pip install -e . in publish jobs (== security F1). Minors: M1 ADR-007 margin 3 omits U+0131/U+01C5; M2 C# unset-locally tests show Passed not skipped while docs say skipped; M3 ADR-007 says shared vectors green 'in either port' under budget mutant but plan measured TS only (confirm vs QA M1); M4 pinned-digest comment understates canon dependence; M5 failure/skip messages should include the generate command. Ledger triage: fix T6 items; leave other deferred minors.
Note for human: npm-publish first real replay happens on a tag push (dispatch dry-run skips prepublishOnly).
Waiting on QA, then ONE fix dispatch for: IMP1, IMP2/F1, F2 (.gitignore glob), M1-M5.
Final QA: PASS on all 6 ACs at a1877f4. 8 of 10 mutants caught; budget-floor mutant caught by fuzz only in both ports (112 of 20000); dedupe mutant missed by shared vectors but caught by fuzz (103); M6 guard weakening survives = coverage gap G1 informational; -0.0 not fuzzed (N5). Defects: D1 LOW pytest assertion rewriting hangs difflib on a mismatch of two 700KB strings (test_fuzz_generator.py:51,57) -> compare sha256; D2 LOW gitignore too narrow. N1 C# canary vacuous on empty cases; N2 C# assert messages; N4 C# unset shows Passed not skipped; N7 master plan lines 6,142 stale (controller post-gate update). Seeds 1,7,99,31337: 0 divergences in both ports.
Final-gate fix wave: ONE fix dispatch (fresh sonnet implementer), findings file final-fixes.md; base a1877f4.
Final fix wave DONE: commits 4819262 (ci), b273f43 (gitignore), 24c2176 (tests), 540ba2a (docs); Python 1087+1 skipped, TS 684/681+1, C# 623. Scoped re-review (opus) next.
Final fix wave re-review (opus): all findings addressed (A,B,C1-C3,D1-D5), no new Critical/Important. Minor deferred: CHANGELOG ~203 says the astral margin is one 'the fuzz domain excludes' (astral letters are still generated in the note field; ADR-007 margin 1 is exact); two over-wide lines. Out of scope for fix wave, controller to do: master plan lines 6,127,128,142 and S7 plan line ~44 still call U+0130 new/unrecorded.
Evidence filed under docs/reviews and docs/qa; master plan and the Slice 7 plan (erratum) updated. Slice 7 branch complete pending the human's push, the first CI run and the merge.
