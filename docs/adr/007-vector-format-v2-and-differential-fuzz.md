# ADR-007 — Parity vectors v2 and cross-language differential fuzz

**Date:** 2026-11-19 · **Status:** proposed · **Amends:** ADR-001 §2, ADR-002 §2
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
