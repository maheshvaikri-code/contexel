> Filed 2026-11-20 from the Slice 3 review workspace for branch `feat/hardening-s3-audit-release` (head `c8bc7f3` after the fix wave; commit hashes in this document are those of the branch after one subject was reworded). Sanitised: no user name, home or temporary path, e-mail address or agent identifier. Gate G4 (whole-branch code review) followed by the single scoped re-review of the fix wave.

# Code Review (G4): Slice 3, audit truthfulness and release hygiene @ feat/hardening-s3-audit-release

**Reviewer role:** Code Reviewer (fresh context, adversarial) · **Date:** 2026-11-20
**Range:** base 0f09d36 (main) .. head 5f4e444, 13 commits, 35 files, +2106/-50
**Reviewed against:** docs/briefs/foundation-hardening.md AC28-AC34; design sections 7 and 8;
docs/adr/008-policy-fingerprint-and-trace-attribution.md; plan
docs/superpowers/plans/2026-11-20-foundation-hardening-s3-audit-release.md (S3-1..S3-8, Review Focus);
controller ledger progress.md.
**Method:** every probe ran on `git archive` copies in a scratch dir (old = 0f09d36, new = 5f4e444,
mix = old source + head tests). Nothing was built or written inside <repo>;
`git -C <repo> status --short` is empty at the end.

## Findings (severity-ranked)

No BLOCKER. No MAJOR.

