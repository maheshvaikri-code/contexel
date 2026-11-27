# Foundation hardening, Slice 7: Differential fuzz — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A seeded, deterministic corpus of random cases inside the documented parity envelope, computed by the Python canon and replayed in CI by the TypeScript and C# suites, so a divergence between the ports that no hand-written vector anticipated turns the build red (brief AC 36).

**Architecture:** One generator, `parity/generate_fuzz.py`, writes a `cases` file in the format of `parity/vectors.json`. The TypeScript and C# suites replay it with the runners that already replay the shared vectors (`checkCase`, `CaseTests.AssertCase`), so a fuzz case and a vector case are judged by the same code. The corpus is generated in CI (and in the release gate), never committed. **Nothing in `contexel/`, `ts/src/` or `csharp/Contexel/` changes**: this slice is tests, one case-table addition, CI and documentation.

**Tech Stack:** Python 3.9+ standard library and contexel (pytest); `node:test` for TypeScript; xunit 2.9.2 for C#. No new dependency.

**Spec:** brief `docs/briefs/foundation-hardening.md` (AC 36); design `docs/superpowers/specs/2026-11-19-foundation-hardening-design.md` ("Differential fuzz"); ADR-007; master plan `docs/plans/foundation-hardening.md` (Slice 7 row).

**Baseline (verified 2026-11-26 on `542ab28`, `main` after the Slice 6 merge):** Python 1076 passed and 1 skipped (a symlink test, Windows); TypeScript 678; C# 617. **Target after this slice:** Python 1087 passed and 1 skipped (1085 passed and 3 skipped where the benchmark dataset cache is absent); TypeScript 681 passed and 1 skipped with the corpus variable unset, 684 passed with it set; C# 623.

**How this plan was verified:** every block below was written and run in a scratch worktree of `542ab28`; the plan was then generated from those files by a script and **replayed onto a second fresh worktree of `542ab28`** (every created file byte-compared, every edit applied and compared, `parity/vectors.json` regenerated), which matched. Measured on that tree (Windows, Python 3.12, Node 24, .NET 8): generation 11 s for 20,000 cases (37 MB), TypeScript replay 2.6 s, C# replay 6 s. Ten alphabet and value tiers (about 20,000 cases each, 40,000 for the combined run) on four seeds (7, 11, 13, 17) were replayed before the domain was fixed (section "What the measurements decided"). Three mutants were applied to the finished tree: each is caught by the fuzz. Not verified: a CI run on Linux, macOS or Windows runners (the first CI run of the branch is that evidence, and the 60-second target is checked there).

> **Erratum (2026-11-26, found at the final code review of the executed slice):** this plan calls the U+0130 margin new (the table in "What the measurements decided", ruling S7-10 and the open items). It was already recorded in `docs/adr/002-csharp-parity.md` since Slice 5 (ruling S5-13); the branch removed the duplicate entry and the claims. The plan also wired only the release gate's test jobs; the two publish jobs (`npm-publish`, `nuget-publish`) run the replays too and were wired during execution (see the master plan, deviation log).

## Global Constraints

