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
