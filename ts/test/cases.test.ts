/**
 * Data-driven parity cases (ADR-007): replay every case in vectors.json
 * `cases` through one adapter per stage and compare with the Python canon.
 * Adding a case never touches this file.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  allowlist,
  dedupe,
  merge,
  pipeline,
  quarantine,
  rank,
  rescore,
  select,
  shaped,
  stage,
  trace,
  trimToBudget,
  truncateField,
  type Records,
  type StageFn,
} from "../src/index.js";

type Args = Record<string, unknown>;
interface Spec {
  stage: string;
  args: Args;
}
interface Case extends Spec {
  id: string;
  input: unknown;
  expect: unknown;
}

const vectors = JSON.parse(
  readFileSync(new URL("../../../parity/vectors.json", import.meta.url), "utf-8")
);
const FIXTURE: Records = vectors.fixture;
const ALLOWED_KEYS = new Set(["id", "stage", "args", "input", "expect"]);

// Python snake_case argument names -> TypeScript camelCase option names.
const camel = (s: string) => s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
function toOptions(args: Args): Args {
  return Object.fromEntries(Object.entries(args).map(([k, v]) => [camel(k), v]));
}

// One adapter per record stage: every TS stage has the shape (records, options).
type RecordStage = (records: Records, options: never) => Records;
const RECORD_STAGES: Record<string, RecordStage> = {
  select,
  dedupe,
  allowlist,
  quarantine,
  rescore,
  rank,
  truncate_field: truncateField,
  trim_to_budget: trimToBudget,
};

function bind(spec: Spec): StageFn {
  const fn = RECORD_STAGES[spec.stage];
  assert.ok(fn, `unknown stage ${spec.stage}`);
  return stage(fn as never, toOptions(spec.args) as never);
}
const build = (specs: Spec[]): StageFn => pipeline(specs.map(bind));

function run(c: Case): unknown {
  const input = c.input === "$fixture" ? FIXTURE : c.input;
  const records = input as Records;
  const fn = RECORD_STAGES[c.stage];
  if (fn) return fn(records, toOptions(c.args) as never);
  const stages = c.args.stages as Spec[];
  switch (c.stage) {
    case "merge":
      return merge(input as Records[], toOptions(c.args));
    case "pipeline":
      return build(stages)(records);
    case "shaped":
      return shaped(build(stages))(() => records)();
    case "trace_report": {
      const [, tr] = trace({ idField: (c.args.id_field as string) ?? undefined }, () =>
        build(stages)(records)
      );
      return tr.report();
    }
    default:
      throw new Error(`unknown case kind ${c.stage}`);
  }
}

test("the cases section is present and complete", () => {
  assert.ok(Array.isArray(vectors.cases), "vectors.cases missing");
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
    for (const key of Object.keys(c)) {
      assert.ok(ALLOWED_KEYS.has(key), `case ${c.id} has unsupported key ${key}`);
    }
    assert.deepStrictEqual(run(c), c.expect);
  });
}
