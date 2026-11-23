# ADR-006 — rescore: validated `match`, frozen `stem` mode, opt-in NFC

**Date:** 2026-11-19 · **Status:** accepted (2026-11-22, Slice 5) · **Amends:** ADR-001/002 parity margins (Unicode version)
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

## Amendments at G2 (Slice 5 plan, 2026-11-22)
Decisions the design left open, each recorded in the Slice 5 plan as S5-1 to S5-8:
- **The rules are an ordered `if`/`else if` chain whose conditions include the
  length tests**, so when a rule's length condition fails the next rule is tried:
  `ties` (four letters) reaches the plural `s` rule and becomes `tie`; `tied` stays
  `tied`. Only one of `ing` and `ed` is considered, and only once (`feeding`
  becomes `feed`, not `fe`). The authoritative text is `docs/stemmer-rules.md`.
- **Lengths are code points, every comparison is ordinal.** An astral letter
  counts once in all three languages; C# uses `StringComparison.Ordinal` because a
  culture-sensitive `EndsWith` skips ignorable characters (a soft hyphen after
  `tests`). Both are pinned by shared vectors.
- **`stem` is not exported.** `contexel.stem` is the module (a function of the same
  name exported from the package would shadow it), and a documented function is a
  commitment the frozen rule set does not need: the behavior is reachable, and
  pinned, through `rescore(match="stem")`. The function is internal in TypeScript
  and C#. Exporting it later is additive.
- **Stem mode tokenizes the text and stems each token** (rather than searching for
  the stemmed terms): terms are the de-duplicated stems of the query in
  first-occurrence order, a text word counts when its stem is a term, and a
  position is the start of the word in code points.
- **`normalize` accepts exactly `None` and `"nfc"`** (lower-case; `"NFC"`, `"nfd"`
  and `"nfkc"` raise `config.invalid_value`), validated with the other
  configuration, before any work. In `quarantine` the text is scanned as given
  and, when `normalize="nfc"`, also in its NFC form (a record is hit when either
  matches), and the patterns are never normalized.
- **`normalize` in `quarantine` can only widen detection** (found at review during
  execution, ruling S5-10, decided by the project owner). The first design
  replaced the scanned text by its NFC form; NFC composes a combining mark that
  follows the last letter of a marker into that letter (`s` followed by U+0301
  becomes `ś`), so `ignore all previous instructions` with such a mark on the
  final letter was flagged by default and missed with `normalize="nfc"`: opting in
  weakened the screen. The raw text is now always scanned and the NFC form is
  scanned in addition, in all three languages; the shared vectors pin it (case
  `quarantine/normalize_nfc_cannot_hide_a_marker_behind_a_trailing_mark`).
- **C# normalizes around characters its platform rejects.** `string.Normalize`
  throws `ArgumentException` on a lone surrogate and on U+FFFE; Python and
  JavaScript return them unchanged. Such a character has no composition and blocks
  none on either side, so contexel normalizes the runs between them and keeps the
  character: no input raises, and the result equals the other two languages'.
- **The Unicode-version margin** is recorded in ADR-002's margin list: the vectors
  use accented Latin, Hangul, combining marks (including two orders that NFC
  reorders) and an astral compatibility ideograph, none of which changed in the
  Unicode versions in use. Newer characters may normalize differently per runtime.
