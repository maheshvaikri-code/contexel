/**
 * Audit truthfulness (ADR-008, brief AC 28-30): the trail must not
 * under-report. Mirrors tests/test_audit_truth.py.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { allowlist, select, trace, type Records } from "../src/index.js";
import { traced } from "../src/trace.js";

/** Run one stage under a trace; return its output and recorded dropped ids. */
function drops(
  records: Records,
  stageFn: (records: Records) => Records,
  idField = "id"
): [Records, unknown[]] {
  const [out, tr] = trace({ idField }, () => stageFn(records));
  const stages = tr.audit().stages as { dropped_ids: unknown[] }[];
  return [out, stages[0].dropped_ids];
}

// --- AC 28: dropped_ids -----------------------------------------------------

test("trace reports a drop when another survivor never had the id", () => {
  // "a" is dropped. The record without an id was in the input already, so it
  // is not evidence that a survivor lost its id: "a" must be reported.
  const records: Records = [{ id: "a", t: "x" }, { t: "y" }, { id: "b", t: "z" }];
  const [out, dropped] = drops(records, (r) => allowlist(r, { field: "t", allowed: ["y", "z"] }));
  assert.deepEqual(
    out.map((r) => r.t),
    ["y", "z"]
  );
  assert.deepEqual(dropped, ["a"]);
});

test("trace: select stripping ids is not a drop", () => {
  const records: Records = [0, 1, 2].map((i) => ({ id: `u${i}`, title: `t${i}` }));
  const [out, dropped] = drops(records, (r) => select(r, { fields: ["title"] }));
  assert.equal(out.length, 3);
  assert.deepEqual(dropped, []);
});

test("trace: a mixed input with select stripping ids is not a drop", () => {
  const records: Records = [{ id: "a", title: "x" }, { title: "y" }, { id: "b", title: "z" }];
  const [out, dropped] = drops(records, (r) => select(r, { fields: ["title"] }));
  assert.equal(out.length, 3);
  assert.deepEqual(dropped, []);
});

test("trace: the ambiguity is bounded by the lost count", () => {
  // The stage keeps "a" with its id, keeps one record WITHOUT an id and
  // discards two. Only ONE id can be explained by a stripped survivor.
  const keepAAndOneStripped = (records: Records): Records => [records[0], { title: "stripped" }];
  const records: Records = [
    { id: "a", title: "1" },
    { id: "b", title: "2" },
    { id: "c", title: "3" },
  ];
  const [out, dropped] = drops(records, traced("keep_a_and_one_stripped", keepAAndOneStripped));
  assert.equal(out.length, 2);
  assert.deepEqual(dropped, ["c"]);
});

test("trace: a stage that adds id-less records never hides more than it added", () => {
  const addTwoDropB = (records: Records): Records => [records[0], { n: 1 }, { n: 2 }];
  const [, dropped] = drops([{ id: "a" }, { id: "b" }], traced("add_two_drop_b", addTwoDropB));
  assert.deepEqual(dropped, []);
});

test("trace: dropped ids are reported in input order", () => {
  const records: Records = [
    { id: 1, k: "drop" },
    { k: "keep" },
    { id: 3, k: "drop" },
    { id: 4, k: "keep" },
  ];
  const [, dropped] = drops(records, (r) => allowlist(r, { field: "k", allowed: ["keep"] }));
  assert.deepEqual(dropped, [1, 3]);
});
