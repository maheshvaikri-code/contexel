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
  codePointIndexer,
  pyCompare,
  pyEqKey,
  pyRound,
  pyRstrip,
  pyStr,
} from "./py.js";

export type Rec = Record<string, unknown>;
export type Records = Rec[];

/** A bare string means ONE field, not its characters (parity with Python). */
function fieldList(fields: string | string[]): string[] {
  return typeof fields === "string" ? [fields] : fields;
}

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

export const select = traced(
  "select",
  (records: Records, params: { fields: string | string[] }): Records => {
    const keep = fieldList(params.fields);
    return records.map((r) => {
      const out: Rec = {};
      for (const k of keep) if (Object.hasOwn(r, k)) defineField(out, k, r[k]);
      return out;
    });
  }
);

export const dedupe = traced(
  "dedupe",
  (records: Records, params: { key?: string | string[] | null } = {}): Records => {
    const key = params.key ?? null;
    const keys = key === null ? null : Array.isArray(key) ? key : [key];
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
);

export const allowlist = traced(
  "allowlist",
  (records: Records, params: { field: string; allowed: unknown[] | Set<unknown> }): Records => {
    // Python builds set(allowed) up front: an unhashable entry raises.
    const allowed = new Set<string>();
    for (const a of params.allowed) allowed.add(pyEqKey(a));
    return records.filter((r) => {
      // Python r.get(field): a missing field reads as None, and None can
      // legitimately be allowed; unhashable values fail closed.
      const v = Object.hasOwn(r, params.field) ? r[params.field] : null;
      try {
        return allowed.has(pyEqKey(v));
      } catch {
        return false;
      }
    });
  }
);

const INJECTION_PATTERNS = [
  "ignore\\s+(?:all\\s+|any\\s+)?(?:previous|prior|above|earlier)\\s+(?:instructions|messages|prompts|context)",
  "disregard\\s+(?:all\\s+|the\\s+)?(?:previous|prior|above|earlier)",
  "you\\s+are\\s+now\\s+",
  "new\\s+instructions\\s*:",
  "system\\s+prompt",
  "</?\\s*(?:system|assistant|instructions?)\\s*>",
];

export const quarantine = traced(
  "quarantine",
  (
    records: Records,
    params: {
      fields?: string | string[];
      patterns?: string[];
      action?: "drop" | "flag";
      into?: string;
    } = {}
  ): Records => {
    const fields = fieldList(params.fields ?? ["snippet"]);
    const action = params.action ?? "drop";
    const into = params.into ?? "quarantined";
    if (action !== "drop" && action !== "flag") {
      throw new Error(`action must be 'drop' or 'flag', got ${String(action)}`);
    }
    const matcher = new RegExp((params.patterns ?? INJECTION_PATTERNS).join("|"), "i");
    const out: Records = [];
    for (const r of records) {
      // Python str(r.get(f, "")): None -> "None", nested containers via
      // repr — a payload inside a dict or list still hits the matcher.
      const text = fields
        .map((f) => (Object.hasOwn(r, f) ? pyStr(r[f]) : ""))
        .join(" ");
      const hit = matcher.test(text);
      if (action === "flag") out.push({ ...r, [into]: hit });
      else if (!hit) out.push(r);
    }
    return out;
  }
);

/* Word matching: identical to Python's [^\W_] on ASCII (all parity
   vectors); exotic Unicode word classes may differ at the margin. */
const WORD = /[\p{L}\p{N}]+/gu;

export const rescore = traced(
  "rescore",
  (
    records: Records,
    params: {
      query: string | string[];
      fields?: string | string[];
      into?: string;
      proximity?: boolean;
      match?: "word" | "substring";
    }
  ): Records => {
    const fields = fieldList(params.fields ?? ["snippet"]);
    const into = params.into ?? "score";
    const proximity = params.proximity ?? true;
    const match = params.match ?? "word";

    const rawTerms =
      typeof params.query === "string"
        ? params.query.toLowerCase().match(WORD) ?? []
        : params.query.flatMap((p) => String(p).toLowerCase().match(WORD) ?? []);
    const terms = [...new Set(rawTerms)];
    if (!terms.length || !records.length) {
      return records.map((r) => ({ ...r, [into]: 0.0 }));
    }

    const texts = records.map((r) =>
      fields
        .map((f) => (Object.hasOwn(r, f) ? pyStr(r[f]) : ""))
        .join(" ")
        .toLowerCase()
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
      } else {
        for (const t of terms) {
          let idx = text.indexOf(t);
          let cnt = 0;
          const firstIdx = idx;
          while (idx !== -1) {
            cnt++;
            idx = text.indexOf(t, idx + 1);
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

export const rank = traced(
  "rank",
  (
    records: Records,
    params: { by: string | ((r: Rec) => unknown); desc?: boolean }
  ): Records => {
    const desc = params.desc ?? true;
    const by = params.by;
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

export const truncateField = traced(
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
    const suffix = params.suffix ?? "…";
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

export const trimToBudget = traced(
  "trim_to_budget",
  (
    records: Records,
    params: { maxTokens: number; tokenizer?: tokens.Tokenizer | null; minRecords?: number }
  ): Records => {
    // minRecords guards the silent-failure edge: a too-small budget would
    // return [], indistinguishable from "nothing matched" — keep the first
    // (best-ranked) records anyway; the overrun shows in the audit.
    const minRecords = params.minRecords ?? 0;
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
