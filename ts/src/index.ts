/**
 * contexel — deterministic, dependency-free context shaping for
 * code-writing agents. TypeScript parity of the Python package, enforced
 * by shared golden vectors (see the repo's parity/ directory and ADR-001).
 */
export {
  select,
  dedupe,
  allowlist,
  quarantine,
  rescore,
  rank,
  truncateField,
  trimToBudget,
  merge,
  type Rec,
  type Records,
} from "./stages.js";
export { pipeline, stage, type StageFn } from "./pipeline.js";
export { shaped } from "./shaped.js";
export { trace, currentTrace, Trace, type Entry } from "./trace.js";
export * as tokens from "./tokens.js";

export const VERSION = "0.1.17";
