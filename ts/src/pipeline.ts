/**
 * In-language composition — parity port. Any `records => records` callable
 * is a valid stage. Pipelines carry a stable, address-free fingerprint
 * (language-local in v1 per ADR-001) recorded into any active trace.
 */
import { createHash } from "node:crypto";
import type { Rec, Records } from "./stages.js";
import { currentTrace } from "./trace.js";

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
  if (typeof value === "function") return (value as { name?: string }).name || "function";
  if (typeof value === "object") {
    const entries = Object.entries(value as Rec).sort(([a], [b]) =>
      a < b ? -1 : a > b ? 1 : 0
    );
    return "{" + entries.map(([k, v]) => `${JSON.stringify(k)}:${stableRepr(v)}`).join(",") + "}";
  }
  return typeof value;
}

/** Bind params to a stage so it slots into a pipeline as `records => records`. */
export function stage<P>(
  fn: (records: Records, params: P) => Records,
  params: P
): StageFn {
  const run: Described = (records: Records) => fn(records, params);
  Object.defineProperty(run, "name", { value: fn.name || "stage" });
  run.__contexelDesc = `${fn.name || "stage"}(${stableRepr(params)})`;
  return run;
}

/** Compose stages left-to-right; the callable exposes `.fingerprint`. */
export function pipeline(stages: StageFn[]): Described {
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
    let out = records;
    for (const s of stages) out = s(out);
    return out;
  };
  run.fingerprint = fingerprint;
  return run;
}
