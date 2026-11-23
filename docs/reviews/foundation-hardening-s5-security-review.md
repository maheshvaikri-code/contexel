> Filed 2026-11-22 from the Slice 5 review workspace for branch `feat/hardening-s5-stemmer-nfc` (reviewed at head `36c4792`; the fix wave that followed is summarised in section 6). Sanitised: no user name, home or temporary path, e-mail address or agent identifier.

# G5 Security Review - Foundation hardening Slice 5 (stemmer and NFC normalization) @ 36c4792

**Security Reviewer** (fresh-context verifier, G5, holder of the ship veto) - **Date:** 2026-11-22
**Range:** `0b42966..36c4792`. The reviewer read the source and the diff and ran experiments on copies of the repository outside the checkout (Python 3.12 with Unicode 15.0.0, Node 24, .NET 8). The scope was set by the plan's gate 3: `quarantine`'s new `normalize` option as a control, plus `rescore(match="stem")`.

## Decision: VETO on `normalize="nfc"` cost only; lifted by the project owner's recorded acceptance

The option is correct as a control: the default is off and unchanged, opting in never flags less than the default (ruling S5-10), hostile strings never raise, and validation is exact. But its cost is not linear on one hostile input shape, which the plan's gate required ("the normalized copy of each scanned text is linear in its size"). The veto covered only that cost; `match="stem"`, the validation of `normalize` and the widen-only rule passed. The veto lifts when the cost is fixed or the project owner signs an override. **The project owner decided to accept the cost as a documented known limit** (option "accept and document", recorded in the Slice 5 plan as S5-11); the code is unchanged for it.

## 1. H-1 (High): NFC time grows with the square of a combining-mark run, in all three runtimes

**Where:** `contexel/stages.py` (quarantine and the `rescore` `prepare`), `ts/src/stages.ts`, `csharp/Contexel/PyCompat.cs` `NormalizeNfc` (called from `Stages.cs`).
**Cause:** NFC sorts every run of combining marks into canonical order; the runtime normalizers (CPython `unicodedata`, V8/ICU, .NET) do it with an insertion-style sort, quadratic in the run. contexel's own wrapping is linear. The shortcut "skip when the NFC form equals the text" does not help, because NFC really changes this text, and the raw scan misses it (no marker), so the NFC step always runs. A single combining class is linear; the cost needs two classes.
**Reproduction:** one record `"a" + (U+0301 U+0323) * k`:

| Port | marks | `normalize` on |
|---|---|---|
| Python `quarantine` | 128,000 | 5.1 s |
| Python `quarantine` | 256,000 | 19 s |
| TypeScript | 128,000 | 5.7 s |
| TypeScript | 512,000 | 92 s |
| C# | 128,000 | 4.6 s |
| C# | 512,000 | 76 s |

The default path takes milliseconds on the same text (Python: 5.9 ms and 14.5 ms). A hostile retrieved document of about 1 MB could stall the opt-in screen for minutes.
**Reviewer's fix (prototyped, not applied):** cut the text after every 30th consecutive combining mark (the Unicode stream-safe limit) and normalize each piece; every character NFC reorders is a mark, so each sort handles at most 30 marks; `quarantine` scans the raw text first, so it cannot be weaker than the default. Prototype: 512,000 alternating marks in about 68 ms, 2.5 million in 330 ms; identical to exact NFC on short-run text. It needs the same cut in all three ports and both stages, a shared vector and a timing test, so it would make the result differ from exact NFC for runs longer than 30 marks.
**Disposition:** accepted and documented by the project owner (READMEs, changelog known limits, ADR-006 with the figures and this follow-up, the site page and the doc comments of `quarantine` and `rescore`: cap the size of text you do not control). Residual risk: an opt-in option can be made slow by hostile text; the default path is unaffected.

## 2. Information findings

- **I-1:** an existing case-folding difference between ports carries into the NFC widening: `"I" + U+0307 + "GNORE ALL PRIOR PROMPTS"` composes to U+0130, which Python lower-cases to `i` plus U+0307 and TypeScript does not (documented in the README already). It is a widening in one port, not a weakening; no action.
- **I-2:** C# pays one caught exception per record that contains a lone surrogate (about 4 microseconds per record, linear: 100,000 records 531 ms against 94 ms by default); no action.
- **I-3:** a Python `normalize` object whose `__repr__` raises gives `RuntimeError` instead of `ConfigError`; the existing `check_bool` behaves the same; no action.

