"""Context-shaping-plane surfaces: async @shaped, scoped token accounting,
policy fingerprints, and audit-grade traces."""
import asyncio

from contexel import dedupe, pipeline, select, shaped, stage, tokens, trace, trim_to_budget


def test_shaped_wraps_async_tools():
    @shaped([stage(select, fields=["url"]), stage(dedupe, key="url")])
    async def search(query: str) -> list[dict]:
        return [{"url": "u1", "x": 1}, {"url": "u1", "x": 2}, {"url": "u2"}]

    out = asyncio.run(search("q"))
    assert out == [{"url": "u1"}, {"url": "u2"}]


def test_shaped_sync_unchanged():
    @shaped([stage(select, fields=["url"])])
    def search(query: str) -> list[dict]:
        return [{"url": "u1", "x": 1}]

    assert search("q") == [{"url": "u1"}]


def test_scoped_tokenizer_is_context_local():
    text = "abcd" * 25  # 100 chars -> 25 heuristic tokens
    assert tokens.count(text) == 25
    with tokens.scoped(tokenizer=lambda t: 1):
        assert tokens.count(text) == 1
        assert not tokens.is_heuristic()
    assert tokens.count(text) == 25  # restored on exit
    assert tokens.is_heuristic()


def test_scoped_isolates_concurrent_tasks():
    async def tenant(cost: int, text: str) -> int:
        with tokens.scoped(tokenizer=lambda t, c=cost: c):
            await asyncio.sleep(0)  # force interleaving
            return tokens.count(text)

    async def main():
        return await asyncio.gather(tenant(7, "x" * 400), tenant(99, "x" * 400))

    assert asyncio.run(main()) == [7, 99]


def test_scoped_serializer_is_context_local():
    record = {"a": 1}
    with tokens.scoped(serializer=lambda v: "zz"):
        assert tokens.serialize(record) == "zz"
    assert tokens.serialize(record) == '{"a": 1}'


def test_trace_no_phantom_drops_when_select_strips_id_field():
    # Regression (G4 BLOCKER): a stage that removes the id field itself must
    # not report its surviving records as dropped.
    records = [{"url": f"u{i}", "title": f"t{i}"} for i in range(3)]
    with trace(id_field="url") as t:
        out = pipeline([stage(select, fields=["title"])])(records)
    assert len(out) == 3
    assert t.audit()["stages"][0]["dropped_ids"] == []


def test_trace_unhashable_id_values_do_not_crash():
    records = [{"k": ["a", 1], "t": "x" * 200}, {"k": ["b", 2], "t": "y" * 200}]
    with trace(id_field="k") as t:
        out = pipeline([stage(trim_to_budget, max_tokens=60)])(records)
    assert len(out) == 1
    assert t.audit()["stages"][0]["dropped_ids"] == [["b", 2]]


def test_fingerprint_distinguishes_named_key_functions():
    # Regression (G4 MAJOR): callable params contribute their __name__.
    def score_a(r):
        return r.get("x", 0)

    def score_b(r):
        return -r.get("x", 0)

    from contexel import rank
    pa = pipeline([stage(rank, by=score_a)])
    pb = pipeline([stage(rank, by=score_b)])
    assert pa.fingerprint != pb.fingerprint


def test_pipeline_fingerprint_is_stable_and_param_sensitive():
    p1 = pipeline([stage(select, fields=["a", "b"]), stage(dedupe, key="a")])
    p2 = pipeline([stage(select, fields=["a", "b"]), stage(dedupe, key="a")])
    p3 = pipeline([stage(select, fields=["a"]), stage(dedupe, key="a")])
    assert p1.fingerprint == p2.fingerprint  # same policy -> same hash
    assert p1.fingerprint != p3.fingerprint  # changed params -> changed hash


def test_trace_audit_records_policy_and_dropped_ids():
    records = [
        {"url": "u1", "t": "keep " * 50},
        {"url": "u1", "t": "dup " * 50},
        {"url": "u2", "t": "keep " * 50},
        {"url": "u3", "t": "cut " * 200},
    ]
    pipe = pipeline([
        stage(dedupe, key="url"),
        stage(trim_to_budget, max_tokens=150),
    ])
    with trace(id_field="url") as t:
        out = pipe(records)

    audit = t.audit()
    assert audit["policies"] == [pipe.fingerprint]
    assert audit["id_field"] == "url"
    by_stage = {s["stage"]: s for s in audit["stages"]}
    assert by_stage["dedupe"]["dropped_ids"] == ["u1"]       # the duplicate
    assert "u3" in by_stage["trim_to_budget"]["dropped_ids"]  # over budget
    kept = {r["url"] for r in out}
    assert all(d not in kept or d == "u1" for d in by_stage["trim_to_budget"]["dropped_ids"])
