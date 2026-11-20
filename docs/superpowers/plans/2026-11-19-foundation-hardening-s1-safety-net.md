# Foundation Hardening — Slice 1: Safety Net — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make contexel's determinism and invariants *enforced* in CI, and replace hand-copied cross-language test data with data-driven parity cases — **without changing any library behavior**.

**Architecture:** Python gains seeded property tests (with canaries), a cross-process hash-seed test and golden fingerprints. A single case table (`parity/parity_cases.py`) computes expectations with the Python canon and is emitted into `parity/vectors.json` as a new `cases` array; TypeScript and C# replay it through one adapter per stage. All existing `vectors.json` sections stay byte-identical.

**Tech Stack:** Python ≥ 3.9 (stdlib + pytest, no `hypothesis`), TypeScript (`node:test`), C# (xunit, net8.0).

**Spec:** `docs/superpowers/specs/2026-11-19-foundation-hardening-design.md` (§8 Enforcement) · **Brief:** `docs/briefs/foundation-hardening.md` (AC 19, 20, 21, 22, and the AC 29 baseline) · **ADR:** `docs/adr/007-vector-format-v2-and-differential-fuzz.md` · **Master plan:** `docs/plans/foundation-hardening.md`

## Global Constraints

- Python `>=3.9`; **zero runtime dependencies**; no model calls; no network.
- **No `hypothesis`** and no other new dependency: property tests use stdlib `random` (brief AC 20).
- **This slice changes no library behavior:** no edits under `contexel/`, `ts/src/`, or `csharp/Contexel/`.
- **Every existing section of `parity/vectors.json` stays byte-identical;** only `_meta.case_count` and the new `cases` key are added.
- Never store an invisible or combining character literally in source: write it as an explicit `\u` escape.
- **Run the vector generator against the checkout:** `python parity/generate_vectors.py` puts `parity/` (not the repository root) first on `sys.path`, so without an editable install it silently imports an INSTALLED `contexel` and can write wrong vectors. Run it as `PYTHONPATH=<repo root> python parity/generate_vectors.py` (or after `pip install -e .`, as CI does) and verify with `python -c "import contexel; print(contexel.__file__)"` under the same environment.
- Case data must stay inside the parity envelope: JSON only, **no integer-valued floats, NaN/Inf, or integers beyond 2^53** (TypeScript cannot tell `1.0` from `1`).
- **Never run the hash-seed child with `python -I`:** `-I` implies `-E`, which discards `PYTHONHASHSEED` and makes the test vacuous.
- Test code must run on Python 3.9 (no `match` statements, no `X | Y` annotations) and on Windows, macOS and Linux (read/write JSON as UTF-8, LF newlines).
- Commits: Conventional Commits (`type(scope): imperative summary`, ≤ 72 chars); author = the repo's configured identity; **no `Co-Authored-By` trailer** (project owner's standing rule); **never push**; no version bump (tests only).
- Baselines before this slice (recorded 2026-11-19): Python `72 passed` (`pytest --ignore-glob="tests/test_doctrine_*"`), TypeScript `41 pass`, C# `39 passed`. The gitignored `tests/test_doctrine_*` tooling tests are not part of CI and have one unrelated pre-existing failure; always exclude them.

## Review Focus

Failure modes the spec implies but a straightforward implementation would not test; each is pinned by a test in the owning task:

