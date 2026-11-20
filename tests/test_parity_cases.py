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
    actual = parity_cases.outcome(case, VECTORS["fixture"])
    committed = {k: case[k] for k in ("expect", "expect_error") if k in case}
    assert len(committed) == 1, "a case has exactly one of expect / expect_error"
    assert json.dumps(actual, sort_keys=True, ensure_ascii=False) == json.dumps(
        committed, sort_keys=True, ensure_ascii=False)


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
