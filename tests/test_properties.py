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
