/**
 * Deterministic context-economy stages — parity port of contexel's Python
 * `stages` module. Every stage is `(records, params) => records`, never
 * mutates its input, and is auto-traced when a trace is active. Behavior
 * matches the Python implementation on the shared golden vectors
 * (parity/vectors.json); boundaries are documented in ADR-001.
 */
import * as tokens from "./tokens.js";
import { traced } from "./trace.js";
import {
  ConfigError,
  InputShapeError,
  checkBool,
  checkChoice,
  checkFields,
  checkNonNegativeInt,
  checkNormalize,
  checkQuery,
  checkStr,
  invalidValue,
} from "./errors.js";
import { stem } from "./stem.js";
import { checked, isMapping } from "./validate.js";
import {
  allowKey,
  codePointIndexer,
  compareCodePoints,
  pyCompare,
  pyRepr,
  pyRound,
  pyRstrip,
  pyStr,
  pyTypeName,
} from "./py.js";

export type Rec = Record<string, unknown>;
export type Records = Rec[];

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

/* ------------------------------ fingerprints ----------------------------- */

/** Python-mapped type tag: int/float distinction for JSON-sourced numbers. */
function typedKey(value: unknown): string {
  if (value === null || value === undefined) return "NoneType:None";
  if (typeof value === "boolean") return `bool:${value}`;
  if (typeof value === "number") {
    return Number.isInteger(value) ? `int:${value}` : `float:${value}`;
  }
  if (typeof value === "string") return `str:${JSON.stringify(value)}`;
  if (Array.isArray(value)) return "list:[" + value.map(typedKey).join(",") + "]";
  if (value instanceof Set) {
    return "set:(" + [...value].map(typedKey).sort().join(",") + ")";
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Rec)
      .map(([k, v]) => `${JSON.stringify(k)}:${typedKey(v)}`)
      .sort();
    return "dict:{" + entries.join(",") + "}";
  }
  return `${typeof value}:${String(value)}`;
}

/* -------------------------------- stages --------------------------------- */

export const select = checked(
  "select",
  true,
  traced(
    "select",
    (records: Records, params: { fields: string | string[] }): Records => {
      const keep = checkFields(params.fields, "select");
      return records.map((r) => {
        const out: Rec = {};
        for (const k of keep) if (Object.hasOwn(r, k)) defineField(out, k, r[k]);
        return out;
      });
    }
  )
);

export const dedupe = checked(
  "dedupe",
  // a key indexes the item; without one the whole item is hashed
  (params?: { key?: string | string[] | null }) => params?.key != null,
  traced(
    "dedupe",
    (records: Records, params: { key?: string | string[] | null } = {}): Records => {
      const key = params.key ?? null;
      const keys = key === null ? null : checkFields(key, "dedupe", "key");
      const seen = new Set<string>();
      const out: Records = [];
      for (const r of records) {
        const basis =
          keys === null ? r : keys.map((k) => (Object.hasOwn(r, k) ? r[k] : null));
        const fp = typedKey(basis);
        if (seen.has(fp)) continue;
        seen.add(fp);
        out.push(r);
      }
      return out;
    }
  )
);

export const allowlist = checked(
  "allowlist",
  true,
  traced(
    "allowlist",
    (records: Records, params: { field: string; allowed: string | unknown[] | Set<unknown> }): Records => {
      checkStr(params.field, "allowlist", "field");
      // a bare string is ONE allowed value, never its characters
      const values = typeof params.allowed === "string" ? [params.allowed] : params.allowed;
      if (!Array.isArray(values) && !(values instanceof Set)) {
        throw invalidValue(
          "allowlist",
          "allowed",
          `allowed must be a string or a list of values, got ${pyTypeName(params.allowed)}`
        );
      }
      const allowed = new Set<string>();
      try {
        for (const a of values) allowed.add(allowKey(a));
      } catch {
        throw invalidValue("allowlist", "allowed", "allowed contains an unhashable value");
      }
      const field = params.field;
      return records.filter((r) => {
        // Python r.get(field): a missing field reads as None, and None can
        // legitimately be allowed; an unhashable value fails closed.
        const v = Object.hasOwn(r, field) ? r[field] : null;
        try {
          return allowed.has(allowKey(v));
        } catch {
          return false;
        }
      });
    }
  )
);

