/**
 * Payload stages (ADR-005): `asRecords` / `split` / `join` carry text through
 * the record stages and back, losslessly, with the same boundaries in every
 * language. Mirrors tests/test_text_stages.py. Property checks are seeded
 * (CONTEXEL_PROP_SEED, CONTEXEL_PROP_CASES) from a tiny generator of our own,
 * and each check has a canary proving it can fail. Non-ASCII text is built with
 * String.fromCodePoint so no editor can rewrite it.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ConfigError,
  ContexelError,
  InputShapeError,
  asRecords,
  dedupe,
  isStrict,
  join,
  pipeline,
  split,
  stage,
  tokens,
  trace,
  type Rec,
  type Records,
} from "../src/index.js";
import { traced } from "../src/trace.js";
import { checked } from "../src/validate.js";

const NL = String.fromCharCode(10);
const CR = String.fromCharCode(13);
const ASTRAL = String.fromCodePoint(0x1f600);
const E_ACUTE = String.fromCodePoint(0xe9);
// every character Python's str.splitlines() treats as a line end, other than LF and CR
const WIDE_LINE_ENDS = [0x0b, 0x0c, 0x1c, 0x1d, 0x1e, 0x85, 0x2028, 0x2029]
  .map((c) => String.fromCodePoint(c))
  .join("");

type SplitOptions = { field?: string; by?: string; size?: unknown; into?: string };

// the stages take loosely typed input on purpose in these tests (null, numbers)
const asRec = (x: unknown) => asRecords(x as never);
const splitOf = (records: unknown, options?: SplitOptions): Records =>
  split(records as Records, options as never);
const joinOf = (records: unknown, options?: { field?: unknown; sep?: unknown }): string =>
  join(records as Records, options as never);
const chunksOf = (text: string, options?: SplitOptions): Records =>
  splitOf(asRecords(text), options);
const texts = (chunks: Records) => chunks.map((c) => c.text);
const chunkOf = (c: Rec) => c.chunk as { index: number; start: number; end: number };
const spans = (chunks: Records) => chunks.map((c) => [chunkOf(c).start, chunkOf(c).end]);

/** Assert `fn` throws a `cls` error with this code (and, when given, stage and param). */
function raises(
  fn: () => unknown,
  cls: typeof ConfigError | typeof InputShapeError,
  code: string,
  where: { stage?: string; param?: string } = {}
): void {
  assert.throws(fn, (e: unknown) => {
    assert.ok(e instanceof cls, `expected ${cls.name}, got ${String(e)}`);
    assert.ok(e instanceof ContexelError);
    assert.strictEqual(e.code, code);
    if (where.stage !== undefined) assert.strictEqual(e.stage, where.stage);
    if (where.param !== undefined) assert.strictEqual(e.param, where.param);
    return true;
  });
}

/** A record with an own data property of this name (also "__proto__"). */
function recordWith(props: Record<string, unknown>): Rec {
  const r: Rec = {};
  for (const [k, v] of Object.entries(props)) {
    Object.defineProperty(r, k, { value: v, writable: true, enumerable: true, configurable: true });
  }
  return r;
}

/* ------------------------------------------------------------- asRecords ---- */

test("asRecords wraps a string", () => {
  assert.deepStrictEqual(asRecords("hello"), [{ text: "hello" }]);
  assert.deepStrictEqual(asRecords("x", { field: "body" }), [{ body: "x" }]);
  assert.deepStrictEqual(asRecords(""), [{ text: "" }]);
});

test("asRecords: a single mapping is one record, the same object", () => {
  const m = { a: 1 };
  const out = asRecords(m);
  assert.deepStrictEqual(out, [{ a: 1 }]);
  assert.strictEqual(out[0], m); // the same object, not a copy
  const bare = Object.create(null) as Rec;
  bare.a = 1;
  assert.strictEqual(asRecords(bare)[0], bare); // a null-prototype object is a mapping
});

test("asRecords: a list keeps mappings and wraps everything else", () => {
  const keep = { a: 1 };
  const nested = { k: { z: [1, 2] } };
  const out = asRecords([keep, "s", 5, null, ["n", 1], nested, true]);
  assert.deepStrictEqual(out, [
    { a: 1 },
    { text: "s" },
    { text: 5 },
    { text: null },
    { text: ["n", 1] },
    { k: { z: [1, 2] } },
    { text: true },
  ]);
  assert.strictEqual(out[0], keep);
  assert.strictEqual(out[5], nested);
  assert.deepStrictEqual(asRecords([]), []);
});

test("asRecords does not mutate a list", () => {
  const items = [{ a: 1 }, "s"];
  const before = structuredClone(items);
  asRecords(items);
  assert.deepStrictEqual(items, before);
});

class Point {
  x = 1;
}

