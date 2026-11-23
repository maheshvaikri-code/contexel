/**
 * Typed errors (ADR-003) — parity port of contexel's Python `errors` module.
 *
 * Every error contexel throws on purpose is a `ContexelError` carrying a
 * stable `code`: the cross-language contract (messages are for humans and may
 * differ between the Python, TypeScript and C# ports; codes may not).
 *
 * - `ConfigError`: the *call* is wrong — a bad option, an empty field list, an
 *   invalid regex. Always thrown.
 * - `InputShapeError`: the *data* is wrong — not a list, an item that is not a
 *   mapping, an output field that already exists. Shape errors from the
 *   original stages are thrown only in strict mode (`strict(fn)`); a field
 *   conflict is always thrown, because continuing would silently destroy data.
 */
import { pyRepr, pyTypeName } from "./py.js";

/** The complete, stable set of error codes. */
export const ERROR_CODES = [
  "config.invalid_value",
  "config.empty",
  "config.contradictory",
  "config.invalid_pattern",
  "input.not_list",
  "input.not_mapping",
  "input.field_conflict",
] as const;

export type ErrorCode = (typeof ERROR_CODES)[number];

export interface ErrorLocation {
  stage?: string;
  param?: string;
}

/** Base class: `code` (stable), `stage` and `param` (both optional). */
export class ContexelError extends Error {
  readonly code: ErrorCode;
  readonly stage: string | undefined;
  readonly param: string | undefined;

  constructor(code: ErrorCode, message: string, where: ErrorLocation = {}) {
    super(message);
    if (!(ERROR_CODES as readonly string[]).includes(code)) {
      throw new Error(`unknown contexel error code ${pyRepr(code)}`);
    }
    this.name = new.target.name;
    this.code = code;
    this.stage = where.stage;
    this.param = where.param;
  }
}

/** The stage was configured wrongly. */
export class ConfigError extends ContexelError {}

/** The data does not have the shape the stage needs. */
export class InputShapeError extends ContexelError {}

export function invalidValue(stage: string, param: string, message: string): ConfigError {
  return new ConfigError("config.invalid_value", `${stage}: ${message}`, { stage, param });
}

/** A bare string means ONE field (never its characters); otherwise an array of
 * strings. `allowEmpty: false` rejects an empty array: a stage that scans no
 * fields silently does nothing, and for a security control that is the
 * failure to refuse. */
export function checkFields(
  value: unknown,
  stage: string,
  param = "fields",
  allowEmpty = true
): string[] {
  let names: string[];
  if (typeof value === "string") {
    names = [value];
  } else if (Array.isArray(value)) {
    if (!value.every((v) => typeof v === "string")) {
      throw invalidValue(stage, param, `${param} must contain only strings`);
    }
    names = [...value];
  } else {
    throw invalidValue(
      stage,
      param,
      `${param} must be a string or a list of strings, got ${pyTypeName(value)}`
    );
  }
  if (!names.length && !allowEmpty) {
    throw new ConfigError(
      "config.empty",
      `${stage}: ${param} is empty, so the stage would silently do nothing; pass at least one field`,
      { stage, param }
    );
  }
  return names;
}

export function checkQuery(value: unknown, stage: string, param = "query"): string | unknown[] {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    if (!value.every((v) => typeof v === "string")) {
      throw invalidValue(stage, param, `${param} must contain only strings`);
    }
    return value;
  }
  throw invalidValue(
    stage,
    param,
    `${param} must be a string or a list of strings, got ${pyTypeName(value)}`
  );
}

/** An integer >= 0. A boolean is not an integer here, and `0` stays valid:
 * "no budget left" is a real answer. (TypeScript cannot tell 10.0 from 10.) */
export function checkNonNegativeInt(value: unknown, stage: string, param: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw invalidValue(stage, param, `${param} must be an integer >= 0, got ${pyRepr(value)}`);
  }
  return value;
}

export function checkBool(value: unknown, stage: string, param: string): boolean {
  if (typeof value !== "boolean") {
    throw invalidValue(stage, param, `${param} must be true or false, got ${pyRepr(value)}`);
  }
  return value;
}

export function checkStr(value: unknown, stage: string, param: string): string {
  if (typeof value !== "string") {
    throw invalidValue(stage, param, `${param} must be a string, got ${pyTypeName(value)}`);
  }
  return value;
}

/** `normalize` is null/undefined (leave the text alone) or "nfc". Anything
 * else raises: a normalization that silently did nothing would leave the
 * screen or the match it was asked to widen exactly as narrow as before. */
export function checkNormalize(value: unknown, stage: string): "nfc" | null {
  if (value === undefined || value === null) return null;
  if (value !== "nfc") {
    throw invalidValue(stage, "normalize", `normalize must be null or 'nfc', got ${pyRepr(value)}`);
  }
  return "nfc";
}

export function checkChoice(
  value: unknown,
  stage: string,
  param: string,
  choices: readonly string[]
): string {
  if (typeof value !== "string" || !choices.includes(value)) {
    const listed = choices.map((c) => pyRepr(c)).join(", ");
    throw invalidValue(stage, param, `${param} must be one of ${listed}, got ${pyRepr(value)}`);
  }
  return value;
}
