Filed 2026-11-26 from the Slice 7 execution workspace for branch `feat/hardening-s7-differential-fuzz`. Sanitised: no user name, home or temporary path, e-mail address or agent identifier.

# Code review (G4): Slice 7, differential fuzz

- Role: Code Reviewer (fresh context, read-only)
- Range: 247d11a82521d23f60f1c7d4fa14f323a24f10e3..a1877f4db2e7d30a578dfbd31f57c219314e19bf (7 commits, 15 files, +995/-6)
- Read-only: nothing in the checkout was changed. Every command ran against `git archive` copies in a scratch directory outside the repository, with `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider`.

## Evidence I produced (real output, scratch copies of HEAD and of the base)
- `parity/vectors.json` regenerated from HEAD's canon is byte-identical to the committed file (`cmp` silent). A structured diff against the base version shows 0 cases removed, 0 changed, the same order, and exactly 3 added (`truncate_field/custom_suffix_is_counted_before_the_cut`, `.../empty_suffix_leaves_the_whole_budget`, `.../astral_suffix_is_one_code_point`). The only `_meta` change is `case_count` 174 -> 177. Focus 4 holds.
- The default corpus took 10.6 s to generate and is 36,739,827 bytes, all ASCII. It has 20,000 cases, 2,209 error cases (all 6 codes), 3,115 strict cases, and 24 redraws (17 `expect:` and 7 `intermediate:`, all integer-valued 0.0). This matches the plan and ADR-007 ("about one case in a thousand"). U+0130, U+0131, U+01C5 and U+212A do not appear. `suffix` is drawn as `""` 198 times, `~` 196, U+2026 190 and `...` 189.
- `tests/test_fuzz_generator.py`: 8 passed in 4.08 s (Python 3.12.7). The slowest test is 1.34 s, so the default suite is not slowed noticeably.
- In the first 2,000 cases, 1,231 have some astral character in their input, and 501 of those have an astral letter (category L).

## Strengths
- **S7-2 reuse, done properly.** Both replays call the vector runners `checkCase` and `CaseTests.AssertCase`. I checked both runners: they have no skip path and no early return that a fuzz case could fall into. A case needs exactly one of `expect` / `expect_error`, every key is validated, and an error case must throw the port's contexel error with the exact code.
- **The guard is the same strength in both ports.** An empty `CONTEXEL_FUZZ_CASES` counts as unset, and any non-empty `CI` counts as CI, in TS and C# alike. A path that is set but missing or unreadable fails: TS at module load, C# in every Fact. In both ports, a relative path resolves against the repository root, not the working directory, so `working-directory: ts` in the workflows is harmless.
- **The anti-vacuity checks are layered.** The corpus must have at least 1,000 cases. `case_count` and `kind_counts` must agree with the content, ids must be distinct, and at least one error case must exist. Both ports have a canary over the first 300 cases. The Python side pins `outside_envelope` with tests that can fail, including the intermediate-stage 0.0 that a later `select` hides.
- **The generator is deterministic and portable.** It draws only through `random()`, from an int seed. It uses no set or hash ordering (`dict(sorted(...))`), writes `--out` as ASCII bytes, and has ASCII-only source; separator characters are built with `chr()`. A redrawn case keeps its `(seed, index)` derivation, and the `PYTHONHASHSEED` 0 and 1 CLI cross-check is a good touch.
- **The C# adapter fix is minimal and discriminating.** All three new shared cases fail if the adapter drops `suffix`: the default U+2026 gives `abcdefghijab` + U+2026 for each. The C# library default is still exercised by `ParityTests.cs:52/70/208`, which call `TruncateField` without a suffix.
- **Every job that replays has its corpus.** CI: `ts-parity` and `cs-parity`. Release: `ts-test` and `cs-test`, plus `npm-publish` (`npm publish` runs `prepublishOnly`, which is `npm run build && npm test`) and `nuget-publish` (`Test, pack` runs `dotnet test`). No other job runs `npm test` or `dotnet test`: the smoke jobs, `pages.yml` and the Python `test` jobs do not.
- The commits are clean: 7 Conventional Commits of 72 characters or fewer, no trailer, and no private paths in the diff.