const NOT_A_LIST: Array<[string, unknown]> = [
  ["null", null],
  ["undefined", undefined],
  ["Uint8Array", new Uint8Array([1])],
  ["Buffer", Buffer.from("x")],
  ["an integer", 5],
  ["a float", 2.5],
  ["a boolean", true],
  ["a bigint", 5n],
  ["a Set", new Set([1, 2])],
  ["a Map", new Map([[1, 2]])],
  ["a Date", new Date(0)],
  ["a class instance", new Point()],
  ["a function", () => 1],
];

for (const [label, bad] of NOT_A_LIST) {
  test(`asRecords: ${label} raises input.not_list`, () => {
    raises(() => asRec(bad), InputShapeError, "input.not_list", { stage: "as_records" });
  });
}

test("asRecords: a class instance inside a list is wrapped, not kept", () => {
  const p = new Point();
  const out = asRecords([p]);
  assert.strictEqual(out[0].text, p);
});

for (const bad of ["", 5, null, ["text"]]) {
  test(`asRecords: field ${JSON.stringify(bad)} must be a non-empty string`, () => {
    raises(
      () => asRecords("x", { field: bad as never }),
      ConfigError,
      "config.invalid_value",
      { stage: "as_records", param: "field" }
    );
  });
}

test("asRecords checks the shape before the field name", () => {
  raises(() => asRecords(null as never, { field: "" }), InputShapeError, "input.not_list");
});

test("asRecords: a field named __proto__ is an ordinary own property", () => {
  const [wrapped] = asRecords("x", { field: "__proto__" });
  assert.ok(Object.hasOwn(wrapped, "__proto__"));
  assert.strictEqual(Object.getPrototypeOf(wrapped), Object.prototype);
  const [item] = asRecords([5], { field: "__proto__" });
  assert.ok(Object.hasOwn(item, "__proto__"));
  assert.strictEqual(Object.getPrototypeOf(item), Object.prototype);
});

/* ------------------------------------------------------------------ split ---- */

test("split by lines keeps the separators", () => {
  const c = chunksOf("one" + NL + "two" + NL + "three", { by: "lines" });
  assert.deepStrictEqual(texts(c), ["one" + NL, "two" + NL, "three"]);
  assert.deepStrictEqual(spans(c), [[0, 4], [4, 8], [8, 13]]);
  assert.deepStrictEqual(c.map((x) => chunkOf(x).index), [0, 1, 2]);
  assert.deepStrictEqual(texts(chunksOf("a" + NL)), ["a" + NL]); // no empty remainder
  assert.deepStrictEqual(texts(chunksOf(NL)), [NL]);
  assert.deepStrictEqual(texts(chunksOf(NL + NL)), [NL, NL]);
});

test("split: CRLF is one boundary and a lone CR is none", () => {
  assert.deepStrictEqual(texts(chunksOf("a" + CR + NL + "b" + CR + "c" + NL + "d")), [
    "a" + CR + NL,
    "b" + CR + "c" + NL,
    "d",
  ]);
  assert.deepStrictEqual(texts(chunksOf("a" + CR + "b")), ["a" + CR + "b"]);
  assert.deepStrictEqual(texts(chunksOf(CR)), [CR]);
  assert.deepStrictEqual(texts(chunksOf("a" + CR + NL)), ["a" + CR + NL]);
});

test("split by lines ignores the wider splitlines separators", () => {
  const text = "a" + WIDE_LINE_ENDS + "b";
  assert.deepStrictEqual(texts(chunksOf(text, { by: "lines" })), [text]);
});

const PARAGRAPHS: Array<[string, string[]]> = [
  ["a" + NL + NL + "b", ["a" + NL + NL, "b"]],
  ["a" + NL + NL + NL + "b", ["a" + NL + NL + NL, "b"]],
  ["a" + CR + NL + CR + NL + "b", ["a" + CR + NL + CR + NL, "b"]],
  ["a" + NL + CR + NL + "b", ["a" + NL + CR + NL, "b"]],
  ["a" + CR + CR + NL + NL + "b", ["a" + CR + CR + NL + NL, "b"]],
  ["a" + NL + "b", ["a" + NL + "b"]],
  ["a" + CR + NL + "b", ["a" + CR + NL + "b"]],
  ["a" + NL + " " + NL + "b", ["a" + NL + " " + NL + "b"]],
  [NL + NL + "abc", [NL + NL, "abc"]],
  ["abc" + NL + NL, ["abc" + NL + NL]],
  ["a" + NL + NL + "b" + NL + NL + "c", ["a" + NL + NL, "b" + NL + NL, "c"]],
  [NL + NL + NL + NL, [NL + NL + NL + NL]],
];

PARAGRAPHS.forEach(([text, expected], i) => {
  test(`split by paragraphs: boundary case ${i}`, () => {
    assert.deepStrictEqual(texts(chunksOf(text, { by: "paragraphs" })), expected);
  });
});

