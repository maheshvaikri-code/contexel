/**
 * Payload stages: carry text through the record stages and back (ADR-005) —
 * parity port of contexel's Python `text` module.
 *
 * Every other stage takes a list of mappings. A log, a web page or a plain
 * string is none of that, so three small stages convert at the edges:
 *
 *     const chunks = split(asRecords(logText), { by: "lines" });   // text -> records
 *     // ... dedupe, rescore, rank, trimToBudget
 *     const text = join(chunks);                                   // records -> text
 *
 * `asRecords` and `join` are the entry and exit points: call them outside
 * `pipeline` (like `merge`), because a pipeline hands every stage a list.
 * `split` is an ordinary traced stage and belongs in a pipeline.
 *
 * Unlike the original stages, these validate the *shape* of their input in
 * every mode, not only in strict mode: they are new, so there is no lenient
 * behavior to stay compatible with.
 *
 * Boundaries are explicit and identical in Python, TypeScript and C#: a line
 * ends after "\n" only (so "\r\n" is one boundary and a lone "\r" is none), a
 * paragraph ends after a run of two or more newlines (`(?:\r?\n){2,}`), and
 * sizes and offsets count code points, never UTF-16 units.
 */
import * as tokens from "./tokens.js";
import { traced } from "./trace.js";
import { ConfigError, InputShapeError, checkChoice, checkStr, invalidValue } from "./errors.js";
import { checked } from "./validate.js";
import { pyRepr, pyTypeName } from "./py.js";
import type { Rec, Records } from "./stages.js";

/** Own-property write that cannot hit setters or the "__proto__" trap —
 * a key named "__proto__" becomes an ordinary data property, as in Python. */
function defineField(out: Rec, key: string, value: unknown): void {
  Object.defineProperty(out, key, {
    value,
    writable: true,
    enumerable: true,
    configurable: true,
  });
}

/** A mapping, as the on-ramp sees one: a plain object (the prototype is
 * `Object.prototype` or `null`). An array, `Set`, `Map`, `Date`, typed array,
 * boxed primitive or class instance is not one. */
