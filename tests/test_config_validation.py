"""Configuration validation (ADR-003, brief AC 7): a misconfigured call always
raises a typed ConfigError -- strict mode is not needed -- and never silently
does something else."""
import pytest

from contexel import (ConfigError, dedupe, rank, rescore, select, trim_to_budget,
                      truncate_field)

RECS = [{"a": "x y", "n": 1}, {"a": "y z", "n": 2}]


def raised(call):
    with pytest.raises(ConfigError) as info:
        call()
    return info.value


def test_rescore_unknown_match_raises():
    for bad in ("fuzzy", "WORD", "", None, 5, ["word"]):
        e = raised(lambda: rescore(RECS, "x", fields=["a"], match=bad))
        assert (e.code, e.stage, e.param) == ("config.invalid_value", "rescore", "match")
    assert rescore(RECS, "x", fields=["a"], match="word")
    assert rescore(RECS, "x", fields=["a"], match="substring")


def test_rescore_match_stem_is_reserved_until_the_stemmer_ships():
    e = raised(lambda: rescore(RECS, "x", fields=["a"], match="stem"))
    assert e.code == "config.invalid_value"
    assert "not available yet" in str(e)


def test_rescore_empty_fields_raises():
    for empty in ([], ()):
        e = raised(lambda: rescore(RECS, "x", fields=empty))
        assert (e.code, e.param) == ("config.empty", "fields")


@pytest.mark.parametrize("kwargs, param", [
    ({"query": None}, "query"),
    ({"query": 5}, "query"),
    ({"query": "x", "fields": 5}, "fields"),
    ({"query": "x", "fields": [1]}, "fields"),
    ({"query": "x", "into": 5}, "into"),
    ({"query": "x", "proximity": "yes"}, "proximity"),
    ({"query": "x", "proximity": 1}, "proximity"),
])
def test_rescore_wrong_typed_parameters_raise(kwargs, param):
    e = raised(lambda: rescore(RECS, **{"fields": ["a"], **kwargs}))
    assert (e.code, e.param) == ("config.invalid_value", param)


def test_configuration_errors_raise_even_with_no_records_and_no_strict_mode():
    assert raised(lambda: rescore([], "x", match="fuzzy")).code == "config.invalid_value"
    assert raised(lambda: trim_to_budget([], -1)).code == "config.invalid_value"
    # an empty query is not a configuration error: it scores everything 0.0
    assert rescore(RECS, "", fields=["a"]) == [{**r, "score": 0.0} for r in RECS]


@pytest.mark.parametrize("stage_name, call", [
    ("select", lambda: select([], 5)),
    ("dedupe", lambda: dedupe([], key=5)),
    ("rank", lambda: rank([], 5)),
    ("rescore", lambda: rescore([], None)),
    ("truncate_field", lambda: truncate_field([], "a", None)),
    ("trim_to_budget", lambda: trim_to_budget([], None)),
], ids=["select", "dedupe", "rank", "rescore", "truncate_field", "trim_to_budget"])
def test_every_configuration_stage_validates_even_on_an_empty_record_list(stage_name, call):
    e = raised(call)
    assert (e.code, e.stage) == ("config.invalid_value", stage_name)


@pytest.mark.parametrize("bad", [None, -1, -100, 1.5, 10.0, "10", True, False, [10]])
def test_max_tokens_must_be_a_non_negative_integer(bad):
    for call in (lambda: trim_to_budget(RECS, bad),
                 lambda: truncate_field(RECS, "a", bad)):
        e = raised(call)
        assert (e.code, e.param) == ("config.invalid_value", "max_tokens")
        assert isinstance(e, ValueError) and not isinstance(e, TypeError)


def test_max_tokens_zero_returns_empty_and_stays_valid():
    assert trim_to_budget(RECS, 0) == []
    assert truncate_field(RECS, "a", 0)  # valid; clips to the minimum, never raises


def test_bool_is_not_a_valid_max_tokens():
    assert raised(lambda: trim_to_budget(RECS, True)).code == "config.invalid_value"
    assert raised(lambda: truncate_field(RECS, "a", True)).code == "config.invalid_value"


@pytest.mark.parametrize("bad", [-1, 1.5, None, True, "1"])
def test_min_records_must_be_a_non_negative_integer(bad):
    e = raised(lambda: trim_to_budget(RECS, 10, min_records=bad))
    assert e.param == "min_records"
    assert trim_to_budget(RECS, 0, min_records=1) == RECS[:1]


def test_truncate_field_field_and_suffix_must_be_strings():
    assert raised(lambda: truncate_field(RECS, 5, 10)).param == "field"
    assert raised(lambda: truncate_field(RECS, "a", 10, suffix=None)).param == "suffix"


@pytest.mark.parametrize("bad", [None, 5, 1.5, ["a", 1], {"a": 1}, {"a"}, b"a"])
def test_fields_must_be_a_string_or_a_list_of_strings(bad):
    for call in (lambda: select(RECS, bad),
                 lambda: rescore(RECS, "x", fields=bad)):
        e = raised(call)
        assert e.code == "config.invalid_value" and e.param == "fields"


def test_a_string_a_list_and_a_tuple_are_valid_fields_and_a_bare_string_is_one_field():
    assert select(RECS, "a") == [{"a": r["a"]} for r in RECS]
    assert select(RECS, ["a"]) == select(RECS, ("a",)) == select(RECS, "a")


def test_dedupe_key_must_be_none_a_string_or_a_list_of_strings():
    assert raised(lambda: dedupe(RECS, key=5)).param == "key"
    assert raised(lambda: dedupe(RECS, key=["a", 1])).param == "key"
    assert dedupe(RECS, key=None) == RECS
    assert dedupe(RECS, key="a") == dedupe(RECS, key=["a"]) == RECS


@pytest.mark.parametrize("by, desc, param", [
    (5, True, "by"), (None, True, "by"), (["n"], True, "by"),
    ("n", 1, "desc"), ("n", None, "desc"),
])
def test_rank_by_and_desc_are_validated(by, desc, param):
    assert raised(lambda: rank(RECS, by, desc)).param == param


def test_rank_accepts_a_field_name_and_a_key_function():
    assert rank(RECS, "n") == RECS[::-1]
    assert rank(RECS, lambda r: r["n"], desc=False) == RECS


def test_every_configuration_error_carries_its_stage_name():
    cases = {
        "select": lambda: select(RECS, 5),
        "dedupe": lambda: dedupe(RECS, key=5),
        "rank": lambda: rank(RECS, 5),
        "rescore": lambda: rescore(RECS, None),
        "truncate_field": lambda: truncate_field(RECS, "a", None),
        "trim_to_budget": lambda: trim_to_budget(RECS, None),
    }
    for stage_name, call in cases.items():
        assert raised(call).stage == stage_name
