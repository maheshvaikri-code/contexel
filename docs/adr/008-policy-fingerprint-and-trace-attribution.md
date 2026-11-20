# ADR-008 — Fingerprint truthfulness and trace drop attribution

**Date:** 2026-11-19 · **Status:** proposed · **Deciders:** Chief Architect + human (audit contract change)

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
