> Filed 2026-11-20 from the Slice 3 review workspace for branch `feat/hardening-s3-audit-release` (head `c8bc7f3` after the fix wave; commit hashes in this document are those of the branch after one subject was reworded). Sanitised: no user name, home or temporary path, e-mail address or agent identifier. Gate G5 Security (holds the ship veto): SIGN-OFF WITH CONDITIONS.

# G5 Security Review: Foundation hardening, Slice 3 (audit truthfulness and release hygiene)

- Branch: feat/hardening-s3-audit-release, base 0f09d36 (= main), head 5f4e444 (13 commits)
- Reviewer: Security Reviewer (fresh context, holds the ship veto). Read-only: every probe ran in a `git archive` copy under <tmp>; `git status --short` on the repository was empty at start and at finish.
- Loads: roles/security-reviewer.md, skills/security.md, standards/dependency-policy.md. Inputs: brief ACs 28-34, ADR-008, the S3 plan (Gates, Security focus), the whole-branch diff.

## Verdict

**G5 SECURITY: SIGN-OFF WITH CONDITIONS**

No CRITICAL or HIGH finding. Nothing this branch introduces lets the audit under-report through a built-in stage, makes attribution super-linear, adds a runtime dependency or network/file/subprocess use, or adds CI permissions, secrets, third-party actions or script injection. The slice strictly improves audit integrity (AC28, AC29, AC30 for plain containers) over main.

Conditions (merge preconditions for the human):
1. **C1 (MERGE PRECONDITION): run `pip-audit` on the `.[lint]` closure (ruff, mypy 2.x, typing_extensions, mypy_extensions, pathspec, librt, ast-serialize) and on `.[dev]`; attach the output and disposition each finding.** I could not run it: it needs the network, which this review is not allowed to use.
2. **C2: the first CI run of the new `hygiene` job (and the release-gate version step) must be green on the human's push.** It has never run.
3. **C3 (strongly recommended before merge, not blocking): add a top-level `permissions: contents: read` to `.github/workflows/ci.yml`** (finding M-1). If the human defers it, record the deferral.

Severity counts: CRITICAL 0 / HIGH 0 / MEDIUM 1 / LOW 5 / INFO 9

## Threat model (summary)

- **Assets:** (1) the audit trail (`trace(...).audit()`: `dropped_ids`, `policies`): "did relevant context reach the model, and under which policy?"; (2) the policy fingerprint as an identifier of behavior; (3) the release pipeline (seven version copies, PyPI/npm/NuGet publish); (4) the public repository's hygiene.
- **Entry points / attacker:** (a) record CONTENT reaching stages: retrieved documents, tool output, id values (JSON-shaped: str/int/float/bool/null/list/dict), which an outside attacker can influence; (b) stage parameters, which come from the developer and sometimes from config/JSON; (c) a pull request (possibly from a fork) that edits code, workflows, pyproject or tools; (d) PyPI packages that CI resolves at run time.
- **Worst plausible abuse:** an attacker-controlled record that hides a drop of a legitimate record from the audit, or makes the audit blow up (DoS/abort); two behaviorally different policies sharing a fingerprint; CI running PyPI code with a write-scoped token; a release with mismatched versions; personal data in the public tree.
- **Out of the trust boundary (by design):** stage CODE. A custom stage is a black box and can do anything, including claiming any `__contexel_desc__`; the fingerprint is an identifier, not an integrity control against malicious stage code.

## Findings

### MEDIUM