- **Nothing in `contexel/`, `ts/src/` or `csharp/Contexel/` changes.** The code changes are `parity/generate_fuzz.py`, three cases in `parity/parity_cases.py` (and the regenerated `parity/vectors.json`), the C# case adapter (`csharp/Contexel.Tests/CaseTests.cs`, test code), the two new replay tests, one test file, CI and documentation. If a task seems to need a library change, **stop and report**.
- Python >= 3.9 and **zero new dependencies** (standard library only; no `hypothesis`). The generator draws only from `random.Random.random()` (the one method Python keeps stable), so the corpus is byte-identical on every Python version and operating system.
- **The corpus is never committed**: `parity/fuzz-corpus.json` is git-ignored (Task 1). `parity/vectors.json` changes only by the three added cases of Task 2 (regenerate it with `python parity/generate_vectors.py`, never by hand).
- **The network is never used by this plan.** `ts/node_modules` is already installed; if it is missing, **stop and ask** (do not run `npm ci` or `dotnet restore` against the network without the human's word; the NuGet cache is present on this machine).
- No version bump: identifiers change only at a release (the human's call); the work accumulates under `[Unreleased]` in `CHANGELOG.md`.
- One commit per task, Conventional Commits, 72 characters at most (count them). **No `Co-Authored-By` trailer** (the project owner's standing rule, which overrides the harness default). Never push, open a pull request or merge: those are the human's.
- The repository is **public**: no Windows user name, home or temporary path, e-mail address or agent identifier in any file or commit message.
- Tests are never weakened to go green. A fuzz divergence is **fixed or recorded as an ADR margin** (ADR-007, "Process"); it is never filtered, skipped or hidden. If the default corpus diverges when you replay it, **stop and report** the cases (`python parity/generate_fuzz.py --seed 20261126 --show INDEX`): the plan measured zero.
- This machine writes CRLF; the blocks below are LF. Either is fine in the working tree, but **byte-compare each created file with its block** after writing it: the editing tools have in the past turned a backslash-u escape into the character it names, and shell heredocs have collapsed backslashes. (This slice's files avoid backslash-u escapes on purpose: the generator builds every special character from `chr()`.)
- The C# tests are run with `dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo`; the TypeScript tests with `npm test` in `ts/`. Environment variables are passed on the command line in Git Bash (`CONTEXEL_FUZZ_CASES=parity/fuzz-corpus.json dotnet test ...`).

## What the measurements decided

Before this plan was written the generator was prototyped and replayed through both ports at 20,000 cases per run (seeds 7, 11, 13, 17 and the default). The prototype began with the spec's envelope and widened it one character class or value class at a time, so each exclusion below is measured, not assumed.

| Allowed into the corpus | TypeScript | C# | Decision |
|---|---|---|---|
| ASCII words, separators, Latin-1, BMP CJK, Hangul, Cyrillic, emoji | 0 | 0 | in the domain |
| Combining marks (NFC composition, `normalize="nfc"`) | 0 | 0 | in |
| Non-string values (None, bool, numbers, lists, dicts) read by `rescore` and `quarantine` | 0 | 0 | in |
| Numbers from 5e-324 to 2^53 - 1, scores and ints mixed | 0 | 0 | in |
| Control characters, quotes, backslash, U+2028, U+FEFF | 0 | 0 | in |
| Larger inputs (up to 40 records) | 0 | 0 | in (24 at most in the generator) |
| Strict mode, invalid configuration (6 error codes) | 0 | 0 | in (a scalar item only in `input.not_mapping` cases, see S7-6) |
| Astral letters in text that `rescore` reads | 0 | **135** | the known C# margin (Slice 5 ruling S5-8): astral letters only in the field `note` |
| U+0130 in text that `rescore` reads | 0 | **31** (6,000 cases) | **new margin**, recorded (S7-10) |
| U+212A (Kelvin) against a `[A-Z]` quarantine pattern | **1** | 0 | the ADR-001 margin (Unicode case folding); excluded with the other case-special characters |
| `truncate_field(suffix=...)` | 0 | 127 | **a gap in the C# test adapter**, not in the library: fixed (Task 2) |
| a `0.0` score (an empty query, or a query with no word characters) | rejected | | the TypeScript envelope: such a case is redrawn (S7-4, S7-5) |
| a scalar item in a list of records, where the canon does not raise | | not representable | S7-6 |

With the domain fixed, the corpus is 20,000 cases with 0 divergences in both ports, and a defect that the shared vectors miss is caught: lowering the budget floor of `truncate_field` from 1 to 0 leaves the TypeScript vectors green (681 passed) and fails 112 fuzz cases, in TypeScript and in C# alike.

## Review Focus

1. **The 60-second target on the slowest runner.** Measured here (see above) with a wide margin; macOS and Windows CI runners are slower and C# parses a 37 MB file. The first CI run is the evidence. If a replay exceeds 60 seconds, lower `DEFAULT_CASES` in `parity/generate_fuzz.py` and re-pin the digest (ADR-007 names this as an invalidation trigger).
2. **A replay that passes by testing nothing.** Pinned: an unset `CONTEXEL_FUZZ_CASES` fails when `CI` is set (GitHub sets it on every runner, including `release.yml`, so that workflow gets the same two steps, S7-11); a corpus below 1,000 cases, a case count that disagrees with its metadata, duplicate ids, kinds that differ from the generated kinds and a corpus with no error case all fail; a canary test corrupts the first 300 expectations and requires each to be refused.
3. **A divergence at another seed.** Only the default seed gates. The four other seeds measured at plan time found only the margins listed above. A scheduled run over fresh seeds would widen the net; it is not part of this slice (open item 2 below).
4. **Windows and macOS path and encoding behavior.** The variable holds a path relative to the repository root, resolved by each runner; the corpus is ASCII-only JSON (`ensure_ascii`), written as bytes; the generator prints only ASCII. A test pins that the CLI output equals the library output under two `PYTHONHASHSEED` values.
5. **Memory.** The C# runner parses the corpus into dictionaries (about 37 MB of JSON). It ran here without trouble; a hosted runner has several gigabytes.

## Rulings made at plan time (open to the human's correction)

- **S7-1. The corpus is generated, not committed; the variable names its path.** ADR-007 rejected a committed corpus (option C). `CONTEXEL_FUZZ_CASES` is a path relative to the repository root (or absolute). Unset: skipped locally, **failed under `CI`**. Cost if wrong: someone who wants the fuzz locally runs one extra command.
- **S7-2. The replays reuse the vector runners.** `checkCase` (TypeScript) and `CaseTests.AssertCase` (C#, `internal static`, same assembly) judge a fuzz case exactly as they judge a vector case, so the two never drift apart. Cost if wrong: none; a separate runner would be a second thing to keep in step.
- **S7-3. The domain is the measured one** (table above). Cost if wrong: a character class that does diverge is excluded (a coverage hole, recorded in ADR-007); one that does not is fuzzed.
- **S7-4. A case outside the envelope is redrawn, not dropped,** from a derived seed (`attempt`), so the corpus always has exactly the requested number of cases and case `i` still depends on `(seed, i)` alone. Every redraw is counted by reason in `_meta.redrawn` (24 in 20,000 at the default seed), and a test requires them to be few (under 5%) and explained. Cost if wrong: none.
- **S7-5. The envelope is checked at every stage, not only on the final output.** A score of `0.0` that a later stage serializes costs a different number of tokens in TypeScript (it prints `0`), so a pipeline whose intermediate output holds an integer-valued float is outside the envelope even when the final expectation does not show it (found at plan time: a `trace_report` diverged). Cost if wrong: a slightly narrower domain.
- **S7-6. A scalar or null item in a list of records appears only in cases that expect `input.not_mapping`.** The C# value model is a list of mappings (ADR-002): it cannot hold `5` or `"x"`, and the canon passes such an item through `trim_to_budget` and `dedupe`. Measured: 45 divergences in 20,000 strict cases before the rule, 0 after. Cost if wrong: strict-mode shape errors are fuzzed only where every port can express them.
- **S7-7. The default seed is 20261126 and the default size 20,000 cases.** Only this corpus gates. Cost if wrong: see Review Focus 1 and 3.
- **S7-8. The generator draws only from `random()`** and pins its first draws and the digest of the first 300 cases' inputs. `randint`, `choice` and `sample` are not guaranteed stable across Python versions; `random()` is. The pinned digest depends on the canon only through the redraw rule (a redrawn case changes the draw sequence), so a canon change that alters a score's integer-valued-ness re-pins it (say so in the commit). Cost if wrong: a re-pin.
- **S7-9. The C# adapter gap is fixed, not recorded as a margin.** The library supports `suffix`; the test adapter did not pass it on. Task 2 adds three shared cases (`custom_suffix_is_counted_before_the_cut`, `empty_suffix_leaves_the_whole_budget`, `astral_suffix_is_one_code_point`), so the vectors keep the finding.
- **S7-10. U+0130 is recorded as an open margin, not fixed here.** Python and JavaScript lower-case it to `i` + U+0307; .NET's `ToLowerInvariant` leaves it, so C# `rescore` tokenizes text that contains it differently (word and stem modes alike). A fix would change C# behavior, which this test-and-CI slice does not do. It goes in ADR-007 and ADR-002, and the character is excluded from the generator. Cost if wrong: one character differs in C# `rescore`; the human decides later, as for S5-8.
- **S7-11. `release.yml` generates and replays the corpus too.** GitHub sets `CI` on every runner, so without the two steps the release gate's TypeScript and C# jobs would fail on the guard of S7-1. Cost if wrong: about half a minute per release job; to make the release gate independent of the fuzz, revert the two release edits and replace the guard's `CI` test with an explicit variable.
- **S7-12. No library change, no version bump, no release.** If replaying the default corpus finds a divergence the plan did not measure, it is triaged by ADR-007's process (fix with a shared case, or record a margin and narrow the generator in the same change); **stop and ask** if it can be neither (master plan, stop-and-ask triggers).
- **S7-13. The Python tests use small corpora** (400 and 2,000 cases), so they cost about three seconds in the default suite; the 20,000-case corpus is exercised by the two replays.

## Coverage of the acceptance criteria

| AC 36 says | Where |
|---|---|
| a seeded differential-fuzz corpus | Task 1 (`parity/generate_fuzz.py`); determinism, the pinned draws and digest, `--show` reproduction |
| generated inside the documented parity envelope | Task 1: `outside_envelope` (input, arguments, expectation and every intermediate output), `test_fuzz_corpus_is_deterministic_and_inside_the_envelope`, `test_the_domain_rules_hold_in_every_case`, `test_the_envelope_check_can_fail` |
| replayed by the TypeScript and C# suites in CI | Tasks 3, 4, 5 |
| every divergence is either fixed or recorded as an ADR margin that narrows the fuzz domain | Task 2 (the adapter gap, fixed, with shared cases) and Task 6 (margins in ADR-007 and ADR-002); the generator is narrowed in Task 1 |
| none is filtered silently | redraws counted in `_meta.redrawn` and bounded by a test; both replays list every divergence (first 20) with the reproduction command |
| target runtime under 60 seconds | measured (see above); the first CI run confirms it |

## Execution notes

- The branch is `feat/hardening-s7-differential-fuzz`, from `main` at `542ab28` (or later). The plan's own branch is `docs/hardening-s7-plan`; the plan merges first.
- In an edit pair, the text between the fences is the exact string to find and the exact string to put in its place; where a string ends with a newline, its block ends with an empty line. Each `old` string occurs exactly once in its file (if it does not, **stop and report**).
- Tasks run in order: 1 (generator), 2 (shared cases and the C# adapter), 3 (TypeScript replay), 4 (C# replay), 5 (CI), 6 (documentation). Tasks 3 and 4 need the corpus from Task 1: `python parity/generate_fuzz.py --out parity/fuzz-corpus.json` (ignored by git).
- Every task ends with its suites green and one commit. The whole-branch gates (code review, QA with mutation testing, security review) run after Task 6; their mutants should include: a corrupted `expect` in a port, the budget floor of `truncate_field`, the C# adapter without `suffix`, the replay with `CONTEXEL_FUZZ_CASES` unset under `CI`, and a generator that stops redrawing.
- After the gates the evidence is filed under `docs/reviews/` and `docs/qa/` and the master plan is updated, as in Slice 6.

## Tasks

### Task 0: Baseline and branch (no commit)

- [ ] **Step 1: Branch from `main`.**

```bash
git switch main && git pull --ff-only
git switch -c feat/hardening-s7-differential-fuzz
git log --oneline -1
```

Expected: the head is the merge of the Slice 6 plan or a later `main`.

- [ ] **Step 2: Record the baseline** (the numbers the later tasks compare against).

```bash
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*' 2>&1 | tail -1
(cd ts && npm test 2>&1 | grep -E "^ℹ (tests|pass|fail|skipped)")
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo 2>&1 | grep -E "Passed!|Failed!"
```

Expected: `1076 passed, 1 skipped`; TypeScript `tests 678`, `pass 678`, `fail 0`; C# `Passed: 617`. Also run `python -m ruff check contexel`, `python -m mypy`, `python tools/check_versions.py`, `python tools/site_check.py` and `python tools/check_benchmark_numbers.py`: all clean. (`tests/test_doctrine_*` are git-ignored here and one of them fails with or without any change; they are excluded on purpose.) **If a number differs, stop and report it.**

### Task 1: The generator and its tests

**Files:**
- Create: `tests/test_fuzz_generator.py`, `parity/generate_fuzz.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces (used by every later task): `python parity/generate_fuzz.py --out FILE [--seed N] [--cases N]` writes a corpus `{"_meta": {...}, "cases": [...]}` (ASCII JSON, one line); `--seed N --show INDEX` prints one case. The case format is that of `parity/vectors.json` (`id`, `stage`, `args`, `input`, `expect` or `expect_error`, optional `strict`); no case uses `"$fixture"`. `_meta` has `format`, `seed`, `case_count`, `kind_counts`, `error_codes`, `strict_cases`, `redrawn`. Case ids are `fuzz/<seed>/<index, five digits>/<kind>`.
- Library: `generate_fuzz.build(seed, count)`, `make_case(seed, index, redrawn=None)`, `outside_envelope(case, outcome)`, `dumps(corpus)`, the class `Gen`, and the constants `KINDS`, `RECORD_KINDS`, `EXCLUDED`, `DEFAULT_SEED`, `DEFAULT_CASES`.

- [ ] **Step 1: Write the tests (they fail first).** Create `tests/test_fuzz_generator.py` with exactly this content:

````python file:tests/test_fuzz_generator.py
"""AC 36: the differential fuzz generator (parity/generate_fuzz.py). Nothing here needs
TypeScript or C#: the replays have their own tests (ts/test/fuzz.test.ts,
csharp/Contexel.Tests/FuzzTests.cs). What is pinned here is what makes the corpus worth
replaying: it is deterministic, it stays inside the documented parity envelope, it covers every
kind of case, and the checks that keep it inside the envelope can fail."""
import hashlib
import json
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "parity"))

import generate_fuzz as gf  # noqa: E402
from parity_cases import ALLOWED_KEYS, assert_in_envelope, outcome  # noqa: E402

SMALL = 400
LARGE = 2000
# random() is the only generator method Python promises to keep stable across versions: these
# draws and this digest of the first 300 cases (their inputs and arguments, not the canon's answers)
# are the same on every Python and operating system. Change them only with the generator.
PINNED_DRAWS = [323, 150, 650, 72, 535, 365]
PINNED_FIRST_300 = "b0094c7ee3bd7ec0b69c1693a7b4e44290cc4440b22b4dd6372966c363c63635"
ERROR_CODES = {"config.contradictory", "config.empty", "config.invalid_pattern",
               "config.invalid_value", "input.field_conflict", "input.not_mapping"}


@pytest.fixture(scope="module")
def small():
    return gf.build(gf.DEFAULT_SEED, SMALL)


@pytest.fixture(scope="module")
def large():
    return gf.build(gf.DEFAULT_SEED, LARGE)


def _run_cli(*args, hashseed="0"):
    env = {**os.environ, "PYTHONHASHSEED": hashseed, "PYTHONPATH": str(ROOT)}
    return subprocess.run([sys.executable, str(ROOT / "parity" / "generate_fuzz.py"), *args],
                          capture_output=True, check=True, env=env, cwd=str(ROOT))


def test_fuzz_corpus_is_deterministic_and_inside_the_envelope(small, tmp_path):
    again = gf.build(gf.DEFAULT_SEED, SMALL)
    assert gf.dumps(small) == gf.dumps(again)
    assert gf.dumps(small).isascii()                      # one byte stream on every platform
    for hashseed in ("0", "1"):                           # the corpus never depends on hash order
        out = tmp_path / f"corpus-{hashseed}.json"
        _run_cli("--cases", str(SMALL), "--out", str(out), hashseed=hashseed)
        assert out.read_bytes() == gf.dumps(small).encode("ascii")
    ids = set()
    for case in small["cases"]:
        assert set(case) <= ALLOWED_KEYS, case["id"]
        assert case["id"] not in ids
        ids.add(case["id"])
        stored = {k: case[k] for k in ("expect", "expect_error") if k in case}
        assert outcome(case, []) == stored, case["id"]    # the canon still gives the same answer
        assert gf.outside_envelope(case, stored) is None, case["id"]
        for part, where in ((case["input"], "input"), (case["args"], "args"), (stored.get("expect"), "expect")):
            assert_in_envelope(part, case["id"] + "." + where)
    assert small["_meta"]["case_count"] == SMALL == len(small["cases"])


def test_the_generator_and_the_first_cases_are_pinned():
    g = gf.Gen(7)
    assert [g.below(1000) for _ in range(6)] == PINNED_DRAWS
    cases = [gf.make_case(gf.DEFAULT_SEED, i) for i in range(300)]
    drawn = [{k: c.get(k) for k in ("id", "stage", "args", "input", "strict")} for c in cases]
    digest = hashlib.sha256(json.dumps(drawn, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
    assert digest.hexdigest() == PINNED_FIRST_300


def test_every_kind_error_code_and_strict_mode_is_covered(large):
    meta = large["_meta"]
    assert set(meta["kind_counts"]) == set(gf.KINDS)
    assert min(meta["kind_counts"].values()) >= 20, meta["kind_counts"]
    assert set(meta["error_codes"]) == ERROR_CODES
    assert min(meta["error_codes"].values()) >= 1, meta["error_codes"]
    assert meta["strict_cases"] >= 100
    wide = [c for c in large["cases"] if any(ord(ch) > 0xFFFF for ch in json.dumps(c["input"], ensure_ascii=False))]
    assert len(wide) >= 100                               # astral text really is generated (in `note`)
    assert sum(1 for c in large["cases"] if c["stage"] == "rescore" and c["args"].get("match") == "stem") >= 10


def _walk(value, key=None):
    """Every string in the value, with the record key it sits under (None at the top level)."""
    if isinstance(value, str):
        yield key, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _walk(v, k)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v, key)


def _stage_specs(case):
    if case["stage"] in gf.RECORD_KINDS:
        yield case
    for spec in case["args"].get("stages", []):
        yield spec


def test_the_domain_rules_hold_in_every_case(large):
    excluded = set(gf.EXCLUDED)
    for case in large["cases"]:
        for key, text in list(_walk(case["input"])) + list(_walk(case["args"])):
            assert not excluded & set(text), (case["id"], "a case-special character")
            for ch in text:
                if ord(ch) > 0xFFFF and unicodedata.category(ch).startswith("L"):
                    assert key == "note", (case["id"], "an astral letter outside `note`", key)
            assert not any(0xD800 <= ord(ch) <= 0xDFFF for ch in text), "a lone surrogate"
        for spec in _stage_specs(case):
            if spec["stage"] == "rescore":
                assert "note" not in spec["args"].get("fields", []), case["id"]
        items = case["input"] if case["stage"] in gf.RECORD_KINDS + ["pipeline", "shaped", "join",
                                                                    "trace_report", "trace_dropped_ids"] else []
        if any(not isinstance(i, dict) for i in items):
            assert case.get("expect_error", {}).get("code") == "input.not_mapping", case["id"]


def test_a_case_depends_on_its_seed_and_index_alone(large):
    for index in (0, 17, 1999):
        assert gf.make_case(gf.DEFAULT_SEED, index) == large["cases"][index]
    shown = json.loads(_run_cli("--seed", str(gf.DEFAULT_SEED), "--show", "17").stdout.decode("ascii"))
    assert shown == large["cases"][17]
    assert gf.make_case(gf.DEFAULT_SEED + 1, 17) != large["cases"][17]


def test_the_envelope_check_can_fail():
    def verdict(case):
        return gf.outside_envelope(case, outcome(case, []))

    base = {"id": "x", "stage": "select", "args": {"fields": ["a"]}, "input": [{"a": 1}]}
    assert verdict(base) is None
    assert "integer-valued float" in verdict({**base, "input": [{"a": 1.0}]})
    assert "NaN" in verdict({**base, "input": [{"a": float("nan")}]})
    assert "integer beyond 2**53" in verdict({**base, "input": [{"a": 2 ** 53 + 1}]})
    # an empty query scores every record 0.0. A final stage that drops the score hides it from the
    # expectation; the intermediate check still sees it
    assert verdict({"id": "z", "stage": "rescore", "args": {"query": ""}, "input": [{"snippet": "a"}]}
                   ).startswith("expect: integer-valued float")
    pipe = {"id": "y", "stage": "pipeline", "input": [{"snippet": "zzz"}],
            "args": {"stages": [{"stage": "rescore", "args": {"query": "", "fields": ["snippet"]}},
                                {"stage": "select", "args": {"fields": ["snippet"]}}]}}
    assert outcome(pipe, [])["expect"] == [{"snippet": "zzz"}]
    assert verdict(pipe).startswith("intermediate: integer-valued float")


def test_a_redraw_is_counted_and_a_hopeless_case_is_an_error(monkeypatch):
    real = gf.draw_case
    calls = {"n": 0}

    def flaky(seed, index, attempt):
        calls["n"] += 1
        if attempt < 2:
            return {"id": "x", "stage": "select", "args": {"fields": ["a"]}, "input": [{"a": 1.0}]}
        return real(seed, index, attempt)

    monkeypatch.setattr(gf, "draw_case", flaky)
    redrawn = {}
    gf.make_case(gf.DEFAULT_SEED, 3, redrawn)
    assert redrawn == {"input: integer-valued float 1.0": 2}
    monkeypatch.setattr(gf, "draw_case", lambda seed, index, attempt: {
        "id": "x", "stage": "select", "args": {"fields": ["a"]}, "input": [{"a": 1.0}]})
    with pytest.raises(AssertionError, match="no case inside the envelope"):
        gf.make_case(gf.DEFAULT_SEED, 3)


def test_the_redraws_of_the_corpus_are_few_and_explained(large):
    redrawn = large["_meta"]["redrawn"]
    assert sum(redrawn.values()) < LARGE // 20, redrawn   # under 5% of the cases
    assert all(reason.startswith(("expect:", "intermediate:", "input:", "args:", "canon raised"))
               for reason in redrawn), redrawn

````

- [ ] **Step 2: Run them; they fail.**

```bash
PYTHONPATH=. python -m pytest tests/test_fuzz_generator.py -q 2>&1 | tail -3
```

Expected: an error collecting the module (`ModuleNotFoundError: No module named 'generate_fuzz'`).

- [ ] **Step 3: Write the generator.** Create `parity/generate_fuzz.py` with exactly this content:

````python file:parity/generate_fuzz.py
"""Seeded differential fuzz corpus for the cross-language parity suites (ADR-007, AC 36).

    python parity/generate_fuzz.py --out parity/fuzz-corpus.json [--seed N] [--cases N]
    python parity/generate_fuzz.py --seed N --show INDEX      # one case, to reproduce a divergence

The Python canon computes every expectation. The output is a ``cases`` file in
the format of ``parity/vectors.json`` (see ``parity_cases.py``), so the
TypeScript and C# suites replay it with the runners that already replay the
shared vectors (``ts/test/fuzz.test.ts``, ``csharp/Contexel.Tests/FuzzTests.cs``).
The corpus is generated, never committed (it is ignored by git).

The generator draws only from ``random.Random.random()``, the one method Python
guarantees to keep stable, so a seed gives the same corpus on every Python
version and operating system. Case ``i`` depends on ``(seed, i)`` alone: a
divergence is reproduced from its index without regenerating the rest.

The domain is the documented parity envelope (ADR-001 4a, ADR-002 3, ADR-007):
JSON data only, no NaN or Inf, no integer-valued floats (a score of 0.0 that a
later stage serializes is one: the case is redrawn), integers within 2**53, no
case-special characters (U+0130 among them), and astral letters only in the
``note`` field, which ``rescore`` never reads (the C# tokenizer margin of
ADR-006). A scalar item in a list of records appears only in cases that expect
``input.not_mapping``: a C# list holds mappings. Every redraw is counted in
``_meta.redrawn``; nothing is dropped silently.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from contexel import ContexelError, as_records, strict  # noqa: E402
from parity_cases import _pipe, assert_in_envelope, outcome  # noqa: E402

FORMAT = 1
DEFAULT_SEED = 20261126
DEFAULT_CASES = 20000
MAX_ATTEMPTS = 50

# ---------------------------------------------------------------------------
# Alphabets. Every character is written as a code point: this file has no
# non-ASCII source text and no backslash escapes.
# ---------------------------------------------------------------------------
LATIN1 = [chr(c) for c in (0xE9, 0xE8, 0xFC, 0xF1, 0xE5, 0xC9, 0xDC, 0xD1)]
BMP_CJK = [chr(c) for c in (0x65E5, 0x672C, 0x8A9E, 0x4E2D, 0x6587)]
HANGUL = [chr(0xD55C), chr(0xAE00)]
CYRILLIC = [chr(c) for c in (0x41F, 0x440, 0x438, 0x432, 0x435, 0x442)]
EMOJI = [chr(0x1F600), chr(0x1F680)]
ASTRAL_LETTERS = [chr(0x20000), chr(0x20001), chr(0x2A6D6)]   # CJK extension B: caseless letters
COMBINING = [chr(0x301), chr(0x302), chr(0x323)]
CONTROL = [chr(0), chr(7), chr(27), chr(127), chr(0x2028), chr(0x2029), chr(0x85), chr(0xA0),
           chr(0x200B), chr(0xFEFF), chr(92), chr(34), chr(39)]
# Characters outside the envelope, kept out of every generated string (a test pins this):
# case-special letters, where the runtimes' case tables differ (ADR-001, ADR-002, ADR-007).
EXCLUDED = [chr(c) for c in (0x130, 0x131, 0x17F, 0xDF, 0x212A, 0x212B, 0x1E9E, 0x3A3, 0x3C2, 0x1C5)]

WORDS = ["retry", "backoff", "jitter", "parse", "parsing", "parsed", "config", "value", "values",
         "error", "errors", "cache", "caches", "the", "of", "and", "a", "x", "Retry", "BACKOFF",
         "ignore all previous instructions", "disregard the above", "secret", "foo123", "bar42",
         "42", "3.14", "it's", 'say "hi"', "(paren)", "a-b", "snake_case", "tab\tsep"]
NARROW = (WORDS + ["caf" + LATIN1[0], "na" + chr(0xEF) + "ve", "r" + LATIN1[0] + "sum" + LATIN1[0],
                   "".join(BMP_CJK[:3]), "".join(BMP_CJK[3:]), HANGUL[0] + HANGUL[1], "".join(CYRILLIC),
                   "emoji" + EMOJI[0], EMOJI[1],
                   "cafe" + COMBINING[0], "a" + COMBINING[1] + COMBINING[2],
                   chr(0x1112) + chr(0x1161) + chr(0x11AB)]
          + ["a" + c + "b" for c in CONTROL] + ["".join(CONTROL[:5])])
WIDE = NARROW + ["x" + ASTRAL_LETTERS[0], "".join(ASTRAL_LETTERS), ASTRAL_LETTERS[1] + "s", ASTRAL_LETTERS[2]]
SEPS = [" ", " ", " ", "  ", "\n", "\r\n", "\n\n", "\n\n\n", ", ", ". ", "\t"]
NUMBERS = [-3, 0, 7, 2 ** 53 - 1, -(2 ** 53 - 1), 10 ** 15, 1e-5, 1.5e-7, 123456789.123,
           4503599627370495.5, 0.1 + 0.2, -2.5, 5e-324, 1.5e-300, 0.5, 1e15 + 0.5, 99999.99999,
           0.0001, 1234567.891]

# Field roles. ``note`` alone may hold astral letters; ``rescore`` never reads it.
TEXT_FIELDS = ["snippet", "title", "path", "text"]
SCALAR_FIELDS = TEXT_FIELDS + ["note", "line", "source", "score", "hits"]
ANY_FIELDS = SCALAR_FIELDS + ["tags", "meta"]
RESCORE_FIELDS = [f for f in ANY_FIELDS if f != "note"]
RECORD_KINDS = ["select", "dedupe", "allowlist", "quarantine", "rescore", "rank",
                "truncate_field", "trim_to_budget", "split"]
OTHER_KINDS = ["merge", "stem", "as_records", "join", "text_pipeline", "pipeline", "shaped",
               "trace_report", "trace_dropped_ids"]
KINDS = RECORD_KINDS + OTHER_KINDS
WEIGHT = {"pipeline": 3, "trace_dropped_ids": 2, "text_pipeline": 2, "shaped": 1, "trace_report": 1}
NO_ITEM_CHECK = ("merge", "stem", "as_records", "text_pipeline")


class Gen:
    """Draws from ``random()`` alone (see the module docstring)."""

    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed).random

    def below(self, n: int) -> int:
        return int(self._random() * n)

    def between(self, lo: int, hi: int) -> int:
        return lo + self.below(hi - lo + 1)

    def chance(self, p: float) -> bool:
        return self._random() < p

    def choice(self, seq: Sequence[Any]) -> Any:
        return seq[self.below(len(seq))]

    def sample(self, seq: Sequence[Any], k: int) -> List[Any]:
        pool = list(seq)
        return [pool.pop(self.below(len(pool))) for _ in range(min(k, len(pool)))]

    def pick(self, seq: Sequence[Any], lo: int = 1, hi: int = 3) -> List[Any]:
        return self.sample(seq, self.between(lo, hi))

    def real(self) -> float:
        return self._random()


def text(g: Gen, lo: int = 0, hi: int = 12, wide: bool = False) -> str:
    pool = WIDE if wide else NARROW
    return "".join(g.choice(pool) + g.choice(SEPS) for _ in range(g.between(lo, hi)))


def fraction(g: Gen) -> float:
    value = round(g.real() * 10 + 0.001, 3)
    return value + 0.001 if value.is_integer() else value


def number(g: Gen) -> Any:
    return g.choice(NUMBERS) if g.chance(0.5) else g.choice([g.between(0, 9), fraction(g)])


def record(g: Gen) -> Dict[str, Any]:
    rec: Dict[str, Any] = {
        "path": g.choice(["src/a.py", "src/b.py", "docs/guide.md", "tests/t.py", "web/x.txt"]),
        "line": g.between(1, 6),
        "source": g.choice(["repo", "docs", "web", None]),
        "snippet": text(g, 0, 8),
        "title": text(g, 0, 3),
        "note": text(g, 0, 4, wide=True),
        "text": text(g, 0, 12),
        "score": number(g),
        "hits": number(g),
        "tags": g.choice([[], ["a"], ["a", "b"]]),
        "meta": g.choice([{}, {"k": 1}, {"k": {"z": None}}, {"k": [1, 2.5, "s"]}]),
    }
    for key in list(rec):
        if g.chance(0.12):
            del rec[key]
    return rec


def records(g: Gen) -> List[Dict[str, Any]]:
    limit = 24 if g.chance(0.06) else 8
    out: List[Dict[str, Any]] = []
    for _ in range(g.between(0, limit)):
        if out and g.chance(0.2):
            out.append(json.loads(json.dumps(g.choice(out))))      # an exact duplicate
        else:
            out.append(record(g))
    return out


# ---------------------------------------------------------------------------
# Stage arguments: valid ones, and a table of invalid ones for the error cases.
# ---------------------------------------------------------------------------
def args_for(kind: str, g: Gen) -> Dict[str, Any]:
    if kind == "select":
        return {"fields": g.pick(ANY_FIELDS + ["nope"], 1, 4)}
    if kind == "dedupe":
        return {"key": g.choice([None, g.choice(SCALAR_FIELDS), g.pick(SCALAR_FIELDS, 1, 2)])}
    if kind == "allowlist":
        pool = ["repo", "docs", "web", None, 1, 2, 3, 0, True, False, 2.5, "a", "src/a.py"]
        return {"field": g.choice(["source", "line", "score", "hits", "title", "path"]),
                "allowed": g.choice([g.sample(pool, g.between(1, 4)), g.choice(["repo", "docs"])])}
    if kind == "quarantine":
        a: Dict[str, Any] = {"fields": g.pick(ANY_FIELDS, 1, 3)}
        if g.chance(0.4):
            a["patterns"] = g.pick(["secret", r"foo\d+", r"b(a|o)r", r"[A-Z]{3,}", "42"], 1, 2)
            if g.chance(0.5):
                a["replace_patterns"] = True
        if g.chance(0.4):
            a["action"] = g.choice(["drop", "flag"])
        if g.chance(0.15):
            a["into"] = g.choice(["flagged", "q"])
        if g.chance(0.3):
            a["normalize"] = g.choice([None, "nfc"])
        return a
    if kind == "rescore":
        a = {"query": g.choice([text(g, 1, 3), [g.choice(NARROW), g.choice(NARROW)], g.choice(NARROW)]),
             "fields": g.pick(RESCORE_FIELDS, 1, 3)}
        if g.chance(0.2):
            a["into"] = g.choice(["rel", "s2"])
        if g.chance(0.3):
            a["proximity"] = g.choice([True, False])
        if g.chance(0.4):
            a["match"] = g.choice(["word", "stem"])
        if g.chance(0.3):
            a["normalize"] = g.choice([None, "nfc"])
        return a
    if kind == "rank":
        return {"by": g.choice(["score", "line", "hits", "title", "path", "note"]),
                "desc": g.choice([True, False])}
    if kind == "truncate_field":
        a = {"field": g.choice(TEXT_FIELDS + ["note"]), "max_tokens": g.between(0, 20)}
        if g.chance(0.3):
            a["suffix"] = g.choice(["...", "~", chr(0x2026), ""])
        return a
    if kind == "trim_to_budget":
        a = {"max_tokens": g.between(0, 1500 if g.chance(0.2) else 400)}
        if g.chance(0.4):
            a["min_records"] = g.between(0, 3)
        return a
    if kind == "split":
        by = g.choice(["lines", "paragraphs", "size"])
        a = {"field": g.choice(["text", "snippet", "note"]), "by": by}
        if by == "size":
            a["size"] = g.between(1, 30)
        if g.chance(0.2):
            a["into"] = g.choice(["c", "part"])
        return a
    raise AssertionError(kind)


BAD_ARGS: Dict[str, List[Dict[str, Any]]] = {
    "select": [{"fields": []}, {"fields": "a"}],
    "dedupe": [{"key": []}, {"key": ""}],
    "allowlist": [{"field": "", "allowed": ["x"]}, {"field": "source", "allowed": []}],
    "quarantine": [{"fields": ["snippet"], "action": "allow"}, {"fields": []},
                   {"patterns": ["("]}, {"normalize": "NFC"}],
    "rescore": [{"query": "x", "match": "fuzzy"}, {"query": "x", "normalize": "nfd"}],
    "rank": [{"by": ""}],
    "truncate_field": [{"field": "snippet", "max_tokens": -1}, {"field": "", "max_tokens": 3}],
    "trim_to_budget": [{"max_tokens": -5}, {"max_tokens": 5, "min_records": -1}],
    "split": [{"by": "words"}, {"by": "size"}, {"by": "lines", "size": 3}, {"by": "size", "size": 0}],
}


def stage_args(kind: str, g: Gen, error_rate: float) -> Dict[str, Any]:
    return g.choice(BAD_ARGS[kind]) if g.chance(error_rate) else args_for(kind, g)


def specs(g: Gen, lo: int = 1, hi: int = 5) -> List[Dict[str, Any]]:
    kinds = [g.choice(RECORD_KINDS) for _ in range(g.between(lo, hi))]
    return [{"stage": k, "args": stage_args(k, g, 0.06)} for k in kinds]


STEMS = ["pars", "test", "load", "stop", "plan", "class", "stat", "quer", "stud", "valu", "fil", "run",
         "hit", "log", "need", "string", "bu", "gla"]
ENDS = ["", "s", "es", "ies", "ied", "ing", "ed", "ings", "eds", "ss", "us", "is", "e", "y", "ly"]


def stem_words(g: Gen) -> List[str]:
    out = []
    for _ in range(g.between(1, 12)):
        word = g.choice(STEMS) + g.choice(ENDS)
        if g.chance(0.15):
            word = word + word[-1] + g.choice(["ing", "ed"])
        out.append(word.upper() if g.chance(0.1) else word)
    return out


def payload(g: Gen) -> Any:
    return g.choice([
        text(g, 0, 30),
        [text(g, 0, 6) for _ in range(g.between(0, 4))],
        [record(g) for _ in range(g.between(0, 3))],
        record(g),
        [text(g, 0, 4), record(g), g.between(0, 9), None, [1, "a"]],
    ])


def draw_case(seed: int, index: int, attempt: int) -> Dict[str, Any]:
    g = Gen((seed * 1_000_003 + index) * 101 + attempt)
    kind = g.choice([k for k in KINDS for _ in range(WEIGHT.get(k, 2))])
    cid = "fuzz/%d/%05d/%s" % (seed, index, kind)
    if kind in RECORD_KINDS:
        case = {"id": cid, "stage": kind, "args": stage_args(kind, g, 0.15), "input": records(g)}
        return with_strict(case, g)
    if kind == "merge":
        args: Dict[str, Any] = {}
        if g.chance(0.6):
            args["schema"] = {"title": ["title", "path"], "url": ["source", "path"]}
            if g.chance(0.5):
                args["dedupe_key"] = g.choice(["title", "url"])
        return {"id": cid, "stage": kind, "args": args,
                "input": [records(g) for _ in range(g.between(0, 3))]}
    if kind == "stem":
        return {"id": cid, "stage": kind, "args": {}, "input": stem_words(g)}
    if kind == "as_records":
        return {"id": cid, "stage": kind,
                "args": {} if g.chance(0.7) else {"field": g.choice(["t", "body"])}, "input": payload(g)}
    if kind == "join":
        return {"id": cid, "stage": kind,
                "args": {"field": g.choice(["text", "snippet"]), "sep": g.choice(["", "\n", " | "])},
                "input": records(g)}
    if kind == "text_pipeline":
        args = {"stages": specs(g, 1, 4)}
        if g.chance(0.5):
            args["field"] = g.choice(["text", "snippet"])
        if g.chance(0.5):
            args["sep"] = g.choice(["", "\n"])
        return {"id": cid, "stage": kind, "args": args, "input": payload(g)}
    if kind in ("pipeline", "shaped"):
        return with_strict({"id": cid, "stage": kind, "args": {"stages": specs(g)}, "input": records(g)}, g)
    args = {"stages": specs(g)}
    if kind == "trace_dropped_ids":
        args["id_field"] = g.choice(["path", "title", "line"])
    elif g.chance(0.6):
        args["id_field"] = g.choice(["path", "title"])
    return {"id": cid, "stage": kind, "args": args, "input": records(g)}


def with_strict(case: Dict[str, Any], g: Gen) -> Dict[str, Any]:
    """A quarter of the cases run in strict mode; some of those carry a scalar or null item."""
    if g.chance(0.25):
        case["strict"] = True
        if case["input"] and g.chance(0.4):
            case["input"].insert(g.below(len(case["input"]) + 1), g.choice([None, 5, "x"]))
    return case


# ---------------------------------------------------------------------------
# The envelope, and the canon's outcome.
# ---------------------------------------------------------------------------
def outside_envelope(case: Dict[str, Any], got: Dict[str, Any]) -> Optional[str]:
    """Why a case lies outside the parity envelope, or None. Besides the input, the arguments and
    the expectation, every intermediate output of a pipeline is checked: a score of 0.0 that a
    later stage serializes costs a different token count in TypeScript."""
    for part, where in ((case["input"], "input"), (case["args"], "args"), (got.get("expect"), "expect")):
        try:
            assert_in_envelope(part, where)
        except AssertionError as error:
            return "%s: %s" % (where, str(error).split(": ", 1)[1][:40])
    stages = case["args"].get("stages")
    if not stages or case["stage"] == "merge":
        return None
    records_in = case["input"]
    if case["stage"] == "text_pipeline":
        records_in = as_records(records_in, case["args"].get("field", "text"))
    for count in range(1, len(stages) + 1):
        try:
            if case.get("strict"):
                with strict():
                    out = _pipe(stages[:count])(json.loads(json.dumps(records_in)))
            else:
                out = _pipe(stages[:count])(json.loads(json.dumps(records_in)))
        except ContexelError:
            return None
        try:
            assert_in_envelope(out, "stage %d" % count)
        except AssertionError as error:
            return "intermediate: %s" % str(error).split(": ", 1)[1][:40]
    return None


def only_mappings_or_not_mapping_error(case: Dict[str, Any], got: Dict[str, Any]) -> bool:
    if case["stage"] in NO_ITEM_CHECK or all(isinstance(i, dict) for i in case["input"]):
        return True
    return got.get("expect_error", {}).get("code") == "input.not_mapping"


def make_case(seed: int, index: int, redrawn: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Case ``index`` of the corpus for ``seed``: the first draw that lies inside the envelope,
    with the canon's outcome. Each redraw is counted in ``redrawn`` by reason."""
    redrawn = redrawn if redrawn is not None else {}
    for attempt in range(MAX_ATTEMPTS):
        case = draw_case(seed, index, attempt)
        try:
            got = outcome(case, [])
        except ContexelError:
            raise
        except Exception as error:   # the canon raised something that is not a contexel error
            reason = "canon raised %s" % type(error).__name__
            redrawn[reason] = redrawn.get(reason, 0) + 1
            continue
        if not only_mappings_or_not_mapping_error(case, got):
            case["input"] = [i for i in case["input"] if isinstance(i, dict)]
            got = outcome(case, [])
        reason = outside_envelope(case, got)
        if reason is None:
            return {**case, **got}
        redrawn[reason] = redrawn.get(reason, 0) + 1
    raise AssertionError("no case inside the envelope for seed %d index %d" % (seed, index))


def build(seed: int = DEFAULT_SEED, count: int = DEFAULT_CASES) -> Dict[str, Any]:
    redrawn: Dict[str, int] = {}
    cases = [make_case(seed, i, redrawn) for i in range(count)]
    kinds: Dict[str, int] = {}
    codes: Dict[str, int] = {}
    for c in cases:
        kinds[c["stage"]] = kinds.get(c["stage"], 0) + 1
        if "expect_error" in c:
            code = c["expect_error"]["code"]
            codes[code] = codes.get(code, 0) + 1
    meta = {"format": FORMAT, "generated_by": "parity/generate_fuzz.py (python contexel canon)",
            "adr": "docs/adr/007-vector-format-v2-and-differential-fuzz.md",
            "seed": seed, "case_count": len(cases), "kind_counts": dict(sorted(kinds.items())),
            "error_codes": dict(sorted(codes.items())), "strict_cases": sum(1 for c in cases if c.get("strict")),
            "redrawn": dict(sorted(redrawn.items()))}
    return {"_meta": meta, "cases": cases}


def dumps(corpus: Dict[str, Any]) -> str:
    return json.dumps(corpus, ensure_ascii=True, separators=(",", ":")) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--cases", type=int, default=DEFAULT_CASES)
    parser.add_argument("--out", help="write the corpus to this file")
    parser.add_argument("--show", type=int, metavar="INDEX", help="print case INDEX of the seed and exit")
    args = parser.parse_args(argv)
    if args.show is not None:
        print(json.dumps(make_case(args.seed, args.show), indent=1, ensure_ascii=True))
        return 0
    if not args.out:
        parser.error("--out is required (or --show INDEX)")
    corpus = build(args.seed, args.cases)
    with open(args.out, "wb") as handle:
        handle.write(dumps(corpus).encode("ascii"))
    meta = corpus["_meta"]
    print("wrote %d cases (seed %d) to %s; %d error cases, %d strict, %d redrawn"
          % (meta["case_count"], args.seed, args.out, sum(meta["error_codes"].values()),
             meta["strict_cases"], sum(meta["redrawn"].values())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
````

- [ ] **Step 4: Ignore the corpus.** Edit `.gitignore`:

````text old:.gitignore
# Test / benchmark caches

````

with

````text new:.gitignore
# The differential fuzz corpus is generated, never committed (ADR-007)
parity/fuzz-corpus.json

# Test / benchmark caches

````

- [ ] **Step 5: Run the tests; they pass.**

```bash
PYTHONPATH=. python -m pytest tests/test_fuzz_generator.py -q 2>&1 | tail -3
```

Expected: `8 passed`.

- [ ] **Step 6: Generate the default corpus and check it.**

```bash
PYTHONPATH=. python parity/generate_fuzz.py --out parity/fuzz-corpus.json
git status --short | grep fuzz-corpus || echo "the corpus is ignored by git"
```

Expected: `wrote 20000 cases (seed 20261126) to parity/fuzz-corpus.json; 2209 error cases, 3115 strict, 24 redrawn` and the line `the corpus is ignored by git`; the file is 36,739,827 bytes. (Running it twice, or with `PYTHONHASHSEED` set to another value, gives the same bytes.)

- [ ] **Step 7: Lint, type-check, commit.**

```bash
python -m ruff check contexel && python -m mypy
git add .gitignore parity/generate_fuzz.py tests/test_fuzz_generator.py
git commit -m "test(parity): add the seeded differential fuzz generator"
```

### Task 2: The C# case adapter and the shared `suffix` cases

The first replay of the fuzz found that the C# case adapter rejected the `suffix` argument of `truncate_field` (the TypeScript adapter and the library accept it). Three shared cases keep the finding in the vectors.

**Files:**
- Modify: `parity/parity_cases.py`, `parity/vectors.json` (regenerated), `csharp/Contexel.Tests/CaseTests.cs`

- [ ] **Step 1: Add the three cases.** Edit `parity/parity_cases.py`:

````text old:parity/parity_cases.py
    return cases


MAX_SAFE_INT = 2 ** 53
````

with

````text new:parity/parity_cases.py

    # ---- Slice 7: the suffix argument of truncate_field (found by the differential fuzz: the C# case
    # adapter did not pass it on). The suffix is counted in tokens before the cut, so a longer suffix
    # leaves a shorter head; an empty suffix leaves the whole budget; an astral suffix is one code point.
    long_text = "abcdefghij" * 3
    add("truncate_field/custom_suffix_is_counted_before_the_cut", "truncate_field",
        {"field": "s", "max_tokens": 4, "suffix": "..."}, [{"s": long_text}, {"s": "short"}])
    add("truncate_field/empty_suffix_leaves_the_whole_budget", "truncate_field",
        {"field": "s", "max_tokens": 4, "suffix": ""}, [{"s": long_text}, {"s": "short"}])
    add("truncate_field/astral_suffix_is_one_code_point", "truncate_field",
        {"field": "s", "max_tokens": 4, "suffix": ASTRAL}, [{"s": long_text}])
    return cases


MAX_SAFE_INT = 2 ** 53
````

- [ ] **Step 2: Regenerate the vectors.**

```bash
PYTHONPATH=. python parity/generate_vectors.py
git diff --stat parity/vectors.json
```

Expected: `"case_count": 177` (was 174) and a diff of about 70 added lines and one changed line (the count). If the whole file shows as changed, it is a line-ending artifact: verify with `git diff --ignore-cr-at-eol --stat` and restore with `git checkout -- parity/vectors.json` followed by a regeneration only if the content differs.

- [ ] **Step 3: See it fail (RED) in C#, and pass in Python and TypeScript.**

```bash
PYTHONPATH=. python -m pytest tests/test_parity_cases.py -q 2>&1 | tail -1
(cd ts && npm test 2>&1 | grep -E "^ℹ (pass|fail)")
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo --filter "FullyQualifiedName~CaseMatchesPython" 2>&1 | grep -E "Failed!|unknown argument" | head -4
```

Expected: Python passes; TypeScript `pass 681`, `fail 0`; C# `Failed: 3` with `unknown argument 'suffix' for stage truncate_field` (the three new cases).

- [ ] **Step 4: Fix the adapter.** Edit `csharp/Contexel.Tests/CaseTests.cs` (two edits):

````text old:csharp/Contexel.Tests/CaseTests.cs
["truncate_field"] = ["field", "max_tokens"],
````

with

````text new:csharp/Contexel.Tests/CaseTests.cs
["truncate_field"] = ["field", "max_tokens", "suffix"],
````

````text old:csharp/Contexel.Tests/CaseTests.cs
"truncate_field" => Stages.TruncateField(r, (string)a["field"]!, (int)(long)a["max_tokens"]!),
````

with

````text new:csharp/Contexel.Tests/CaseTests.cs
"truncate_field" => Stages.TruncateField(r, (string)a["field"]!, (int)(long)a["max_tokens"]!,
            suffix: Str(a, "suffix", "…")),
````

- [ ] **Step 5: Run the C# suite (GREEN).**

```bash
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo 2>&1 | grep -E "Passed!|Failed!"
```

Expected: `Passed: 620` (617 + 3).

- [ ] **Step 6: Commit** (the vectors file is part of the change).

```bash
git add parity/parity_cases.py parity/vectors.json csharp/Contexel.Tests/CaseTests.cs
git commit -m "test(csharp): pass truncate_field's suffix in the case runner"
```

### Task 3: The TypeScript replay

**Files:**
- Create: `ts/test/fuzz.test.ts`
- Modify: `ts/package.json` (the `test` script lists its files)

**Interfaces:**
- Consumes: `checkCase(c, fixture)` and the `Case` type from `ts/test/runner.ts` (unchanged); the corpus of Task 1.

- [ ] **Step 1: Create the test.** `ts/test/fuzz.test.ts` with exactly this content:

````typescript file:ts/test/fuzz.test.ts
/**
 * Differential fuzz (ADR-007, brief AC 36): replay the seeded corpus that
 * `python parity/generate_fuzz.py` wrote through the runner that replays the
 * shared vectors, and compare every outcome with the Python canon.
 *
 * `CONTEXEL_FUZZ_CASES` is the path of the corpus (relative to the repository
 * root, or absolute). Unset, the replay is skipped locally; in CI (`CI` set) an
 * unset variable fails, so the job cannot go green by testing nothing.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import { checkCase, type Case } from "./runner.js";

const ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const MIN_CASES = 1000;
const SHOWN = 20;
const configured = process.env.CONTEXEL_FUZZ_CASES;

interface Corpus {
  _meta: { seed: number; case_count: number; kind_counts: Record<string, number> };
  cases: Case[];
}

/** A copy of the case whose expectation is wrong: every checker must refuse it. */
function corrupted(c: Case): Case {
  const copy = JSON.parse(JSON.stringify(c)) as Case;
  if (copy.expect_error !== undefined) {
    copy.expect_error = { code: copy.expect_error.code + ".wrong" };
  } else if (Array.isArray(copy.expect)) {
    copy.expect = [...copy.expect, { canary: 1 }];
  } else if (typeof copy.expect === "string") {
    copy.expect = copy.expect + "!";
  } else {
    copy.expect = { canary: 1 };
  }
  return copy;
}

if (configured === undefined || configured === "") {
  if (process.env.CI) {
    test("the fuzz corpus is configured in CI", () => {
      assert.fail("CONTEXEL_FUZZ_CASES is not set: generate the corpus and point the variable at it");
    });
  } else {
    test("differential fuzz replay", { skip: "CONTEXEL_FUZZ_CASES is not set" }, () => {});
  }
} else {
  const corpus = JSON.parse(readFileSync(path.resolve(ROOT, configured), "utf-8")) as Corpus;

  test("the fuzz corpus is present and complete", () => {
    assert.ok(corpus.cases.length >= MIN_CASES, `only ${corpus.cases.length} cases (a replay must never pass vacuously)`);
    assert.strictEqual(corpus.cases.length, corpus._meta.case_count, "case_count disagrees with the cases array");
    assert.strictEqual(new Set(corpus.cases.map((c) => c.id)).size, corpus.cases.length, "duplicate case ids");
    const seen: Record<string, number> = {};
    for (const c of corpus.cases) seen[c.stage] = (seen[c.stage] ?? 0) + 1;
    assert.deepStrictEqual(seen, corpus._meta.kind_counts, "the kinds replayed differ from the kinds generated");
    assert.ok(corpus.cases.some((c) => c.expect_error !== undefined), "no error case in the corpus");
  });

  test(`every fuzz case matches the Python canon (seed ${corpus._meta.seed})`, () => {
    const failures: string[] = [];
    for (const c of corpus.cases) {
      try {
        checkCase(c, []);
      } catch (error) {
        const message = String((error as Error).message ?? error).split("\n").slice(0, 6).join("\n    ");
        failures.push(`${c.id}\n    ${message}`);
      }
    }
    if (failures.length > 0) {
      const index = Number(failures[0].split("\n")[0].split("/")[2]);
      assert.fail(
        `${failures.length} of ${corpus.cases.length} fuzz cases diverge from the canon. First ${Math.min(SHOWN, failures.length)}:\n` +
          failures.slice(0, SHOWN).join("\n") +
          `\nReproduce one: python parity/generate_fuzz.py --seed ${corpus._meta.seed} --show ${index}`
      );
    }
  });

  test("the replay can fail: a corrupted expectation is refused", () => {
    const sample = corpus.cases.slice(0, 300);
    assert.ok(sample.length > 0);
    for (const c of sample) {
      assert.throws(() => checkCase(corrupted(c), []), Error, `a corrupted ${c.id} was accepted`);
    }
  });
}
````

- [ ] **Step 2: Add it to the test script.** Edit `ts/package.json`:

````text old:ts/package.json
dist-test/test/rescore-modes.test.js"
````

with

````text new:ts/package.json
dist-test/test/rescore-modes.test.js dist-test/test/fuzz.test.js"
````

- [ ] **Step 3: Run it in the three modes** (the corpus of Task 1 Step 6 must exist).

```bash
cd ts
npm test 2>&1 | grep -E "^ℹ (tests|pass|fail|skipped)"
CONTEXEL_FUZZ_CASES=parity/fuzz-corpus.json npm test 2>&1 | grep -E "^ℹ (tests|pass|fail|skipped)|fuzz"
CI=1 npm test 2>&1 | grep -E "^ℹ (pass|fail)|configured in CI"
cd ..
```

Expected, in order: unset: `tests 682`, `pass 681`, `fail 0`, `skipped 1`; set: `tests 684`, `pass 684`, `skipped 0`, and the lines `the fuzz corpus is present and complete`, `every fuzz case matches the Python canon (seed 20261126)`, `the replay can fail: a corrupted expectation is refused` (the middle one takes about 2.6 s); `CI=1` with the variable unset: `fail 1`, `the fuzz corpus is configured in CI`.

- [ ] **Step 4: Commit.**

```bash
git add ts/test/fuzz.test.ts ts/package.json
git commit -m "test(ts): replay the differential fuzz corpus"
```

### Task 4: The C# replay

**Files:**
- Create: `csharp/Contexel.Tests/FuzzTests.cs`

**Interfaces:**
- Consumes: `CaseTests.AssertCase(Rec)` (`internal static`, same assembly), `VectorData.Convert/AsRec/AsList` (public), the corpus of Task 1.

- [ ] **Step 1: Create the test.** `csharp/Contexel.Tests/FuzzTests.cs` with exactly this content:

````csharp file:csharp/Contexel.Tests/FuzzTests.cs
using System.Text;
using System.Text.Json;
using Xunit;
using static Contexel.Tests.VectorData;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;

/// <summary>
/// Differential fuzz (ADR-007, brief AC 36): replays the seeded corpus that
/// <c>python parity/generate_fuzz.py</c> wrote through the case runner of the shared
/// vectors (<see cref="CaseTests.AssertCase"/>) and compares every outcome with the
/// Python canon. <c>CONTEXEL_FUZZ_CASES</c> is the corpus path (relative to the
/// repository root, or absolute). Unset, the replay returns at once locally; in CI
/// (<c>CI</c> set) an unset variable fails, so the job cannot go green by testing
/// nothing.
/// </summary>
public class FuzzTests
{
    private const int MinCases = 1000, Shown = 20;

    private static string RepoRoot()
    {
        string? dir = AppContext.BaseDirectory;
        while (dir is not null && !File.Exists(Path.Combine(dir, "parity", "vectors.json")))
            dir = Path.GetDirectoryName(dir);
        return dir ?? throw new FileNotFoundException("repository root not found above the test directory");
    }

    /// <summary>The corpus, or null when the variable is unset and this is not CI.</summary>
    private static Rec? Corpus()
    {
        var configured = Environment.GetEnvironmentVariable("CONTEXEL_FUZZ_CASES");
        if (string.IsNullOrEmpty(configured))
        {
            Assert.False(!string.IsNullOrEmpty(Environment.GetEnvironmentVariable("CI")),
                "CONTEXEL_FUZZ_CASES is not set: generate the corpus and point the variable at it");
            return null;
        }
        using var doc = JsonDocument.Parse(File.ReadAllText(Path.GetFullPath(configured, RepoRoot())));
        return AsRec(Convert(doc.RootElement));
    }

    private static Rec Corrupted(Rec c)
    {
        var copy = new Rec(c);
        if (c.TryGetValue("expect_error", out var err))
            copy["expect_error"] = new Rec { ["code"] = (string)AsRec(err)["code"]! + ".wrong" };
        else
            copy["expect"] = c["expect"] switch
            {
                List<object?> l => new List<object?>(l) { new Rec { ["canary"] = 1L } },
                string s => s + "!",
                _ => new Rec { ["canary"] = 1L },
            };
        return copy;
    }

    [Fact]
    public void FuzzCorpusIsPresentAndComplete()
    {
        if (Corpus() is not { } corpus) return;
        var meta = AsRec(corpus["_meta"]);
        var cases = AsList(corpus["cases"]).Select(AsRec).ToList();
        Assert.True(cases.Count >= MinCases, $"only {cases.Count} cases (a replay must never pass vacuously)");
        Assert.Equal((long)meta["case_count"]!, (long)cases.Count);
        Assert.Equal(cases.Count, cases.Select(c => (string)c["id"]!).Distinct().Count());
        var seen = cases.GroupBy(c => (string)c["stage"]!).ToDictionary(g => g.Key, g => (long)g.Count());
        var generated = AsRec(meta["kind_counts"]).ToDictionary(kv => kv.Key, kv => (long)kv.Value!);
        Assert.Equal(generated.OrderBy(kv => kv.Key), seen.OrderBy(kv => kv.Key));
        Assert.Contains(cases, c => c.ContainsKey("expect_error"));
    }

    [Fact]
    public void EveryFuzzCaseMatchesPython()
    {
        if (Corpus() is not { } corpus) return;
        var seed = (long)AsRec(corpus["_meta"])["seed"]!;
        var cases = AsList(corpus["cases"]).Select(AsRec).ToList();
        var failures = new List<string>();
        foreach (var c in cases)
        {
            try { CaseTests.AssertCase(c); }
            catch (Exception e)
            {
                var lines = e.Message.Split('\n').Take(6).Select(l => l.TrimEnd('\r'));
                failures.Add($"{(string)c["id"]!}\n    {string.Join("\n    ", lines)}");
            }
        }
        if (failures.Count == 0) return;
        var index = long.Parse(failures[0].Split('\n')[0].Split('/')[2]);
        var shown = new StringBuilder();
        foreach (var f in failures.Take(Shown)) shown.AppendLine(f);
        throw new Xunit.Sdk.XunitException(
            $"{failures.Count} of {cases.Count} fuzz cases diverge from the canon. First {Math.Min(Shown, failures.Count)}:\n" +
            $"{shown}Reproduce one: python parity/generate_fuzz.py --seed {seed} --show {index}");
    }

    [Fact]
    public void TheReplayCanFailACorruptedExpectationIsRefused()
    {
        if (Corpus() is not { } corpus) return;
        foreach (var c in AsList(corpus["cases"]).Select(AsRec).Take(300))
            Assert.ThrowsAny<Exception>(() => CaseTests.AssertCase(Corrupted(c)));
    }
}
````

- [ ] **Step 2: Run it in the three modes.**

```bash
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo 2>&1 | grep -E "Passed!|Failed!"
CONTEXEL_FUZZ_CASES=parity/fuzz-corpus.json dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo --filter "FullyQualifiedName~FuzzTests" 2>&1 | grep -E "Passed!|Failed!"
CI=1 dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo --filter "FullyQualifiedName~FuzzTests" 2>&1 | grep -E "Passed!|Failed!|not set" | head -3
```

Expected: unset: `Passed: 623` (the three new facts return at once); set: `Passed: 3` (a few seconds: 4 s on a quick run, 12 s when the machine is busy); `CI=1` with the variable unset: `Failed: 3` with `CONTEXEL_FUZZ_CASES is not set`.

- [ ] **Step 3: Commit.**

```bash
git add csharp/Contexel.Tests/FuzzTests.cs
git commit -m "test(csharp): replay the differential fuzz corpus"
```

### Task 5: CI and the release gate

**Files:**
- Modify: `.github/workflows/ci.yml`, `.github/workflows/release.yml`

- [ ] **Step 1: Edit `.github/workflows/ci.yml`** (the `ts-parity` and `cs-parity` jobs; three edits):

````text old:.github/workflows/ci.yml
      - run: git diff --exit-code parity/vectors.json
      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7
````

with

````text new:.github/workflows/ci.yml
      - run: git diff --exit-code parity/vectors.json
      # Differential fuzz (ADR-007, AC 36): a seeded corpus from the canon, replayed below
      - name: Generate the differential fuzz corpus
        run: python parity/generate_fuzz.py --out parity/fuzz-corpus.json
      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7
````

````text old:.github/workflows/ci.yml
      - run: npm test
        working-directory: ts

````

with

````text new:.github/workflows/ci.yml
      - run: npm test
        working-directory: ts
        env:
          CONTEXEL_FUZZ_CASES: parity/fuzz-corpus.json

````

````text old:.github/workflows/ci.yml
      - run: git diff --exit-code parity/vectors.json
      - uses: actions/setup-dotnet@a98b56852c35b8e3190ac28c8c2271da59106c68 # v6
        with:
          dotnet-version: "8.0.x"
      - run: dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo

````

with

````text new:.github/workflows/ci.yml
      - run: git diff --exit-code parity/vectors.json
      # Differential fuzz (ADR-007, AC 36): a seeded corpus from the canon, replayed below
      - name: Generate the differential fuzz corpus
        run: python parity/generate_fuzz.py --out parity/fuzz-corpus.json
      - uses: actions/setup-dotnet@a98b56852c35b8e3190ac28c8c2271da59106c68 # v6
        with:
          dotnet-version: "8.0.x"
      - run: dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
        env:
          CONTEXEL_FUZZ_CASES: parity/fuzz-corpus.json

````

- [ ] **Step 2: Edit `.github/workflows/release.yml`** (the `ts-test` and `cs-test` jobs; three edits):

````text old:.github/workflows/release.yml
      - run: git diff --exit-code parity/vectors.json
      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7
````

with

````text new:.github/workflows/release.yml
      - run: git diff --exit-code parity/vectors.json
      # Differential fuzz (ADR-007, AC 36): a seeded corpus from the canon, replayed below
      - name: Generate the differential fuzz corpus
        run: python parity/generate_fuzz.py --out parity/fuzz-corpus.json
      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7
````

````text old:.github/workflows/release.yml
      - name: Full TS suite on this exact commit
        working-directory: ts
        run: |
````

with

````text new:.github/workflows/release.yml
      - name: Full TS suite on this exact commit
        working-directory: ts
        env:
          CONTEXEL_FUZZ_CASES: parity/fuzz-corpus.json
        run: |
````

````text old:.github/workflows/release.yml
      - run: git diff --exit-code parity/vectors.json
      - uses: actions/setup-dotnet@a98b56852c35b8e3190ac28c8c2271da59106c68 # v6
        with:
          dotnet-version: '8.0.x'
      - name: Full C# suite on this exact commit
        run: dotnet test
````

with

````text new:.github/workflows/release.yml
      - run: git diff --exit-code parity/vectors.json
      # Differential fuzz (ADR-007, AC 36): a seeded corpus from the canon, replayed below
      - name: Generate the differential fuzz corpus
        run: python parity/generate_fuzz.py --out parity/fuzz-corpus.json
      - uses: actions/setup-dotnet@a98b56852c35b8e3190ac28c8c2271da59106c68 # v6
        with:
          dotnet-version: '8.0.x'
      - name: Full C# suite on this exact commit
        env:
          CONTEXEL_FUZZ_CASES: parity/fuzz-corpus.json
        run: dotnet test
````

- [ ] **Step 3: Check the YAML and run the CI sequence by hand.**

```bash
python -c "import yaml; [yaml.safe_load(open(f, encoding='utf-8')) for f in ('.github/workflows/ci.yml', '.github/workflows/release.yml')]; print('both workflows parse')"
PYTHONPATH=. python parity/generate_vectors.py && git diff --exit-code parity/vectors.json
PYTHONPATH=. python parity/generate_fuzz.py --out parity/fuzz-corpus.json
(cd ts && CONTEXEL_FUZZ_CASES=parity/fuzz-corpus.json npm test 2>&1 | grep -E "^ℹ (pass|fail)")
CONTEXEL_FUZZ_CASES=parity/fuzz-corpus.json dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo 2>&1 | grep -E "Passed!|Failed!"
```

Expected: `both workflows parse` (if PyYAML is not installed, say so and rely on the diff); `git diff --exit-code` silent (the vectors were committed in Task 2); TypeScript `pass 684`; C# `Passed: 623`. (`git diff --exit-code parity/vectors.json` can show a phantom change on this machine from line endings: compare with `git diff --ignore-cr-at-eol --exit-code parity/vectors.json`.) **The workflows themselves are first run by the human's push; say so in the report.**

- [ ] **Step 4: Commit.**

```bash
git add .github/workflows/ci.yml .github/workflows/release.yml
git commit -m "ci: generate and replay the differential fuzz corpus"
```

### Task 6: Documentation and the record of the margins

**Files:**
- Modify: `docs/adr/007-vector-format-v2-and-differential-fuzz.md`, `docs/adr/002-csharp-parity.md`, `README.md`, `CHANGELOG.md`

- [ ] **Step 1: ADR-007** (the status line and the section that records the domain, the margins, the finding and the process):

````text old:docs/adr/007-vector-format-v2-and-differential-fuzz.md
**Status:** accepted (cases format implemented in Slice 1; differential fuzz pending Slice 7)
````

with

````text new:docs/adr/007-vector-format-v2-and-differential-fuzz.md
**Status:** accepted (cases format implemented in Slice 1; differential fuzz implemented in Slice 7)
````

````text old:docs/adr/007-vector-format-v2-and-differential-fuzz.md
- Invalidation triggers: fuzz runtime exceeding the CI budget; an envelope too narrow to be meaningful.
````

with

````text new:docs/adr/007-vector-format-v2-and-differential-fuzz.md
- Invalidation triggers: fuzz runtime exceeding the CI budget; an envelope too narrow to be meaningful.

## The differential fuzz as built (Slice 7)
`parity/generate_fuzz.py` writes a seeded corpus (default seed 20261126, 20,000 cases, about 37 MB, never
committed) in the `cases` format of `vectors.json`; the Python canon computes every expectation. The
TypeScript (`ts/test/fuzz.test.ts`) and C# (`FuzzTests.cs`) suites replay it through the runners that replay
the shared vectors. `CONTEXEL_FUZZ_CASES` names the corpus file; unset, the replay is skipped locally and
**fails when `CI` is set**, so a job cannot go green by testing nothing. CI and the release workflow both
generate the corpus and set the variable. The generator draws only from `random.random()`, the one method
Python keeps stable, so a seed gives the same corpus on every Python and operating system; case `i` depends
on `(seed, i)` alone, and `python parity/generate_fuzz.py --seed S --show I` prints one case.

**Domain.** The documented parity envelope (ADR-001 4a, ADR-002 3), and in addition: a case whose canon
output contains an integer-valued float at ANY stage (an empty query scores every record 0.0, which TypeScript
serializes as `0` and so counts differently downstream) is redrawn, and every redraw is counted in
`_meta.redrawn` (about one case in a thousand); a scalar or null item in a list of records appears only in
cases that expect `input.not_mapping` (a C# list holds mappings); text uses ASCII, Latin-1, BMP CJK, Hangul
and Cyrillic letters, emoji, combining marks, control characters and quote characters, and records carry
non-string values and wide numbers (down to 5e-324, up to 2^53 - 1) that the text stages read.

**Margins the domain excludes** (each was measured by allowing the character class, then excluded):
1. *Astral letters in text that `rescore` reads* (ADR-006, Slice 5 ruling S5-8): the C# word tokenizer treats
   a letter outside the BMP differently (135 divergences in 20,000 cases). Astral letters are generated only
   in the field `note`, which `rescore` never reads; every other stage handles them and is fuzzed on them.
2. *U+0130 (capital I with dot above)*: Python and JavaScript lower-case it to `i` and U+0307; .NET's
   `ToLowerInvariant` leaves it. C# `rescore` tokenizes text containing it differently (31 divergences in
   6,000 cases). Excluded and **open**: a fix would change C# behavior (recorded for the human).
3. *Other case-special characters* (U+017F, U+00DF, U+212A, U+212B, U+1E9E, the sigmas): ADR-001 and ADR-002
   already record that the runtimes' case tables differ for `quarantine`'s case-insensitive matching
   (U+212A against `[A-Z]` diverged once in 20,000 cases in TypeScript). Excluded.

**Findings fixed.** The C# case adapter did not pass `truncate_field`'s `suffix` argument (the library did);
fixed, with three shared cases. A defect of the kind the fuzz is for: with the budget floor of
`truncate_field` changed from 1 to 0 in either port the shared vectors stayed green and 112 fuzz cases failed.

**Process.** A divergence is either fixed (the fix adds a shared case to `parity/parity_cases.py`, so the
vectors keep it) or recorded here as a margin that narrows the domain, and the generator is narrowed in the
same change. Nothing is filtered silently: redraws are counted and the replays name every divergence.
````

- [ ] **Step 2: ADR-002** (the margin found by the fuzz):

````text old:docs/adr/002-csharp-parity.md
   - Lone surrogates (out of the JSON-safe envelope) advance one unit
````

with

````text new:docs/adr/002-csharp-parity.md
   - U+0130 (capital I with dot above): Python and JavaScript lower-case it to `i` and U+0307; `ToLowerInvariant`
     leaves it, so `rescore` tokenizes text containing it differently (found by the differential fuzz, ADR-007;
     excluded from its domain).
   - Lone surrogates (out of the JSON-safe envelope) advance one unit
````

- [ ] **Step 3: README** (one sentence in the parity paragraph; no number, so the benchmark check is unaffected):

````text old:README.md
token counts, and a growing block of adversarial edge cases must match or
the build is red, on Linux, Windows, and macOS.

````

with

````text new:README.md
token counts, and a growing block of adversarial edge cases must match or
the build is red, on Linux, Windows, and macOS. A seeded differential fuzz
corpus ([parity/generate_fuzz.py](parity/generate_fuzz.py)), generated from
the canon on every run and never committed, is replayed by the TypeScript and
C# suites too.

````

- [ ] **Step 4: CHANGELOG**:

````text old:CHANGELOG.md
### Changed — benchmark claims (documentation only)

````

with

````text new:CHANGELOG.md
### Added — differential fuzz (ADR-007; tests and CI only, no library change)
- `parity/generate_fuzz.py` writes a seeded corpus of random cases inside the documented parity envelope, in
  the format of `parity/vectors.json`, with every expectation computed by the Python canon. The TypeScript
  (`ts/test/fuzz.test.ts`) and C# (`FuzzTests.cs`) suites replay it through the runners that replay the shared
  vectors. CI and the release workflow generate it and set `CONTEXEL_FUZZ_CASES`; locally the replay is skipped
  unless that variable names the corpus, and under CI an unset variable fails. The corpus is the same on every
  Python and operating system, is never committed, and a divergence is reproduced with
  `python parity/generate_fuzz.py --seed S --show INDEX`.
- The fuzz found one gap, in the C# test adapter (it did not pass `truncate_field`'s `suffix`), fixed with three
  new shared cases, and one margin that was not recorded: C# `rescore` treats U+0130 differently from Python and
  JavaScript. The domain, the margins it excludes and why are in ADR-007.

### Changed — benchmark claims (documentation only)

````

- [ ] **Step 5: Run the whole project's checks.**

```bash
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*' 2>&1 | tail -1
python tools/check_benchmark_numbers.py | tail -1
python tools/site_check.py | tail -1
python tools/check_versions.py | tail -1
python -m ruff check contexel | tail -1
python -m mypy | tail -1
(cd ts && CONTEXEL_FUZZ_CASES=parity/fuzz-corpus.json npm test 2>&1 | grep -E "^ℹ (tests|pass|fail|skipped)")
CONTEXEL_FUZZ_CASES=parity/fuzz-corpus.json dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo 2>&1 | grep -E "Passed!|Failed!"
```

Expected: `1087 passed, 1 skipped`; `benchmark numbers: README, PyPI README and site agree with the generated results`; `checked 6 pages under site/ -> OK`; `check_versions: all 7 version locations say 0.1.17`; `All checks passed!`; `Success: no issues found in 10 source files`; TypeScript `tests 684`, `pass 684`; C# `Passed: 623`. Then the privacy check: `git diff main..HEAD | grep -ci "AppData\|@gmail\|C:\\\\Users"` prints `0`, and `git log main..HEAD --format=%B | grep -c Co-Authored` prints `0`.

- [ ] **Step 6: Commit.**

```bash
git add docs/adr/007-vector-format-v2-and-differential-fuzz.md docs/adr/002-csharp-parity.md README.md CHANGELOG.md
git commit -m "docs: record the differential fuzz and its margins (ADR-007)"
```

## Open for the human

1. **Review rulings S7-1 to S7-13**, above all S7-10 (U+0130 is recorded, not fixed), S7-11 (the release workflow runs the fuzz too) and S7-7 (only the default seed gates).
2. **A scheduled multi-seed fuzz** (a weekly workflow over fresh seeds that opens an issue on a divergence) would widen the net beyond the one gating seed; it adds a workflow and CI cost, so it is not in this slice. Say if you want it planned.
3. **A C# fix for U+0130 and for astral letters in the word tokenizer** (S5-8) would be a behavior change of `match="word"` and `match="stem"`; with it the generator's exclusions could be lifted. Not in this slice.
4. **The first CI run** of the execution branch is the evidence for the 60-second target and for macOS and Windows behavior (path, memory, encoding).
