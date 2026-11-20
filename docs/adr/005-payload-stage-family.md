# ADR-005 — Non-record payloads: `as_records`, `split`, `join`

**Date:** 2026-11-19 · **Status:** proposed · **Deciders:** Chief Architect + human (public API addition)

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
