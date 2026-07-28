/**
 * Token measurement — parity port of contexel's Python `tokens` module.
 *
 * Counting is encoding-relative: a record's cost is the token count of its
 * serialized text. The canonical serialization replicates Python's
 * `json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)` —
 * including the ", " / ": " separators — so both languages price identical
 * records identically. Token length counts Unicode code points (Python
 * `len`), not UTF-16 units.
 *
 * Parity boundary (ADR-001): JS has one number type — a JSON `1.0` parses
 * to `1` and serializes as `"1"`, where Python emits `"1.0"`.
 */
import { AsyncLocalStorage } from "node:async_hooks";
import { compareCodePoints, pyFloat } from "./py.js";

export type Tokenizer = (text: string) => number;
export type Serializer = (value: unknown) => string;

export function codePointLength(text: string): number {
  let n = 0;
  for (const _ of text) n++;
  return n;
}

function heuristic(text: string): number {
  if (!text) return 0;
  return Math.max(1, Math.ceil(codePointLength(text) / 4));
}

/** Python-compatible canonical JSON (sort_keys, ensure_ascii=False, default=str). */
export function pythonJson(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return value > 0 ? "Infinity" : value < 0 ? "-Infinity" : "NaN";
    // Python repr thresholds for floats ("1e-05", not JS's "0.00001");
    // integer-valued numbers collapse to int form (ADR-001 boundary 4a).
    return Number.isInteger(value) ? String(value) : pyFloat(value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) {
    return "[" + value.map(pythonJson).join(", ") + "]";
  }
  if (value instanceof Set) {
    // Python json.dumps falls to default=str for sets; not JSON data — best effort.
    return JSON.stringify(String(value));
  }
  if (typeof value === "object") {
    // Python sorted() compares by code point; JS default string order is
    // UTF-16, which sorts astral-plane keys differently.
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => compareCodePoints(a, b));
    return "{" + entries.map(([k, v]) => JSON.stringify(k) + ": " + pythonJson(v)).join(", ") + "}";
  }
  return JSON.stringify(String(value)); // default=str
}

let processTokenizer: Tokenizer | null = null;
let processSerializer: Serializer | null = null;

interface Scope { tokenizer?: Tokenizer; serializer?: Serializer }
const scopeStore = new AsyncLocalStorage<Scope>();

/** Process-wide default tokenizer; null resets to the built-in estimator. */
export function setTokenizer(tokenizer: Tokenizer | null): void {
  processTokenizer = tokenizer;
}

/** Process-wide default serializer; null resets to canonical JSON. */
export function setSerializer(serializer: Serializer | null): void {
  processSerializer = serializer;
}

/**
 * Context-local token accounting — safe for concurrent tenants. The JS
 * analog of Python's `tokens.scoped()`: overrides apply within `fn` and
 * every async continuation it spawns; other tasks are untouched.
 */
export function scoped<T>(overrides: Scope, fn: () => T): T {
  // merge with any enclosing scope so nested overrides compose, like
  // Python's two independent ContextVars; an explicit `undefined` means
  // "not provided", never "clobber the outer override"
  const merged: Scope = { ...scopeStore.getStore() };
  if (overrides.tokenizer !== undefined) merged.tokenizer = overrides.tokenizer;
  if (overrides.serializer !== undefined) merged.serializer = overrides.serializer;
  return scopeStore.run(merged, fn);
}

function activeTokenizer(): Tokenizer {
  return scopeStore.getStore()?.tokenizer ?? processTokenizer ?? heuristic;
}

function activeSerializer(): Serializer {
  return scopeStore.getStore()?.serializer ?? processSerializer ?? pythonJson;
}

/** True when the tokenizer in effect is the built-in estimator (enables
 * the closed-form truncate fast path, which relies on ceil(len/4)). */
export function isHeuristic(tokenizer?: Tokenizer | null): boolean {
  return (tokenizer ?? activeTokenizer()) === heuristic;
}

/** Render a value exactly the way token counting will price it. */
export function serialize(value: unknown): string {
  if (typeof value === "string") return value;
  return activeSerializer()(value);
}

/** Token cost of any serializable value (strings bypass the serializer). */
export function count(value: unknown, tokenizer?: Tokenizer | null): number {
  const tok = tokenizer ?? activeTokenizer();
  return tok(typeof value === "string" ? value : serialize(value));
}