const INJECTION_PATTERNS = [
  "ignore\\s+(?:all\\s+|any\\s+)?(?:previous|prior|above|earlier)\\s+(?:instructions|messages|prompts|context)",
  "disregard\\s+(?:all\\s+|the\\s+)?(?:previous|prior|above|earlier)",
  "you\\s+are\\s+now\\s+",
  "new\\s+instructions\\s*:",
  "system\\s+prompt",
  "</?\\s*(?:system|assistant|instructions?)\\s*>",
];

// the built-ins are trusted and compiled together, once; every caller pattern
// is compiled on its own so it cannot change how the built-ins are read
const BUILTIN_MATCHER = new RegExp(INJECTION_PATTERNS.join("|"), "i");

/** The text a quarantine pattern is matched against for one field value.
 *
 * A string is used as is. A container contributes its object keys (code-point
 * order) and its leaves, each as text, joined by a single space — so a marker
 * split by a newline or a quote inside a nested value is still found (a
 * repr-style rendering would show the newline as a backslash and an `n`).
 * Scalars render with Python's `str()` (`null` is "None", `true` is "True").
 * Iterative, and each container is expanded once, so neither a deeply nested
 * nor a self-referencing value can exhaust the stack or loop. */
function scanText(value: unknown): string {
  const parts: string[] = [];
  const stack: unknown[] = [value];
  const seen = new Set<object>();
  while (stack.length) {
    const v = stack.pop();
    if (typeof v === "string") {
      parts.push(v);
    } else if (Array.isArray(v)) {
      if (seen.has(v)) continue;
      seen.add(v);
      for (let i = v.length - 1; i >= 0; i--) stack.push(v[i]);
    } else if (v !== null && typeof v === "object" && !(v instanceof Set)) {
      if (seen.has(v)) continue;
      seen.add(v);
      const obj = v as Rec;
      const keys = Object.keys(obj).sort(compareCodePoints);
      // pushed in reverse so each key pops just before its value, in order
      for (let i = keys.length - 1; i >= 0; i--) {
        stack.push(obj[keys[i]]);
        stack.push(keys[i]);
      }
    } else {
      parts.push(pyStr(v));
    }
  }
  return parts.join(" ");
}

/**
 * Drop (or, with `action: "flag"`, mark) records whose `fields` contain a
 * prompt-injection marker.
 *
 * Every item must be a mapping: a non-mapping item (string, array, null,
 * number, boolean) ALWAYS throws `InputShapeError` (`input.not_mapping`), in
 * drop and flag mode, strict mode or not, because a screen that skips what it
 * cannot read would keep the attack.
 *
 * `patterns` EXTEND the built-in markers (`replacePatterns: true` is the
 * explicit opt-out). The built-ins and EACH caller pattern are compiled
 * separately and a record is dropped/flagged when ANY of them matches, so a
 * pattern's groups, named groups and numbered backreferences stay its own,
 * and an invalid pattern is named in the `ConfigError`.
 *
 * `normalize: "nfc"` widens detection and never narrows it: the text is
 * scanned as given and also in its Unicode NFC form, and a record is hit if
 * either matches (so a marker typed with a precomposed character is also found
 * in its decomposed spelling). It never touches the patterns; the default
 * (`null`) scans the text as it is. Any other value throws `ConfigError`.
 * NFC costs time that grows with the square of a long run of alternating
 * combining marks: cap the size of text you do not control (README, "Matching:
 * stems and Unicode forms").
 */
