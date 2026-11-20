# ADR-003 — Typed errors, config-vs-shape split, ambient strict mode

**Date:** 2026-11-19 · **Status:** accepted (implemented in Slice 2 of the foundation-hardening plan)
**Deciders:** Chief Architect + human (public contract change, §5)

## Context
Misconfiguration and malformed input fail silently or with accidental
exceptions (`rescore(match="stem")` runs substring mode; `select("path", ["x"])`
returns `[{}, {}, {}, {}]`; `max_tokens=None` raises a raw `TypeError`). Only
`quarantine` raises typed `ValueError`s, and only for configuration. Existing
callers and tests rely on `ValueError`/`TypeError`/`ArgumentException`
(Python tests use `pytest.raises(ValueError)`; C# tests use
`Assert.Throws<ArgumentException>`).

## Decision
We will add `ContexelError` with `ConfigError` and `InputShapeError`, each
carrying a stable `code` (the cross-language contract; messages are not),
subclassing what each language already raises. **Configuration errors always
raise; data-shape errors raise only in an opt-in strict mode for legacy
stages, and always for the new stages.** Strict is an ambient context flag, also
settable via `pipeline(strict=True)` / `shaped(strict=True)`, which enter it
inside their own run so it holds on threads. Strict never alters a successful
result and is not part of the fingerprint. Two shape errors are always raised,
strict mode or not: `input.field_conflict` (carrying on would destroy data) and
`quarantine`'s `input.not_mapping` (a screen that skips an item it cannot read
would keep the attack).

## Alternatives considered
| Option | Pros | Cons | Why not |
|--------|------|------|---------|
| A (chosen) ambient flag + pipeline/shaped sugar | one switch; works with direct stage calls; thread-safe via sugar | ambient state; bare form not inherited by threads (documented) | — |
| B `strict=` kwarg on every stage | explicit, no ambient state | 9 signatures × 3 languages; nobody repeats it, so unused | defeats the purpose |
| C pipeline-level only | simple | direct stage calls and `@shaped` boundary unprotected | gaps where garbage originates |
| D always strict (break) | strongest | breaks callers relying on lenient shapes | violates byte-identical-valid-output |
| E one flat exception | trivial | callers cannot tell config from data errors | poor error taxonomy |

## Consequences
- Positive: misconfiguration cannot hide; `catch` clauses for the shape errors
  (and C# `catch (ArgumentException)`) keep working; vectors can assert
  `expect_error.code` across languages.
- Negative / debt accepted: C# exact-type test assertions must change to
  `ThrowsAny`; a few raw `TypeError`s become `ConfigError` (a `ValueError`), so
  an `except TypeError` no longer catches those configuration mistakes, and a bad
  `quarantine` regex raises `ConfigError` instead of `re.error` (in C#, a handler
  for `RegexParseException` no longer sees it; in TypeScript, a bad regex used to
  throw a `SyntaxError` and a wrong-typed or `null` argument a raw `TypeError`,
  and `ConfigError` extends only `Error`, so `instanceof SyntaxError` and
  `instanceof TypeError` no longer match: catch `ContexelError` or
  `ConfigError`).
- Known per-language difference: C# `fields: null` (`quarantine`, `rescore`)
  still means "use the default fields", because C# cannot tell an omitted
  optional argument from an explicit `null` without changing the public API to
  overloads, and it is left as is to avoid changing the public API; Python and
  TypeScript raise `config.invalid_value`.
- Invalidation triggers: a language where subclassing the platform's error type
  is impossible; evidence that users want strict-by-default.
