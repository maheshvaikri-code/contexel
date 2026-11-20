/**
 * Configuration validation (ADR-003): a misconfigured call always throws a
 * typed ConfigError — strict mode is not needed — and never silently does
 * something else. Mirrors tests/test_config_validation.py. `param` is the
 * TypeScript option name (maxTokens, replacePatterns).
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ConfigError,
  InputShapeError,
  allowlist,
  dedupe,
  quarantine,
  rank,
  rescore,
  select,
  trimToBudget,
  truncateField,
  type Records,
} from "../src/index.js";

const RECS: Records = [
  { a: "x y", n: 1 },
  { a: "y z", n: 2 },
];

function raised(fn: () => unknown): ConfigError {
  try {
    fn();
  } catch (e) {
    assert.ok(e instanceof ConfigError, `expected ConfigError, got ${String(e)}`);
    return e;
  }
  assert.fail("expected a ConfigError, nothing was thrown");
}

test("rescore unknown match raises", () => {
  for (const bad of ["fuzzy", "WORD", "", null, 5, ["word"]]) {
    const e = raised(() => rescore(RECS, { query: "x", fields: ["a"], match: bad as never }));
    assert.deepStrictEqual(
      [e.code, e.stage, e.param],
      ["config.invalid_value", "rescore", "match"],
      `match ${JSON.stringify(bad)}`
    );
  }
  assert.ok(rescore(RECS, { query: "x", fields: ["a"], match: "word" }));
  assert.ok(rescore(RECS, { query: "x", fields: ["a"], match: "substring" }));
});

test("rescore match stem is reserved until the stemmer ships", () => {
  const e = raised(() => rescore(RECS, { query: "x", fields: ["a"], match: "stem" as never }));
  assert.strictEqual(e.code, "config.invalid_value");
  assert.ok(e.message.includes("not available yet"));
});

test("rescore empty fields raises", () => {
  const e = raised(() => rescore(RECS, { query: "x", fields: [] }));
  assert.deepStrictEqual([e.code, e.param], ["config.empty", "fields"]);
});

const RESCORE_BAD: Array<[Record<string, unknown>, string]> = [
  [{ query: null }, "query"],
  [{ query: 5 }, "query"],
  [{ query: undefined }, "query"],
  [{ query: "x", fields: 5 }, "fields"],
  [{ query: "x", fields: [1] }, "fields"],
  [{ query: "x", fields: null }, "fields"],
  [{ query: "x", into: 5 }, "into"],
  [{ query: "x", into: null }, "into"],
  [{ query: "x", proximity: "yes" }, "proximity"],
  [{ query: "x", proximity: 1 }, "proximity"],
  [{ query: "x", proximity: null }, "proximity"],
];
for (const [options, param] of RESCORE_BAD) {
  test(`rescore wrong-typed parameter raises: ${JSON.stringify(options)}`, () => {
    const e = raised(() => rescore(RECS, { fields: ["a"], ...options } as never));
    assert.deepStrictEqual([e.code, e.param], ["config.invalid_value", param]);
  });
}

test("configuration errors throw even with no records and no strict mode", () => {
  assert.strictEqual(
    raised(() => rescore([], { query: "x", match: "fuzzy" as never })).code,
    "config.invalid_value"
  );
  assert.strictEqual(raised(() => trimToBudget([], { maxTokens: -1 })).code, "config.invalid_value");
  assert.strictEqual(raised(() => quarantine([], { fields: [] })).code, "config.empty");
  // an empty query is not a configuration error: it scores everything 0.0
  assert.deepStrictEqual(
    rescore(RECS, { query: "", fields: ["a"] }),
    RECS.map((r) => ({ ...r, score: 0 }))
  );
});

const BAD_MAX_TOKENS = [null, undefined, -1, -100, 1.5, "10", true, false, [10], NaN, Infinity];
for (const bad of BAD_MAX_TOKENS) {
  test(`maxTokens must be a non-negative integer: ${String(bad)}`, () => {
    for (const call of [
      () => trimToBudget(RECS, { maxTokens: bad as never }),
      () => truncateField(RECS, { field: "a", maxTokens: bad as never }),
    ]) {
      const e = raised(call);
      assert.deepStrictEqual([e.code, e.param], ["config.invalid_value", "maxTokens"]);
      assert.ok(!(e instanceof InputShapeError) && !(e instanceof TypeError));
    }
  });
}

test("maxTokens zero returns empty and stays valid", () => {
  assert.deepStrictEqual(trimToBudget(RECS, { maxTokens: 0 }), []);
  assert.ok(truncateField(RECS, { field: "a", maxTokens: 0 })); // clips to the minimum, never throws
});

test("a boolean is not a valid maxTokens", () => {
  assert.strictEqual(
    raised(() => trimToBudget(RECS, { maxTokens: true as never })).code,
    "config.invalid_value"
  );
  assert.strictEqual(
    raised(() => truncateField(RECS, { field: "a", maxTokens: true as never })).code,
    "config.invalid_value"
  );
});

for (const bad of [-1, 1.5, null, true, "1"]) {
  test(`minRecords must be a non-negative integer: ${JSON.stringify(bad)}`, () => {
    const e = raised(() => trimToBudget(RECS, { maxTokens: 10, minRecords: bad as never }));
    assert.strictEqual(e.param, "minRecords");
  });
}

test("minRecords valid values keep the first records over a too-small budget", () => {
  assert.deepStrictEqual(trimToBudget(RECS, { maxTokens: 0, minRecords: 1 }), RECS.slice(0, 1));
});

test("truncate_field field and suffix must be strings", () => {
  assert.strictEqual(raised(() => truncateField(RECS, { field: 5 as never, maxTokens: 10 })).param, "field");
  assert.strictEqual(
    raised(() => truncateField(RECS, { field: "a", maxTokens: 10, suffix: null as never })).param,
    "suffix"
  );
});

for (const bad of [null, 5, 1.5, ["a", 1], { a: 1 }, new Set(["a"]), true]) {
  test(`fields must be a string or a list of strings: ${JSON.stringify(bad)}`, () => {
    for (const call of [
      () => select(RECS, { fields: bad as never }),
      () => quarantine(RECS, { fields: bad as never }),
      () => rescore(RECS, { query: "x", fields: bad as never }),
    ]) {
      const e = raised(call);
      assert.deepStrictEqual([e.code, e.param], ["config.invalid_value", "fields"]);
    }
  });
}

test("a string and a list are valid fields and a bare string is one field", () => {
  const one = RECS.map((r) => ({ a: r.a }));
  assert.deepStrictEqual(select(RECS, { fields: "a" }), one);
  assert.deepStrictEqual(select(RECS, { fields: ["a"] }), one);
});

test("select with an empty field list stays valid", () => {
  assert.deepStrictEqual(select(RECS, { fields: [] }), [{}, {}]);
});

test("dedupe key must be null, a string or a list of strings", () => {
  assert.strictEqual(raised(() => dedupe(RECS, { key: 5 as never })).param, "key");
  assert.strictEqual(raised(() => dedupe(RECS, { key: ["a", 1] as never })).param, "key");
  assert.deepStrictEqual(dedupe(RECS, { key: null }), RECS);
  assert.deepStrictEqual(dedupe(RECS), RECS);
  assert.deepStrictEqual(dedupe(RECS, { key: "a" }), RECS);
  assert.deepStrictEqual(dedupe(RECS, { key: ["a"] }), RECS);
});

const RANK_BAD: Array<[unknown, unknown, string]> = [
  [5, true, "by"],
  [null, true, "by"],
  [["n"], true, "by"],
  ["n", 1, "desc"],
  ["n", null, "desc"],
];
for (const [by, desc, param] of RANK_BAD) {
  test(`rank by and desc are validated: ${JSON.stringify([by, desc])}`, () => {
    assert.strictEqual(raised(() => rank(RECS, { by, desc } as never)).param, param);
  });
}

test("rank accepts a field name and a key function", () => {
  assert.deepStrictEqual(rank(RECS, { by: "n" }), [...RECS].reverse());
  assert.deepStrictEqual(rank(RECS, { by: (r) => r.n, desc: false }), RECS);
});

const QUARANTINE_BAD: Array<[Record<string, unknown>, string]> = [
  [{ into: 5 }, "into"],
  [{ replacePatterns: 1 }, "replacePatterns"],
  [{ patterns: 5 }, "patterns"],
  [{ patterns: ["ok", 5] }, "patterns"],
];
for (const [options, param] of QUARANTINE_BAD) {
  test(`quarantine wrong-typed parameter raises: ${JSON.stringify(options)}`, () => {
    const e = raised(() => quarantine(RECS, { fields: ["a"], ...options } as never));
    assert.deepStrictEqual([e.code, e.param], ["config.invalid_value", param]);
  });
}

test("every configuration error carries its stage name", () => {
  const cases: Record<string, () => unknown> = {
    select: () => select(RECS, { fields: 5 as never }),
    dedupe: () => dedupe(RECS, { key: 5 as never }),
    rank: () => rank(RECS, { by: 5 as never }),
    allowlist: () => allowlist(RECS, { field: "a", allowed: null as never }),
    quarantine: () => quarantine(RECS, { fields: 5 as never }),
    rescore: () => rescore(RECS, { query: null as never }),
    truncate_field: () => truncateField(RECS, { field: "a", maxTokens: null as never }),
    trim_to_budget: () => trimToBudget(RECS, { maxTokens: null as never }),
  };
  for (const [name, call] of Object.entries(cases)) {
    assert.strictEqual(raised(call).stage, name);
  }
});
