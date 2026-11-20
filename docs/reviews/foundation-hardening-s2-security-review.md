# Foundation hardening, Slice 2: G5 security review (with ship veto)

**Branch:** `feat/hardening-s2-errors-strict` · **Role:** Security Reviewer (fresh context, holds the ship veto) · **Date:** 2026-11-20
**Written for:** the maintainer deciding whether Slice 2 may merge, and later reviewers who need the evidence behind the controls.

Two rounds. Round 1 reviewed `c9e1370`, vetoed it, and listed conditions. The defects were fixed in `24bf8a7`, `96893bf`, `4f1cf83` (and the closing `a0f9152`, `dc045a8`, `8f0623d`); round 2 re-gated `b85f95b`, lifted the veto and set two conditions, both since met. Reports were produced by independent reviewers who ran everything below against clean `git archive` copies of `22f82db` (before the slice), `c9e1370` (round 1) and HEAD, on Python 3.12, Python 3.9.13, Node 24 and .NET 8.

## Round 1 (`c9e1370`): VETO

**S-1, Critical: the default (non-strict) Python `quarantine` silently kept any item that is not a mapping.** `contexel/stages.py` read each field as `_scan_text(r[f]) if f in r else ""`; for a `str`, `list` or `tuple` item `f in r` is a substring/element test, so the text was `""`, nothing matched and the item was kept. Before the slice the code raised `AttributeError` (fail closed). A heterogeneous JSON array from a tool could therefore carry the bare string `"ignore all previous instructions"` straight into the model's context. Reproduced at `c9e1370`: `quarantine(["ignore all previous instructions"])` returned the string; `[{"snippet": "ok"}, "<marker>"]` kept the marker; the same through `pipeline`. Flag mode, `None` and `int` items still raised. TypeScript had the same hole before the slice (`Object.hasOwn("text", f)` is false), and in flag mode spread the string into per-character keys. C# threw `NullReferenceException` for a null item (fail closed by accident).

