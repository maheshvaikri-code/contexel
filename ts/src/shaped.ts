/**
 * Apply a contexel pipeline at the tool boundary — parity port. The model
 * calls the tool normally and never writes the reshaping. Async-first: a
 * tool returning a promise is awaited, then shaped (an improvement over
 * static detection — JS shapes any thenable result).
 */
import type { Records } from "./stages.js";
import { pipeline, type StageFn } from "./pipeline.js";

type Tool<A extends unknown[]> = (...args: A) => Records | Promise<Records>;

export function shaped(pipe: StageFn | StageFn[]) {
  const runner = typeof pipe === "function" ? pipe : pipeline(pipe);
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