## Issues

### Critical (Must Fix)
None.

### Important (Should Fix)

**I1. The U+0130 margin is not new. The branch records it a second time and calls it "not recorded" in public docs.** The plan itself is wrong here (S7-10, and the "new margin" row of its table).
- `docs/adr/002-csharp-parity.md:85-90` has recorded this exact margin since Slice 5 (ruling S5-13, commit e3c4c80). That entry reads "C# `ToLowerInvariant` leaves U+0130 ... unchanged where Python and JavaScript lower-case it to `i` plus U+0307 ... This is older than Slice 5 and is now recorded."
- The branch adds a second bullet at `docs/adr/002-csharp-parity.md:67-69` that says "found by the differential fuzz".
- `CHANGELOG.md:202` says "one margin that was not recorded: C# `rescore` treats U+0130 differently".
- ADR-007 margin 2 (`docs/adr/007-...md:59-61`) does not point to ADR-002.
- The master plan `docs/plans/foundation-hardening.md:127`, already on `main` and outside this diff, makes the same claim.

**Why it matters:** the release notes are public, and they make a false provenance claim. ADR-002's margin list now contains duplicates. Focus 5 asks for exactly this accuracy.

**Fix (documentation only, about 5 lines):**
- Delete the new ADR-002 bullet (:67-69), or fold its new fact into the existing entry at :85: "the differential fuzz measured 31 divergences in 6,000 cases; excluded from its domain (ADR-007)".
- Reword the CHANGELOG to something like: "...and measured one known C# margin (U+0130, recorded in ADR-002), which is now excluded from the domain".
- Add "(recorded in ADR-002 since Slice 5)" to ADR-007 margin 2, and keep it **open**.
- Correct the master plan line in the post-gate master-plan update.
- Related attribution slip: ADR-007 margin 1 (`:56`) cites "ADR-006, Slice 5 ruling S5-8", and the generator docstring (`parity/generate_fuzz.py:22`) cites "the C# tokenizer margin of ADR-006". The astral tokenizer margin is recorded in ADR-002 §7 (`:77-84`). ADR-006 records only that lengths are code points. Cite ADR-002 (S5-8 / S5-13).

**I2. `python -m pip install -e .` in `npm-publish` and `nuget-publish` is unnecessary, and it pulls unpinned PyPI code into OIDC jobs** (`.github/workflows/release.yml:177` and `:227`).
- `pyproject.toml` declares `dependencies = []` and the `hatchling` build backend. The editable install therefore fetches and runs the latest `hatchling` closure, with no hashes, in jobs that hold `id-token: write`. In `npm-publish` that happens before the `NPM_TOKEN` step.
- The generator needs only the repository's own `contexel` on the path.
- This is the security reviewer's F1 / condition C1. From the review side it is also the cleaner build: it is faster and has one less network dependency in a publish job.

**Fix:** drop the install step in those two jobs and run the generator with `env: PYTHONPATH: ${{ github.workspace }}`, or `PYTHONPATH=. python parity/generate_fuzz.py --out parity/fuzz-corpus.json`. Keep the other jobs as they are; their install predates this branch and is needed by `generate_vectors.py`.

**Controller ruling (1) itself is right.** Giving the publish jobs the corpus keeps the gate. The alternatives, `--ignore-scripts` or a guard exemption, would disable a check (§5). Only the install method should change.

