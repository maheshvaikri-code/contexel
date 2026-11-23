/**
 * The frozen English stemmer (ADR-006, docs/stemmer-rules.md): mirrors
 * tests/test_stem.py. `stem` is not part of the public API, so these tests
 * import it from the module. Non-ASCII text is built with String.fromCodePoint
 * so no editor can rewrite it.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import * as api from "../src/index.js";
import { stem } from "../src/stem.js";

const cp = (n: number): string => String.fromCodePoint(n);
const ASTRAL = cp(0x1d49c); // one code point, two UTF-16 units
const E_ACUTE = cp(0xe9);

const FAMILIES: string[][] = [
  ["parse", "parses", "parsed", "parsing"],
  ["value", "values", "valued"],
  ["query", "queries", "queried", "querying"],
  ["try", "tries", "tried", "trying"],
  ["file", "files", "filed", "filing"],
  ["code", "codes", "coded", "coding"],
  ["test", "tests", "tested", "testing"],
  ["run", "runs", "running"],
  ["stop", "stops", "stopped", "stopping"],
  ["return", "returns", "returned", "returning"],
  ["class", "classes"],
  ["match", "matches", "matched", "matching"],
  ["request", "requests", "requested", "requesting"],
  ["error", "errors"],
  ["index", "indexes", "indexed", "indexing"],
  ["cache", "caches", "cached", "caching"],
];

for (const family of FAMILIES) {
  test(`stem family unifies: ${family[0]}`, () => {
    assert.strictEqual(new Set(family.map(stem)).size, 1);
  });
}

test("the parse family stems to pars", () => {
  assert.deepStrictEqual(FAMILIES[0].map(stem), ["pars", "pars", "pars", "pars"]);
});

// every rule, in the order the rules apply, with the word that exercises it
const RULES: Array<[string, string, string]> = [
  ["sses", "glasses", "glass"],
  ["ies", "queries", "query"],
  ["ied", "queried", "query"],
  ["s", "tests", "test"],
  ["ing", "testing", "test"],
  ["ed", "tested", "test"],
  ["undoubling", "stopped", "stop"],
  ["final e", "value", "valu"],
  ["ies, four letters: the plural s rule", "ties", "tie"],
  ["ied, four letters: no vowel-bearing base of three letters", "tied", "tied"],
  ["ss is not a plural", "class", "class"],
  ["us is not a plural", "status", "status"],
  ["is is not a plural", "analysis", "analysis"],
  ["three letters or fewer", "bus", "bus"],
  ["base must keep three letters", "need", "need"],
  ["base must keep a vowel", "string", "string"],
  ["l is not undoubled", "falling", "fall"],
  ["s is not undoubled", "passed", "pass"],
  ["only one of ing and ed is stripped", "feeding", "feed"],
  ["digits are letters to the rules", "2020s", "2020"],
];

for (const [name, word, expected] of RULES) {
  test(`stem rule: ${name}`, () => {
    assert.strictEqual(stem(word), expected);
  });
}

// documented in docs/stemmer-rules.md: the price of a small frozen rule set
const LIMITS: Array<[string, string]> = [
  ["configure", "configur"],
  ["config", "config"],
  ["speed", "spe"],
  ["news", "new"],
  ["using", "using"],
  ["series", "sery"],
  ["species", "specy"],
  ["bias", "bia"],
];

for (const [word, expected] of LIMITS) {
  test(`stem documented limit: ${word}`, () => {
    assert.strictEqual(stem(word), expected);
  });
}

test("stem expects lower-case input", () => {
  assert.strictEqual(stem("PARSING"), "PARSING");
  assert.strictEqual(stem("Parsing"), "Pars");
});

test("stem leaves words of three code points or fewer unchanged", () => {
  const alphabet = [..."abcdefghijklmnopqrstuvwxyz0123456789", E_ACUTE, ASTRAL];
  const check = (word: string): void => assert.strictEqual(stem(word), word);
  check("");
  for (const a of alphabet) {
    check(a);
    for (const b of alphabet) {
      check(a + b);
      for (const c of alphabet) check(a + b + c);
    }
  }
});

test("stem counts code points, not UTF-16 units", () => {
  // an astral letter is ONE code point: these words are three to six code
  // points long, so the length rules treat them as the short words they are
  assert.strictEqual(stem(ASTRAL + "as"), ASTRAL + "as");
  assert.strictEqual(stem(ASTRAL + "aing"), ASTRAL + "aing");
  assert.strictEqual(stem(ASTRAL + "ies"), ASTRAL + "ie");
  assert.strictEqual(stem(ASTRAL + ASTRAL + "ies"), ASTRAL + ASTRAL + "y");
  assert.strictEqual(stem(ASTRAL + "aaing"), ASTRAL + "aa");
});

test("stem never throws and never grows a word", () => {
  // a small seeded generator of our own: the sequence is the same on every runtime
  let state = 20261123;
  const next = (n: number): number => {
    state = (Math.imul(state, 1103515245) + 12345) >>> 0;
    return (state >>> 8) % n;
  };
  const alphabet = [
    ..."abcdefghijklmnopqrstuvwxyz",
    ..."abcdefghijklmnopqrstuvwxyz",
    ..."0123456789 _-",
    ..."ABCSEING",
    E_ACUTE,
    cp(0x4e2d),
    cp(0x1f600),
    ASTRAL,
    cp(0xd800), // a lone surrogate
  ];
  for (let i = 0; i < 50000; i++) {
    let word = "";
    const n = next(13);
    for (let j = 0; j < n; j++) word += alphabet[next(alphabet.length)];
    const out = stem(word);
    assert.strictEqual(typeof out, "string");
    assert.ok(out.length <= word.length, JSON.stringify(word));
    assert.strictEqual(out === "", word === "");
  }
});

test("stem is not part of the public API", () => {
  // ruling S5-1: reached through rescore({ match: "stem" }) and the module only
  assert.ok(!("stem" in api));
});

test("the rule table examples are what the stemmer returns", () => {
  const NL = String.fromCharCode(10);
  const CR = String.fromCharCode(13);
  const doc = readFileSync(new URL("../../../docs/stemmer-rules.md", import.meta.url), "utf-8")
    .split(CR + NL)
    .join(NL);
  const rows = [...doc.matchAll(/^\| `([^`]*)` \| `([^`]*)` \|$/gm)];
  assert.ok(rows.length >= 40, "the rule document lost its worked examples");
  for (const [, word, expected] of rows) assert.strictEqual(stem(word), expected, word);
});
