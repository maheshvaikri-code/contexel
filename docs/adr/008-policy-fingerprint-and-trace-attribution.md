# ADR-008 — Fingerprint truthfulness and trace drop attribution

**Date:** 2026-11-19 · **Status:** accepted (2026-11-20, Slice 3) · **Deciders:** Chief Architect + human (audit contract change)

## Context
Verified defects: `allowed={"a"}` and `allowed={"b"}` share a fingerprint (sets hash
as their type name); mutating a bound list after construction changes behavior
but not the fingerprint; nested pipelines contribute only `"run"`; a tiktoken
tokenizer is `<lambda>`. In `trace`, a record dropped while some surviving record
never had the id field is reported as not dropped (`dropped_ids == []`),
because survivors lacking the id are assumed to have lost it.
Fingerprints are language-local (ADR-001/002) and stay so.

## Decision
We will snapshot bound containers at `stage()` time and copy the stage list in
`pipeline()`; hash sets by sorted content; give nested pipelines a descriptor
carrying their fingerprint; name tiktoken tokenizers `tiktoken:<encoding|model>`.
A pipeline containing none of these keeps its current fingerprint. In trace, only
`lost = unidentified_out − unidentified_in` unmatched ids are treated as
"survivor lost its id"; the rest are reported dropped. Audit keys are unchanged.

## Per-language scope (Slice 3)
- **Python** implements the decision as written: `stage()` snapshots plain
  `list`/`tuple`/`dict`/`set` values (exact types, any depth; a `frozenset` is
  immutable and returned as it is); a subclass is hashed by its contents at
  build time but not copied, and a custom object stays live, so a later change
  to either alters behavior without altering the fingerprint. A nested
  pipeline carries `("pipeline", (fp,))`; a tiktoken tokenizer is named
  `tiktoken:<encoding|model>`; `disallowed_special=()` is passed so special-token
  literals are counted.
- **TypeScript** snapshots an exact `Array`, plain or null-prototype object and
  `Set` shell (a `Set`'s elements are not copied); a `Set` or `Array` subclass
  stays live; an own `__proto__` key (as `JSON.parse` produces) is kept as an
  own key in the copy; a `Set` is hashed by sorted contents; a pipeline used
  as a stage contributes `pipeline(<fp>)`. No tiktoken exists in this port.
- **C#** cannot snapshot behavior: a stage is a delegate, and the declared
  `Stage.Parameters` exist only to feed the fingerprint, so the fingerprint is
  computed once at construction and a closure over a caller's list can still
  change behavior (documented, not fixable without an API that owns the data).
  Sets are hashed by sorted contents at any depth; a stage built from `inner.Run`
  contributes the inner fingerprint (a lambda wrapper is opaque). No tiktoken.
- **Trace** attribution (`lost`) is identical in all three and pinned by shared
  vectors of kind `trace_dropped_ids`. The rule counts id-less records, so it is
  an approximation in both directions for a black-box stage: one that ADDS
  id-less records can hide up to that many drops (the bound in the decision
  above), and one that both strips an id from a survivor AND drops an id-less
  record can have that survivor reported in `dropped_ids` although it survived
  (the built-in stages never do either). That is deliberate, since a reported
  drop is the safe side of the audit; such a stage should keep its ids.

## Alternatives considered
| Option | Pros | Cons | Why not |
|--------|------|------|---------|
| A (chosen) snapshot at build | O(1) per call; fingerprint can be a plain function attribute | breaks intentional post-build mutation | — |
| B fingerprint at call time | supports mutation | per-call cost; needs a class for `.fingerprint` | cost and API change |
| C leave as is | none | an audit feature that can misattribute policy | defect |
| D id tracking by record lineage | exact | impossible through black-box custom stages | not feasible |

## Consequences
- Positive: two policies cannot silently share an identifier; drops are no longer hidden by id-less records.
- Negative / debt: ambiguity remains when a stage strips ids from survivors (only the bounded `lost` count is absorbed); behavior change for post-build mutation.
- Invalidation triggers: a cross-language canonical fingerprint (roadmap) would supersede the language-local format.
