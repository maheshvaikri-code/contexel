"""Generative property tests for every stage (stdlib only, seeded).

A failure message always carries the seed: set CONTEXEL_PROP_SEED to it and
CONTEXEL_PROP_CASES=1 to reproduce. Each property has a *canary* (a
deliberately broken stage) proving the harness can actually fail.
"""
import copy
import itertools
import json
import random

import pytest

from contexel import (allowlist, dedupe, quarantine, rank, rescore, select,
                      tokens, trim_to_budget, truncate_field)

from _gen import case, seeds

STAGES = {
    "select": lambda r: select(r, ["path", "snippet", "score"]),
    "dedupe_key": lambda r: dedupe(r, key=["path", "line"]),
    "dedupe_whole": lambda r: dedupe(r),
    "allowlist": lambda r: allowlist(r, "source", ["repo", "docs"]),
    "quarantine_drop": lambda r: quarantine(r),
    "quarantine_flag": lambda r: quarantine(r, action="flag"),
    "rescore": lambda r: rescore(r, "retry backoff jitter", fields=("snippet", "path")),
    "rank": lambda r: rank(r, by="score"),
    "truncate": lambda r: truncate_field(r, "snippet", 6),
    "trim": lambda r: trim_to_budget(r, 80),
}
# quarantine_flag is deliberately absent from IDEMPOTENT: ADR-003 makes a
# second flag pass raise input.field_conflict instead of overwriting.
IDEMPOTENT = ["select", "dedupe_key", "dedupe_whole", "allowlist",
              "quarantine_drop", "rescore", "rank", "truncate", "trim"]
SUBSEQUENCE = ["dedupe_key", "dedupe_whole", "allowlist", "quarantine_drop", "trim"]
SAME_LENGTH = ["select", "quarantine_flag", "rescore", "rank", "truncate"]


def canon(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def is_subsequence(small, big):
    it = iter(big)
    return all(any(item == other for other in it) for item in small)


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


@pytest.mark.parametrize("name", sorted(STAGES))
def test_stage_is_pure_and_deterministic(name):
    fn = STAGES[name]
    for seed in seeds():
        _, recs = case(seed)
        check_purity(fn, recs, seed)
        check_determinism(fn, recs, seed)


@pytest.mark.parametrize("name", IDEMPOTENT)
def test_stage_is_idempotent(name):
    for seed in seeds():
        _, recs = case(seed)
        check_idempotent(STAGES[name], recs, seed)


@pytest.mark.parametrize("name", SUBSEQUENCE)
def test_filter_stage_returns_a_subsequence(name):
    for seed in seeds():
        _, recs = case(seed)
        assert is_subsequence(STAGES[name](recs), recs), f"seed={seed}"


@pytest.mark.parametrize("name", SAME_LENGTH)
def test_transform_stage_preserves_count(name):
    for seed in seeds():
        _, recs = case(seed)
        assert len(STAGES[name](recs)) == len(recs), f"seed={seed}"


def test_rank_is_a_permutation_and_stable():
    for seed in seeds():
        _, recs = case(seed)
        out = rank(recs, by="score")
        assert sorted(map(canon, out)) == sorted(map(canon, recs)), f"seed={seed}"
        present = [r for r in out if "score" in r]
        scores = [r["score"] for r in present]
        assert scores == sorted(scores, reverse=True), f"seed={seed}"
        assert all("score" not in r for r in out[len(present):]), f"seed={seed}"


def test_trim_never_exceeds_budget_without_min_records():
    for seed in seeds():
        _, recs = case(seed)
        out = trim_to_budget(recs, 80)
        assert sum(tokens.count(r) + 2 for r in out) <= 80, f"seed={seed}"


def test_trim_min_records_keeps_the_best_records():
    for seed in seeds():
        _, recs = case(seed)
        out = trim_to_budget(recs, 5, min_records=2)
        assert len(out) >= min(2, len(recs)), f"seed={seed}"
        assert out == recs[: len(out)], f"seed={seed}"


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
