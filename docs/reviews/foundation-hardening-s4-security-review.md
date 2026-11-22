> Filed 2026-11-22 from the Slice 4 review workspace for branch `feat/hardening-s4-payload-stages` (reviewed at head `d5eebcb`; the fix wave that followed is summarised in section 9). Sanitised: no user name, home or temporary path, e-mail address or agent identifier. Gate G5 security (read-only review with measurements; the reviewer held the ship veto).

# G5 Security Review - Foundation hardening Slice 4 (payload stages) @ d5eebcb

**Security Reviewer** (fresh-context verifier, G5) - **Date:** 2026-11-22
**Range:** `7b1a507..d5eebcb` (base = main with Slice 3 merged). The reviewer read the source and the diff, and ran experiments in Python 3.12.7 (checkout confirmed through `contexel.__file__`), Node v24.18.0 against `ts/dist` and .NET 8 (a throwaway console project referencing `Contexel.csproj`). The checkout was never changed (`git status --short` empty).

## Decision: APPROVE WITH CONDITIONS (no veto)

The linear-time claim holds in all three languages. No prototype pollution, no injection through error messages, no new dependency and no secret were found. There was no documented resource bound, though, and the documentation presents `split` as the path for untrusted logs, web pages and tool output. Two amplification paths had to be documented before release, and one C# input-validation gap had to be fixed or listed. All conditions were met by the fix wave (section 9).

## 1. Linear-time claim: SAFE (time); one Low finding on Python memory

Read: Python lines use a `str.find` loop, size uses `range`, paragraphs used `re.finditer(r"(?:\r?\n){2,}")` (each start attempt either fails within two characters or consumes the whole run greedily: no catastrophic backtracking); the TypeScript `cut` and the C# `Ends` scan resume at `j+1` or `j` and never revisit a character; code points are counted per chunk, so the sum is linear; no string concatenation in a loop.

Measured (chunk ends only, 100k / 1M / 4M characters; 14 adversarial patterns: `\r`, `\r\n`, `\n\r`, `\r\r\n`, `\n`, `\r\n...x`, `\n...x`, `\nx`, `\r\n\r`, `a`, an astral character, `\r\r\n\n`, a lone surrogate): every curve scales about linearly. Examples at 4M characters: Python paragraphs worst case (`\n`) 676 ms; TypeScript paragraphs at most 24 ms (`\r\r\n\n`, 1M chunks, 455 ms); C# paragraphs at most 7.4 ms (`\r\r\n\n` 906 ms). Full `split` by lines on `\n`: TypeScript 49 / 771 / 3,179 ms and C# 59 / 1,117 / 3,173 ms at 100k / 1M / 4M, dominated by building the records. Python full `split`, 1M / 4M of `\n`: 2.0 s / 8.9 s (4.5 s / 17.0 s traced); the jump at 4M comes from CPython's garbage collector, not the algorithm (with `gc.disable()`, size=1 measured 0.76 / 1.47 / 3.14 s at 1 / 2 / 4M).

**S4-SEC-3 (Low): the Python paragraph regex used memory proportional to the longest newline run.** `sre` keeps backtracking state for every repetition of the group. Measured peak (`tracemalloc`): 1M `\n` = 122 MB, 4M = 583 MB, 16M = 2.2 GB and 4.5 s; 4M of `\r\n` = 299 MB; runs of 1,000 newlines (4M characters in total) peak at 0.15 MB, so the cost is per run. The TypeScript and C# scanners need no such memory (17 ms and 4 ms at 4M). Scenario: a 16 MB tool output made of newlines, sent through `by="paragraphs"` (which returns one chunk), allocates 2.2 GB in Python only. Fix: a hand-written scanner, plus a memory assertion in the adversarial test.

## 2. Resource bound: two Medium findings

**S4-SEC-1 (Medium): one record per separator, no cap, no documented bound.** Retained memory per input character at one chunk per character (1,000,000 characters):

| Language | Input | Retained | Per character | Time |
|---|---|---|---|---|
| Python | `size=1` or lines on `\n` | 436 MB | 436 B | 0.7-2.0 s |
| Python | CJK characters | 496 MB | 496 B | |
| TypeScript | heap delta | 139.6 MB | 140 B | 0.37 s |
| C# | `GC.GetTotalMemory` | 536.4 MB | 536 B | 0.8-1.0 s |

Traced, 1M lines took 4.5 s in Python, 3.2 s in TypeScript and 2.3 s in C#. Extrapolated (not measured): 20 MB of `\n` would need about 9 GB in Python, 11 GB in C# and 2.8 GB in TypeScript. A service feeding unbounded tool output through `split` can be pushed out of memory. Condition: document the amplification and advise capping the input before `split`; a `max_chunks` limit with a typed error can be considered in a later slice.

