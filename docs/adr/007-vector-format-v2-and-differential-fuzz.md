# ADR-007 — Parity vectors v2 and cross-language differential fuzz

**Date:** 2026-11-19 · **Status:** accepted (cases format implemented in Slice 1; differential fuzz implemented in Slice 7) · **Amends:** ADR-001 §2, ADR-002 §2
**Deciders:** Chief Architect + human (fuzz slice approved 2026-11-19)

## Context
`vectors.json` stores expected outputs only. Stage arguments and edge inputs are
hand-copied into the generator, `parity.test.ts` and `ParityTests.cs`, so they can
drift. `merge`, `shaped` and `trace.report` have no vector. The 118k-case and
100k-pair fuzz runs cited in earlier ADRs were ad hoc and are not committed, so
they cannot be re-run.

## Decision
We will add a `cases` array (`{id, stage, args, input, expect | expect_error:{code}}`
and pipeline cases) generated from one Python case table; TypeScript and C#
replay it through one adapter per stage. Legacy sections stay until converted.
We will also add a **seeded differential fuzz**: `parity/generate_fuzz.py` emits
random cases inside the documented parity envelope; CI generates and replays them
in TypeScript and C#. Divergences are fixed or recorded as an ADR margin that
narrows the domain — never filtered silently.

## Alternatives considered
| Option | Pros | Cons | Why not |
|--------|------|------|---------|
| A (chosen) data-driven cases + generated fuzz | one place to add cases; reproducible fuzz; nothing large committed | one adapter per stage per port | — |
| B keep hand-copied vectors | no work | drift stays possible | the defect being fixed |
| C commit a large fuzz corpus | no generation step | repo bloat; stale corpora | regenerate instead |
| D property tests per port | local | not differential — cannot detect cross-language divergence | misses the real risk |

## Consequences
- Positive: adding a case touches only the generator; errors compared by `code`.
- Negative / debt: callable-valued arguments remain hand-written edges; fuzz may surface real port bugs (scope growth is the point).
- Invalidation triggers: fuzz runtime exceeding the CI budget; an envelope too narrow to be meaningful.

## The differential fuzz as built (Slice 7)
`parity/generate_fuzz.py` writes a seeded corpus (default seed 20261126, 20,000 cases, about 37 MB, never
committed) in the `cases` format of `vectors.json`; the Python canon computes every expectation. The
TypeScript (`ts/test/fuzz.test.ts`) and C# (`FuzzTests.cs`) suites replay it through the runners that replay
the shared vectors. `CONTEXEL_FUZZ_CASES` names the corpus file; unset, the replay does nothing locally (in
TypeScript the test is reported as skipped; in C# the three tests return at once and show as passed, because
xunit 2.9.2 has no dynamic skip) and **fails when `CI` is set**, so a job cannot go green by testing nothing. CI and the release workflow
generate the corpus and set the variable in every job that runs the replays: the two parity jobs of
`ci.yml`, and in `release.yml` the TypeScript and C# test jobs and the npm and NuGet publish jobs
(`npm publish` runs `prepublishOnly`, which runs `npm test`, and `nuget-publish` re-runs the C# suite).
The generator draws only from `random.random()`, the one method Python keeps stable, so a seed gives the
same corpus on every Python and operating system; case `i` depends on `(seed, i)` alone, and `python parity/generate_fuzz.py --seed S --show I` prints one case.

**Domain.** The documented parity envelope (ADR-001 4a, ADR-002 3), and in addition: a case whose canon
output contains an integer-valued float at ANY stage (an empty query scores every record 0.0, which TypeScript
serializes as `0` and so counts differently downstream) is redrawn, and every redraw is counted in
`_meta.redrawn` (about one case in a thousand); a scalar or null item in a list of records appears only in
cases that expect `input.not_mapping` (a C# list holds mappings); text uses ASCII, Latin-1, BMP CJK, Hangul
and Cyrillic letters, emoji, combining marks, control characters and quote characters, and records carry
non-string values and wide numbers (down to 5e-324, up to 2^53 - 1) that the text stages read.

**Margins the domain excludes** (each was measured by allowing the character class, then excluded):
1. *Astral letters in text that `rescore` reads* (ADR-002 item 7, Slice 5 ruling S5-8): the C# word tokenizer treats
   a letter outside the BMP differently (135 divergences in 20,000 cases). Astral letters are generated only
   in the field `note`, which `rescore` never reads; every other stage handles them and is fuzzed on them.
2. *U+0130 (capital I with dot above)*: already recorded in ADR-002 item 7 since Slice 5; the fuzz did not
   discover it, it only needed to leave it out. Python and JavaScript lower-case it to `i` and U+0307; .NET's
   `ToLowerInvariant` leaves it. C# `rescore` tokenizes text containing it differently (31 divergences in
   6,000 cases when it was allowed). Excluded from the fuzz domain and **open**: a fix would change C#
   behavior (recorded for the human).
3. *Other case-special characters* (U+0131, U+017F, U+00DF, U+212A, U+212B, U+1E9E, U+03A3, U+03C2 and
   U+01C5, with U+0130 above: the whole of `EXCLUDED` in `parity/generate_fuzz.py`): ADR-001 and ADR-002
   already record that the runtimes' case tables differ for `quarantine`'s case-insensitive matching
   (U+212A against `[A-Z]` diverged once in 20,000 cases in TypeScript). All are excluded as case-special.
   Of these, U+0131 and U+01C5 were allowed in one 6,000-case run and diverged in neither port; they stay
   excluded with the rest.

**Findings fixed.** The C# case adapter did not pass `truncate_field`'s `suffix` argument (the library did);
fixed, with three shared cases. A defect of the kind the fuzz is for: with the budget floor of
`truncate_field` changed from 1 to 0 in either port the shared vectors stayed green and 112 fuzz cases failed.

**Process.** A divergence is either fixed (the fix adds a shared case to `parity/parity_cases.py`, so the
vectors keep it) or recorded here as a margin that narrows the domain, and the generator is narrowed in the
same change. Nothing is filtered silently: redraws are counted and the replays name every divergence.
