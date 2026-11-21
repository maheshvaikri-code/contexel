# Foundation hardening, Slice 3: Audit truthfulness and release hygiene — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the audit trail tell the truth (a dropped record is never hidden, a policy fingerprint covers what shaped the output and cannot go stale, tiktoken counts special-token text) and make a release impossible with mismatched version copies or an untyped, unlinted package.

**Architecture:** Python is the canon and each port follows it, held together by the shared vectors for what is language-independent (dropped ids, through a new case kind) and by per-language golden baselines for what is language-local (fingerprints, ADR-001/002). Four layers, one task group each: trace attribution (Tasks 2 to 3), fingerprint coverage and the build-time copy (Tasks 4 to 7), tiktoken (Task 5), release hygiene (Tasks 8 to 9), documentation (Task 10).

**Tech Stack:** Python 3.9+ standard library (pytest for tests), TypeScript 5 on Node 22 (`node:test`), C# 12 on .NET 8 (xunit); `ruff` and `mypy` as dev-only tools.

**Spec:** brief `docs/briefs/foundation-hardening.md` (ACs 28 to 33; AC 34 for the documentation); design `docs/superpowers/specs/2026-11-19-foundation-hardening-design.md` sections 7 and 8; `docs/adr/008-policy-fingerprint-and-trace-attribution.md`; master plan `docs/plans/foundation-hardening.md` (Slice 3 row, deviation log R1 to R22 of Slice 2).

**Baseline (verified 2026-11-20 on `main` at `835454a`, the Slice 2 merge):** Python 475 passed; TypeScript 313 pass (`tsc` clean); C# 279 passed (0 warnings); `parity/vectors.json` 70 cases (31 error cases). **Targets after this slice:** Python 529, TypeScript 347, C# 312, 77 vector cases. Each task states the count it must reach.

**How this plan was verified:** the code in every block below was written and run in a scratch copy of `main` (all three suites, vectors regenerated twice with an identical hash, ruff, mypy, the site check, the version check). The full Python suite also ran on 3.11 (523 passed, 2 skipped where `hatchling` and `tiktoken` are absent). On Python 3.9 the changed files compile, the new behaviors run, the version check runs and the vectors regenerate identically, but `pytest` is not installed for 3.9 here, so the full suite on 3.9 is left to CI. The blocks are extracted from that tree by script, not retyped, and a second script replayed them onto a fresh checkout of `main`, ran the suites after each task's tests and after its implementation, and compared the resulting tree with the scratch tree (result at the end of this file). The red results quoted in the steps are measured, not predicted.

## Global Constraints