| # | Sev | Location | Finding | Suggested fix | Before merge? |
|---|-----|----------|---------|---------------|---------------|
| 1 | MINOR | README.md:56-57; CHANGELOG.md:204-206 (Behavior change 9); contexel/pipeline.py:12-13 | Overclaims nested-pipeline coverage. README says the fingerprint "covers what a stage is bound to (lists, dicts, sets, **a nested pipeline**, ...)", but a pipeline bound as a kwarg still hashes as `run`. Probe: `stage(apply, inner=A)` vs `stage(apply, inner=B)` collide (`4a4845ed1b42c49f` both) and give different output (`[{'a':1}]` vs `[{'b':2}]`). This case is in Known limitations, so the README contradicts the CHANGELOG. CHANGELOG item 9 says "Python and TypeScript: **any** pipeline used as a stage", but `stage(inner)` (Python) and `stage(inner, {})` (TypeScript) still collide (old and new both `add40106a64ca3b0` / `37fa38c7754485b8`), and no Known limitation mentions that. | Reword README:57 ("a nested pipeline used directly as a stage"). Add "a pipeline wrapped by stage() hashes by its name (run)" to Known limitations, or (code, a permitted AC29 shape) have stage() keep a pipeline's `__contexel_desc__`. | YES (docs; this slice is about the audit not saying false things) |
| 2 | MINOR | site/stages.html:197-201 | "stage() keeps a private copy of the plain lists, dicts and sets bound to it, so the fingerprint **cannot go stale**" is unconditional. It is false for a container subclass and a custom object (pipeline.py:25-28 says so), for the elements of a TypeScript Set, and for C# (no copy at all). The ledger fixed the same overclaim in the pipeline.py docstring ("For the exact containers listed, ...") but not on the site. | Qualify it the way pipeline.py:20 does. | YES (docs) |
| 3 | MINOR | CHANGELOG.md:57; .github/workflows/ci.yml:38; tools/check_versions.py:5 | "It runs on every push and pull request" is not true. ci.yml `on:` is `push: branches: [main]` plus `pull_request`, so a push to any other branch without a PR does not run `hygiene`. AC33 says "on every push, not only at tag time". The intent (before the tag) is met; the literal wording is not. | Reword to "every push to main and every pull request". Or, if the human wants literal AC33, widen the push trigger (a CI-policy change, so it is the human's call). | YES (wording); trigger change = human decision |
| 4 | MINOR (needs human acknowledgement, not a code change) | contexel/trace.py:191-197 (and ts/src/trace.ts, csharp/Contexel/Trace.cs) | The AC28 formula over-reports in one case. A black-box stage that strips an id from a survivor AND drops an id-less record now gets that survivor reported in dropped_ids. Measured: 1,332 of my custom-stage cases, all in exactly that class (0 outside it). Built-in stages: 0 regressions across 12 configurations x 408 inputs. This is documented as deliberate (CHANGELOG item 8, ADR-008 "Per-language scope") and the spec fixes the formula. The ledger asks that the human see it. | None in code. The human acknowledges the trade-off at merge. | YES (acknowledgement) |
| 5 | MINOR (deferred T5) | tests/test_audit_truth.py:287-290 | A broad `except Exception` around `tiktoken.get_encoding` turns any tiktoken failure (including a real bug) into a skip. Here it ran (PASSED, not skipped). | Narrow it to the fetch errors, or fail in the release gate where `accurate` is installed. | follow-up |
| 6 | MINOR (deferred T3) | ts/test/runner.ts:150-155 | A trace_dropped_ids case without id_field would replay with `idField: undefined`, so every stage reports []. A case that expects [] would then pass vacuously. Latent: all 7 committed cases carry `id_field: "id"` (checked). | Assert that id_field is a string. | follow-up |
| 7 | MINOR (deferred T9) | pyproject.toml:33 | The `lint` extra floats (`ruff>=0.15,<1`, `mypy>=2.3,<3`), so a new ruff rule or mypy error can turn `hygiene` red without a code change. pip-audit on these is still not run (needs the network). | Pin exact versions or add a constraints file. pip-audit is a merge precondition (human). | pip-audit: YES (human); pins: follow-up |
| 8 | NIT | docs/adr/008-...md:42; CHANGELOG.md:334 | "identical in all three" holds only up to id-key equality. Cross-language replay: TypeScript differs from Python in 17 of 1,500 cases, and every one is 0 vs false (Python and C# merge them into one key). The Known limitation names only 1 and true. | Add "(and 0 and false)" and "up to id-key equality". | optional |
| 9 | NIT | ts/src/pipeline.ts:78-81 (shipped in dist/pipeline.d.ts) | The stage() doc comment that IDE users see says "any array, plain object or Set". The copy is by exact type and a Set's elements stay live. The qualification is only in the file header. | Add "exact" and "(a Set's elements are not copied)". | optional |
| 10 | NIT | CHANGELOG.md:61 | "never shipped": the `lint` extra is declared in the published wheel metadata (Provides-Extra: lint). Only the tools are not shipped. | "never a runtime dependency". | optional |
| 11 | NIT | csharp/Contexel/Trace.cs:109,120 | C# trace now counts a null record as id-less instead of throwing NullReferenceException. That follows ruling S3-5 and is tested (TraceCountsANullItemAsIdlessInsteadOfFailing), but Behavior change 8 does not list it. Impact is small: Traced is internal and the built-ins still throw on null (probe: Stages.Dedupe with a null item throws NRE in both old and new). | One clause in item 8. | optional |
| 12 | NIT (deferred T8) | tests/test_check_versions.py:84 | The assertion that "7" is in the output would also pass for "17" or a version containing 7. | Assert the full "all 7 version locations say 1.2.3" line. | optional |
| 13 | NIT (deferred T1) | csharp/Contexel.Tests/FingerprintTests.cs (Opaque.ToString) | Dead override. | Remove. | optional |

### Triage of the ledger's deferred items
- **Must fix before merge:** findings 1, 2 and 3 (docs and wording only), plus two human items: the finding 4 acknowledgement and pip-audit on ruff 0.15.15 and mypy 2.3.0 with their dependency closure (finding 7, needs the network).
- **Already resolved on the branch (verified):**
  - The T2 over-report is documented (CHANGELOG 8, ADR-008).
  - The trace() docstring is updated (trace.py:121-129).
  - The T4 docstring wording is fixed (pipeline.py:20-28 and 65-70).
  - The T4 out-parameter and shared-object notes and the generator fix are in CHANGELOG 10.
  - The T4 dict-key repr and comma-join notes are in Known limitations.
  - The T6 Map/Date/RegExp, cyclic-Set RangeError, getters and symbol keys are documented.
  - T7 Pipeline.cs:22-32 is reworded and the C# collisions are documented.
  - The T8 csproj first Version element is documented.
  - The 2fbc6fe subject is reworded: all 13 subjects are 72 characters or fewer, there is no Co-Authored-By trailer, and there are no private paths or e-mail addresses in the diff (grep came back empty).
- **Can follow up after merge:**
  - T1: nameless-stage collision test and C# bare-delegate golden. My differentials cover these shapes: TypeScript arrow, C# lambda Fn, both unchanged.
  - T3: partial-absorption shared vector. My cross-language replay covers partial absorption: C# 0 differences in 1,241 cases.
  - T5 (finding 5), T3 runner (finding 6), T9 pins, wheel-leak check, sdist include list, hatchling pin.
  - T8: BOM handling and top-level `permissions:` (G5 Security).

## Scope check
The diff matches the plan slice. There are no new public names in any language (evidence 3). There is no version bump. The two accepted plan deviations (ts/src/pipeline.ts snapshot; tools/check_versions.py UnicodeDecodeError) are judged as code and are correct: the __proto__ own key is kept, exact-prototype copy is probed in the evidence, and exit 2 names the file. The shaped.py `cast` is type-only, an identity at runtime. Nothing is extra and nothing is missing against AC28-AC33. AC34 holds apart from the doc overclaims above.

## Suites (re-run by me on the head copy)
```
Python: 531 passed in 3.25s
TypeScript (npm test): tests 351, pass 351, fail 0, skipped 0
C#: 0 Warning(s) 0 Error(s); Passed! - Failed: 0, Passed: 312, Skipped: 0, Total: 312
ruff check contexel -> All checks passed!
mypy -> Success: no issues found in 8 source files
python tools/check_versions.py -> check_versions: all 7 version locations say 0.1.17 (exit=0)
parity/generate_vectors.py (default seed and PYTHONHASHSEED=1) -> IDENTICAL modulo CRLF to the committed file
slice tests under PYTHONHASHSEED=1 and =99 -> 61 passed (both)
tiktoken tests: 3 PASSED (the real-package test ran; the cl100k cache is present locally, no network used)
```

## Evidence 1: old vs new differential for trace attribution (Python)
Interpreter check: PYTHONPATH=old copy gives `...\g4\old\contexel\__init__.py`, and PYTHONPATH=new copy gives `...\g4\new\contexel\__init__.py`. The stale installed 0.1.17 does not shadow either copy.

**Driver** (the same script run against both copies). The corpus is 8 handmade inputs plus 400 seeded random inputs (0-9 records each). The id pool is a, b, c, 0, "", False, None, 1, ["x"], ["x"], a, True, 1.0, with id-less dicts, None records and string records mixed in.

The inputs go through the built-in stages and through a custom stage:
- **Built-in stages:** select (with and without id), dedupe (title, id, whole record), allowlist, quarantine, rank, rescore, truncate_field, trim_to_budget at 0 and 20.
- **Custom @traced stage:** a per-record keep/drop/strip plan, add of 0/1/2 id-less records, and dup of record 0. The plans are nothing_dropped, all_dropped, strip_all, drop_idless, strip_and_drop_idless and 6 random mixes.

Ground truth comes from the plan for the custom stage and from multiset equality matching for the non-transforming built-ins. The comparison normalizes the 1/True/1.0 and 0/False key-equality class.
```
total cases: 31824   differing old vs new: 6983   error behaviour differs: 0
cases where old dropped_ids is not a suffix of new: 0      (new only ever ADDS reports)
(builtin, FIXED) 298                                       (all built-in differences are fixes; 0 regressions)
(custom, FIXED) 2294
(custom, REGRESSED, strip_id & drop_idless) 1332           (finding 4: documented over-report; 0 REGRESSED outside this class)
(custom, both-wrong, adds_idless) 2099                     (documented bound: a stage that ADDS id-less records can hide up to that many)
(custom, both-wrong, strip & drop_idless) 634              (same class as finding 4)
(custom, both-wrong, OTHER) 326                            (strip + drop: the count is right, but which id gets absorbed is ambiguous ("first lost in input order", documented), or the 0==False key-equality collision, pre-existing)
```
Per built-in configuration, old vs new:
```
allowlist_src   both-right 190, FIXED 53, both-wrong-same 3, both-wrong 1 (1 vs True key-equality only)
dedupe_id       both-right 201, FIXED 44;  dedupe_title FIXED 3;  dedupe_whole FIXED 2
quarantine_drop both-right 164, FIXED 76;  trim20 both-right 295, FIXED 113
select_title / select_id_title / rank / rescore / truncate / trim0: identical (all both-right)
```
Sample FIXED: dup|dedupe_id, input [{id:a},{id:a},{title:x}]: old [], new ['a'], truth ['a'].
Sample REGRESSED (intended, documented): nondict|planned:strip_and_drop_idless: old [], new ['a'], truth [].

**Classification.** Every difference is either an AC28 fix or one of the two documented black-box approximations. There is no unintended difference.

**Cross-language replay of the same attribution** (1,500 seeded cases of the custom stage; the Python head output is the expectation):
```
TypeScript: cases=1500 ts_vs_py_differences=17   (all 17 are 0 vs false key-equality: finding 8)
TypeScript without boolean ids: cases=1500 ts_vs_py_differences=0
C# (scratch xunit test in the temp copy): compared=1241 skipped_nondict=259 cs_vs_py_differences=0
```

## Evidence 2: fingerprint differential
**Python:** 63 pipelines that bind none of {set, frozenset, nested pipeline, tiktoken}. Shapes not pinned by tests/test_fingerprint_golden.py include:
- -0.0, NaN, inf, 2**70, bytes, astral unicode
- a dict with keys 1/"1"/None/2.5/True/(1,2)
- partial, bound method, builtin len, a class, a callable instance, a custom object
- list, dict and tuple subclasses, namedtuple, OrderedDict, defaultdict, deque, Enum, Decimal, Fraction, range, dict_keys, complex, MappingProxyType
- stage-of-stage, partial and callable-instance bare stages, a traced bare stage, a lambda stage, strict, the empty pipeline
- a pipeline bound as a kwarg, and every built-in with typical args

```
md5 of the fingerprint JSON: old seeds 0/1/2 and new seeds 0/1/2 all 52911593a5fa3fd979dcce0aacda7894
OLD==NEW (63 fingerprints byte-identical, hash-seed independent)
```
**TypeScript:** 76 fingerprints, built from 37 shapes in two forms each, plus 6 more:
- -0, NaN, Infinity, undefined, a null-prototype object, a getter, a symbol key
- a class and its instance, Date, Map, RegExp, an Array subclass, sparse arrays, an array with an extra property, Uint8Array
- a JSON-parsed __proto__ key, numeric keys
- bare and arrow stages, strict, empty, a pipeline as a param, built-ins

Result: TS OLD==NEW.

**C#** (a scratch test in both temp copies): 35 fingerprints:
- null, int, long, double, -0.0, NaN, decimal, float
- list, array, char[], nested containers, Dictionary, SortedDictionary, ReadOnlyDictionary, ReadOnlyCollection
- a delegate at top level, in a list and in a dict
- a KVP list, a lazy LINQ sequence, an object, an enum, a ValueTuple
- no params vs empty params, a non-pipeline method group, a lambda Fn, empty, strict

Result: C# OLD==NEW.

**The intended changes happen** (Python, new vs old):
```
old: set {a} vs {b} COLLIDE; frozenset COLLIDE; nested A vs B COLLIDE; traced(A) COLLIDE
new: set DIFFER; frozenset DIFFER (and == the set); nested direct DIFFER; traced(A) DIFFER
new still COLLIDE: stage(A) vs stage(B); functools.partial(A); lambda r: A(r); kwarg-bound pipeline (finding 1)
TS new: Set DIFFER, nested direct DIFFER; stage(A,{}) and arrow wrapper still COLLIDE
```
**AC30 behaviour** (old -> new):
```
list / set / tuple(list) / dict(list) mutation after build: behaviour_same False -> True (fp unchanged in both)
list subclass (documented live): False -> False
pipeline stage list mutation: False -> True; pipeline from a generator: ran nothing -> runs
TS: allowed.push after build -> old keeps a and b, new keeps a only; stage-array copy: old [] -> new [{"s":"a"}]
```
**AC31** (real tiktoken 0.8.0, cached cl100k):
```
old: name <lambda>; count/truncate/trim/scoped count of "<|endoftext|>" or "<|fim_prefix|>" -> RAISES ValueError
new: name tiktoken:cl100k_base; count 8; count of plain text 2 (unchanged); truncate returns a str; trim keeps 3; scoped count 13
```
The committed goldens were not edited after Task 1: git diff fa6b2c7..HEAD on the three golden files shows only added lines and no changed 16-hex value.

## Evidence 3: nothing public added or removed
- **Python** (every module's non-underscore names plus signatures, old vs new): `__all__` is identical (19 names). The only diffs are `shaped.cast`, a typing.cast import (not in `__all__`, not public API), and the dataclasses `field` default repr, which differs only by memory address.
- **TypeScript:** ts/src/index.ts is unchanged. The built declarations differ only in pipeline.d.ts: the stage() doc comment, and the first parameter of pipeline renamed stages to stageList. The rename is positional and non-breaking.
- **C#:** git diff over csharp/Contexel shows no added or removed line containing public, internal, protected or export. Settle and IsSet are private.

## Evidence 4: cross-language semantic drift
- **trace.py / trace.ts / Trace.cs:** the same algorithm: remaining multiset, unmatched in input order, lost = max(0, out_idless - in_idless), dropped = unmatched[lost:]. They differ in two places:
  - Id keys: TypeScript keeps 1/true and 0/false apart. Measured: 17 of 1,500 (finding 8).
  - Null handling: C# counts null as id-less (S3-5). Python counts None and any non-dict as id-less. TypeScript counts null and non-objects as id-less. All three match in the replay.
  - The guard for an empty id field is the same everywhere: Python `if tr.id_field`, TypeScript `if (fid)`, C# IsNullOrEmpty.
- **pipeline.py / pipeline.ts / Pipeline.cs:**
  - **Copying:** Python copies exact list, tuple, dict and set. TypeScript copies an exact Array, a plain or null-prototype object, and a Set shell. C# copies nothing (documented; it cannot without new API).
  - **Nested pipelines:** Python detects one through `__contexel_desc__` on any callable (it survives functools.wraps, so traced(A) is covered). TypeScript detects only a pipeline's own run function. C# detects Fn.Target is Pipeline, which covers any delegate bound to a Pipeline (documented). None of the three covers stage(A) or a lambda wrapper (finding 1).
  - **Sets:** Python and C# sort the element reprs (C# Ordinal). TypeScript uses the default sort (UTF-16 order). That is deterministic, and fingerprints are language-local (ADR-002), so it is not a defect.
  - **C# Settle** replaces only sets. Every other shape reaches PythonJson with the same structure, so the 35-shape C# differential is unchanged. Non-string dictionary keys threw InvalidCastException before and after.
  - **Collision probes** (descriptor injection) all come out distinct:
    - Python: ("pipeline",(fp,)) vs a stage named pipeline with params.
    - TypeScript: pipeline(<fp>) vs pipeline("<json>").
    - C#: pipeline=<fp> vs a JSON-quoted param.

## Evidence 5: docs honesty (each claim checked against code or a probe)
- CHANGELOG 8: accurate, including the bound and the over-report. The over-report is measured (finding 4). "All three languages" is confirmed by the replay.
- CHANGELOG 9: accurate for sets (all three), tiktoken naming and C# inner.Run. "A pipeline that binds none of these keeps its exact fingerprint" is confirmed by evidence 2. "Any pipeline used as a stage" is an overclaim (finding 1).
- CHANGELOG 10: accurate (AC30 probes, generator fix, exact-type copy, __proto__ own key, getters and symbols).
- CHANGELOG 11: accurate (the count for plain text is unchanged: 2 vs 2).
- Known limitations:
  - The kwarg-bound pipeline hashing as run is confirmed.
  - The C# set-vs-string collision is confirmed by reading the code: Settle renders the set to a string.
  - Map/Date/RegExp rendering as {} is consistent with my TypeScript shapes (unchanged old/new).
  - The stage(A) case is missing (finding 1).
- "77 cases in all": confirmed (77 cases, 7 of kind trace_dropped_ids).
- ADR-008: consistent with the code, apart from finding 8.
- README: finding 1. site/stages.html: finding 2. site/getting-started.html: accurate. ts/README and csharp/README: accurate (NIT 9 is about the d.ts).
- "on every push": finding 3.

## Evidence 6: test quality
**Head tests run against the base code** (mix copy), to separate regression tests from guards.

Python (tests/test_audit_truth.py, 21 tests): 13 FAIL on the old code, so they are real regression tests:
- reports_a_drop_when_another_survivor_never_had_the_id
- dropped_ids_in_input_order
- both tiktoken tests
- pipeline_copies_its_list
- nested_bound_containers_copied
- set ignores insertion order and set type
- differs for tiktoken, for set contents, for nested pipelines
- bound_container_mutation
- same_private_copy_on_every_call
- set_nested_in_list_or_dict

8 PASS on the old code and are guards:
- select_stripping_ids, mixed_input_select, ambiguity_is_bounded, adds_idless_bound
- set_hash_seed. This one is vacuous on the old code, because the old code hashed every set as "set". On the head it is meaningful: it would catch an unsorted rendering.
- set_not_list_or_dict, nested_pipeline_still_runs, callable/custom/subclass_not_copied

The 15 golden parametrizations all PASS on the old code, by design.

TypeScript (audit + fingerprint, 21 tests): 12 FAIL on the old code, including both __proto__ and exact-Array/Set tests. 9 are guards or goldens.

Vectors: 3 of the 7 trace_dropped_ids cases fail on the old TypeScript (drop_beside_a_record_without_the_id, each_stage_is_attributed_on_its_own, dropped_ids_keep_input_order). falsy, duplicate, list_ids and select_strip are guards.

C#: 10 FAIL on the old code (7 tests plus the same 3 vectors). FingerprintDiffersForSetContents and ASetNestedInAListOrADictionaryIsCoveredToo pass on the old C# (old C# already rendered sets as ordered lists), so they are guards there.

**Other checks:**
- Every test function in the 8 new or changed test files contains at least one assertion (scripted scan).
- Nondeterminism: the hash-seed test spawns subprocesses with sys.path.insert(0, ROOT). Slice tests pass under PYTHONHASHSEED 1 and 99. C# set sorting is Ordinal (culture-free). check_versions tests cover CRLF.
- Silent skips: test_the_wheel_ships_py_typed uses importorskip on hatchling. The CI hygiene job checks the wheel independently. The tiktoken real test skips on any exception (finding 5). Neither skipped here.

## Verdict
**G4: PASS WITH CONDITIONS.** 0 BLOCKER, 0 MAJOR, 7 MINOR, 6 NIT.

Must be fixed or settled before merge:
1. Finding 1: reword README.md:57 and CHANGELOG item 9 ("any pipeline used as a stage"), and add stage(inner) / wrapper to Known limitations (or cover it in code).
2. Finding 2: qualify "cannot go stale" in site/stages.html:200-201.
3. Finding 3: reword "every push" (CHANGELOG.md:57, ci.yml:38, check_versions.py:5), or the human widens the push trigger.
4. Finding 4: the human acknowledges the documented over-report trade-off of the AC28 formula.
5. Merge precondition (ledger, finding 7): pip-audit on the lint extra (ruff 0.15.15, mypy 2.3.0 and closure). It needs the network, so it is the human's step.

Findings 5-7 and all NITs can land as follow-ups.


---

# Scoped re-review of the fix wave (head c8bc7f3)

# Scoped re-review: fix wave 5f4e444..c8bc7f3 (4 commits)

All probes ran on `git archive c8bc7f3` copies in a scratch directory. <repo> was not built or written, except for this report (git-excluded).

## Per item
- A1 ADDRESSED.
  - Hand derivation from AC28: the input is [{t:x},{a,x},{b,x},{c,y}] and the output is [{c,y}]. unidentified_out=0 and unidentified_in=1, so lost=max(0,-1)=0. unmatched=[a,b], so dropped=[a,b], which matches the vector's expect [["a","b"]]. Without the clamp, lost=-1 and unmatched[-1:]=[b].
  - Python mutant (no max): 3 failed, 127 passed. The failures are test_a_dropped_idless_record_never_absorbs_an_identified_drop, the parity canon case and the case-table test.
  - TS mutant (no Math.max), rebuilt in the copy: tests 354, pass 353, fail 1. The failing test is "case trace_dropped_ids/a_dropped_idless_...", actual [['b']], expected [['a','b']].
  - C# at head: dotnet test --filter CaseTests|ASetInADictionary... gave 81 passed, 0 failed (all 79 cases replayed).
- A2 ADDRESSED. Mutant (frozenset converted to a set in _snapshot): 1 failed (test_a_bound_frozenset_is_passed_as_the_same_object), 129 passed. Not vacuous.
- A3 ADDRESSED.
  - Python mutant (id_key returns str(value)): 3 failed (the new test and 2 parity tests).
  - The test puts the dropped "1" before the surviving 1. That order is what keeps the test from being vacuous: with the survivor first, the mutant would pass.
  - TS and C# by reading: TS idKey returns a primitive unchanged into a Map (SameValueZero, so 1 and "1" are distinct). C# IdKey gives "num:1" for 1 and "str:1" for "1". The vector expect is ["1"], and C# and TS replay it green.
- A4 ADDRESSED. Mutant (`copy[(string)e.Key] = e.Value;`, run with dotnet test --filter on the new test): FAIL, expected 963d23a0f1e77523, actual a96af6b821c0554a. HashSet keeps insertion order, so the test is not vacuous.
- A5 ADDRESSED. The test asserts `out == "check_versions: all 7 version locations say 1.2.3" + NL`; the fixture version is 1.2.3 and NL is defined in the test. A mutant of the success line fails it.
- A6 N/A (correctly not done).
  - Tokens.cs WriteJson's `default:` branch writes `Convert.ToString(value, InvariantCulture)`, and Pipeline.StableRepr sends non-delegates to Tokens.PythonJson(Settle(v)).
  - So Opaque.ToString()=>"Opaque" produces the golden "opaque_object" 704c1b356f69617b. Without it, the default ToString is the nested type's full name, which changes the hash.
  - The G4 #13 premise was wrong. A one-line comment on the override ("load-bearing: the library renders an opaque value with Convert.ToString") would prevent the same mistake again (optional).
- A7 ADDRESSED.
  - All 9 committed trace_dropped_ids cases carry id_field "id" (79 cases, _meta 79).
  - The guard was removed in a copy, with a cast kept so the copy compiles. Result: tests 354, fail 1, "a trace_dropped_ids case without a non-empty string id_field is rejected", "Missing expected exception".
- B1 ADDRESSED.
  - With 100,000-deep `[...]` and `{"a":...}`, the script exits 2 with "check_versions: ts/package.json (npm package): the JSON is nested too deeply to read" and no traceback.
  - The pre-fix script (git show 5f4e444) exits 1 with a RecursionError traceback. The new test fails on the pre-fix script (assert 1 == 2) and 22 others pass.
  - Other hostile JSON gives no other escape:
    - a 100k-digit integer: ValueError, exit 2;
    - 1e999: "not a version string", exit 2;
    - trailing data and a BOM: JSONDecodeError, exit 2;
    - a lone surrogate version `\ud800`: exit 1 (disagree); stderr's backslashreplace prints `\ud800`, piped too;
    - a lone surrogate key: exit 0.
  - On Python 3.9 there is no integer-digit limit, so a huge integer parses instead of raising: slow for very large files, but nothing escapes.
- C1 ADDRESSED.
  - The top-level `permissions: contents: read` sits right after `on:`, in the same style as release.yml. PyYAML parses it: permissions {'contents':'read'}; jobs test, hygiene, ts-parity, cs-parity; no job-level permissions.
  - The only actions used are checkout, setup-python, setup-node (npm cache, which uses the runtime cache token, not GITHUB_TOKEN scopes) and setup-dotnet. There is no upload-artifact and no write step, and no action SHA changed.
  - Apart from the permissions block, only the hygiene comment changed (wording). The file stays CRLF throughout.
- D1 ADDRESSED. Python probe: inner fingerprints differ; used directly they differ; stage(i1) and stage(i2) have the same fingerprint (desc ('run',())); as a kwarg they have the same fingerprint. The TS probe gives the same for stage(inner,{}) and for a param. README, CHANGELOG BC9, the Known-limitations bullet and the pipeline.py docstring all match.
- D2 ADDRESSED. The site text is qualified, and `python tools/site_check.py` gives "checked 6 pages under site/ -> OK". "cannot go stale" remains only in qualified form (pipeline.py:22, site/stages.html:200) and in historical plan or ledger records.
- D3 ADDRESSED. CHANGELOG:57, the ci.yml comment and the check_versions docstring all match `on: push: branches [main]; pull_request`.
- D4 ADDRESSED. ADR-008 and BC8 say "up to id-key equality", and 0/false was added to the 1/true bullet.
- D5 ADDRESSED. The comment says "exact array, plain object or Set (a Set's elements are not copied)".
- D6 ADDRESSED. The text now says "never a runtime dependency".
- D7 ADDRESSED. C# Trace.cs now has `r is not null && r.TryGetValue` in both loops (main had a bare r.TryGetValue). The "built-in stages still throw" half was read, not probed.
- D8 ADDRESSED.
  - TS probe: a Uint8Array, a Buffer, a class instance and a node:vm other-realm object are each passed as the same object. An exact array, a plain object and a Set are copied.
  - The 0.26 s / 1.0 s figures are phrased as a measurement ("took about"), and they match the security report (256.8 / 1034.9 ms). They are not stated as a guarantee.
- D9 ADDRESSED. The bullet is present.
- Group D purity: `git show c8bc7f3 -- '*.py' '*.ts' '*.cs'` changes only docstring lines (pipeline.py module docstring, check_versions.py docstring) and comment lines (ts/src/pipeline.ts). No code line changed.
- CHANGELOG "79 cases": parity/vectors.json has 79 cases and _meta.case_count is 79.

New breakage in the fix diff: none found.
- Each file keeps uniform line endings, with no whole-file churn.
- Privacy grep of the diff and of the 4 commit messages (user name, C:/Users, AppData, e-mail): no matches. There are no Co-Authored-By or Signed-off-by trailers.
- Commit subjects are 62, 62, 55 and 58 characters long, all 72 or less.

## Residual findings
- NIT (docs consistency): the Python bullet of ADR-008 "Per-language scope" still says "A nested pipeline carries ("pipeline", (fp,))", without the "used directly as a stage" qualifier that the TS bullet and every other surface now carry.
- INFO (ADR text, pre-existing): ADR-008's Decision states `lost = unidentified_out - unidentified_in` without the max(0, ...) clamp that A1 now pins.
- INFO (cosmetic): CHANGELOG BC8 has a reflow artefact ("null item). An" ends a line before "audit recorded ..."). It renders fine.
- INFO (optional, A6): a comment marking Opaque.ToString as load-bearing.

Verdict: all findings addressed (A6 correctly declined on a false premise). Open findings: 1 NIT and 3 INFO, none blocking.
