# ADR-005 — Non-record payloads: `as_records`, `split`, `join`

**Date:** 2026-11-19 · **Status:** accepted (2026-11-21, Slice 4) · **Deciders:** Chief Architect + human (public API addition)

## Context
Stages require "a list of mappings". Non-coding agents mostly receive text: logs,
web pages, plain strings, nested JSON. Python and TypeScript are lenient at
runtime; C# hard-codes `List<Dictionary<string, object?>>` in every public
signature. Every stage except `dedupe(key=None)` and `trim_to_budget` needs a
field to act on.

## Decision
We will keep "a record is a mapping" and add a three-stage family: `as_records`
(on-ramp: str / mapping / list → records), `split` (records → chunk records by
lines, paragraphs, or code-point size, lossless, with code-point offsets and
parent fields preserved), `join` (off-ramp: records → str). New stages validate
shape always. Boundaries are explicit and language-independent: lines end after
`"\n"` only; paragraphs after `(?:\r?\n){2,}`; sizes and offsets in code points.

## Alternatives considered
| Option | Pros | Cons | Why not |
|--------|------|------|---------|
| A (chosen) chunk + adapt | ~3 stages; C# signatures unchanged; all stages reused | callers do one conversion step | — |
| B item-generic stages | no conversion step | 27 signature changes, C# rewrite, byte-identity re-proof per stage | cost and risk |
| C Python + TS only | fast | breaks the three-registry parity contract | CI could not publish all three |
| D tokenizer-sized chunks | better budget fit | needs a cross-language tokenizer; tiktoken is Python-only | not portable now |

## Consequences
- Positive: logs and pages flow through dedupe/rescore/rank/trim unchanged.
- Negative / debt: `rank` loses reading order (docs show re-ranking by `chunk.start`); no overlap windows; an empty text record vanishes on `split`.
- Invalidation triggers: a user need for overlap or token-sized chunks; a portable tokenizer.

## Amendments at G2 (Slice 4 plan, 2026-11-21)
Decisions the design left open, each recorded in the Slice 4 plan as S4-1 to S4-8:
- **Ramps stay outside `pipeline`** (S4-1). `as_records` takes a non-list and
  `join` returns a string; a pipeline hands every stage a list, TypeScript and C#
  type it `Records -> Records`, and a strict pipeline rejects a stage that returns
  a non-list. They are called around a pipeline, as `merge` is.
- **Shape is checked in every mode, and before the configuration** (S4-2), through
  an internal `always` option of the existing strict wrapper.
- **A string-valued parent that already has `into` raises `input.field_conflict`,
  even when its text is empty; a record passed through (its field is not a
  string) is never checked** (S4-3).
- **`split` is attributed exactly under `trace`** (S4-4). Found while planning: the
  Slice 3 rule (`lost = max(0, unidentified_out - unidentified_in)`) read the
  id-less chunks of an expanded id-less record as ids lost by survivors and hid a
  real drop (ADR-008). `split` never removes an id, so it declares `keeps_ids`
  and `lost` is 0 for it.
- **"Mapping" is per language** (S4-5): `Mapping` in Python, a plain object in
  TypeScript, `Dictionary<string, object?>` in C#.
