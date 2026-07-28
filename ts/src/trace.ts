/**
 * Per-stage observability — parity port of contexel's Python `trace`.
 * `trace({idField}, fn)` runs `fn` with an active trace (AsyncLocalStorage,
 * the JS analog of contextvars) and records what every stage did; with
 * `idField` it also records which records each stage dropped (records
 * lacking the field are untracked). `audit()` is the governance record.
 */
import { AsyncLocalStorage } from "node:async_hooks";
import * as tokens from "./tokens.js";
import { pyRound } from "./py.js";

export interface Entry {
  stage: string;
  inCount: number;
  outCount: number;
  tokensBefore: number;
  tokensAfter: number;
  droppedIds: unknown[];
}

export class Trace {
  entries: Entry[] = [];
  policies: string[] = [];
  idField: string | null;

  constructor(idField: string | null = null) {
    this.idField = idField;
  }

  get tokensBefore(): number {
    return this.entries.length ? this.entries[0].tokensBefore : 0;
  }

  get tokensAfter(): number {
    return this.entries.length ? this.entries[this.entries.length - 1].tokensAfter : 0;
  }

  get reduction(): number {
    const before = this.tokensBefore;
    return before === 0 ? 0 : 1 - this.tokensAfter / before;
  }

  report(): string {
    if (!this.entries.length) return "(no stages traced)";
    const lines = this.entries.map(
      (e) =>
        `${e.stage.padEnd(16)} ${String(e.inCount).padStart(5)} -> ` +
        `${String(e.outCount).padEnd(5)} ${e.tokensBefore.toLocaleString("en-US").padStart(7)} -> ` +
        `${e.tokensAfter.toLocaleString("en-US").padEnd(7)} tokens`
    );
    lines.push("-".repeat(56));
    lines.push(
      `${"total".padEnd(16)} ${"".padStart(5)}    ${"".padEnd(5)} ` +
        `${this.tokensBefore.toLocaleString("en-US").padStart(7)} -> ` +
        `${this.tokensAfter.toLocaleString("en-US").padEnd(7)} tokens  ` +
        `(${pyRound(this.reduction * 100, 0)}% reduction)`
    );
    return lines.join("\n");
  }

  /** JSON-able governance record: policy fingerprints, per-stage dropped
   * record ids (stage = removal reason; records lacking the field are
   * untracked), token movement. */
  audit(): Record<string, unknown> {
    return {
      policies: [...this.policies],
      id_field: this.idField,
      tokens_before: this.tokensBefore,
      tokens_after: this.tokensAfter,
      reduction: pyRound(this.reduction, 4), // Python round(): half to even
      stages: this.entries.map((e) => ({
        stage: e.stage,
        records_in: e.inCount,
        records_out: e.outCount,
        tokens_before: e.tokensBefore,
        tokens_after: e.tokensAfter,
        dropped_ids: [...e.droppedIds],
      })),
    };
  }
}

const store = new AsyncLocalStorage<Trace>();

export function currentTrace(): Trace | null {
  return store.getStore() ?? null;
}

/** Run `fn` with an active trace; returns [result, trace]. */
export function trace<T>(
  options: { idField?: string } | null,
  fn: () => T
): [T, Trace] {
  const tr = new Trace(options?.idField ?? null);
  const result = store.run(tr, fn);
  return [result, tr];
}

type Rec = Record<string, unknown>;

function idKey(value: unknown): unknown {
  if (value !== null && typeof value === "object") return tokens.pythonJson(value);
  return value;
}

/** Wrap a stage so an active trace records its effect (incl. dropped ids). */
export function traced<A extends unknown[]>(
  name: string,
  fn: (records: Rec[], ...args: A) => Rec[]
): (records: Rec[], ...args: A) => Rec[] {
  return (records: Rec[], ...args: A): Rec[] => {
    const tr = currentTrace();
    if (!tr) return fn(records, ...args);
    const beforeN = records.length;
    const beforeTok = tokens.count(records);
    const out = fn(records, ...args);
    const dropped: unknown[] = [];
    const fid = tr.idField;
    if (fid) {
      const remaining = new Map<unknown, number>();
      let unidentified = 0; // survivors without the id field absorb drops
      for (const r of out) {
        if (r !== null && typeof r === "object" && Object.hasOwn(r, fid)) {
          const k = idKey((r as Rec)[fid]);
          remaining.set(k, (remaining.get(k) ?? 0) + 1);
        } else {
          unidentified++;
        }
      }
      for (const r of records) {
        if (r !== null && typeof r === "object" && Object.hasOwn(r, fid)) {
          const original = (r as Rec)[fid];
          const k = idKey(original);
          const left = remaining.get(k) ?? 0;
          if (left > 0) remaining.set(k, left - 1);
          else if (unidentified > 0) unidentified--;
          else dropped.push(original);
        }
      }
    }
    tr.entries.push({
      stage: name,
      inCount: beforeN,
      outCount: out.length,
      tokensBefore: beforeTok,
      tokensAfter: tokens.count(out),
      droppedIds: dropped,
    });
    return out;
  };
}
