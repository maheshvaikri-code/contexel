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


def test_the_stem_vectors_hold_at_least_a_hundred_pairs():
    """Brief AC 18: at least 100 word -> stem pairs, identical in all three languages."""
    stem_cases = [c for c in VECTORS["cases"] if c["stage"] == "stem"]
    assert all(len(c["input"]) == len(c["expect"]) for c in stem_cases)
    assert sum(len(c["input"]) for c in stem_cases) >= 100


def test_the_undoubling_group_has_an_ing_and_an_ed_word_for_every_listed_letter():
    """Each of the 17 undoubling letters must change some stem if it is dropped
    from the rule: the vectors need an "ing" and an "ed" word for every one."""
    from contexel.stem import _UNDOUBLE

    case = next(c for c in VECTORS["cases"] if c["id"] == "stem/undoubling_each_listed_letter")
    assert len(_UNDOUBLE) == 17
    for suffix in ("ing", "ed"):
        covered = {w[-len(suffix) - 1] for w in case["input"]
                   if w.endswith(suffix) and w[-len(suffix) - 1] == w[-len(suffix) - 2]}
        assert covered >= set(_UNDOUBLE), (suffix, sorted(set(_UNDOUBLE) - covered))


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["id"])
def test_committed_case_matches_canon(case):
    assert set(case) <= parity_cases.ALLOWED_KEYS
    actual = parity_cases.outcome(case, VECTORS["fixture"])
    committed = {k: case[k] for k in ("expect", "expect_error") if k in case}
    assert len(committed) == 1, "a case has exactly one of expect / expect_error"
    assert json.dumps(actual, sort_keys=True, ensure_ascii=False) == json.dumps(
        committed, sort_keys=True, ensure_ascii=False)


def _check_the_budget_bites(ranked, kept, out):
    """What the budget must have done to the end-to-end log case: `ranked` is
    the record list handed to trim_to_budget, `kept` what it returned, `out`
    the joined text of `kept`."""
    # the budget dropped records: fewer remain after trim_to_budget than before
    assert len(kept) < len(ranked)
    # the lines it cut reached trim_to_budget and are absent from the output:
    # both "health check ok" lines dedupe left, "cache warmed" and the line with
    # accented characters (all four score 0 and rank last)
    before = "".join(r["text"] for r in ranked)
    for cut in ("health check ok", "cache warmed", chr(0xE9) + "v" + chr(0xE9) + "nement"):
        assert cut in before
        assert cut not in out
    # the best lines lead: ERROR (all three query words), then the two WARN lines
    lines = out.splitlines()
    assert " ERROR timeout after retry" in lines[0]
    assert " WARN  retry backoff jitter" in lines[1]
    assert " WARN  retry limit reached" in lines[2]


def test_the_end_to_end_log_case_fits_its_budget_and_keeps_the_best_lines_first():
    from contexel import as_records, join, tokens, trim_to_budget

    case = next(c for c in VECTORS["cases"] if c["id"] == "text_pipeline/log_text_end_to_end")
    stages = case["args"]["stages"]
    assert stages[-1]["stage"] == "trim_to_budget"
    budget = stages[-1]["args"]["max_tokens"]
    out = case["expect"]
    # split makes one record per line; dedupe drops only the exact duplicate
    # (the second "10:00:03 health check ok" line; the 10:00:07 one differs by
    # its timestamp and stays); rescore scores the lines that mention the query
    # and gives the others 0; rank puts the best first (ties keep their order);
    # trim_to_budget then keeps records from the front while their cost, each
    # record with its metadata, stays within the budget
    ranked = parity_cases._pipe(stages[:-1])(as_records(case["input"]))
    kept = trim_to_budget(ranked, max_tokens=budget)
    assert join(kept) == out
    assert sum(tokens.count(r) + 2 for r in kept) <= budget
    _check_the_budget_bites(ranked, kept, out)
    # the joined text is smaller still than the records it came from
    assert tokens.count(out) <= budget
    assert out.startswith("2026-11-19 10:00:04 ERROR timeout after retry")
    assert out.count("retry") >= 3
    assert len(out) < len(case["input"])


def test_error_cases_use_only_documented_codes_and_strict_is_true_or_absent():
    from contexel import errors
    error_cases = [c for c in VECTORS["cases"] if "expect_error" in c]
    assert error_cases, "no error case: expect_error would be untested"
    assert {c["expect_error"]["code"] for c in error_cases} == set(errors.CODES)
    for c in VECTORS["cases"]:
        assert c.get("strict", True) is True


@pytest.mark.parametrize("case, fragment", [
    ({"id": "bad/code", "stage": "select", "args": {"fields": ["a"]}, "input": None,
      "expect_error": {"code": "config.empty"}, "strict": True}, "the canon did"),
    ({"id": "bad/ok", "stage": "select", "args": {"fields": ["a"]}, "input": [{"a": 1}],
      "expect_error": {"code": "input.not_list"}}, "the canon did"),
    ({"id": "bad/undeclared", "stage": "select", "args": {"fields": ["a"]},
      "input": None, "strict": True}, "unexpected error"),
])
def test_build_cases_checks_that_the_canon_really_raises_the_declared_code(
        monkeypatch, case, fragment):
    monkeypatch.setattr(parity_cases, "_raw_cases", lambda: [case])
    with pytest.raises(AssertionError, match=fragment):
        parity_cases.build_cases(VECTORS["fixture"])


def test_build_cases_rejects_a_case_declaring_both_expect_and_expect_error(monkeypatch):
    case = {"id": "bad/both", "stage": "select", "args": {"fields": ["a"]},
            "input": None, "strict": True, "expect": [{"a": 1}],
            "expect_error": {"code": "input.not_list"}}
    monkeypatch.setattr(parity_cases, "_raw_cases", lambda: [case])
    with pytest.raises(AssertionError, match=r"bad/both.*both expect and expect_error"):
        parity_cases.build_cases(VECTORS["fixture"])


def test_build_cases_rejects_a_case_with_a_misspelled_key(monkeypatch):
    case = {"id": "bad/typo", "stage": "select", "args": {"fields": ["a"]},
            "input": [{"a": 1}], "expected": [{"a": 1}]}
    monkeypatch.setattr(parity_cases, "_raw_cases", lambda: [case])
    with pytest.raises(AssertionError):
        parity_cases.build_cases(VECTORS["fixture"])


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
    ("args", {"id": "bad/in", "stage": "allowlist",
              "args": {"field": "a", "allowed": [2.0]}, "input": []}),
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
