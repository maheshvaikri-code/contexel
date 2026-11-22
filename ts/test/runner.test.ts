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
    [
      ...Object.keys(RECORD_STAGES),
      "as_records",
      "join",
      "text_pipeline",
      "merge",
      "pipeline",
      "shaped",
      "trace_report",
      "trace_dropped_ids",
    ].sort()
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

for (const kind of ["pipeline", "shaped", "text_pipeline", "trace_report", "trace_dropped_ids"]) {
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

test("a trace_dropped_ids case without a non-empty string id_field is rejected", () => {
  // with no id field nothing is attributed and [[]] would pass vacuously
  const stages = [{ stage: "select", args: { fields: ["a"] } }];
  for (const args of [{ stages }, { stages, id_field: "" }, { stages, id_field: 1 }]) {
    const c = base({ id: "t/no_id_field", stage: "trace_dropped_ids", args, expect: [[]] });
    assert.throws(
      () => checkCase(c, FIXTURE),
      /case t\/no_id_field: trace_dropped_ids needs a non-empty string id_field/
    );
  }
});

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

/* ---- payload kinds (Slice 4): as_records, join, text_pipeline, split ---- */

const NL = String.fromCharCode(10);

test("split is a record stage: valid on its own and as a nested stage", () => {
  checkCase(
    base({
      stage: "split",
      args: { by: "size", size: 2, into: "part" },
      input: [{ text: "abcde" }],
      expect: [
        { text: "ab", part: { index: 0, start: 0, end: 2 } },
        { text: "cd", part: { index: 1, start: 2, end: 4 } },
        { text: "e", part: { index: 2, start: 4, end: 5 } },
      ],
    }),
    FIXTURE
  );
  checkCase(
    base({
      stage: "pipeline",
      args: { stages: [{ stage: "split", args: { by: "lines" } }] },
      input: [{ text: "a" + NL + "b" }],
      expect: [
        { text: "a" + NL, chunk: { index: 0, start: 0, end: 2 } },
        { text: "b", chunk: { index: 1, start: 2, end: 3 } },
      ],
    }),
    FIXTURE
  );
});

for (const kind of ["split", "as_records", "join", "text_pipeline"]) {
  test(`an unknown argument name for ${kind} is rejected, not ignored`, () => {
    // `fields` and `separator` are typos for `field` and `sep`: ignoring them would default
    const stages = [{ stage: "split", args: {} }];
    for (const bad of ["fields", "separator", "chunk_size", "Field"]) {
      const args: Record<string, unknown> = kind === "text_pipeline" ? { stages, [bad]: "x" } : { [bad]: "x" };
      assert.throws(
        () => runCase(base({ stage: kind, args, input: [{ text: "a" }], expect: [] }), FIXTURE),
        new RegExp(`unknown argument "${bad}" for stage ${kind}`)
      );
    }
  });
}

test("a text_pipeline with an unknown nested stage is rejected", () => {
  const c = base({
    stage: "text_pipeline",
    args: { stages: [{ stage: "no_such_stage", args: {} }] },
    input: "a",
    expect: "a",
  });
  assert.throws(() => runCase(c, FIXTURE), /stages\[0\]: unknown stage "no_such_stage"/);
});

test("a text_pipeline nested stage must be a record stage, and its arguments are checked", () => {
  for (const nested of ["as_records", "join", "text_pipeline", "merge"]) {
    const c = base({
      stage: "text_pipeline",
      args: { stages: [{ stage: nested, args: {} }] },
      input: "a",
      expect: "a",
    });
    assert.throws(() => runCase(c, FIXTURE), new RegExp(`unknown stage "${nested}"`));
  }
  const typo = base({
    stage: "text_pipeline",
    args: { stages: [{ stage: "split", args: { by: "lines", sizes: 3 } }] },
    input: "a",
    expect: "a",
  });
  assert.throws(() => runCase(typo, FIXTURE), /stages\[0\]: unknown argument "sizes" for stage split/);
});

test("a text_pipeline needs its stages to be a list", () => {
  const c = base({ stage: "text_pipeline", args: { stages: "split" }, input: "a", expect: "a" });
  assert.throws(() => runCase(c, FIXTURE), /args\.stages must be a list/);
});

test("a text_pipeline runs asRecords, the stages, then join, with field and sep defaulted", () => {
  const stages = [{ stage: "split", args: { by: "lines" } }];
  checkCase(
    base({ stage: "text_pipeline", args: { stages }, input: "a" + NL + "b" + NL, expect: "a" + NL + "b" + NL }),
    FIXTURE
  );
  // a named field is used for the wrap, the stage and the join; sep joins the chunks
  checkCase(
    base({
      stage: "text_pipeline",
      args: { field: "body", sep: "|", stages: [{ stage: "split", args: { field: "body", by: "size", size: 2 } }] },
      input: "abcde",
      expect: "ab|cd|e",
    }),
    FIXTURE
  );
  // the stages really run: dedupe drops the repeated chunk
  checkCase(
    base({
      stage: "text_pipeline",
      args: { stages: [{ stage: "split", args: {} }, { stage: "dedupe", args: { key: "text" } }] },
      input: ["x" + NL + "x" + NL + "y"],
      expect: "x" + NL + "y",
    }),
    FIXTURE
  );
});

test("a text_pipeline expect_error case checks the code the pipeline throws", () => {
  const stages = [{ stage: "split", args: {} }];
  checkCase(
    base({ stage: "text_pipeline", args: { stages }, input: null, expect_error: { code: "input.not_list" } }),
    FIXTURE
  );
  assert.throws(
    () =>
      checkCase(
        base({ stage: "text_pipeline", args: { stages }, input: null, expect_error: { code: "input.not_mapping" } }),
        FIXTURE
      ),
    /wrong error code/
  );
});

test("as_records and join cases pass on the right output and fail on a wrong one", () => {
  checkCase(base({ stage: "as_records", args: { field: "body" }, input: "x", expect: [{ body: "x" }] }), FIXTURE);
  checkCase(base({ stage: "join", args: { sep: "-" }, input: [{ text: "a" }, { text: "b" }], expect: "a-b" }), FIXTURE);
  assert.throws(
    () => checkCase(base({ stage: "as_records", args: {}, input: "x", expect: [{ body: "x" }] }), FIXTURE),
    assert.AssertionError
  );
  assert.throws(
    () => checkCase(base({ stage: "join", args: {}, input: [{ text: "a" }], expect: "b" }), FIXTURE),
    assert.AssertionError
  );
});

test("as_records and join pass a null input through as null", () => {
  checkCase(base({ stage: "as_records", args: {}, input: null, expect_error: { code: "input.not_list" } }), FIXTURE);
  checkCase(base({ stage: "join", args: {}, input: null, expect_error: { code: "input.not_list" } }), FIXTURE);
  checkCase(
    base({ stage: "join", args: {}, input: [{ text: "a" }, null], expect_error: { code: "input.not_mapping" } }),
    FIXTURE
  );
  checkCase(
    base({ stage: "as_records", args: { field: "" }, input: "x", expect_error: { code: "config.invalid_value" } }),
    FIXTURE
  );
});

test("the payload kinds are not strict-dependent: strict true changes nothing", () => {
  checkCase(base({ stage: "as_records", args: {}, input: "x", strict: true, expect: [{ text: "x" }] }), FIXTURE);
  checkCase(base({ stage: "join", args: {}, input: null, strict: true, expect_error: { code: "input.not_list" } }), FIXTURE);
  checkCase(
    base({ stage: "split", args: {}, input: [{ text: "a" + NL + "b" }, 1], strict: true, expect_error: { code: "input.not_mapping" } }),
    FIXTURE
  );
});
