/**
 * Data-driven parity cases (ADR-007): replay every case in vectors.json
 * `cases` through one adapter per stage and compare with the Python canon.
 * Adding a case never touches this file; the runner itself is in runner.ts.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import type { Records } from "../src/index.js";
import { checkCase, type Case } from "./runner.js";

const vectors = JSON.parse(
  readFileSync(new URL("../../../parity/vectors.json", import.meta.url), "utf-8")
);
const FIXTURE: Records = vectors.fixture;

test("the cases section is present and complete", () => {
  assert.ok(Array.isArray(vectors.cases), "vectors.cases missing");
  assert.ok(vectors.cases.length > 0, "vectors.cases is empty (a runner must never pass vacuously)");
  assert.strictEqual(
    vectors.cases.length,
    vectors._meta.case_count,
    "case_count disagrees with the cases array (a runner must not silently skip cases)"
  );
  const ids = vectors.cases.map((c: Case) => c.id);
  assert.strictEqual(new Set(ids).size, ids.length, "duplicate case ids");
});

for (const c of vectors.cases as Case[]) {
  test(`case ${c.id}`, () => {
    checkCase(c, FIXTURE);
  });
}