### Minor (Nice to Have)
- **M1. ADR-007 margin 3 is incomplete** (`docs/adr/007-...md:62`). It omits U+0131 and U+01C5, which `EXCLUDED` holds (`parity/generate_fuzz.py`, `EXCLUDED`). List all the excluded characters, so the record matches the code. This is a ledger item; fix it together with I1.
- **M2. Locally, C# reports the fuzz as passed when it tested nothing.**
  - `FuzzTests.cs:33-40` returns early, so the three Facts show as Passed: the 623 count is the same with or without the variable. ADR-007 `:39` and CHANGELOG `:197` say "skipped". TypeScript really does skip (`fuzz.test.ts:49`). CI is unaffected, because the guard fails there.
  - Fix: an xunit 2.x `FuzzFactAttribute : FactAttribute` that sets `Skip` in its constructor when both variables are unset (no dependency needed), or reword the docs to say "returns without replaying".
- **M3. ADR-007 `:68` claims more than the plan measured.** It says that with the floor of `truncate_field` changed to 0 "in either port the shared vectors stayed green and 112 fuzz cases failed". The plan (line 50) measured the TypeScript vectors green (681) and 112 fuzz failures in both ports. Green C# vectors under that mutant is not stated. Confirm it against the QA mutation run, or reword to "the TypeScript vectors stayed green and 112 fuzz cases failed in each port".
- **M4. The pinned-digest comment understates its dependence on the canon** (`tests/test_fuzz_generator.py:24-26`, plan S7-8).
  - The digest depends on the canon through the redraw rule. It also depends on it through the S7-6 strip: `make_case` rewrites `input` when the canon does not raise `input.not_mapping`. And it depends on it through "canon raised" redraws.
  - "Change them only with the generator" will mislead whoever changes strict-mode behavior. Reword to: "re-pin when the generator changes, or when a canon change alters a redraw or the not_mapping strip (say so in the commit)".
- **M5. The CI failure and skip messages give no command** (`fuzz.test.ts:46/49`, `FuzzTests.cs:38`). Append `python parity/generate_fuzz.py --out parity/fuzz-corpus.json` and `CONTEXEL_FUZZ_CASES=parity/fuzz-corpus.json`. A contributor who hits the CI failure locally (with `CI` set) then knows what to run.

## Deferred-minor triage (ledger `minor (deferred)` lines)

| Ledger line | Verdict |
|---|---|
| T1: astral-coverage test counts emoji too (`tests/test_fuzz_generator.py` ~87) | **Leave.** The domain test pins letter placement separately. Measured: 501 cases with astral letters in the first 2,000, so tightening the check to `category L` later is a safe one-line change. |
| T1: `as_records` call and the second `outcome()` in `make_case` not wrapped; no-op `except ContexelError: raise`; a canon crash becomes a counted redraw | **Leave.** An unwrapped exception crashes the generator loudly, which fails closed. A canon crash is counted in `_meta.redrawn` and bounded by a test, not hidden. None occurs at the default seed. |
| T1: "no backslash escapes" comment inaccurate; dead counter; private `_pipe` import; usage line omits PYTHONPATH; E501 outside CI lint scope | **Leave.** None affects behavior. Fix the comment if the file is touched for I1 (docstring `:22`). |
| T2: `astral_suffix` case cannot tell code-point from UTF-16 counting; `...` costs 1 token like the default | **Leave.** All three cases still catch the adapter regression they exist for. The case name slightly overclaims; a 4-astral-character suffix would discriminate if ever wanted. |
| T3: corpus parsed at module load; canary `assert.throws(Error)` accepts any Error; index taken by splitting the id | **Leave.** A load failure fails the file. A canary that accepts the wrong Error is only a false pass if `corrupted()` itself throws, and it cannot for these shapes. |
| T4: `ThrowsAny` with `Corrupted()` inside the lambda; corpus parsed 3 times; cast in the catch handler; `Assert.False` double negative | **Leave.** `Corrupted` cannot throw for the corpus shapes, and the 3 parses cost about 6 s in total. |
| T6: ADR-007 margin 3 omits U+0131 and U+01C5 | **Fix before merge** (M1, together with I1). |
| T6: two over-wide lines | **Leave.** |
| T6: ADR-007 margin 2 does not cross-reference ADR-002 | **Fix before merge.** It is part of I1, and the cross-reference is the correction. |

