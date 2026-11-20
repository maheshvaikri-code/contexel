"""Data-driven parity cases (ADR-007).

One table. The Python canon computes every expectation; the TypeScript and C#
suites replay the same JSON through one adapter per stage. Adding a case means
editing ONLY this file, then regenerating vectors.

Case shape (all JSON):
    {"id": "<stage>/<what>", "stage": <kind>, "args": {...}, "input": <records
     | "$fixture" | list-of-sources for merge>, "expect": <canon output>}

Kinds: the eight record stages, ``merge`` (input = list of sources),
``pipeline`` / ``shaped`` (args.stages = [{"stage", "args"}, ...]), and
``trace_report`` (args.stages + optional args.id_field; expect = report text).
Callable-valued arguments cannot be JSON: those stay hand-written edge vectors.
"""
from __future__ import annotations

from typing import Any, Dict, List

from contexel import (allowlist, dedupe, merge, pipeline, quarantine, rank,
                      rescore, select, shaped, stage, trace, trim_to_budget,
                      truncate_field)

RECORD_STAGES = {
    "select": select, "dedupe": dedupe, "allowlist": allowlist,
    "quarantine": quarantine, "rescore": rescore, "rank": rank,
    "truncate_field": truncate_field, "trim_to_budget": trim_to_budget,
}
ALLOWED_KEYS = {"id", "stage", "args", "input", "expect"}

# Arguments that make each record stage valid on an empty list (AC 20/22: the
# empty-input class had no cross-language coverage).
_EMPTY_ARGS: Dict[str, Dict[str, Any]] = {
    "select": {"fields": ["a"]},
    "dedupe": {"key": ["a"]},
    "allowlist": {"field": "a", "allowed": ["x"]},
    "quarantine": {"fields": ["a"]},
    "rescore": {"query": "x", "fields": ["a"]},
    "rank": {"by": "a"},
    "truncate_field": {"field": "a", "max_tokens": 3},
    "trim_to_budget": {"max_tokens": 10},
}


def _pipe(specs: List[dict]):
    return pipeline([stage(RECORD_STAGES[s["stage"]], **s["args"]) for s in specs])


def run_case(case: dict, fixture: List[dict]) -> Any:
    records = fixture if case["input"] == "$fixture" else case["input"]
    kind, args = case["stage"], case["args"]
    if kind in RECORD_STAGES:
        return RECORD_STAGES[kind](records, **args)
    if kind == "merge":
        return merge(*records, **args)
    if kind == "pipeline":
        return _pipe(args["stages"])(records)
    if kind == "shaped":
        return shaped(_pipe(args["stages"]))(lambda: records)()
    if kind == "trace_report":
        with trace(id_field=args.get("id_field")) as t:
            _pipe(args["stages"])(records)
        return t.report()
    raise ValueError(f"unknown case kind {kind!r}")