- Python >= 3.9 and zero runtime dependencies. Repository tooling (`tools/`) and tests must also run on 3.9: no `X | Y` annotations evaluated at runtime, no `tomllib`, no `match`. The dev tools `ruff` and `mypy` live in a separate `lint` extra and are never imported by the library.
- Valid-today inputs keep byte-identical output **and** unchanged fingerprints, except for the shapes AC 29 and AC 30 name (a bound set, a nested pipeline, a tiktoken tokenizer, a mutated bound container). The golden baselines of Task 1 prove it.
- Python is canon; TypeScript and C# match it through the shared vectors. Fingerprints stay language-local (ADR-001, ADR-002): no cross-language fingerprint vectors.
- No version bump: identifiers change only at a release (the human's call); the work accumulates under `[Unreleased]` in `CHANGELOG.md`.
- One commit per task, Conventional Commits, 72 characters at most. **No `Co-Authored-By` trailer** (the project owner's standing rule, which overrides the harness default). Never push, open a pull request or merge: those are the human's.
- The repository is **public**: no Windows user name, home or temporary path, e-mail address or agent identifier in any file or commit message.
- Tests are never weakened to go green. A golden value that fails means behavior changed: stop and report.
- Regenerate vectors only with `PYTHONPATH=. python parity/generate_vectors.py` (a stale installed `contexel` shadows the checkout otherwise); never edit `parity/vectors.json` by hand.
- This machine writes CRLF; the blocks below are LF. Either is fine in the working tree, but **byte-compare each file with its block** after writing it: the editing tools have in the past turned a backslash-u escape into the character it names, and a shell heredoc collapses backslashes. The regular expressions in `tools/check_versions.py` are the one place this slice needs backslashes.

## Review Focus

The input classes the brief implies but its own tests would not reach, most likely first, each with the test that pins it:

1. **Falsy, duplicated and list-valued ids in `dropped_ids`** (a rewrite of the attribution must not treat `0`, `""` or a repeated id as "no id"): vector cases `trace_dropped_ids/falsy_ids_are_reported`, `.../a_duplicate_id_reports_the_dropped_copy`, `.../list_ids_are_attributed` (Task 3, all three languages).
2. **A stage that adds id-less records** (the documented bound: it can hide at most that many drops): `test_trace_a_stage_that_adds_idless_records_never_hides_more_than_it_added` and its TypeScript and C# twins (Tasks 2 and 3); a stage that only strips ids hides none (`..._select_stripping_ids_is_not_a_drop`).
3. **Mixed-type and nested sets in a fingerprint** (`{2, None, (1, 2), 2.5, frozenset(...)}` must sort without a `TypeError`, and give one fingerprint under every `PYTHONHASHSEED`): `test_fingerprint_of_a_set_is_the_same_under_every_hash_seed`, `test_a_set_nested_in_a_list_or_dict_is_covered_too` and the TypeScript and C# twins (Tasks 4, 6, 7).
4. **The caller changes a bound container after building the stage**, at every depth, and what is deliberately not copied (a subclass, a custom object, a function, a TypeScript class instance, `Map` and the elements of a `Set`): `test_bound_container_mutation_cannot_change_behavior`, `test_nested_bound_containers_are_copied_at_every_depth`, `test_a_callable_a_custom_object_and_a_list_subclass_are_not_copied` and twins (Tasks 4 and 6).
5. **Version-file inputs the check must survive or refuse loudly**: CRLF files, a `[tool.*]` table that has its own `version`, a missing file, a file with no version, `package-lock.json` whose two entries disagree: `tests/test_check_versions.py` (Task 8). A pre-release string is compared as an exact string and is out of scope.

## Rulings made at plan time

Each is open to correction at the plan review; none changes a security control or a public contract without being listed under "Behavior changes".

| # | Ruling | Why | Cost if wrong |
|---|---|---|---|
| S3-1 | ADR-008 is accepted as written: **snapshot at build** (option A), not fingerprint at call time. | The human chose it at G1; it keeps `.fingerprint` a plain attribute and calls O(1). | Code that edits a bound list after building the stage must rebuild the stage (Behavior change 10). |
| S3-2 | Python copies only **exact** `list`, `tuple`, `dict`, `set` (any depth); a subclass, a custom object, a callable and a `frozenset` are returned as they are. | A deep copy of arbitrary objects would break stateful objects and identity. Hashing a subclass by value stays (changing it would change today's fingerprints, which AC 29 forbids). | A container subclass can still change behavior without changing its fingerprint: documented under "Known limitations". |
| S3-3 | TypeScript copies arrays, plain objects and `Set` shells (a `Set`'s elements are not copied). | A `Set` of objects is identity-keyed: copying its elements would break membership tests on the caller's own objects. | A mutated element object inside a bound `Set` is not covered (documented). |
| S3-4 | C# detects a nested pipeline from the delegate's `Target` (`new Stage("inner", inner.Run)`), adds **no new public API**, and cannot promise AC 30 for closures. | A `Stage` is a delegate; its `Parameters` only feed the fingerprint. A new `AsStage` method would be a public-contract change that was not in the design. | A lambda wrapper is opaque (documented, pinned by a test). |
| S3-5 | The dropped-ids rule is checked in all three languages through a **new vector kind** `trace_dropped_ids`; C# counts a `null` item as id-less. | AC 28 is language-independent; without a shared case the ports could drift silently. | A fourth case kind in each runner (small). |
| S3-6 | `ruff` and `mypy` go in a new **`lint`** extra, not `dev`. ruff: rules `E,F,W,B`, line length 100. mypy: default strictness, target 3.10. | mypy 2.x needs Python >= 3.10 and the 3.9 legs install `dev`. `--strict` (14 errors) is not adopted: no brief criterion asks for it. | A stricter gate is a later, separate decision. |
| S3-7 | `tools/check_versions.py` reads `pyproject.toml` with a regular expression, compares exact strings, runs in the new CI job `hygiene` and in the release `test` job. | It must run on 3.9 and in the gate that every publish job already depends on. | A pre-release spelling mismatch between PyPI and npm would fail loudly. |
| S3-8 | tiktoken tests: a fake `tiktoken` module proves the mechanism (name, `disallowed_special=()`) offline; one test uses the real package and **skips** when the package or its cached encoding is unavailable. | The encoding files are fetched on first use; a test must never fail for lack of the network. | None for correctness; the real-package test runs where tiktoken is installed (the release gate installs `accurate`). |

## Coverage of the acceptance criteria

| AC | Proven by | Task |
|---|---|---|
| 28 | `test_trace_reports_a_drop_when_another_survivor_never_had_the_id`; vector cases `trace_dropped_ids/*` replayed by TypeScript and C#; the twins in each language | 2, 3 |
| 29 | `test_fingerprint_differs_for_set_contents`, `..._for_nested_pipelines`, `..._for_tiktoken_encodings`; golden baselines in all three languages stay green | 1, 4, 6, 7 |
| 30 | `test_bound_container_mutation_cannot_change_behavior`, `test_pipeline_copies_its_list_of_stages` and twins; C# limit documented and pinned | 4, 6, 7 |
| 31 | `test_tiktoken_counts_special_token_literals`, `test_tiktoken_tokenizer_asks_for_special_tokens_to_be_ordinary_text` | 5 |
| 32 | `tests/test_packaging.py`; `ruff` and `mypy` clean; the CI `hygiene` job | 9 |
| 33 | `tests/test_check_versions.py` (`test_agreeing_versions_pass`, `test_disagreeing_versions_fail_naming_the_file`); CI `hygiene` and the release gate | 8 |
| 34 | changelog "Behavior changes" 8 to 11; no new public stage or parameter | 10 |
| 35, 36 | not in this slice (CI matrix is proven by the human's push; fuzz is Slice 7) | n/a |

## Execution notes

- **Branch:** `feat/hardening-s3-audit-release`, from a clean `main` (Task 0). Task 0 and the close-out commit nothing but the branch and the evidence.
- **Subagent-driven execution, if chosen:** one fresh implementer per task, handed this file's task text only; the controller byte-compares every file to its block after each task (lesson from Slices 1 and 2: plan code is not preserved verbatim by implementers), runs the three suites itself and reads the diff before dispatching the independent task reviewer. Mutation testing and the whole-branch gates follow the last task (see "Gates").
- **Stop-and-ask triggers** (Doctrine section 5 and the master plan): a golden value or count that does not match; anything that needs the network or a credential (installing `ruff` or `mypy`, `pip-audit`); an acceptance criterion that proves wrong when tested; a change to a public contract not listed under "Behavior changes".

## Tasks

### Task 0: Baseline, branch and tooling check (no commit)

**Acceptance criteria:** none (makes every later task verifiable)

**Files:**
- No file changes. Everything this task learns goes in the ledger.

**Interfaces:**
- Consumes: `main` at or after `835454a` (Slice 2 merged; later commits may only touch `docs/`).
- Produces: the branch `feat/hardening-s3-audit-release` and the baseline counts every later task compares against.

- [ ] **Step 0.1: Branch from a clean `main`**

```bash
git checkout main && git pull --ff-only origin main
git status --short            # must print nothing
git diff 835454a..HEAD --stat -- . ':!docs'   # must print nothing (only docs changed)
git checkout -b feat/hardening-s3-audit-release
```

- [ ] **Step 0.2: Baseline of all three suites**

```bash
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
cd ts && npm run build && npm test
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
```

Expected:

```text
475 passed
ℹ tests 313 / ℹ pass 313 / ℹ fail 0   (tsc clean)
Passed!  - Failed: 0, Passed: 279, Skipped: 0, Total: 279   (0 warnings)
```

**Stop and report instead of improvising** if any count differs: this plan was written against exactly these numbers.

- [ ] **Step 0.3: Measure what the lint and type gate will face (read-only)**

```bash
python -m mypy contexel --python-version 3.10 --no-incremental
python -m mypy contexel --python-version 3.10 --strict --no-incremental | tail -1
python -m ruff check contexel --no-cache
python -m ruff check contexel --no-cache --select E,F,W,B --statistics
```

Expected:

```text
contexel\shaped.py:66: error: Argument 1 has incompatible type "list[Any] | tuple[Any, ...]"; expected "list[dict[str, Any]]"  [arg-type]
Found 1 error in 1 file (checked 8 source files)
Found 14 errors in 6 files (checked 8 source files)        <- --strict, informational only
All checks passed!
9	E501	line-too-long                                          <- at the default width of 88
```

Measured on 2026-11-20 with mypy 2.3.0 and ruff 0.15.15. mypy 2.x refuses `--python-version 3.9` (its floor is 3.10), which is why the configuration in Task 9 targets 3.10. This retires the plan-time risk that clearing mypy would be disproportionate: one error, one line. If ruff or mypy is not installed, installing them needs the network: ask the human first.

- [ ] **Step 0.4: Dependency-policy record for the two dev tools (read-only)**

Facts read from the installed packages (`importlib.metadata`): **ruff 0.15.15**, MIT, no dependencies; **mypy 2.3.0**, MIT, requires Python >= 3.10 and depends on `typing_extensions`, `mypy_extensions`, `pathspec`, `librt`, `ast-serialize` (and `tomli` below 3.11). Both are dev-only: they go in a new `lint` extra, are never shipped and add no runtime dependency. Need: CI has no lint or type gate today (the Makefile that lints is git-ignored and skips `contexel/`). **Open item for the human:** `pip-audit` (the policy's "audit clean today") needs the network and was not run at plan time; run it on the two packages or waive it in writing before Task 9 lands.


---

### Task 1: Pin today's policy fingerprints in all three languages

**Acceptance criteria:** AC 29 ("a pipeline containing none of those has the **same** fingerprint as before"); the Slice 1 close-out item (a callable without `__name__`)

**Files:**
- Modify: `tests/test_fingerprint_golden.py`, `ts/package.json`
- Create: `ts/test/fingerprint.test.ts`, `csharp/Contexel.Tests/FingerprintTests.cs`

**Interfaces:**
- Produces: golden baselines that Tasks 4, 6 and 7 must keep green. Every value was recorded from `main` before any library change (Python's four new values are for a `functools.partial` and a callable instance, as a bound parameter and as a bare stage; TypeScript's and C#'s eight and seven are their first baselines).
- Fingerprints stay language-local (ADR-001, ADR-002): the TypeScript and C# values are not comparable with Python's.

- [ ] **Step 1.1: Add the baselines**

In `tests/test_fingerprint_golden.py`, replace this block:
<!-- OP replace-old path=tests/test_fingerprint_golden.py -->
```python
together they bind every branch of ``_stable_repr``: primitives, lists and
tuples, dicts (mixed-type keys, nested values), named callables, and the
type-name fallback for an opaque object.
"""
import pytest
```
with:
<!-- OP replace-new -->
```python
together they bind every branch of ``_stable_repr``: primitives, lists and
tuples, dicts (mixed-type keys, nested values), named callables, and the
type-name fallback for an opaque object, and the two fallbacks for a callable
that has no ``__name__`` (a ``functools.partial`` or an instance of a class
with ``__call__``): the type name as a bound parameter, and the word
``callable`` as a bare stage.
"""
import functools

import pytest
```

In `tests/test_fingerprint_golden.py`, replace this block:
<!-- OP replace-old path=tests/test_fingerprint_golden.py -->
```python
class Opaque:  # an opaque object: fingerprints by its type name only
    pass
```
with:
<!-- OP replace-new -->
```python
class Opaque:  # an opaque object: fingerprints by its type name only
    pass


class Scorer:  # a callable object with no __name__
    def __call__(self, r):
        return r["a"]
```

In `tests/test_fingerprint_golden.py`, replace this block:
<!-- OP replace-old path=tests/test_fingerprint_golden.py -->
```python
        stage(rescore, query="a b", fields=("x", "y"))]), "11b53020d9d935bb"),
    "empty_pipeline": (lambda: pipeline([]), "2e38e77b22c314a4"),
}
```
with:
<!-- OP replace-new -->
```python
        stage(rescore, query="a b", fields=("x", "y"))]), "11b53020d9d935bb"),
    "empty_pipeline": (lambda: pipeline([]), "2e38e77b22c314a4"),
    # a callable WITHOUT a __name__ bound as a parameter: the type name
    "partial_parameter_without_a_name": (lambda: pipeline([
        stage(rank, by=functools.partial(key))]), "2b15c203079d2493"),
    "callable_instance_parameter_without_a_name": (lambda: pipeline([
        stage(rank, by=Scorer())]), "d183451e1e9263c8"),
    # ... and as a bare stage: the word "callable", so two different nameless
    # stages share a fingerprint (documented: name your stages)
    "bare_partial_stage_without_a_name": (lambda: pipeline([
        functools.partial(select, fields=["a"])]), "216c659b364587e7"),
    "bare_callable_instance_stage_without_a_name": (lambda: pipeline([
        Scorer()]), "216c659b364587e7"),
}
```

Create `ts/test/fingerprint.test.ts` with exactly this content (it ends with one newline):
<!-- OP create path=ts/test/fingerprint.test.ts -->
```typescript
/**
 * Policy fingerprints (ADR-008, brief AC 29-30). Mirrors the policy tests in
 * tests/test_audit_truth.py and the baseline in tests/test_fingerprint_golden.py.
 *
 * Fingerprints are language-local (ADR-001): these values are TypeScript's own.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  allowlist,
  dedupe,
  pipeline,
  quarantine,
  rank,
  rescore,
  select,
  stage,
  trimToBudget,
  truncateField,
  type Records,
} from "../src/index.js";

// --- the recorded baseline (written before the audit-truthfulness change) ---
// Do not regenerate these values to make a test pass: a change here is a
// behavior change that needs an ADR.

function annotate(records: Records, _options: unknown): Records {
  return records;
}

function bare(records: Records): Records {
  return records;
}

class Opaque {}

const SHAPES: Record<string, [() => ReturnType<typeof pipeline>, string]> = {
  contract: [
    () =>
      pipeline([
        stage(allowlist, { field: "source", allowed: ["repo", "docs"] }),
        stage(quarantine, { fields: ["snippet"] }),
        stage(select, { fields: ["path", "line", "source", "snippet"] }),
        stage(dedupe, { key: ["path", "line"] }),
        stage(rescore, { query: "exponential backoff jitter", fields: ["snippet", "path"] }),
        stage(truncateField, { field: "snippet", maxTokens: 12 }),
        stage(rank, { by: "score", desc: true }),
        stage(trimToBudget, { maxTokens: 150 }),
      ]),
    "c0fd8cd67a287c16",
  ],
  primitives: [
    () =>
      pipeline([
        stage(select, { fields: ["a", "b"] }),
        stage(dedupe, { key: "a" }),
        stage(rank, { by: "score", desc: true }),
        stage(trimToBudget, { maxTokens: 100 }),
      ]),
    "d0b41503982b29a1",
  ],
  list_of_mixed_scalars_and_null: [
    () =>
      pipeline([
        stage(allowlist, { field: "s", allowed: ["x", null, 1, 2.5, true] }),
        stage(quarantine, { fields: ["snippet"], action: "drop" }),
      ]),
    "bd1f276ee89b8191",
  ],
  object_with_nesting: [
    () =>
      pipeline([
        stage(annotate, {
          mapping: { b: [1, null, { z: 2.5 }], k: "v" },
          empty: {},
          label: "m",
        }),
      ]),
    "775bd890610029e3",
  ],
  opaque_object: [() => pipeline([stage(annotate, { marker: new Opaque(), n: 3 })]), "98cabc1924c55dbc"],
  named_function: [() => pipeline([stage(annotate, { key: bare, desc: false })]), "575df49f70c34e06"],
  bare_named_function: [() => pipeline([bare]), "d33631bdd67f21f3"],
  empty_pipeline: [() => pipeline([]), "4f53cda18c2baa0c"],
};

for (const [name, [build, expected]] of Object.entries(SHAPES)) {
  test(`fingerprint matches the recorded baseline: ${name}`, () => {
    assert.equal(build().fingerprint, expected);
  });
}

test("the keyword order of bound params does not change the fingerprint", () => {
  const a = pipeline([stage(truncateField, { field: "s", maxTokens: 5, suffix: ".." })]);
  const b = pipeline([stage(truncateField, { suffix: "..", maxTokens: 5, field: "s" })]);
  assert.equal(a.fingerprint, b.fingerprint);
});
```

In `ts/package.json`, replace this block:
<!-- OP replace-old path=ts/package.json -->
```json
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "test": "tsc -p tsconfig.test.json && node --test dist-test/test/parity.test.js dist-test/test/behavior.test.js dist-test/test/cases.test.js dist-test/test/errors.test.js dist-test/test/strict.test.js dist-test/test/controls.test.js dist-test/test/config.test.js dist-test/test/runner.test.js dist-test/test/docs.test.js",
    "prepublishOnly": "npm run build && npm test"
  },
```
with:
<!-- OP replace-new -->
```json
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "test": "tsc -p tsconfig.test.json && node --test dist-test/test/parity.test.js dist-test/test/behavior.test.js dist-test/test/cases.test.js dist-test/test/errors.test.js dist-test/test/strict.test.js dist-test/test/controls.test.js dist-test/test/config.test.js dist-test/test/runner.test.js dist-test/test/docs.test.js dist-test/test/fingerprint.test.js",
    "prepublishOnly": "npm run build && npm test"
  },
```

Create `csharp/Contexel.Tests/FingerprintTests.cs` with exactly this content (it ends with one newline):
<!-- OP create path=csharp/Contexel.Tests/FingerprintTests.cs -->
```csharp
using Xunit;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>Policy fingerprints (ADR-008, brief AC 29-30). Mirrors the policy
/// tests in tests/test_audit_truth.py and the baseline in
/// tests/test_fingerprint_golden.py. Fingerprints are language-local
/// (ADR-002): these values are C#'s own.</summary>
public class FingerprintTests
{
    // A NAMED method: a delegate fingerprints by its method name, and a
    // compiler-generated lambda name would change whenever this file does.
    private static Records Bare(Records records) => records;

    private sealed class Opaque
    {
        public override string ToString() => "Opaque";
    }

    private static Stage Named(string name, Rec? parameters = null) =>
        new(name, Bare, parameters);

    private static List<object?> L(params object?[] items) => [.. items];

    // --- the recorded baseline (written before the audit-truthfulness change)
    // Do not regenerate these values to make a test pass: a change here is a
    // behavior change that needs an ADR.

    public static IEnumerable<object[]> Shapes() =>
    [
        ["contract", "b9c896d3ae7472ab"],
        ["primitives", "313a7dd4b4762dc5"],
        ["list_of_mixed_scalars_and_null", "7c1c9be15a644f14"],
        ["object_with_nesting", "b9ac84206a283de7"],
        ["opaque_object", "704c1b356f69617b"],
        ["named_delegate", "ff5201ec8ea5cd37"],
        ["empty_pipeline", "e3b0c44298fc1c14"],
    ];

    private static Pipeline Build(string shape) => shape switch
    {
        "contract" => new Pipeline(
            Named("allowlist", new Rec { ["field"] = "source", ["allowed"] = L("repo", "docs") }),
            Named("quarantine", new Rec { ["fields"] = L("snippet") }),
            Named("select", new Rec { ["fields"] = L("path", "line", "source", "snippet") }),
            Named("dedupe", new Rec { ["key"] = L("path", "line") }),
            Named("rescore", new Rec
            {
                ["query"] = "exponential backoff jitter", ["fields"] = L("snippet", "path"),
            }),
            Named("truncate_field", new Rec { ["field"] = "snippet", ["max_tokens"] = 12L }),
            Named("rank", new Rec { ["by"] = "score", ["desc"] = true }),
            Named("trim_to_budget", new Rec { ["max_tokens"] = 150L })),
        "primitives" => new Pipeline(
            Named("select", new Rec { ["fields"] = L("a", "b") }),
            Named("dedupe", new Rec { ["key"] = "a" }),
            Named("rank", new Rec { ["by"] = "score", ["desc"] = true }),
            Named("trim_to_budget", new Rec { ["max_tokens"] = 100L })),
        "list_of_mixed_scalars_and_null" => new Pipeline(
            Named("allowlist", new Rec { ["field"] = "s", ["allowed"] = L("x", null, 1L, 2.5, true) }),
            Named("quarantine", new Rec { ["fields"] = L("snippet"), ["action"] = "drop" })),
        "object_with_nesting" => new Pipeline(
            Named("annotate", new Rec
            {
                ["mapping"] = new Rec { ["b"] = L(1L, null, new Rec { ["z"] = 2.5 }), ["k"] = "v" },
                ["empty"] = new Rec(),
                ["label"] = "m",
            })),
        "opaque_object" => new Pipeline(
            Named("annotate", new Rec { ["marker"] = new Opaque(), ["n"] = 3L })),
        "named_delegate" => new Pipeline(
            Named("annotate", new Rec { ["key"] = (Func<Records, Records>)Bare, ["desc"] = false })),
        "empty_pipeline" => new Pipeline(),
        _ => throw new ArgumentException(shape),
    };

    [Theory]
    [MemberData(nameof(Shapes))]
    public void FingerprintMatchesTheRecordedBaseline(string shape, string expected) =>
        Assert.Equal(expected, Build(shape).Fingerprint);

    [Fact]
    public void ParameterOrderDoesNotChangeTheFingerprint()
    {
        var a = new Pipeline(Named("t", new Rec { ["field"] = "s", ["max_tokens"] = 5L }));
        var b = new Pipeline(Named("t", new Rec { ["max_tokens"] = 5L, ["field"] = "s" }));
        Assert.Equal(a.Fingerprint, b.Fingerprint);
    }
}
```

- [ ] **Step 1.2: Run all three suites (they pass: they pin what exists today)**

```bash
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*' tests/test_fingerprint_golden.py
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
cd ts && npm run build && npm test
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
```

Expected:

```text
16 passed
479 passed
ℹ tests 322 / ℹ pass 322 / ℹ fail 0
Passed!  - Failed: 0, Passed: 287, Skipped: 0, Total: 287
```

There is no red phase, because the task pins existing behavior. **Do not recompute any value to make a test pass:** a mismatch means the baseline was mistyped or the code changed, so stop and report.

- [ ] **Step 1.3: Prove the baselines can fail (then undo)**

Change one letter of one expected value in each of the three files, run that file's suite, see exactly that test fail, and restore the value (`git diff` must show no change to the expected values). This is a sanity check, not a commit.

- [ ] **Step 1.4: Commit**

```bash
git add tests/test_fingerprint_golden.py ts/package.json ts/test/fingerprint.test.ts csharp/Contexel.Tests/FingerprintTests.cs
git commit -m "test: pin today's policy fingerprints in all three languages"
```


---

### Task 2: Python trace attribution: a drop is never hidden by an id-less record

**Acceptance criteria:** AC 28 (Python canon)

**Files:**
- Create: `tests/test_audit_truth.py` (AC 28 tests; Tasks 4 and 5 append)
- Modify: `contexel/trace.py`

**Interfaces:**
- Produces: the canon behavior the shared vectors in Task 3 are generated from: `lost = max(0, unidentified_out - unidentified_in)`; the first `lost` unmatched ids (input order) are explained away as "the survivor lost its id", every other unmatched id is reported in `dropped_ids`.
- `unidentified_in` counts input records that are not a `dict` or lack the id field; `unidentified_out` counts the same among the stage's output. Audit keys do not change.

- [ ] **Step 2.1: Write the failing tests**

Create `tests/test_audit_truth.py` with exactly this content (it ends with one newline):
<!-- OP create path=tests/test_audit_truth.py -->
```python
"""Audit truthfulness (ADR-008, brief AC 28-31): the trail must not under-report.

Each test here pins one way the audit used to say something false.
"""
from contexel import allowlist, select, trace
from contexel.trace import traced


def _drops(records, stage_fn, id_field="id"):
    """Run one stage under a trace and return its recorded ``dropped_ids``."""
    with trace(id_field=id_field) as t:
        out = stage_fn(records)
    return out, t.audit()["stages"][0]["dropped_ids"]


# --- AC 28: dropped_ids ----------------------------------------------------

def test_trace_reports_a_drop_when_another_survivor_never_had_the_id():
    # "a" is dropped. The record without an id was in the input already, so it
    # is not evidence that a survivor lost its id: "a" must be reported.
    records = [{"id": "a", "t": "x"}, {"t": "y"}, {"id": "b", "t": "z"}]
    out, dropped = _drops(
        records, lambda r: allowlist(r, field="t", allowed=["y", "z"]))
    assert [r["t"] for r in out] == ["y", "z"]
    assert dropped == ["a"]


def test_trace_select_stripping_ids_is_not_a_drop():
    # select removes the id field from every survivor: nothing was dropped.
    records = [{"id": f"u{i}", "title": f"t{i}"} for i in range(3)]
    out, dropped = _drops(records, lambda r: select(r, fields=["title"]))
    assert len(out) == 3
    assert dropped == []


def test_trace_mixed_input_with_select_stripping_ids_is_not_a_drop():
    # One record never had an id; select strips it from the other two. The
    # stage produced 3 id-less survivors from 1 id-less input, so exactly two
    # input ids are explained by stripping, and none is reported dropped.
    records = [{"id": "a", "title": "x"}, {"title": "y"}, {"id": "b", "title": "z"}]
    out, dropped = _drops(records, lambda r: select(r, fields=["title"]))
    assert len(out) == 3
    assert dropped == []


def test_trace_ambiguity_is_bounded_by_the_lost_count():
    # A custom stage keeps "a" with its id, keeps one record WITHOUT an id and
    # discards two. Trace cannot tell which of "b"/"c" became the id-less
    # survivor, but only ONE id can be explained that way: the other is dropped.
    def keep_a_and_one_stripped(records):
        return [records[0], {"title": "stripped"}]

    records = [{"id": "a", "title": "1"}, {"id": "b", "title": "2"},
               {"id": "c", "title": "3"}]
    out, dropped = _drops(records, traced(keep_a_and_one_stripped))
    assert len(out) == 2
    assert dropped == ["c"]


def test_trace_a_stage_that_adds_idless_records_never_hides_more_than_it_added():
    # Two id-less records are ADDED and "b" is dropped: the explanation budget
    # is 2, so "b" is absorbed. This is the documented, bounded ambiguity.
    def add_two_drop_b(records):
        return [records[0], {"n": 1}, {"n": 2}]

    records = [{"id": "a"}, {"id": "b"}]
    _out, dropped = _drops(records, traced(add_two_drop_b))
    assert dropped == []


def test_trace_dropped_ids_are_reported_in_input_order():
    records = [{"id": 1, "k": "drop"}, {"k": "keep"}, {"id": 3, "k": "drop"},
               {"id": 4, "k": "keep"}]
    _out, dropped = _drops(
        records, lambda r: allowlist(r, field="k", allowed=["keep"]))
    assert dropped == [1, 3]
```

- [ ] **Step 2.2: Run them and watch two fail**

```bash
PYTHONPATH=. python -m pytest -q tests/test_audit_truth.py
```

Expected:

```text
FAILED tests/test_audit_truth.py::test_trace_reports_a_drop_when_another_survivor_never_had_the_id
FAILED tests/test_audit_truth.py::test_trace_dropped_ids_are_reported_in_input_order
2 failed, 4 passed
```

The four that pass are guards: they pin that a stage which only strips ids, or that adds id-less records, still reports nothing it cannot prove (a fix that reports every unmatched id would break them).

- [ ] **Step 2.3: Fix the attribution**

In `contexel/trace.py`, replace this block:
<!-- OP replace-old path=contexel/trace.py -->
```python
            remaining: dict = {}
            unidentified = 0  # surviving records without the id field
            for r in out:
                if isinstance(r, dict) and fid in r:
```
with:
<!-- OP replace-new -->
```python
            remaining: dict = {}
            unidentified_out = 0  # surviving records without the id field
            for r in out:
                if isinstance(r, dict) and fid in r:
```

In `contexel/trace.py`, replace this block:
<!-- OP replace-old path=contexel/trace.py -->
```python
                    remaining[key] = remaining.get(key, 0) + 1
                else:
                    unidentified += 1
            for r in records:
                if isinstance(r, dict) and fid in r:
```
with:
<!-- OP replace-new -->
```python
                    remaining[key] = remaining.get(key, 0) + 1
                else:
                    unidentified_out += 1
            unidentified_in = 0  # input records that never had the id field
            unmatched: list = []  # input ids with no surviving record
            for r in records:
                if isinstance(r, dict) and fid in r:
```

In `contexel/trace.py`, replace this block:
<!-- OP replace-old path=contexel/trace.py -->
```python
                    if remaining.get(key, 0) > 0:
                        remaining[key] -= 1
                    elif unidentified > 0:
                        # a survivor lost the id field (e.g. select dropped
                        # it) — that is not a dropped record
                        unidentified -= 1
                    else:
                        dropped.append(original)
        tr._add(getattr(fn, "__name__", "stage"),
                before_n, len(out), before_tok, tokens.count(out), dropped)
```
with:
<!-- OP replace-new -->
```python
                    if remaining.get(key, 0) > 0:
                        remaining[key] -= 1
                    else:
                        unmatched.append(original)
                else:
                    unidentified_in += 1
            # A survivor can lose its id (select drops the field), and that is
            # not a drop. Only the id-less survivors the stage ADDED beyond the
            # id-less records it was given can be that, so at most ``lost``
            # unmatched ids are explained away; every other one is reported
            # dropped. (Black-box stages leave which ones ambiguous: the first
            # ``lost`` in input order are the ones absorbed.)
            lost = max(0, unidentified_out - unidentified_in)
            dropped = unmatched[lost:]
        tr._add(getattr(fn, "__name__", "stage"),
                before_n, len(out), before_tok, tokens.count(out), dropped)
```

- [ ] **Step 2.4: Run the tests and the whole Python suite**

```bash
PYTHONPATH=. python -m pytest -q tests/test_audit_truth.py tests/test_plane.py tests/test_controls.py tests/test_injection_controls.py
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
```

Expected:

```text
107 passed
485 passed
```

`test_trace_no_phantom_drops_when_select_strips_id_field` in `tests/test_plane.py` must stay green unchanged.

- [ ] **Step 2.5: Commit**

```bash
git add tests/test_audit_truth.py contexel/trace.py
git commit -m "fix(py): report a drop that an id-less record used to hide"
```


---

### Task 3: Shared vectors for dropped ids, and the same fix in TypeScript and C#

**Acceptance criteria:** AC 28 (all three languages, held together by the shared vectors)

**Files:**
- Modify: `parity/parity_cases.py`, regenerate `parity/vectors.json`
- Modify: `ts/src/trace.ts`, `ts/test/runner.ts`, `ts/test/runner.test.ts`, `ts/package.json`; create `ts/test/audit.test.ts`
- Modify: `csharp/Contexel/Trace.cs`, `csharp/Contexel.Tests/CaseTests.cs`, `csharp/Contexel.Tests/RunnerTests.cs`; create `csharp/Contexel.Tests/AuditTruthTests.cs`

**Interfaces:**
- Consumes: Task 2's canon behavior.
- Produces: a new vector case kind `trace_dropped_ids` (args `stages` + `id_field`; expect = the `dropped_ids` list of each traced stage, in stage order). Seven cases: four that fail on the old code in at least one port, three guards (falsy ids `0` and `""`, a duplicated id, a list-valued id).
- C# counts a `null` item as id-less on both sides (the one non-mapping item C# can hold) instead of throwing `NullReferenceException`, so the accounting is defined the same way as Python's and TypeScript's.

- [ ] **Step 3.1: Add the case kind and the cases to the generator**

In `parity/parity_cases.py`, replace this block:
<!-- OP replace-old path=parity/parity_cases.py -->
```python
Kinds: the eight record stages, ``merge`` (input = list of sources),
``pipeline`` / ``shaped`` (args.stages = [{"stage", "args"}, ...]), and
``trace_report`` (args.stages + optional args.id_field; expect = report text).
Callable-valued arguments cannot be JSON: those stay hand-written edge vectors.
"""
```
with:
<!-- OP replace-new -->
```python
Kinds: the eight record stages, ``merge`` (input = list of sources),
``pipeline`` / ``shaped`` (args.stages = [{"stage", "args"}, ...]), and
``trace_report`` (args.stages + optional args.id_field; expect = report text) and
``trace_dropped_ids`` (args.stages + args.id_field; expect = the ``dropped_ids`` of
each traced stage, in stage order).
Callable-valued arguments cannot be JSON: those stay hand-written edge vectors.
"""
```

In `parity/parity_cases.py`, replace this block:
<!-- OP replace-old path=parity/parity_cases.py -->
```python
            _pipe(args["stages"])(records)
        return t.report()
    raise ValueError(f"unknown case kind {kind!r}")
```
with:
<!-- OP replace-new -->
```python
            _pipe(args["stages"])(records)
        return t.report()
    if kind == "trace_dropped_ids":
        with trace(id_field=args["id_field"]) as t:
            _pipe(args["stages"])(records)
        return [stage_entry["dropped_ids"] for stage_entry in t.audit()["stages"]]
    raise ValueError(f"unknown case kind {kind!r}")
```

In `parity/parity_cases.py`, replace this block:
<!-- OP replace-old path=parity/parity_cases.py -->
```python
        {"patterns": ["alpha None beta"]},
        [{"snippet": {"beta": None, "alpha": None}}, {"snippet": "fine"}])
    return cases
```
with:
<!-- OP replace-new -->
```python
        {"patterns": ["alpha None beta"]},
        [{"snippet": {"beta": None, "alpha": None}}, {"snippet": "fine"}])

    # --- Slice 3: trace attribution (ADR-008, brief AC 28) ---
    # expect = each traced stage's dropped_ids, in stage order. A record that
    # never had the id field must not hide a real drop, and a stage that only
    # strips the id from its survivors drops nothing.
    add("trace_dropped_ids/drop_beside_a_record_without_the_id", "trace_dropped_ids",
        {"id_field": "id",
         "stages": [{"stage": "allowlist",
                     "args": {"field": "t", "allowed": ["y", "z"]}}]},
        [{"id": "a", "t": "x"}, {"t": "y"}, {"id": "b", "t": "z"}])
    add("trace_dropped_ids/select_stripping_ids_is_not_a_drop", "trace_dropped_ids",
        {"id_field": "id",
         "stages": [{"stage": "select", "args": {"fields": ["title"]}}]},
        [{"id": "a", "title": "x"}, {"title": "y"}, {"id": "b", "title": "z"}])
    add("trace_dropped_ids/each_stage_is_attributed_on_its_own", "trace_dropped_ids",
        {"id_field": "id",
         "stages": [{"stage": "allowlist", "args": {"field": "t", "allowed": ["y"]}},
                    {"stage": "select", "args": {"fields": ["title"]}}]},
        [{"id": "a", "t": "x", "title": "A"}, {"id": "b", "t": "y", "title": "B"},
         {"t": "y", "title": "C"}])
    add("trace_dropped_ids/dropped_ids_keep_input_order", "trace_dropped_ids",
        {"id_field": "id",
         "stages": [{"stage": "allowlist", "args": {"field": "k", "allowed": ["keep"]}}]},
        [{"id": 1, "k": "drop"}, {"k": "keep"}, {"id": 3, "k": "drop"},
         {"id": 4, "k": "keep"}])
    # falsy, duplicated and list-valued ids are ids like any other
    keep_only = {"id_field": "id", "stages": [
        {"stage": "allowlist", "args": {"field": "k", "allowed": ["keep"]}}]}
    add("trace_dropped_ids/falsy_ids_are_reported", "trace_dropped_ids", keep_only,
        [{"id": 0, "k": "drop"}, {"id": "", "k": "drop"}, {"id": "x", "k": "keep"}])
    add("trace_dropped_ids/a_duplicate_id_reports_the_dropped_copy",
        "trace_dropped_ids", keep_only,
        [{"id": "a", "k": "keep"}, {"id": "a", "k": "drop"}])
    add("trace_dropped_ids/list_ids_are_attributed", "trace_dropped_ids", keep_only,
        [{"id": ["a", 1], "k": "keep"}, {"id": ["b", 2], "k": "drop"}])
    return cases
```

- [ ] **Step 3.2: Regenerate the vectors and check them**

```bash
PYTHONPATH=. python parity/generate_vectors.py
python -c "import json; v=json.load(open('parity/vectors.json',encoding='utf-8')); print(len(v['cases']), sum('expect_error' in c for c in v['cases']), v['_meta']['case_count'])"
tr -cd '\r' < parity/vectors.json | wc -c
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
```

Expected:

```text
77 31 77
0
492 passed
```

(70 cases before; the 31 error cases are unchanged; the file must contain no carriage return.) Run the generator as shown: without `PYTHONPATH=.` a stale installed `contexel` shadows the checkout.

- [ ] **Step 3.3: TypeScript: the runner kind and the audit tests (still failing)**

In `ts/test/runner.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.ts -->
```typescript
  shaped: ["stages"],
  trace_report: ["stages", "id_field"],
};
```
with:
<!-- OP replace-new -->
```typescript
  shaped: ["stages"],
  trace_report: ["stages", "id_field"],
  trace_dropped_ids: ["stages", "id_field"],
};
```

In `ts/test/runner.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.ts -->
```typescript
/** Throw unless `spec` is a known stage kind whose arguments are all known —
 * and, for pipeline/shaped/trace_report, so is every nested stage spec. */
export function validateSpec(spec: Spec, where: string): void {
  assert.ok(
```
with:
<!-- OP replace-new -->
```typescript
/** Throw unless `spec` is a known stage kind whose arguments are all known —
 * and, for pipeline/shaped/trace_report/trace_dropped_ids, so is every nested
 * stage spec. */
export function validateSpec(spec: Spec, where: string): void {
  assert.ok(
```

In `ts/test/runner.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.ts -->
```typescript
      return tr.report();
    }
    default:
      throw new Error(`unknown case kind ${c.stage}`);
```
with:
<!-- OP replace-new -->
```typescript
      return tr.report();
    }
    case "trace_dropped_ids": {
      const [, tr] = trace({ idField: c.args.id_field as string }, () =>
        build(stages)(records)
      );
      return (tr.audit().stages as { dropped_ids: unknown[] }[]).map((e) => e.dropped_ids);
    }
    default:
      throw new Error(`unknown case kind ${c.stage}`);
```

In `ts/test/runner.test.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.test.ts -->
```typescript
  assert.deepStrictEqual(
    Object.keys(ARG_NAMES).sort(),
    [...Object.keys(RECORD_STAGES), "merge", "pipeline", "shaped", "trace_report"].sort()
  );
});
```
with:
<!-- OP replace-new -->
```typescript
  assert.deepStrictEqual(
    Object.keys(ARG_NAMES).sort(),
    [
      ...Object.keys(RECORD_STAGES),
      "merge",
      "pipeline",
      "shaped",
      "trace_report",
      "trace_dropped_ids",
    ].sort()
  );
});
```

In `ts/test/runner.test.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.test.ts -->
```typescript
});

for (const kind of ["pipeline", "shaped", "trace_report"]) {
  test(`an unknown argument inside a nested ${kind} stage spec is rejected`, () => {
    const c = base({
```
with:
<!-- OP replace-new -->
```typescript
});

for (const kind of ["pipeline", "shaped", "trace_report", "trace_dropped_ids"]) {
  test(`an unknown argument inside a nested ${kind} stage spec is rejected`, () => {
    const c = base({
```

Create `ts/test/audit.test.ts` with exactly this content (it ends with one newline):
<!-- OP create path=ts/test/audit.test.ts -->
```typescript
/**
 * Audit truthfulness (ADR-008, brief AC 28-30): the trail must not
 * under-report. Mirrors tests/test_audit_truth.py.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { allowlist, select, trace, type Records } from "../src/index.js";
import { traced } from "../src/trace.js";

/** Run one stage under a trace; return its output and recorded dropped ids. */
function drops(
  records: Records,
  stageFn: (records: Records) => Records,
  idField = "id"
): [Records, unknown[]] {
  const [out, tr] = trace({ idField }, () => stageFn(records));
  const stages = tr.audit().stages as { dropped_ids: unknown[] }[];
  return [out, stages[0].dropped_ids];
}

// --- AC 28: dropped_ids -----------------------------------------------------

test("trace reports a drop when another survivor never had the id", () => {
  // "a" is dropped. The record without an id was in the input already, so it
  // is not evidence that a survivor lost its id: "a" must be reported.
  const records: Records = [{ id: "a", t: "x" }, { t: "y" }, { id: "b", t: "z" }];
  const [out, dropped] = drops(records, (r) => allowlist(r, { field: "t", allowed: ["y", "z"] }));
  assert.deepEqual(
    out.map((r) => r.t),
    ["y", "z"]
  );
  assert.deepEqual(dropped, ["a"]);
});

test("trace: select stripping ids is not a drop", () => {
  const records: Records = [0, 1, 2].map((i) => ({ id: `u${i}`, title: `t${i}` }));
  const [out, dropped] = drops(records, (r) => select(r, { fields: ["title"] }));
  assert.equal(out.length, 3);
  assert.deepEqual(dropped, []);
});

test("trace: a mixed input with select stripping ids is not a drop", () => {
  const records: Records = [{ id: "a", title: "x" }, { title: "y" }, { id: "b", title: "z" }];
  const [out, dropped] = drops(records, (r) => select(r, { fields: ["title"] }));
  assert.equal(out.length, 3);
  assert.deepEqual(dropped, []);
});

test("trace: the ambiguity is bounded by the lost count", () => {
  // The stage keeps "a" with its id, keeps one record WITHOUT an id and
  // discards two. Only ONE id can be explained by a stripped survivor.
  const keepAAndOneStripped = (records: Records): Records => [records[0], { title: "stripped" }];
  const records: Records = [
    { id: "a", title: "1" },
    { id: "b", title: "2" },
    { id: "c", title: "3" },
  ];
  const [out, dropped] = drops(records, traced("keep_a_and_one_stripped", keepAAndOneStripped));
  assert.equal(out.length, 2);
  assert.deepEqual(dropped, ["c"]);
});

test("trace: a stage that adds id-less records never hides more than it added", () => {
  const addTwoDropB = (records: Records): Records => [records[0], { n: 1 }, { n: 2 }];
  const [, dropped] = drops([{ id: "a" }, { id: "b" }], traced("add_two_drop_b", addTwoDropB));
  assert.deepEqual(dropped, []);
});

test("trace: dropped ids are reported in input order", () => {
  const records: Records = [
    { id: 1, k: "drop" },
    { k: "keep" },
    { id: 3, k: "drop" },
    { id: 4, k: "keep" },
  ];
  const [, dropped] = drops(records, (r) => allowlist(r, { field: "k", allowed: ["keep"] }));
  assert.deepEqual(dropped, [1, 3]);
});
```

In `ts/package.json`, replace this block:
<!-- OP replace-old path=ts/package.json -->
```json
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "test": "tsc -p tsconfig.test.json && node --test dist-test/test/parity.test.js dist-test/test/behavior.test.js dist-test/test/cases.test.js dist-test/test/errors.test.js dist-test/test/strict.test.js dist-test/test/controls.test.js dist-test/test/config.test.js dist-test/test/runner.test.js dist-test/test/docs.test.js dist-test/test/fingerprint.test.js",
    "prepublishOnly": "npm run build && npm test"
  },
```
with:
<!-- OP replace-new -->
```json
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "test": "tsc -p tsconfig.test.json && node --test dist-test/test/parity.test.js dist-test/test/behavior.test.js dist-test/test/cases.test.js dist-test/test/errors.test.js dist-test/test/strict.test.js dist-test/test/controls.test.js dist-test/test/config.test.js dist-test/test/runner.test.js dist-test/test/docs.test.js dist-test/test/fingerprint.test.js dist-test/test/audit.test.js",
    "prepublishOnly": "npm run build && npm test"
  },
```

- [ ] **Step 3.4: Run the TypeScript suite and watch five fail**

```bash
cd ts && npm run build && npm test
```

Expected:

```text
✖ case trace_dropped_ids/drop_beside_a_record_without_the_id
✖ case trace_dropped_ids/dropped_ids_keep_input_order
✖ case trace_dropped_ids/each_stage_is_attributed_on_its_own
✖ trace reports a drop when another survivor never had the id
✖ trace: dropped ids are reported in input order
ℹ fail 5
```

- [ ] **Step 3.5: TypeScript: fix the attribution**

In `ts/src/trace.ts`, replace this block:
<!-- OP replace-old path=ts/src/trace.ts -->
```typescript
    const beforeTok = tokens.count(records);
    const out = fn(records, ...args);
    const dropped: unknown[] = [];
    const fid = tr.idField;
    if (fid) {
      const remaining = new Map<unknown, number>();
      let unidentified = 0; // survivors without the id field absorb drops
      for (const r of out) {
        if (r !== null && typeof r === "object" && Object.hasOwn(r, fid)) {
```
with:
<!-- OP replace-new -->
```typescript
    const beforeTok = tokens.count(records);
    const out = fn(records, ...args);
    let dropped: unknown[] = [];
    const fid = tr.idField;
    if (fid) {
      const remaining = new Map<unknown, number>();
      let unidentifiedOut = 0; // surviving records without the id field
      for (const r of out) {
        if (r !== null && typeof r === "object" && Object.hasOwn(r, fid)) {
```

In `ts/src/trace.ts`, replace this block:
<!-- OP replace-old path=ts/src/trace.ts -->
```typescript
          remaining.set(k, (remaining.get(k) ?? 0) + 1);
        } else {
          unidentified++;
        }
      }
      for (const r of records) {
        if (r !== null && typeof r === "object" && Object.hasOwn(r, fid)) {
```
with:
<!-- OP replace-new -->
```typescript
          remaining.set(k, (remaining.get(k) ?? 0) + 1);
        } else {
          unidentifiedOut++;
        }
      }
      let unidentifiedIn = 0; // input records that never had the id field
      const unmatched: unknown[] = []; // input ids with no surviving record
      for (const r of records) {
        if (r !== null && typeof r === "object" && Object.hasOwn(r, fid)) {
```

In `ts/src/trace.ts`, replace this block:
<!-- OP replace-old path=ts/src/trace.ts -->
```typescript
          const left = remaining.get(k) ?? 0;
          if (left > 0) remaining.set(k, left - 1);
          else if (unidentified > 0) unidentified--;
          else dropped.push(original);
        }
      }
    }
    tr.entries.push({
```
with:
<!-- OP replace-new -->
```typescript
          const left = remaining.get(k) ?? 0;
          if (left > 0) remaining.set(k, left - 1);
          else unmatched.push(original);
        } else {
          unidentifiedIn++;
        }
      }
      // A survivor can lose its id (select drops the field), and that is not a
      // drop. Only the id-less survivors the stage ADDED beyond the id-less
      // records it was given can be that, so at most `lost` unmatched ids are
      // explained away; every other one is reported dropped (the first `lost`
      // in input order are the ones absorbed).
      const lost = Math.max(0, unidentifiedOut - unidentifiedIn);
      dropped = unmatched.slice(lost);
    }
    tr.entries.push({
```

- [ ] **Step 3.6: Run the TypeScript suite**

```bash
cd ts && npm run build && npm test
```

Expected:

```text
ℹ tests 337 / ℹ pass 337 / ℹ fail 0
```

- [ ] **Step 3.7: C#: the runner kind and the audit tests (still failing)**

In `csharp/Contexel.Tests/CaseTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/CaseTests.cs -->
```csharp
        ["shaped"] = ["stages"],
        ["trace_report"] = ["stages", "id_field"],
    };

    private static readonly HashSet<string> NestingKinds = ["pipeline", "shaped", "trace_report"];
    private static readonly HashSet<string> SpecKeys = ["stage", "args"];

    /// <summary>Reject an unknown option name in a case's args and, for
    /// pipeline/shaped/trace_report, in every nested stage spec.</summary>
    internal static void ValidateArgs(string kind, Rec args, string where)
    {
```
with:
<!-- OP replace-new -->
```csharp
        ["shaped"] = ["stages"],
        ["trace_report"] = ["stages", "id_field"],
        ["trace_dropped_ids"] = ["stages", "id_field"],
    };

    private static readonly HashSet<string> NestingKinds =
        ["pipeline", "shaped", "trace_report", "trace_dropped_ids"];
    private static readonly HashSet<string> SpecKeys = ["stage", "args"];

    /// <summary>Reject an unknown option name in a case's args and, for
    /// pipeline/shaped/trace_report/trace_dropped_ids, in every nested stage
    /// spec.</summary>
    internal static void ValidateArgs(string kind, Rec args, string where)
    {
```

In `csharp/Contexel.Tests/CaseTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/CaseTests.cs -->
```csharp
                return t.Report();
            }
            default:
                throw new ArgumentException($"unknown case kind {kind}");
```
with:
<!-- OP replace-new -->
```csharp
                return t.Report();
            }
            case "trace_dropped_ids":
            {
                using var t = Trace.Begin((string)args["id_field"]!);
                Build(args).Run(Input(c));
                return ((List<object?>)t.Audit()["stages"]!)
                    .Select(s => ((Rec)s!)["dropped_ids"]).ToList();
            }
            default:
                throw new ArgumentException($"unknown case kind {kind}");
```

In `csharp/Contexel.Tests/RunnerTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/RunnerTests.cs -->
```csharp
    [InlineData("shaped")]
    [InlineData("trace_report")]
    public void AnUnknownArgKeyInANestedStageSpecIsRejected(string wrapper)
    {
```
with:
<!-- OP replace-new -->
```csharp
    [InlineData("shaped")]
    [InlineData("trace_report")]
    [InlineData("trace_dropped_ids")]
    public void AnUnknownArgKeyInANestedStageSpecIsRejected(string wrapper)
    {
```

Create `csharp/Contexel.Tests/AuditTruthTests.cs` with exactly this content (it ends with one newline):
<!-- OP create path=csharp/Contexel.Tests/AuditTruthTests.cs -->
```csharp
using Xunit;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>Audit truthfulness (ADR-008, brief AC 28-30): the trail must not
/// under-report. Mirrors tests/test_audit_truth.py.</summary>
public class AuditTruthTests
{
    private static Rec R(params (string Key, object? Value)[] fields)
    {
        var r = new Rec();
        foreach (var (key, value) in fields) r[key] = value;
        return r;
    }

    /// <summary>Run one stage under a trace; return its recorded dropped ids.</summary>
    private static List<object?> Drops(Func<Records> stage)
    {
        using var t = Trace.Begin("id");
        stage();
        var stages = (List<object?>)t.Audit()["stages"]!;
        return (List<object?>)((Rec)stages[0]!)["dropped_ids"]!;
    }

    [Fact]
    public void TraceReportsADropWhenAnotherSurvivorNeverHadTheId()
    {
        Records records = [R(("id", "a"), ("t", "x")), R(("t", "y")), R(("id", "b"), ("t", "z"))];
        var dropped = Drops(() => Stages.Allowlist(records, "t", new List<object?> { "y", "z" }));
        Assert.Equal(new object?[] { "a" }, dropped);
    }

    [Fact]
    public void TraceSelectStrippingIdsIsNotADrop()
    {
        Records records = [R(("id", "u0"), ("title", "t0")), R(("id", "u1"), ("title", "t1")),
                           R(("id", "u2"), ("title", "t2"))];
        Assert.Empty(Drops(() => Stages.Select(records, new[] { "title" })));
    }

    [Fact]
    public void TraceMixedInputWithSelectStrippingIdsIsNotADrop()
    {
        Records records = [R(("id", "a"), ("title", "x")), R(("title", "y")),
                           R(("id", "b"), ("title", "z"))];
        Assert.Empty(Drops(() => Stages.Select(records, new[] { "title" })));
    }

    [Fact]
    public void TraceAmbiguityIsBoundedByTheLostCount()
    {
        // The stage keeps "a" with its id, keeps one record WITHOUT an id and
        // discards two. Only ONE id can be explained by a stripped survivor.
        Records records = [R(("id", "a"), ("title", "1")), R(("id", "b"), ("title", "2")),
                           R(("id", "c"), ("title", "3"))];
        var dropped = Drops(() => Trace.Traced("keep_a_and_one_stripped", records,
            () => [records[0], R(("title", "stripped"))]));
        Assert.Equal(new object?[] { "c" }, dropped);
    }

    [Fact]
    public void TraceAStageThatAddsIdlessRecordsNeverHidesMoreThanItAdded()
    {
        Records records = [R(("id", "a")), R(("id", "b"))];
        var dropped = Drops(() => Trace.Traced("add_two_drop_b", records,
            () => [records[0], R(("n", 1L)), R(("n", 2L))]));
        Assert.Empty(dropped);
    }

    [Fact]
    public void TraceDroppedIdsAreReportedInInputOrder()
    {
        Records records = [R(("id", 1L), ("k", "drop")), R(("k", "keep")),
                           R(("id", 3L), ("k", "drop")), R(("id", 4L), ("k", "keep"))];
        var dropped = Drops(() => Stages.Allowlist(records, "k", new List<object?> { "keep" }));
        Assert.Equal(new object?[] { 1L, 3L }, dropped);
    }

    [Fact]
    public void TraceCountsANullItemAsIdlessInsteadOfFailing()
    {
        // a null item (the one non-mapping item C# can hold) has no id: it is
        // unidentified on both sides, so the drop of "a" is still reported
        Records records = [R(("id", "a")), null!, R(("id", "b"))];
        var dropped = Drops(() => Trace.Traced("keep_b_and_null", records,
            () => [records[1], records[2]]));
        Assert.Equal(new object?[] { "a" }, dropped);
    }
}
```

- [ ] **Step 3.8: Run the C# suite and watch six fail**

```bash
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
```

Expected:

```text
Failed Contexel.Tests.CaseTests.CaseMatchesPython(id: "trace_dropped_ids/drop_beside_a_record_without_the"...)
Failed Contexel.Tests.CaseTests.CaseMatchesPython(id: "trace_dropped_ids/dropped_ids_keep_input_order")
Failed Contexel.Tests.CaseTests.CaseMatchesPython(id: "trace_dropped_ids/each_stage_is_attributed_on_its_...")
Failed Contexel.Tests.AuditTruthTests.TraceReportsADropWhenAnotherSurvivorNeverHadTheId
Failed Contexel.Tests.AuditTruthTests.TraceDroppedIdsAreReportedInInputOrder
Failed Contexel.Tests.AuditTruthTests.TraceCountsANullItemAsIdlessInsteadOfFailing
Failed!  - Failed: 6, Passed: 296, Skipped: 0, Total: 302
```

- [ ] **Step 3.9: C#: fix the attribution**

In `csharp/Contexel/Trace.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel/Trace.cs -->
```csharp
        {
            var remaining = new Dictionary<string, int>();
            int unidentified = 0; // survivors without the id field absorb drops
            foreach (var r in output)
            {
                if (r.TryGetValue(fid, out var v))
                {
                    string k = IdKey(v);
                    remaining[k] = remaining.GetValueOrDefault(k) + 1;
                }
                else unidentified++;
            }
            foreach (var r in records)
            {
                if (r.TryGetValue(fid, out var original))
                {
                    string k = IdKey(original);
                    int left = remaining.GetValueOrDefault(k);
                    if (left > 0) remaining[k] = left - 1;
                    else if (unidentified > 0) unidentified--;
                    else dropped.Add(original);
                }
            }
        }
        tr.Entries.Add(new Entry(name, beforeN, output.Count, beforeTok,
```
with:
<!-- OP replace-new -->
```csharp
        {
            var remaining = new Dictionary<string, int>();
            int unidentifiedOut = 0; // surviving records without the id field
            foreach (var r in output)
            {
                if (r is not null && r.TryGetValue(fid, out var v))
                {
                    string k = IdKey(v);
                    remaining[k] = remaining.GetValueOrDefault(k) + 1;
                }
                else unidentifiedOut++;
            }
            int unidentifiedIn = 0; // input records that never had the id field
            var unmatched = new List<object?>(); // input ids with no surviving record
            foreach (var r in records)
            {
                if (r is not null && r.TryGetValue(fid, out var original))
                {
                    string k = IdKey(original);
                    int left = remaining.GetValueOrDefault(k);
                    if (left > 0) remaining[k] = left - 1;
                    else unmatched.Add(original);
                }
                else unidentifiedIn++;
            }
            // A survivor can lose its id (select drops the field), and that is
            // not a drop. Only the id-less survivors the stage ADDED beyond the
            // id-less records it was given can be that, so at most `lost`
            // unmatched ids are explained away; every other one is reported
            // dropped (the first `lost` in input order are the ones absorbed).
            int lost = Math.Max(0, unidentifiedOut - unidentifiedIn);
            dropped.AddRange(unmatched.Skip(lost));
        }
        tr.Entries.Add(new Entry(name, beforeN, output.Count, beforeTok,
```

- [ ] **Step 3.10: Run the C# suite**

```bash
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
```

Expected:

```text
Passed!  - Failed: 0, Passed: 302, Skipped: 0, Total: 302   (0 warnings)
```

- [ ] **Step 3.11: Commit**

```bash
git add parity/parity_cases.py parity/vectors.json ts csharp
git status --short           # only the files named in this task
git commit -m "fix: report dropped ids that an id-less record hid (ts, cs, vectors)"
```


---

### Task 4: Python fingerprints cover what shaped the output, and cannot go stale

**Acceptance criteria:** AC 29 (sets, nested pipelines, tiktoken encodings), AC 30 (snapshot at build)

**Files:**
- Modify: `contexel/pipeline.py`, `contexel/tokens.py`, `tests/test_audit_truth.py`

**Interfaces:**
- Consumes: Task 1's golden baselines (must stay green); Task 2's test file.
- Produces: `_stable_repr` renders a `set` or `frozenset` as `set{...}` of its sorted element reprs (hash-seed independent; the same for both types, different from a list or dict); `pipeline()` sets `__contexel_desc__ = ("pipeline", (fingerprint,))` on its returned callable so an outer pipeline hashes the inner fingerprint instead of `run`; `_snapshot` (private) copies exact `list`, `tuple`, `dict`, `set` values recursively and returns anything else (including a subclass, a custom object, a `frozenset` and a callable) as it is; `stage()` binds the snapshot and fingerprints the snapshot; `pipeline()` copies its list of stages; `tiktoken_tokenizer` returns a named function whose `__name__` is `tiktoken:<model or encoding>`.
- No public name is added or removed.

- [ ] **Step 4.1: Write the failing tests**

In `tests/test_audit_truth.py`, replace this block:
<!-- OP replace-old path=tests/test_audit_truth.py -->
```python
Each test here pins one way the audit used to say something false.
"""
from contexel import allowlist, select, trace
from contexel.trace import traced
```
with:
<!-- OP replace-new -->
```python
Each test here pins one way the audit used to say something false.
"""
import os
import subprocess
import sys
import types

import pytest

from contexel import (allowlist, dedupe, pipeline, select, stage, tokens,
                      trace, truncate_field)
from contexel.trace import traced

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```

In `tests/test_audit_truth.py`, replace this block:
<!-- OP replace-old path=tests/test_audit_truth.py -->
```python
    assert dropped == [1, 3]
```
with:
<!-- OP replace-new -->
```python
    assert dropped == [1, 3]


# --- AC 29: what the fingerprint covers -----------------------------------

def _fp(*stages):
    return pipeline(list(stages)).fingerprint


def test_fingerprint_differs_for_set_contents():
    a = _fp(stage(allowlist, field="s", allowed={"a"}))
    b = _fp(stage(allowlist, field="s", allowed={"b"}))
    assert a != b


def test_fingerprint_of_a_set_ignores_insertion_order_and_set_type():
    ab = _fp(stage(allowlist, field="s", allowed={"a", "b"}))
    ba = _fp(stage(allowlist, field="s", allowed={"b", "a"}))
    frozen = _fp(stage(allowlist, field="s", allowed=frozenset({"a", "b"})))
    assert ab == ba == frozen


def test_fingerprint_of_a_set_is_not_that_of_a_list_or_a_dict():
    as_set = _fp(stage(allowlist, field="s", allowed={"a"}))
    as_list = _fp(stage(allowlist, field="s", allowed=["a"]))
    as_dict = _fp(stage(allowlist, field="s", allowed={"a": 1}))
    assert len({as_set, as_list, as_dict}) == 3


def test_fingerprint_of_a_set_is_the_same_under_every_hash_seed():
    code = """
import sys
sys.path.insert(0, %r)
from contexel import allowlist, pipeline, stage
names = {'alpha', 2, None, (1, 2), 2.5, frozenset({'x', 'y'}), 'k1', 'k2'}
print(pipeline([stage(allowlist, field='s', allowed=names)]).fingerprint)
""" % ROOT
    seen = set()
    for seed in ("0", "1", "2", "4242"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, "-c", code], env=env,
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        seen.add(proc.stdout.strip())
    assert len(seen) == 1, seen


def test_a_set_nested_in_a_list_or_dict_is_covered_too():
    assert (_fp(stage(allowlist, field="s", allowed=[1, {"a", "b"}]))
            != _fp(stage(allowlist, field="s", allowed=[1, {"a", "c"}])))
    assert (_fp(stage(allowlist, field="s", allowed={"k": {"a"}}))
            != _fp(stage(allowlist, field="s", allowed={"k": {"b"}})))
    assert (_fp(stage(allowlist, field="s", allowed=[{"b", "a"}]))
            == _fp(stage(allowlist, field="s", allowed=[{"a", "b"}])))


def test_fingerprint_differs_for_nested_pipelines():
    inner_a = pipeline([stage(select, fields=["a"])])
    inner_b = pipeline([stage(select, fields=["b"])])
    outer_a = pipeline([inner_a, stage(dedupe, key="a")])
    outer_b = pipeline([inner_b, stage(dedupe, key="a")])
    same_as_a = pipeline([pipeline([stage(select, fields=["a"])]),
                          stage(dedupe, key="a")])
    assert outer_a.fingerprint != outer_b.fingerprint
    assert outer_a.fingerprint == same_as_a.fingerprint


def test_a_nested_pipeline_still_runs_its_stages():
    inner = pipeline([stage(select, fields=["a"])])
    out = pipeline([inner, stage(dedupe, key="a")])([{"a": 1, "b": 2}, {"a": 1}])
    assert out == [{"a": 1}]


class _FakeEncoding:
    """One 'token' per character; remembers how it was called."""

    def __init__(self):
        self.kwargs = []

    def encode(self, text, **kwargs):
        self.kwargs.append(kwargs)
        return list(text)


@pytest.fixture
def fake_tiktoken(monkeypatch):
    enc = _FakeEncoding()
    module = types.ModuleType("tiktoken")
    module.get_encoding = lambda name: enc
    module.encoding_for_model = lambda model: enc
    monkeypatch.setitem(sys.modules, "tiktoken", module)
    return enc


def test_fingerprint_differs_for_tiktoken_encodings(fake_tiktoken):
    def fp(tok):
        return _fp(stage(truncate_field, field="s", max_tokens=5, tokenizer=tok))

    cl = tokens.tiktoken_tokenizer("cl100k_base")
    o2 = tokens.tiktoken_tokenizer("o200k_base")
    again = tokens.tiktoken_tokenizer("cl100k_base")
    assert cl.__name__ == "tiktoken:cl100k_base"
    assert tokens.tiktoken_tokenizer(model="gpt-4o").__name__ == "tiktoken:gpt-4o"
    assert fp(cl) != fp(o2)
    assert fp(cl) == fp(again)


# --- AC 30: a policy cannot change behavior without changing its fingerprint -

def test_bound_container_mutation_cannot_change_behavior():
    allowed = ["a"]
    pipe = pipeline([stage(allowlist, field="s", allowed=allowed)])
    before = pipe.fingerprint
    allowed.append("b")  # the caller changes THEIR list afterwards
    out = pipe([{"s": "a"}, {"s": "b"}])
    assert [r["s"] for r in out] == ["a"]
    assert pipe.fingerprint == before


def _probe(records, config):
    """A custom stage that reports exactly what it was bound to."""
    return [{"config": repr(config)}]


def test_nested_bound_containers_are_copied_at_every_depth():
    names = ["a"]
    inner = ["z"]
    config = {"names": names, "pair": (1, inner), "tags": {"t"}, "n": {"deep": [names]}}
    probe = stage(_probe, config=config)
    pipe = pipeline([probe])
    expected, before = probe([]), pipe.fingerprint
    names.append("b")
    inner.append("y")
    config["tags"].add("u")
    config["n"]["deep"].append("v")
    config["extra"] = 1
    assert probe([]) == expected
    assert pipe.fingerprint == before


def test_pipeline_copies_its_list_of_stages():
    keep_a = stage(select, fields=["a"])
    stages = [keep_a]
    pipe = pipeline(stages)
    before = pipe.fingerprint
    stages.append(stage(select, fields=["b"]))
    stages[0] = stage(select, fields=["b"])
    assert pipe([{"a": 1, "b": 2}]) == [{"a": 1}]
    assert pipe.fingerprint == before


def test_a_callable_a_custom_object_and_a_list_subclass_are_not_copied():
    # documented limit: only plain containers are copied; anything else stays
    # live and is fingerprinted by its name or type name only
    class Box:
        pass

    class Tags(list):
        pass

    def by(r):
        return r["a"]

    box, tags = Box(), Tags(["x"])
    seen = {}

    def grab(records, **objects):
        seen.update(objects)
        return records

    stage(grab, key=by, box=box, tags=tags)([])
    assert seen["key"] is by
    assert seen["box"] is box
    assert seen["tags"] is tags


def test_a_stage_gets_the_same_private_copy_on_every_call():
    sizes = []

    def measure(records, names):
        sizes.append(len(names))
        return records

    names = ["a"]
    bound = stage(measure, names=names)
    bound([])
    names.append("b")
    bound([])
    assert sizes == [1, 1]
```

- [ ] **Step 4.2: Run them and watch nine fail**

```bash
PYTHONPATH=. python -m pytest -q tests/test_audit_truth.py
```

Expected:

```text
FAILED ...::test_fingerprint_differs_for_set_contents
FAILED ...::test_fingerprint_of_a_set_ignores_insertion_order_and_set_type
FAILED ...::test_a_set_nested_in_a_list_or_dict_is_covered_too
FAILED ...::test_fingerprint_differs_for_nested_pipelines
FAILED ...::test_fingerprint_differs_for_tiktoken_encodings
FAILED ...::test_bound_container_mutation_cannot_change_behavior
FAILED ...::test_nested_bound_containers_are_copied_at_every_depth
FAILED ...::test_pipeline_copies_its_list_of_stages
FAILED ...::test_a_stage_gets_the_same_private_copy_on_every_call
9 failed, 10 passed
```

(The AC 28 tests from Task 2 are the other six passing; of the new ones, `test_a_callable_a_custom_object_and_a_list_subclass_are_not_copied`, `test_a_nested_pipeline_still_runs_its_stages`, `test_fingerprint_of_a_set_is_not_that_of_a_list_or_a_dict` and the hash-seed test pass on the old code: they are guards that the change does not over-reach.)

- [ ] **Step 4.3: Implement**

In `contexel/pipeline.py`, replace this block:
<!-- OP replace-old path=contexel/pipeline.py -->
```python
:func:`contexel.trace` -- so an audit trail can say *which version of the
policy* shaped a given context. Coverage, precisely: primitives, lists,
tuples, and dicts are hashed by value; callables by ``__name__`` (distinct
lambdas collide as ``<lambda>`` -- name your key functions); any other object
contributes only its type name. Bind parameters through :func:`stage` when the
fingerprint should cover them; opaque stage callables contribute only their
``__name__``.
"""
from __future__ import annotations
```
with:
<!-- OP replace-new -->
```python
:func:`contexel.trace` -- so an audit trail can say *which version of the
policy* shaped a given context. Coverage, precisely: primitives, lists,
tuples, dicts, sets and frozensets are hashed by value (a set by its sorted
contents, so insertion order and the hash seed do not matter); a nested
:func:`pipeline` contributes its own fingerprint; callables are hashed by
``__name__`` (distinct lambdas collide as ``<lambda>`` -- name your key
functions; a tokenizer from :func:`contexel.tokens.tiktoken_tokenizer` is named
``tiktoken:<encoding or model>``); any other object contributes only its type
name. Bind parameters through :func:`stage` when the fingerprint should cover
them; opaque stage callables contribute only their ``__name__``.

The fingerprint cannot go stale: :func:`stage` takes a private copy of the
plain containers (``list``, ``tuple``, ``dict``, ``set``, ``frozenset``, at any
depth) bound to it, and :func:`pipeline` copies its list of stages, so changing
the caller's own list or dict afterwards changes neither the behavior nor the
fingerprint. Objects that are not plain containers (a subclass, a custom
class) are not copied: they stay live, and only their type name is hashed.
"""
from __future__ import annotations
```

In `contexel/pipeline.py`, replace this block:
<!-- OP replace-old path=contexel/pipeline.py -->
```python
            f"{k!r}:{_stable_repr(v)}" for k, v in items
        ) + "}"
    if callable(value):
        return getattr(value, "__name__", type(value).__name__)
```
with:
<!-- OP replace-new -->
```python
            f"{k!r}:{_stable_repr(v)}" for k, v in items
        ) + "}"
    if isinstance(value, (set, frozenset)):
        # Iteration order depends on the hash seed: hash the sorted contents.
        return "set{" + ",".join(sorted(_stable_repr(v) for v in value)) + "}"
    if callable(value):
        return getattr(value, "__name__", type(value).__name__)
```

In `contexel/pipeline.py`, replace this block:
<!-- OP replace-old path=contexel/pipeline.py -->
```python
def stage(fn: Callable, **kwargs: Any) -> StageFn:
    """Bind keyword args to a stage so it slots into a pipeline as a ``records -> records`` step."""

    def run(records: Records) -> Records:
        return fn(records, **kwargs)

    run.__name__ = getattr(fn, "__name__", "stage")
    run.__contexel_desc__ = (  # type: ignore[attr-defined]
        run.__name__,
        tuple(sorted((k, _stable_repr(v)) for k, v in kwargs.items())),
    )
    return run
```
with:
<!-- OP replace-new -->
```python
def _snapshot(value: Any) -> Any:
    """A private copy of the plain containers in ``value`` (any depth).

    Only an exact ``list``, ``tuple``, ``dict``, ``set`` or ``frozenset`` is
    copied (its elements recursively); everything else is returned as it is.
    """
    kind = type(value)
    if kind is list:
        return [_snapshot(v) for v in value]
    if kind is tuple:
        return tuple(_snapshot(v) for v in value)
    if kind is dict:
        return {k: _snapshot(v) for k, v in value.items()}
    if kind is set:
        return set(value)  # elements are hashable, so already immutable
    return value


def stage(fn: Callable, **kwargs: Any) -> StageFn:
    """Bind keyword args to a stage so it slots into a pipeline as a ``records -> records`` step.

    The stage keeps a private copy of any plain list, tuple, dict or set among
    the arguments, so changing the caller's own container afterwards cannot
    change what the stage does or what its fingerprint says.
    """
    bound = {k: _snapshot(v) for k, v in kwargs.items()}

    def run(records: Records) -> Records:
        return fn(records, **bound)

    run.__name__ = getattr(fn, "__name__", "stage")
    run.__contexel_desc__ = (  # type: ignore[attr-defined]
        run.__name__,
        tuple(sorted((k, _stable_repr(v)) for k, v in bound.items())),
    )
    return run
```

In `contexel/pipeline.py`, replace this block:
<!-- OP replace-old path=contexel/pipeline.py -->
```python
    """
    check_bool(strict, "pipeline", "strict")
    descs = tuple(
        getattr(s, "__contexel_desc__", (getattr(s, "__name__", "callable"),))
```
with:
<!-- OP replace-new -->
```python
    """
    check_bool(strict, "pipeline", "strict")
    stages = list(stages)  # a later change to the caller's list is not ours
    descs = tuple(
        getattr(s, "__contexel_desc__", (getattr(s, "__name__", "callable"),))
```

In `contexel/pipeline.py`, replace this block:
<!-- OP replace-old path=contexel/pipeline.py -->
```python
    run.fingerprint = fingerprint  # type: ignore[attr-defined]
    return run
```
with:
<!-- OP replace-new -->
```python
    run.fingerprint = fingerprint  # type: ignore[attr-defined]
    # as a stage of an outer pipeline, contribute this fingerprint (not "run")
    run.__contexel_desc__ = ("pipeline", (fingerprint,))  # type: ignore[attr-defined]
    return run
```

In `contexel/tokens.py`, replace this block:
<!-- OP replace-old path=contexel/tokens.py -->
```python
    enc = (tiktoken.encoding_for_model(model) if model
           else tiktoken.get_encoding(encoding))
    return lambda text: len(enc.encode(text))
```
with:
<!-- OP replace-new -->
```python
    enc = (tiktoken.encoding_for_model(model) if model
           else tiktoken.get_encoding(encoding))

    def count_tokens(text: str) -> int:
        return len(enc.encode(text))

    # distinct encodings must not share a policy fingerprint
    count_tokens.__name__ = f"tiktoken:{model or encoding}"
    return count_tokens
```

- [ ] **Step 4.4: Run the tests, the golden baseline and the whole suite**

```bash
PYTHONPATH=. python -m pytest -q tests/test_audit_truth.py tests/test_fingerprint_golden.py
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
```

Expected:

```text
35 passed
505 passed
```

`tests/test_fingerprint_golden.py` (all 16, including the Slice 1 baseline) must pass unchanged: a pipeline that binds none of a set, a nested pipeline or a tiktoken tokenizer keeps its exact fingerprint.

- [ ] **Step 4.5: Commit**

```bash
git add contexel/pipeline.py contexel/tokens.py tests/test_audit_truth.py
git commit -m "fix(py): fingerprint sets, nested pipelines, tiktoken; copy bound containers"
```


---

### Task 5: Python tiktoken counts special-token text instead of raising

**Acceptance criteria:** AC 31

**Files:**
- Modify: `contexel/tokens.py`, `tests/test_audit_truth.py`

**Interfaces:**
- Consumes: the named `count_tokens` closure from Task 4 and the `fake_tiktoken` fixture.
- Produces: `tokenizer(text)` calls `enc.encode(text, disallowed_special=())`, so `"<|endoftext|>"` is ordinary text. Counts for text without special-token literals are unchanged.

- [ ] **Step 5.1: Write the failing tests**

In `tests/test_audit_truth.py`, replace this block:
<!-- OP replace-old path=tests/test_audit_truth.py -->
```python
from contexel import (allowlist, dedupe, pipeline, select, stage, tokens,
                      trace, truncate_field)
from contexel.trace import traced
```
with:
<!-- OP replace-new -->
```python
from contexel import (allowlist, dedupe, pipeline, select, stage, tokens,
                      trace, trim_to_budget, truncate_field)
from contexel.trace import traced
```

In `tests/test_audit_truth.py`, replace this block:
<!-- OP replace-old path=tests/test_audit_truth.py -->
```python
    assert sizes == [1, 1]
```
with:
<!-- OP replace-new -->
```python
    assert sizes == [1, 1]


# --- AC 31: tiktoken and special-token literals ----------------------------

def test_tiktoken_tokenizer_asks_for_special_tokens_to_be_ordinary_text(fake_tiktoken):
    tok = tokens.tiktoken_tokenizer()
    assert tok("<|endoftext|>") == len("<|endoftext|>")
    assert fake_tiktoken.kwargs == [{"disallowed_special": ()}]


def test_tiktoken_counts_special_token_literals():
    tiktoken = pytest.importorskip("tiktoken")
    try:
        tiktoken.get_encoding("cl100k_base")
    except Exception as exc:  # the encoding file is fetched on first use
        pytest.skip(f"cl100k_base is not available here: {exc!r}")
    tok = tokens.tiktoken_tokenizer()
    assert tok("a <|endoftext|> b") > 3
    cut = truncate_field([{"s": "<|endoftext|>" * 8}], "s", 4, tokenizer=tok)
    assert isinstance(cut[0]["s"], str) and cut[0]["s"]
    kept = trim_to_budget([{"s": "<|endoftext|>"}] * 3, max_tokens=500, tokenizer=tok)
    assert len(kept) == 3
```

- [ ] **Step 5.2: Run them and watch them fail**

```bash
PYTHONPATH=. python -m pytest -q tests/test_audit_truth.py -k 'tiktoken_tokenizer_asks or special_token'
```

Expected:

```text
FAILED ...::test_tiktoken_tokenizer_asks_for_special_tokens_to_be_ordinary_text
FAILED ...::test_tiktoken_counts_special_token_literals      <- ValueError: Encountered text corresponding to disallowed special token
2 failed
```

The second test needs the real `tiktoken` package and its cached `cl100k_base` file; where either is missing it **skips** (it never fails for lack of the network), and the first test (a fake encoder that records how it is called) is the portable proof of the mechanism.

- [ ] **Step 5.3: Implement**

In `contexel/tokens.py`, replace this block:
<!-- OP replace-old path=contexel/tokens.py -->
```python
    def count_tokens(text: str) -> int:
        return len(enc.encode(text))

    # distinct encodings must not share a policy fingerprint
```
with:
<!-- OP replace-new -->
```python
    def count_tokens(text: str) -> int:
        # disallowed_special=(): text such as "<|endoftext|>" is ordinary
        # text to count here, not a reason to raise
        return len(enc.encode(text, disallowed_special=()))

    # distinct encodings must not share a policy fingerprint
```

- [ ] **Step 5.4: Run the tests and the whole suite**

```bash
PYTHONPATH=. python -m pytest -q tests/test_audit_truth.py
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
```

Expected:

```text
21 passed
507 passed
```

(Where `tiktoken` is not installed, one test skips and the counts read `20 passed, 1 skipped` and `506 passed, 1 skipped`.)

- [ ] **Step 5.5: Commit**

```bash
git add contexel/tokens.py tests/test_audit_truth.py
git commit -m "fix(py): count special-token text with tiktoken instead of raising"
```


---

### Task 6: TypeScript fingerprints: sets, nested pipelines, snapshot at build

**Acceptance criteria:** AC 29, AC 30 (TypeScript)

**Files:**
- Modify: `ts/src/pipeline.ts`, `ts/test/fingerprint.test.ts`

**Interfaces:**
- Consumes: Task 1's TypeScript baselines (eight shapes, must stay green).
- Produces: `stableRepr` renders a `Set` as `set{...}` of its sorted element reprs; a pipeline sets `__contexelDesc = "pipeline(<fingerprint>)"` on its returned function; `snapshot` (private) copies arrays and plain objects recursively and a `Set` as a shell (its elements are the caller's own) and returns everything else (class instances, `Map`, functions) as it is; `stage()` binds and fingerprints the snapshot; `pipeline()` copies its array of stages. No public name changes. There is no tiktoken in this port.

- [ ] **Step 6.1: Add the failing tests**

In `ts/test/fingerprint.test.ts`, replace this block:
<!-- OP replace-old path=ts/test/fingerprint.test.ts -->
```typescript
  trimToBudget,
  truncateField,
  type Records,
} from "../src/index.js";

// --- the recorded baseline (written before the audit-truthfulness change) ---
```
with:
<!-- OP replace-new -->
```typescript
  trimToBudget,
  truncateField,
  type Records,
  type StageFn,
} from "../src/index.js";

// --- the recorded baseline (written before the audit-truthfulness change) ---
```

In `ts/test/fingerprint.test.ts`, replace this block:
<!-- OP replace-old path=ts/test/fingerprint.test.ts -->
```typescript
  assert.equal(a.fingerprint, b.fingerprint);
});
```
with:
<!-- OP replace-new -->
```typescript
  assert.equal(a.fingerprint, b.fingerprint);
});

// --- AC 29: what the fingerprint covers ---------------------------------

const fp = (...stages: StageFn[]): string => pipeline(stages).fingerprint as string;

test("fingerprint differs for set contents", () => {
  assert.notEqual(
    fp(stage(allowlist, { field: "s", allowed: new Set(["a"]) as never })),
    fp(stage(allowlist, { field: "s", allowed: new Set(["b"]) as never }))
  );
});

test("the fingerprint of a set ignores insertion order", () => {
  assert.equal(
    fp(stage(annotate, { s: new Set(["a", "b", "c"]) })),
    fp(stage(annotate, { s: new Set(["c", "a", "b"]) }))
  );
});

test("the fingerprint of a set is not that of an array or an object", () => {
  const forms = [new Set(["a"]), ["a"], { a: 1 }, {}, new Set()].map((v) =>
    fp(stage(annotate, { v }))
  );
  assert.equal(new Set(forms).size, forms.length);
});

test("a Set nested in an array or an object is covered too", () => {
  const withSet = (v: unknown) => fp(stage(annotate, { v }));
  assert.notEqual(withSet([1, new Set(["a"])]), withSet([1, new Set(["b"])]));
  assert.notEqual(withSet({ k: new Set(["a"]) }), withSet({ k: new Set(["b"]) }));
  assert.equal(withSet([new Set(["b", "a"])]), withSet([new Set(["a", "b"])]));
});

test("fingerprint differs for nested pipelines", () => {
  const innerA = pipeline([stage(select, { fields: ["a"] })]);
  const innerB = pipeline([stage(select, { fields: ["b"] })]);
  const outer = (inner: StageFn) => fp(inner, stage(dedupe, { key: "a" }));
  const sameAsA = pipeline([stage(select, { fields: ["a"] })]);
  assert.notEqual(outer(innerA), outer(innerB));
  assert.equal(outer(innerA), outer(sameAsA));
});

test("a nested pipeline still runs its stages", () => {
  const inner = pipeline([stage(select, { fields: ["a"] })]);
  const out = pipeline([inner, stage(dedupe, { key: "a" })])([{ a: 1, b: 2 }, { a: 1 }]);
  assert.deepEqual(out, [{ a: 1 }]);
});

// --- AC 30: a policy cannot change behavior without changing its fingerprint

test("a bound array changed afterwards cannot change behavior", () => {
  const allowed = ["a"];
  const pipe = pipeline([stage(allowlist, { field: "s", allowed })]);
  const before = pipe.fingerprint;
  allowed.push("b");
  assert.deepEqual(pipe([{ s: "a" }, { s: "b" }]), [{ s: "a" }]);
  assert.equal(pipe.fingerprint, before);
});

test("nested bound containers are copied at every depth", () => {
  const names = ["a"];
  const config = { names, deep: { list: [names] }, tags: new Set(["t"]) };
  const probe = stage((_r: Records, c: typeof config) => [{ config: JSON.stringify(c, (_k, v) => (v instanceof Set ? [...v] : v)) }], config);
  const pipe = pipeline([probe]);
  const expected = probe([]);
  const before = pipe.fingerprint;
  names.push("b");
  config.deep.list.push(["z"]);
  config.tags.add("u");
  (config as Record<string, unknown>).extra = 1;
  assert.deepEqual(probe([]), expected);
  assert.equal(pipe.fingerprint, before);
});

test("pipeline copies its array of stages", () => {
  const stages = [stage(select, { fields: ["a"] })];
  const pipe = pipeline(stages);
  const before = pipe.fingerprint;
  stages.push(stage(select, { fields: ["b"] }));
  stages[0] = stage(select, { fields: ["b"] });
  assert.deepEqual(pipe([{ a: 1, b: 2 }]), [{ a: 1 }]);
  assert.equal(pipe.fingerprint, before);
});

test("a function, a class instance, a Map and the elements of a Set are not copied", () => {
  // documented limit: only arrays, plain objects and Set shells are copied
  class Box {}
  const box = new Box();
  const map = new Map([["k", 1]]);
  const element = { id: 1 };
  const set = new Set([element]);
  const seen: Record<string, unknown> = {};
  const grab = (r: Records, p: Record<string, unknown>): Records => {
    Object.assign(seen, p);
    return r;
  };
  stage(grab, { key: bare, box, map, set })([]);
  assert.equal(seen.key, bare);
  assert.equal(seen.box, box);
  assert.equal(seen.map, map);
  assert.notEqual(seen.set, set); // the Set is copied...
  assert.equal([...(seen.set as Set<unknown>)][0], element); // ...its elements are not
});
```

- [ ] **Step 6.2: Run them and watch eight fail**

```bash
cd ts && npm run build && npm test
```

Expected:

```text
✖ fingerprint differs for set contents
✖ the fingerprint of a set is not that of an array or an object
✖ a Set nested in an array or an object is covered too
✖ fingerprint differs for nested pipelines
✖ a bound array changed afterwards cannot change behavior
✖ nested bound containers are copied at every depth
✖ pipeline copies its array of stages
✖ a function, a class instance, a Map and the elements of a Set are not copied
ℹ fail 8
```

- [ ] **Step 6.3: Implement**

In `ts/src/pipeline.ts`, replace this block:
<!-- OP replace-old path=ts/src/pipeline.ts -->
```typescript
 * is a valid stage. Pipelines carry a stable, address-free fingerprint
 * (language-local in v1 per ADR-001) recorded into any active trace.
 */
import { createHash } from "node:crypto";
```
with:
<!-- OP replace-new -->
```typescript
 * is a valid stage. Pipelines carry a stable, address-free fingerprint
 * (language-local in v1 per ADR-001) recorded into any active trace.
 *
 * Coverage: primitives, arrays, plain objects and `Set`s (by sorted contents)
 * are hashed by value; a nested pipeline contributes its own fingerprint;
 * functions by `name`; any other object only by its type. `stage()` takes a
 * private copy of the arrays, plain objects and `Set`s bound to it (a `Set`'s
 * elements are not copied) and `pipeline()` copies its list of stages, so
 * changing the caller's own array or object afterwards changes neither the
 * behavior nor the fingerprint. Class instances, `Map`s and the elements of a
 * `Set` stay live.
 */
import { createHash } from "node:crypto";
```

In `ts/src/pipeline.ts`, replace this block:
<!-- OP replace-old path=ts/src/pipeline.ts -->
```typescript
  }
  if (Array.isArray(value)) return "[" + value.map(stableRepr).join(",") + "]";
  if (typeof value === "function") return (value as { name?: string }).name || "function";
  if (typeof value === "object") {
```
with:
<!-- OP replace-new -->
```typescript
  }
  if (Array.isArray(value)) return "[" + value.map(stableRepr).join(",") + "]";
  // Insertion order is not part of a set's meaning: hash the sorted contents.
  if (value instanceof Set) return "set{" + [...value].map(stableRepr).sort().join(",") + "}";
  if (typeof value === "function") return (value as { name?: string }).name || "function";
  if (typeof value === "object") {
```

In `ts/src/pipeline.ts`, replace this block:
<!-- OP replace-old path=ts/src/pipeline.ts -->
```typescript
}

/** Bind params to a stage so it slots into a pipeline as `records => records`. */
export function stage<P>(
  fn: (records: Records, params: P) => Records,
  params: P
): StageFn {
  const run: Described = (records: Records) => fn(records, params);
  Object.defineProperty(run, "name", { value: fn.name || "stage" });
  run.__contexelDesc = `${fn.name || "stage"}(${stableRepr(params)})`;
  return run;
}
```
with:
<!-- OP replace-new -->
```typescript
}

/** A private copy of the arrays, plain objects and `Set`s in `value` (any
 * depth). A `Set` is copied as a shell: its elements are the caller's own.
 * Everything else (class instances, `Map`s, functions) is returned as it is. */
function snapshot<T>(value: T): T {
  if (Array.isArray(value)) return value.map(snapshot) as T;
  if (value instanceof Set) return new Set(value) as T;
  if (value !== null && typeof value === "object") {
    const proto = Object.getPrototypeOf(value);
    if (proto === Object.prototype || proto === null) {
      const copy: Rec = Object.create(proto);
      for (const [k, v] of Object.entries(value as Rec)) copy[k] = snapshot(v);
      return copy as T;
    }
  }
  return value;
}

/** Bind params to a stage so it slots into a pipeline as `records => records`.
 * The stage keeps a private copy of any array, plain object or `Set` among the
 * params, so changing the caller's own value afterwards cannot change what the
 * stage does or what its fingerprint says. */
export function stage<P>(
  fn: (records: Records, params: P) => Records,
  params: P
): StageFn {
  const bound = snapshot(params);
  const run: Described = (records: Records) => fn(records, bound);
  Object.defineProperty(run, "name", { value: fn.name || "stage" });
  run.__contexelDesc = `${fn.name || "stage"}(${stableRepr(bound)})`;
  return run;
}
```

In `ts/src/pipeline.ts`, replace this block:
<!-- OP replace-old path=ts/src/pipeline.ts -->
```typescript
 * worker thread. Strict never changes a successful result and is not part of
 * the fingerprint. */
export function pipeline(stages: StageFn[], options: { strict?: boolean } = {}): Described {
  if (options.strict !== undefined) checkBool(options.strict, "pipeline", "strict");
  const isStrictPipeline = options.strict === true;
  const descs = stages.map(
    (s) => (s as Described).__contexelDesc ?? ((s as Described).name || "callable")
```
with:
<!-- OP replace-new -->
```typescript
 * worker thread. Strict never changes a successful result and is not part of
 * the fingerprint. */
export function pipeline(stageList: StageFn[], options: { strict?: boolean } = {}): Described {
  if (options.strict !== undefined) checkBool(options.strict, "pipeline", "strict");
  const isStrictPipeline = options.strict === true;
  const stages = [...stageList]; // a later change to the caller's array is not ours
  const descs = stages.map(
    (s) => (s as Described).__contexelDesc ?? ((s as Described).name || "callable")
```

In `ts/src/pipeline.ts`, replace this block:
<!-- OP replace-old path=ts/src/pipeline.ts -->
```typescript
  };
  run.fingerprint = fingerprint;
  return run;
}
```
with:
<!-- OP replace-new -->
```typescript
  };
  run.fingerprint = fingerprint;
  // as a stage of an outer pipeline, contribute this fingerprint (not "run")
  run.__contexelDesc = `pipeline(${fingerprint})`;
  return run;
}
```

- [ ] **Step 6.4: Run the TypeScript suite**

```bash
cd ts && npm run build && npm test
```

Expected:

```text
ℹ tests 347 / ℹ pass 347 / ℹ fail 0
```

- [ ] **Step 6.5: Commit**

```bash
git add ts/src/pipeline.ts ts/test/fingerprint.test.ts
git commit -m "fix(ts): fingerprint sets and nested pipelines; copy bound params"
```


---

### Task 7: C# fingerprints: sets at any depth, nested pipelines

**Acceptance criteria:** AC 29 (C#); AC 30 as far as C# can promise it (documented)

**Files:**
- Modify: `csharp/Contexel/Pipeline.cs`, `csharp/Contexel.Tests/FingerprintTests.cs`

**Interfaces:**
- Consumes: Task 1's C# baselines (seven shapes, must stay green).
- Produces: a parameter value containing a set (`ISet<T>` or `IReadOnlySet<T>`, at any depth) is hashed by its sorted element reprs (`set{...}`); a parameter with no set renders exactly as before; a stage whose `Fn.Target` is a `Pipeline` (a stage built from `inner.Run`) appends `pipeline=<inner fingerprint>`. No public name changes and no new API.
- What C# cannot do (documented, not fixed): a `Stage` is a delegate and its `Parameters` exist only to feed the fingerprint, so the fingerprint is computed once at construction and a closure over a list the caller keeps changing can change behavior without changing it. A lambda that calls `inner.Run` is opaque.

- [ ] **Step 7.1: Add the failing tests**

In `csharp/Contexel.Tests/FingerprintTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/FingerprintTests.cs -->
```csharp
        Assert.Equal(a.Fingerprint, b.Fingerprint);
    }
}
```
with:
<!-- OP replace-new -->
```csharp
        Assert.Equal(a.Fingerprint, b.Fingerprint);
    }

    // --- AC 29: what the fingerprint covers ---------------------------------

    private static string Fp(params Stage[] stages) => new Pipeline(stages).Fingerprint;

    private static Stage WithParam(string key, object? value) =>
        Named("annotate", new Rec { [key] = value });

    [Fact]
    public void FingerprintDiffersForSetContents() =>
        Assert.NotEqual(Fp(WithParam("allowed", new HashSet<string> { "a" })),
                        Fp(WithParam("allowed", new HashSet<string> { "b" })));

    [Fact]
    public void TheFingerprintOfASetIgnoresInsertionOrderAndSetType()
    {
        var ab = Fp(WithParam("s", new HashSet<string> { "a", "b", "c" }));
        var ba = Fp(WithParam("s", new HashSet<string> { "c", "a", "b" }));
        var sorted = Fp(WithParam("s", new SortedSet<string> { "b", "c", "a" }));
        Assert.Equal(ab, ba);
        Assert.Equal(ab, sorted);
    }

    [Fact]
    public void TheFingerprintOfASetIsNotThatOfAListOrADictionary()
    {
        var forms = new object?[]
        {
            new HashSet<string> { "a" }, L("a"), new Rec { ["a"] = 1L }, new Rec(),
            new HashSet<string>(),
        }.Select(v => Fp(WithParam("v", v))).ToList();
        Assert.Equal(forms.Count, forms.Distinct().Count());
    }

    [Fact]
    public void ASetNestedInAListOrADictionaryIsCoveredToo()
    {
        Assert.NotEqual(
            Fp(WithParam("v", L(1L, new HashSet<long> { 1, 2 }))),
            Fp(WithParam("v", L(1L, new HashSet<long> { 1, 3 }))));
        Assert.NotEqual(
            Fp(WithParam("v", new Rec { ["k"] = new HashSet<string> { "x" } })),
            Fp(WithParam("v", new Rec { ["k"] = new HashSet<string> { "y" } })));
    }

    private static Stage Select(string field) =>
        new("select", r => Stages.Select(r, new[] { field }),
            new Rec { ["fields"] = L(field) });

    private static Stage Outer(Pipeline inner) => new("inner", inner.Run);

    [Fact]
    public void FingerprintDiffersForNestedPipelines()
    {
        var innerA = new Pipeline(Select("a"));
        var innerB = new Pipeline(Select("b"));
        var sameAsA = new Pipeline(Select("a"));
        var dedupe = Named("dedupe", new Rec { ["key"] = "a" });
        Assert.NotEqual(Fp(Outer(innerA), dedupe), Fp(Outer(innerB), dedupe));
        Assert.Equal(Fp(Outer(innerA), dedupe), Fp(Outer(sameAsA), dedupe));
    }

    [Fact]
    public void ANestedPipelineWithItsOwnParametersStillContributesItsFingerprint()
    {
        var parameters = new Rec { ["note"] = "x" };
        Assert.NotEqual(
            Fp(new Stage("inner", new Pipeline(Select("a")).Run, parameters)),
            Fp(new Stage("inner", new Pipeline(Select("b")).Run, parameters)));
    }

    [Fact]
    public void ANestedPipelineStillRunsItsStages()
    {
        var inner = new Pipeline(Select("a"));
        var outer = new Pipeline(Outer(inner),
            new Stage("dedupe", r => Stages.Dedupe(r, "a"), new Rec { ["key"] = "a" }));
        Records input = [new Rec { ["a"] = 1L, ["b"] = 2L }, new Rec { ["a"] = 1L }];
        var result = outer.Run(input);
        Assert.Single(result);
        Assert.Equal(1L, result[0]["a"]);
    }

    [Fact]
    public void ANestedPipelineWrappedInALambdaIsNotDetected()
    {
        // documented limit: only a stage built from `inner.Run` itself is
        // recognised; a lambda that calls it is opaque, like any other lambda
        var innerA = new Pipeline(Select("a"));
        var innerB = new Pipeline(Select("b"));
        Assert.Equal(Fp(new Stage("inner", r => innerA.Run(r))),
                     Fp(new Stage("inner", r => innerB.Run(r))));
    }

    // --- AC 30 (as far as C# can promise it) ---------------------------------

    [Fact]
    public void ParametersChangedAfterConstructionDoNotChangeTheFingerprint()
    {
        var allowed = L("a");
        var pipe = new Pipeline(Named("allowlist", new Rec { ["allowed"] = allowed }));
        var before = pipe.Fingerprint;
        allowed.Add("b");
        Assert.Equal(before, pipe.Fingerprint);
    }

    [Fact]
    public void PipelineCopiesItsListOfStages()
    {
        var stages = new List<Stage> { Select("a") };
        var pipe = new Pipeline(stages);
        var before = pipe.Fingerprint;
        stages.Add(Select("b"));
        stages[0] = Select("b");
        Records input = [new Rec { ["a"] = 1L, ["b"] = 2L }];
        var result = pipe.Run(input);
        Assert.Equal(new[] { "a" }, result[0].Keys.ToArray());
        Assert.Equal(before, pipe.Fingerprint);
    }
}
```

- [ ] **Step 7.2: Run them and watch four fail**

```bash
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
```

Expected:

```text
Failed ...FingerprintTests.TheFingerprintOfASetIgnoresInsertionOrderAndSetType
Failed ...FingerprintTests.TheFingerprintOfASetIsNotThatOfAListOrADictionary
Failed ...FingerprintTests.FingerprintDiffersForNestedPipelines
Failed ...FingerprintTests.ANestedPipelineWithItsOwnParametersStillContributesItsFingerprint
Failed!  - Failed: 4, Passed: 308, Skipped: 0, Total: 312
```

The other new tests pass on the old code on purpose: they pin what C# already did (a set's contents already changed the fingerprint, as a list), what cannot change, and the two documented limits.

- [ ] **Step 7.3: Implement**

In `csharp/Contexel/Pipeline.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel/Pipeline.cs -->
```csharp
using System.Globalization;
using System.Security.Cryptography;
```
with:
<!-- OP replace-new -->
```csharp
using System.Collections;
using System.Globalization;
using System.Security.Cryptography;
```

In `csharp/Contexel/Pipeline.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel/Pipeline.cs -->
```csharp
/// an audit shows WHICH policy shaped the context. Fingerprints are
/// language-local in v1 (ADR-002).
/// </summary>
public sealed class Pipeline
```
with:
<!-- OP replace-new -->
```csharp
/// an audit shows WHICH policy shaped the context. Fingerprints are
/// language-local in v1 (ADR-002).
///
/// Coverage: parameters are hashed by canonical JSON, a set (any
/// <c>ISet&lt;T&gt;</c> or <c>IReadOnlySet&lt;T&gt;</c>, at any depth) by its
/// sorted contents, a delegate by its method name, and a stage built from
/// another pipeline's <c>Run</c> method group contributes that pipeline's
/// fingerprint. The fingerprint is computed once, from the declared
/// <see cref="Stage.Parameters"/>, when the pipeline is constructed; the
/// stage function itself is opaque, so a function that closes over a list or
/// dictionary you keep changing can still change behavior without changing
/// the fingerprint. Keep what a stage reads unchanged, or copy it when you
/// build the stage.
/// </summary>
public sealed class Pipeline
```

In `csharp/Contexel/Pipeline.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel/Pipeline.cs -->
```csharp
                    .OrderBy(kv => kv.Key, StringComparer.Ordinal)
                    .Select(kv => kv.Key + "=" + StableRepr(kv.Value))));
            repr.Append(");");
        }
```
with:
<!-- OP replace-new -->
```csharp
                    .OrderBy(kv => kv.Key, StringComparer.Ordinal)
                    .Select(kv => kv.Key + "=" + StableRepr(kv.Value))));
            // a stage that IS another pipeline (new Stage(name, inner.Run))
            // contributes that pipeline's fingerprint
            if (s.Fn.Target is Pipeline inner)
            {
                if (s.Parameters is { Count: > 0 }) repr.Append(',');
                repr.Append("pipeline=").Append(inner.Fingerprint);
            }
            repr.Append(");");
        }