**Controller rulings:**
- (1) Publish jobs generate the corpus: **agree**, change the install method (I2).
- (2) ADR-007's "as built" sentence naming `npm-publish` and `nuget-publish`: **accurate** against release.yml and `ts/package.json` `prepublishOnly`. One nuance: on a `workflow_dispatch` dry run, `npm-publish` runs only `npm pack --dry-run`, which does not trigger `prepublishOnly`. The corpus is generated there but not replayed. See Recommendations.

## Declined to judge
- **No version bump, against the auto-memory rule "bump every commit":** the plan's Global Constraints and the programme's `[Unreleased]` practice are the human's standing call.
- **Fixing the C# U+0130 and astral tokenizer behavior:** a library change is out of scope (S7-10, S5-8). Deciding is the human's.
- **Scheduled multi-seed fuzz (plan open item 2):** not part of this slice.
- **The 60-second target and memory on hosted Windows/macOS runners:** these can be verified only by the first CI run. Local numbers fit comfortably: 10.6 s to generate, and replays of 2.6 s (TS) and 6 s (C#), as reported.
- **Byte identity of the canon's expectations across OSes** (`math.log` in `rescore`): each job generates and replays on the same OS, so it cannot cause a false pass. The existing 3-OS `git diff --exit-code parity/vectors.json` is the standing evidence that the canon does not depend on the OS.
- **Pinned digest stability on Python 3.9 / 3.13:** verified on 3.12 only. The CI `test` matrix (3.9 to 3.13, three OSes) is the evidence on first push.
- **Replays not checking `_meta.format`, the seed or the default size:** CI always regenerates with the defaults, and a hand-crafted corpus is outside the threat model.
- **A stale local corpus from another checkout:** a local ergonomics issue. CI always regenerates.
- **Supply-chain depth, the `.gitignore` anchoring, and leaks in error messages:** the security reviewer's remit (F1 to F3). Only I2 is carried here.
- **Pre-existing `tests/test_doctrine_*` failures:** excluded by the baseline.
- **ruff E501 in `parity/` and `tests/`:** the CI lint scope is `contexel` only.

## Recommendations
1. Apply I1, M1 and I2 in one small follow-up commit: documentation plus 2 workflow lines. No re-measurement is needed. Then confirm M3 against the QA mutation report.
2. On the first push, read the CI timings of `cs-parity` on windows-latest and macos-latest (Review Focus 1). Confirm the pinned-digest test is green on the 3.9 legs.
3. Before the next tag, consider one `workflow_dispatch` dry run of release.yml. It does not run `npm-publish`'s replay, though, so the first real `prepublishOnly` replay happens after PyPI has published. The risk is low (same commit, env and path as `ts-test`), but the human should know about this ordering.
4. Optional: the `FuzzFactAttribute` (M2), and command hints in the guard messages (M5).

## Assessment
**Ready to merge?** With fixes

**Reasoning:** The fuzz itself is sound. It is deterministic, cannot pass vacuously in CI in either port, covers every job that replays, and changes the vectors by exactly the three intended cases. Two things should be fixed first: the public docs claim that the U+0130 margin was unrecorded when ADR-002 has recorded it since Slice 5 (a plan defect, I1), and the publish jobs run an unneeded unpinned PyPI install next to OIDC (I2). Both are a few lines.


---

## Fix wave re-review (after the three gates)

### Finding Verdicts
- **A: ADDRESSED.** In `.github/workflows/release.yml`, the `npm-publish` (steps at ~174-180) and `nuget-publish` (~224-229) jobs no longer have the `python -m pip install -e .` step. `setup-python` is still there. The generate step has a step-level `env: PYTHONPATH: ${{ github.workspace }}`, and the syntax is correct. The job-level `CONTEXEL_FUZZ_CASES` and `permissions: id-token: write` are unchanged.
  - PyYAML parses the file, and the step lists for both jobs are as expected.
  - Nothing new installs from PyPI or npm before the credentials appear. The only package install left is the `npm ci` in npm-publish, which was there before Task 5.
  - The generator import works with only PYTHONPATH set. `parity/generate_fuzz.py:35` does `sys.path.insert(0, <parity dir>)`, and the script directory is also sys.path[0], so `parity_cases` resolves. `contexel` comes from the PYTHONPATH entry. `PYTHONPATH=<repo> python -c "import contexel"` resolved to `<repo>/contexel/__init__.py`, and `generate_fuzz.py --cases 50 --out <scratch>` wrote 50 cases.
  - The fix diff does not touch `ts-test`, `cs-test` or `ci.yml`. Both test jobs still run `pip install -e .`, as intended.
- **B: ADDRESSED.** `.gitignore:19` reads `parity/fuzz-*.json`, under the same comment as before.
  - `git check-ignore -v` matches `parity/fuzz-corpus.json` and `parity/fuzz-seed7.json`. For `parity/vectors.json` it exits 1 (not ignored).
  - `git ls-files parity/` lists only `generate_fuzz.py`, `generate_vectors.py`, `parity_cases.py` and `vectors.json`, so no tracked file is hidden.
- **C1: ADDRESSED.** `tests/test_fuzz_generator.py:58` and `:63` now compare sha256 digests. The comment is at `:57`, and `hashlib` is imported at `:6`.
  - Both original comparisons are converted: the string compare and the bytes-vs-encoded compare. The meaning is the same, since the digests are equal exactly when the byte streams are.
  - No other `dumps` equality is left in the file.
  - I ran the file with `PYTHONPATH=<repo>`: 8 passed in 2.89s.
- **C2: ADDRESSED.** The comment at `tests/test_fuzz_generator.py:26-28` now names both places the digest depends on the canon: the redraw rule, and whether a scalar item is kept (`only_mappings_or_not_mapping_error`, generator `:359-379`).
  - S7-6 is the ruling the slice plan uses for exactly this (`docs/superpowers/plans/2026-11-26-foundation-hardening-s7-differential-fuzz.md:42,48`).
  - `PINNED_DRAWS` and `PINNED_FIRST_300` match a1877f4 byte for byte.
- **C3: ADDRESSED.**
  - **(a) Canary guard.** `FuzzTests.cs:216-218` materializes the first 300 cases and asserts `Count > 0` with a message, matching the TypeScript guard at `ts/test/fuzz.test.ts:90`. I ran it against a scratch corpus with an empty `cases` array: `Failed TheReplayCanFailACorruptedExpectationIsRefused — the corpus has no cases to corrupt (a canary must never pass vacuously)`.
  - **(b) Completeness asserts.** `:182-193` are equivalent to the originals:
    - `(long)meta["case_count"]! == cases.Count`: the cast binds before `==`, and the int widens to long, so this is the same test as the old `Assert.Equal`.
    - The distinct-id count equals the case count, now with its own message, so a duplicate id no longer reads like a count mismatch.
    - The kinds check compares the sorted `key=value` join of both dictionaries. That is equivalent for the identifier-like stage names.
    - `Any(expect_error)` is the same condition as `Assert.Contains`.
    - No condition was weakened.
  - **(c) Unset/CI messages.** `FuzzTests.cs:155-158` and `fuzz.test.ts:444-448` keep the leading text `CONTEXEL_FUZZ_CASES is not set: ...`, and the TypeScript test name is still `the fuzz corpus is configured in CI`. The added command `python parity/generate_fuzz.py --out parity/fuzz-corpus.json` is the same as the CI step, and `CONTEXEL_FUZZ_CASES=parity/fuzz-corpus.json` works because both ports resolve the path against the repo root.
- **D1: ADDRESSED.** The Task 6 duplicate bullet is gone. U+0130 now appears in ADR-002 only in the original bullet (`docs/adr/002-csharp-parity.md:82-87`), which was added in e3c4c80 on 2026-11-22 (Slice 5). The new final sentence, "The differential fuzz (ADR-007) leaves it out of its domain.", is accurate.
- **D2: ADDRESSED.** ADR-007 margin 2 (`:60-64`) says U+0130 is already recorded in ADR-002 item 7 since Slice 5, was not discovered by the fuzz, and is excluded and open. It keeps "31 divergences in 6,000 cases".
- **D3: ADDRESSED.** ADR-007 margin 1 (`:57`) and the generator docstring (`parity/generate_fuzz.py:22`) now cite "ADR-002 item 7, Slice 5 ruling S5-8". The astral bullet does sit under ADR-002 item 7 (`:52`, bullets `:74-80`), and ADR-006 only mentions S5-8 as a plan ruling. Only the docstring changed in the generator.
- **D4: ADDRESSED.** ADR-007 margin 3 (`:65-70`) lists U+0131, U+017F, U+00DF, U+212A, U+212B, U+1E9E, U+03A3, U+03C2 and U+01C5, "with U+0130 above". That is exactly `EXCLUDED` at `parity/generate_fuzz.py:60`. The U+0131/U+01C5 statement (one 6,000-case run, no divergence in either port) is accurate and claims no divergence that was not measured.
- **D5: ADDRESSED.**
  - The CHANGELOG (`:197-204`) now says one gap (the C# adapter, fixed), and that U+0130 and astral letters are margins already recorded in ADR-002.
  - CHANGELOG `:197-199` and ADR-007 `:39-41` both say TypeScript reports a skip and C# returns at once and shows as passed because xunit 2.9.2 has no dynamic skip. The csproj does pin xunit 2.9.2.
  - The source comments agree: `FuzzTests.cs` says "returns at once" and `fuzz.test.ts` says "skipped".
  - A grep of ADR-002, ADR-007, CHANGELOG and the READMEs finds no remaining "found by", "not recorded" or "discover(ed)" claim about U+0130. The one hit is ADR-007's "the fuzz did not discover it".

### New Breakage in the Fix Diff
None at Critical or Important.
- **Minor (cosmetic):** the reworded lines run past the paragraph's wrap width: `CHANGELOG.md:199` (124 chars against about 110) and `docs/adr/007-vector-format-v2-and-differential-fuzz.md:41` (137 chars). The ADR already had a 160-char line at `:46`.
- **Minor (wording):** `CHANGELOG.md:203-204` says the astral margin is one "the fuzz domain excludes". In fact astral letters are still generated in `note`, and only text that `rescore` reads is excluded. ADR-007 margin 1 states this exactly.

Other checks on the fix diff:
- Line endings: the index is LF for all 9 files, and `git diff --stat --ignore-cr-at-eol` equals the plain stat (55+/29-), so there is no end-of-line churn.
- No non-ASCII characters, e-mail addresses or local paths in the added lines.
- No changes under `contexel/`, `ts/src/` or `csharp/Contexel/`, and no version bump.
- No Co-Authored-By trailer: every commit body is empty.
- Commit subjects are 56-66 characters.
- Working tree is clean after my checks.

### Out-of-Scope Observations
- `docs/plans/foundation-hardening.md:127` still says U+0130 is "a margin that was not recorded and now is, in ADR-007 and ADR-002". The slice plan `docs/superpowers/plans/2026-11-26-foundation-hardening-s7-differential-fuzz.md:44` still calls it a "**new margin**". The brief excluded plan files (D7, the controller updates them), so these remain for the controller.
- The how-to command in the messages omits `PYTHONPATH`. It works when `contexel` is installed or editable-installed, which is the normal developer setup. No action needed.

### Verdict
**Fix wave:** All findings addressed, no new Critical/Important breakage.
