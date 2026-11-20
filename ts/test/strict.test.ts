/**
 * Strict mode (ADR-003): opt-in shape validation that names the stage and the
 * item index, never changes a successful result, and holds in a worker thread
 * when the pipeline or shaper turns it on itself. Mirrors tests/test_strict.py.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { Worker } from "node:worker_threads";

import {
  ContexelError,
  InputShapeError,
  allowlist,
  dedupe,
  isStrict,
  pipeline,
  quarantine,
  rank,
  rescore,
  select,
  shaped,
  stage,
  strict,
  trace,
  trimToBudget,
  truncateField,
  type Records,
} from "../src/index.js";

const vectors = JSON.parse(
  readFileSync(new URL("../../../parity/vectors.json", import.meta.url), "utf-8")
);
const FIXTURE: Records = vectors.fixture;

// every stage with arguments that are valid on a list of {"a": ...} records
const CALLS: Record<string, (r: unknown) => unknown> = {
  select: (r) => select(r as Records, { fields: ["a"] }),
  dedupe: (r) => dedupe(r as Records, { key: ["a"] }),
  rank: (r) => rank(r as Records, { by: "a" }),
  allowlist: (r) => allowlist(r as Records, { field: "a", allowed: ["x"] }),
  quarantine: (r) => quarantine(r as Records, { fields: ["a"] }),
  rescore: (r) => rescore(r as Records, { query: "x", fields: ["a"] }),
  truncate_field: (r) => truncateField(r as Records, { field: "a", maxTokens: 5 }),
  trim_to_budget: (r) => trimToBudget(r as Records, { maxTokens: 10 }),
};
const NEEDS_MAPPING = Object.keys(CALLS).filter((k) => k !== "trim_to_budget");

function shapeError(fn: () => unknown): InputShapeError {
  try {
    fn();
  } catch (e) {
    assert.ok(e instanceof InputShapeError, `expected InputShapeError, got ${String(e)}`);
    return e;
  }
  assert.fail("expected an InputShapeError, nothing was thrown");
}

test("strict off keeps today's lenient behavior", () => {
  assert.ok(!isStrict());
  assert.deepStrictEqual(dedupe([1, 1, 2] as never), [1, 2]); // items need not be mappings
  assert.deepStrictEqual(rank([3, 1, 2] as never, { by: (x) => x }), [3, 2, 1]);
  assert.throws(
    // still a raw error, as before
    () => select(null as never, { fields: ["a"] }),
    (e: unknown) => e instanceof TypeError && !(e instanceof ContexelError)
  );
});

for (const name of Object.keys(CALLS)) {
  for (const bad of [null, "abc", { a: 1 }, 5]) {
    test(`strict rejects a non-list and names the stage: ${name} ${JSON.stringify(bad)}`, () => {
      const e = strict(() => shapeError(() => CALLS[name](bad)));
      assert.strictEqual(e.code, "input.not_list");
      assert.strictEqual(e.stage, name);
      assert.ok(e.message.includes(name));
    });
  }
}

for (const name of NEEDS_MAPPING) {
  test(`strict rejects a non-mapping item and names the index: ${name}`, () => {
    const records = [{ a: "x" }, { a: "y" }, 7, { a: "z" }];
    const e = strict(() => shapeError(() => CALLS[name](records)));
    assert.strictEqual(e.code, "input.not_mapping");
    assert.strictEqual(e.stage, name);
    assert.ok(e.message.includes("item 2"));
  });
}

test("strict treats an array item, null and undefined as not a mapping", () => {
  for (const bad of [[1], null, undefined, "s", true]) {
    const e = strict(() => shapeError(() => select([{ a: 1 }, bad] as never, { fields: ["a"] })));
    assert.strictEqual(e.code, "input.not_mapping");
    assert.ok(e.message.includes("item 1"));
  }
});

test("strict does not require a mapping where the stage does not index one", () => {
  strict(() => {
    assert.deepStrictEqual(trimToBudget([1, 2, 3] as never, { maxTokens: 100 }), [1, 2, 3]);
    assert.deepStrictEqual(dedupe([1, 1, 2] as never), [1, 2]); // key absent hashes the item
    assert.deepStrictEqual(rank([3, 1, 2] as never, { by: (x) => x }), [3, 2, 1]); // a key function takes anything
    assert.throws(() => dedupe([1, 1, 2] as never, { key: "a" }), InputShapeError); // a key does index the item
    assert.throws(() => rank([3, 1, 2] as never, { by: "a" }), InputShapeError);
  });
});

test("the flag is scoped to the block and nests", () => {
  assert.ok(!isStrict());
  strict(() => {
    assert.ok(isStrict());
    strict(() => assert.ok(isStrict()));
    assert.ok(isStrict());
  });
  assert.ok(!isStrict());
  assert.throws(
    () =>
      strict(() => {
        throw new RangeError("boom");
      }),
    RangeError
  );
  assert.ok(!isStrict());
});

test("strict returns the value of the function it runs", () => {
  assert.strictEqual(
    strict(() => 42),
    42
  );
});

test("the flag follows await inside a strict block and is gone after it", async () => {
  await strict(async () => {
    await new Promise((r) => setTimeout(r, 1));
    assert.ok(isStrict());
    await Promise.resolve();
    assert.ok(isStrict());
  });
  assert.ok(!isStrict());
});

test("two concurrent async tasks do not see each other's strict flag", async () => {
  const strictTask = strict(async () => {
    await new Promise((r) => setTimeout(r, 5));
    return isStrict();
  });
  const lenientTask = (async () => {
    await new Promise((r) => setTimeout(r, 1));
    return isStrict();
  })();
  assert.deepStrictEqual(await Promise.all([strictTask, lenientTask]), [true, false]);
});

test("strict check runs before trace", () => {
  const e = strict(() =>
    trace(null, () => shapeError(() => select(null as never, { fields: ["a"] })))
  )[0]; // not a raw records.length TypeError
  assert.strictEqual(e.code, "input.not_list");
});

test("strict shape check comes before configuration validation", () => {
  const e = strict(() => shapeError(() => select(null as never, { fields: 5 as never })));
  assert.strictEqual(e.code, "input.not_list");
});

const here = new URL("../src/index.js", import.meta.url).href;

/** Run `body` (CommonJS text) in a worker thread that has the library loaded as
 * `lib`; resolves with whatever the body posts. */