```

In `csharp/Contexel/Pipeline.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel/Pipeline.cs -->
```csharp
    {
        Delegate d => "<fn:" + d.Method.Name + ">",
        _ => Tokens.PythonJson(value),
    };

    public Records Run(Records records)
```
with:
<!-- OP replace-new -->
```csharp
    {
        Delegate d => "<fn:" + d.Method.Name + ">",
        _ => Tokens.PythonJson(Settle(value)),
    };

    private static bool IsSet(object value) =>
        value.GetType().GetInterfaces().Any(i => i.IsGenericType &&
            (i.GetGenericTypeDefinition() == typeof(ISet<>) ||
             i.GetGenericTypeDefinition() == typeof(IReadOnlySet<>)));

    /// <summary>Replace every set, at any depth, by a string of its sorted
    /// contents (iteration order is not part of a set's meaning). Everything
    /// else keeps the shape it had, so a parameter with no set renders
    /// exactly as it did before.</summary>
    private static object? Settle(object? value)
    {
        if (value is null or string) return value;
        if (IsSet(value))
            return "set{" + string.Join(",", ((IEnumerable)value).Cast<object?>()
                .Select(StableRepr).OrderBy(s => s, StringComparer.Ordinal)) + "}";
        if (value is IDictionary dict)
        {
            var copy = new Dictionary<string, object?>();
            foreach (DictionaryEntry e in dict) copy[(string)e.Key] = Settle(e.Value);
            return copy;
        }
        if (value is IEnumerable seq) return seq.Cast<object?>().Select(Settle).ToList();
        return value;
    }

    public Records Run(Records records)
```