export const quarantine = checked(
  "quarantine",
  true,
  traced(
    "quarantine",
    (
      records: Records,
      params: {
        fields?: string | string[];
        patterns?: string | string[] | null;
        action?: "drop" | "flag";
        into?: string;
        replacePatterns?: boolean;
        normalize?: "nfc" | null;
      } = {}
    ): Records => {
      const action = params.action === undefined ? "drop" : params.action;
      if (action !== "drop" && action !== "flag") {
        throw new ConfigError(
          "config.invalid_value",
          `action must be 'drop' or 'flag', got ${String(action)}`,
          { stage: "quarantine", param: "action" }
        );
      }
      // fields=[] would scan nothing: a configured-looking control that does
      // nothing is exactly what this stage refuses to be
      const fields = checkFields(params.fields === undefined ? ["snippet"] : params.fields, "quarantine", "fields", false);
      const into = params.into === undefined ? "quarantined" : params.into;
      checkStr(into, "quarantine", "into");
      const replacePatterns = params.replacePatterns === undefined ? false : params.replacePatterns;
      checkBool(replacePatterns, "quarantine", "replacePatterns");
      const normalize = checkNormalize(params.normalize, "quarantine");
      // custom patterns EXTEND the built-ins: passing domain markers must
      // never silently disable "ignore all previous instructions" detection;
      // replacePatterns is the explicit opt-out
      let matchers: RegExp[];
      if (params.patterns === undefined || params.patterns === null) {
        if (replacePatterns) {
          throw new ConfigError(
            "config.contradictory",
            "replacePatterns without patterns is contradictory; pass the replacement patterns",
            { stage: "quarantine", param: "replacePatterns" }
          );
        }
        matchers = [BUILTIN_MATCHER];
      } else {
        const userPatterns = checkFields(params.patterns, "quarantine", "patterns");
        if (userPatterns.some((p) => !p)) {
          // an empty fragment becomes an empty regex alternative, which
          // matches EVERY record — the opposite of configuring a screen
          throw new ConfigError(
            "config.empty",
            "empty pattern fragments match everything; remove them",
            { stage: "quarantine", param: "patterns" }
          );
        }
        const compiled: RegExp[] = [];
        for (const p of userPatterns) {
          try {
            // each pattern alone (flag "i" only, never g or y: test() would
            // become stateful): its groups and references stay its own
            compiled.push(new RegExp(p, "i"));
          } catch (e) {
            throw new ConfigError(
              "config.invalid_pattern",
              `quarantine: invalid pattern ${pyRepr(p)}: ${(e as Error).message}`,
              { stage: "quarantine", param: "patterns" }
            );
          }
        }
        matchers = replacePatterns ? compiled : [BUILTIN_MATCHER, ...compiled];
      }
      if (!matchers.length) {
        throw new ConfigError(
          "config.empty",
          "replacePatterns with no patterns would disable the control entirely; " +
            "pass at least one pattern",
          { stage: "quarantine", param: "patterns" }
        );
      }
      const out: Records = [];
      for (let i = 0; i < records.length; i++) {
        const r = records[i];
        // fail closed: a non-mapping item would otherwise look like "no field
        // present" and be KEPT (and, in flag mode, spread into the output).
        // isMapping lets any non-array object through, so a Map, Set, Date,
        // RegExp, typed array or boxed primitive is refused here too: only a
        // plain object, a class instance or a null-prototype object is scanned
        const tag = Object.prototype.toString.call(r);
        if (!isMapping(r) || tag !== "[object Object]") {
          const kind = isMapping(r) ? tag.slice(8, -1) : pyTypeName(r);
          throw new InputShapeError(
            "input.not_mapping",
            `quarantine: item ${i} must be a mapping, got ${kind}`,
            { stage: "quarantine" }
          );
        }
        // a missing field reads as ""; containers are scanned leaf by leaf
        const text = fields
          .map((f) => (Object.hasOwn(r, f) ? scanText(r[f]) : ""))
          .join(" ");
        let hit = matchers.some((m) => m.test(text));
        if (!hit && normalize === "nfc") {
          // widen only: the raw text was scanned first, never replaced
          const composed = text.normalize("NFC");
          if (composed !== text) hit = matchers.some((m) => m.test(composed));
        }
        if (action === "flag") {
          if (Object.hasOwn(r, into)) {
            throw new InputShapeError(
              "input.field_conflict",
              `quarantine: record ${i} already has a ${pyRepr(into)} field; pass a different into`,
              { stage: "quarantine", param: "into" }
            );
          }
          out.push({ ...r, [into]: hit });
        } else if (!hit) {
          out.push(r);
        }
      }
      return out;
    }
  )
);

