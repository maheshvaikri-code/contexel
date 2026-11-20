/**
 * The case runner's own rules (brief section 5): an unknown argument name is
 * rejected, an expect_error case fails on the wrong code, a stage named like
 * an inherited property is an unknown stage, and a null input reaches the
 * stage as null.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import type { Records } from "../src/index.js";
import { ARG_NAMES, RECORD_STAGES, checkCase, runCase, type Case } from "./runner.js";

const FIXTURE: Records = [{ a: "x", n: 1 }];

const base = (over: Partial<Case> & Record<string, unknown>): Case =>
  ({ id: "t/case", stage: "select", args: { fields: ["a"] }, input: [{ a: 1, b: 2 }], ...over }) as Case;

test("a valid case passes", () => {
  checkCase(base({ expect: [{ a: 1 }] }), FIXTURE);
});

test("the argument table covers exactly the record stages plus the composite kinds", () => {
  assert.deepStrictEqual(
    Object.keys(ARG_NAMES).sort(),
    [...Object.keys(RECORD_STAGES), "merge", "pipeline", "shaped", "trace_report"].sort()
  );
});

test("an unknown argument name in a case is rejected, not ignored", () => {
  // `field` (a typo for `fields`) would silently default if it were ignored
  assert.throws(
    () => checkCase(base({ args: { field: ["a"] }, expect: [{ a: 1 }] }), FIXTURE),
    /unknown argument "field" for stage select/
  );
  assert.throws(
    () =>
      checkCase(
        base({ stage: "trim_to_budget", args: { max_tokens: 10, maxTokens: 10 }, expect: [] }),
        FIXTURE
      ),
    /unknown argument "maxTokens"/
  );
});

for (const kind of ["pipeline", "shaped", "trace_report"]) {
  test(`an unknown argument inside a nested ${kind} stage spec is rejected`, () => {
    const c = base({
      stage: kind,
      args: { stages: [{ stage: "select", args: { fields: ["a"], extra: 1 } }] },
      expect: [],
    });
    assert.throws(() => checkCase(c, FIXTURE), /stages\[0\]: unknown argument "extra"/);
  });

  test(`an unknown argument on the ${kind} case itself is rejected`, () => {
    const c = base({
      stage: kind,
      args: { stages: [{ stage: "select", args: { fields: ["a"] } }], bogus: true },
      expect: [],
    });
    assert.throws(() => checkCase(c, FIXTURE), /unknown argument "bogus"/);
  });
}

test("an unknown key in a nested stage spec is rejected", () => {
  const c = base({
    stage: "pipeline",
    args: { stages: [{ stage: "select", args: { fields: ["a"] }, strict: true }] },
    expect: [],
  });
  assert.throws(() => checkCase(c, FIXTURE), /unsupported key strict/);
});

test("an unsupported case key is rejected", () => {
  assert.throws(() => checkCase(base({ expect: [{ a: 1 }], bogus: 1 }), FIXTURE), /unsupported key bogus/);
});

test("a case needs exactly one of expect and expect_error", () => {
  assert.throws(() => checkCase(base({}), FIXTURE), /exactly one of expect \/ expect_error/);
  assert.throws(
    () => checkCase(base({ expect: [], expect_error: { code: "input.not_list" } }), FIXTURE),
    /exactly one of expect \/ expect_error/
  );
});

test("an expect case whose output differs from the library's fails", () => {
  // the comparison itself is under test: select returns [{ a: 1 }], not 999
  assert.throws(() => checkCase(base({ expect: [{ a: 999 }] }), FIXTURE), assert.AssertionError);
});

test("an expect_error case passes on the right code", () => {
  checkCase(
    base({ input: null, strict: true, expect_error: { code: "input.not_list" } }),
    FIXTURE
  );
});

test("an expect_error case with the wrong code fails", () => {
  assert.throws(
    () =>
      checkCase(base({ input: null, strict: true, expect_error: { code: "input.not_mapping" } }), FIXTURE),
    /wrong error code/
  );
});

test("an expect_error case fails when nothing is thrown", () => {
  assert.throws(
    () => checkCase(base({ expect_error: { code: "input.not_list" } }), FIXTURE),
    /should throw input\.not_list, but returned/
  );
});

test("an expect_error case fails on a non-contexel exception", () => {
  // not strict: select(null) is a raw TypeError, which is not the typed error
  assert.throws(
    () => checkCase(base({ input: null, expect_error: { code: "input.not_list" } }), FIXTURE),
    /threw a non-contexel error/
  );
});

test("a non-boolean strict is rejected, not coerced", () => {
  for (const bad of ["true", "false", 1, null]) {
    const c = base({ strict: bad as never, expect: [{ a: 1 }] });
    assert.throws(() => runCase(c, FIXTURE), /case t\/case: strict must be a boolean/);
  }
});

test("strict: true runs the case in strict mode (and its absence does not)", () => {
  const strictCase = base({ input: [{ a: 1 }, null], strict: true, expect_error: { code: "input.not_mapping" } });
  checkCase(strictCase, FIXTURE);
  assert.throws(() => runCase({ ...strictCase, strict: false }, FIXTURE), TypeError);
});

test("a null input reaches the stage as null and a null item as a null item", () => {
  assert.throws(() => runCase(base({ input: null, expect: [] }), FIXTURE), TypeError);
  checkCase(base({ input: [{ a: 1 }, null], strict: true, expect_error: { code: "input.not_mapping" } }), FIXTURE);
  // and dedupe without a key hashes a null item without complaint
  checkCase(
    base({ stage: "dedupe", args: {}, input: [null, null, { a: 1 }], strict: true, expect: [null, { a: 1 }] }),
    FIXTURE
  );
});

for (const name of ["constructor", "__proto__", "toString", "hasOwnProperty", "valueOf"]) {
  test(`a stage named ${name} is an unknown stage, not an inherited property`, () => {
    assert.throws(
      () => runCase(base({ stage: name, args: {}, expect: [] }), FIXTURE),
      /unknown stage/
    );
    assert.throws(
      () =>
        runCase(
          base({ stage: "pipeline", args: { stages: [{ stage: name, args: {} }] }, expect: [] }),
          FIXTURE
        ),
      /unknown stage/
    );
  });
}

test("a nested stage must be a record stage", () => {
  assert.throws(
    () =>
      runCase(
        base({ stage: "pipeline", args: { stages: [{ stage: "merge", args: {} }] }, expect: [] }),
        FIXTURE
      ),
    /unknown stage "merge"/
  );
});