- [ ] **Step 7.4: Run the C# suite**

```bash
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
```

Expected:

```text
Passed!  - Failed: 0, Passed: 312, Skipped: 0, Total: 312   (0 warnings)
```

- [ ] **Step 7.5: Commit**

```bash
git add csharp/Contexel/Pipeline.cs csharp/Contexel.Tests/FingerprintTests.cs
git commit -m "fix(cs): fingerprint sets at any depth and nested pipelines"
```


---

### Task 8: Release hygiene: a version check on every push and in the release gate

**Acceptance criteria:** AC 33

**Files:**
- Create: `tools/check_versions.py`, `tests/test_check_versions.py`
- Modify: `.github/workflows/ci.yml` (new job `hygiene`, version step only; Task 9 completes it), `.github/workflows/release.yml`

**Interfaces:**
- Produces: `python tools/check_versions.py [--root DIR]`: reads the seven version locations (`pyproject.toml` `[project]` table, `contexel/__init__.py`, `ts/package.json`, `ts/package-lock.json` twice, `ts/src/index.ts`, `csharp/Contexel/Contexel.csproj`); exit 0 when they are equal, 1 when they differ (prints each location and its version, naming the file), 2 when a location cannot be read (names the file and what was expected). Standard library only; runs on Python 3.9 (no `tomllib`, a regular expression reads the `[project]` table).
- The check demands exact string equality. The project's versions are plain `z.y.x`; a pre-release spelled differently by PyPI (`0.2.0rc1`) and npm (`0.2.0-rc.1`) would fail it loudly rather than be guessed at (out of scope).