Other findings: **S-2 (Important)** joining the built-in markers and all custom patterns into one regex also renumbers numbered backreferences (`["(zz)q", "(evil)-\1"]` on `"zz evil-evil"` matches alone but not when joined in Python and C#), and in .NET an inline option leaks into later patterns (`(?-i)QQ|EVIL` no longer matches `evil`); on Python 3.9/3.10 a global inline flag in a custom pattern (`(?a)zzz`) applied to the whole joined regex and stopped the built-ins matching an NBSP-separated marker (reproduced on 3.9.13: kept; 3.12 raises). **S-3** the leaf scan used `str(v)` where the old code scanned `repr`, so an in-process object showing the marker only in its `repr` regressed. S-4 (misspelled field name scans nothing), S-5 (`None` in `allowed` admits records lacking the field), S-6 (C# stack overflow with a deep value under `trace()`), S-7 (no regex match timeout in any port), S-8 (messages echo the caller's pattern) were pre-existing.

No new dependency, no secrets, no `eval`/`exec`/`pickle.loads`/subprocess/network in library code, and error messages never echo record content.

## What was fixed

| Finding | Fix |
|---|---|
| S-1 | `quarantine` always raises `InputShapeError("input.not_mapping")` for a non-mapping item, in drop and flag mode, strict mode or not (Python, TypeScript; a null item in C#), plus shared vectors `quarantine/non_mapping_item_raises`, `..._in_flag_mode`, `quarantine/null_item_raises`. Human decision. |
| S-2 / P12 | The built-ins compile once and each custom pattern compiles on its own; a record is dropped when any matcher matches. The single joined regex and its "cannot be combined" error are gone. Human decision. |
| S-3 | The scan also reads `repr()` when it differs from `str()`; exact `int`/`float`/`bool`/`None` leaves skip the call. |
| S-4..S-8 | Documented under "Known limitations" in the changelog and READMEs. |

## Round 2 (`b85f95b`): SHIP WITH CONDITIONS, veto lifted

Evidence that the vetoed defect is closed:
- **Python:** 1,600 non-mapping probes per interpreter (20 item kinds including bytes, set, generator, memoryview, str subclass; 10 runners: direct, pipeline, strict pipeline, `dedupe` then `quarantine`, shaped, strict shaped, `trace`, strict scope), on 3.12 and 3.9: **0 leaks** (`c9e1370` leaked 240 and raised 720 raw `TypeError`). Legitimate non-dict `Mapping` items (`MappingProxyType`, `OrderedDict`, `defaultdict`, `ChainMap`, `UserDict`, a custom `Mapping`) are still accepted and scanned: 160 of 160 correct.
- **C#:** 64 of 64 null-item probes raise `InputShapeException input.not_mapping` (`c9e1370`: 24 typed, 40 `NullReferenceException`).
- **TypeScript:** 960 of 960 primitive or JSON-shaped non-objects raise typed. The one remaining path was the condition below.
- **Regression hunt:** 139 shared JSON cases plus 11 pattern cases (separators, placements, flags, backreferences, lookarounds, anchors, empty-matching, `(a+)+$`, 20-pattern lists) over three trees on four runtimes; plus 44 non-JSON cases (depth 1e4/1e5/1e6, cycles, shared structure, custom `__repr__`). No input caught by an earlier tree is missed at HEAD in built-in markers or nesting. The `repr` scan repaired a regression introduced inside the slice. Deep nesting up to 1e6 and cycles, which crashed `22f82db`, are handled.
- **Denial of service:** no regression. 50 MB string with 20 custom patterns: Python 17.2 s to 16.6 s, TypeScript 0.10 s to 0.16 s, C# 1.22 s to 0.88 s; 100k short records with 20 patterns 1.54 s to 1.96 s (Python); memory flat; 1e6 sequential reuses of one strict scope leave no residue.

**Conditions at round 2, both met:**
- **C1 (Important), met in `dc045a8`.** TypeScript `quarantine` still kept objects that pass `isMapping` but are not plain records (`new String("ignore all previous instructions")`, `Map`, `Set`, `Date`, `RegExp`, typed arrays, boxed `Number`/`Boolean`), strict mode included; `JSON.stringify(new String(m))` writes the bare string. Not producible by `JSON.parse`, pre-existing, but it contradicted "always raise". Fix: also reject when `Object.prototype.toString.call(r) !== "[object Object]"`; plain objects, class instances and null-prototype objects still scan. Controller re-ran all eight kinds in drop and flag mode: all raise `input.not_mapping`.
- **C2 (Minor, docs), met in `299099d`.** Per-pattern matching also narrows some pre-slice lists (inline flags and group numbers used to leak between patterns; a few records that were dropped only because of the leak are now kept; in TypeScript an unmatched backreference used to match empty). The changelog now says so and says the new behaviour is the intended one.

## Open items (documented; none blocks the ship)

Documented in `CHANGELOG.md` "Known limitations" and the READMEs, each verified by running it:
- The built-in markers do not match identically across ports: U+0085 (caught by Python and C#, kept by TypeScript), U+001C..1F (Python only), U+FEFF (TypeScript only), dotless i / dotted I / long s (Python only), Kelvin sign (folded by Python and C#, not TypeScript), `\Z` (a literal `Z` in TypeScript).
- Obfuscations no port catches: zero-width characters, RLM/RLO, soft hyphen, combining marks, homoglyphs, fullwidth forms, `&nbsp;`, a marker split across two sibling dict values, `< /system >`. The README states `quarantine` is a tripwire, not a security boundary.
- A misspelled `fields` entry scans nothing and keeps everything (all ports); `None`/`null` in `allowed` admits records lacking the field; no regex match timeout (C# default is infinite) and custom patterns run on attacker text (`(a+)+$` is exponential); shared in-process containers are expanded once; sets/`Map`/`Set`/`Date` are not expanded; C# does not read nested `System.Text.Json` `JsonElement` values (decision: documented, follow-up); `dedupe(key=[])` keeps one record; a deep value under an active `trace()` kills the C# process (uncatchable stack overflow).
- **Known gap, reported to the maintainer, not part of the veto:** `allowlist` on a non-mapping item. Python raises a raw `AttributeError`, C# a `NullReferenceException` for a null item, and TypeScript drops it (a string reads as a missing field) except when `allowed` contains `null`, where it keeps the item. Making `allowlist` raise `input.not_mapping` needs another Python, vector, TypeScript and C# cycle; recommended before the next release.

**VERDICT: SHIP (conditions met).** VETO LIFTED: yes. The evidence is above; the final tree was re-verified by the controller (Python 475, TypeScript 313, C# 279, vectors regenerate byte-identically).