/* Word matching: identical to Python's [^\W_] on ASCII (all parity
   vectors); exotic Unicode word classes may differ at the margin. */
const WORD = /[\p{L}\p{N}]+/gu;

const rescoreStage = traced(
  "rescore",
  (
    records: Records,
    params: {
      query: string | string[];
      fields?: string | string[];
      into?: string;
      proximity?: boolean;
      match?: "word" | "substring" | "stem";
      normalize?: "nfc" | null;
    }
  ): Records => {
    const query = checkQuery(params.query, "rescore");
    const fields = checkFields(params.fields === undefined ? ["snippet"] : params.fields, "rescore", "fields", false);
    const into = params.into === undefined ? "score" : params.into;
    checkStr(into, "rescore", "into");
    const proximity = params.proximity === undefined ? true : params.proximity;
    checkBool(proximity, "rescore", "proximity");
    const match = params.match === undefined ? "word" : params.match;
    checkChoice(match, "rescore", "match", ["word", "substring", "stem"]);
    const normalize = checkNormalize(params.normalize, "rescore");
    // NFC first, then lower-case (ADR-006)
    const prepare = (text: string): string =>
      (normalize === "nfc" ? text.normalize("NFC") : text).toLowerCase();

    const rawTerms =
      typeof query === "string"
        ? prepare(query).match(WORD) ?? []
        : query.flatMap((p) => prepare(String(p)).match(WORD) ?? []);
    const terms = [...new Set(match === "stem" ? rawTerms.map(stem) : rawTerms)];
    if (!terms.length || !records.length) {
      return records.map((r) => ({ ...r, [into]: 0.0 }));
    }

    const texts = records.map((r) =>
      prepare(fields.map((f) => (Object.hasOwn(r, f) ? pyStr(r[f]) : "")).join(" "))
    );

    let finder: RegExp | null = null;
    if (match === "word") {
      const alt = [...terms]
        .sort((a, b) => b.length - a.length)
        .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
        .join("|");
      // boundary guards: underscore counts as a boundary (snake_case splits)
      finder = new RegExp(`(?<![\\p{L}\\p{N}])(?:${alt})(?![\\p{L}\\p{N}])`, "gu");
    }

    const n = records.length;
    const tfs: Array<Map<string, number>> = [];
    const firsts: Array<Map<string, number>> = [];
    const df = new Map<string, number>(terms.map((t) => [t, 0]));
    for (const text of texts) {
      // Python positions are code-point indices; JS regex/indexOf yield
      // UTF-16 units — convert so the proximity window means the same thing.
      const toCp = codePointIndexer(text);
      const row = new Map<string, number>();
      const first = new Map<string, number>();
      if (finder) {
        finder.lastIndex = 0;
        for (const m of text.matchAll(finder)) {
          const t = m[0];
          row.set(t, (row.get(t) ?? 0) + 1);
          if (!first.has(t)) first.set(t, toCp(m.index ?? 0));
        }
      } else if (match === "stem") {
        for (const m of text.matchAll(WORD)) {
          const t = stem(m[0]);
          if (df.has(t)) {
            row.set(t, (row.get(t) ?? 0) + 1);
            if (!first.has(t)) first.set(t, toCp(m.index ?? 0));
          }
        }
      } else {
        for (const t of terms) {
          let idx = text.indexOf(t);
          let cnt = 0;
          const firstIdx = idx;
          while (idx !== -1) {
            cnt++;
            // Python str.count is NON-overlapping: advance past the whole
            // match ("aaaa".count("aa") === 2)
            idx = text.indexOf(t, idx + t.length);
          }
          if (cnt) {
            row.set(t, cnt);
            first.set(t, toCp(firstIdx));
          }
        }
      }
      for (const t of row.keys()) df.set(t, (df.get(t) ?? 0) + 1);
      tfs.push(row);
      firsts.push(first);
    }
    const idf = new Map<string, number>(
      terms.map((t) => [t, Math.log((n - (df.get(t) ?? 0) + 0.5) / ((df.get(t) ?? 0) + 0.5) + 1.0)])
    );

    const k1 = 1.5;
    const window = 80;
    return records.map((r, i) => {
      const row = tfs[i];
      const first = firsts[i];
      let score = 0;
      for (const [t, tf] of row) score += (idf.get(t) ?? 0) * (tf / (tf + k1));
      if (proximity && row.size > 1) {
        for (let j = 0; j + 1 < terms.length; j++) {
          const t1 = terms[j];
          const t2 = terms[j + 1];
          if (first.has(t1) && first.has(t2)) {
            const gap = (first.get(t2) as number) - (first.get(t1) as number);
            if (gap > 0 && gap <= window) {
              score += ((idf.get(t1) ?? 0) + (idf.get(t2) ?? 0)) / 4;
            }
          }
        }
      }
      return { ...r, [into]: pyRound(score, 6) };
    });
  }
);

