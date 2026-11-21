/**
 * Policy fingerprints (ADR-008, brief AC 29-30). Mirrors the policy tests in
 * tests/test_audit_truth.py and the baseline in tests/test_fingerprint_golden.py.
 *
 * Fingerprints are language-local (ADR-001): these values are TypeScript's own.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  allowlist,
  dedupe,
  pipeline,
  quarantine,
  rank,
  rescore,
  select,
  stage,
  trimToBudget,
  truncateField,
  type Records,
} from "../src/index.js";

// --- the recorded baseline (written before the audit-truthfulness change) ---
// Do not regenerate these values to make a test pass: a change here is a
// behavior change that needs an ADR.

function annotate(records: Records, _options: unknown): Records {
  return records;
}

function bare(records: Records): Records {
  return records;
}

class Opaque {}

const SHAPES: Record<string, [() => ReturnType<typeof pipeline>, string]> = {
  contract: [
    () =>
      pipeline([
        stage(allowlist, { field: "source", allowed: ["repo", "docs"] }),
        stage(quarantine, { fields: ["snippet"] }),
        stage(select, { fields: ["path", "line", "source", "snippet"] }),
        stage(dedupe, { key: ["path", "line"] }),
        stage(rescore, { query: "exponential backoff jitter", fields: ["snippet", "path"] }),
        stage(truncateField, { field: "snippet", maxTokens: 12 }),
        stage(rank, { by: "score", desc: true }),
        stage(trimToBudget, { maxTokens: 150 }),
      ]),
    "c0fd8cd67a287c16",
  ],
  primitives: [
    () =>
      pipeline([
        stage(select, { fields: ["a", "b"] }),
        stage(dedupe, { key: "a" }),
        stage(rank, { by: "score", desc: true }),
        stage(trimToBudget, { maxTokens: 100 }),
      ]),
    "d0b41503982b29a1",
  ],
  list_of_mixed_scalars_and_null: [
    () =>
      pipeline([
        stage(allowlist, { field: "s", allowed: ["x", null, 1, 2.5, true] }),
        stage(quarantine, { fields: ["snippet"], action: "drop" }),
      ]),
    "bd1f276ee89b8191",
  ],
  object_with_nesting: [
    () =>
      pipeline([
        stage(annotate, {
          mapping: { b: [1, null, { z: 2.5 }], k: "v" },
          empty: {},
          label: "m",
        }),
      ]),
    "775bd890610029e3",
  ],
  opaque_object: [() => pipeline([stage(annotate, { marker: new Opaque(), n: 3 })]), "98cabc1924c55dbc"],
  named_function: [() => pipeline([stage(annotate, { key: bare, desc: false })]), "575df49f70c34e06"],
  bare_named_function: [() => pipeline([bare]), "d33631bdd67f21f3"],
  empty_pipeline: [() => pipeline([]), "4f53cda18c2baa0c"],
};

for (const [name, [build, expected]] of Object.entries(SHAPES)) {
  test(`fingerprint matches the recorded baseline: ${name}`, () => {
    assert.equal(build().fingerprint, expected);
  });
}

test("the keyword order of bound params does not change the fingerprint", () => {
  const a = pipeline([stage(truncateField, { field: "s", maxTokens: 5, suffix: ".." })]);
  const b = pipeline([stage(truncateField, { suffix: "..", maxTokens: 5, field: "s" })]);
  assert.equal(a.fingerprint, b.fingerprint);
});