## 3. Verified, with evidence

1. **The default is off and `normalize=None` is unchanged from base.** By reading the code (the only default-path change is the new parameter and a block guarded by `normalize == "nfc"`) and by comparison of base and head: Python 3 seeds of 20,000 iterations (flag and drop, nested values, six pattern sets including `replace_patterns`): 0 differences; TypeScript 120,000 comparisons: 0 differences; C# 60,000 cases: 0 differences.
2. **With `normalize="nfc"` the screen is never weaker than the default.** The raw scan is the same line as before; the NFC form is scanned only when the raw scan missed and the composed text differs; patterns are never normalized; the built-ins and `replace_patterns` are unchanged. The same 60,000 cases in all three ports: default-hit-and-nfc-miss = 0 in Python, TypeScript and C# (nfc-only hits: 578, 891, 578 respectively: the TypeScript excess is the existing case-folding difference of I-1, present in default mode too). A targeted Python fuzz (markers with combining marks, jamo, surrogates, U+FFFE and U+FFFF, NUL inserted or appended), 200,000 cases: 0 weaker, 13 nfc-only. New false positives: with only the built-ins, NFC adds a hit only for text that already is a marker under case folding; with caller patterns it adds exactly the intended hits (a precomposed pattern found in decomposed text).
3. **Cost against size is linear on the other hostile inputs:** 5 million combining marks of one class, a Hangul jamo run, 5 MB of ASCII plus a trailing mark, a lone surrogate every 2 or 4 characters, U+FFFE every 2 characters, a marker followed by 5 million spaces and a mark. Python at 5 million characters: 334 to 897 ms with `normalize` on against 220 to 492 ms by default; TypeScript 15 to 104 ms; C# 15 to 677 ms. The second scan costs at most 2x. The C# `NormalizeNfc` uses a `StringBuilder` and one `Normalize` call per piece between rejected characters: nothing quadratic. The stemmer is linear (Python 5 million characters, one token: 56 ms; many tokens: 843 ms). Exception: H-1.
4. **Hostile strings never raise.** Lone high and low surrogates, a reversed pair, U+FFFE, U+FFFF, an unassigned code point, NUL, a leading combining mark, 200,001 combining marks, U+10FFFF plus a mark, U+E0001, U+FDD0 plus a mark, through `quarantine` (built-ins, a caller pattern, nested values) and `rescore` (`stem`, `word`, `substring`, string and list queries): 15 of 15 in Python and TypeScript, 16 of 16 in C#. On this platform .NET refuses exactly the surrogates and U+FFFE, which `NormalizeNfc` splits around.
5. **Validation of `normalize` is exact.** Values tried: `"NFC"`, `"nfd"`, `"nfkc"`, `"nfkd"`, `""`, `" nfc"`, `"nfc "`, `"Nfc"`, fullwidth `nfc`, `"nfc\0"`, and in Python and TypeScript numbers, NaN, booleans, lists, tuples, dicts, bytes, boxed strings, a symbol, a function and objects with a throwing `toString`. Every value raised `config.invalid_value` with param `normalize`, on both stages, with records, with `[]`, with an empty or wordless query, before any invalid pattern is reported. `None`/`null`/absent and `"nfc"` are accepted. The message only echoes the caller's own value.
6. **Other:** the stemmer is a pure string function and tokenization uses the existing pattern (no new injection path); no `eval`, `exec`, shell, pickle or unsafe in the added lines; no new dependency (manifests unchanged except the TypeScript test list; imports are standard library); no secret, personal data or private path in the added files, tests, docs or commit messages.

## 4. Role-card sweep

Secrets clean - input boundaries validated (H-1 is the one unbounded cost, accepted) - dependencies: none added - dangerous constructs: none - access control: not applicable - failure posture: errors fail closed.

## 5. Residual risk and sign-off

- **Accepted by the project owner:** H-1 (the NFC cost), documented as a known limit with the bounded variant as a possible later additive change.
- **Accepted, existing:** I-1 (case-folding difference between ports) and the Unicode-version margin listed in ADR-002 and ADR-006.

## 6. After the review

The fix wave (commits `0c4615d` and `e3c4c80`) added the documentation of the accepted cost and the test and vector gaps found by QA; the scoped re-review checked that the documentation never claims linear cost, states that the default path is unaffected and quotes the figures above. The security review's other findings needed no change. The reviewer also left a timing process running in the background during its large-input runs; stopping it was not permitted to the reviewer or to the controller and was left to the project owner.
