/**
 * Strict mode: opt-in validation of the *shape* of stage input (ADR-003) —
 * parity port of contexel's Python `validate` module.
 *
 * The original stages are lenient about data shape (a non-list fails somewhere
 * inside, or worse, silently produces nonsense). That stays the default, so
 * valid input and today's callers keep byte-identical behavior. Switch strict
 * mode on to get a typed `InputShapeError` that names the stage (and the item
 * index) instead:
 *
 *     strict(() => shape(records));                      // ambient: this async context
 *     const pipe = pipeline([...], { strict: true });    // also holds in a worker thread
 *
 * Strict never changes a successful result and is not part of a pipeline's
 * fingerprint.
 */
import { AsyncLocalStorage } from "node:async_hooks";
import { InputShapeError } from "./errors.js";
import { pyTypeName } from "./py.js";
import type { Rec } from "./stages.js";

const store = new AsyncLocalStorage<boolean>();

/** Run `fn` with strict shape validation on for the stages called inside; the
 * flag follows `await` (AsyncLocalStorage) and is restored when `fn` returns
 * or throws. It is NOT inherited by a `worker_threads` Worker:
 * `pipeline(..., { strict: true })` and `shaped(..., { strict: true })` enter
 * strict mode inside their own run, so they are safe there. */
export function strict<T>(fn: () => T): T {
  return store.run(true, fn);
}

/** Whether strict mode is active in the current async context. */
export function isStrict(): boolean {
  return store.getStore() ?? false;
}

/** A mapping, as a stage that indexes records sees one: a non-null object
 * that is not an array. */
function isMapping(value: unknown): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Throw unless `records` is an array — and, when `mapping`, unless every item
 * is a mapping. The message names the stage and the index. */
export function checkRecords(records: unknown, stage: string, mapping: boolean): void {
  if (!Array.isArray(records)) {
    throw new InputShapeError(
      "input.not_list",
      `${stage}: records must be a list, got ${pyTypeName(records)}`,
      { stage }
    );
  }
  if (mapping) {
    for (let i = 0; i < records.length; i++) {
      if (!isMapping(records[i])) {
        throw new InputShapeError(
          "input.not_mapping",
          `${stage}: item ${i} must be a mapping, got ${pyTypeName(records[i])}`,
          { stage }
        );
      }
    }
  }
}

/** Strict pipelines: a stage must hand the next one a list. */
export function checkStageOutput(out: unknown, stage: string, index: number): void {
  if (!Array.isArray(out)) {
    throw new InputShapeError(
      "input.not_list",
      `stage ${index} (${stage}) returned ${pyTypeName(out)}, not a list`,
      { stage }
    );
  }
}

/**
 * Wrap a record stage: in strict mode, validate its input before the stage
 * (and `traced`) touches it. Apply it OUTSIDE `traced`: `traced` reads
 * `records.length` first, so a non-list would otherwise throw a raw error
 * under a trace instead of the typed one. `needsMapping` is `true` when the
 * stage always indexes items as mappings, or a function of the call's
 * arguments for stages that only sometimes need one (`dedupe` with a `key`,
 * `rank` with a field name).
 */
export function checked<A extends unknown[], R>(
  name: string,
  needsMapping: boolean | ((...args: A) => boolean),
  fn: (records: Rec[], ...args: A) => R
): (records: Rec[], ...args: A) => R {
  return (records: Rec[], ...args: A): R => {
    if (isStrict()) {
      const need = typeof needsMapping === "function" ? needsMapping(...args) : needsMapping;
      checkRecords(records, name, need);
    }
    return fn(records, ...args);
  };
}
