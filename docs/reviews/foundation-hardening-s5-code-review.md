> Filed 2026-11-22 from the Slice 5 review workspace for branch `feat/hardening-s5-stemmer-nfc` (per-task reviews on the task commits; G4 whole-branch review at head `36c4792`; scoped re-review of the fix wave at head `e3c4c80`). Sanitised: no user name, home or temporary path, e-mail address or agent identifier.

# G4 Code Review - Foundation hardening Slice 5 (stemmer and NFC normalization)

**Plan:** `docs/superpowers/plans/2026-11-22-foundation-hardening-s5-stemmer-nfc.md` - **Brief:** ACs 7, 16, 17, 18, 18a, 18b and 34 of `docs/briefs/foundation-hardening.md` - **ADRs:** 006 (accepted and amended by this slice), 002 (margin list amended)
**Range:** `0b42966` (main, Slice 4 merged and the Slice 5 plan merged) to the head of the branch: six task commits (`4fe03e2`, `1c6bfc4`, `fd3ddab`, `9d3ad09`, `5995ab0`, `36c4792`), one per-task fix commit (`96604ac`), the fix wave (`0c4615d`, `e3c4c80`) and a comment-fix commit that followed the re-review.

## Outcome

**Ready to merge: yes, after the fix wave, which is done.** The whole-branch review found no Critical finding and no defect in the observable behavior of any of the three ports. It confirmed that no existing behavior changed and that the three ports agree. It reported one Important finding (the quadratic cost of NFC on a long run of combining marks), which the project owner decided to accept as a documented known limit, and nine Minor items and seven nits, which the fix wave applied. The scoped re-review of the fix wave found every finding addressed and one Minor comment error, corrected afterwards.

## 1. How the work was reviewed

| Gate | Who | Result |
|---|---|---|
| Per-task review (spec compliance and quality), tasks 1 to 6 | fresh reviewers, one per task | Tasks 1, 3, 4, 5, 6 approved first time (Minor findings deferred); Task 2 needed one fix round (1 Important, found by the reviewer and reproduced by the controller) |
| G4 whole-branch review at `36c4792` | most capable model, read the plan, the brief, the ledger and the full diff | Ship after fixes: 0 Critical, 1 Important, 9 Minor, 7 Nit |
| G5 QA (mutation, differential) | see `docs/qa/foundation-hardening-s5-qa.md` | Pass with findings: 151 mutants; the surviving ones were test gaps, closed by the fix wave |
| G5 security | see `docs/reviews/foundation-hardening-s5-security-review.md` | Veto on the NFC cost only; lifted by the project owner's recorded acceptance |
| Fix wave, then one scoped re-review at `e3c4c80` | most capable model | All findings addressed; one Minor comment error, fixed afterwards |

The controller checked every task itself before dispatching its review: the changed files were compared with the plan's code blocks by a replay tool (deviations only where a ruling required them), the three suites were run, the commit was inspected (author, subject length, trailers, privacy) and the diff of the source files was read.

## 2. Per-task review results

| Task | Commit | Result | Findings |
|---|---|---|---|
| 1 Python stemmer and rule table | `4fe03e2` | approved, no Important | 5 Minor deferred (undoubling outcome undocumented; doc describes ports and vectors not yet written; a comment; a silent-skip guard; no test pins that `stem` is not exported) |
| 2 Python `rescore` stem mode and `normalize` | `1c6bfc4`, fix `96604ac` | needs fixes, then approved | **1 Important** (see below), 6 Minor deferred |
| 3 TypeScript port | `fd3ddab` | approved, no Important | differential fuzz of the stemmer against Python: 200,000 words, 0 mismatches; 2 Minor |
| 4 C# port | `9d3ad09` | approved, no Important | 4 Minor (no XML doc on `Rescore`, a test name, a weak plan-mandated assertion, "null" versus "None" in a message) |
| 5 shared vectors | `5995ab0` | approved, no Important | 4 Minor (null runner tests prove acceptance only, the Python `stem` runner ignores args, 169 distinct words in 181 pairs, no quarantine empty-input error case) |
| 6 documentation | `36c4792` | approved, no Important | 8 Minor (wording of the changelog and READMEs, ADR-006 lead-in, ADR-002 lacks the astral margin, site paragraph) |

**The Important finding of Task 2 (ruling S5-10).** The plan specified that `quarantine(normalize="nfc")` replaces the scanned text by its NFC form. The reviewer showed, and the controller reproduced, that NFC composes a combining mark that follows the last letter of a marker into that letter (`s` followed by U+0301 becomes one character), so `ignore all previous instruction` plus `s` plus U+0301 was flagged by default and missed with `normalize="nfc"`: opting in weakened the screen. Because it was a security tradeoff and a change of an agreed contract, it went to the project owner, who ruled **widen-only**: the raw scanned text is scanned first, the NFC form is scanned in addition, a record is hit when either matches, and the patterns are never normalized. It was fixed in all three ports, pinned by eight regression tests per language and a shared vector, and recorded in the plan's "Amendments at execution" and in ADR-006.

## 3. G4 whole-branch review at `36c4792`