def _raw_cases() -> List[dict]:
    cases: List[dict] = []

    def add(cid: str, kind: str, args: dict, inp: Any) -> None:
        cases.append({"id": cid, "stage": kind, "args": args, "input": inp})

    for kind, args in _EMPTY_ARGS.items():
        add(f"{kind}/empty_input", kind, args, [])
    add("merge/empty_sources", "merge", {}, [])
    add("pipeline/empty_input", "pipeline",
        {"stages": [{"stage": "select", "args": {"fields": ["a"]}},
                    {"stage": "trim_to_budget", "args": {"max_tokens": 10}}]}, [])

    add("merge/concat_without_schema", "merge", {},
        [[{"a": 1}, {"a": 2}], [{"a": 3}]])
    add("merge/schema_first_present_wins_and_dedupes", "merge",
        {"schema": {"title": ["title", "name", "headline"],
                    "url": ["url", "link", "href"]}, "dedupe_key": "url"},
        [[{"title": "A", "url": "u1", "junk": 1}, {"name": "B", "link": "u2"}],
         [{"headline": "C", "href": "u1"}, {"title": "D", "url": "u3"}]])
    add("merge/schema_unmatched_record_becomes_empty", "merge",
        {"schema": {"title": ["title"]}}, [[{"other": 1}, {"title": "T"}]])

    add("rank/missing_field_goes_last_desc", "rank", {"by": "a"},
        [{"a": 2}, {"b": 1}, {"a": 3}, {"a": 2, "t": "second"}])
    add("rank/missing_field_goes_last_asc", "rank", {"by": "a", "desc": False},
        [{"a": 2}, {"b": 1}, {"a": 3}, {"a": 2, "t": "second"}])
    add("dedupe/nfc_and_nfd_stay_distinct", "dedupe", {"key": "k"},
        [{"k": "café"}, {"k": "café"}, {"k": "café"}])
    add("truncate_field/counts_code_points_not_bytes", "truncate_field",
        {"field": "s", "max_tokens": 4},
        [{"s": "日本語" * 10}, {"s": "emoji\U0001F600" * 6}])
    add("select/missing_and_nested_fields", "select", {"fields": ["a", "n", "zz"]},
        [{"a": 1, "n": {"x": [1, 2]}, "drop": True}, {"zz": None}])

    add("shaped/select_then_dedupe_on_fixture", "shaped",
        {"stages": [{"stage": "select", "args": {"fields": ["path", "line"]}},
                    {"stage": "dedupe", "args": {"key": ["path", "line"]}}]},
        "$fixture")
    add("pipeline/allowlist_then_trim_on_fixture", "pipeline",
        {"stages": [{"stage": "allowlist",
                     "args": {"field": "source", "allowed": ["repo"]}},
                    {"stage": "trim_to_budget", "args": {"max_tokens": 60}}]},
        "$fixture")
    add("trace_report/contract_on_fixture", "trace_report",
        {"id_field": "path",
         "stages": [
             {"stage": "allowlist", "args": {"field": "source", "allowed": ["repo", "docs"]}},
             {"stage": "quarantine", "args": {"fields": ["snippet"]}},
             {"stage": "select", "args": {"fields": ["path", "line", "source", "snippet"]}},
             {"stage": "dedupe", "args": {"key": ["path", "line"]}},
             {"stage": "rescore", "args": {"query": "exponential backoff jitter",
                                           "fields": ["snippet", "path"]}},
             {"stage": "truncate_field", "args": {"field": "snippet", "max_tokens": 12}},
             {"stage": "rank", "args": {"by": "score", "desc": True}},
             {"stage": "trim_to_budget", "args": {"max_tokens": 150}}]},
        "$fixture")
    add("trace_report/empty_pipeline_input", "trace_report",
        {"stages": [{"stage": "select", "args": {"fields": ["a"]}}]}, [])
    return cases


MAX_SAFE_INT = 2 ** 53


def assert_in_envelope(value: Any, where: str) -> None:
    """The documented parity envelope (ADR-001 4a, ADR-002 3): JSON data only,
    no NaN/Inf, no integer-valued floats (TypeScript cannot tell 1.0 from 1),
    integers within +-2**53."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, float):
        assert value == value and value not in (float("inf"), float("-inf")), f"{where}: NaN/Inf"
        assert not value.is_integer(), f"{where}: integer-valued float {value!r}"
        return
    if isinstance(value, int):
        assert abs(value) <= MAX_SAFE_INT, f"{where}: integer beyond 2**53"
        return
    if isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            assert_in_envelope(v, f"{where}[{i}]")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            assert isinstance(k, str), f"{where}: non-string key {k!r}"
            assert_in_envelope(v, f"{where}.{k}")
        return
    raise AssertionError(f"{where}: {type(value).__name__} is not JSON data")


def build_cases(fixture: List[dict]) -> List[dict]:
    ids = set()
    out = []
    for case in _raw_cases():
        assert case["id"] not in ids, f"duplicate case id {case['id']}"
        ids.add(case["id"])
        assert set(case) <= ALLOWED_KEYS, case
        expect = run_case(case, fixture)
        assert_in_envelope(case["input"] if case["input"] != "$fixture" else fixture, case["id"] + ".input")
        assert_in_envelope(case["args"], case["id"] + ".args")
        assert_in_envelope(expect, case["id"] + ".expect")
        out.append({**case, "expect": expect})
    return out