- [ ] **Step 8.1: Write the failing tests**

Create `tests/test_check_versions.py` with exactly this content (it ends with one newline):
<!-- OP create path=tests/test_check_versions.py -->
```python
"""tools/check_versions.py (brief AC 33): the seven version locations of the three
packages must agree, and the check must say which file is wrong when they do not."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NL = chr(10)
sys.path.insert(0, str(ROOT / "tools"))
import check_versions  # noqa: E402

PYPROJECT = """[build-system]
requires = ["hatchling"]

[project]
name = "contexel"
version = "{v}"
description = "x"

[project.urls]
Homepage = "https://example.invalid"

[tool.example]
version = "9.9.9"
"""
INIT = """__version__ = "{v}"
__all__ = []
"""
INDEX_TS = """export const VERSION = "{v}";
"""
CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <Version>{v}</Version>
  </PropertyGroup>
</Project>
"""

# the seven locations: the keyword that sets each one, and the file it lives in
KEYS = {
    "pyproject": "pyproject.toml",
    "init": "contexel/__init__.py",
    "package": "ts/package.json",
    "lock_root": "ts/package-lock.json",
    "lock_entry": "ts/package-lock.json",
    "index_ts": "ts/src/index.ts",
    "csproj": "csharp/Contexel/Contexel.csproj",
}


def make_tree(root: Path, version: str = "1.2.3", **versions: str) -> Path:
    """Write a minimal repository whose seven locations say ``version``, except
    the ones named in ``versions`` (keyword = key of KEYS)."""
    v = {key: versions.get(key, version) for key in KEYS}
    lock = {"name": "contexel", "version": v["lock_root"], "lockfileVersion": 3,
            "packages": {"": {"name": "contexel", "version": v["lock_entry"]},
                         "node_modules/x": {"version": "9.9.9"}}}
    files = {
        "pyproject.toml": PYPROJECT.format(v=v["pyproject"]),
        "contexel/__init__.py": INIT.format(v=v["init"]),
        "ts/package.json": json.dumps({"name": "contexel", "version": v["package"]}),
        "ts/package-lock.json": json.dumps(lock),
        "ts/src/index.ts": INDEX_TS.format(v=v["index_ts"]),
        "csharp/Contexel/Contexel.csproj": CSPROJ.format(v=v["csproj"]),
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def run(root, capsys):
    status = check_versions.main(["--root", str(root)])
    out = capsys.readouterr()
    return status, out.out, out.err


def test_agreeing_versions_pass(tmp_path, capsys):
    status, out, err = run(make_tree(tmp_path), capsys)
    assert status == 0, err
    assert "1.2.3" in out and "7" in out


@pytest.mark.parametrize("key", sorted(KEYS))
def test_disagreeing_versions_fail_naming_the_file(tmp_path, capsys, key):
    root = make_tree(tmp_path, **{key: "1.2.4"})
    status, _out, err = run(root, capsys)
    assert status == 1
    assert KEYS[key] in err
    assert "1.2.3" in err and "1.2.4" in err


def test_the_pyproject_version_is_the_project_tables_not_another_tables(tmp_path, capsys):
    root = make_tree(tmp_path)
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    other, rest = text.split("[tool.example]")
    # a [tool.*] table with a different version BEFORE [project] must not win
    (root / "pyproject.toml").write_text(
        "[tool.example]" + rest + NL + other, encoding="utf-8")
    status, _out, err = run(root, capsys)
    assert status == 0, err


def test_crlf_files_are_read(tmp_path, capsys):
    root = make_tree(tmp_path)
    for rel in ("pyproject.toml", "contexel/__init__.py", "ts/src/index.ts",
                "csharp/Contexel/Contexel.csproj"):
        path = root / rel
        path.write_bytes(path.read_bytes().replace(NL.encode(), (chr(13) + NL).encode()))
    status, _out, err = run(root, capsys)
    assert status == 0, err


def test_a_missing_file_fails_loudly_naming_it(tmp_path, capsys):
    root = make_tree(tmp_path)
    (root / "csharp/Contexel/Contexel.csproj").unlink()
    status, _out, err = run(root, capsys)
    assert status == 2
    assert "csharp/Contexel/Contexel.csproj" in err


@pytest.mark.parametrize("rel, broken", [
    ("pyproject.toml", "[project]" + NL + "name = 'x'" + NL),
    ("contexel/__init__.py", "__all__ = []" + NL),
    ("ts/package.json", "{}"),
    ("ts/package.json", "not json"),
    ("ts/package-lock.json", json.dumps({"version": "1.2.3", "packages": {}})),
    ("ts/src/index.ts", "export const NAME = 'x';" + NL),
    ("csharp/Contexel/Contexel.csproj", "<Project></Project>"),
])
def test_a_file_without_a_readable_version_fails_loudly(tmp_path, capsys, rel, broken):
    root = make_tree(tmp_path)
    (root / rel).write_text(broken, encoding="utf-8")
    status, _out, err = run(root, capsys)
    assert status == 2
    assert rel in err


def test_the_repository_itself_agrees(capsys):
    status, out, err = run(ROOT, capsys)
    assert status == 0, err
    assert "version locations say" in out


def test_it_runs_as_the_script_ci_runs(tmp_path):
    root = make_tree(tmp_path, csproj="9.0.0")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_versions.py"), "--root", str(root)],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 1
    assert "csharp/Contexel/Contexel.csproj" in proc.stderr
```

