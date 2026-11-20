/**
 * The typed error model (ADR-003): a stable `code` is the cross-language
 * contract, the two subclasses are real `Error`s that survive `instanceof`,
 * and the original quarantine messages are untouched.
 * Mirrors tests/test_errors.py.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import * as contexel from "../src/index.js";
import {
  ConfigError,
  ContexelError,
  ERROR_CODES,
  InputShapeError,
  quarantine,
} from "../src/index.js";

const DOCUMENTED_CODES = [
  "config.invalid_value",
  "config.empty",
  "config.contradictory",
  "config.invalid_pattern",
  "input.not_list",
  "input.not_mapping",
  "input.field_conflict",
];

test("config error is an Error and a ContexelError (and not an InputShapeError)", () => {
  const e = new ConfigError("config.empty", "nothing to do", {
    stage: "quarantine",
    param: "fields",
  });
  assert.ok(e instanceof ContexelError);
  assert.ok(e instanceof Error);
  assert.ok(e instanceof ConfigError);
  assert.ok(!(e instanceof InputShapeError));
  assert.ok(!(e instanceof TypeError));
  assert.deepStrictEqual(
    [e.code, e.stage, e.param, e.message, e.name],
    ["config.empty", "quarantine", "fields", "nothing to do", "ConfigError"]
  );
});

test("input shape error is an Error and a ContexelError (and not a ConfigError)", () => {
  const e = new InputShapeError("input.not_list", "not a list", { stage: "select" });
  assert.ok(e instanceof ContexelError);
  assert.ok(e instanceof Error);
  assert.ok(e instanceof InputShapeError);
  assert.ok(!(e instanceof ConfigError));
  assert.deepStrictEqual(
    [e.code, e.stage, e.param, e.name],
    ["input.not_list", "select", undefined, "InputShapeError"]
  );
});

test("stage and param are optional", () => {
  const e = new ContexelError("config.empty", "x");
  assert.strictEqual(e.stage, undefined);
  assert.strictEqual(e.param, undefined);
  assert.ok(typeof e.stack === "string" && e.stack.length > 0);
});

test("error codes are the documented set", () => {
  assert.deepStrictEqual([...ERROR_CODES], DOCUMENTED_CODES);
});

test("an unknown code is refused", () => {
  assert.throws(
    () => new ConfigError("config.made_up" as never, "x"),
    /unknown contexel error code/
  );
  assert.throws(
    () => new InputShapeError("nope" as never, "x"),
    /unknown contexel error code/
  );
});

test("the errors are exported from the package", () => {
  for (const name of ["ContexelError", "ConfigError", "InputShapeError", "strict", "isStrict"]) {
    assert.ok(name in contexel, `${name} is not exported`);
  }
});

const MESSAGE_CASES: Array<[Record<string, unknown>, string, string]> = [
  [
    { action: "allow" },
    "action must be 'drop' or 'flag', got allow",
    "config.invalid_value",
  ],
  [
    { patterns: [""] },
    "empty pattern fragments match everything; remove them",
    "config.empty",
  ],
  [
    { patterns: [], replacePatterns: true },
    "replacePatterns with no patterns would disable the control entirely; pass at least one pattern",
    "config.empty",
  ],
  [
    { replacePatterns: true },
    "replacePatterns without patterns is contradictory; pass the replacement patterns",
    "config.contradictory",
  ],
];

for (const [options, message, code] of MESSAGE_CASES) {
  test(`existing quarantine message is unchanged: ${code} ${JSON.stringify(options)}`, () => {
    assert.throws(
      () => quarantine([{ snippet: "x" }], options as never),
      (e: unknown) => {
        assert.ok(e instanceof Error); // the pre-existing generic handler still works
        assert.strictEqual(e.message, message);
        assert.ok(e instanceof ConfigError);
        assert.strictEqual(e.code, code);
        return true;
      }
    );
  });
}
