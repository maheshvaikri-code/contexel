# G2 Plan — TypeScript parity (Class L; brief = ADR-001's Decision section)

1. `ts/` package: `package.json` (npm `contexel`, 0.1.15, ESM, zero deps),
   `tsconfig.json` (strict, NodeNext, declarations), `src/` mirroring the
   Python modules (tokens, stages, pipeline, shaped, trace, index).
2. `parity/generate_vectors.py` → `parity/vectors.json` (committed):
   fixed ASCII search-hit fixture (ints/strings only), per-stage expected
   outputs, composed-contract output, rescore scores, token counts, audit
   record (fingerprints excluded per ADR boundary 4c).
3. `ts/test/`: parity suite (byte-equality against vectors) + behavior
   tests (async shaped, scoped isolation, quarantine probe, dedupe
   typed keys) on `node:test`.
4. G4: fresh-context code-reviewer subagent over the ts/ + parity diff.
5. G5: `npm run build` + `npm test` real output; Python suite unchanged.
6. Docs: README + README_PYPI TypeScript section; CHANGELOG [Unreleased].
   Site + npm publish workflow = follow-up tasks (§5 for the publish).

## Scope added during execution (recorded per doctrine)

7. G4 round 1 (REQUEST-CHANGES: 1 BLOCKER, 6 MAJOR) drove a parity-hardening
   pass: new `ts/src/py.ts` (Python `str`/`repr`/float-repr/half-even
   `round`/code-point compare/`rstrip`/hash-equality replication), own-property
   semantics throughout, and a Python canon fix (`_typed_tuple` container
   type tags). The vector suite grew an `edges` block (13 divergence
   classes) so every fixed finding is enforced, not just fixed. CI
   `ts-parity` job regenerates vectors from canon and diffs before running
   the TS suite.
8. User field report (mid-task): `trim_to_budget(min_records=)` empty-list
   guard and bare-string `fields` acceptance — implemented in both
   languages + vectors + site stage reference.
9. G4 round 2: APPROVE-WITH-NITS; NITs closed (scoped `undefined` merge,
   `-0` ADR margin, allowlist prose, this plan update).
