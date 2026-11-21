/**
 * In-language composition — parity port. Any `records => records` callable
 * is a valid stage. Pipelines carry a stable, address-free fingerprint
 * (language-local in v1 per ADR-001) recorded into any active trace.
 *
 * Coverage: primitives, arrays, plain objects and `Set`s (by sorted contents)
 * are hashed by value; a nested pipeline contributes its own fingerprint;
 * functions by `name`; any other object by its own enumerable entries (so a
 * `Map`, `Date` or `RegExp`, which have none, all render as `{}`). `stage()`
 * takes a private copy of the exact arrays, plain objects and `Set`s bound to
 * it (subclasses are kept as they are; a `Set`'s elements are not copied) and `pipeline()` copies its list of stages, so
 * changing the caller's own array or object afterwards changes neither the
 * behavior nor the fingerprint. Class instances, `Map`s and the elements of a
 * `Set` stay live.
 */
import { createHash } from "node:crypto";
import { checkBool } from "./errors.js";
import type { Rec, Records } from "./stages.js";
import { currentTrace } from "./trace.js";
import { checkStageOutput, strict as strictRun } from "./validate.js";

export type StageFn = (records: Records) => Records;

interface Described extends StageFn {
  __contexelDesc?: string;
  fingerprint?: string;
}

function stableRepr(value: unknown): string {
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return "[" + value.map(stableRepr).join(",") + "]";
  // Insertion order is not part of a set's meaning: hash the sorted contents.
  if (value instanceof Set) return "set{" + [...value].map(stableRepr).sort().join(",") + "}";
  if (typeof value === "function") return (value as { name?: string }).name || "function";
  if (typeof value === "object") {
    const entries = Object.entries(value as Rec).sort(([a], [b]) =>
      a < b ? -1 : a > b ? 1 : 0
    );
    return "{" + entries.map(([k, v]) => `${JSON.stringify(k)}:${stableRepr(v)}`).join(",") + "}";
  }
  return typeof value;
}

/** A private copy of the exact arrays, plain objects and `Set`s in `value`
 * (any depth), the same exact-type rule as the Python port. A `Set` is copied
 * as a shell: its elements are the caller's own. Everything else (subclasses,
 * class instances, `Map`s, functions) is returned as it is. */
function snapshot<T>(value: T): T {
  if (value === null || typeof value !== "object") return value;
  const proto = Object.getPrototypeOf(value);
  if (proto === Array.prototype) return (value as unknown[]).map(snapshot) as T;
  if (proto === Set.prototype) return new Set(value as unknown as Set<unknown>) as T;
  if (proto === Object.prototype || proto === null) {
    const copy: Rec = Object.create(proto);
    // defineProperty, not assignment: `copy["__proto__"] = v` would call the
    // prototype setter and re-parent the copy instead of keeping the own key.
    for (const [k, v] of Object.entries(value as Rec)) {
      Object.defineProperty(copy, k, {
        value: snapshot(v),
        enumerable: true,
        writable: true,
        configurable: true,
      });
    }
    return copy as T;
  }
  return value;
}

/** Bind params to a stage so it slots into a pipeline as `records => records`.
 * The stage keeps a private copy of any array, plain object or `Set` among the
 * params, so changing the caller's own value afterwards cannot change what the
 * stage does or what its fingerprint says. */
export function stage<P>(
  fn: (records: Records, params: P) => Records,
  params: P
): StageFn {
  const bound = snapshot(params);
  const run: Described = (records: Records) => fn(records, bound);
  Object.defineProperty(run, "name", { value: fn.name || "stage" });
  run.__contexelDesc = `${fn.name || "stage"}(${stableRepr(bound)})`;
  return run;
}

/** Compose stages left-to-right; the callable exposes `.fingerprint`.
 *
 * `{ strict: true }` runs every stage in strict mode (see `strict`) and checks
 * that each stage hands the next one a list, so a custom stage that returns
 * `null` throws an `InputShapeError` naming it, instead of breaking the stage
 * after it. It is entered inside the pipeline's own run, so it also holds in a
 * worker thread. Strict never changes a successful result and is not part of
 * the fingerprint. */
export function pipeline(stageList: StageFn[], options: { strict?: boolean } = {}): Described {
  if (options.strict !== undefined) checkBool(options.strict, "pipeline", "strict");
  const isStrictPipeline = options.strict === true;
  const stages = [...stageList]; // a later change to the caller's array is not ours
  const descs = stages.map(
    (s) => (s as Described).__contexelDesc ?? ((s as Described).name || "callable")
  );
  const fingerprint = createHash("sha256")
    .update(JSON.stringify(descs))
    .digest("hex")
    .slice(0, 16);

  const run: Described = (records: Records) => {
    const tr = currentTrace();
    if (tr && !tr.policies.includes(fingerprint)) tr.policies.push(fingerprint);
    if (!isStrictPipeline) {
      let out = records;
      for (const s of stages) out = s(out);
      return out;
    }
    return strictRun(() => {
      let out = records;
      for (let i = 0; i < stages.length; i++) {
        const s = stages[i] as Described;
        out = s(out);
        checkStageOutput(out, s.name || "callable", i);
      }
      return out;
    });
  };
  run.fingerprint = fingerprint;
  // as a stage of an outer pipeline, contribute this fingerprint (not "run")
  run.__contexelDesc = `pipeline(${fingerprint})`;
  return run;
}