test("split by size counts code points", () => {
  const text = "ab" + ASTRAL.repeat(3) + "c"; // 6 code points, 9 UTF-16 units
  const c = chunksOf(text, { by: "size", size: 2 });
  assert.deepStrictEqual(texts(c), ["ab", ASTRAL.repeat(2), ASTRAL + "c"]);
  assert.deepStrictEqual(spans(c), [[0, 2], [2, 4], [4, 6]]);
  assert.deepStrictEqual(texts(chunksOf("abcdef", { by: "size", size: 3 })), ["abc", "def"]);
  assert.deepStrictEqual(texts(chunksOf("abc", { by: "size", size: 10 })), ["abc"]);
  assert.deepStrictEqual(texts(chunksOf("ab", { by: "size", size: 1 })), ["a", "b"]);
  assert.deepStrictEqual(texts(chunksOf(ASTRAL.repeat(3), { by: "size", size: 1 })), [ASTRAL, ASTRAL, ASTRAL]);
});

test("split counts a lone surrogate as one code point, as an iterating string does", () => {
  const lone = String.fromCharCode(0xd83d);
  const c = chunksOf(lone + ASTRAL + "a", { by: "size", size: 2 });
  assert.deepStrictEqual(texts(c), [lone + ASTRAL, "a"]);
  assert.deepStrictEqual(spans(c), [[0, 2], [2, 3]]);
  const lines = chunksOf("a" + lone + NL + "b");
  assert.deepStrictEqual(spans(lines), [[0, 3], [3, 4]]);
});

const MODES: Array<[string, SplitOptions]> = [
  ["lines", { by: "lines" }],
  ["paragraphs", { by: "paragraphs" }],
  ["size", { by: "size", size: 3 }],
];

for (const [label, options] of MODES) {
  test(`split by ${label}: empty text yields nothing and a separator-free text is one chunk`, () => {
    assert.deepStrictEqual(splitOf([{ text: "", id: 1 }], options), []);
    const out = splitOf([{ id: 0, text: "xyz" }, { id: 1, text: "" }, { id: 2, text: "q" }], options);
    assert.deepStrictEqual(
      out.map((c) => [c.id, c.text]),
      [[0, "xyz"], [2, "q"]]
    );
    const only = chunksOf("abc", options);
    assert.deepStrictEqual(texts(only), ["abc"]);
    assert.deepStrictEqual(spans(only), [[0, 3]]);
  });
}

test("split: offsets index back into the text by code points", () => {
  const text = "caf" + E_ACUTE + CR + NL + "na" + NL + "ve" + ASTRAL + NL + NL + "z";
  const cps = [...text];
  for (const [, options] of MODES) {
    for (const c of chunksOf(text, options)) {
      assert.strictEqual(cps.slice(chunkOf(c).start, chunkOf(c).end).join(""), c.text);
    }
  }
});

test("split: chunks carry the parent fields and the input is never mutated", () => {
  const parent = { id: 7, text: "a" + NL + "b", meta: { k: 1 }, tags: ["t"] };
  const before = structuredClone(parent);
  const out = split([parent]);
  assert.deepStrictEqual(out, [
    { id: 7, text: "a" + NL, meta: { k: 1 }, tags: ["t"], chunk: { index: 0, start: 0, end: 2 } },
    { id: 7, text: "b", meta: { k: 1 }, tags: ["t"], chunk: { index: 1, start: 2, end: 3 } },
  ]);
  assert.deepStrictEqual(parent, before);
});

test("split: the index restarts for each parent and parents keep their order", () => {
  const out = split([
    { id: "a", text: "1" + NL + "2" + NL },
    { id: "b", text: "x" + NL + "y" + NL + "z" },
  ]);
  assert.deepStrictEqual(
    out.map((c) => [c.id, chunkOf(c).index]),
    [["a", 0], ["a", 1], ["b", 0], ["b", 1], ["b", 2]]
  );
});

test("split passes a record without a string field through untouched", () => {
  const records = [
    { id: 1 },
    { id: 2, text: null },
    { id: 3, text: 5 },
    { id: 4, text: ["a" + NL + "b"] },
    { id: 5, text: "k" + NL + "l" },
  ];
  const out = split(records);
  assert.deepStrictEqual(out.slice(0, 4), records.slice(0, 4));
  for (let i = 0; i < 4; i++) assert.strictEqual(out[i], records[i]);
  assert.deepStrictEqual(texts(out.slice(4)), ["k" + NL, "l"]);
});

test("split: a pass-through record may already have the into key", () => {
  const record = { text: 5, chunk: "x" };
  const out = split([record]);
  assert.deepStrictEqual(out, [record]);
  assert.strictEqual(out[0], record);
});