**M-1. `ci.yml` has no `permissions:` block. The new `hygiene` job runs PyPI-resolved code on every push to main with the repository-default token, persisted on disk by checkout.** (pre-existing posture, widened by this slice)
- Evidence: `grep -rn permissions .github/workflows/` lists only pages.yml and release.yml (release.yml has a top-level `contents: read`). ci.yml has none, in any job (test, hygiene, ts-parity, cs-parity). `actions/checkout` is used without `persist-credentials: false` (default true: the token is written to `.git/config` for the later steps).
- Exposure: on `pull_request` from a fork, GitHub gives a read-only token and no secrets, so a malicious PR that edits the workflow, `pyproject.toml` (build backend, extras) or `tools/check_versions.py` runs code with read-only scope, which is the exposure the repository already had through `pip install -e ".[dev]"` (pytest + hatchling) in the `test` job. On `push` to main the token scope is the repository/organisation default, which cannot be seen from the tree: it is either read-only ("restricted") or read/write ("permissive"). The hygiene job adds ruff, mypy 2.x and mypy's closure (typing_extensions, mypy_extensions, pathspec, librt (native), ast-serialize), resolved within `ruff>=0.15,<1`, `mypy>=2.3,<3` with no lockfile or hashes, and its build backend (hatchling, build isolation) for `pip install -e` and `pip wheel`, to the code that runs next to that token. Nothing is cached in the hygiene job (setup-python without `cache:`), so there is no cache-poisoning path from it.
- Fix: top-level `permissions: contents: read` in ci.yml (no job needs more), and optionally `persist-credentials: false` on the checkouts. Two lines; it closes the push-to-main case whatever the repository default is.

### LOW

