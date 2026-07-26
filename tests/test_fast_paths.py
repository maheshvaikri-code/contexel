"""The fast paths must be invisible: identical outputs, only faster."""
from contexel import dedupe, tokens, truncate_field

LONG = [{"id": i, "text": "lorem ipsum dolor sit amet " * 40} for i in range(20)]


def test_truncate_closed_form_matches_generic_search():
    # Wrapping the heuristic defeats the identity check, forcing the generic
    # binary-search path — both paths must produce byte-identical output.
    wrapped = lambda text: tokens.count(text)  # noqa: E731
    fast = truncate_field(LONG, "text", max_tokens=12)
    generic = truncate_field(LONG, "text", max_tokens=12, tokenizer=wrapped)
    assert fast == generic


def test_truncate_fast_path_is_detected():
    assert tokens.is_heuristic(None)
    assert not tokens.is_heuristic(lambda text: 1)


def test_dedupe_mixed_types_stay_distinct():
    records = [{"k": 1}, {"k": 1.0}, {"k": True}, {"k": "1"}]
    assert len(dedupe(records, key="k")) == 4  # json semantics preserved


def test_dedupe_unhashable_values_fall_back():
    records = [
        {"k": {"a", "b"}},  # set: unhashable in a tuple fingerprint
        {"k": {"b", "a"}},
        {"k": {"a", "c"}},
    ]
    assert len(dedupe(records, key="k")) == 2


def test_dedupe_whole_record_ignores_key_order():
    records = [{"a": 1, "b": 2}, {"b": 2, "a": 1}]
    assert len(dedupe(records)) == 1