**S4-SEC-2 (Medium): copying the parent into every chunk makes serialization quadratic.** Chunks are shallow copies of the parent, so memory is shared, but every consumer that prices tokens serializes each chunk in full (`traced` calls `tokens.count(out)`, and `trim_to_budget` does the same). With a 50,000-character side field:

| Measurement | N=1000 | N=2000 | N=4000 |
|---|---|---|---|
| Python traced `split` | 168 ms | 341 ms | 692 ms |
| Python traced peak memory | 54 MB | 121 MB | 272 MB (5,036 B per input character) |
| Python `trim_to_budget` (huge budget) | 216 ms | 364 ms | 645 ms |
| TypeScript traced | 509 ms | 855 ms | 1,959 ms |
| C# traced | 166 ms | 285 ms | 587 ms |

An untraced `split` took 0-4 ms. The cost is O(N x M), N = chunk count, M = size of the other fields. Exploit (extrapolated, not run): `as_records(tool_result)` keeps a mapping as is, so `split(field="stdout")` on `{"stdout": 100k newlines, "stderr": 1 MB}` gives about 10^11 characters to serialize under a trace or a budget: a hang or out-of-memory (in TypeScript a `RangeError` at V8's string limit). Condition: document it and advise `select`ing the needed fields before `split`; an option to drop or limit inherited fields may follow later.

**Size types: SAFE.** Python: `True`, `False`, `2.0`, `1.5`, inf, NaN, -1, 0, `'2'`, `None` are rejected with `config.invalid_value`; `10**100` gives one chunk. TypeScript: 1.5, Infinity, NaN, -0, `true`, `5n` are rejected; `2.0` is accepted as 2 (documented); 1e300 and `MAX_SAFE_INTEGER+2` give one chunk. C#: 0, -1, `int.MinValue`, null are rejected; `int.MaxValue` and `int.MaxValue-1` give one chunk; no overflow (`j` stays at most n, offsets are `long`, a `long` size is clamped to `int.MaxValue`).

## 3. TypeScript prototype hazards: SAFE

All measured. `into` named `__proto__`, `constructor`, `toString`, `hasOwnProperty` or `__defineGetter__` becomes an own data property and the chunk's prototype stays `Object.prototype`. Records from `JSON.parse` with an own `__proto__` (`{"__proto__": {"isAdmin": true}}`): chunks get `isAdmin` undefined, the prototype is unchanged, `__proto__` stays an own property and `({}).isAdmin` is undefined (no pollution); `field: "__proto__"` splits the own value correctly; an own `__proto__` with `into: "__proto__"` raises `field_conflict`. Inherited names (`field: "constructor"` or `"toString"`) pass through untouched; `into: "constructor"` fires no false conflict; `join` with `field: "constructor"` skips the record. Mechanism: `Object.hasOwn` for every read and conflict check, `Object.defineProperty` for every write, spread copies own keys as data properties. `isPlainObject` rejects Map, Set, Date, Uint8Array, Buffer, class instances, boxed String, `arguments`, functions, bigint, null, undefined and objects with `Symbol.toStringTag`, and accepts null-prototype objects. Info: a cross-realm plain object (`vm`) is rejected at the top level but wrapped as `{text: obj}` as a list item: inconsistent, fails toward refusing, not exploitable.

## 4. `join` and `serialize` on untrusted values: SAFE for this slice; one pre-existing Low finding

**S4-SEC-6 (Low, pre-existing): C# `Tokens.PythonJson` recurses with no depth limit and no cycle detection.** Measured: a nested list at depth 2,000 works; depth 5,000 and any cycle crash with an uncatchable stack overflow. Python raises catchable errors (`ValueError` on a cycle, `RecursionError` at depth 100k); TypeScript throws a catchable `RangeError` on a cycle and on a 100k-deep value. New exposure versus pre-existing: `join` adds one more path into the same serializer, for field values; the same serializer was already reached by `Tokens.Count` in `Trace.Traced` and in budget pricing, so the root cause predates this slice. Untrusted JSON in C# is capped by System.Text.Json's default `MaxDepth` of 64 (a depth-1,000 parse threw), and JSON cannot express cycles. Fix (later, Slice 7): a depth cap with a typed error in all three serializers.

Other pre-existing serializer behavior that `join` now shows as text (no security impact for text bound for an LLM): `NaN` and `Infinity` come out as bare words; Python raises `ValueError` for integers over 4,300 digits and `TypeError` for keys of mixed types; lone surrogates stay raw in Python and C# (TypeScript escapes them inside containers); C# throws `InvalidCastException` on non-string dictionary keys; TypeScript renders a function as its source and a Map or Date as `{}`. `join` itself is linear: 1M records in 177 ms (Python) and 138 ms (TypeScript).

## 5. Error messages and information leaks: SAFE

Measured in all three languages: no message echoes record contents (item errors name the index and the type, for example `item 1 must be a mapping, got str`); the configuration values `into`, `by` and `size` are echoed through `repr`-style escaping (an `into` of `x\n<ESC>[31mFAKE` appears with its control characters escaped, so it cannot forge a log line); type names come from the runtime, not from attacker data.

## 6. Trust boundary of `always` and `keeps_ids`: SAFE (Info only)

`keeps_ids` only forces `lost = 0`, so the dropped list is always a superset of what the default Slice 3 rule would report; it cannot under-report relative to Slice 3. Over-reporting happens only when `id_field` equals the split field (both parents reported dropped, measured) or when a custom Python stage declares it wrongly. Under-reporting cases: the documented duplicate-id case (measured: the drop is hidden), and an `id_key` collision of the list `[1]` and the string `"[1]"` in Python and TypeScript (measured; C# prefixes keys with their type); impact is limited because `split` only ever drops records whose text is empty. `always` only adds checks (a non-strict `split([1])` raises `input.not_mapping`); the only way around strict mode is Python's `split.__wrapped__`, reachable only by the caller's own code. Info (availability): one hostile record carrying the `into` key aborts the whole `split` call with `field_conflict`; this fails closed by design, so callers handling untrusted records should pick an `into` name no attacker key can reach.

## 7. Supply chain and secrets: SAFE

No pyproject, csproj, lockfile, requirements or `.github` change; the only change to `ts/package.json` adds `dist-test/test/text.test.js` to the test script. No URLs added, no secret-shaped strings, no personal paths or e-mail addresses in any added line, commit author and committer are the repository's established identity. No `eval`, `new Function`, `exec`, `subprocess`, `child_process`, dynamic import or require, `fetch`, sockets, `Process.Start`, reflection loading, `unsafe` or `pickle` in the new source. `npm audit` and `pip-audit` were not run (no network); there is no new dependency for them to cover.

## 8. Other findings

**S4-SEC-4 (Low, C#):** `Text.AsRecords` treated `JsonObject` and `ExpandoObject` (they implement only the generic `IDictionary<,>`) as lists: `AsRecords(JsonNode.Parse("{\"text\":\"a\",\"b\":1}"))` returned `[{"text":"[text, a]"},{"text":"[b, 1]"}]` instead of `input.not_list`, bypassing the "shape checked in every mode" promise for the most common C# JSON object type. Fix: exclude generic `IDictionary<,>` and add a test.

**S4-SEC-5 (Low, C#):** `new Rec(r)` dropped the record's key comparer. With an `OrdinalIgnoreCase` record `{TEXT: "a\nb"}` each chunk carried the full parent text under `TEXT` plus the chunk under `text`: feeds S4-SEC-2 and differs from Python and TypeScript. Fix: `new Rec(r, r.Comparer)`.

Info: C# accepts any lazy `IEnumerable` (3M items in 883 ms; an infinite one would hang; caller-supplied, not data). TypeScript `slice` may keep the parent string alive through retained chunks, bounded by the input size.

## 9. Resolution (after the fix wave, head `520ab28`)

| Finding | Resolution |
|---|---|
| S4-SEC-1 (Medium) | Documented: README payload section, TypeScript and C# READMEs, CHANGELOG "Known limitations", ADR-005 (about 440 MB / 140 MB / 540 MB per million chunks in Python / TypeScript / C#, linear time, advice to cap untrusted input before `split`; a cap option "may be considered later", not promised) |
| S4-SEC-2 (Medium) | Documented in the same places: each chunk copies its parent, so a trace or `trim_to_budget` costs about chunks x size of the other fields; `select` the needed fields before `split` |
| S4-SEC-3 (Low) | Fixed: the Python paragraph cut is a hand-written one-pass scanner (same semantics as `(?:\r?\n){2,}`, proven equivalent by exhaustive comparison over all 29,524 strings up to length 9 over {a, newline, carriage return} and 200,000 random texts); a memory assertion fails on the old regex (556 MB and 285 MB against a 100 MB bound). Measured after: 0.0 MB peak on 4M newlines, and faster than the regex on every input tried |
| S4-SEC-4 (Low) | Fixed: `IDictionary<,>` excluded in `AsRecords`; tests for `ExpandoObject` and `JsonObject`, and a guard that `ArrayList` and `List<object?>` are still lists |
| S4-SEC-5 (Low) | Fixed: `new Rec(r, r.Comparer)`; a test fails with the old construction |
| S4-SEC-6 (Low, pre-existing) | Deferred to Slice 7 (a depth cap with a typed error in all three serializers); not introduced by this slice |

## 10. Not verified

Linux, macOS, Node 18 and 20, Python 3.9 and 3.10; `npm audit` and `pip-audit` (no network); peak resident memory per process (Python figures are from `tracemalloc`, which slows Python heavily, so the Python times above were measured without it; C# from `GC.GetTotalMemory`; TypeScript from heap delta); the 9-11 GB figures at 20 MB and the 10^11-character case are extrapolated, not run; C# stack depth on thread-pool threads; the full TypeScript and C# suites were not run by this reviewer (the controller ran them).
