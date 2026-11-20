# ADR-004 — allowlist: bool never equals a number

**Date:** 2026-11-19 · **Status:** accepted (implemented in Slice 2 of the foundation-hardening plan) · **Amends:** ADR-001 §4, ADR-002 §5 (`PyEqKey`: True == 1 == 1.0)
**Deciders:** Chief Architect + human (chosen by the human 2026-11-19)

## Context
`allowlist` is the provenance gate, the control the library calls strongest.
Matching used Python equality, so `allowed=[1]` admits `True` and `1.0`
(verified by running it). The ports copied this deliberately. TypeScript cannot
distinguish `1` from `1.0` (one number type), so full type-strictness is not
expressible in all three languages.

## Decision
We will match on a key `(is_bool, value)`: a bool never equals a number; int
and float keep comparing by numeric value in all languages; strings, `None`
and other values are unchanged; unhashable record values still fail closed.
A bare string for `allowed` is one value. The vector `allowlist_bool_int`
changes from `[{v:true},{v:1},{v:1.0}]` to `[{v:1},{v:1.0}]` in all three suites.

## Alternatives considered
| Option | Pros | Cons | Why not |
|--------|------|------|---------|
| A (chosen) bool≠number, int=float | closes the realistic confusion; enforceable in all ports | `1` vs `1.0` still equal | — |
| B full type-strict (int≠float) | strongest | impossible in TS; would split the parity envelope | not portable |
| C keep Python equality | no change | weaker than configured; the stated goal of this work | rejected by the human |

## Consequences
- Positive: `true` can no longer pass an `allowed=[1]` gate.
- Negative: behavior change for anyone relying on `True == 1`; one vector changes; ports' `pyEqKey` split into an allowlist key and the existing equality helper.
- Invalidation triggers: a user need for int-vs-float strictness (would need a TS representation of integer-valued floats).