test("split: an existing into key raises input.field_conflict", () => {
  assert.throws(
    () => split([{ text: "ok" + NL + "ok" }, { text: "a" + NL + "b", chunk: 1 }]),
    (e: unknown) => {
      assert.ok(e instanceof InputShapeError);
      assert.deepStrictEqual([e.code, e.stage, e.param], ["input.field_conflict", "split", "into"]);
      assert.match(e.message, /record 1/);
      return true;
    }
  );
  // a different into name is the way out
  const out = split([{ text: "a" + NL + "b", chunk: 1 }], { into: "part" });
  assert.deepStrictEqual(out.map((c) => c.chunk), [1, 1]);
  assert.strictEqual((out[0].part as { index: number }).index, 0);
  // an empty text yields no chunks, but the clash is still refused
  raises(() => split([{ text: "", chunk: 1 }]), InputShapeError, "input.field_conflict");
  // into equal to field clashes with the very text being split
  raises(() => split([{ text: "a" }], { into: "text" }), InputShapeError, "input.field_conflict");
});

test("split reads and tests OWN properties only, never inherited ones", () => {
  const inheritedText = Object.create({ text: "a" + NL + "b" }) as Rec;
  assert.strictEqual(split([inheritedText])[0], inheritedText); // no own text: passes through
  const inheritedInto = Object.assign(Object.create({ chunk: 1 }) as Rec, { text: "a" + NL + "b" });
  const out = split([inheritedInto]); // an inherited into is no conflict
  assert.deepStrictEqual(texts(out), ["a" + NL, "b"]);
  assert.ok(Object.hasOwn(out[0], "chunk"));
});

test("split: a field or into named __proto__ is an ordinary own data property", () => {
  const byField = split([recordWith({ ["__proto__"]: "a" + NL + "b" })], { field: "__proto__" });
  assert.strictEqual(byField.length, 2);
  for (const c of byField) {
    assert.strictEqual(Object.getPrototypeOf(c), Object.prototype);
    assert.ok(Object.hasOwn(c, "__proto__") && Object.hasOwn(c, "chunk"));
  }
  assert.deepStrictEqual(
    byField.map((c) => Object.getOwnPropertyDescriptor(c, "__proto__")?.value),
    ["a" + NL, "b"]
  );
  const byInto = split([{ text: "a" + NL + "b" }], { into: "__proto__" });
  for (const c of byInto) {
    assert.strictEqual(Object.getPrototypeOf(c), Object.prototype);
    assert.ok(Object.hasOwn(c, "__proto__"));
  }
  assert.deepStrictEqual(Object.getOwnPropertyDescriptor(byInto[1], "__proto__")?.value, {
    index: 1,
    start: 2,
    end: 3,
  });
  // an OWN __proto__ already there is a clash; the inherited accessor is not
  raises(
    () => split([recordWith({ text: "a", ["__proto__"]: 1 })], { into: "__proto__" }),
    InputShapeError,
    "input.field_conflict"
  );
  assert.strictEqual(split([{ text: "a" }], { into: "__proto__" }).length, 1);
});

for (const size of [undefined, null, 0, -1, true, 2.5, "3", NaN, Infinity]) {
  test(`split by size requires a positive integer size: ${String(size)}`, () => {
    raises(
      () => splitOf([{ text: "abc" }], { by: "size", size }),
      ConfigError,
      "config.invalid_value",
      { stage: "split", param: "size" }
    );
  });
}

test("split by size accepts any positive integer, however large", () => {
  assert.deepStrictEqual(texts(chunksOf("abc", { by: "size", size: Number.MAX_SAFE_INTEGER * 4 })), ["abc"]);
});

for (const [by, size] of [["lines", 3], ["paragraphs", 3], ["lines", 0]] as const) {
  test(`split: size ${size} with by=${by} is contradictory`, () => {
    raises(
      () => splitOf([{ text: "abc" }], { by, size }),
      ConfigError,
      "config.contradictory",
      { stage: "split", param: "size" }
    );
  });
}

test("split: a null size with another mode means no size", () => {
  assert.deepStrictEqual(texts(splitOf([{ text: "a" + NL + "b" }], { by: "lines", size: null })), ["a" + NL, "b"]);
  assert.deepStrictEqual(texts(splitOf([{ text: "ab" }], { by: "paragraphs", size: undefined })), ["ab"]);
});

for (const by of ["words", "", null, 3, ["lines"]]) {
  test(`split: unknown by ${JSON.stringify(by)} raises`, () => {
    raises(
      () => splitOf([{ text: "abc" }], { by: by as never }),
      ConfigError,
      "config.invalid_value",
      { stage: "split", param: "by" }
    );
  });
}

for (const options of [{ field: 5 }, { into: null }, { into: 3 }]) {
  test(`split: field and into must be strings: ${JSON.stringify(options)}`, () => {
    raises(
      () => splitOf([{ text: "abc" }], options as never),
      ConfigError,
      "config.invalid_value"
    );
  });
}