function inWorker(body: string): Promise<Record<string, unknown>> {
  const code = `
    const { parentPort } = require("node:worker_threads");
    import(${JSON.stringify(here)}).then(async (lib) => {
      try { ${body} } catch (e) {
        parentPort.postMessage({
          name: e.constructor.name, code: e.code, stage: e.stage,
          contexel: e instanceof lib.ContexelError, typeError: e instanceof TypeError });
      }
    });`;
  return new Promise((resolve, reject) => {
    const w = new Worker(code, { eval: true });
    w.once("message", resolve);
    w.once("error", reject);
  });
}

test("pipeline strict holds in a worker thread", async () => {
  const seen = await inWorker(`
    const pipe = lib.pipeline([lib.stage(lib.select, { fields: ["a"] })], { strict: true });
    pipe(null);
    parentPort.postMessage({ name: "no error" });`);
  assert.strictEqual(seen.name, "InputShapeError");
  assert.strictEqual(seen.code, "input.not_list");
});

test("a bare strict block is not inherited by a new worker (the documented caveat)", async () => {
  const seen = await strict(() =>
    inWorker(`
      lib.select(null, { fields: ["a"] });
      parentPort.postMessage({ name: "no error" });`)
  );
  assert.strictEqual(seen.contexel, false); // a raw TypeError, not a typed error
  assert.strictEqual(seen.typeError, true);
});

test("pipeline strict names the stage that returned a non-list", () => {
  const returnsNull = function returnsNull(_records: Records): Records {
    return null as never;
  };
  const pipe = pipeline(
    [stage(select, { fields: ["a"] }), returnsNull, stage(select, { fields: ["a"] })],
    { strict: true }
  );
  const e = shapeError(() => pipe([{ a: 1 }]));
  assert.strictEqual(e.code, "input.not_list");
  assert.strictEqual(e.stage, "returnsNull");
  assert.ok(e.message.includes("stage 1"));
});

test("pipeline strict names a bound custom stage and an anonymous one", () => {
  const bad = (_r: Records): Records => undefined as never;
  const named = pipeline([stage(select, { fields: ["a"] }), stage(bad, {})], { strict: true });
  assert.strictEqual(shapeError(() => named([{ a: 1 }])).stage, "bad");
  const anonymous = pipeline([(_r: Records) => null as never], { strict: true });
  assert.strictEqual(shapeError(() => anonymous([{ a: 1 }])).stage, "callable");
});