- [ ] **Step 8.2: Run them and watch the module be missing**

```bash
PYTHONPATH=. python -m pytest -q tests/test_check_versions.py
```

Expected:

```text
ModuleNotFoundError: No module named 'check_versions'
1 error
```

- [ ] **Step 8.3: Write the tool**

Create `tools/check_versions.py` with exactly this content (it ends with one newline):
<!-- OP create path=tools/check_versions.py -->
```python
"""Fail when the seven version locations of the three packages disagree.

One release ships a PyPI wheel, an npm tarball and a NuGet package, and each
carries its own copy of the version. A release whose copies differ publishes
mismatched packages, so this check runs on every push and in the release gate
(brief AC 33), not only when a tag is cut.

Standard library only, and it runs on every supported Python (3.9 and later),
so the pyproject version is read with a regular expression, not ``tomllib``.

    python tools/check_versions.py            # check the repository
    python tools/check_versions.py --root DIR # check another tree (the tests do)

Exit status: 0 all agree, 1 they disagree (the files are named), 2 a location
could not be read (the file and what was expected are named).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable, List, NamedTuple, Optional, Sequence


NL = chr(10)


class Location(NamedTuple):
    label: str      # what the entry is, for the message
    path: str       # relative to the root, with forward slashes
    read: Callable[[str], str]  # file text -> the version string


class Found(NamedTuple):
    label: str
    path: str
    version: str


class Unreadable(Exception):
    """A location whose version could not be read."""


def _project_version(text: str) -> str:
    # the `version = "x"` line of the [project] table, not another table's
    section = re.search(r"^\[project\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if section:
        line = re.search(r'^version\s*=\s*"([^"]+)"', section.group(1), re.M)
        if line:
            return line.group(1)
    raise Unreadable('no version = "..." line in the [project] table')


def _regex(pattern: str, what: str) -> Callable[[str], str]:
    def read(text: str) -> str:
        found = re.search(pattern, text, re.M)
        if not found:
            raise Unreadable(f"no {what}")
        return found.group(1)

    return read


def _json_version(*keys: str) -> Callable[[str], str]:
    def read(text: str) -> str:
        try:
            value = json.loads(text)
            for key in keys:
                value = value[key]
        except (ValueError, KeyError, TypeError) as exc:
            raise Unreadable(f"no {' / '.join(keys)} in the JSON ({exc!r})") from exc
        if not isinstance(value, str) or not value:
            raise Unreadable(f"{' / '.join(keys)} is not a version string")
        return value

    return read


LOCATIONS: Sequence[Location] = (
    Location("Python package (pyproject)", "pyproject.toml", _project_version),
    Location("Python module", "contexel/__init__.py",
             _regex(r'^__version__\s*=\s*"([^"]+)"', '__version__ = "..." line')),
    Location("npm package", "ts/package.json", _json_version("version")),
    Location("npm lockfile (root)", "ts/package-lock.json", _json_version("version")),
    Location("npm lockfile (package entry)", "ts/package-lock.json",
             _json_version("packages", "", "version")),
    Location("TypeScript constant", "ts/src/index.ts",
             _regex(r'^export const VERSION\s*=\s*"([^"]+)"', 'export const VERSION = "..."')),
    Location("NuGet package (csproj)", "csharp/Contexel/Contexel.csproj",
             _regex(r"<Version>([^<]+)</Version>", "<Version> element")),
)


def collect(root: Path) -> List[Found]:
    """Read every location; raise Unreadable (naming the file) on the first failure."""
    found: List[Found] = []
    for loc in LOCATIONS:
        path = root / loc.path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise Unreadable(f"{loc.path}: cannot read it ({exc.strerror or exc})") from exc
        try:
            found.append(Found(loc.label, loc.path, loc.read(text)))
        except Unreadable as exc:
            raise Unreadable(f"{loc.path} ({loc.label}): {exc}") from exc
    return found


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split(NL + NL)[0])
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                        help="repository root (default: this repository)")
    args = parser.parse_args(argv)
    try:
        found = collect(Path(args.root))
    except Unreadable as exc:
        print(f"check_versions: {exc}", file=sys.stderr)
        return 2
    versions = sorted({f.version for f in found})
    if len(versions) == 1:
        print(f"check_versions: all {len(found)} version locations say {versions[0]}")
        return 0
    print("check_versions: the version locations disagree:", file=sys.stderr)
    for f in found:
        print(f"  {f.version:<12} {f.path}  ({f.label})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 8.4: Run the tests, the tool on this repository, and the suite**

```bash
PYTHONPATH=. python -m pytest -q tests/test_check_versions.py
python tools/check_versions.py; echo "exit=$?"
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
```

Expected:

```text
20 passed
check_versions: all 7 version locations say 0.1.17
exit=0
527 passed
```

Also run it once under the oldest interpreter you have (`py -3.9 tools/check_versions.py`): it must print the same line.

- [ ] **Step 8.5: Wire it into CI and the release gate**

In `.github/workflows/ci.yml`, replace this block:
<!-- OP replace-old path=.github/workflows/ci.yml -->
```yaml
      - run: pip install -e ".[dev]"
      - run: python -m pytest -q

  # Cross-language parity (ADR-001): Python is canon. Regenerate the golden
