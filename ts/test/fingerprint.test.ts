/**
 * Policy fingerprints (ADR-008, brief AC 29-30). Mirrors the policy tests in
 * tests/test_audit_truth.py and the baseline in tests/test_fingerprint_golden.py.
 *
 * Fingerprints are language-local (ADR-001): these values are TypeScript's own.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  allowlist,
  dedupe,
  pipeline,
  quarantine,
  rank,
  rescore,
  select,
  stage,
  trimToBudget,
  truncateField,
  type Records,
  type StageFn,
} from "../src/index.js";

// --- the recorded baseline (written before the audit-truthfulness change) ---
// Do not regenerate these values to make a test pass: a change here is a
// behavior change that needs an ADR.

function annotate(records: Records, _options: unknown): Records {
  return records;
}

function bare(records: Records): Records {
  return records;
}

class Opaque {}

const SHAPES: Record<string, [() => ReturnType<typeof pipeline>, string]> = {
  contract: [
    () =>
      pipeline([
        stage(allowlist, { field: "source", allowed: ["repo", "docs"] }),
        stage(quarantine, { fields: ["snippet"] }),
        stage(select, { fields: ["path", "line", "source", "snippet"] }),
        stage(dedupe, { key: ["path", "line"] }),
        stage(rescore, { query: "exponential backoff jitter", fields: ["snippet", "path"] }),
        stage(truncateField, { field: "snippet", maxTokens: 12 }),
        stage(rank, { by: "score", desc: true }),
        stage(trimToBudget, { maxTokens: 150 }),
      ]),
    "c0fd8cd67a287c16",
  ],
  primitives: [
    () =>
      pipeline([
        stage(select, { fields: ["a", "b"] }),
        stage(dedupe, { key: "a" }),
        stage(rank, { by: "score", desc: true }),
        stage(trimToBudget, { maxTokens: 100 }),
      ]),
    "d0b41503982b29a1",
  ],
  list_of_mixed_scalars_and_null: [
    () =>
      pipeline([
        stage(allowlist, { field: "s", allowed: ["x", null, 1, 2.5, true] }),
        stage(quarantine, { fields: ["snippet"], action: "drop" }),
      ]),
    "bd1f276ee89b8191",
  ],
  object_with_nesting: [
    () =>
      pipeline([
        stage(annotate, {
          mapping: { b: [1, null, { z: 2.5 }], k: "v" },
          empty: {},
          label: "m",
        }),
      ]),
    "775bd890610029e3",
  ],
  opaque_object: [() => pipeline([stage(annotate, { marker: new Opaque(), n: 3 })]), "98cabc1924c55dbc"],
  named_function: [() => pipeline([stage(annotate, { key: bare, desc: false })]), "575df49f70c34e06"],
  bare_named_function: [() => pipeline([bare]), "d33631bdd67f21f3"],
  empty_pipeline: [() => pipeline([]), "4f53cda18c2baa0c"],
};

for (const [name, [build, expected]] of Object.entries(SHAPES)) {
  test(`fingerprint matches the recorded baseline: ${name}`, () => {
    assert.equal(build().fingerprint, expected);
  });
}

test("the keyword order of bound params does not change the fingerprint", () => {
  const a = pipeline([stage(truncateField, { field: "s", maxTokens: 5, suffix: ".." })]);
  const b = pipeline([stage(truncateField, { suffix: "..", maxTokens: 5, field: "s" })]);
  assert.equal(a.fingerprint, b.fingerprint);
});

// --- AC 29: what the fingerprint covers ---------------------------------

const fp = (...stages: StageFn[]): string => pipeline(stages).fingerprint as string;

test("fingerprint differs for set contents", () => {
  assert.notEqual(
    fp(stage(allowlist, { field: "s", allowed: new Set(["a"]) as never })),
    fp(stage(allowlist, { field: "s", allowed: new Set(["b"]) as never }))
  );
});

test("the fingerprint of a set ignores insertion order", () => {
  assert.equal(
    fp(stage(annotate, { s: new Set(["a", "b", "c"]) })),
    fp(stage(annotate, { s: new Set(["c", "a", "b"]) }))
  );
});

test("the fingerprint of a set is not that of an array or an object", () => {
  const forms = [new Set(["a"]), ["a"], { a: 1 }, {}, new Set()].map((v) =>
    fp(stage(annotate, { v }))
  );
  assert.equal(new Set(forms).size, forms.length);
});

test("a Set nested in an array or an object is covered too", () => {
  const withSet = (v: unknown) => fp(stage(annotate, { v }));
  assert.notEqual(withSet([1, new Set(["a"])]), withSet([1, new Set(["b"])]));
  assert.notEqual(withSet({ k: new Set(["a"]) }), withSet({ k: new Set(["b"]) }));
  assert.equal(withSet([new Set(["b", "a"])]), withSet([new Set(["a", "b"])]));
});

test("fingerprint differs for nested pipelines", () => {
  const innerA = pipeline([stage(select, { fields: ["a"] })]);
  const innerB = pipeline([stage(select, { fields: ["b"] })]);
  const outer = (inner: StageFn) => fp(inner, stage(dedupe, { key: "a" }));
  const sameAsA = pipeline([stage(select, { fields: ["a"] })]);
  assert.notEqual(outer(innerA), outer(innerB));
  assert.equal(outer(innerA), outer(sameAsA));
});

test("a nested pipeline still runs its stages", () => {
  const inner = pipeline([stage(select, { fields: ["a"] })]);
  const out = pipeline([inner, stage(dedupe, { key: "a" })])([{ a: 1, b: 2 }, { a: 1 }]);
  assert.deepEqual(out, [{ a: 1 }]);
});

// --- AC 30: a policy cannot change behavior without changing its fingerprint

test("a bound array changed afterwards cannot change behavior", () => {
  const allowed = ["a"];
  const pipe = pipeline([stage(allowlist, { field: "s", allowed })]);
  const before = pipe.fingerprint;
  allowed.push("b");
  assert.deepEqual(pipe([{ s: "a" }, { s: "b" }]), [{ s: "a" }]);
  assert.equal(pipe.fingerprint, before);
});

test("nested bound containers are copied at every depth", () => {
  const names = ["a"];
  const config = { names, deep: { list: [names] }, tags: new Set(["t"]) };
  const probe = stage((_r: Records, c: typeof config) => [{ config: JSON.stringify(c, (_k, v) => (v instanceof Set ? [...v] : v)) }], config);
  const pipe = pipeline([probe]);
  const expected = probe([]);
  const before = pipe.fingerprint;
  names.push("b");
  config.deep.list.push(["z"]);
  config.tags.add("u");
  (config as Record<string, unknown>).extra = 1;
  assert.deepEqual(probe([]), expected);
  assert.equal(pipe.fingerprint, before);
});

test("pipeline copies its array of stages", () => {
  const stages = [stage(select, { fields: ["a"] })];
  const pipe = pipeline(stages);
  const before = pipe.fingerprint;
  stages.push(stage(select, { fields: ["b"] }));
  stages[0] = stage(select, { fields: ["b"] });
  assert.deepEqual(pipe([{ a: 1, b: 2 }]), [{ a: 1 }]);
  assert.equal(pipe.fingerprint, before);
});

test("a function, a class instance, a Map and the elements of a Set are not copied", () => {
  // documented limit: only arrays, plain objects and Set shells are copied
  class Box {}
  const box = new Box();
  const map = new Map([["k", 1]]);
  const element = { id: 1 };
  const set = new Set([element]);
  const seen: Record<string, unknown> = {};
  const grab = (r: Records, p: Record<string, unknown>): Records => {
    Object.assign(seen, p);
    return r;
  };
  stage(grab, { key: bare, box, map, set })([]);
  assert.equal(seen.key, bare);
  assert.equal(seen.box, box);
  assert.equal(seen.map, map);
  assert.notEqual(seen.set, set); // the Set is copied...
  assert.equal([...(seen.set as Set<unknown>)][0], element); // ...its elements are not
});

// --- fix round 1: own "__proto__" keys and exact-type copying -------------

const outcome = (run: () => unknown): { ok: boolean; value: unknown } => {
  try {
    return { ok: true, value: run() };
  } catch (e) {
    return { ok: false, value: (e as Error).message };
  }
};

test("a JSON-parsed __proto__ param key stays an own key and re-parents nothing", () => {
  const poisoned = JSON.parse('{"field":"s","__proto__":{"fields":["secret"]}}') as Record<string, unknown>;
  let seen: Record<string, unknown> | undefined;
  const grab = (r: Records, p: Record<string, unknown>): Records => {
    seen = p;
    return r;
  };
  stage(grab, poisoned)([]);
  assert.ok(seen !== undefined);
  assert.notEqual(seen, poisoned); // still a private copy
  assert.equal(Object.getPrototypeOf(seen), Object.prototype);
  assert.deepEqual(Object.keys(seen), ["field", "__proto__"]);
  assert.deepEqual(Object.getOwnPropertyDescriptor(seen, "__proto__")?.value, { fields: ["secret"] });
  assert.equal(seen.fields, undefined); // nothing inherited
  assert.equal(({} as Record<string, unknown>).fields, undefined); // no global pollution
});

test("a poisoned __proto__ policy behaves as it did unbound and fingerprints differently", () => {
  const records: Records = [{ s: "evil" }, { s: "ok" }];
  const poisonedAllow = JSON.parse('{"field":"s","__proto__":{"allowed":["evil"]}}');
  assert.deepEqual(
    outcome(() => stage(allowlist, poisonedAllow)(records)),
    outcome(() => allowlist(records, poisonedAllow))
  );
  const poisonedSelect = JSON.parse('{"__proto__":{"fields":["secret"]}}');
  assert.deepEqual(
    outcome(() => stage(select, poisonedSelect)([{ secret: 1, a: 2 }])),
    outcome(() => select([{ secret: 1, a: 2 }], poisonedSelect))
  );
  assert.notEqual(fp(stage(select, poisonedSelect)), fp(stage(select, {} as never)));
  assert.equal(({} as Record<string, unknown>).allowed, undefined);
  assert.equal(({} as Record<string, unknown>).fields, undefined);
});

test("a Set subclass and an Array subclass are passed through by identity", () => {
  class CISet extends Set<string> {
    override has(v: string): boolean {
      return super.has(v.toLowerCase());
    }
  }
  class Tagged extends Array<number> {
    tag: string;
    constructor(...items: number[]) {
      super(...items);
      this.tag = "t";
    }
  }
  const ci = new CISet(["a"]);
  const tagged = new Tagged(1, 2, 3);
  const seen: Record<string, unknown> = {};
  const grab = (r: Records, p: Record<string, unknown>): Records => {
    Object.assign(seen, p);
    return r;
  };
  stage(grab, { ci, tagged, nested: [ci, tagged] })([]);
  assert.equal(seen.ci, ci);
  assert.equal(seen.tagged, tagged);
  assert.equal((seen.nested as unknown[])[0], ci);
  assert.equal((seen.nested as unknown[])[1], tagged);
});

test("a plain Array and a plain Set are still copied", () => {
  const arr = [1];
  const set = new Set([1]);
  const seen: Record<string, unknown> = {};
  const grab = (r: Records, p: Record<string, unknown>): Records => {
    Object.assign(seen, p);
    return r;
  };
  stage(grab, { arr, set })([]);
  arr.push(2);
  set.add(2);
  assert.deepEqual(seen.arr, [1]);
  assert.deepEqual([...(seen.set as Set<number>)], [1]);
});