function isPlainObject(value: unknown): value is Rec {
  if (value === null || typeof value !== "object") return false;
  if (Object.prototype.toString.call(value) !== "[object Object]") return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/** The name of a value's type for an error message. */
function kindOf(value: unknown): string {
  if (value !== null && typeof value === "object" && !Array.isArray(value) && !(value instanceof Set)) {
    const ctor = (value as { constructor?: { name?: unknown } }).constructor;
    return typeof ctor?.name === "string" && ctor.name ? ctor.name : "object";
  }
  return pyTypeName(value);
}

/**
 * Turn a payload into a list of records, the shape every stage takes.
 *
 * A string becomes `[{ [field]: x }]`; a mapping (a plain object) becomes `[x]`
 * (the same object, not a copy); an array keeps each mapping item and wraps
 * every other item as `{ [field]: item }` (nested JSON values are allowed).
 * `null`, `undefined`, bytes and every other type throw `InputShapeError`
 * (`input.not_list`). `field` must be a non-empty string (`ConfigError`,
 * `config.invalid_value`); the type check runs first. Not traced: it is an
 * entry point.
 */
export function asRecords(x: unknown, options: { field?: string } = {}): Records {
  const isText = typeof x === "string";
  const isList = Array.isArray(x);
  const isMap = isPlainObject(x);
  if (!isText && !isList && !isMap) {
    throw new InputShapeError(
      "input.not_list",
      `as_records: expected a string, a mapping or a list, got ${kindOf(x)}`,
      { stage: "as_records" }
    );
  }
  const field = options.field === undefined ? "text" : options.field;
  checkStr(field, "as_records", "field");
  if (field === "") throw invalidValue("as_records", "field", "field must not be empty");
  const wrap = (item: unknown): Rec => {
    const record: Rec = {};
    defineField(record, field, item);
    return record;
  };
  if (isText) return [wrap(x)];
  if (isMap) return [x];
  return (x as unknown[]).map((item) => (isPlainObject(item) ? item : wrap(item)));
}

const SURROGATE = /[\uD800-\uDFFF]/;

/** Whether a high surrogate at `i` is followed by a low one (one code point). */
function isPair(text: string, i: number): boolean {
  const hi = text.charCodeAt(i);
  if (hi < 0xd800 || hi > 0xdbff) return false;
  const lo = text.charCodeAt(i + 1); // NaN past the end
  return lo >= 0xdc00 && lo <= 0xdfff;
}

/**
 * Cut `text` into chunks and hand each to `emit(chunk, start, end)`, the
 * offsets counted in code points. One pass over the text: every position is
 * looked at a bounded number of times, so a million characters of separators
 * that almost match cost no more than a million of anything else.
 */
function cut(
  text: string,
  by: string,
  size: number | null,
  emit: (chunk: string, start: number, end: number) => void
): void {
  const n = text.length;
  const astral = SURROGATE.test(text); // without a surrogate UTF-16 index === code-point offset
  let from = 0; // UTF-16 index where the next chunk starts
  let cp = 0; // the same place, in code points
  const put = (to: number, known?: number): void => {
    let length = known ?? to - from;
    if (known === undefined && astral) {
      length = 0;
      for (let i = from; i < to; i += isPair(text, i) ? 2 : 1) length++;
    }
    emit(text.slice(from, to), cp, cp + length);
    from = to;
    cp += length;
  };
  if (by === "size") {
    const step = size as number;
    if (!astral) {
      for (let i = step; i < n; i += step) put(i);
    } else {
      while (from < n) {
        let to = from;
        let taken = 0;
        while (to < n && taken < step) {
          to += isPair(text, to) ? 2 : 1;
          taken++;
        }
        put(to, taken);
      }
    }
  } else if (by === "lines") {
    for (let pos = text.indexOf("\n"); pos !== -1; pos = text.indexOf("\n", pos + 1)) put(pos + 1);
  } else {
    // the leftmost run of two or more newline units ("\n" or "\r\n"), taken as
    // long as possible: (?:\r?\n){2,}. A start that yields fewer than two units
    // cannot succeed anywhere up to the point where it stopped, so the scan
    // resumes after that point and never revisits a character.
    let i = 0;
    while (i < n) {
      let j = i;
      let units = 0;
      for (;;) {
        const c = text.charCodeAt(j);
        if (c === 10) j += 1;
        else if (c === 13 && text.charCodeAt(j + 1) === 10) j += 2;
        else break;
        units++;
      }
      if (units >= 2) {
        put(j);
        i = j;
      } else {
        i = j + 1;
      }
    }
  }
  if (from < n) put(n); // the remainder after the last boundary is a chunk
}

/**
 * Cut the text in `field` into chunk records.
 *
 * `by: "lines"` (the default) ends a chunk after each `"\n"`; `by:
 * "paragraphs"` after each run of two or more newlines; `by: "size"` every
 * `size` code points (`size` must then be a positive integer). Every chunk
 * keeps its trailing separator, so joining the chunks with `""` reproduces the
 * text exactly.
 *
 * Each chunk is `{ ...parent, [field]: chunkText, [into]: { index, start, end } }`:
 * `index` counts from 0 within its parent and `[start, end)` are code-point
 * offsets into the original text. A record whose own `field` is not a string
 * passes through untouched (the same object); a string that is empty yields no
 * chunks (that record disappears). A string-valued record that already has its
 * own `into` property throws `InputShapeError` (`input.field_conflict`).
 *
 * `by` must be `"lines"`, `"paragraphs"` or `"size"` and `size` must be omitted
 * for the first two (`ConfigError`: `config.invalid_value` and
 * `config.contradictory`). Items must be mappings: this stage checks its input
 * in every mode.
 *
 * `rank` reorders chunks by score. To restore reading order before `join`,
 * rank again with `by: (r) => r.chunk.start` and `desc: false`.
 */
export const split = checked(
  "split",
  true,
  traced(
    "split",
    (
      records: Records,
      params: {
        field?: string;
        by?: "lines" | "paragraphs" | "size";
        size?: number | null;
        into?: string;
      } = {}
    ): Records => {
      const field = params.field === undefined ? "text" : params.field;
      checkStr(field, "split", "field");
      const by = params.by === undefined ? "lines" : params.by;
      checkChoice(by, "split", "by", ["lines", "paragraphs", "size"]);
      const into = params.into === undefined ? "chunk" : params.into;
      checkStr(into, "split", "into");
      const size = params.size === undefined ? null : params.size;
      if (by === "size") {
        if (typeof size !== "number" || !Number.isInteger(size) || size < 1) {
          throw invalidValue(
            "split",
            "size",
            `size must be a positive integer when by='size', got ${pyRepr(size)}`
          );
        }
      } else if (size !== null) {
        throw new ConfigError(
          "config.contradictory",
          `split: size=${pyRepr(size)} only applies to by='size', got by=${pyRepr(by)}`,
          { stage: "split", param: "size" }
        );
      }
      const out: Records = [];
      for (let i = 0; i < records.length; i++) {
        const r = records[i];
        const text = Object.hasOwn(r, field) ? r[field] : undefined;
        if (typeof text !== "string") {
          out.push(r);
          continue;
        }
        if (Object.hasOwn(r, into)) {
          throw new InputShapeError(
            "input.field_conflict",
            `split: record ${i} already has a ${pyRepr(into)} field; pass a different into`,
            { stage: "split", param: "into" }
          );
        }
        let index = 0;
        cut(text, by, size, (chunk, start, end) => {
          const c: Rec = { ...r };
          defineField(c, field, chunk);
          defineField(c, into, { index: index++, start, end });
          out.push(c);
        });
      }
      return out;
    },
    { keepsIds: true }
  ),
  true
);

/**
 * Join the `field` of every record into one string.
 *
 * A record without its own `field` is skipped; a string value is used as it is;
 * any other value is rendered with `tokens.serialize`, the text the token
 * budget priced. The parts are joined with `sep`. Items must be mappings
 * (checked in every mode). Not traced: it is an exit point.
 */
export const join = checked(
  "join",
  true,
  (records: Records, params: { field?: string; sep?: string } = {}): string => {
    const field = params.field === undefined ? "text" : params.field;
    checkStr(field, "join", "field");
    const sep = params.sep === undefined ? "" : params.sep;
    checkStr(sep, "join", "sep");
    const parts: string[] = [];
    for (const r of records) {
      if (!Object.hasOwn(r, field)) continue;
      const value = r[field];
      parts.push(typeof value === "string" ? value : tokens.serialize(value));
    }
    return parts.join(sep);
  },
  true
);