**L-1. Id-key collisions name the WRONG record as dropped (count correct, identity wrong).** Pre-existing (`id_key` is unchanged), not covered by the shared vectors, and the three languages disagree.
- Python keys a hashable id by its value (so `1`, `1.0` and `True` are one key) and an unhashable id by `repr` (so a list id `[1, 2]` and the string id `"[1, 2]"` are one key). TypeScript keys objects by `pythonJson` (so a list and its JSON text collide) but keeps `1` and `true` apart. C# type-tags its keys (`str:`, `json:`, `num:`) so a list and a string never collide, but bool and number collide as in Python.
- Repro (probes P1/P4/P8, real output): input `[{id:1,k:drop},{id:True,k:keep}]` gives Python `[True]`, C# `[Boolean:True]`, TS `[1]`. Input `[{id:[1,2],k:drop},{id:"[1, 2]",k:keep}]` gives Python `['[1, 2]']`, TS `["[1, 2]"]`, C# `[List...]`, so only C# names the record that was actually dropped.
- Impact: an attacker who controls the id value of one record can make the audit name its own SURVIVING record as dropped, and so hide WHICH legitimate record was dropped. The count of `dropped_ids` stays right. The 1/true divergence is documented (CHANGELOG Known limitations); the misattribution itself and the list/string collision are not.
- Fix: type-tagged keys in Python and TypeScript (the C# scheme, with Python's documented `1 == 1.0` decision made explicit for bool), plus vector cases; or document it as a limit. Not slice-introduced: track it for a later slice.

**L-2. CPython int hash flooding makes the attribution loop (and `dedupe`) quadratic with attacker-chosen integer ids.** Pre-existing (the same `dict` on main), not slice-introduced.
- Repro (probe P3): ids `i * (2**61 - 1)` all hash to 0. Traced identity stage: n=4000 took 256.8 ms and n=8000 took 1034.9 ms (x4 per doubling), against 3.0 / 5.6 ms for benign ids. Main measured the same (255.3 / 1062.7 ms). Untraced `dedupe(key="id")` on the same ids: 497 / 2095 ms. Extrapolated, 1e5 such ids would take about 2.5-3 minutes per traced stage.
- The slice's own loop is linear: `unmatched` is one list sliced once. With adversarial duplicates and id-less records, Python took 62.7 ms at 1e4 and 633.7 ms at 1e5; with a stage that adds id-less records, 67.8 / 671.9 ms; with unhashable list ids (repr path), 156.6 / 1591 ms; peak memory 2.6-10.3 MB at 1e5. TypeScript took 18.3 / 134.0 ms and C# 15 / 201 ms.
- Fix (later slice): key numbers by a type-tagged string (str hashing is SipHash with a random seed), or bound the input size. C# already uses string keys; the V8 `Map` number hashing was not probed.

**L-3. `tools/check_versions.py`: a deeply nested JSON file escapes as an uncaught `RecursionError`: exit 1 with a traceback, not the documented exit 2.**
- Repro (probe P6): `ts/package.json` = `"[" * 100000` gives `exit=1 :: RecursionError: maximum recursion depth exceeded while decoding a JSON array`. `_json_version` catches only `ValueError, KeyError, TypeError`.
- It still fails CLOSED (nonzero, never "agree"), so this is a contract and diagnostics defect, not a bypass. Fix: also catch `RecursionError` (and `MemoryError`) and raise `Unreadable`.

**L-4. Dev-tool dependency policy: no lockfile/hashes for the `lint` extra; MPL-2.0 and native code in the closure; audit not run.**
- `lint = ["ruff>=0.15,<1", "mypy>=2.3,<3"]` (ranges, no hashes, no lockfile). The policy says "CI installs from lockfiles only", which the repository did not do for `dev` either (pre-existing). Local closure (installed versions): ruff 0.15.15 MIT (one native binary), mypy 2.3.0 MIT (mypyc-compiled), typing_extensions 4.14.1 PSF-2.0, mypy_extensions 1.0.0 MIT, pathspec 1.1.1 **MPL-2.0** (the policy says "flag for thought": acceptable for a dev-only tool that is never shipped), librt 0.13.0 MIT (native), ast-serialize 0.6.0 MIT, tomli only below 3.11 (not used on 3.12).
- `dependencies = []` is still empty. The extra is opt-in: the built wheel's METADATA has `Requires-Dist: mypy<3,>=2.3; extra == 'lint'` and `ruff<1,>=0.15; extra == 'lint'`, so a plain `pip install contexel` cannot pull them.
- pip-audit is NOT run (condition C1).

**L-5. A LOCALLY built sdist would ship the local review-scratch directory (agent review artifacts).** Pre-existing; the published artifacts are not affected.
- the local review-scratch directory is excluded only through `.git/info/exclude`, which hatchling ignores (it reads `.gitignore`). Repro (probe P9): a copy of HEAD plus `.git/info/exclude` and a file in that directory gives `review-scratch directory IN SDIST`; `.mypy_cache` and `.ruff_cache` are excluded (they write their own `.gitignore`).
- release.yml builds with `python -m build` from a fresh CI checkout, so a published sdist is clean. A sdist the human builds from the working tree would carry agent artifacts (temporary paths, agent identifiers) into a public package. Fix: add the local review-scratch directory to `.gitignore`, or give `[tool.hatch.build.targets.sdist]` an explicit `include`.
- That the sdist contains the whole tracked repository (tests, site, docs, ts/, csharp/, benchmarks, root markdown) is a pre-existing size and hygiene matter, not a security concern: everything in it is already public in the repository, and installing the sdist only builds `contexel/` through hatchling.

### INFO

- **I-1. Fingerprint, things still LIVE after build (AC30 limits).** Python (probe P5): behavior changes while the fingerprint stays the same for a list subclass, a dict subclass, OrderedDict, deque, bytearray, a custom object, a custom object inside a tuple and a custom object inside a set; the same with a closure or lambda (callables are hashed by `__name__`). Exact list, nested dict/list, set and a list inside a tuple are now frozen (all four were live on main). TypeScript (probe P7): live for an Array subclass, a class instance, a Map, an element object of a Set and a TypedArray; frozen for a plain array, a nested object, a Set shell and a frozen object (all live on main). C# (probe P8): a closure over a list stays live (fingerprint same, behavior 0 -> 1). All of these are documented (CHANGELOG Behavior change 10, Known limitations, ADR-008), EXCEPT two TypeScript shapes, which are not named: a **TypedArray** (hashed by content at build, not copied) and a **cross-realm** plain object or array (`node:vm`: the exact-prototype check fails, so it stays live: probe P7b `behaviour changed: true fp changed: false`). Recommend one doc line.
- **I-2. Policies that share a fingerprint although they behave differently** (by design and documented: names and type names only): two lambdas (all three languages); `Obj(1)` and `Obj(2)`; two `functools.partial`; `deque([1])` and `deque([2])`; `b"a"` and `b"b"`; `(1,)` and `[1]` (Python); TS `Map` k=1 and k=2, `Date` and `RegExp`; a C# lambda wrapper around two different inner pipelines. FIXED relative to main: Python `{'a,b'}` vs `{'a','b'}` and `{True}` vs `{1}` now differ; nested pipelines differ in all three; TS `Set {1}` vs `{'1'}` differ; a C# HashSet no longer depends on insertion order. `{1}` vs `frozenset({1})` now share a fingerprint, which is correct (same behavior).
- **I-3. Reproducibility.** Python set fingerprints are identical under PYTHONHASHSEED 0, 1, 2, 3, 42 and 12345 for `{2, None, (1,2), 2.5, "x", frozenset(...), True}` nested in dicts and lists (probe P5b: one value over six seeds). A frozenset used as a dict KEY varies with the seed (5 distinct values over 6 seeds), as documented under Known limitations (pre-existing). C# is culture-independent: identical fingerprints under tr-TR, de-DE, ar-SA and invariant (Ordinal ordering, InvariantCulture). TypeScript sorts by UTF-16 code unit (locale-free). No platform dependence: Python float `repr` is shortest round-trip, and sha256 is used everywhere.
- **I-4. Raise / recursion / memory on hostile parameters: no regression against main.** A cyclic list and 5000-deep nesting raise `RecursionError` in Python on both head and main; TS cyclic and 20000-deep raise `RangeError` on both; a TS Set that contains a cycle now throws where main rendered `{}` (documented). In C#, a self-containing list or set overflows the stack, which kills the process and cannot be caught: pre-existing and documented. Parameters are developer-supplied, so this is not attacker-reachable in the normal model. Rendering a set is O(n), and sorting strings never raises `TypeError`.
- **I-5. Trace on hostile objects fails LOUD, not silent (pre-existing).** Python ids whose `__repr__` raises (unhashable), whose `__hash__` raises a non-TypeError, or whose `__eq__` raises propagate out of the traced stage (RuntimeError/ValueError, the same on main). C# raises `InvalidCastException` for a dict id with non-string keys (main too). TS: a BigInt or cyclic id throws in token counting (main too). None of these is reachable from JSON-shaped data, and none hides the audit silently.
- **I-6. The documented bound and the over-report direction, quantified (probe P1, Python; TS and C# share the rule through the vectors).** A stage that drops 5 id-carrying records and ADDS k id-less records reports `max(0, 5 - k)`: k=0 gives 5, k=2 gives 3, k=5 gives 0, k=9 gives 0 (main is the same: main's rule had the same gap for added records). An id-less record planted in the INPUT beside a drop no longer hides it: `['a']` on head against `[]` on main, and likewise in TS and C#. The built-in traced stages never add records (select, dedupe, rank, allowlist, quarantine, rescore, truncate_field, trim_to_budget; `merge` is not traced), so attacker-planted id-less records cannot hide drops in built-ins. Over-report: a stage that strips the id from a survivor AND drops an id-less record reports that survivor (`['a']`; main reported `[]`); distinct NaN objects are reported dropped in Python (`[nan]`, while TS and C# match NaN). Both are on the safe side; the NaN case is undocumented but harmless. Falsy ids (0, "", None/null, False, []) and duplicates (`['a','a']`) are reported correctly; a 1 MB id is reported intact.
- **I-7. Cross-language agreement on hostile ids.** The shared vectors cover: id-less beside a drop, select stripping ids, per-stage attribution, input order, falsy ids, duplicates, list ids. Outside the vectors the languages disagree on: bool vs number (L-1), list vs JSON-text string (L-1), NaN (Python over-reports), and a null record (now id-less in C#, where main threw NullReferenceException: an improvement). TypeScript also loses integers above 2^53 at the JSON-parse layer (outside the library).
- **I-8. tiktoken `disallowed_special=()` (AC31): no budget evasion.** Probe P10 (real cl100k_base, offline from the local cache, socket connect disabled): the endoftext special-token literal counts 7 (ordinary text) against 1 as a special token; 1000 copies count 6001 against 1000; plain text is unchanged (2 = 2). The count is always at least the special-token count, so attacker text cannot shrink its own token count to slip past `trim_to_budget`; before the slice the same text raised `ValueError` (main repro). The tokenizer name is `tiktoken:cl100k_base`. It does not raise.
- **I-9. Secrets / personal data (sweep item 1).** The whole-branch diff (`git diff 0f09d36..5f4e444`) was grepped for Windows profile paths (the drive-letter user folder in both slash styles, the application-data folder), the local user-name prefix, webmail addresses, Unix home paths, the session scratch folder name, GitHub token prefixes (classic and fine-grained), AWS access-key ids, `sk-` API keys, private-key headers and `password=` / `secret=` / quoted `token=` assignments: no match. Commit message bodies of `main..HEAD`: no e-mail, path, agent identifier or `Co-Authored-By`. The only e-mail is the owner's git author/committer identity in the commit metadata (13 of 13 commits), which is the project owner's standing configured identity and not file content. No secret-like tracked files (`.env`, `.pem`, `.key`, `id_rsa`, `credentials`).

## Sweep checklist (role card)

1. Secrets: clean (I-9).
2. Input boundaries: trace attribution (L-1, L-2, I-5 to I-7); fingerprint snapshot (I-1 to I-4); check_versions (below, L-3). No injection sink: no SQL, shell, path built from data, or template.
3. Dependencies: no runtime dependency; dev-only `lint` extra reviewed (L-4); **pip-audit not run (C1)**.
4. Dangerous constructs: none added. No eval/exec/pickle/subprocess/shell in `contexel/` or `tools/check_versions.py` (grep). The library added no import beyond the stdlib; `contexel/` has no open/socket/urllib/subprocess.
5. AuthZ/AuthN: not applicable (library). CI token scope is M-1.
6. Failure posture: check_versions fails closed on every odd input tried (below); trace fails loud on hostile objects; resource use is linear except the pre-existing int hash flood (L-2).

### tools/check_versions.py (focus d), executed
- Reads only seven constant relative paths joined to `--root`. Nothing from file content becomes a path; `--root` is operator-chosen (CLI). A symlinked location would be followed (`read_text`) and only the matched version string printed; that needs a PR author, who can already run code. Symlinks were not probed (Windows without the privilege).
- No eval/exec/subprocess/shell/write (grep: `no eval/exec/subprocess/shell/write in check_versions.py`).
- ReDoS, 1 MB hostile inputs per regex (probe P6): `[project]`+1 MB spaces 9.6 ms; `[project]`+500k lines 26.2 ms; 100k `[project]` lines 0.0 ms; `version="` lines (pyproject) 21.9 ms; `__version__ = "` lines 0.0 ms; `export const VERSION = "` lines 0.0 ms; 111k `<Version>` 1.3 ms; `<Version>`+1 MB 4.1 ms. All linear (each `[^"]+` or `[^<]+` stops at the next delimiter, which the next start supplies).
- Fail-closed matrix (CLI on a copied tree): baseline exit 0; BOM in package.json exit 2; BOM in csproj and in `__init__.py` exit 0 (correct: the anchors are not on line 1); CRLF in all files exit 0 (correct); missing `ts/src/index.ts` exit 2; non-UTF-8 `__init__.py` exit 2; a directory in place of package.json exit 2; a leading space in `<Version>` exit 1 (disagree); single-quoted TOML version exit 2; empty version exit 2; mismatch exit 1; numeric JSON version exit 2; nonexistent root exit 2; deep JSON exit 1 with a traceback (L-3). In no case did it report agreement while a location was unparsed.

### CI and release (focus c)
- The hygiene job and the release `test` step use the same pinned SHAs as every other job (checkout 3d3c42e5..., setup-python 5fda3b95...). No new action, permission, secret, `pull_request_target` (none in any workflow) or GitHub expression inside an added line (grep of the added workflow lines for the dollar-double-brace syntax: none). release.yml keeps its top-level `contents: read`; the version check runs before any install, stdlib only.
- Local equivalent of the hygiene job (installed tools, no network): `check_versions: all 7 version locations say 0.1.17` (exit 0); `ruff 0.15.15 ... All checks passed!`; `mypy 2.3.0 ... Success: no issues found in 8 source files`; wheel contents below.

### Packaging / runtime surface (focus e)
- Wheel built with `hatchling.build.build_wheel` from the HEAD archive: `contexel/{__init__,errors,pipeline,shaped,stages,tokens,trace,validate}.py`, `contexel/py.typed` and `dist-info/{METADATA,WHEEL,licenses/LICENSE,RECORD}`, nothing else. `Requires-Python: >=3.9`; every `Requires-Dist` carries an `extra ==` marker.
- Suites on the HEAD archive: Python `531 passed in 3.42s` (529 plus the 2 tiktoken/hatchling tests that run where installed); TypeScript `tests 351, pass 351, fail 0`; C# `Passed: 312, Failed: 0`.

## Executed probes (scripts under <tmp>/probes, run against <tmp>/head = HEAD archive and <tmp>/main = 0f09d36 archive)
- P1 `p_trace.py`: trace attribution, hostile ids (head vs main). Key lines: head `1 idless beside drop: ['a']`, main `[]`; `2 adds 2 idless, drops 5 -> reported 3`; `4a True survives, 1 dropped: [True]`; `4c ... ['[1, 2]']`; `4f NaN distinct objects: [nan]`; `5 BadRepr RAISES RuntimeError` (both).
- P2/P3 `p_timing.py`, `p_collide.py`: linear scaling and the int hash flood (numbers in L-2).
- P4 `p_ts.mjs` and P8 (the C# console probe): TS and C# hostile ids, timing, snapshot, culture.
- P5 `p_fp.py`, P5b `p_seed.py`: Python live shapes, collisions, cycles, hash seed.
- P6 `p_redos.py` and the CLI matrix: check_versions.
- P7 `p_ts.mjs`, P7b `p_ts2.mjs`: TS own `__proto__` key (stays an own key, `Object.prototype` not polluted, fingerprint differs from `{a:1}`); `constructor`/`prototype` keys inert; a null-prototype object copied with a null prototype (frozen after build); a getter read once at build (`[{"v":1}] [{"v":1}]`, main `2` then `3`); symbol and non-enumerable keys not copied (documented); cross-realm objects live (undocumented).
- P8 C# console probe (assembly named for InternalsVisibleTo): `nested inner.Run differ: True`, `nested lambda wrapper differ: False`, `HashSet order-indep: True` (main False), `closure list mutated: behaviour 0->1, fingerprint same True`, culture-invariant fingerprints.
- P9 sdist file-selection probe (L-5). P10 `p_tik.py` (I-8).

## Residual risks accepted / documented
- The trace rule is an approximation for black-box stages: a stage that adds k id-less records can hide up to k drops, and a stage that strips ids and drops id-less records can over-report (ADR-008, CHANGELOG 8). Accepted by ADR-008.
- Python subclasses and custom objects, TS class instances, Map and Set elements, and C# closures stay live (CHANGELOG 10, Known limitations). Accepted by ADR-008 and rulings S3-2 to S3-4.
- Fingerprints are identifiers, not integrity controls against stage code (names only; `__contexel_desc__` is trusted).
- Pre-existing and out of slice: L-1, L-2, L-5, I-4 (C# stack overflow), and the frozenset dict key that depends on the hash seed.

## Not verified
- **pip-audit / any network advisory lookup** (no network allowed): condition C1.
- The **first CI run** of the `hygiene` job and of the release version step; Linux and macOS; the repository's default GITHUB_TOKEN permission setting (not visible from the tree).
- **Python 3.9 and 3.10** (only 3.12 here), **Node 18 and 20** (only Node 24 here), .NET only 8.0.403 on Windows.
- Symlinked version files (Windows without the privilege); V8 `Map` number-hash flooding; the npm and NuGet closure (unchanged by this slice).
