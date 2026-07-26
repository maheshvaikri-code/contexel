# Brief — contexel as a Context Shaping Plane

**Source:** the human's readiness audit, 2026-07-26. Verdict accepted:
suitable for an internal pilot, not yet an enterprise-critical dependency.
The target state is a governed **context shaping plane**: async-capable,
tenant-isolated, audit-traceable, exactly-accounted, provenance-attested —
with its non-goals (injection defense) stated as threat model, not silence.

## Gap register → disposition

| # | Gap (audit finding) | Disposition |
|---|---------------------|-------------|
| 1 | Alpha classifier; same-day release history; no adoption evidence | Time + honesty. Stays Alpha until real external adoption; no cosmetic reclassification. |
| 2 | `@shaped` synchronous — async tool → `TypeError: 'coroutine' object is not iterable` | **Fix now**: async-aware `shaped` (await, then shape). |
| 3 | Tokenizer/serializer defaults process-global — unsafe for concurrent tenants | **Fix now**: `tokens.scoped(...)` contextvar overlay (per-task/tenant isolation); process-global setters retained for single-tenant compatibility. Resolution order: explicit arg → scoped context → process default → built-in. |
| 4 | 4-char estimate inadequate for hard limits (−29% JSON) | **Improve now**: `use_tiktoken(model=...)` (model-specific encodings) + documentation stating exact tokenizers are required for hard limits. The estimator remains for soft budgeting only. |
| 5 | Traces lack policy version/hash, dropped-record IDs, removal reasons | **Fix now**: pipeline fingerprints (stable policy hash recorded per traced run), `trace(id_field=...)` records per-stage dropped record IDs (reason = stage), `Trace.audit()` emits the governance record. Protected-field assertions: roadmap (needs schema contracts). |
| 6 | Not an injection defense — adversarial text outranked legitimate records by matching more query terms | Threat model stated in README + PyPI readme + site: shaping ranks relevance, it does not authenticate content. Roadmap: provenance-aware stages (source allowlists / trust tiers as first-class record fields). |
| 7 | Release used an API token; no Trusted Publishing, no attestations | **Fix now**: release.yml switches to PyPI Trusted Publishing (OIDC) with attestations; requires the human to register the GitHub publisher on PyPI before the next tag (documented in the workflow header). |

## Out of scope (this iteration)
Protected-field guarantees, trust-tier stages, multi-tenant benchmark, SLSA
beyond PyPI attestations. Each returns as its own class-M task.