/**
 * Replaces the tool's relevance score with a deterministic lexical one (BM25
 * style, computed inside the batch; see the Python `rescore` for the details).
 * `match: "word"` (default) counts exact words, `"substring"` raw substrings,
 * `"stem"` reduces every word of the query and the text to its stem with the
 * frozen English stemmer (README). `normalize: "nfc"` applies Unicode NFC to the
 * query and the text before lower-casing; the default `null` changes nothing,
 * and any other value throws `ConfigError`. NFC costs time that grows with the
 * square of a long run of alternating combining marks: cap the size of text you
 * do not control (README, "Matching: stems and Unicode forms").
 */
export const rescore = checked("rescore", true, rescoreStage);

const rankStage = traced(
  "rank",
  (
    records: Records,
    params: { by: string | ((r: Rec) => unknown); desc?: boolean }
  ): Records => {
    const by = params.by;
    if (typeof by !== "string" && typeof by !== "function") {
      throw invalidValue(
        "rank",
        "by",
        `by must be a field name or a key function, got ${pyTypeName(by)}`
      );
    }
    const desc = params.desc === undefined ? true : params.desc;
    checkBool(desc, "rank", "desc");
    const dir = desc ? -1 : 1;
    // decorate-sort-undecorate like Python sorted(key=...): the key is
    // computed once per record, the sort is stable, and reverse=desc keeps
    // ties in original order (never reverse a stable ascending sort).
    const sortKeyed = (rs: Records, keyOf: (r: Rec) => unknown): Records => {
      const keyed = rs.map((r) => [keyOf(r), r] as const);
      keyed.sort((p, q) => dir * pyCompare(p[0], q[0]));
      return keyed.map((p) => p[1]);
    };
    if (typeof by === "function") return sortKeyed([...records], by);
    const present = records.filter((r) => Object.hasOwn(r, by));
    const missing = records.filter((r) => !Object.hasOwn(r, by));
    return [...sortKeyed(present, (r) => r[by]), ...missing];
  }
);

