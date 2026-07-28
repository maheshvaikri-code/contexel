/**
 * Python-semantics helpers — the parity layer under stages/tokens/trace.
 * Each function replicates the exact CPython behavior the canon relies on;
 * remaining margins (exotic repr escapes, huge integers, list-vs-list
 * comparison in sorts) are documented in ADR-001.
 */

/** repr(float): fixed notation for 1e-4 <= |x| < 1e16, else scientific
 * with a sign and a two-digit exponent. JS switches at 1e-7/1e21, so
 * String(1e-5) === "0.00001" where Python says "1e-05". */
export function pyFloat(value: number): string {
  const [mant, expStr] = value.toExponential().split("e");
  const exp = parseInt(expStr, 10);
  const neg = mant.startsWith("-");
  const digits = mant.replace("-", "").replace(".", "");
  let body: string;
  if (exp < -4 || exp >= 16) {
    const m = digits.length > 1 ? digits[0] + "." + digits.slice(1) : digits;
    body = m + "e" + (exp < 0 ? "-" : "+") + String(Math.abs(exp)).padStart(2, "0");
  } else if (exp >= 0) {
    body = digits.slice(0, exp + 1).padEnd(exp + 1, "0") + "." + (digits.slice(exp + 1) || "0");
  } else {
    body = "0." + "0".repeat(-exp - 1) + digits;
  }
  return neg ? "-" + body : body;
}

/** str() for numbers: int digits, nan/inf like Python, pyFloat otherwise.
 * Integer-valued floats collapse to int form (ADR-001 boundary 4a). */
export function pyNumber(value: number): string {
  if (Number.isNaN(value)) return "nan";
  if (!Number.isFinite(value)) return value > 0 ? "inf" : "-inf";
  if (Number.isInteger(value)) return String(value);
  return pyFloat(value);
}

function pyTypeName(value: unknown): string {
  if (value === null || value === undefined) return "NoneType";
  if (Array.isArray(value)) return "list";
  if (value instanceof Set) return "set";
  switch (typeof value) {
    case "boolean": return "bool";
    case "number": return Number.isInteger(value) ? "int" : "float";
    case "string": return "str";
    case "object": return "dict";
    default: return typeof value;
  }
}

/** repr(str): quote choice + escapes for control characters. Exotic
 * non-printables (Unicode Cf/Zs beyond Latin-1) stay literal — an ADR-001
 * margin; ASCII and common text are exact. */
function pyReprStr(s: string): string {
  const q = s.includes("'") && !s.includes('"') ? '"' : "'";
  let out = q;
  for (const ch of s) {
    const c = ch.codePointAt(0)!;
    if (ch === "\\" || ch === q) out += "\\" + ch;
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    else if (c < 0x20 || (c >= 0x7f && c <= 0xa0) || c === 0xad) {
      out += "\\x" + c.toString(16).padStart(2, "0");
    } else out += ch;
  }
  return out + q;
}

/** repr(): containers render Python-style ({'k': 'v'}, ['a', 1]). */
export function pyRepr(value: unknown): string {
  if (value === undefined || value === null) return "None";
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value === "number") return pyNumber(value);
  if (typeof value === "string") return pyReprStr(value);
  if (Array.isArray(value)) return "[" + value.map(pyRepr).join(", ") + "]";
  if (typeof value === "object" && !(value instanceof Set)) {
    const entries = Object.entries(value as Record<string, unknown>).map(
      ([k, v]) => `${pyReprStr(k)}: ${pyRepr(v)}`
    );
    return "{" + entries.join(", ") + "}";
  }
  return String(value);
}

/** str(): what Python's `str(r.get(f, ""))` produces for JSON-safe values —
 * None -> "None", True -> "True", nested containers via repr. */
export function pyStr(value: unknown): string {
  if (typeof value === "string") return value;
  return pyRepr(value);
}

/** round(x, nd) with CPython semantics: correctly rounded on the double's
 * EXACT value, ties to even. A tie exists iff x is exactly k/2^(nd+1) with
 * k odd (the only doubles whose decimal expansion ends in ...5 at digit
 * nd+1); everything else is unambiguous and toFixed rounds it correctly.
 * So 2.675 (really 2.67499...82) rounds DOWN to 2.67 like Python, while a
 * true tie like 0.90625 -> 0.9062 goes to even. */
