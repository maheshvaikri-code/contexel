"""Audit truthfulness (ADR-008, brief AC 28-31): the trail must not under-report.

Each test here pins one way the audit used to say something false.
"""
import os
import subprocess
import sys
import types

import pytest

from contexel import (allowlist, dedupe, pipeline, select, stage, tokens,
                      trace, trim_to_budget, truncate_field)
from contexel.trace import traced

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def test_a_dropped_idless_record_never_absorbs_an_identified_drop():
    # The stage drops an id-less record as well as "a" and "b". It ends with
    # FEWER id-less records than it was given, which explains no lost id: the
    # budget is 0, not negative, so both ids are reported.
    records = [{"t": "x"}, {"id": "a", "t": "x"}, {"id": "b", "t": "x"},
               {"id": "c", "t": "y"}]
    out, dropped = _drops(
        records, lambda r: allowlist(r, field="t", allowed=["y"]))
    assert out == [{"id": "c", "t": "y"}]
    assert dropped == ["a", "b"]


def test_ids_1_and_the_string_1_are_different_ids():
    # The survivor's id is the integer 1; the dropped record's is the string
    # "1". Keying both alike would let the survivor stand for the drop.
    records = [{"id": "1", "k": "drop"}, {"id": 1, "k": "keep"}]
    out, dropped = _drops(
        records, lambda r: allowlist(r, field="k", allowed=["keep"]))
    assert out == [{"id": 1, "k": "keep"}]
    assert dropped == ["1"]
    assert type(dropped[0]) is str


# --- AC 29: what the fingerprint covers -----------------------------------

def _fp(*stages):
    return pipeline(list(stages)).fingerprint


def test_fingerprint_differs_for_set_contents():
    a = _fp(stage(allowlist, field="s", allowed={"a"}))
    b = _fp(stage(allowlist, field="s", allowed={"b"}))
    assert a != b


def test_fingerprint_of_a_set_ignores_insertion_order_and_set_type():
    ab = _fp(stage(allowlist, field="s", allowed={"a", "b"}))
    ba = _fp(stage(allowlist, field="s", allowed={"b", "a"}))
    frozen = _fp(stage(allowlist, field="s", allowed=frozenset({"a", "b"})))
    assert ab == ba == frozen


def test_fingerprint_of_a_set_is_not_that_of_a_list_or_a_dict():
    as_set = _fp(stage(allowlist, field="s", allowed={"a"}))
    as_list = _fp(stage(allowlist, field="s", allowed=["a"]))
    as_dict = _fp(stage(allowlist, field="s", allowed={"a": 1}))
    assert len({as_set, as_list, as_dict}) == 3


def test_fingerprint_of_a_set_is_the_same_under_every_hash_seed():
    code = """
import sys
sys.path.insert(0, %r)
from contexel import allowlist, pipeline, stage
names = {'alpha', 2, None, (1, 2), 2.5, frozenset({'x', 'y'}), 'k1', 'k2'}
print(pipeline([stage(allowlist, field='s', allowed=names)]).fingerprint)
""" % ROOT
    seen = set()
    for seed in ("0", "1", "2", "4242"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, "-c", code], env=env,
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        seen.add(proc.stdout.strip())
    assert len(seen) == 1, seen


def test_a_set_nested_in_a_list_or_dict_is_covered_too():
    assert (_fp(stage(allowlist, field="s", allowed=[1, {"a", "b"}]))
            != _fp(stage(allowlist, field="s", allowed=[1, {"a", "c"}])))
    assert (_fp(stage(allowlist, field="s", allowed={"k": {"a"}}))
            != _fp(stage(allowlist, field="s", allowed={"k": {"b"}})))
    assert (_fp(stage(allowlist, field="s", allowed=[{"b", "a"}]))
            == _fp(stage(allowlist, field="s", allowed=[{"a", "b"}])))


def test_fingerprint_differs_for_nested_pipelines():
    inner_a = pipeline([stage(select, fields=["a"])])
    inner_b = pipeline([stage(select, fields=["b"])])
    outer_a = pipeline([inner_a, stage(dedupe, key="a")])
    outer_b = pipeline([inner_b, stage(dedupe, key="a")])
    same_as_a = pipeline([pipeline([stage(select, fields=["a"])]),
                          stage(dedupe, key="a")])
    assert outer_a.fingerprint != outer_b.fingerprint
    assert outer_a.fingerprint == same_as_a.fingerprint


def test_a_nested_pipeline_still_runs_its_stages():
    inner = pipeline([stage(select, fields=["a"])])
    out = pipeline([inner, stage(dedupe, key="a")])([{"a": 1, "b": 2}, {"a": 1}])
    assert out == [{"a": 1}]


class _FakeEncoding:
    """One 'token' per character; remembers how it was called."""

    def __init__(self):
        self.kwargs = []

    def encode(self, text, **kwargs):
        self.kwargs.append(kwargs)
        return list(text)