function truncateText(
  text: string,
  maxTokens: number,
  tokenizer: tokens.Tokenizer | null,
  suffix: string
): string {
  if (tokens.count(text, tokenizer) <= maxTokens) return text;
  const budget = Math.max(1, maxTokens - tokens.count(suffix, tokenizer));
  if (tokens.isHeuristic(tokenizer)) {
    // ceil(len/4) is invertible: longest prefix within budget = 4*budget
    // code points (Python slices by code points, so must we).
    const cps = [...text];
    return pyRstrip(cps.slice(0, 4 * budget).join("")) + suffix;
  }
  const cps = [...text];
  let lo = 0;
  let hi = cps.length;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (tokens.count(cps.slice(0, mid).join(""), tokenizer) <= budget) lo = mid;
    else hi = mid - 1;
  }
  return pyRstrip(cps.slice(0, lo).join("")) + suffix;
}

export const rank = checked(
  "rank",
  // a field name indexes each item; a key function takes anything
  (params?: { by?: unknown }) => typeof params?.by === "string",
  rankStage
);

const truncateFieldStage = traced(
  "truncate_field",
  (
    records: Records,
    params: {
      field: string;
      maxTokens: number;
      tokenizer?: tokens.Tokenizer | null;
      suffix?: string;
    }
  ): Records => {
    checkStr(params.field, "truncate_field", "field");
    checkNonNegativeInt(params.maxTokens, "truncate_field", "maxTokens");
    const suffix = params.suffix === undefined ? "…" : params.suffix;
    checkStr(suffix, "truncate_field", "suffix");
    return records.map((r) => {
      const value = r[params.field];
      if (typeof value !== "string") return r;
      return {
        ...r,
        [params.field]: truncateText(value, params.maxTokens, params.tokenizer ?? null, suffix),
      };
    });
  }
);

export const truncateField = checked("truncate_field", true, truncateFieldStage);

const trimToBudgetStage = traced(
  "trim_to_budget",
  (
    records: Records,
    params: { maxTokens: number; tokenizer?: tokens.Tokenizer | null; minRecords?: number }
  ): Records => {
    // minRecords guards the silent-failure edge: a too-small budget would
    // return [], indistinguishable from "nothing matched" — keep the first
    // (best-ranked) records anyway; the overrun shows in the audit.
    checkNonNegativeInt(params.maxTokens, "trim_to_budget", "maxTokens");
    const minRecords = params.minRecords === undefined ? 0 : params.minRecords;
    checkNonNegativeInt(minRecords, "trim_to_budget", "minRecords");
    const out: Records = [];
    let used = 0;
    for (const r of records) {
      const cost = tokens.count(r, params.tokenizer ?? null) + 2; // list framing
      if (used + cost > params.maxTokens && out.length >= minRecords) break;
      out.push(r);
      used += cost;
    }
    return out;
  }
);

// trim_to_budget never indexes an item as a mapping: strict checks only the list
export const trimToBudget = checked("trim_to_budget", false, trimToBudgetStage);

/** Combiner (not auto-traced, matching Python): normalize and concatenate
 * record lists from different tools; `schema` maps unified name -> source
 * name or candidate list (first match wins). */
export function merge(
  sources: Records[],
  options: {
    schema?: Record<string, string | string[]>;
    dedupeKey?: string | null;
  } = {}
): Records {
  const combined: Records = [];
  for (const src of sources) {
    for (const r of src) {
      if (!options.schema) {
        combined.push(r);
        continue;
      }
      const mapped: Rec = {};
      for (const [unified, candidates] of Object.entries(options.schema)) {
        const names = typeof candidates === "string" ? [candidates] : candidates;
        for (const name of names) {
          if (Object.hasOwn(r, name)) {
            defineField(mapped, unified, r[name]);
            break;
          }
        }
      }
      combined.push(mapped);
    }
  }
  if (options.dedupeKey != null) {
    return dedupe(combined, { key: options.dedupeKey });
  }
  return combined;
}