1. **A runner that silently skips cases** (a typo in a key, a short loop) and reports green → `_meta.case_count` must equal the array length, ids unique, unknown keys rejected — Task 5 (TypeScript) and Task 6 (C#), proven by a tamper negative control.
2. **A hash-seed sweep that is vacuous** (the flag drops the env var, or the data has no hash-order hazard) → Task 2 guards: the seed must demonstrably take effect (seed 0 gives `hash_randomization == 0`, the same seed gives the same `hash()` twice, a different seed changes it, and with the variable removed the flag reads 1 as a control), and a known hash-dependent child must be stable per seed yet produce more than one output across seeds. Negative control: forcing the child through `python -I` makes both guards fail.
3. **Property tests that cannot fail** → Task 1 canaries: a mutating stage, a non-deterministic stage and a non-idempotent stage must each be caught by the checkers. (G4/G5 fix wave: every other check also has a canary: subsequence, count, input positions, rank permutation/order/missing-last/tie order, budget, `min_records`, and each filter stage's effect; a stage that raises must still report its seed.)
4. **Expected data TypeScript cannot represent** (an integer-valued float such as `2.0`, NaN, a huge integer) silently passing in one language and failing in another → Task 4 envelope guard, with accept/reject tests.
5. **Regeneration drift** (CRLF on Windows, a different key order, non-UTF-8 read) making `git diff --exit-code parity/vectors.json` flaky in CI → Task 4 asserts byte-stable, LF-only regeneration and that legacy sections are unchanged.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `tests/_gen.py` | create | seeded record generators; seed/case-count env; regression-seed list |
| `tests/test_properties.py` | create | purity, determinism, idempotence, subsequence, count, input-order, rank tie-order, budget and filter-effect properties + a canary per check |
| `tests/test_determinism_processes.py` | create | subprocess sweep over `PYTHONHASHSEED`; vacuity canaries |
| `tests/test_fingerprint_golden.py` | create | pins today's policy fingerprints (the AC 29 baseline) |
| `parity/parity_cases.py` | create | the single case table, `run_case`, envelope guard |
| `parity/generate_vectors.py` | modify (3 small edits) | emit `cases` and `_meta.case_count` |
| `parity/vectors.json` | regenerate | adds `cases`; legacy sections unchanged |
| `tests/test_parity_cases.py` | create | Python replay of committed cases + envelope-guard tests |
| `ts/test/cases.test.ts` | create | generic TypeScript runner |
| `ts/package.json` | modify (`test` script) | include the new test file |
| `csharp/Contexel.Tests/CaseTests.cs` | create | generic C# runner |
| `CHANGELOG.md`, `docs/adr/007-…md` | modify | `[Unreleased]` entry; ADR status |

---

### Task 0: Branch and baseline

**Files:** none modified.

**Interfaces:** Produces: a clean branch `feat/hardening-s1-safety-net` and recorded baseline counts that Task 7 compares against.

- [ ] **Step 1: Create the branch from a clean tree**

```bash
cd /d/contexel
git status --short            # expect: no output (clean)
git switch -c feat/hardening-s1-safety-net
```

- [ ] **Step 2: Record the Python baseline**

Run: `python -m pytest -q -p no:cacheprovider --ignore-glob="tests/test_doctrine_*"`
Expected: `72 passed`. If the number differs, stop: the tree is not the one this plan was written against.

- [ ] **Step 3: Record the TypeScript and C# baselines**

```bash
(cd ts && npm test 2>&1 | grep -E "^ℹ (tests|pass|fail)")      # expect: tests 41, pass 41, fail 0
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo -v q 2>&1 | tail -2   # expect: Passed! - Failed: 0, Passed: 39
```

- [ ] **Step 4: Confirm none of the files this slice creates are git-ignored**

```bash
git check-ignore -v tests/_gen.py tests/test_properties.py tests/test_determinism_processes.py \
  tests/test_fingerprint_golden.py tests/test_parity_cases.py parity/parity_cases.py \
  ts/test/cases.test.ts csharp/Contexel.Tests/CaseTests.cs ; echo "exit=$?"
```
Expected: no matches and `exit=1`. If a path is ignored, fix the pattern before continuing.

---

### Task 1: Property-test harness with canaries (AC 20)

**Files:**
- Create: `tests/_gen.py`
- Create: `tests/test_properties.py`

**Interfaces:**
- Produces: `_gen.seeds() -> Iterator[int]`, `_gen.canary_seeds() -> Iterator[int]` (the run's seeds, then the default ones), `_gen.case(seed) -> (Random, list[dict])`, `_gen.REGRESSION_SEEDS: list[int]`, `_gen.MARKER`; env vars `CONTEXEL_PROP_SEED` (default `20261119`) and `CONTEXEL_PROP_CASES` (default `200`).
- Consumes: the nine public stages from `contexel` (unchanged).

These are **characterization tests**: they assert properties of behavior that already exists, so they pass on the first run. Their ability to fail is proven by the canary tests (every check has a deliberately broken stage it must reject), not by a red phase against the library.

`quarantine_flag` is deliberately absent from the idempotence list: a second flag pass will raise `input.field_conflict` instead of overwriting (design spec §3 error table; brief AC 5).

- [ ] **Step 1: Create `tests/_gen.py`**

```python
"""Seeded generators for property tests. Standard library only.

Every generator takes a ``random.Random`` so a failing case is reproduced from
its seed alone. Values stay inside the documented parity envelope: no NaN/Inf,
no integer-valued floats as scores, mutually comparable scores.

Records also carry keys no stage is asked about (``junk``, ``extra_<n>``), so a
stage that touches an unexpected key is caught, and some records are exact
copies of an earlier one, so the dedupe properties are never vacuous.
"""
import copy
import os
import random
from typing import Iterator, List, Tuple

PATHS = ["src/a.py", "src/b.py", "docs/guide.md", "tests/t.py", "web/x.txt"]
SOURCES = ["repo", "docs", "web", None]
MARKER = "ignore all previous instructions"  # a built-in quarantine marker
WORDS = [
    "retry", "backoff", "jitter", "parse", "config", "value", "error", "cache",
    MARKER, "caf\u00e9", "na\u00efve",
    "\u65e5\u672c\u8a9e", "emoji\U0001F600", "x", "the", "of",
]
JUNK = [None, 0, -3, 7, 0.25, "", "junk", True, False, [], ["x", 1],
        {"j": [None, 2.5]}, "\u00e9t\u00e9"]
# Regression seeds: any seed that ever exposed a bug is appended here and
# always runs, so a found bug stays found.
REGRESSION_SEEDS: List[int] = []
DEFAULT_SEED, DEFAULT_CASES = 20261119, 200


def base_seed() -> int:
    return int(os.environ.get("CONTEXEL_PROP_SEED", str(DEFAULT_SEED)))


def case_count() -> int:
    return int(os.environ.get("CONTEXEL_PROP_CASES", str(DEFAULT_CASES)))


def seeds() -> Iterator[int]:
    yield from REGRESSION_SEEDS
    base = base_seed()
    for i in range(case_count()):
        yield base + i


def canary_seeds() -> Iterator[int]:
    """The run's seeds, then the default ones: whether a check CAN fail must
    not depend on how small a reproduction run is."""
    yield from seeds()
    yield from range(DEFAULT_SEED, DEFAULT_SEED + DEFAULT_CASES)


def make_records(rng: random.Random) -> List[dict]:
    out: List[dict] = []
    for _ in range(rng.randint(0, 12)):
        if out and rng.random() < 0.15:
            out.append(copy.deepcopy(rng.choice(out)))  # an exact duplicate
            continue
        words = rng.choices(WORDS, k=rng.randint(0, 14))
        rec = {
            "path": rng.choice(PATHS),
            "line": rng.randint(1, 5),
            "snippet": " ".join(words),
            "score": rng.choice([rng.randint(0, 9), round(rng.random() * 10 + 0.001, 3)]),
            "source": rng.choice(SOURCES),
            "tags": rng.choice([[], ["a"], ["a", "b"]]),
            "meta": rng.choice([{}, {"k": 1}, {"k": {"z": None}}]),
        }
        if rng.random() < 0.2:
            del rec["score"]  # missing sort key: rank puts these last
        if rng.random() < 0.5:
            rec["junk"] = copy.deepcopy(rng.choice(JUNK))
        for n in range(rng.randint(0, 2)):
            rec[f"extra_{n}"] = copy.deepcopy(rng.choice(JUNK))
        out.append(rec)
    return out


def case(seed: int) -> Tuple[random.Random, List[dict]]:
    rng = random.Random(seed)
    return rng, make_records(rng)
```

- [ ] **Step 2: Create `tests/test_properties.py`**

```python
"""Generative property tests for every stage (stdlib only, seeded).

A failure message always carries the seed, whether a check failed or a stage
raised: set CONTEXEL_PROP_SEED to it and CONTEXEL_PROP_CASES=1 to reproduce.
Every check has a *canary* (a deliberately broken stage it must reject),
proving the harness can actually fail; the canaries in the CANARIES table
also search the default seeds, so a one-case reproduction run keeps them green.
"""
import contextlib
import copy
import itertools
import json
import re

import pytest

from contexel import (allowlist, dedupe, quarantine, rank, rescore, select,
                      tokens, trim_to_budget, truncate_field)

from _gen import MARKER, canary_seeds, case, seeds

ALLOWED_SOURCES = ["repo", "docs"]
STAGES = {
    # "_i" is the input index that check_positions tags records with
    "select": lambda r: select(r, ["_i", "path", "snippet", "score"]),
    "dedupe_key": lambda r: dedupe(r, key=["path", "line"]),
    "dedupe_whole": lambda r: dedupe(r),
    "allowlist": lambda r: allowlist(r, "source", ALLOWED_SOURCES),
    "quarantine_drop": lambda r: quarantine(r),
    "quarantine_flag": lambda r: quarantine(r, action="flag"),
    "rescore": lambda r: rescore(r, "retry backoff jitter", fields=("snippet", "path")),
    "rank": lambda r: rank(r, by="score"),
    "truncate": lambda r: truncate_field(r, "snippet", 6),
    "trim": lambda r: trim_to_budget(r, 80),
}
# quarantine_flag is deliberately absent from IDEMPOTENT: a second flag pass
# will raise input.field_conflict instead of overwriting (design spec section
# 3, error table; brief AC 5).
IDEMPOTENT = ["select", "dedupe_key", "dedupe_whole", "allowlist",
              "quarantine_drop", "rescore", "rank", "truncate", "trim"]
SUBSEQUENCE = ["dedupe_key", "dedupe_whole", "allowlist", "quarantine_drop", "trim"]
SAME_LENGTH = ["select", "quarantine_flag", "rescore", "rank", "truncate"]
ORDER_KEEPING = ["select", "quarantine_flag", "rescore", "truncate"]  # rank reorders


def canon(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def indexed(recs):
    """Tag each record with its input position (``_i``)."""
    return [{**r, "_i": i} for i, r in enumerate(recs)]


def is_subsequence(small, big):
    it = iter(big)  # shared: each match must come after the previous one
    return all(any(item == other for other in it) for item in small)


@contextlib.contextmanager
def reporting(seed):
    """Re-raise ANY exception from one seed's checks with the seed in it."""
    try:
        yield
    except Exception as exc:
        if f"(seed={seed})" in str(exc):
            raise
        raise AssertionError(f"{type(exc).__name__}: {exc} (seed={seed})") from exc


def for_each_case(check, seed_source=seeds):
    for seed in seed_source():
        with reporting(seed):
            _, recs = case(seed)
            check(recs, seed)


def check_purity(fn, recs, seed):
    before = copy.deepcopy(recs)
    fn(recs)
    assert recs == before, f"input mutated (seed={seed})"


def check_determinism(fn, recs, seed):
    first, second = fn(recs), fn(copy.deepcopy(recs))
    assert canon(first) == canon(second), f"non-deterministic (seed={seed})"


def check_idempotent(fn, recs, seed):
    once = fn(recs)
    assert canon(fn(once)) == canon(once), f"not idempotent (seed={seed})"


def check_subsequence(fn, recs, seed):
    assert is_subsequence(fn(recs), recs), f"not a subsequence (seed={seed})"


def check_count(fn, recs, seed):
    assert len(fn(recs)) == len(recs), f"record count changed (seed={seed})"


def check_positions(fn, recs, seed):
    out = fn(indexed(recs))
    assert [(r.get("_i"), r.get("path")) for r in out] == [
        (i, r.get("path")) for i, r in enumerate(recs)], f"input order not kept (seed={seed})"


def check_rank(fn, recs, seed):
    """by="score", desc: a permutation, scores descending, missing scores
    last, and equal scores (and the missing ones) in input order."""
    tagged = indexed(recs)
    out = fn(tagged)
    assert sorted(map(canon, out)) == sorted(map(canon, tagged)), f"not a permutation (seed={seed})"
    present = [r for r in out if "score" in r]
    assert all("score" not in r for r in out[len(present):]), f"missing scores not last (seed={seed})"
    scores = [r["score"] for r in present]
    assert scores == sorted(scores, reverse=True), f"scores not descending (seed={seed})"
    for a, b in zip(present, present[1:]):
        assert a["score"] != b["score"] or a["_i"] < b["_i"], f"tie order changed (seed={seed})"
    missing = [r["_i"] for r in out[len(present):]]
    assert missing == sorted(missing), f"tie order changed (seed={seed})"


def check_trim_budget(fn, recs, seed):
    out = fn(recs)  # a budget of 80, without min_records
    assert sum(tokens.count(r) + 2 for r in out) <= 80, f"over budget (seed={seed})"


def check_min_records_prefix(fn, recs, seed):
    out = fn(recs)  # a budget of 5 with min_records=2
    assert len(out) >= min(2, len(recs)), f"fewer than min_records kept (seed={seed})"
    assert out == recs[: len(out)], f"not a prefix (seed={seed})"


def has_marker(r):
    return MARKER in str(r.get("snippet", "")).lower()


def check_dedupe_key_effect(fn, recs, seed):
    keys = [(r.get("path"), r.get("line")) for r in fn(recs)]
    assert len(keys) == len(set(keys)), f"duplicate (path, line) kept (seed={seed})"


def check_dedupe_whole_effect(fn, recs, seed):
    out = [canon(r) for r in fn(recs)]
    assert len(out) == len(set(out)), f"duplicate record kept (seed={seed})"


def check_allowlist_effect(fn, recs, seed):
    assert all(r.get("source") in ALLOWED_SOURCES for r in fn(recs)), \
        f"disallowed source kept (seed={seed})"


def check_quarantine_drop_effect(fn, recs, seed):
    assert not any(has_marker(r) for r in fn(recs)), f"marker record kept (seed={seed})"


def check_quarantine_flag_effect(fn, recs, seed):
    assert all(r["quarantined"] is has_marker(r) for r in fn(recs)), \
        f"wrong quarantine flag (seed={seed})"


EFFECTS = {
    "dedupe_key": check_dedupe_key_effect,
    "dedupe_whole": check_dedupe_whole_effect,
    "allowlist": check_allowlist_effect,
    "quarantine_drop": check_quarantine_drop_effect,
    "quarantine_flag": check_quarantine_flag_effect,
}


@pytest.mark.parametrize("name", sorted(STAGES))
def test_stage_is_pure_and_deterministic(name):
    fn = STAGES[name]

    def check(recs, seed):
        check_purity(fn, recs, seed)
        check_determinism(fn, recs, seed)
    for_each_case(check)


@pytest.mark.parametrize("name", IDEMPOTENT)
def test_stage_is_idempotent(name):
    for_each_case(lambda recs, seed: check_idempotent(STAGES[name], recs, seed))


@pytest.mark.parametrize("name", SUBSEQUENCE)
def test_filter_stage_returns_a_subsequence(name):
    for_each_case(lambda recs, seed: check_subsequence(STAGES[name], recs, seed))


@pytest.mark.parametrize("name", sorted(EFFECTS))
def test_filter_stage_has_its_effect(name):
    for_each_case(lambda recs, seed: EFFECTS[name](STAGES[name], recs, seed))


@pytest.mark.parametrize("name", SAME_LENGTH)
def test_transform_stage_preserves_count(name):
    for_each_case(lambda recs, seed: check_count(STAGES[name], recs, seed))


@pytest.mark.parametrize("name", ORDER_KEEPING)
def test_transform_stage_keeps_input_positions(name):
    for_each_case(lambda recs, seed: check_positions(STAGES[name], recs, seed))


def test_rank_is_a_permutation_and_stable():
    for_each_case(lambda recs, seed: check_rank(STAGES["rank"], recs, seed))


def test_trim_never_exceeds_budget_without_min_records():
    for_each_case(lambda recs, seed: check_trim_budget(STAGES["trim"], recs, seed))


def test_trim_min_records_keeps_a_prefix_of_at_least_min_records():
    fn = lambda r: trim_to_budget(r, 5, min_records=2)  # noqa: E731
    for_each_case(lambda recs, seed: check_min_records_prefix(fn, recs, seed))


# --- canaries: the harness must be able to fail --------------------------------

def _mutating(recs):
    for r in recs:
        r["touched"] = True
    return recs


_counter = itertools.count()


def _nondeterministic(recs):
    return [{**r, "n": next(_counter)} for r in recs]


def _not_idempotent(recs):
    return [{**r, "snippet": r.get("snippet", "") + "!"} for r in recs]


def _first_nonempty_case():
    for seed in seeds():
        _, recs = case(seed)
        if recs:
            return seed, recs
    raise AssertionError("generator produced no non-empty case")


def test_canary_purity_check_detects_mutation():
    seed, recs = _first_nonempty_case()
    with pytest.raises(AssertionError, match="input mutated"):
        check_purity(_mutating, recs, seed)


def test_canary_determinism_check_detects_nondeterminism():
    seed, recs = _first_nonempty_case()
    with pytest.raises(AssertionError, match="non-deterministic"):
        check_determinism(_nondeterministic, recs, seed)


def test_canary_idempotence_check_detects_non_idempotence():
    seed, recs = _first_nonempty_case()
    with pytest.raises(AssertionError, match="not idempotent"):
        check_idempotent(_not_idempotent, recs, seed)


def _identity(recs):
    return list(recs)


def _reverse(recs):
    return list(reversed(recs))


def _drop_first(recs):
    return recs[1:]


def _rank_ascending(recs):
    return rank(recs, by="score", desc=False)


def _rank_missing_first(recs):
    out = rank(recs, by="score")
    return [r for r in out if "score" not in r] + [r for r in out if "score" in r]


def _rank_ties_by_path(recs):  # QA mutation 7: ties no longer in input order
    present = sorted((r for r in recs if "score" in r),
                     key=lambda r: (r["score"], str(r.get("path"))), reverse=True)
    return present + [r for r in recs if "score" not in r]


def _trim_ignoring_min_records(recs):
    return trim_to_budget(recs, 5)


def _flag_nothing(recs):
    return [{**r, "quarantined": False} for r in recs]


CANARIES = {
    "subsequence": (check_subsequence, _reverse, "not a subsequence"),
    "count": (check_count, _drop_first, "record count changed"),
    "positions": (check_positions, _reverse, "input order not kept"),
    "rank_permutation": (check_rank, _drop_first, "not a permutation"),
    "rank_missing_last": (check_rank, _rank_missing_first, "missing scores not last"),
    "rank_descending": (check_rank, _rank_ascending, "scores not descending"),
    "rank_ties": (check_rank, _rank_ties_by_path, "tie order changed"),
    "trim_budget": (check_trim_budget, _identity, "over budget"),
    "min_records_count": (check_min_records_prefix, _trim_ignoring_min_records,
                          "fewer than min_records kept"),
    "min_records_prefix": (check_min_records_prefix, _reverse, "not a prefix"),
    "dedupe_key": (check_dedupe_key_effect, _identity, "duplicate (path, line) kept"),
    "dedupe_whole": (check_dedupe_whole_effect, _identity, "duplicate record kept"),
    "allowlist": (check_allowlist_effect, _identity, "disallowed source kept"),
    "quarantine_drop": (check_quarantine_drop_effect, _identity, "marker record kept"),
    "quarantine_flag": (check_quarantine_flag_effect, _flag_nothing, "wrong quarantine flag"),
}


@pytest.mark.parametrize("name", sorted(CANARIES))
def test_canary_check_rejects_a_broken_stage(name):
    check, broken, message = CANARIES[name]
    with pytest.raises(AssertionError, match=re.escape(message) + r" \(seed=-?\d+\)"):
        for_each_case(lambda recs, seed: check(broken, recs, seed), canary_seeds)


def test_canary_subsequence_helper_respects_order_and_multiplicity():
    assert is_subsequence([1, 3], [1, 2, 3])
    assert not is_subsequence([3, 1], [1, 2, 3])
    assert not is_subsequence([1, 1], [1, 2])


def _raising(recs):
    raise KeyError("boom")


def test_canary_a_stage_that_raises_still_reports_its_seed():
    first = next(canary_seeds())
    with pytest.raises(AssertionError, match=re.escape(f"(seed={first})")) as info:
        for_each_case(lambda recs, seed: check_count(_raising, recs, seed), canary_seeds)
    assert isinstance(info.value.__cause__, KeyError)
```

- [ ] **Step 3: Run it**

Run: `python -m pytest tests/test_properties.py -q -p no:cacheprovider`
Expected: `61 passed` (35 before the G4/G5 fix wave).

- [ ] **Step 4: Prove a failure reproduces from its seed alone**

```bash
CONTEXEL_PROP_SEED=20261119 CONTEXEL_PROP_CASES=1 python -m pytest tests/test_properties.py -q -p no:cacheprovider
```
Expected: `61 passed` (one case per property, same seed; the CANARIES table still searches the default seeds, so it stays green). This is the reproduction recipe a failure message points to. With `CONTEXEL_PROP_CASES=0` the three original canaries fail loudly by design.

- [ ] **Step 5: Commit**

```bash
git add tests/_gen.py tests/test_properties.py
git commit -m "test: seeded property tests for every stage, with canaries"
```

---

### Task 2: Cross-process determinism sweep (AC 19)

**Files:**
- Create: `tests/test_determinism_processes.py`

**Interfaces:** Consumes: `contexel` public API. Produces: nothing other tasks use.

The child builds records containing **sets** (iteration order depends on the hash seed), mixed types and non-ASCII text, runs the full contract under a trace, and prints a SHA-256 of the output plus audit (the audit includes the policy fingerprint). The parent asserts the digest is identical for `PYTHONHASHSEED` 0, 1, 2 and 4242.

- [ ] **Step 1: Create `tests/test_determinism_processes.py`**

```python
"""Cross-process determinism: the same pipeline must produce byte-identical
output under different PYTHONHASHSEED values (AC 19).

Never run the child with ``python -I``: -I implies -E, which discards
PYTHON* environment variables, including PYTHONHASHSEED, and would make this
test vacuous.
"""
import hashlib
import os
import subprocess
import sys

CHILD = r"""
import hashlib, json, sys
sys.path.insert(0, {root!r})
from contexel import (allowlist, dedupe, pipeline, quarantine, rank, rescore,
                      select, stage, trace, trim_to_budget, truncate_field)

def records():
    out = []
    for i in range(60):
        out.append({{
            "path": "src/f%d.py" % (i % 7),
            "line": i % 5,
            "source": ["repo", "docs", "web"][i % 3],
            "snippet": "retry backoff jitter value%d café 日本語 %s" % (i, "x" * (i % 9)),
            "tags": {{"b", "a", "c%d" % (i % 4)}},   # a set: iteration order is hash-seeded
            "score": (i * 7) % 11,
        }})
    return out

contract = pipeline([
    stage(allowlist, field="source", allowed=["repo", "docs"]),
    stage(quarantine, fields=("snippet",)),
    stage(dedupe, key=["tags"]),
    stage(select, fields=["path", "line", "snippet", "tags"]),
    stage(rescore, query="retry backoff jitter", fields=("snippet",)),
    stage(truncate_field, field="snippet", max_tokens=10),
    stage(rank, by="score", desc=True),
    stage(trim_to_budget, max_tokens=200),
])
with trace(id_field="path") as t:
    out = contract(records())
audit = t.audit()
payload = json.dumps([out, audit], sort_keys=True, default=lambda v: sorted(v, key=repr),
                     ensure_ascii=False)
print(hashlib.sha256(payload.encode("utf-8")).hexdigest())
"""

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root when placed in tests/


def _probe(code: str, seed, flags=()) -> str:
    """Run ``code`` in a child with PYTHONHASHSEED=seed (variable removed when
    seed is None) and return its stripped stdout."""
    env = dict(os.environ)
    if seed is None:
        env.pop("PYTHONHASHSEED", None)
    else:
        env["PYTHONHASHSEED"] = seed
    proc = subprocess.run(
        [sys.executable, *flags, "-c", code],
        env=env, capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def run_with_seed(seed: str) -> str:
    return _probe(CHILD.format(root=ROOT), seed)


def test_same_output_across_hash_seeds():
    digests = {seed: run_with_seed(seed) for seed in ("0", "1", "2", "4242")}
    assert len(set(digests.values())) == 1, digests
    assert all(len(d) == 64 for d in digests.values())


def test_child_really_sees_the_requested_hash_seed():
    # Guards against the vacuous-test failure mode (a flag that drops the env):
    # assert the seed TOOK EFFECT, not merely that outputs differ.
    flag = "import sys; print(sys.flags.hash_randomization)"
    h = "print(hash('contexel'))"
    assert _probe(flag, "0") == "0", "PYTHONHASHSEED=0 must disable randomization"
    first, again = _probe(h, "1"), _probe(h, "1")
    assert first == again, "the same PYTHONHASHSEED must give the same hash()"
    assert _probe(h, "0") != first, "different PYTHONHASHSEED values must change hash()"
    # control: with the variable absent, randomization is on, so the flag discriminates
    assert _probe(flag, None) == "1"


def test_canary_a_hash_dependent_child_is_detected():
    """The sweep must be able to see a hash-seed dependence when one exists."""
    code = "print(','.join({'alpha', 'beta', 'gamma', 'delta', 'epsilon'}))"
    outs = set()
    for seed in ("0", "1", "2", "4242"):
        first, again = _probe(code, seed), _probe(code, seed)
        assert first == again, f"seed {seed} was not honoured (set order varied between runs)"
        outs.add(first)
    assert len(outs) > 1, "set order never varied; the sweep could not detect a hazard"
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/test_determinism_processes.py -q -p no:cacheprovider`
Expected: `3 passed`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_determinism_processes.py
git commit -m "test: assert identical output across PYTHONHASHSEED values"
```

---

### Task 3: Golden policy fingerprints (AC 29 baseline)

**Files:**
- Create: `tests/test_fingerprint_golden.py`

**Interfaces:** Consumes: only `contexel` (the `contract` shape is an inline copy of `generate_vectors.contract()` as of 2026-11-19, so a later edit to the parity contract cannot move a golden). Produces: the recorded baseline that Slice 3 must not change for plain pipelines.

The hex values were computed from the unmodified 0.1.17 canon on 2026-11-19 and were identical under `PYTHONHASHSEED` 0, 1 and 2. The two shapes added in the G4/G5 fix wave (`dict_with_mixed_keys_and_nesting`, `opaque_object`) were recorded the same way and also computed from a `git archive main` copy. **Never regenerate them to turn a test green.**

- [ ] **Step 1: Create `tests/test_fingerprint_golden.py`**

```python
"""Golden policy fingerprints, recorded from the 0.1.17 canon (2026-11-19).

These pin the compatibility promise of ADR-008 / AC 29: a pipeline that binds
none of {sets, nested pipelines, a tiktoken tokenizer} keeps its EXACT current
fingerprint after the audit-truthfulness change. Do not regenerate these values
to make a test pass: a change here is a behavior change that needs an ADR.

Every shape is written out inline (no shape depends on another module), and
together they bind every branch of ``_stable_repr``: primitives, lists and
tuples, dicts (mixed-type keys, nested values), named callables, and the
type-name fallback for an opaque object.
"""
import pytest

from contexel import (allowlist, dedupe, pipeline, quarantine, rank, rescore,
                      select, stage, trim_to_budget, truncate_field)


def key(r):  # a NAMED callable: callables fingerprint by __name__
    return r["a"]


def annotate(records, **_options):  # a NAMED custom stage
    return records


class Opaque:  # an opaque object: fingerprints by its type name only
    pass


SHAPES = {
    # today's parity contract, copied inline so the golden never moves with it
    "contract": (lambda: pipeline([
        stage(allowlist, field="source", allowed=["repo", "docs"]),
        stage(quarantine, fields=("snippet",)),
        stage(select, fields=["path", "line", "source", "snippet"]),
        stage(dedupe, key=["path", "line"]),
        stage(rescore, query="exponential backoff jitter", fields=("snippet", "path")),
        stage(truncate_field, field="snippet", max_tokens=12),
        stage(rank, by="score", desc=True),
        stage(trim_to_budget, max_tokens=150)]), "0a312755f913d64b"),
    "primitives": (lambda: pipeline([
        stage(select, fields=["a", "b"]), stage(dedupe, key="a"),
        stage(rank, by="score", desc=True), stage(trim_to_budget, max_tokens=100)]),
        "24b66acf41ad058f"),
    "list_of_mixed_scalars_and_none": (lambda: pipeline([
        stage(allowlist, field="s", allowed=["x", None, 1, 2.5, True]),
        stage(quarantine, fields=("snippet",), patterns=None, action="drop")]),
        "3e55e84d283957fb"),
    "dict_with_mixed_keys_and_nesting": (lambda: pipeline([
        stage(annotate, mapping={"b": [1, None, {"z": 2.5}], 1: "one",
                                 2.5: {"k": None}, None: [], (1, "t"): False},
              empty={}, label="m")]),
        "5d865072cb72afe5"),
    "opaque_object": (lambda: pipeline([stage(annotate, marker=Opaque(), n=3)]),
                      "79dab73b8b021852"),
    "named_callable": (lambda: pipeline([stage(rank, by=key, desc=False)]),
                       "c0528eaa77a2360e"),
    "bare_named_function": (lambda: pipeline([key]), "0841f22ac0700431"),
    "rescore_defaults": (lambda: pipeline([
        stage(rescore, query="a b", fields=("x", "y"))]), "11b53020d9d935bb"),
    "empty_pipeline": (lambda: pipeline([]), "2e38e77b22c314a4"),
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_fingerprint_matches_the_recorded_baseline(name):
    build, expected = SHAPES[name]
    assert build().fingerprint == expected


def test_keyword_order_does_not_change_the_fingerprint():
    a = pipeline([stage(truncate_field, field="s", max_tokens=5, suffix="..")])
    b = pipeline([stage(truncate_field, suffix="..", max_tokens=5, field="s")])
    assert a.fingerprint == b.fingerprint == "4576e85b3ab2efb1"


def test_stage_order_changes_the_fingerprint():
    s1, s2 = stage(select, fields=["a"]), stage(dedupe, key="a")
    assert pipeline([s1, s2]).fingerprint != pipeline([s2, s1]).fingerprint


def test_a_bound_parameter_changes_the_fingerprint():
    one = pipeline([stage(trim_to_budget, max_tokens=100)])
    two = pipeline([stage(trim_to_budget, max_tokens=101)])
    assert one.fingerprint != two.fingerprint
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/test_fingerprint_golden.py -q -p no:cacheprovider`
Expected: `12 passed` (10 before the G4/G5 fix wave).

- [ ] **Step 3: Commit**

```bash
git add tests/test_fingerprint_golden.py
git commit -m "test: pin today's policy fingerprints as the compatibility baseline"
```

---

### Task 4: The case table, generator edit and Python replay (AC 21, 22)

**Files:**
- Create: `parity/parity_cases.py`
- Modify: `parity/generate_vectors.py`
- Regenerate: `parity/vectors.json`
- Create: `tests/test_parity_cases.py`

**Interfaces:**
- Produces: `parity_cases.build_cases(fixture) -> list[dict]`, `parity_cases.run_case(case, fixture) -> Any`, `parity_cases.assert_in_envelope(value, where)`, `parity_cases.ALLOWED_KEYS`; and in `vectors.json`: `_meta.case_count: int` and `cases: [{id, stage, args, input, expect}]` where `input` is a records list, a list of sources (for `merge`), or the string `"$fixture"`.
- Consumes: `generate_vectors.FIXTURE`.

- [ ] **Step 1: Write the failing test first — create `tests/test_parity_cases.py`**

```python
"""The committed parity vectors' `cases` must equal what the Python canon
computes today (the same check CI does with `git diff`, runnable locally),
and the generator must reject data outside the documented parity envelope."""
import json
import os
import sys
import unicodedata

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "parity"))
import parity_cases  # noqa: E402

with open(os.path.join(ROOT, "parity", "vectors.json"), encoding="utf-8") as fh:
    VECTORS = json.load(fh)


def test_case_count_matches_meta_and_ids_are_unique():
    cases = VECTORS["cases"]
    assert VECTORS["_meta"]["case_count"] == len(cases)
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["id"])
def test_committed_case_matches_canon(case):
    assert set(case) <= parity_cases.ALLOWED_KEYS
    actual = parity_cases.run_case(case, VECTORS["fixture"])
    assert json.dumps(actual, sort_keys=True, ensure_ascii=False) == json.dumps(
        case["expect"], sort_keys=True, ensure_ascii=False)


def test_unicode_normalization_case_has_two_distinct_keys():
    case = next(c for c in VECTORS["cases"] if c["id"] == "dedupe/nfc_and_nfd_stay_distinct")
    keys = {r["k"] for r in case["input"]}
    assert len(keys) == 2
    a, b = sorted(keys)
    assert a != b
    assert unicodedata.normalize("NFC", a) == unicodedata.normalize("NFC", b)
    assert len(case["expect"]) == 2


@pytest.mark.parametrize("bad", [1.0, float("nan"), float("inf"), 2 ** 60, {1: "x"}, (1, {"a": 2.0}), b"x"])
def test_envelope_guard_rejects_values_ports_cannot_represent(bad):
    with pytest.raises(AssertionError):
        parity_cases.assert_in_envelope(bad, "t")


@pytest.mark.parametrize("ok", [0.5, 3, -7, "s", None, True, [1, 2.5], {"a": {"b": [0.25]}}])
def test_envelope_guard_accepts_representable_values(ok):
    parity_cases.assert_in_envelope(ok, "t")


# An integer-valued float reaching each part of a case: only the input
# (select drops it), only the args (an empty input), only the expectation
# (rescore with no query terms scores 0.0).
@pytest.mark.parametrize("part, case", [
    ("input", {"id": "bad/in", "stage": "select", "args": {"fields": ["b"]},
               "input": [{"a": 2.0, "b": 1}]}),
    ("args", {"id": "bad/in", "stage": "trim_to_budget", "args": {"max_tokens": 10.0},
              "input": []}),
    ("expect", {"id": "bad/in", "stage": "rescore", "args": {"query": "", "fields": ["a"]},
                "input": [{"a": "x"}]}),
])
def test_build_cases_runs_the_envelope_guard_on_every_part(monkeypatch, part, case):
    monkeypatch.setattr(parity_cases, "_raw_cases", lambda: [case])
    with pytest.raises(AssertionError, match=rf"bad/in\.{part}.*integer-valued float"):
        parity_cases.build_cases(VECTORS["fixture"])


def test_committed_cases_equal_what_the_case_table_builds_today():
    built = parity_cases.build_cases(VECTORS["fixture"])
    assert json.dumps(built, sort_keys=True, ensure_ascii=False) == json.dumps(
        VECTORS["cases"], sort_keys=True, ensure_ascii=False), \
        "parity_cases.py changed: run PYTHONPATH=. python parity/generate_vectors.py"
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_parity_cases.py -q -p no:cacheprovider`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'parity_cases'`.

- [ ] **Step 3: Create `parity/parity_cases.py`**

```python
"""Data-driven parity cases (ADR-007).

One table. The Python canon computes every expectation; the TypeScript and C#
suites replay the same JSON through one adapter per stage. Adding a case means
editing ONLY this file, then regenerating vectors.

Case shape (all JSON):
    {"id": "<stage>/<what>", "stage": <kind>, "args": {...}, "input": <records
     | "$fixture" | list-of-sources for merge>, "expect": <canon output>}

Kinds: the eight record stages, ``merge`` (input = list of sources),
``pipeline`` / ``shaped`` (args.stages = [{"stage", "args"}, ...]), and
``trace_report`` (args.stages + optional args.id_field; expect = report text).
Callable-valued arguments cannot be JSON: those stay hand-written edge vectors.
"""
from __future__ import annotations

from typing import Any, Dict, List

from contexel import (allowlist, dedupe, merge, pipeline, quarantine, rank,
                      rescore, select, shaped, stage, trace, trim_to_budget,
                      truncate_field)

RECORD_STAGES = {
    "select": select, "dedupe": dedupe, "allowlist": allowlist,
    "quarantine": quarantine, "rescore": rescore, "rank": rank,
    "truncate_field": truncate_field, "trim_to_budget": trim_to_budget,
}
ALLOWED_KEYS = {"id", "stage", "args", "input", "expect"}

# Arguments that make each record stage valid on an empty list (AC 20/22: the
# empty-input class had no cross-language coverage).
_EMPTY_ARGS: Dict[str, Dict[str, Any]] = {
    "select": {"fields": ["a"]},
    "dedupe": {"key": ["a"]},
    "allowlist": {"field": "a", "allowed": ["x"]},
    "quarantine": {"fields": ["a"]},
    "rescore": {"query": "x", "fields": ["a"]},
    "rank": {"by": "a"},
    "truncate_field": {"field": "a", "max_tokens": 3},
    "trim_to_budget": {"max_tokens": 10},
}


def _pipe(specs: List[dict]):
    return pipeline([stage(RECORD_STAGES[s["stage"]], **s["args"]) for s in specs])


def run_case(case: dict, fixture: List[dict]) -> Any:
    records = fixture if case["input"] == "$fixture" else case["input"]
    kind, args = case["stage"], case["args"]
    if kind in RECORD_STAGES:
        return RECORD_STAGES[kind](records, **args)
    if kind == "merge":
        return merge(*records, **args)
    if kind == "pipeline":
        return _pipe(args["stages"])(records)
    if kind == "shaped":
        return shaped(_pipe(args["stages"]))(lambda: records)()
    if kind == "trace_report":
        with trace(id_field=args.get("id_field")) as t:
            _pipe(args["stages"])(records)
        return t.report()
    raise ValueError(f"unknown case kind {kind!r}")


def _raw_cases() -> List[dict]:
    cases: List[dict] = []

    def add(cid: str, kind: str, args: dict, inp: Any) -> None:
        cases.append({"id": cid, "stage": kind, "args": args, "input": inp})

    for kind, args in _EMPTY_ARGS.items():
        add(f"{kind}/empty_input", kind, args, [])
    add("merge/empty_sources", "merge", {}, [])
    add("pipeline/empty_input", "pipeline",
        {"stages": [{"stage": "select", "args": {"fields": ["a"]}},
                    {"stage": "trim_to_budget", "args": {"max_tokens": 10}}]}, [])

    add("merge/concat_without_schema", "merge", {},
        [[{"a": 1}, {"a": 2}], [{"a": 3}]])
    add("merge/schema_first_present_wins_and_dedupes", "merge",
        {"schema": {"title": ["title", "name", "headline"],
                    "url": ["url", "link", "href"]}, "dedupe_key": "url"},
        [[{"title": "A", "url": "u1", "junk": 1}, {"name": "B", "link": "u2"}],
         [{"headline": "C", "href": "u1"}, {"title": "D", "url": "u3"}]])
    add("merge/schema_unmatched_record_becomes_empty", "merge",
        {"schema": {"title": ["title"]}}, [[{"other": 1}, {"title": "T"}]])

    add("rank/missing_field_goes_last_desc", "rank", {"by": "a"},
        [{"a": 2}, {"b": 1}, {"a": 3}, {"a": 2, "t": "second"}])
    add("rank/missing_field_goes_last_asc", "rank", {"by": "a", "desc": False},
        [{"a": 2}, {"b": 1}, {"a": 3}, {"a": 2, "t": "second"}])
    add("dedupe/nfc_and_nfd_stay_distinct", "dedupe", {"key": "k"},
        [{"k": "caf\u00e9"}, {"k": "cafe\u0301"}, {"k": "caf\u00e9"}])
    add("truncate_field/counts_code_points_not_bytes", "truncate_field",
        {"field": "s", "max_tokens": 4},
        [{"s": "日本語" * 10}, {"s": "emoji\U0001F600" * 6}])
    add("select/missing_and_nested_fields", "select", {"fields": ["a", "n", "zz"]},
        [{"a": 1, "n": {"x": [1, 2]}, "drop": True}, {"zz": None}])

    add("shaped/select_then_dedupe_on_fixture", "shaped",
        {"stages": [{"stage": "select", "args": {"fields": ["path", "line"]}},
                    {"stage": "dedupe", "args": {"key": ["path", "line"]}}]},
        "$fixture")
    add("pipeline/allowlist_then_trim_on_fixture", "pipeline",
        {"stages": [{"stage": "allowlist",
                     "args": {"field": "source", "allowed": ["repo"]}},
                    {"stage": "trim_to_budget", "args": {"max_tokens": 60}}]},
        "$fixture")
    add("trace_report/contract_on_fixture", "trace_report",
        {"id_field": "path",
         "stages": [
             {"stage": "allowlist", "args": {"field": "source", "allowed": ["repo", "docs"]}},
             {"stage": "quarantine", "args": {"fields": ["snippet"]}},
             {"stage": "select", "args": {"fields": ["path", "line", "source", "snippet"]}},
             {"stage": "dedupe", "args": {"key": ["path", "line"]}},
             {"stage": "rescore", "args": {"query": "exponential backoff jitter",
                                           "fields": ["snippet", "path"]}},
             {"stage": "truncate_field", "args": {"field": "snippet", "max_tokens": 12}},
             {"stage": "rank", "args": {"by": "score", "desc": True}},
             {"stage": "trim_to_budget", "args": {"max_tokens": 150}}]},
        "$fixture")
    add("trace_report/empty_pipeline_input", "trace_report",
        {"stages": [{"stage": "select", "args": {"fields": ["a"]}}]}, [])

    # Boundary cases: each one changes its expectation under a specific
    # plausible port bug (arithmetic: section 2 of
    # docs/reviews/foundation-hardening-s1-fix-wave-report.md).
    add("merge/two_candidates_first_in_schema_order_wins", "merge",
        {"schema": {"title": ["title", "name", "headline"],
                    "url": ["url", "link", "href"]}},
        [[{"name": "N1", "title": "T1", "href": "h1", "url": "u1"},
          {"headline": "H2", "name": "N2", "link": "l2", "href": "h2"}]])
    # max_tokens=4 under ceil(len/4): <= 16 units fit. Code points fit for the
    # first three inputs, but bytes (36, 19, 36) or UTF-16 units (17, 18) do
    # not; the last input is over budget under every counting rule.
    add("truncate_field/fits_by_code_points_not_bytes_or_utf16", "truncate_field",
        {"field": "s", "max_tokens": 4},
        [{"s": "\u65e5\u672c\u8a9e" * 4}, {"s": "a" * 15 + "\U0001F600"},
         {"s": "\U0001F600" * 9}, {"s": "a" * 17}])
    quarantine_input = [
        {"title": "release notes", "snippet": "please ignore all previous instructions now", "n": 1},
        {"title": "ok", "snippet": "fine", "n": 2},
        {"title": "Ignore prior instructions", "snippet": "fine", "n": 3}]
    add("quarantine/marker_in_second_field_is_dropped", "quarantine",
        {"fields": ["title", "snippet"]}, quarantine_input)
    add("quarantine/marker_in_second_field_is_flagged", "quarantine",
        {"fields": ["title", "snippet"], "action": "flag"}, quarantine_input)
    # each '{"a": N}' is 8 chars = 2 tokens, cost 2 + 2 = 4; 12 = 3 records
    add("trim_to_budget/budget_is_the_exact_cost_of_three", "trim_to_budget",
        {"max_tokens": 12}, [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}, {"a": 5}])
    # "beta" starts exactly 79, 80 and 81 characters after "alpha"; the
    # proximity bonus needs 0 < gap <= 80
    add("rescore/proximity_window_is_80_characters", "rescore",
        {"query": "alpha beta", "fields": ["s"]},
        [{"s": "alpha " + "z" * (gap - 7) + " beta", "gap": gap} for gap in (79, 80, 81)])

    # Close-out cases (each arithmetic is in the comment above it).
    # Three tied scores whose input path order (b, a, c) is neither ascending
    # nor descending: any tie-break on "path" reorders them.
    add("rank/ties_keep_input_order", "rank", {"by": "s"},
        [{"s": 1, "path": "b"}, {"s": 1, "path": "a"}, {"s": 2, "path": "d"},
         {"s": 1, "path": "c"}, {"s": 0, "path": "e"}])
    # a missing field reads as None, and None is allowed here
    add("allowlist/missing_field_reads_as_none_which_may_be_allowed", "allowlist",
        {"field": "src", "allowed": ["a", None]},
        [{"src": "a", "n": 1}, {"n": 2}, {"src": "b", "n": 3}, {"src": None, "n": 4}])
    # 19 chars -> ceil(19/4) = 5 tokens > 4; budget 4 - 1 (suffix) = 3 tokens
    # = 12 chars, and the 12-char cut "abcdefghi   " ends in spaces: rstrip
    add("truncate_field/cut_landing_in_whitespace_is_stripped_before_the_suffix",
        "truncate_field", {"field": "s", "max_tokens": 4},
        [{"s": "abcdefghi" + " " * 3 + "jklmnop"}])
    return cases


MAX_SAFE_INT = 2 ** 53


def assert_in_envelope(value: Any, where: str) -> None:
    """The documented parity envelope (ADR-001 4a, ADR-002 3): JSON data only,
    no NaN/Inf, no integer-valued floats (TypeScript cannot tell 1.0 from 1),
    integers within +-2**53."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, float):
        assert value == value and value not in (float("inf"), float("-inf")), f"{where}: NaN/Inf"
        assert not value.is_integer(), f"{where}: integer-valued float {value!r}"
        return
    if isinstance(value, int):
        assert abs(value) <= MAX_SAFE_INT, f"{where}: integer beyond 2**53"
        return
    if isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            assert_in_envelope(v, f"{where}[{i}]")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            assert isinstance(k, str), f"{where}: non-string key {k!r}"
            assert_in_envelope(v, f"{where}.{k}")
        return
    raise AssertionError(f"{where}: {type(value).__name__} is not JSON data")


def build_cases(fixture: List[dict]) -> List[dict]:
    ids = set()
    out = []
    for case in _raw_cases():
        assert case["id"] not in ids, f"duplicate case id {case['id']}"
        ids.add(case["id"])
        assert set(case) <= ALLOWED_KEYS, case
        expect = run_case(case, fixture)
        assert_in_envelope(case["input"] if case["input"] != "$fixture" else fixture, case["id"] + ".input")
        assert_in_envelope(case["args"], case["id"] + ".args")
        assert_in_envelope(expect, case["id"] + ".expect")
        out.append({**case, "expect": expect})
    return out
```

- [ ] **Step 4: Make four edits to `parity/generate_vectors.py`** (a–d below)

(a) After the `from contexel import (...)` block add:

```python
from parity_cases import build_cases
```

(b) Immediately after the line `audit.pop("policies")  # fingerprints are language-local in v1 (ADR-001)` add:

```python
    cases = build_cases(FIXTURE)  # data-driven cases (ADR-007)
```

(c) In the `_meta` dict, after `"fixture_records": len(FIXTURE),` add:

```python
            "case_count": len(cases),
```

(d) Replace the end of the `edges` dict (the lines `query="aa ab", fields=("s",), match="substring"),` / `},` / `}` that close `edges` and `vectors`) so `cases` becomes the last top-level key:

```python
                query="aa ab", fields=("s",), match="substring"),
        },
        "cases": cases,
    }
```

- [ ] **Step 5: Regenerate the vectors**

Run: `PYTHONPATH=. python parity/generate_vectors.py` (see Global Constraints: without `PYTHONPATH` it may import an installed `contexel`)
Expected: `wrote …\parity\vectors.json (…bytes)`.

- [ ] **Step 6: Prove the legacy sections are byte-identical and regeneration is stable**

```bash
PYTHONPATH=. python - <<'EOF'
import json, subprocess, sys
old = json.loads(subprocess.check_output(["git", "show", "HEAD:parity/vectors.json"]).decode("utf-8"))
new = json.load(open("parity/vectors.json", encoding="utf-8"))
legacy = [k for k in old if k != "_meta"]
assert all(new[k] == old[k] for k in legacy), "a legacy section changed"
assert {k: v for k, v in new["_meta"].items() if k != "case_count"} == old["_meta"]
assert [k for k in new if k not in old] == ["cases"], [k for k in new if k not in old]
first = open("parity/vectors.json", "rb").read()
subprocess.run([sys.executable, "parity/generate_vectors.py"], check=True, capture_output=True)
assert open("parity/vectors.json", "rb").read() == first, "regeneration is not byte-stable"
assert b"\r\n" not in first, "CRLF found: vectors must be LF-only"
print("OK: legacy sections identical; only _meta.case_count and cases added; regeneration byte-stable; LF only")
EOF
```
Expected: the `OK:` line. Any assertion failure means stop and diagnose (do not edit legacy sections).

- [ ] **Step 7: Run the Python replay and the whole Python suite**

```bash
python -m pytest tests/test_parity_cases.py -q -p no:cacheprovider      # expect: 52 passed (39 before the fix wave, 49 before the close-out)
python -m pytest -q -p no:cacheprovider --ignore-glob="tests/test_doctrine_*"   # expect: 200 passed (72 + 61 + 3 + 12 + 52)
```

- [ ] **Step 8: Commit**

```bash
git add parity/parity_cases.py parity/generate_vectors.py parity/vectors.json tests/test_parity_cases.py
git commit -m "test(parity): data-driven cases table with an envelope guard"
```

---

### Task 5: TypeScript generic runner (AC 21, 22)

**Files:**
- Create: `ts/test/cases.test.ts`
- Modify: `ts/package.json` (the `test` script)

**Interfaces:** Consumes: `vectors.cases`, `vectors._meta.case_count`, `vectors.fixture`; the TypeScript stage functions, which all have the shape `(records, options)` with camelCase options.

- [ ] **Step 1: Create `ts/test/cases.test.ts`**

```typescript
/**
 * Data-driven parity cases (ADR-007): replay every case in vectors.json
 * `cases` through one adapter per stage and compare with the Python canon.
 * Adding a case never touches this file.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  allowlist,
  dedupe,
  merge,
  pipeline,
  quarantine,
  rank,
  rescore,
  select,
  shaped,
  stage,
  trace,
  trimToBudget,
  truncateField,
  type Records,
  type StageFn,
} from "../src/index.js";

type Args = Record<string, unknown>;
interface Spec {
  stage: string;
  args: Args;
}
interface Case extends Spec {
  id: string;
  input: unknown;
  expect: unknown;
}

const vectors = JSON.parse(
  readFileSync(new URL("../../../parity/vectors.json", import.meta.url), "utf-8")
);
const FIXTURE: Records = vectors.fixture;
const ALLOWED_KEYS = new Set(["id", "stage", "args", "input", "expect"]);

// Python snake_case argument names -> TypeScript camelCase option names.
const camel = (s: string) => s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
function toOptions(args: Args): Args {
  return Object.fromEntries(Object.entries(args).map(([k, v]) => [camel(k), v]));
}

// One adapter per record stage: every TS stage has the shape (records, options).
type RecordStage = (records: Records, options: never) => Records;
const RECORD_STAGES: Record<string, RecordStage> = {
  select,
  dedupe,
  allowlist,
  quarantine,
  rescore,
  rank,
  truncate_field: truncateField,
  trim_to_budget: trimToBudget,
};

function bind(spec: Spec): StageFn {
  const fn = RECORD_STAGES[spec.stage];
  assert.ok(fn, `unknown stage ${spec.stage}`);
  return stage(fn as never, toOptions(spec.args) as never);
}
const build = (specs: Spec[]): StageFn => pipeline(specs.map(bind));

function run(c: Case): unknown {
  const input = c.input === "$fixture" ? FIXTURE : c.input;
  const records = input as Records;
  const fn = RECORD_STAGES[c.stage];
  if (fn) return fn(records, toOptions(c.args) as never);
  const stages = c.args.stages as Spec[];
  switch (c.stage) {
    case "merge":
      return merge(input as Records[], toOptions(c.args));
    case "pipeline":
      return build(stages)(records);
    case "shaped":
      return shaped(build(stages))(() => records)();
    case "trace_report": {
      const [, tr] = trace({ idField: (c.args.id_field as string) ?? undefined }, () =>
        build(stages)(records)
      );
      return tr.report();
    }
    default:
      throw new Error(`unknown case kind ${c.stage}`);
  }
}

test("the cases section is present and complete", () => {
  assert.ok(Array.isArray(vectors.cases), "vectors.cases missing");
  assert.ok(vectors.cases.length > 0, "vectors.cases is empty (a runner must never pass vacuously)");
  assert.strictEqual(
    vectors.cases.length,
    vectors._meta.case_count,
    "case_count disagrees with the cases array (a runner must not silently skip cases)"
  );
  const ids = vectors.cases.map((c: Case) => c.id);
  assert.strictEqual(new Set(ids).size, ids.length, "duplicate case ids");
});

for (const c of vectors.cases as Case[]) {
  test(`case ${c.id}`, () => {
    for (const key of Object.keys(c)) {
      assert.ok(ALLOWED_KEYS.has(key), `case ${c.id} has unsupported key ${key}`);
    }
    assert.deepStrictEqual(run(c), c.expect);
  });
}
```

- [ ] **Step 2: Add it to the `test` script in `ts/package.json`**

Replace
`"test": "tsc -p tsconfig.test.json && node --test dist-test/test/parity.test.js dist-test/test/behavior.test.js",`
with
`"test": "tsc -p tsconfig.test.json && node --test dist-test/test/parity.test.js dist-test/test/behavior.test.js dist-test/test/cases.test.js",`

(Without this edit CI would never run the new file.)

- [ ] **Step 3: Run the whole TypeScript suite**

Run: `cd ts && npm test`
Expected: `ℹ tests 73`, `ℹ pass 73`, `ℹ fail 0` (41 existing + 32 new: 31 cases + the completeness check; 64 with 22 cases before the G4/G5 fix wave, 70 with 28 before the close-out).

- [ ] **Step 4: Negative control — prove the runner can fail**

```bash
python - <<'EOF'
import json
p = "parity/vectors.json"
d = json.load(open(p, encoding="utf-8"))
c = next(x for x in d["cases"] if x["id"] == "rank/missing_field_goes_last_desc")
c["expect"] = list(reversed(c["expect"]))
d["cases"].append({"id": "bad/extra_key", "stage": "select", "args": {"fields": ["a"]},
                   "input": [], "expect": [], "surprise": 1})
d["_meta"]["case_count"] = len(d["cases"]) - 1
json.dump(d, open(p, "w", encoding="utf-8", newline="\n"), indent=2, ensure_ascii=False)
EOF
(cd ts && node --test dist-test/test/cases.test.js 2>&1 | grep -E "^✖|^ℹ (pass|fail)")
git checkout -- parity/vectors.json
```
Expected: three `✖` lines (completeness check, the tampered case, `bad/extra_key`) and `ℹ fail 3`. Then the tampered file is restored by `git checkout`. **Confirm `git status --short parity/vectors.json` prints nothing.**

- [ ] **Step 5: Commit**

```bash
git add ts/test/cases.test.ts ts/package.json
git commit -m "test(ts): replay data-driven parity cases through one adapter per stage"
```

---

### Task 6: C# generic runner (AC 21, 22)

**Files:**
- Create: `csharp/Contexel.Tests/CaseTests.cs`

**Interfaces:** Consumes: `VectorData.Vectors`, `AsList`, `AsRec`, `AsRecords`, `AssertDeepEqual`, `Fixture` (all existing in `VectorData.cs`); `Stages.*`, `Pipeline`, `Stage`, `Shaped.Wrap`, `Trace.Begin` (existing). `VectorData` preserves int-vs-float from raw JSON text, so integers arrive as `long`.

- [ ] **Step 1: Create `csharp/Contexel.Tests/CaseTests.cs`**

```csharp
using Xunit;
using static Contexel.Tests.VectorData;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>
/// Data-driven parity cases (ADR-007): replay every case in vectors.json
/// "cases" through one adapter per stage and compare with the Python canon.
/// Adding a case never touches this file.
/// </summary>
public class CaseTests
{
    private static readonly HashSet<string> AllowedKeys =
        ["id", "stage", "args", "input", "expect"];

    public static IEnumerable<object[]> CaseIds() =>
        AsList(Vectors["cases"]).Select(c => new object[] { (string)AsRec(c)["id"]! });

    private static string[] Strs(object? v) => v switch
    {
        string s => [s],
        List<object?> l => l.Select(x => (string)x!).ToArray(),
        _ => throw new ArgumentException("expected a string or a list of strings"),
    };

    private static object? OptStrs(Rec a, string key) =>
        a.TryGetValue(key, out var v) && v is not null ? Strs(v) : null;

    private static bool Flag(Rec a, string key, bool dflt) =>
        a.TryGetValue(key, out var v) ? (bool)v! : dflt;

    private static string Str(Rec a, string key, string dflt) =>
        a.TryGetValue(key, out var v) ? (string)v! : dflt;

    private static Records Input(Rec c) =>
        c["input"] is "$fixture" ? Fixture : AsRecords(c["input"]);

    // One adapter per record stage: JSON args -> the port's call shape.
    private static Records RunStage(string kind, Rec a, Records r) => kind switch
    {
        "select" => Stages.Select(r, Strs(a["fields"])),
        "dedupe" => Stages.Dedupe(r, OptStrs(a, "key")),
        "allowlist" => Stages.Allowlist(r, (string)a["field"]!, AsList(a["allowed"])),
        "quarantine" => Stages.Quarantine(r, OptStrs(a, "fields"), OptStrs(a, "patterns"),
            Str(a, "action", "drop"), Str(a, "into", "quarantined"),
            Flag(a, "replace_patterns", false)),
        "rescore" => Stages.Rescore(r, a["query"] is string q ? q : Strs(a["query"]),
            OptStrs(a, "fields"), Str(a, "into", "score"), Flag(a, "proximity", true),
            Str(a, "match", "word")),
        "rank" => Stages.Rank(r, (string)a["by"]!, Flag(a, "desc", true)),
        "truncate_field" => Stages.TruncateField(r, (string)a["field"]!, (int)(long)a["max_tokens"]!),
        "trim_to_budget" => Stages.TrimToBudget(r, (int)(long)a["max_tokens"]!,
            minRecords: a.TryGetValue("min_records", out var m) ? (int)(long)m! : 0),
        _ => throw new ArgumentException($"unknown stage {kind}"),
    };

    private static readonly HashSet<string> RecordStages =
        ["select", "dedupe", "allowlist", "quarantine", "rescore", "rank",
         "truncate_field", "trim_to_budget"];

    private static Stage Bind(Rec spec)
    {
        var kind = (string)spec["stage"]!;
        var args = AsRec(spec["args"]);
        return new Stage(kind, r => RunStage(kind, args, r), args);
    }

    private static Pipeline Build(Rec args) =>
        new(AsList(args["stages"]).Select(s => Bind(AsRec(s))).ToArray());

    private static object? Run(Rec c)
    {
        var kind = (string)c["stage"]!;
        var args = AsRec(c["args"]);
        if (RecordStages.Contains(kind)) return RunStage(kind, args, Input(c));
        switch (kind)
        {
            case "merge":
                return Stages.Merge(AsList(c["input"]).Select(AsRecords),
                    args.TryGetValue("schema", out var sc) && sc is not null
                        ? AsRec(sc).ToDictionary(kv => kv.Key,
                            kv => (object)(kv.Value is string s ? s : Strs(kv.Value)))
                        : null,
                    args.TryGetValue("dedupe_key", out var dk) ? (string?)dk : null);
            case "pipeline":
                return Build(args).Run(Input(c));
            case "shaped":
            {
                var records = Input(c);
                return Shaped.Wrap(Build(args), () => records)();
            }
            case "trace_report":
            {
                using var t = Trace.Begin(args.TryGetValue("id_field", out var f) ? (string?)f : null);
                Build(args).Run(Input(c));
                return t.Report();
            }
            default:
                throw new ArgumentException($"unknown case kind {kind}");
        }
    }

    [Fact]
    public void CasesSectionIsPresentAndComplete()
    {
        var cases = AsList(Vectors["cases"]);
        Assert.NotEmpty(cases); // a runner must never pass vacuously
        Assert.Equal((long)AsRec(Vectors["_meta"])["case_count"]!, (long)cases.Count);
        var ids = cases.Select(c => (string)AsRec(c)["id"]!).ToList();
        Assert.Equal(ids.Count, ids.Distinct().Count());
    }

    [Theory]
    [MemberData(nameof(CaseIds))]
    public void CaseMatchesPython(string id)
    {
        var c = AsList(Vectors["cases"]).Select(AsRec).Single(x => (string)x["id"]! == id);
        foreach (var key in c.Keys)
            Assert.True(AllowedKeys.Contains(key), $"case {id} has unsupported key {key}");
        AssertDeepEqual(c["expect"], Run(c), id);
    }
}
```

- [ ] **Step 2: Run only the new tests**

Run: `dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo -v q --filter "FullyQualifiedName~CaseTests"`
Expected: `Passed!  - Failed: 0, Passed: 32` (31 cases + the completeness check; 23 before the G4/G5 fix wave, 29 before the close-out).

- [ ] **Step 3: Run the whole C# suite**

Run: `dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo -v q`
Expected: `Passed!  - Failed: 0, Passed: 71` (39 existing + 32 new).

- [ ] **Step 4: Negative control**

Repeat Task 5 Step 4's tamper script, then run
`dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo -v q --filter "FullyQualifiedName~CaseTests"`
Expected: `Failed!  - Failed: 3`. Then `git checkout -- parity/vectors.json` and confirm `git status --short parity/vectors.json` prints nothing.

- [ ] **Step 5: Commit**

```bash
git add csharp/Contexel.Tests/CaseTests.cs
git commit -m "test(cs): replay data-driven parity cases through one adapter per stage"
```

---

### Task 7: Changelog, ADR status, full verification, handoff

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/adr/007-vector-format-v2-and-differential-fuzz.md` (status line)

- [ ] **Step 1: Add an `[Unreleased]` section to `CHANGELOG.md`**

Insert immediately above the line `## [0.1.17] — 2026-07-28`:

```markdown
## [Unreleased]

### Added — test infrastructure (no library behavior change)
- Seeded stdlib property tests for every stage (purity, determinism,
  idempotence, subsequence, count, input order, rank tie stability and
  budget invariants, and each filter stage's effect), every check with a
  canary proving it can fail; failures print their seed, including when a
  stage raises.
- A cross-process determinism test that sweeps `PYTHONHASHSEED` over a
  pipeline whose data contains sets, mixed types and non-ASCII text, and
  asserts that the requested seed actually took effect in each child process.
- Golden policy-fingerprint tests pinning today's values (the compatibility
  baseline for the audit-truthfulness work, ADR-008), including dict-valued
  and opaque-object parameters.
- Data-driven parity cases (ADR-007): `parity/parity_cases.py` is the single
  case table; `vectors.json` gains a `cases` array and `_meta.case_count`;
  the TypeScript and C# suites replay every case through one adapter per
  stage. First coverage of `merge`, `shaped`, `trace.report()` and the
  empty-input class in all three languages. A generator-side envelope guard
  rejects data TypeScript cannot represent (integer-valued floats, NaN/Inf,
  integers beyond 2^53), and a pinning test keeps the NFC/NFD case holding
  two distinct keys. Boundary cases pin the first-present `merge`
  candidate, code-point (not byte or UTF-16) token counting, multi-field
  `quarantine`, the exact `trim_to_budget` cost, the 80-character
  `rescore` proximity window, `rank` ties kept in input order, a missing
  `allowlist` field read as `None`, and whitespace stripped before the
  truncation suffix; both runners fail on an empty case list.
```

- [ ] **Step 2: Mark ADR-007's status**

In `docs/adr/007-vector-format-v2-and-differential-fuzz.md` change `**Status:** proposed` to `**Status:** accepted (cases format implemented in Slice 1; differential fuzz pending Slice 7)`.

- [ ] **Step 3: Full verification — all three languages, regenerate-and-diff**

```bash
python -m pytest -q -p no:cacheprovider --ignore-glob="tests/test_doctrine_*"       # expect: 200 passed
PYTHONPATH=. python parity/generate_vectors.py && git diff --exit-code parity/vectors.json && echo "vectors fresh"
(cd ts && npm test 2>&1 | grep -E "^ℹ (tests|pass|fail)")                           # expect: 73 / 73 / 0
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo -v q 2>&1 | tail -2 # expect: Passed: 71
git status --short                                                                   # expect: only CHANGELOG.md and the ADR modified
```

- [ ] **Step 4: Confirm no library code changed**

Run: `git diff --stat main -- contexel ts/src csharp/Contexel`
Expected: **no output.** Any output means the slice violated its core constraint: stop and revert that change.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md docs/adr/007-vector-format-v2-and-differential-fuzz.md
git commit -m "docs: changelog and ADR-007 status for the safety-net slice"
git log --oneline main..HEAD
```
Expected: the log lists one commit per task plus the review-fix commits, none pushed.

- [ ] **Step 6: Hand off to review (do not merge)**

Dispatch the `code-reviewer` agent (fresh context; G4) on `git diff main...HEAD`, then `qa-engineer` (G5) to re-run the three suites and the two negative controls independently. Report findings to the human. **Do not merge to `main` or push** without the human's go.

---

## Self-Review (run when this plan was written, 2026-11-19)

1. **Spec coverage.** §8 *Hash-seed test* → Task 2. *Generative property tests with canaries* → Task 1. *Vectors v2 (`cases`, one adapter per stage, `_meta.case_count`)* → Tasks 4–6. *`merge`, `shaped`, `trace.report` cases and the empty-input class (AC 22)* → Task 4's case table, replayed in Tasks 5–6. *AC 29 baseline* → Task 3. *`expect_error`* is deliberately **not** in this slice: runners reject unknown keys, and Slice 2 adds `expect_error` support together with the first error cases. No gaps.
2. **Placeholder scan.** No unfinished-work markers; every code step has complete code inlined from files that were executed during planning.
3. **Type consistency.** `build_cases`, `run_case`, `assert_in_envelope`, `ALLOWED_KEYS` are defined in Task 4 and used by `tests/test_parity_cases.py` with the same names. The case keys `id, stage, args, input, expect` are identical in the Python table, the TypeScript runner and the C# runner. Counts: 22 cases + 1 completeness test = 23 in each runner when written; 28 + 1 = 29 after the G4/G5 fix wave; 31 + 1 = 32 after the close-out round.
4. **Review Focus.** Items 1–5 each map to a named test or negative control above.

**Verified before writing (2026-11-19, scratch copies, not the repo):** the property and process tests (38 passed, canaries included), the golden fingerprints (10 passed under `PYTHONHASHSEED` 0/1/2), the Python replay and envelope guard (38 passed in scratch; the repository suite has 39 after the Task 4 review added a pinning test), the generator edit (legacy sections identical; regeneration byte-stable; LF only), the TypeScript runner (23/23 pass), the C# runner (23/23 pass), and the tamper negative control in both languages (3 failures each).

**G4/G5 fix wave (2026-11-19, after the whole-branch review and the G5 QA; scratch copies from `git archive`, never the repo):** the code blocks above for `tests/_gen.py`, `tests/test_properties.py`, `tests/test_fingerprint_golden.py`, `tests/test_parity_cases.py`, `parity/parity_cases.py`, `ts/test/cases.test.ts`, `csharp/Contexel.Tests/CaseTests.cs` and the `CHANGELOG.md` section were replaced by the fixed files (byte-identical). Repository totals: Python 197 passed, TypeScript 70 pass, C# 68 passed, 28 cases. All 17 QA mutations that had survived (rows 1, 7, 15, 17, 18, 19, 22, 29, 30, 32, 33, 36, 37, 39, 41, 42, 47) now fail at least one test, rows 6, 14 and 27 are still caught, the tamper negative control still fails 3 tests in each runner, and `cases: []` with `case_count: 0` now fails both runners. Evidence: `docs/reviews/foundation-hardening-s1-fix-wave-report.md` (findings: `docs/reviews/foundation-hardening-s1-fix-wave-findings.md`; the first QA pass: `docs/qa/foundation-hardening-s1-qa-pass-1.md`).

**Close-out round (2026-11-20, after the opus re-review and the second QA pass, `docs/qa/foundation-hardening-s1-qa-pass-2.md`):** three cases appended after the existing 28 in `parity/parity_cases.py`, because only the Python case table could pin these survivors: `rank/ties_keep_input_order` (a tie-break on `path` in Python, TypeScript or C# rank), `allowlist/missing_field_reads_as_none_which_may_be_allowed` (QA-2 P7) and `truncate_field/cut_landing_in_whitespace_is_stripped_before_the_suffix` (QA-2 P5). All five mutants survived at `f44d006` and fail at `d5439d2` (fresh scratch copy per mutant, `python -B`). Totals: Python 200 passed, TypeScript 73 pass, C# 71 passed, 31 cases. The `parity/parity_cases.py` block above was re-synced (byte-identical), and the QA and review reports were filed, sanitized, under `docs/qa/` and `docs/reviews/`.