test("split validates field, by, into, size in that order", () => {
  const bad = { field: 5, by: "words", into: 3, size: 0 };
  assert.throws(() => splitOf([], bad as never), (e: unknown) => (e as ConfigError).param === "field");
  assert.throws(() => splitOf([], { ...bad, field: "text" } as never), (e: unknown) => (e as ConfigError).param === "by");
  assert.throws(
    () => splitOf([], { ...bad, field: "text", by: "size" } as never),
    (e: unknown) => (e as ConfigError).param === "into"
  );
  assert.throws(
    () => splitOf([], { ...bad, field: "text", by: "size", into: "chunk" } as never),
    (e: unknown) => (e as ConfigError).param === "size"
  );
});

test("split checks its input in every mode", () => {
  assert.ok(!isStrict());
  for (const bad of [null, undefined, "abc", 5, { text: "a" }]) {
    raises(() => splitOf(bad), InputShapeError, "input.not_list", { stage: "split" });
  }
  assert.throws(
    () => splitOf([{ text: "a" }, "x"]),
    (e: unknown) => {
      assert.ok(e instanceof InputShapeError);
      assert.deepStrictEqual([e.code, e.stage], ["input.not_mapping", "split"]);
      assert.match(e.message, /item 1/);
      return true;
    }
  );
  raises(() => splitOf([{ text: "a" }, null]), InputShapeError, "input.not_mapping");
  raises(() => splitOf([[1]]), InputShapeError, "input.not_mapping");
});

test("split checks the shape before the configuration", () => {
  raises(() => splitOf(null, { by: "bogus" }), InputShapeError, "input.not_list");
  raises(() => splitOf([1], { by: "bogus" }), InputShapeError, "input.not_mapping");
});

test("split under a trace reports a non-list with the typed error", () => {
  raises(() => trace(null, () => splitOf(null)), InputShapeError, "input.not_list");
});

test("split does not mutate its input for any mode", () => {
  const records = [{ text: "a" + NL + NL + "b" + NL + "c", meta: { k: [1] } }];
  const before = structuredClone(records);
  for (const [, options] of MODES) split(records, options as never);
  assert.deepStrictEqual(records, before);
});

test("split is traced, and an expansion is not a drop", () => {
  const records = [
    { id: "a", text: "1" + NL + "2" + NL + "3" },
    { id: "b", text: "" },
    { id: "c", text: "z" },
    { text: "no id" + NL + "here" },
  ];
  const [out, tr] = trace({ idField: "id" }, () => split(records));
  const entry = tr.entries[0];
  assert.deepStrictEqual([entry.stage, entry.inCount, entry.outCount], ["split", 4, out.length]);
  assert.strictEqual(out.length, 3 + 1 + 2); // a: 3 chunks, b: none, c: 1, no-id: 2
  // b vanished (documented) and is reported; a and c were expanded or kept
  assert.deepStrictEqual(entry.droppedIds, ["b"]);
});

test("traced keepsIds makes attribution exact, and the default is unchanged", () => {
  // a stage that expands an id-less record into two and drops the record "b"
  const expandAndDrop = (_records: Rec[]): Rec[] => [{ t: "x" }, { t: "y" }, { id: "a" }];
  const records: Rec[] = [{ id: "a" }, { id: "b" }, { t: "one" }];
  const exact = traced("expand_and_drop", expandAndDrop, { keepsIds: true });
  const dflt = traced("expand_and_drop", expandAndDrop);
  const explicit = traced("expand_and_drop", expandAndDrop, { keepsIds: false });
  const [, tr] = trace({ idField: "id" }, () => {
    exact(records);
    dflt(records);
    explicit(records);
  });
  // exact: "b" has no survivor, so it is reported; the default rule explains
  // it away as an id lost by one of the id-less records the stage added
  assert.deepStrictEqual(
    tr.entries.map((e) => e.droppedIds),
    [["b"], [], []]
  );
});

test("traced keepsIds changes nothing without a trace and returns the stage's own output", () => {
  const fn = (records: Rec[]): Rec[] => records.slice(1);
  const wrapped = traced("slice", fn, { keepsIds: true });
  assert.deepStrictEqual(wrapped([{ id: 1 }, { id: 2 }]), [{ id: 2 }]);
});

test("split's stage policies are part of the fingerprint", () => {
  const fp = (options: SplitOptions) => pipeline([stage(split, options as never)]).fingerprint;
  assert.strictEqual(fp({ by: "size", size: 3 }), fp({ by: "size", size: 3 }));
  assert.notStrictEqual(fp({ by: "size", size: 3 }), fp({ by: "size", size: 4 }));
  assert.notStrictEqual(fp({ by: "lines" }), fp({ by: "paragraphs" }));
});

test("split runs in a strict pipeline and strict changes nothing", () => {
  const text = "a" + NL + "b" + NL + NL + "c";
  const stages = [stage(split, { by: "paragraphs" }), stage(dedupe, { key: "text" })];
  assert.deepStrictEqual(
    pipeline(stages, { strict: true })(asRecords(text)),
    pipeline(stages)(asRecords(text))
  );
});

