/**
 * Differential fuzz (ADR-007, brief AC 36): replay the seeded corpus that
 * `python parity/generate_fuzz.py` wrote through the runner that replays the
 * shared vectors, and compare every outcome with the Python canon.
 *
 * `CONTEXEL_FUZZ_CASES` is the path of the corpus (relative to the repository
 * root, or absolute). Unset, the replay is skipped locally; in CI (`CI` set) an
 * unset variable fails, so the job cannot go green by testing nothing.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import { checkCase, type Case } from "./runner.js";

const ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const MIN_CASES = 1000;
const SHOWN = 20;
const configured = process.env.CONTEXEL_FUZZ_CASES;

interface Corpus {
  _meta: { seed: number; case_count: number; kind_counts: Record<string, number> };
  cases: Case[];
}

/** A copy of the case whose expectation is wrong: every checker must refuse it. */
function corrupted(c: Case): Case {
  const copy = JSON.parse(JSON.stringify(c)) as Case;
  if (copy.expect_error !== undefined) {
    copy.expect_error = { code: copy.expect_error.code + ".wrong" };
  } else if (Array.isArray(copy.expect)) {
    copy.expect = [...copy.expect, { canary: 1 }];
  } else if (typeof copy.expect === "string") {
    copy.expect = copy.expect + "!";
  } else {
    copy.expect = { canary: 1 };
  }
  return copy;
}

if (configured === undefined || configured === "") {
  if (process.env.CI) {
    test("the fuzz corpus is configured in CI", () => {
      assert.fail(
        "CONTEXEL_FUZZ_CASES is not set: generate the corpus and point the variable at it " +
          "(python parity/generate_fuzz.py --out parity/fuzz-corpus.json, then set " +
          "CONTEXEL_FUZZ_CASES=parity/fuzz-corpus.json)"
      );
    });
  } else {
    test("differential fuzz replay", { skip: "CONTEXEL_FUZZ_CASES is not set" }, () => {});
  }
} else {
  const corpus = JSON.parse(readFileSync(path.resolve(ROOT, configured), "utf-8")) as Corpus;

  test("the fuzz corpus is present and complete", () => {
    assert.ok(corpus.cases.length >= MIN_CASES, `only ${corpus.cases.length} cases (a replay must never pass vacuously)`);
    assert.strictEqual(corpus.cases.length, corpus._meta.case_count, "case_count disagrees with the cases array");
    assert.strictEqual(new Set(corpus.cases.map((c) => c.id)).size, corpus.cases.length, "duplicate case ids");
    const seen: Record<string, number> = {};
    for (const c of corpus.cases) seen[c.stage] = (seen[c.stage] ?? 0) + 1;
    assert.deepStrictEqual(seen, corpus._meta.kind_counts, "the kinds replayed differ from the kinds generated");
    assert.ok(corpus.cases.some((c) => c.expect_error !== undefined), "no error case in the corpus");
  });

  test(`every fuzz case matches the Python canon (seed ${corpus._meta.seed})`, () => {
    const failures: string[] = [];
    for (const c of corpus.cases) {
      try {
        checkCase(c, []);
      } catch (error) {
        const message = String((error as Error).message ?? error).split("\n").slice(0, 6).join("\n    ");
        failures.push(`${c.id}\n    ${message}`);
      }
    }
    if (failures.length > 0) {
      const index = Number(failures[0].split("\n")[0].split("/")[2]);
      assert.fail(
        `${failures.length} of ${corpus.cases.length} fuzz cases diverge from the canon. First ${Math.min(SHOWN, failures.length)}:\n` +
          failures.slice(0, SHOWN).join("\n") +
          `\nReproduce one: python parity/generate_fuzz.py --seed ${corpus._meta.seed} --show ${index}`
      );
    }
  });

  test("the replay can fail: a corrupted expectation is refused", () => {
    const sample = corpus.cases.slice(0, 300);
    assert.ok(sample.length > 0);
    for (const c of sample) {
      assert.throws(() => checkCase(corrupted(c), []), Error, `a corrupted ${c.id} was accepted`);
    }
  });
}
