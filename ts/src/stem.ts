/**
 * A small, frozen English suffix stemmer (ADR-006, docs/stemmer-rules.md) —
 * parity port of contexel's Python `stem` module.
 *
 * `rescore({ match: "stem" })` reduces every word to a stem before counting, so
 * `parse`, `parses`, `parsed` and `parsing` are one term. The rules are a short,
 * ordered list that Python and C# repeat exactly: the result is pinned by the
 * shared vectors, never by "close enough". The stemmer is FROZEN (a future
 * improvement ships under a new `match` name), English only, not a lemmatizer
 * (`configure` and `config` stay apart, `speed` becomes `spe`), and expects
 * lower-case input. Lengths are counted in code points, not UTF-16 units. It
 * never throws and never makes a word longer. It is not part of the public
 * API: `rescore` is how it is used.
 */

/** a doubled letter from this set loses one copy after "ing"/"ed" is stripped
 * (running -> run, stopped -> stop); "l", "s" and "z" keep both */
const UNDOUBLE = "bcdfghjkmnpqrtvwx";
const VOWEL = /[aeiouy]/;

/** Length in code points, as Python's len() counts it (a lone surrogate is one). */
function cpLength(text: string): number {
  let n = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < text.length) {
      const d = text.charCodeAt(i + 1);
      if (d >= 0xdc00 && d <= 0xdfff) i++;
    }
    n++;
  }
  return n;
}

/** Return the stem of an already lower-case `word`. */
export function stem(word: string): string {
  if (cpLength(word) <= 3) return word;
  let w = word;
  // 1. plurals: the first rule that applies wins
  if (w.endsWith("sses")) {
    w = w.slice(0, -2);
  } else if (w.endsWith("ies") && cpLength(w) > 4) {
    w = w.slice(0, -3) + "y";
  } else if (w.endsWith("ied") && cpLength(w) > 4) {
    w = w.slice(0, -3) + "y";
  } else if (w.endsWith("s") && !(w.endsWith("ss") || w.endsWith("us") || w.endsWith("is"))) {
    w = w.slice(0, -1);
  }
  // 2. "ing" or "ed", never both: the one the word ends with is the only one
  //    considered; it is stripped only if a vowel-bearing base of at least
  //    three code points remains
  const suffix = w.endsWith("ing") ? "ing" : w.endsWith("ed") ? "ed" : "";
  if (suffix) {
    const base = w.slice(0, -suffix.length);
    if (cpLength(base) >= 3 && VOWEL.test(base)) {
      w = base;
      const last = w.charAt(w.length - 1);
      if (last === w.charAt(w.length - 2) && UNDOUBLE.includes(last)) w = w.slice(0, -1);
    }
  }
  // 3. a final "e"
  if (cpLength(w) > 3 && w.endsWith("e")) w = w.slice(0, -1);
  return w;
}