test("an off-ramp inside a strict pipeline is refused", () => {
  // join returns a string, so it belongs OUTSIDE the pipeline (docs)
  const offRamp = join as unknown as (records: Records, params: object) => Records;
  raises(
    () => pipeline([stage(split, {}), stage(offRamp, {})], { strict: true })(asRecords("a" + NL + "b")),
    InputShapeError,
    "input.not_list"
  );
});

test("checked(..., always) validates without strict mode", () => {
  const always = checked("always", true, (records: Rec[]) => records, true);
  const lenient = checked("lenient", true, (records: Rec[]) => records);
  const explicit = checked("explicit", true, (records: Rec[]) => records, false);
  assert.ok(!isStrict());
  raises(() => always(null as never), InputShapeError, "input.not_list", { stage: "always" });
  raises(() => always([1] as never), InputShapeError, "input.not_mapping", { stage: "always" });
  assert.strictEqual(lenient(null as never), null); // strict is off: no check
  assert.strictEqual(explicit(null as never), null);
  assert.deepStrictEqual(always([{ a: 1 }]), [{ a: 1 }]);
});

test("checked(..., always) honours needsMapping, including a function of the arguments", () => {
  const listOnly = checked("list_only", false, (records: Rec[]) => records, true);
  raises(() => listOnly(null as never), InputShapeError, "input.not_list");
  assert.deepStrictEqual(listOnly([1] as never), [1]); // items are not inspected
  const byArgs = checked("by_args", (n: number) => n > 0, (records: Rec[], _n: number) => records, true);
  raises(() => byArgs([1] as never, 1), InputShapeError, "input.not_mapping");
  assert.deepStrictEqual(byArgs([1] as never, 0), [1]);
  raises(() => byArgs(null as never, 0), InputShapeError, "input.not_list");
});

/* ------------------------------------------------------------------- join ---- */

test("join skips missing, keeps strings and serializes the rest", () => {
  const records = [
    { text: "a" },
    { other: 1 },
    { text: { k: 1 } },
    { text: [1, "x"] },
    { text: null },
    { text: true },
    { text: 2.5 },
  ];
  assert.strictEqual(join(records, { sep: "|" }), 'a|{"k": 1}|[1, "x"]|null|true|2.5');
  assert.strictEqual(join(records), 'a{"k": 1}[1, "x"]nulltrue2.5');
});

test("join: field, sep and empty input", () => {
  assert.strictEqual(
    join([{ body: "x" }, { text: "no" }, { body: "y" }], { field: "body", sep: NL }),
    "x" + NL + "y"
  );
  assert.strictEqual(join([]), "");
  assert.strictEqual(join([{ other: 1 }]), "");
  assert.strictEqual(join([{ text: "" }, { text: "" }], { sep: "-" }), "-");
});

test("join reads OWN properties only", () => {
  assert.strictEqual(join([Object.create({ text: "x" }) as Rec]), "");
  assert.strictEqual(join([recordWith({ ["__proto__"]: "p" })], { field: "__proto__" }), "p");
});

test("join renders non-strings with the active serializer", () => {
  const out = tokens.scoped(
    { serializer: (v) => "<" + (Array.isArray(v) ? "list" : typeof v) + ">" },
    () => join([{ text: { k: 1 } }, { text: "s" }, { text: [1] }], { sep: " " })
  );
  assert.strictEqual(out, "<object> s <list>");
});

test("join checks its input in every mode", () => {
  for (const bad of [null, undefined, "abc", 5, { text: "a" }]) {
    raises(() => joinOf(bad), InputShapeError, "input.not_list", { stage: "join" });
  }
  assert.throws(
    () => joinOf([{ text: "a" }, null]),
    (e: unknown) => {
      assert.ok(e instanceof InputShapeError);
      assert.deepStrictEqual([e.code, e.stage], ["input.not_mapping", "join"]);
      return true;
    }
  );
});

for (const options of [{ field: 5 }, { sep: null }, { sep: 1 }]) {
  test(`join: field and sep must be strings: ${JSON.stringify(options)}`, () => {
    raises(
      () => joinOf([{ text: "a" }], options),
      ConfigError,
      "config.invalid_value",
      { stage: "join" }
    );
  });
}

test("join checks the shape before the configuration", () => {
  raises(() => joinOf(null, { field: 5 }), InputShapeError, "input.not_list");
});

test("join round-trips split for every mode", () => {
  const text =
    "line one" + CR + NL + "line two" + NL + NL + NL + "para " + ASTRAL + CR + "lone cr" + NL + E_ACUTE;
  for (const [, options] of MODES) {
    assert.strictEqual(join(chunksOf(text, options)), text);
  }
  assert.strictEqual(join(chunksOf(text, { by: "size", size: 5 })), text);
});

/* ---------------------------------------------------------- properties ---- */