test("a library stage given a non-list inside a strict pipeline reports its own name", () => {
  const pipe = pipeline([(_r: Records) => [{ a: 1 }, 7] as never, stage(select, { fields: ["a"] })], {
    strict: true,
  });
  const e = shapeError(() => pipe([]));
  assert.deepStrictEqual([e.code, e.stage], ["input.not_mapping", "select"]);
});

test("pipeline without strict lets the next stage fail obscurely", () => {
  const returnsNull = function returnsNull(_records: Records): Records {
    return null as never;
  };
  const pipe = pipeline([returnsNull, stage(select, { fields: ["a"] })]);
  assert.throws(
    () => pipe([{ a: 1 }]),
    (e: unknown) => e instanceof TypeError && !(e instanceof ContexelError)
  );
});

test("pipeline strict does not check the pipeline input itself", () => {
  const pipe = pipeline([(_r: Records) => [{ a: 1 }]], { strict: true });
  assert.deepStrictEqual(pipe(null as never), [{ a: 1 }]);
});

test("pipeline strict puts the stages in strict mode", () => {
  const seen: boolean[] = [];
  const probe = (r: Records): Records => {
    seen.push(isStrict());
    return r;
  };
  pipeline([probe], { strict: true })([]);
  pipeline([probe])([]);
  assert.deepStrictEqual(seen, [true, false]);
  assert.ok(!isStrict());
});

test("shaped strict rejects a null return", () => {
  const tool = shaped([stage(select, { fields: ["a"] })], { strict: true })(
    (): Records => null as never
  );
  const e = shapeError(() => tool());
  assert.deepStrictEqual([e.code, e.stage], ["input.not_list", "shaped"]);
});

test("shaped without strict does not add the list check", () => {
  const tool = shaped([(r: Records) => ["ok"] as never])((): Records => null as never);
  assert.deepStrictEqual(tool(), ["ok"]);
});

test("shaped strict holds for async tools and in a worker thread", async () => {
  const tool = shaped([stage(select, { fields: ["a"] })], { strict: true })(
    async (): Promise<Records> => "not a list" as never
  );
  await assert.rejects(
    async () => tool(),
    (e: unknown) => e instanceof InputShapeError && e.stage === "shaped"
  );
  const seen = await inWorker(`
    const tool = lib.shaped([lib.stage(lib.select, { fields: ["a"] })], { strict: true })(
      async () => "not a list");
    await tool();
    parentPort.postMessage({ name: "no error" });`);
  assert.strictEqual(seen.name, "InputShapeError");
});

test("shaped strict with a list of stages also checks each stage's output", () => {
  const returnsNull = function returnsNull(_records: Records): Records {
    return null as never;
  };
  const tool = shaped([stage(select, { fields: ["a"] }), returnsNull], { strict: true })(
    (): Records => [{ a: 1 }]
  );
  const e = shapeError(() => tool());
  assert.deepStrictEqual([e.code, e.stage], ["input.not_list", "returnsNull"]);
});

test("shaped with a prebuilt pipeline runs it in strict mode", () => {
  const pipe = pipeline([stage(select, { fields: ["a"] })]);
  const tool = shaped(pipe, { strict: true })((): Records => [{ a: 1 }, 5] as never);
  assert.strictEqual(shapeError(() => tool()).code, "input.not_mapping");
});

test("strict does not change the fingerprint", () => {
  const stages = [stage(select, { fields: ["a"] }), stage(dedupe, { key: ["a"] })];
  assert.strictEqual(pipeline(stages, { strict: true }).fingerprint, pipeline(stages).fingerprint);
});

test("strict never changes a successful result", () => {
  const stages = [
    stage(allowlist, { field: "source", allowed: ["repo", "docs"] }),
    stage(quarantine, { fields: ["snippet"] }),
    stage(select, { fields: ["path", "line", "source", "snippet"] }),
    stage(dedupe, { key: ["path", "line"] }),
    stage(rescore, { query: "exponential backoff jitter", fields: ["snippet", "path"] }),
    stage(truncateField, { field: "snippet", maxTokens: 12 }),
    stage(rank, { by: "score", desc: true }),
    stage(trimToBudget, { maxTokens: 150 }),
  ];
  const lenient = pipeline(stages)(FIXTURE);
  assert.deepStrictEqual(pipeline(stages, { strict: true })(FIXTURE), lenient);
  assert.deepStrictEqual(
    strict(() => pipeline(stages)(FIXTURE)),
    lenient
  );
  assert.ok(lenient.length > 0);
});