@pytest.fixture
def fake_tiktoken(monkeypatch):
    enc = _FakeEncoding()
    module = types.ModuleType("tiktoken")
    module.get_encoding = lambda name: enc
    module.encoding_for_model = lambda model: enc
    monkeypatch.setitem(sys.modules, "tiktoken", module)
    return enc


def test_fingerprint_differs_for_tiktoken_encodings(fake_tiktoken):
    def fp(tok):
        return _fp(stage(truncate_field, field="s", max_tokens=5, tokenizer=tok))

    cl = tokens.tiktoken_tokenizer("cl100k_base")
    o2 = tokens.tiktoken_tokenizer("o200k_base")
    again = tokens.tiktoken_tokenizer("cl100k_base")
    assert cl.__name__ == "tiktoken:cl100k_base"
    assert tokens.tiktoken_tokenizer(model="gpt-4o").__name__ == "tiktoken:gpt-4o"
    assert fp(cl) != fp(o2)
    assert fp(cl) == fp(again)


# --- AC 30: a policy cannot change behavior without changing its fingerprint -

def test_bound_container_mutation_cannot_change_behavior():
    allowed = ["a"]
    pipe = pipeline([stage(allowlist, field="s", allowed=allowed)])
    before = pipe.fingerprint
    allowed.append("b")  # the caller changes THEIR list afterwards
    out = pipe([{"s": "a"}, {"s": "b"}])
    assert [r["s"] for r in out] == ["a"]
    assert pipe.fingerprint == before


def _probe(records, config):
    """A custom stage that reports exactly what it was bound to."""
    return [{"config": repr(config)}]


def test_nested_bound_containers_are_copied_at_every_depth():
    names = ["a"]
    inner = ["z"]
    config = {"names": names, "pair": (1, inner), "tags": {"t"}, "n": {"deep": [names]}}
    probe = stage(_probe, config=config)
    pipe = pipeline([probe])
    expected, before = probe([]), pipe.fingerprint
    names.append("b")
    inner.append("y")
    config["tags"].add("u")
    config["n"]["deep"].append("v")
    config["extra"] = 1
    assert probe([]) == expected
    assert pipe.fingerprint == before


def test_pipeline_copies_its_list_of_stages():
    keep_a = stage(select, fields=["a"])
    stages = [keep_a]
    pipe = pipeline(stages)
    before = pipe.fingerprint
    stages.append(stage(select, fields=["b"]))
    stages[0] = stage(select, fields=["b"])
    assert pipe([{"a": 1, "b": 2}]) == [{"a": 1}]
    assert pipe.fingerprint == before


def test_a_callable_a_custom_object_and_a_list_subclass_are_not_copied():
    # documented limit: only plain containers are copied; anything else stays
    # live (a list subclass is hashed by its contents at build time but not
    # copied; a callable or custom object is hashed by its name or type name)
    class Box:
        pass

    class Tags(list):
        pass

    def by(r):
        return r["a"]

    box, tags = Box(), Tags(["x"])
    seen = {}

    def grab(records, **objects):
        seen.update(objects)
        return records

    stage(grab, key=by, box=box, tags=tags)([])
    assert seen["key"] is by
    assert seen["box"] is box
    assert seen["tags"] is tags


def test_a_bound_frozenset_is_passed_as_the_same_object():
    # a frozenset is immutable, so there is nothing to copy: the stage gets
    # the caller's object itself, still a frozenset
    allowed = frozenset({"a", "b"})
    seen = {}

    def grab(records, **objects):
        seen.update(objects)
        return records

    stage(grab, allowed=allowed)([])
    assert seen["allowed"] is allowed


def test_a_stage_gets_the_same_private_copy_on_every_call():
    sizes = []

    def measure(records, names):
        sizes.append(len(names))
        return records

    names = ["a"]
    bound = stage(measure, names=names)
    bound([])
    names.append("b")
    bound([])
    assert sizes == [1, 1]


# --- AC 31: tiktoken and special-token literals ----------------------------

def test_tiktoken_tokenizer_asks_for_special_tokens_to_be_ordinary_text(fake_tiktoken):
    tok = tokens.tiktoken_tokenizer()
    assert tok("<|endoftext|>") == len("<|endoftext|>")
    assert fake_tiktoken.kwargs == [{"disallowed_special": ()}]


def test_tiktoken_counts_special_token_literals():
    tiktoken = pytest.importorskip("tiktoken")
    try:
        tiktoken.get_encoding("cl100k_base")
    except Exception as exc:  # the encoding file is fetched on first use
        pytest.skip(f"cl100k_base is not available here: {exc!r}")
    tok = tokens.tiktoken_tokenizer()
    assert tok("a <|endoftext|> b") > 3
    cut = truncate_field([{"s": "<|endoftext|>" * 8}], "s", 4, tokenizer=tok)
    assert isinstance(cut[0]["s"], str) and cut[0]["s"]
    kept = trim_to_budget([{"s": "<|endoftext|>"}] * 3, max_tokens=500, tokenizer=tok)
    assert len(kept) == 3