export function pyRound(x: number, nd: number): number {
  const scaled2 = x * 2 ** (nd + 1); // power-of-two scaling is exact
  if (Number.isInteger(scaled2) && Math.abs(scaled2) % 2 === 1) {
    const trunc = x.toFixed(nd + 1).slice(0, -1); // exact digits, drop the "5"
    const digits = trunc.replace(/[-.]/g, "");
    const last = digits ? digits.charCodeAt(digits.length - 1) - 48 : 0;
    const v = Number(last % 2 === 0 ? trunc : bumpLastDigit(trunc));
    return v === 0 ? 0 : v;
  }
  const v = Number(x.toFixed(nd));
  return v === 0 ? 0 : v;
}

function bumpLastDigit(s: string): string {
  const neg = s.startsWith("-");
  const chars = (neg ? s.slice(1) : s).split("");
  let carry = 1;
  for (let i = chars.length - 1; i >= 0 && carry; i--) {
    if (chars[i] === ".") continue;
    const d = chars[i].charCodeAt(0) - 48 + carry;
    chars[i] = String(d % 10);
    carry = d >= 10 ? 1 : 0;
  }
  if (carry) chars.unshift("1");
  return (neg ? "-" : "") + chars.join("");
}

/** Python string `<`: code-point order. JS `<` is UTF-16 order, which sorts
 * astral characters below U+E000..U+FFFF. */
export function compareCodePoints(a: string, b: string): number {
  const ia = a[Symbol.iterator]();
  const ib = b[Symbol.iterator]();
  for (;;) {
    const ra = ia.next();
    const rb = ib.next();
    if (ra.done && rb.done) return 0;
    if (ra.done) return -1;
    if (rb.done) return 1;
    const ca = ra.value.codePointAt(0)!;
    const cb = rb.value.codePointAt(0)!;
    if (ca !== cb) return ca < cb ? -1 : 1;
  }
}

/** Python comparison for sort keys: numbers/bools inter-compare, strings by
 * code point, anything else raises TypeError like CPython (lists, which
 * Python would compare element-wise, are an ADR-001 margin). */
export function pyCompare(a: unknown, b: unknown): number {
  const an = typeof a === "number" || typeof a === "boolean";
  const bn = typeof b === "number" || typeof b === "boolean";
  if (an && bn) {
    const x = Number(a);
    const y = Number(b);
    return x < y ? -1 : x > y ? 1 : 0;
  }
  if (typeof a === "string" && typeof b === "string") return compareCodePoints(a, b);
  throw new TypeError(
    `'<' not supported between instances of '${pyTypeName(b)}' and '${pyTypeName(a)}'`
  );
}

/** Membership key with Python hash/eq semantics: True == 1 == 1.0, None is
 * its own class; dict/list/set raise TypeError (unhashable) like set(). */
export function pyEqKey(value: unknown): string {
  if (value === undefined || value === null) return "None";
  if (typeof value === "boolean") return "num:" + (value ? 1 : 0);
  if (typeof value === "number") return "num:" + value;
  if (typeof value === "string") return "str:" + value;
  throw new TypeError(`unhashable type: '${pyTypeName(value)}'`);
}

/** Map a UTF-16 index to a code-point index (Python str positions). The
 * common no-surrogate case is the identity, at no cost. */
export function codePointIndexer(text: string): (utf16Index: number) => number {
  if (!/[\uD800-\uDFFF]/.test(text)) return (i) => i;
  const map = new Map<number, number>();
  let cp = 0;
  let i = 0;
  while (i < text.length) {
    map.set(i, cp);
    i += text.codePointAt(i)! > 0xffff ? 2 : 1;
    cp++;
  }
  map.set(text.length, cp);
  return (idx) => map.get(idx)!;
}

/** Trailing-whitespace strip matching Python str.rstrip(): includes the
 * file/group/record/unit separators (0x1C-0x1F) and NEL (0x85), and does
 * NOT strip U+FEFF (which JS \s wrongly includes). */
const PY_TRAILING_WS =
  /[\t-\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/u;

export function pyRstrip(text: string): string {
  return text.replace(PY_TRAILING_WS, "");
}