**Verdict: ship after fixes.** Verified clean by the reviewer (with evidence): the suites (Python 831, TypeScript 669, C# 608, 0 warnings); the vectors regenerate byte-identically, the 130 pre-slice cases and every other section are unchanged (the vectors diff removes exactly one line, the case count); defaults and signatures are backward compatible (new trailing optional parameters); the stemmer matches `docs/stemmer-rules.md` rule for rule in all three ports (60,000-word fuzz: 0 mismatches); the order of the validation checks is identical in all three ports; widen-only holds in all three; `stem` is exported by none; hygiene (conventional commits, no trailer, no private data, no version bump).

### Findings and disposition

| # | Severity | Finding | Disposition |
|---|---|---|---|
| I-1 | Important | `normalize="nfc"` takes time that grows with the square of a long run of combining marks of two combining classes, in all three runtimes (the runtimes' own NFC; contexel's wrapping is linear). Python `quarantine`: 128,000 marks 5.1 s, 256,000 marks 19 s; Node 128,000 marks 5.7 s, 512,000 marks 92 s; C# 128,000 marks 4.6 s, 512,000 marks 76 s; the default path takes milliseconds. | **Decided by the project owner at the G5 gate: accepted and documented** (READMEs, changelog, ADR-006, site, doc comments); no code change. A bounded variant (cut after every 30th consecutive combining mark) is recorded as a possible additive follow-up |
| M-1 | Minor | The undoubling outcome (`added` and `adding` become `ad`, `egged` becomes `eg`, `died` stays while `die` and `dies` stay) was not in the Known limits | Fixed: rows and a bullet in `docs/stemmer-rules.md`, executed by the doc test. Changing the rule would be a plan change for the owner; none was requested |
| M-2 | Minor (must fix) | The plan file still stated the superseded quarantine rule and had no execution amendments | Fixed: "Amendments at execution" (S5-10 to S5-14), pointers at S5-5 and Review Focus 5 |
| M-3 | Minor | The changelog said precomposed and decomposed spellings "match" for `quarantine` too | Fixed: split into a `rescore` and a `quarantine` sentence |
| M-4 | Minor | The Python README said C# normalizes around a lone surrogate "as Python and JavaScript do" | Fixed |
| M-5 | Minor | The reasoning "has no composition and blocks none" is wrong (a lone surrogate or U+FFFE is a starter that composes with nothing, so NFC never combines or reorders across it) | Fixed in the C# comment, ADR-006 and the plan |
| M-6 | Minor | ADR-002's margin list lacked the C# astral-letter word-pattern margin | Fixed |
| M-7 | Minor | Public C# `Rescore` had no XML doc for `match` and `normalize` | Fixed (0 warnings) |
| M-8 | Minor | The new optional C# parameters are source-compatible but not binary-compatible | Ruling by the controller: keep the signatures, add a changelog line telling C# consumers to recompile |
| M-9 | Minor (older than the slice) | C# `ToLowerInvariant` leaves U+0130 unchanged where Python and JavaScript lower-case it to `i` plus U+0307 | Recorded in ADR-002's margin list; no behavior change |
| N-1 to N-7 | Nit | "at least three code points"; ADR-006 lead-in; README rule list; site quarantine paragraph; "built-in markers are unaffected" wording; a test comment; long lines | Fixed, except N-3 and N-7 (left) |

Deferred minors from the task reviews were triaged by the reviewer: fixed in the fix wave where they were cheap and tied to a finding (the S5-1 pin test, the empty-records validation test, the comment), left where the plan mandates the wording or strength.

## 4. Scoped re-review of the fix wave (`36c4792..e3c4c80`)

All findings were verdicted **addressed**, each checked by execution: removing any one of the 17 undoubling letters from the stemmer's list makes the new vector fail in Python (all 17 tried) and in TypeScript and C# (two letters each); a stemmer that strips `ing` and then `ed` again fails in all three languages; the mutants for a list query not normalized, NFC applied after lower-casing, NFKC instead of NFC (in `rescore` and in `quarantine`), validation after the records loop or skipped for empty records, and stem terms not de-duplicated are now killed. The source changes of the wave are comments and doc comments only; the 167 pre-existing vector cases are identical by id and content; the documented NFC cost does not claim linear cost anywhere and the quoted figures equal the security review's.

One Minor was reported: a comment in `parity/parity_cases.py` described U+1E97 wrongly (the expected values of the case are correct). Two smaller leftovers were noted (the same "three or four code points" comment in a TypeScript test, and the doc comments saying "alternating" runs where the cost is broader). All three were corrected in a comment-only commit after the re-review.

## 5. Residual items (not defects)

- The stemmer is frozen from its first release. The undoubling outcome (`added` becomes `ad`) is documented; changing the rule is a decision for the project owner before the first release.
- The C# astral-letter word-pattern margin (a word is split at a letter outside the Basic Multilingual Plane) and the C# U+0130 lower-casing margin are documented, not fixed. A later slice can add an explicit code-point tokenizer.
- The NFC cost is accepted and documented; the bounded variant is a prototyped, additive follow-up.
- Verified on one machine (Windows) only: the first three-operating-system CI run of the branch is the evidence for Linux and macOS, including the .NET normalizer there and the Unicode-version margin.