const DEFAULT_SEED = 20261119;
const DEFAULT_CASES = 200;

function envInt(name: string, fallback: number): number {
  const raw = process.env[name];
  return raw === undefined ? fallback : Number.parseInt(raw, 10);
}

/** The run's seeds: CONTEXEL_PROP_SEED upwards, CONTEXEL_PROP_CASES of them. */
function seeds(): number[] {
  const base = envInt("CONTEXEL_PROP_SEED", DEFAULT_SEED);
  return Array.from({ length: envInt("CONTEXEL_PROP_CASES", DEFAULT_CASES) }, (_, i) => base + i);
}

/** The run's seeds, then the default ones: whether a check CAN fail must not
 * depend on how small a reproduction run is. */
function canarySeeds(): number[] {
  return [...seeds(), ...Array.from({ length: DEFAULT_CASES }, (_, i) => DEFAULT_SEED + i)];
}

/** A tiny linear congruential generator, so the sequence never depends on the
 * runtime (Math.random cannot be seeded). */
class Lcg {
  private state: number;
  constructor(seed: number) {
    this.state = seed >>> 0;
  }
  /** An integer in [0, n). */
  below(n: number): number {
    this.state = (Math.imul(this.state, 1664525) + 1013904223) >>> 0;
    return Math.floor((this.state / 4294967296) * n);
  }
  /** An integer in [lo, hi]. */
  between(lo: number, hi: number): number {
    return lo + this.below(hi - lo + 1);
  }
}

const ALPHABET = ["a", "b", " ", NL, NL, CR, CR + NL, CR + NL, NL + NL, ASTRAL, E_ACUTE, "x"];

function randomText(rng: Lcg): string {
  const k = rng.between(0, 40);
  let out = "";
  for (let i = 0; i < k; i++) out += ALPHABET[rng.below(ALPHABET.length)];
  return out;
}

const cpLength = (s: string): number => [...s].length;

/** Every promise of `split` about one text; throws an AssertionError. */
function checkSplit(text: string, by: string, size: number | null, chunks: Records): void {
  const cps = [...text];
  assert.strictEqual(chunks.map((c) => c.text).join(""), text, "chunks do not rebuild the text");
  assert.deepStrictEqual(
    chunks.map((c) => chunkOf(c).index),
    chunks.map((_, i) => i),
    "bad index"
  );
  let position = 0;
  for (const c of chunks) {
    const { start, end } = chunkOf(c);
    assert.ok(start === position && end > start, "offsets are not contiguous");
    assert.strictEqual(cps.slice(start, end).join(""), c.text, "offsets do not index the text");
    position = end;
  }
  assert.strictEqual(position, cps.length, "offsets do not cover the text");
  const body = chunks.slice(0, -1);
  if (by === "lines") {
    for (const c of body) {
      const t = c.text as string;
      assert.ok(t.endsWith(NL) && t.split(NL).length - 1 === 1, "line boundary");
    }
    if (chunks.length) assert.ok(((chunks[chunks.length - 1].text as string).split(NL).length - 1) <= 1, "line boundary");
  } else if (by === "paragraphs") {
    const run = /(?:\r?\n){2,}/;
    for (const c of chunks) {
      const m = run.exec(c.text as string);
      assert.ok(m === null || m.index + m[0].length === (c.text as string).length, "paragraph boundary");
    }
    for (const c of body) assert.ok(run.test(c.text as string), "paragraph boundary");
  } else {
    for (const c of body) assert.strictEqual(cpLength(c.text as string), size, "size boundary");
    if (chunks.length) {
      const last = cpLength(chunks[chunks.length - 1].text as string);
      assert.ok(last >= 1 && last <= (size as number), "size boundary");
    }
  }
}

const withMode = (by: string, size: number | null): SplitOptions =>
  size === null ? { by } : { by, size };

test("split is lossless and its offsets index back for random texts", () => {
  for (const seed of seeds()) {
    const rng = new Lcg(seed);
    const text = randomText(rng);
    const size = rng.between(1, 6);
    for (const [by, sz] of [["lines", null], ["paragraphs", null], ["size", size]] as const) {
      try {
        checkSplit(text, by, sz, chunksOf(text, withMode(by, sz)));
      } catch (e) {
        // name the seed, whatever failed
        throw new assert.AssertionError({
          message: `seed ${seed} by=${by} text=${JSON.stringify(text)}: ${String(e)}`,
        });
      }
    }
  }
});

const dropLastChar = (chunks: Records): Records =>
  chunks.map((c, i) => (i === chunks.length - 1 ? { ...c, text: [...(c.text as string)].slice(0, -1).join("") } : c));
const shiftOffsets = (chunks: Records): Records =>
  chunks.map((c) => ({ ...c, chunk: { ...chunkOf(c), start: chunkOf(c).start + 1, end: chunkOf(c).end + 1 } }));
