import json

from .agent import Agent, run_code
from .context import ContextWindow, Observation
from .demo import SCRIPT, TASK
from .model import ScriptedClient
from .tools import search_code


def _serialize(ctx) -> str:
    return json.dumps([o.records for o in ctx.observations], sort_keys=True, default=str)


def test_demo_runs_and_answers():
    result = Agent(ScriptedClient(SCRIPT)).run(TASK)
    assert "retry_backoff" in result.answer
    assert result.context.observations
    assert result.context.used <= result.context.budget


def test_context_is_identical_across_runs():
    # The headline guarantee: deterministic stages + deterministic tools mean the
    # context that gets built is byte-identical run to run.
    a = Agent(ScriptedClient(SCRIPT)).run(TASK)
    b = Agent(ScriptedClient(SCRIPT)).run(TASK)
    assert _serialize(a.context) == _serialize(b.context)


def test_contract_neutralizes_nondeterministic_noise():
    raw_a = search_code.__wrapped__("backoff")  # the unshaped tool
    raw_b = search_code.__wrapped__("backoff")
    # raw output carries nondeterministic noise...
    assert [r["request_id"] for r in raw_a] != [r["request_id"] for r in raw_b]
    # ...but the shaped output that actually reaches context is identical.
    assert search_code("backoff") == search_code("backoff")


def test_shaped_tools_drop_noise_fields():
    hits = search_code("backoff")
    assert hits, "expected at least one hit"
    for h in hits:
        assert "request_id" not in h
        assert "blob_sha" not in h
        assert "commit" not in h


def test_run_code_returns_result_using_stages():
    out = run_code(
        "result = [{'a': 1}, {'a': 1}, {'a': 2}]\n"
        "result = dedupe(result, key='a')\n"
    )
    assert out == [{"a": 1}, {"a": 2}]


def test_window_evicts_when_over_budget():
    ctx = ContextWindow(budget=5)  # tiny budget forces eviction
    ctx.add(Observation(0, "code", [{"x": "a" * 200}]))
    ctx.add(Observation(1, "code", [{"x": "b" * 200}]))
    assert ctx.evicted == [0]
    assert len(ctx.observations) == 1
