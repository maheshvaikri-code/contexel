"""Strict mode (ADR-003, brief AC 8, AC 9): opt-in shape validation that names
the stage and the item index, never changes a successful result, and holds on
a worker thread when the pipeline or shaper turns it on itself."""
import asyncio
import json
import os
import threading

import pytest

import contexel
from contexel import (ContexelError, InputShapeError, allowlist, dedupe, pipeline,
                      quarantine, rank, rescore, select, shaped, stage, strict,
                      trace, trim_to_budget, truncate_field)
from contexel.validate import is_strict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "parity", "vectors.json"), encoding="utf-8") as fh:
    FIXTURE = json.load(fh)["fixture"]

# every stage with arguments that are valid on a list of {"a": ...} records
CALLS = {
    "select": lambda r: select(r, ["a"]),
    "dedupe": lambda r: dedupe(r, key=["a"]),
    "rank": lambda r: rank(r, by="a"),
    "allowlist": lambda r: allowlist(r, "a", ["x"]),
    "quarantine": lambda r: quarantine(r, fields=["a"]),
    "rescore": lambda r: rescore(r, query="x", fields=["a"]),
    "truncate_field": lambda r: truncate_field(r, "a", 5),
    "trim_to_budget": lambda r: trim_to_budget(r, 10),
}
NEEDS_MAPPING = [k for k in CALLS if k != "trim_to_budget"]


def test_strict_off_keeps_todays_lenient_behavior():
    assert not is_strict()
    assert dedupe([1, 1, 2]) == [1, 2]                       # items need not be mappings
    assert rank([3, 1, 2], by=lambda x: x) == [3, 2, 1]
    assert select(({"a": 1, "b": 2},), ["a"]) == [{"a": 1}]  # a tuple of records
    with pytest.raises(TypeError) as info:                   # still a raw error, as before
        select(None, ["a"])
    assert not isinstance(info.value, ContexelError)


@pytest.mark.parametrize("name", list(CALLS))
@pytest.mark.parametrize("bad", [None, "abc", {"a": 1}, 5])
def test_strict_rejects_a_non_list_and_names_the_stage(name, bad):
    with strict():
        with pytest.raises(InputShapeError) as info:
            CALLS[name](bad)
    assert info.value.code == "input.not_list"
    assert info.value.stage == name
    assert name in str(info.value)


@pytest.mark.parametrize("name", NEEDS_MAPPING)
def test_strict_rejects_a_non_mapping_item_and_names_the_index(name):
    records = [{"a": "x"}, {"a": "y"}, 7, {"a": "z"}]
    with strict():
        with pytest.raises(InputShapeError) as info:
            CALLS[name](records)
    assert info.value.code == "input.not_mapping"
    assert info.value.stage == name
    assert "item 2" in str(info.value)


def test_strict_does_not_require_a_mapping_where_the_stage_does_not_index_one():
    with strict():
        assert trim_to_budget([1, 2, 3], 100) == [1, 2, 3]
        assert dedupe([1, 1, 2]) == [1, 2]                    # key=None hashes the item
        assert rank([3, 1, 2], by=lambda x: x) == [3, 2, 1]   # a key function takes anything
        with pytest.raises(InputShapeError):
            dedupe([1, 1, 2], key="a")                         # a key does index the item
        with pytest.raises(InputShapeError):
            rank([3, 1, 2], by="a")


def test_strict_accepts_a_tuple_of_mappings():
    with strict():
        assert select(({"a": 1, "b": 2},), ["a"]) == [{"a": 1}]


def test_the_flag_is_scoped_to_the_block_and_nests():
    assert not is_strict()
    with strict():
        assert is_strict()
        with strict():
            assert is_strict()
        assert is_strict()
    assert not is_strict()
    with pytest.raises(RuntimeError):
        with strict():
            raise RuntimeError("boom")
    assert not is_strict()


def test_one_strict_object_can_be_entered_again_while_active():
    s = strict()
    with s:
        with s:
            assert is_strict()
        assert is_strict()          # the inner exit restores the OUTER value
    assert not is_strict()


def test_one_strict_object_restores_after_an_exception_in_the_inner_block():
    s = strict()
    with s:
        with pytest.raises(RuntimeError):
            with s:
                raise RuntimeError("boom")
        assert is_strict()
    assert not is_strict()


def test_one_strict_object_can_be_reused_sequentially():
    s = strict()
    for _ in range(3):
        with s:
            assert is_strict()
        assert not is_strict()


@pytest.mark.parametrize("name", [
    "select", "dedupe", "allowlist", "quarantine", "rescore", "rank",
    "truncate_field", "trim_to_budget"])
