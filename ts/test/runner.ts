/**
 * The data-driven case runner (ADR-007): replays every case in vectors.json
 * `cases` through one adapter per stage. Kept in a module of its own so its
 * own rules (unknown keys, unknown arguments, expect_error) are testable.
 */
import assert from "node:assert/strict";

import {
  ContexelError,
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
  strict,
  trace,
  trimToBudget,
  truncateField,
  type Records,
  type StageFn,
} from "../src/index.js";

export type Args = Record<string, unknown>;
export interface Spec {
  stage: string;
  args: Args;
}
export interface Case extends Spec {
  id: string;
  input: unknown;
  expect?: unknown;
  expect_error?: { code: string };
  strict?: boolean;
}

export const ALLOWED_KEYS = new Set([
  "id",
  "stage",
  "args",
  "input",
  "expect",
  "expect_error",
  "strict",
]);

// Python snake_case argument names -> TypeScript camelCase option names.
const camel = (s: string) => s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
function toOptions(args: Args): Args {
  return Object.fromEntries(Object.entries(args).map(([k, v]) => [camel(k), v]));
}

// One adapter per record stage: every TS stage has the shape (records, options).
type RecordStage = (records: Records, options: never) => Records;
export const RECORD_STAGES: Record<string, RecordStage> = {
  select,
  dedupe,
  allowlist,
  quarantine,
  rescore,
  rank,
  truncate_field: truncateField,
  trim_to_budget: trimToBudget,
};

/** The argument names a JSON case may use, per stage kind (snake_case, as in
 * the JSON). A typo'd name must fail loudly: it must never be silently ignored
 * or defaulted (callable-valued arguments, such as a tokenizer, are not JSON
 * and are not listed). */
export const ARG_NAMES: Record<string, readonly string[]> = {
  select: ["fields"],
  dedupe: ["key"],
  allowlist: ["field", "allowed"],
  quarantine: ["fields", "patterns", "action", "into", "replace_patterns"],
  rescore: ["query", "fields", "into", "proximity", "match"],
  rank: ["by", "desc"],
  truncate_field: ["field", "max_tokens", "suffix"],
  trim_to_budget: ["max_tokens", "min_records"],
  merge: ["schema", "dedupe_key"],
  pipeline: ["stages"],
  shaped: ["stages"],
  trace_report: ["stages", "id_field"],
};

const SPEC_KEYS = new Set(["stage", "args"]);

/** Throw unless `spec` is a known stage kind whose arguments are all known —
 * and, for pipeline/shaped/trace_report, so is every nested stage spec. */
export function validateSpec(spec: Spec, where: string): void {
  assert.ok(
    Object.hasOwn(ARG_NAMES, spec.stage),
    `${where}: unknown stage ${JSON.stringify(spec.stage)}`
  );
  const known = ARG_NAMES[spec.stage];
  for (const name of Object.keys(spec.args ?? {})) {
    assert.ok(
      known.includes(name),
      `${where}: unknown argument ${JSON.stringify(name)} for stage ${spec.stage}`
    );
  }
  const nested = (spec.args as Args | undefined)?.stages;
  if (nested !== undefined) {
    assert.ok(Array.isArray(nested), `${where}: args.stages must be a list`);
    (nested as Spec[]).forEach((s, i) => {
      for (const key of Object.keys(s)) {
        assert.ok(SPEC_KEYS.has(key), `${where}.stages[${i}]: unsupported key ${key}`);
      }
      assert.ok(
        Object.hasOwn(RECORD_STAGES, s.stage),
        `${where}.stages[${i}]: unknown stage ${JSON.stringify(s.stage)}`
      );
      validateSpec(s, `${where}.stages[${i}]`);
    });
  }
}

function bind(spec: Spec): StageFn {
  assert.ok(Object.hasOwn(RECORD_STAGES, spec.stage), `unknown stage ${spec.stage}`);
  return stage(RECORD_STAGES[spec.stage] as never, toOptions(spec.args) as never);
}
const build = (specs: Spec[]): StageFn => pipeline(specs.map(bind));

function execute(c: Case, fixture: Records): unknown {
  // a null input reaches the stage as null, a null item as a null item
  const input = c.input === "$fixture" ? fixture : c.input;
  const records = input as Records;
  if (Object.hasOwn(RECORD_STAGES, c.stage)) {
    return RECORD_STAGES[c.stage](records, toOptions(c.args) as never);
  }
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

/** Run one case (inside strict mode when it says so). Validates the case's
 * keys and arguments first. Returns the output, or throws what the stage threw. */
export function runCase(c: Case, fixture: Records): unknown {
  for (const key of Object.keys(c)) {
    assert.ok(ALLOWED_KEYS.has(key), `case ${c.id} has unsupported key ${key}`);
  }
  if (Object.hasOwn(c, "strict")) {
    assert.strictEqual(typeof c.strict, "boolean", `case ${c.id}: strict must be a boolean`);
  }
  validateSpec(c, `case ${c.id}`);
  return c.strict ? strict(() => execute(c, fixture)) : execute(c, fixture);
}

/** Assert the case's outcome: `expect` equals the output, or `expect_error`
 * names the code of the contexel error the call must throw. Any other
 * exception, or no exception, fails. */
export function checkCase(c: Case, fixture: Records): void {
  const hasExpect = "expect" in c;
  const hasError = "expect_error" in c;
  assert.ok(hasExpect !== hasError, `case ${c.id} needs exactly one of expect / expect_error`);
  if (!hasError) {
    assert.deepStrictEqual(runCase(c, fixture), c.expect);
    return;
  }
  let outcome: { threw: false; value: unknown } | { threw: true; error: unknown };
  try {
    outcome = { threw: false, value: runCase(c, fixture) };
  } catch (error) {
    outcome = { threw: true, error };
  }
  assert.ok(outcome.threw, `case ${c.id} should throw ${c.expect_error?.code}, but returned`);
  const error = (outcome as { error: unknown }).error;
  assert.ok(
    error instanceof ContexelError,
    `case ${c.id} threw a non-contexel error: ${String(error)}`
  );
  assert.strictEqual(error.code, c.expect_error?.code, `case ${c.id}: wrong error code`);
}
