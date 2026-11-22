/**
 * The README's runnable examples are executed from the README itself (brief
 * AC 34): every ```ts block in the section is run (its `import` line removed;
 * the package's exports are in scope) and what it prints must equal the
 * ```text block that follows it, so documentation cannot drift from behavior.
 * Later slices add their sections to SECTIONS.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import * as contexel from "../src/index.js";

const NL = String.fromCharCode(10);
const CR = String.fromCharCode(13);
const FENCE = new RegExp("```(ts|text)" + NL + "([^]*?)```", "g");

/** [README heading, number of runnable examples the section must contain] */
const SECTIONS: Array<[string, number]> = [
  ["## Text, logs and web pages", 2],
  ["## Errors and strict mode", 2],
];

const README = readFileSync(new URL("../../README.md", import.meta.url), "utf-8")
  .split(CR + NL)
  .join(NL);

function examples(heading: string): Array<[string, string]> {
  const start = README.indexOf(heading);
  assert.ok(start >= 0, `README has no section "${heading}"`);
  const end = README.indexOf(NL + "## ", start + 1);
  const section = README.slice(start, end === -1 ? undefined : end);
  const blocks = [...section.matchAll(FENCE)].map((m) => [m[1], m[2]] as const);
  const pairs: Array<[string, string]> = [];
  blocks.forEach(([lang, body], i) => {
    if (lang !== "ts") return;
    assert.ok(i + 1 < blocks.length && blocks[i + 1][0] === "text", "every ts example is followed by its expected output");
    pairs.push([body, blocks[i + 1][1]]);
  });
  return pairs;
}

function run(source: string): string {
  const body = source
    .split(NL)
    .filter((line) => !line.startsWith("import "))
    .join(NL);
  const names = Object.keys(contexel);
  const printed: string[] = [];
  const original = console.log;
  console.log = (...parts: unknown[]) => {
    printed.push(parts.map(String).join(" "));
  };
  try {
    new Function(...names, body)(...Object.values(contexel));
  } finally {
    console.log = original;
  }
  return printed.join(NL);
}

for (const [heading, count] of SECTIONS) {
  test(`${heading}: the section has its ${count} runnable examples`, () => {
    assert.strictEqual(examples(heading).length, count);
  });
  examples(heading).forEach(([source, expected], index) => {
    test(`${heading}: example ${index} prints what the README shows`, () => {
      assert.strictEqual(run(source).trim(), expected.trim());
    });
  });
}

/* ---- Slice 4: the payload-stages example (text in, best lines out, text back) ---- */

test("payload stages: the log example returns the best lines, in rank and in reading order", () => {
  const { asRecords, dedupe, join, pipeline, rank, rescore, split, stage, trimToBudget } = contexel;
  const log =
    "INFO started" + NL + "WARN retry limit reached" + NL + "INFO ok" + NL + "INFO ok" + NL +
    "ERROR timeout after retry" + NL;
  const pipe = pipeline([
    stage(split, { by: "lines" }),
    stage(dedupe, { key: "text" }),
    stage(rescore, { query: "retry timeout", fields: ["text"] }),
    stage(rank, { by: "score" }),
    stage(trimToBudget, { maxTokens: 60 }),
  ]);
  const best = pipe(asRecords(log));
  assert.strictEqual(join(best), "ERROR timeout after retry" + NL + "WARN retry limit reached" + NL);
  const startOf = (r: contexel.Rec) => (r.chunk as { start: number; end: number }).start;
  assert.deepStrictEqual(best.map(startOf), [54, 13]); // offsets into the log
  // rank again by offset to restore reading order
  const reading = rank(best, { by: startOf, desc: false });
  assert.strictEqual(join(reading), "WARN retry limit reached" + NL + "ERROR timeout after retry" + NL);
});

test("payload stages: the paragraphs example keeps each paragraph and its offsets", () => {
  const { asRecords, split } = contexel;
  const paras = split(asRecords("intro" + NL + NL + "body one" + NL + "body two" + NL + NL + "end"), {
    by: "paragraphs",
  });
  assert.deepStrictEqual(
    paras.map((c) => c.text),
    ["intro" + NL + NL, "body one" + NL + "body two" + NL + NL, "end"]
  );
  const chunk = (c: contexel.Rec) => c.chunk as { start: number; end: number };
  assert.deepStrictEqual(
    paras.map((c) => [chunk(c).start, chunk(c).end]),
    [[0, 7], [7, 26], [26, 29]]
  );
});
