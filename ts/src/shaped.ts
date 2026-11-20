/**
 * Apply a contexel pipeline at the tool boundary — parity port. The model
 * calls the tool normally and never writes the reshaping. Async-first: a
 * tool returning a promise is awaited, then shaped (an improvement over
 * static detection — JS shapes any thenable result).
 */
import { InputShapeError } from "./errors.js";
import type { Records } from "./stages.js";
import { pipeline, type StageFn } from "./pipeline.js";
import { strict as strictRun } from "./validate.js";
import { pyTypeName } from "./py.js";

type Tool<A extends unknown[]> = (...args: A) => Records | Promise<Records>;

/**
 * `{ strict: true }` validates the tool's result is a list (an
 * `InputShapeError` with stage "shaped" otherwise — a tool that returns
 * `null` would else surface as an obscure error inside the first stage) and
 * runs the pipeline in strict mode, entered inside this wrapper so it holds in
 * a worker thread. When `pipe` is a list of stages it is composed with
 * `pipeline(..., { strict: true })`, which also checks each stage's output; a
 * prebuilt pipeline is simply run inside strict mode.
 */
export function shaped(pipe: StageFn | StageFn[], options: { strict?: boolean } = {}) {
  const strict = options.strict === true;
  const base = typeof pipe === "function" ? pipe : pipeline(pipe, { strict });
  const runner: StageFn = (records) => {
    if (!strict) return base(records);
    if (!Array.isArray(records)) {
      throw new InputShapeError(
        "input.not_list",
        `shaped: the tool must return a list, got ${pyTypeName(records)}`,
        { stage: "shaped" }
      );
    }
    return strictRun(() => base(records));
  };
  return function <A extends unknown[]>(fn: Tool<A>) {
    return (...args: A): Records | Promise<Records> => {
      const result = fn(...args);
      if (result && typeof (result as Promise<Records>).then === "function") {
        return (result as Promise<Records>).then((records) => runner(records));
      }
      return runner(result as Records);
    };
  };
}