const reverse = (chunks: Records): Records => [...chunks].reverse();
const cutOneTooSoon = (chunks: Records): Records => {
  if (!chunks.length) return chunks;
  const [first, ...rest] = chunks;
  return [
    { ...first, text: [...(first.text as string)].slice(0, -1).join(""), chunk: { ...chunkOf(first), end: chunkOf(first).end - 1 } },
    ...rest,
  ];
};

const CORRUPTIONS: Array<[string, (chunks: Records) => Records]> = [
  ["dropLastChar", dropLastChar],
  ["shiftOffsets", shiftOffsets],
  ["reverse", reverse],
  ["cutOneTooSoon", cutOneTooSoon],
];

for (const [name, corrupt] of CORRUPTIONS) {
  test(`the split check rejects a broken split: ${name}`, () => {
    let caught = 0;
    for (const seed of canarySeeds()) {
      const text = randomText(new Lcg(seed));
      if (cpLength(text) < 4) continue;
      for (const [by, size] of [["lines", null], ["paragraphs", null], ["size", 2]] as const) {
        const chunks = chunksOf(text, withMode(by, size));
        checkSplit(text, by, size, chunks); // the real split passes
        const broken = corrupt(chunks);
        if (JSON.stringify(broken) === JSON.stringify(chunks)) continue; // nothing to corrupt here
        assert.throws(() => checkSplit(text, by, size, broken), assert.AssertionError);
        caught++;
      }
      if (caught) return;
    }
    assert.fail("no seed produced a text the corruption could change");
  });
}

test("the generator is deterministic: the same seed gives the same text, another seed another", () => {
  assert.strictEqual(randomText(new Lcg(1)), randomText(new Lcg(1)));
  const distinct = new Set(Array.from({ length: 20 }, (_, i) => randomText(new Lcg(i))));
  assert.ok(distinct.size > 10);
  // pinned: if this sequence changes, every recorded failing seed changes meaning
  const rng = new Lcg(1);
  assert.deepStrictEqual([0, 1, 2, 3, 4].map(() => rng.below(1000)), [236, 369, 504, 704, 50]);
});

/* ---------------------------------------------------------- performance ---- */

/** Run `fn` and assert it finished in well under two seconds (the requirement
 * is linear time; a quadratic cut of a million characters takes minutes). */
function underTwoSeconds<T>(label: string, fn: () => T): T {
  const started = performance.now();
  const result = fn();
  const elapsed = performance.now() - started;
  assert.ok(elapsed < 2000, `${label} took ${Math.round(elapsed)} ms`);
  return result;
}

test("split completes on a million characters and round-trips", () => {
  const lines = "abcdefghi" + NL;
  const text = lines.repeat(100_000); // exactly 1,000,000 characters
  assert.strictEqual(text.length, 1_000_000);
  const c = underTwoSeconds("lines", () => chunksOf(text, { by: "lines" }));
  assert.strictEqual(c.length, 100_000);
  assert.deepStrictEqual(spans(c)[c.length - 1], [999_990, 1_000_000]);
  assert.strictEqual(join(c), text);

  const paragraphs = ("para" + NL + NL).repeat(166_666) + "tail";
  const p = underTwoSeconds("paragraphs", () => chunksOf(paragraphs, { by: "paragraphs" }));
  assert.strictEqual(p.length, 166_667);
  assert.strictEqual(join(p), paragraphs);

  const sized = underTwoSeconds("size", () => chunksOf(text, { by: "size", size: 1000 }));
  assert.strictEqual(sized.length, 1000);
  assert.strictEqual(join(sized), text);
  assert.deepStrictEqual(spans(sized)[sized.length - 1], [999_000, 1_000_000]);
});

test("split by size counts a million astral code points without UTF-16 arithmetic", () => {
  const text = ASTRAL.repeat(1_000_000); // 2,000,000 UTF-16 units
  const sized = underTwoSeconds("astral size", () => chunksOf(text, { by: "size", size: 1000 }));
  assert.strictEqual(sized.length, 1000);
  assert.deepStrictEqual(spans(sized)[999], [999_000, 1_000_000]);
  assert.strictEqual(join(sized), text);
  const lines = (ASTRAL + NL).repeat(100_000);
  const c = underTwoSeconds("astral lines", () => chunksOf(lines, { by: "lines" }));
  assert.deepStrictEqual(spans(c)[c.length - 1], [199_998, 200_000]);
});

for (const unit of [CR, CR + NL, NL + CR, NL, "a"]) {
  test(`split stays linear on adversarial separators: ${JSON.stringify(unit)}`, () => {
    // a million characters of separators that almost match: must just complete
    const text = unit.repeat(Math.floor(1_000_000 / unit.length));
    for (const by of ["lines", "paragraphs"]) {
      const out = underTwoSeconds(by, () => chunksOf(text, { by }));
      assert.strictEqual(join(out), text);
    }
  });
}