def test_strict_check_runs_before_trace(name):
    calls = {
        "select": lambda: select(None, ["a"]),
        "dedupe": lambda: dedupe(None, key="a"),
        "allowlist": lambda: allowlist(None, "a", ["x"]),
        "quarantine": lambda: quarantine(None),
        "rescore": lambda: rescore(None, "x", fields=["a"]),
        "rank": lambda: rank(None, "a"),
        "truncate_field": lambda: truncate_field(None, "a", 5),
        "trim_to_budget": lambda: trim_to_budget(None, 10),
    }
    with trace(), strict():
        with pytest.raises(InputShapeError) as info:   # not a raw len(None) TypeError
            calls[name]()
    assert info.value.code == "input.not_list"
    assert info.value.stage == name


def test_a_bad_call_under_strict_is_not_misdiagnosed_as_a_shape_error():
    with strict():
        with pytest.raises(TypeError) as info:
            dedupe([None], kee="a")
    assert not isinstance(info.value, ContexelError)
    assert "kee" in str(info.value)


def test_pipeline_strict_holds_on_a_worker_thread():
    pipe = pipeline([stage(select, fields=["a"])], strict=True)
    seen = {}

    def work():
        try:
            pipe(None)
        except BaseException as e:  # noqa: BLE001 - captured for the assertion
            seen["error"] = e

    t = threading.Thread(target=work)
    t.start()
    t.join()
    assert isinstance(seen["error"], InputShapeError)
    assert seen["error"].code == "input.not_list"


def test_a_bare_strict_block_is_not_inherited_by_a_new_thread():
    seen = {}

    def work():
        try:
            select(None, ["a"])
        except BaseException as e:  # noqa: BLE001
            seen["error"] = e

    with strict():
        t = threading.Thread(target=work)
        t.start()
        t.join()
    assert isinstance(seen["error"], TypeError)
    assert not isinstance(seen["error"], ContexelError)   # the documented caveat


def test_pipeline_strict_names_the_stage_that_returned_a_non_list():
    def returns_none(records):
        return None

    pipe = pipeline([stage(select, fields=["a"]), returns_none,
                     stage(select, fields=["a"])], strict=True)
    with pytest.raises(InputShapeError) as info:
        pipe([{"a": 1}])
    assert info.value.code == "input.not_list"
    assert info.value.stage == "returns_none"
    assert "stage 1" in str(info.value)


def test_pipeline_without_strict_lets_the_next_stage_fail_obscurely():
    def returns_none(records):
        return None

    pipe = pipeline([returns_none, stage(select, fields=["a"])])
    with pytest.raises(TypeError) as info:
        pipe([{"a": 1}])
    assert not isinstance(info.value, ContexelError)


def test_shaped_strict_rejects_a_none_return():
    @shaped([stage(select, fields=["a"])], strict=True)
    def tool():
        return None

    with pytest.raises(InputShapeError) as info:
        tool()
    assert (info.value.code, info.value.stage) == ("input.not_list", "shaped")


def test_shaped_strict_with_a_list_of_stages_also_checks_each_stage_output():
    def returns_none(records):
        return None

    tool = shaped([returns_none], strict=True)(lambda: [{"a": 1}])
    with pytest.raises(InputShapeError) as info:
        tool()
    assert info.value.code == "input.not_list"
    assert info.value.stage == "returns_none"


def test_shaped_strict_holds_for_async_tools_and_on_a_worker_thread():
    @shaped([stage(select, fields=["a"])], strict=True)
    async def tool():
        return [{"a": 1}, 5]

    seen = {}

    def work():
        try:
            asyncio.run(tool())
        except BaseException as e:  # noqa: BLE001
            seen["error"] = e

    t = threading.Thread(target=work)
    t.start()
    t.join()
    assert isinstance(seen["error"], InputShapeError)
    assert seen["error"].code == "input.not_mapping"


def test_shaped_with_a_prebuilt_pipeline_runs_it_in_strict_mode():
    pipe = pipeline([stage(select, fields=["a"])])

    @shaped(pipe, strict=True)
    def tool():
        return [{"a": 1}, 5]

    with pytest.raises(InputShapeError) as info:
        tool()
    assert info.value.code == "input.not_mapping"


def test_strict_does_not_change_the_fingerprint():
    stages = [stage(select, fields=["a"]), stage(dedupe, key=["a"])]
    assert pipeline(stages, strict=True).fingerprint == pipeline(stages).fingerprint


def test_strict_never_changes_a_successful_result():
    stages = [
        stage(allowlist, field="source", allowed=["repo", "docs"]),
        stage(quarantine, fields=["snippet"]),
        stage(select, fields=["path", "line", "source", "snippet"]),
        stage(dedupe, key=["path", "line"]),
        stage(rescore, query="exponential backoff jitter", fields=["snippet", "path"]),
        stage(truncate_field, field="snippet", max_tokens=12),
        stage(rank, by="score", desc=True),
        stage(trim_to_budget, max_tokens=150),
    ]
    lenient = pipeline(stages)(FIXTURE)
    assert pipeline(stages, strict=True)(FIXTURE) == lenient
    with strict():
        assert pipeline(stages)(FIXTURE) == lenient
    assert len(lenient) > 0