```
with:
<!-- OP replace-new -->
```yaml
      - run: pip install -e ".[dev]"
      - run: python -m pytest -q

  # Release hygiene (brief AC 32-33), on every push and pull request, not only
  # when a tag is cut: the seven version copies agree, the package is typed and
  # lint-clean, and the wheel really ships py.typed. mypy 2.x needs Python
  # 3.10 or newer, so this runs on 3.12; the test matrix covers 3.9.
  hygiene:
    runs-on: ubuntu-latest
    defaults:
      run:
        shell: bash
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7
        with:
          python-version: "3.12"
      - name: The seven version locations agree
        run: python tools/check_versions.py

  # Cross-language parity (ADR-001): Python is canon. Regenerate the golden
```

In `.github/workflows/release.yml`, replace this block:
<!-- OP replace-old path=.github/workflows/release.yml -->
```yaml
        with:
          python-version: '3.12'
      - name: Install (with test tooling)
        run: python -m pip install -e ".[dev,accurate]"
```
with:
<!-- OP replace-new -->
```yaml
        with:
          python-version: '3.12'
      - name: The seven version locations must agree
        run: python tools/check_versions.py
      - name: Install (with test tooling)
        run: python -m pip install -e ".[dev,accurate]"
```

Check the YAML parses and the new job and step exist:

```bash
python -c "import yaml; ci=yaml.safe_load(open('.github/workflows/ci.yml',encoding='utf-8')); print(list(ci['jobs'])); r=yaml.safe_load(open('.github/workflows/release.yml',encoding='utf-8')); print([s.get('name') for s in r['jobs']['test']['steps']])"
```

Expected:

```text
['test', 'hygiene', 'ts-parity', 'cs-parity']
[None, None, 'The seven version locations must agree', 'Install (with test tooling)', 'Full suite on this exact commit (no inherited green)']
```

- [ ] **Step 8.6: Commit**

```bash
git add tools/check_versions.py tests/test_check_versions.py .github/workflows/ci.yml .github/workflows/release.yml
git commit -m "ci: fail when the seven version locations disagree"
```


---

### Task 9: Typed and lint-clean package: py.typed, ruff, mypy, a wheel check

**Acceptance criteria:** AC 32

**Files:**
- Create: `contexel/py.typed` (empty), `tests/test_packaging.py`
- Modify: `pyproject.toml`, `contexel/shaped.py`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: the `lint` extra (`ruff>=0.15,<1`, `mypy>=2.3,<3`), kept apart from `dev` because mypy 2.x needs Python 3.10 or newer and the 3.9 test legs install `dev`; `[tool.ruff]` (line length 100, target `py39`, rules `E`, `F`, `W`, `B`); `[tool.mypy]` (`files = ["contexel"]`, `python_version = "3.10"`, `warn_unused_ignores`, `warn_redundant_casts`; mypy 2.x refuses a 3.9 target, the 3.9 CI legs prove the runtime); one `typing.cast` in `shaped.py` (no runtime change: the value was already validated as a list or tuple).
- `py.typed` ships in the wheel because `[tool.hatch.build.targets.wheel] packages = ["contexel"]` includes every file in the package.

- [ ] **Step 9.1: Write the failing packaging tests**

Create `tests/test_packaging.py` with exactly this content (it ends with one newline):
<!-- OP create path=tests/test_packaging.py -->
```python
"""What the published wheel contains (brief AC 32): ``py.typed`` marks the package
as typed, so a type checker uses its annotations instead of treating it as untyped."""
import os
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_py_typed_is_in_the_source_tree():
    marker = ROOT / "contexel" / "py.typed"
    assert marker.is_file()
    assert marker.stat().st_size == 0  # PEP 561: a marker file, content ignored


def test_the_wheel_ships_py_typed(tmp_path):
    # hatchling is the build backend; CI's test legs do not have it installed
    # (pip builds in an isolated environment), so CI's "hygiene" job checks the
    # real wheel too.
    build = pytest.importorskip("hatchling.build")
    previous = os.getcwd()
    os.chdir(ROOT)
    try:
        wheel = build.build_wheel(str(tmp_path))
    finally:
        os.chdir(previous)
    with zipfile.ZipFile(tmp_path / wheel) as archive:
        names = archive.namelist()
    assert "contexel/py.typed" in names
    assert "contexel/__init__.py" in names
```

- [ ] **Step 9.2: Run them and watch them fail**

```bash
PYTHONPATH=. python -m pytest -q tests/test_packaging.py
```

Expected:

```text
FAILED tests/test_packaging.py::test_py_typed_is_in_the_source_tree
FAILED tests/test_packaging.py::test_the_wheel_ships_py_typed
2 failed
```

(The second test builds the wheel in-process with `hatchling.build`; where `hatchling` is not installed it skips, and CI's `hygiene` job checks the real wheel instead.)

- [ ] **Step 9.3: Add the marker and the configuration**

<!-- OP create-empty path=contexel/py.typed -->
Create the empty file `contexel/py.typed` (zero bytes; PEP 561 marker).

In `pyproject.toml`, replace this block:
<!-- OP replace-old path=pyproject.toml -->
```toml
accurate = ["tiktoken>=0.5"]
dev = ["pytest>=7"]
benchmarks = [
    "tiktoken>=0.5",
```
with:
<!-- OP replace-new -->
```toml
accurate = ["tiktoken>=0.5"]
dev = ["pytest>=7"]
# Lint and type gate (CI job "hygiene"; dev-only, never shipped). mypy 2.x
# cannot target Python 3.9, so install this extra on Python 3.10 or newer.
lint = ["ruff>=0.15,<1", "mypy>=2.3,<3"]
benchmarks = [
    "tiktoken>=0.5",
```

In `pyproject.toml`, replace this block:
<!-- OP replace-old path=pyproject.toml -->
```toml
packages = ["contexel"]
```
with:
<!-- OP replace-new -->
```toml
packages = ["contexel"]

[tool.ruff]
line-length = 100
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "W", "B"]

[tool.mypy]
files = ["contexel"]
# mypy 2.x refuses a 3.9 target. The 3.9 CI legs run the tests on a real 3.9;
# mypy checks the types against 3.10, the oldest version it supports.
python_version = "3.10"
warn_unused_ignores = true
warn_redundant_casts = true
```

- [ ] **Step 9.4: See the type gate fail on exactly one line**

```bash
python -m ruff check contexel --no-cache
python -m mypy --no-incremental
```

Expected:

```text
All checks passed!
contexel\shaped.py:66: error: Argument 1 has incompatible type "list[Any] | tuple[Any, ...]"; expected "list[dict[str, Any]]"  [arg-type]
Found 1 error in 1 file (checked 8 source files)
```

- [ ] **Step 9.5: Fix it**

In `contexel/shaped.py`, replace this block:
<!-- OP replace-old path=contexel/shaped.py -->
```python
import functools
import inspect
from typing import Any, Callable, Dict, List, Sequence, Union

from .errors import InputShapeError, check_bool
```
with:
<!-- OP replace-new -->
```python
import functools
import inspect
from typing import Any, Callable, Dict, List, Sequence, Union, cast

from .errors import InputShapeError, check_bool
```

In `contexel/shaped.py`, replace this block:
<!-- OP replace-old path=contexel/shaped.py -->
```python
                stage="shaped")
        with strict_mode():
            return base(records)

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
```
with:
<!-- OP replace-new -->
```python
                stage="shaped")
        with strict_mode():
            return base(cast(Records, records))

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
```

- [ ] **Step 9.6: Run the gate, the tests and the suite**

```bash
python -m ruff check contexel --no-cache
python -m mypy --no-incremental
PYTHONPATH=. python -m pytest -q tests/test_packaging.py
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
```

Expected:

```text
All checks passed!
Success: no issues found in 8 source files
2 passed
529 passed
```

(Without `hatchling`, `1 passed, 1 skipped` and `528 passed, 1 skipped`.)

- [ ] **Step 9.7: Complete the `hygiene` CI job**

In `.github/workflows/ci.yml`, replace this block:
<!-- OP replace-old path=.github/workflows/ci.yml -->
```yaml
      - name: The seven version locations agree
        run: python tools/check_versions.py

  # Cross-language parity (ADR-001): Python is canon. Regenerate the golden
```
with:
<!-- OP replace-new -->
```yaml
      - name: The seven version locations agree
        run: python tools/check_versions.py
      - run: pip install -e ".[lint]"
      - run: ruff check contexel
      - run: mypy
      - name: The wheel ships py.typed
        run: |
          pip wheel . --no-deps -w dist
          python -c "import glob, zipfile; names = zipfile.ZipFile(glob.glob('dist/*.whl')[0]).namelist(); assert 'contexel/py.typed' in names, names"

  # Cross-language parity (ADR-001): Python is canon. Regenerate the golden
```

Run the same steps CI runs, locally:

```bash
python tools/check_versions.py && python -m ruff check contexel --no-cache && python -m mypy --no-incremental
python -c "import tempfile, zipfile, os, hatchling.build as b; d=tempfile.mkdtemp(); n=b.build_wheel(d); assert 'contexel/py.typed' in zipfile.ZipFile(os.path.join(d,n)).namelist(); print('wheel', n, 'has py.typed')"
```

Expected:

```text
check_versions: all 7 version locations say 0.1.17
All checks passed!
Success: no issues found in 8 source files
wheel contexel-0.1.17-py3-none-any.whl has py.typed
```

`pip install -e ".[lint]"` and `pip wheel` need the network; they run for the first time in CI after the human pushes (unverified until then).

- [ ] **Step 9.8: Commit**

```bash
git add contexel/py.typed pyproject.toml contexel/shaped.py tests/test_packaging.py .github/workflows/ci.yml
git commit -m "build: ship py.typed; configure ruff and mypy; gate them in CI"
```


---

### Task 10: Documentation: changelog, ADR-008, READMEs, site

**Acceptance criteria:** AC 34 (every behavior change is listed under "Behavior changes"; no new public stage or parameter is added)

**Files:**
- Modify: `contexel/trace.py` (docstring), `README.md`, `site/getting-started.html`, `site/stages.html`, `ts/README.md`, `csharp/Contexel/README.md`, `docs/adr/008-policy-fingerprint-and-trace-attribution.md`, `CHANGELOG.md`

**Interfaces:**
- Documents: Behavior changes 8 to 11 (trace attribution, fingerprint coverage, the build-time copy, tiktoken special tokens), the release-hygiene additions, and the fingerprint scope in "Known limitations". ADR-008 moves from *proposed* to *accepted* and gains a per-language scope section. No version is bumped: the work stays under `[Unreleased]`.

- [ ] **Step 10.1: Edit the documents**

In `contexel/trace.py`, replace this block:
<!-- OP replace-old path=contexel/trace.py -->
```python
    "did the relevant context even reach the model?". Attribution is by the
    id value: records lacking the field are untracked, and keeping the id
    field in every ``select`` gives full attribution. Example::

        with trace(id_field="url") as t:
```
with:
<!-- OP replace-new -->
```python
    "did the relevant context even reach the model?". Attribution is by the
    id value: records lacking the field are untracked, and keeping the id
    field in every ``select`` gives full attribution. When a stage strips the
    id from records it keeps, only as many missing ids as the stage produced
    extra id-less records are explained away; the rest are reported dropped.
    Example::

        with trace(id_field="url") as t:
```

In `README.md`, replace this block:
<!-- OP replace-old path=README.md -->
```markdown
dropped, and `t.audit()` emits a JSON-able governance record keyed by the
pipeline's policy fingerprint — a shaping decision is inspectable and
attributable instead of silent.

