> Filed 2026-11-22 from the Slice 5 review workspace for branch `feat/hardening-s5-stemmer-nfc` (QA ran on head `36c4792`, before the fix wave; the effect of the fix wave is in section 7). Sanitised: no user name, home or temporary path, e-mail address or agent identifier.

# G5 QA Report - Foundation hardening Slice 5 (stemmer and NFC normalization) @ 36c4792

**QA Engineer** (fresh-context verifier, G5) - **Date:** 2026-11-22
**Build under test:** branch `feat/hardening-s5-stemmer-nfc`, head `36c4792` (base `0b42966` = main). Every mutant ran in a fresh `git archive` copy under `<scratch>`, applied by exact-count match and re-read from disk, with `python -B` and `__pycache__` purged.

## Verdict

**G5 QA: PASS WITH FINDINGS.** Every acceptance criterion in scope (7, 16, 17, 18, 18a under ruling S5-10, 18b, 34) was met when executed, in all three languages; the randomized differential found no new divergence; every hostile input raised nothing except `ConfigError`. Mutation testing did not fully pass: several mutants survived, each proven non-equivalent with a concrete input. They were gaps in the tests and vectors, not wrong outputs on the code, and the fix wave closed them. One finding (F1, the NFC cost) was a Doctrine section 5 escalation and was decided by the project owner.

## 1. Baseline (pristine copy)

Python 831 passed (including the 6 tests in `reference_agent/`); TypeScript 669 pass; C# 608 passed; the committed vectors blob regenerates to the same hash twice (SHA-1 `5491bf29ee65bb0e5d5f3c539d98d4b851bc74a4`, 65606 bytes); ruff, mypy (10 source files), the site check and the version check (0.1.17) pass; tree clean, 0 co-author trailers, longest subject 64 characters.

## 2. Mutation testing (151 mutants)

Totals: Python 59 (39 killed, 20 survived), TypeScript 41 (32 killed, 9 survived, 1 equivalent), C# 42 (36 killed, 6 survived), README example mutants 9 (9 killed).

