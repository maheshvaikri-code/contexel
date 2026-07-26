from contexel import (
    select, dedupe, rank, truncate_field, trim_to_budget, merge,
    pipeline, stage, trace, tokens,
)


# ---- stages ---------------------------------------------------------------

def test_select_keeps_only_fields():
    recs = [{"a": 1, "b": 2, "junk": "x"}, {"a": 3, "junk": "y"}]
    assert select(recs, ["a", "b"]) == [{"a": 1, "b": 2}, {"a": 3}]


def test_dedupe_by_key_preserves_order():
    recs = [{"url": "u1"}, {"url": "u2"}, {"url": "u1"}]
    assert dedupe(recs, key="url") == [{"url": "u1"}, {"url": "u2"}]


def test_dedupe_full_record():
    assert dedupe([{"a": 1}, {"a": 1}, {"a": 2}]) == [{"a": 1}, {"a": 2}]


def test_dedupe_multi_key():
    recs = [{"a": 1, "b": 1}, {"a": 1, "b": 2}, {"a": 1, "b": 1}]
    assert dedupe(recs, key=["a", "b"]) == [{"a": 1, "b": 1}, {"a": 1, "b": 2}]


def test_rank_desc_and_missing_last():
    recs = [{"s": 1}, {"x": 0}, {"s": 5}, {"s": 3}]
    out = rank(recs, by="s", desc=True)
    assert out[:3] == [{"s": 5}, {"s": 3}, {"s": 1}]
    assert out[3] == {"x": 0}


def test_rank_callable():
    recs = [{"n": "bb"}, {"n": "a"}, {"n": "ccc"}]
    out = rank(recs, by=lambda r: len(r["n"]), desc=False)
    assert [r["n"] for r in out] == ["a", "bb", "ccc"]


def test_truncate_field_clips_long_string():
    out = truncate_field([{"body": "x" * 1000}], "body", max_tokens=10)
    assert tokens.count(out[0]["body"]) <= 10
    assert out[0]["body"].endswith("\u2026")


def test_truncate_field_leaves_short_and_nonstring():
    out = truncate_field([{"body": "short"}, {"body": 42}], "body", max_tokens=100)
    assert out[0]["body"] == "short"
    assert out[1]["body"] == 42


def test_truncate_field_does_not_mutate_input():
    recs = [{"body": "x" * 1000}]
    truncate_field(recs, "body", max_tokens=10)
    assert recs[0]["body"] == "x" * 1000


def test_trim_to_budget_keeps_prefix_within_budget():
    recs = [{"id": i, "body": "word " * 20} for i in range(5)]
    costs = [tokens.count(r) + 2 for r in recs]
    out = trim_to_budget(recs, max_tokens=costs[0] + costs[1])
    assert out == recs[:2]


def test_trim_to_budget_empty_when_budget_tiny():
    assert trim_to_budget([{"body": "x" * 1000}], max_tokens=1) == []


def test_merge_normalizes_heterogeneous_sources():
    web = [{"title": "A", "url": "u1"}]
    docs = [{"headline": "B", "link": "u2"}]
    out = merge(web, docs, schema={"title": ["title", "headline"], "url": ["url", "link"]})
    assert out == [{"title": "A", "url": "u1"}, {"title": "B", "url": "u2"}]


def test_merge_concat_when_no_schema():
    assert merge([{"a": 1}], [{"a": 2}]) == [{"a": 1}, {"a": 2}]


def test_merge_dedupe_key():
    out = merge([{"url": "u1"}], [{"url": "u1"}, {"url": "u2"}], dedupe_key="url")
    assert out == [{"url": "u1"}, {"url": "u2"}]


# ---- trace ----------------------------------------------------------------

def test_trace_records_each_stage():
    recs = [{"url": "u1", "big": "x" * 200},
            {"url": "u1", "big": "x" * 200},
            {"url": "u2", "big": "x" * 200}]
    with trace() as t:
        r = select(recs, ["url", "big"])
        r = dedupe(r, key="url")
    assert [e.stage for e in t.entries] == ["select", "dedupe"]
    assert t.tokens_before > 0
    assert t.tokens_after <= t.tokens_before
    assert 0.0 <= t.reduction <= 1.0
    assert "reduction" in t.report()


def test_no_trace_is_zero_cost_and_works():
    from contexel.trace import current_trace
    assert current_trace() is None
    assert select([{"a": 1, "b": 2}], ["a"]) == [{"a": 1}]


# ---- pipeline -------------------------------------------------------------

def test_pipeline_composes_stages():
    shape = pipeline([stage(select, fields=["url"]), stage(dedupe, key="url")])
    out = shape([{"url": "u1", "x": 1}, {"url": "u1", "x": 2}, {"url": "u2"}])
    assert out == [{"url": "u1"}, {"url": "u2"}]


def test_pipeline_accepts_bare_lambda():
    assert pipeline([lambda recs: recs[:1]])([1, 2, 3]) == [1]


# ---- tokens ---------------------------------------------------------------

def test_tokens_basic():
    assert tokens.count("") == 0
    assert tokens.count("hello world") > 0
    assert tokens.count("x" * 100) > tokens.count("x" * 10)
    assert tokens.count({"a": "hello"}) > 0


def test_tokens_pluggable():
    try:
        tokens.set_tokenizer(lambda text: len(text.split()))
        assert tokens.count("a b c") == 3
    finally:
        tokens.set_tokenizer(None)
    assert tokens.count("a b c") >= 1