All of it is stdlib-only Python. No embeddings, no model calls, no
```
with:
<!-- OP replace-new -->
```markdown
dropped, and `t.audit()` emits a JSON-able governance record keyed by the
pipeline's policy fingerprint — a shaping decision is inspectable and
attributable instead of silent. The fingerprint covers what a stage is bound to
(lists, dicts, sets, a nested pipeline, a tiktoken encoding), and `stage()`
keeps a private copy of the plain lists, dicts and sets bound to it, so
changing yours afterwards changes neither the behavior nor the fingerprint. A
record that never had the id field is untracked; if a stage strips the id from
the records it keeps (a `select` without it), the trace explains away only as
many missing ids as the stage produced extra id-less records and reports the
rest as dropped, so keep the id field in every `select` for exact attribution.

All of it is stdlib-only Python. No embeddings, no model calls, no
```

In `site/getting-started.html`, replace this block:
<!-- OP replace-old path=site/getting-started.html -->
```html
record = t.audit()   # policy fingerprints, per-stage dropped ids, token movement</code></pre>
<p>Records lacking the id field are untracked, so keep it in every
<code>select</code> when full attribution matters. Gate untrusted sources
before relevance logic with <code>allowlist</code> (and optionally
<code>quarantine</code>) — see the
```
with:
<!-- OP replace-new -->
```html
record = t.audit()   # policy fingerprints, per-stage dropped ids, token movement</code></pre>
<p>Records lacking the id field are untracked. If a stage strips the id from
records it keeps (a <code>select</code> without it), only as many missing ids
as the stage produced extra id-less records are explained away and the rest
are reported dropped, so keep the id in every <code>select</code> when you
need exact attribution. Gate untrusted sources
before relevance logic with <code>allowlist</code> (and optionally
<code>quarantine</code>) — see the
```

In `site/stages.html`, replace this block:
<!-- OP replace-old path=site/stages.html -->
```html
  list.</li>
  <li><code>pipeline([...])</code> exposes <code>.fingerprint</code> — a
  stable policy hash of stage names and bound parameters, recorded into any
  active trace so an audit can say which policy version shaped a context.</li>
  <li><code>trace(id_field=...)</code> — context manager; every stage
  records records-in/out and tokens-before/after, and with
```
with:
<!-- OP replace-new -->
```html
  list.</li>
  <li><code>pipeline([...])</code> exposes <code>.fingerprint</code> — a
  stable policy hash of stage names and bound parameters (a set by its sorted
  contents, a nested pipeline by its own fingerprint, a tiktoken tokenizer by
  its encoding), recorded into any active trace so an audit can say which
  policy version shaped a context. <code>stage()</code> keeps a private copy
  of the plain lists, dicts and sets bound to it, so the fingerprint cannot go
  stale.</li>
  <li><code>trace(id_field=...)</code> — context manager; every stage
  records records-in/out and tokens-before/after, and with
```

In `ts/README.md`, replace this block:
<!-- OP replace-old path=ts/README.md -->
```markdown
  serialization; Unicode word classes differ at the margins; pipeline
  fingerprints are language-local in v1.

## Links
```
with:
<!-- OP replace-new -->
```markdown
  serialization; Unicode word classes differ at the margins; pipeline
  fingerprints are language-local in v1.
- Audit: which records a stage dropped is part of the shared vectors. A
  pipeline's fingerprint hashes a `Set` by its sorted contents and a nested
  pipeline by its own fingerprint, and `stage()` copies the arrays, plain
  objects and `Set`s bound to it, so changing yours afterwards changes neither
  the behavior nor the fingerprint; a class instance, a `Map` and the elements
  of a `Set` are not copied. There is no tiktoken in this package.

## Links
```

In `csharp/Contexel/README.md`, replace this block:
<!-- OP replace-old path=csharp/Contexel/README.md -->
```markdown
`Tokens.Scoped` (AsyncLocal) for concurrency-safe per-tenant token
accounting.

## Errors and strict mode
```
with:
<!-- OP replace-new -->
```markdown
`Tokens.Scoped` (AsyncLocal) for concurrency-safe per-tenant token
accounting.

A pipeline's fingerprint covers each stage's declared `Parameters` (a set, at
any depth, by its sorted contents) and, for a stage built from another
pipeline's `Run` method group (`new Stage("inner", inner.Run)`), that
pipeline's fingerprint. It is computed once, when the pipeline is constructed.
The stage function itself is opaque: a function that closes over a list or
dictionary you keep changing can change behavior without changing the
fingerprint, so keep what a stage reads unchanged or copy it when you build the
stage. A lambda that calls `inner.Run` is opaque too. There is no tiktoken in
this package.

## Errors and strict mode
```

In `docs/adr/008-policy-fingerprint-and-trace-attribution.md`, replace this block:
<!-- OP replace-old path=docs/adr/008-policy-fingerprint-and-trace-attribution.md -->
```markdown
# ADR-008 — Fingerprint truthfulness and trace drop attribution

**Date:** 2026-11-19 · **Status:** proposed · **Deciders:** Chief Architect + human (audit contract change)

## Context
```
with:
<!-- OP replace-new -->
```markdown
# ADR-008 — Fingerprint truthfulness and trace drop attribution

**Date:** 2026-11-19 · **Status:** accepted (2026-11-20, Slice 3) · **Deciders:** Chief Architect + human (audit contract change)

## Context
```

In `docs/adr/008-policy-fingerprint-and-trace-attribution.md`, replace this block:
<!-- OP replace-old path=docs/adr/008-policy-fingerprint-and-trace-attribution.md -->
```markdown
"survivor lost its id"; the rest are reported dropped. Audit keys are unchanged.

## Alternatives considered
| Option | Pros | Cons | Why not |
```
with:
<!-- OP replace-new -->
```markdown
"survivor lost its id"; the rest are reported dropped. Audit keys are unchanged.

## Per-language scope (Slice 3)
- **Python** implements the decision as written: `stage()` snapshots plain
  `list`/`tuple`/`dict`/`set` values (exact types, any depth; a `frozenset` is
  immutable); a subclass or custom object is not copied and stays live. A nested
  pipeline carries `("pipeline", (fp,))`; a tiktoken tokenizer is named
  `tiktoken:<encoding|model>`; `disallowed_special=()` is passed so special-token
  literals are counted.
- **TypeScript** snapshots arrays, plain objects and `Set` shells (a `Set`'s
  elements are not copied); a `Set` is hashed by sorted contents; a pipeline used
  as a stage contributes `pipeline(<fp>)`. No tiktoken exists in this port.
- **C#** cannot snapshot behavior: a stage is a delegate, and the declared
  `Stage.Parameters` exist only to feed the fingerprint, so the fingerprint is
  computed once at construction and a closure over a caller's list can still
  change behavior (documented, not fixable without an API that owns the data).
  Sets are hashed by sorted contents at any depth; a stage built from `inner.Run`
  contributes the inner fingerprint (a lambda wrapper is opaque). No tiktoken.
- **Trace** attribution (`lost`) is identical in all three and pinned by shared
  vectors of kind `trace_dropped_ids`. A stage that ADDS id-less records can hide
  up to that many drops (the bound in the decision above).

## Alternatives considered
| Option | Pros | Cons | Why not |
```

In `CHANGELOG.md`, replace this block:
<!-- OP replace-old path=CHANGELOG.md -->
```markdown
  `contexel.errors`).
- The parity runners reject unknown option names inside a case's `args`.

### Behavior changes
```
with:
<!-- OP replace-new -->
```markdown
  `contexel.errors`).
- The parity runners reject unknown option names inside a case's `args`.

### Added — audit truthfulness and release hygiene (ADR-008)
- The audit no longer says something false: a trace's `dropped_ids` reports a
  drop that an unrelated id-less record used to hide, a policy fingerprint
  covers sets, nested pipelines and the tiktoken encoding, and a stage keeps a
  private copy of what is bound to it (Behavior changes 8 to 10). The shared
  parity vectors gain a case kind, `trace_dropped_ids`, that asserts each
  stage's dropped ids in all three languages (74 cases in all).
- `tools/check_versions.py` (standard library) fails when the seven version
  locations of the three packages disagree (`pyproject.toml`,
  `contexel/__init__.py`, `ts/package.json`, both entries of
  `ts/package-lock.json`, `ts/src/index.ts`, `csharp/Contexel/Contexel.csproj`),
  naming the file. It runs on every push and pull request in the new CI job
  `hygiene`, and in the release gate before any package is published.
- `contexel/py.typed` ships in the wheel (the package is typed), and `ruff` and
  `mypy` are configured and pass on `contexel/`. They live in a new dev-only
  extra, `pip install "contexel[lint]"` (MIT, never shipped, no runtime
  dependency); the CI job `hygiene` runs them on Python 3.12 and checks the
  built wheel. mypy 2.x cannot target Python 3.9, so it checks against 3.10 and
  the Python 3.9 test legs prove the runtime.

### Behavior changes
```

In `CHANGELOG.md`, replace this block:
<!-- OP replace-old path=CHANGELOG.md -->
```markdown
   (`config.invalid_value`; the message says "got list" for a set). Python and
   TypeScript reject sets there as well.

### Compatibility
```
with:
<!-- OP replace-new -->
```markdown
   (`config.invalid_value`; the message says "got list" for a set). Python and
   TypeScript reject sets there as well.
8. `trace(id_field=...)` no longer under-reports `dropped_ids`. A record dropped
   while some other surviving record never had the id field used to be
   reported as not dropped (the id-less survivor was assumed to be the one that
   lost its id). Now only as many unmatched ids as the stage produced extra
   id-less survivors (beyond the id-less records it was given) are explained
   away, the first ones in input order, and every other unmatched id is
   reported dropped. All three languages; the audit keys are unchanged. An
   audit recorded before this change may have under-reported. A stage that
   ADDS id-less records can still hide up to that many drops: a black-box stage
   leaves that ambiguity, and the bound is the number it added.
9. Policy fingerprints cover more, so a pipeline that binds one of these has a
   new fingerprint: a `set` or `frozenset` in Python (it used to hash as the
   type name `set`, so every set collided), a `Set` in TypeScript (it used to
   hash as `{}`) and any `ISet<T>` or `IReadOnlySet<T>` in C# (it used to hash
   as a list in enumeration order) are hashed by their sorted contents, at any
   depth; a nested pipeline contributes its own fingerprint (Python and
   TypeScript: any pipeline used as a stage; C#: a stage built from
   `inner.Run`), where it used to contribute only the word `run`; and a Python
   tiktoken tokenizer is named `tiktoken:<encoding or model>` instead of
   `<lambda>`. A pipeline that binds none of these keeps its exact fingerprint
   (golden tests in all three languages). Fingerprints recorded earlier for the
   changed shapes no longer match.
10. `stage()` copies the plain containers bound to it, and `pipeline()` copies
    its list of stages, in Python and TypeScript, so changing your own list,
    dict or set afterwards no longer changes the behavior (it used to, with the
    fingerprint unchanged). Code that relied on editing a bound list after
    building the stage must build the stage again. Only plain containers are
    copied: a subclass, a custom object, a function, a TypeScript class
    instance or `Map`, and the elements of a TypeScript `Set` stay live. C#
    cannot copy a closure: its fingerprint is computed once when the pipeline
    is constructed.
11. Python `tokens.tiktoken_tokenizer()` counts text such as `"<|endoftext|>"`
    as ordinary text (`disallowed_special=()`) instead of raising `ValueError`;
    counts for text without such literals are unchanged.

### Compatibility
```

In `CHANGELOG.md`, replace this block:
<!-- OP replace-old path=CHANGELOG.md -->
```markdown
  typo such as `{ field: "body" }` is silently ignored; the compile-time
  excess-property check only covers object literals).

### Tests
```
with:
<!-- OP replace-new -->
```markdown
  typo such as `{ field: "body" }` is silently ignored; the compile-time
  excess-property check only covers object literals).
- Fingerprint scope (ADR-008): the ambient tokenizer and serializer
  (`set_tokenizer`, `scoped`) are not part of a pipeline's fingerprint; a
  pipeline bound as a parameter value (not as a stage) hashes as the word `run`
  in Python; a Python container subclass is hashed by value but not copied; a
  C# lambda that calls another pipeline's `Run` is opaque; and nothing hashes
  the code inside a stage function, only its name, so two lambdas share
  `<lambda>`. The fingerprints stay language-local.

### Tests
```

- [ ] **Step 10.2: Check the site and run everything**

```bash
python tools/site_check.py
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
cd ts && npm run build && npm test
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
```

Expected:

```text
checked 6 pages under site/ -> OK
529 passed
ℹ tests 347 / ℹ pass 347 / ℹ fail 0
Passed!  - Failed: 0, Passed: 312, Skipped: 0, Total: 312
```

Privacy check before committing (the repository is public): `git diff main HEAD | grep -n -i -E "C:\\\\Users|/Users/|AppData|@gmail|@users.noreply"` must print nothing.

- [ ] **Step 10.3: Commit**

```bash
git add contexel/trace.py README.md site ts/README.md csharp/Contexel/README.md docs/adr/008-policy-fingerprint-and-trace-attribution.md CHANGELOG.md
git commit -m "docs: changelog, ADR-008 and READMEs for audit truthfulness"
```


## Gates and close-out (after Task 10)

Per the master plan, a slice is done only when a fresh-context reviewer at G4 and a QA engineer at G5 have reported with no unresolved blocker or major finding, and **the Security Reviewer has signed off at G5 for Slice 3** (audit integrity and release pipeline), holding the ship veto.

1. **G4 code review (whole branch, fresh context, adversarial).** Brief: AC 28 to 34, the rulings table above, "Behavior changes" 8 to 11, the Review Focus list. Required evidence: an old-versus-new differential over every traced stage (the only intended differences are the cases AC 28 lists), the golden baselines, and a check that nothing public was added or removed.
2. **G5 QA (execute, do not inspect).** Mutation testing in the Slice 2 manner (fresh `git archive` copy per mutant, `python -B`, TypeScript recompiled, C# under a wall-clock cap and a memory watchdog; verify each mutant applied). Suggested mutants: `lost` computed as `unidentified_out`, as `unidentified_in`, or without `max(0, ...)`; `unmatched[lost:]` replaced by `unmatched[:lost]` or by the whole list; `id_key` truthiness; the set rendering without `sorted`; the snapshot removed in `stage()` or in `pipeline()`; `disallowed_special` removed; each of the seven locations in `check_versions.py` skipped; the CI job's version step removed. Also run the new tests on Python 3.9 and 3.11 and the version check under 3.9.
3. **G5 Security review (veto).** Focus: (a) the audit can no longer be made to under-report by planting an id-less record, and an attacker-chosen record cannot make the attribution loop super-linear (`unmatched` is one list, one slice); (b) the new CI job installs `ruff` and `mypy` from PyPI (dev-only supply-chain surface, bounded by the `lint` extra's version ranges) and uses the same pinned action versions as the existing jobs, with no new permissions or secrets; (c) `tools/check_versions.py` only reads files under the given root; (d) the build-time copy cannot be bypassed for plain containers and its limits are documented; (e) no new runtime dependency, no network use at runtime.
4. **Re-gate** any blocker or major finding with executed evidence before the next step, as in Slice 2.
5. **Close-out:** file the reports under `docs/reviews/foundation-hardening-s3-*.md` and `docs/qa/foundation-hardening-s3-qa.md` (sanitised: no user name, no temporary path, no e-mail, no agent identifier); update the Slice 3 row, the status snapshot and the deviation log of `docs/plans/foundation-hardening.md`; update the programme memory; leave the tree clean and the branch **unpushed** for the human. Report honestly what was not verified: the three-OS CI (it runs when the human pushes; the new `hygiene` job has never run before), Python 3.10, Node 18 and 20, and `pip-audit`.

## What this slice does not do

- **No cross-language fingerprint.** Fingerprints stay language-local; the vectors cover attribution, not fingerprints (ADR-001, ADR-002).
- **The ambient tokenizer and serializer** (`set_tokenizer`, `tokens.scoped`) are not part of a pipeline's fingerprint, and trace pricing with the ambient tokenizer is unchanged (deferred in design section 7, with async `__call__` objects in `shaped`).
- **No fix for the `allowlist` non-mapping item gap** that Slice 2 reported (Python raw `AttributeError`, C# `NullReferenceException`, TypeScript dropping the item): it is a separate change that needs its own Python, vectors, TypeScript and C# cycle; recommended before the next release, and the human may want it ahead of the release cut.
- **No release.** Releasing is the human's call (a version bump across the seven locations, which `tools/check_versions.py` will now police, and the PyPI, npm and NuGet pipelines).

## Self-review (writing-plans checklist)

- **Spec coverage:** AC 28 to 33 each map to a task and a named test (table above); AC 34 is Task 10; AC 35 and 36 are out of this slice by the master plan.
- **Placeholder scan:** every code block is the verified file content or a verified edit; there is no "TBD", "similar to Task N" or undefined name. The only values a task does not spell out are the ones that cannot be known in advance and are labelled: the `pip-audit` result and the first CI run of the `hygiene` job.
- **Type and name consistency:** the names a later task uses (`fake_tiktoken`, `_fp`, `count_tokens`, `trace_dropped_ids`, `__contexel_desc__` / `__contexelDesc`, `Settle`, `IsSet`) are defined in an earlier task or in the same one.
- **Review Focus:** five lines, each with its test named and placed in the task that owns the code.

## Replay result (2026-11-20)

The blocks in this file were applied, in order, to a fresh checkout of `main` at `835454a`; after each task's tests, and again after its implementation, the suites of the languages the task touches were run. Measured, not predicted:

| Task | After its tests | After its implementation |
|---|---|---|
| 1 | Python 479 passed; TypeScript 322 pass; C# 287 passed | (tests only) |
| 2 | Python 2 failed, 483 passed | Python 485 passed |
| 3 | Python 492 passed; TypeScript 5 failed of 337; C# 6 failed of 302 | TypeScript 337 pass; C# 302 passed |
| 4 | Python 9 failed, 496 passed | Python 505 passed |
| 5 | Python 2 failed, 505 passed | Python 507 passed |
| 6 | TypeScript 8 failed of 347 | TypeScript 347 pass |
| 7 | C# 4 failed of 312 | C# 312 passed (0 warnings) |
| 8 | Python: collection error (no module `check_versions`) | Python 527 passed |
| 9 | Python 2 failed, 527 passed | Python 529 passed |
| 10 | (documents only) | Python 529, TypeScript 347, C# 312 |

After Task 10 the 35 files the plan creates or edits (including the regenerated `parity/vectors.json`) were byte-identical, modulo line endings, to the scratch tree the code was verified in. Not covered by this replay: the first CI run of the new `hygiene` job, Linux and macOS, Python 3.10, Node 18 and 20, and `pip-audit`.