**Killed** (representative killer): the short-word limit `<= 3` to `<= 2` (`stem/short_words_unchanged`); the `ies` and `ied` thresholds shifted both ways (`stem/plural_ies_and_ied`); the base length `>= 3` to `>= 2` and the final-`e` length `> 3` to `> 2` (`stem/short_or_vowelless_base`, `stem/documented_limits`); every rule removed (`sses`, `ied`, the `us` and `is` exemptions, the vowel test, the undoubling, the final `e`) in all three languages; `l`, `s` or `z` added to the undoubling list; lengths counted in UTF-16 units at each site (TypeScript `.length`, C# `string.Length`) and a culture-sensitive `EndsWith` in C# (`stem/non_ascii_and_astral_code_points`, `stem/case_is_not_folded_and_ignorable_characters_count`); in `rescore` stem mode the query or the text not stemmed, the membership test keyed on the unstemmed word, the position at the end of the token or in UTF-16 units (`rescore/stem_window_counts_code_points`); NFC applied to the patterns, nested values not normalized, `"NFC"` or any string accepted, validation after the early return in `rescore`, quarantine ignoring `normalize` (the vectors `quarantine/normalize_*`, `rescore/normalize_uppercase_is_not_a_value`); **the S5-10 regression (quarantine scanning only the NFC form) in all three languages** (`quarantine/normalize_nfc_cannot_hide_a_marker_behind_a_trailing_mark`); the C# lone-surrogate and U+FFFE guards (`NormalizeNfcPassesLoneSurrogatesAndU_FFFEThrough`). The mutant that removes the term-membership test in TypeScript is equivalent (a non-term row adds an IDF of 0 and the proximity loop walks the terms only).

**Survived** (non-equivalent; witness on pristine code and on the mutant):

| Mutant | Languages | Witness |
|---|---|---|
| one letter removed from the undoubling list (b c d h j k m q r v w x) | all | `rubbing` rub to rubb; `adding` ad to add; `swimming` swim to swimm; `barred` bar to barr; `revving` rev to revv; `trekking` trek to trekk |
| `ing` and `ed` both stripped (the once-only choice broken) | all | `proceeding` proceed to proc; `speeding` speed to spe; `embedding` embed to emb |
| stem terms not de-duplicated | Python, TypeScript (C# died on a duplicate key) | query `parse value parsing values`: the proximity bonus is counted twice |
| list query not normalized | all | a list query with a decomposed spelling scores 0 instead of matching |
| NFC applied after lower-casing | all | `T` + U+0308 against a query of U+1E97: the order changes the score (125 base-plus-mark pairs commute differently) |
| `quarantine` normalize validated per record (empty records skip it) | all | `quarantine([], normalize="NFC")` returns `[]` instead of raising |
| NFKC instead of NFC (rescore and quarantine) | all | the ligature U+FB01 against `file`; a fullwidth marker flagged |

## 3. Randomized differential (scratch generator; Python canon against TypeScript and C#, canonical JSON, numbers compared as floats)

Per seed 20,000 stem words, 3,000 `rescore` cases (the three `match` modes, `normalize` on and off, string and list queries, NFC and NFD mixes, Hangul, mark orders, emoji runs, the 80-character window) and 1,500 `quarantine` cases (flag mode, optional and replacing patterns, nested values, a combining mark after the last letter of a built-in marker). Sanity checks (a 1e-6 score change, a flipped flag, an altered stem) were detected.

| Seed group | TypeScript stem / rescore / quarantine | C# stem / rescore / quarantine |
|---|---|---|
| 11 to 16 (no astral letters; emoji kept) | 0 / 0 / 0 on every seed | 0 / 0 / 0 on every seed |
| 3 to 7 (astral letters) | 0 / 0 / 0 on every seed | 0 / 642 to 703 per seed / 0 |

Every C# `rescore` mismatch is in a case that contains an astral letter; with those letters replaced by a letter of the Basic Multilingual Plane the mismatches drop to 0. Minimal reproduction: `a` + U+1D49C + `b` scores 0.277259 in Python and TypeScript and 0.901091 in C#, which splits the word. This is the documented margin S5-8 (b); nothing new appeared.

## 4. Adversarial probes (by execution)

- Lone high and low surrogates, U+FFFE (including in the middle of a composition), a high surrogate followed by a mark and U+FFFF with `normalize`, in all three match modes and in `quarantine`: nothing raises; TypeScript matches Python on 54 of 54 probes; C# matches on all scores and flags. The stemmer on words with lone surrogates gives the same result in all three languages.
- Bad `normalize` values (a list, `1`, `True`, `0.0`, bytes, `""`, `"NFC"`, `"nfkc"`, `" nfc"`, `"nfd"`; TypeScript also `{}`): always `config.invalid_value` naming `normalize`, also with `records=[]` and with a wordless query. C# takes `string?`, so non-string values do not compile. Bad `match` values (`STEM`, `stems`, `""`, `None`, `lemma`) raise `config.invalid_value` naming `match`.
- `match="stem"` with `""`, `"   "`, `[]`, `["", "  "]` and `"!!! ???"`: every score is 0.0 with no raise; a list query gives one term per stem.
- A run of 100,000 combining acutes after one letter: linear and fast in all three languages.
- **A run of combining marks of two alternating classes (U+0301 class 230 and U+0323 class 220): quadratic in all three runtimes (F1).** Python: `unicodedata.normalize` alone 1.76 s at 100,000 marks, 7.48 s at 200,000, 29.5 s at 400,000; `quarantine(normalize="nfc")` 30 s at 400,000 against 0.017 s by default. Node: `rescore` 2.5 s, 10.3 s, 41 s. .NET: 2.7 s, 10.8 s, 43 to 47 s. The same 400,000 characters split into short sequences take 0.014 s.
- 5 MB of ordinary mixed NFC and NFD text: roughly linear (Python 1 MB to 5 MB: `rescore` 0.18 s to 1.1 s; Node 0.05 s to 0.24 s; .NET 0.11 s to 0.64 s).

## 5. Acceptance criteria (by execution)

| AC | Evidence | Result |
|---|---|---|
| 7 | The `match` values above raise `config.invalid_value`; `stem` is valid in all three languages | Met |
| 16 | The vectors diff removes one line only (the case count); the first 130 cases and every other section are identical to main; the golden fingerprints test passes (16 tests); full suites green | Met |
| 17 | In all three languages stem mode scores `parse`, `parsing`, `parsed`, `parses` equally (word mode matches only the exact word); `values` matches `value`; short words unchanged; `""`, digits, symbols, NUL, emoji, a 10,004-character word and a soft hyphen never raise or grow; 220,000 differential words agree | Met |
| 18 | `docs/stemmer-rules.md` committed; 181 pairs (169 distinct words) in 14 groups replayed by all three suites | Met |
| 18a | NFC and NFD `cafe` with an accent score equal with `normalize="nfc"` (0.188001) and apart by default (0.392332, 0) in all three; unknown values raise; quarantine checked against S5-10 (widen-only), which supersedes the brief's wording | Met (under S5-10) |
| 18b | Vectors for NFC and NFD Latin, Hangul, an astral compatibility ideograph, mark order, NFC then stem and the trailing-mark case; the Unicode-version margin in ADR-002 and ADR-006 | Met |
| 34 | The changelog records that `"stem"` is now a real mode; all 9 README mutants (expected output and example code, three READMEs) are killed; Python executes the README source, C# compiles a marker-delimited copy byte-tied to the README | Met |

## 6. Findings

- **F1 (Major, security-relevant, section 5 escalation): `normalize="nfc"` is quadratic on a long run of combining marks of alternating classes in all three runtimes.** A 400 KB snippet costs 30 to 47 s of CPU in `quarantine(normalize="nfc")`; the default takes milliseconds. **Decided by the project owner: accepted and documented as a known limit** (see `docs/reviews/foundation-hardening-s5-security-review.md`, H-1; plan ruling S5-11). The bounded-run variant is a possible later additive change.
- **F2 (Major): parts of the frozen stemmer were not pinned by any vector or test.** 12 of the 17 undoubling letters and the once-only `ing`/`ed` rule. **Fixed** by the fix wave (two new stem groups, 34 undoubling words covering both suffixes of every letter, and a structural test that fails if the group loses a letter).
- **F3 (Major): `normalize` gaps in all three languages.** A list query never shown to be normalized; the NFC-before-lower-casing order not pinned; NFC not distinguished from NFKC; `quarantine([], normalize="NFC")` raising untested. **Fixed** by four shared cases and an empty-records test in each language.
- **F4 (Minor): de-duplication of stem terms unpinned in Python and TypeScript.** **Fixed** by a shared case.

Notes without action: the TypeScript membership mutant is equivalent; the C# astral-letter margin was re-confirmed and is documented; the brief's AC 18a wording for quarantine is superseded by S5-10 and the behavior matches S5-10.

## 7. After the fix wave

The controller's checks after the fix wave (`0c4615d`, `e3c4c80`): Python 841 passed, TypeScript 678 pass, C# 617 passed (0 warnings); the vectors regenerate identically (174 cases, 223 stem pairs in 16 groups); the 167 earlier cases are identical by id and content and every other vector section is unchanged; ruff, mypy, the site check and the version check pass. The scoped re-review re-ran the survivors of F2, F3 and F4 as mutants on fresh copies and found each now killed (all 17 undoubling letters in Python, two letters each in TypeScript and C#; the `ing`-then-`ed` mutant in all three).
