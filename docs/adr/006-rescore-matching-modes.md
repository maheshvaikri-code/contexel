# ADR-006 — rescore: validated `match`, frozen `stem` mode, opt-in NFC

**Date:** 2026-11-19 · **Status:** proposed · **Amends:** ADR-001/002 parity margins (Unicode version)
**Deciders:** Chief Architect + human (public API addition)

## Context
`rescore` is exact-word only ("parsing" does not match "parse"). Any unknown
`match` value silently becomes substring mode (verified: `match="stem"`
returned 0.115). NFC and NFD `café` score 0.115 vs 0 (verified). The result
must be byte-identical in three languages, so a rule set must be small and
specified exactly.

## Decision
We will (1) validate `match ∈ {word, substring, stem}` (config error otherwise);
(2) add `match="stem"` using a small, **frozen**, ordered suffix-rule set
(`sses`, `ies`, `ied`, plural `s`, `ing`/`ed` with a vowel-bearing base of ≥ 3
code points and consonant undoubling, final `e`), English only, specified in
the design and pinned by ≥ 100 vector pairs; improvements ship under a **new
mode name**, never by editing `stem`; (3) add `normalize ∈ {None, "nfc"}` to
`rescore` and `quarantine`, applied before lower-casing, default off.

## Alternatives considered
| Option | Pros | Cons | Why not |
|--------|------|------|---------|
| A (chosen) small frozen stemmer | auditable; portable; 16/16 prototype families unify | English-only; known over/under-stems | — |
| B Porter | standard | ~300 lines of subtle rules ×3 ports; divergence risk | parity cost |
| C caller `normalizer=` hook | flexible | cannot be pinned by a vector; fingerprint sees only a name | breaks "same policy, same output" |
| D no stemming | zero risk | leaves the main critique to documentation | rejected by the human |
| E `nfkc` instead of `nfc` | catches fullwidth look-alikes | wider behavior; not requested | possible later extension |

## Consequences
- Positive: recall on inflected queries; default output unchanged.
- Negative / debt: stemmer limits (`configure`≠`config`, `speed`→`spe`, `news`→`new`); NFC depends on each runtime's Unicode database — vectors restricted to stable ranges.
- Invalidation triggers: non-English use; evidence the stemmer harms precision on a real corpus (publish under a new mode).
