"""Golden policy fingerprints, recorded from the 0.1.17 canon (2026-11-19).

These pin the compatibility promise of ADR-008 / AC 29: a pipeline that binds
none of {sets, nested pipelines, a tiktoken tokenizer} keeps its EXACT current
fingerprint after the audit-truthfulness change. Do not regenerate these values
to make a test pass: a change here is a behavior change that needs an ADR.

Every shape is written out inline (no shape depends on another module), and
together they bind every branch of ``_stable_repr``: primitives, lists and
tuples, dicts (mixed-type keys, nested values), named callables, and the
type-name fallback for an opaque object.
"""
import pytest

from contexel import (allowlist, dedupe, pipeline, quarantine, rank, rescore,
                      select, stage, trim_to_budget, truncate_field)


def key(r):  # a NAMED callable: callables fingerprint by __name__
    return r["a"]


def annotate(records, **_options):  # a NAMED custom stage
    return records


class Opaque:  # an opaque object: fingerprints by its type name only
    pass


SHAPES = {
    # today's parity contract, copied inline so the golden never moves with it
    "contract": (lambda: pipeline([
        stage(allowlist, field="source", allowed=["repo", "docs"]),
        stage(quarantine, fields=("snippet",)),
        stage(select, fields=["path", "line", "source", "snippet"]),
        stage(dedupe, key=["path", "line"]),
        stage(rescore, query="exponential backoff jitter", fields=("snippet", "path")),
        stage(truncate_field, field="snippet", max_tokens=12),
        stage(rank, by="score", desc=True),
        stage(trim_to_budget, max_tokens=150)]), "0a312755f913d64b"),
    "primitives": (lambda: pipeline([
        stage(select, fields=["a", "b"]), stage(dedupe, key="a"),
        stage(rank, by="score", desc=True), stage(trim_to_budget, max_tokens=100)]),
        "24b66acf41ad058f"),
    "list_of_mixed_scalars_and_none": (lambda: pipeline([
        stage(allowlist, field="s", allowed=["x", None, 1, 2.5, True]),
        stage(quarantine, fields=("snippet",), patterns=None, action="drop")]),
        "3e55e84d283957fb"),
    "dict_with_mixed_keys_and_nesting": (lambda: pipeline([
        stage(annotate, mapping={"b": [1, None, {"z": 2.5}], 1: "one",
                                 2.5: {"k": None}, None: [], (1, "t"): False},
              empty={}, label="m")]),
        "5d865072cb72afe5"),
    "opaque_object": (lambda: pipeline([stage(annotate, marker=Opaque(), n=3)]),
                      "79dab73b8b021852"),
    "named_callable": (lambda: pipeline([stage(rank, by=key, desc=False)]),
                       "c0528eaa77a2360e"),
    "bare_named_function": (lambda: pipeline([key]), "0841f22ac0700431"),
    "rescore_defaults": (lambda: pipeline([
        stage(rescore, query="a b", fields=("x", "y"))]), "11b53020d9d935bb"),
    "empty_pipeline": (lambda: pipeline([]), "2e38e77b22c314a4"),
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_fingerprint_matches_the_recorded_baseline(name):
    build, expected = SHAPES[name]
    assert build().fingerprint == expected


def test_keyword_order_does_not_change_the_fingerprint():
    a = pipeline([stage(truncate_field, field="s", max_tokens=5, suffix="..")])
    b = pipeline([stage(truncate_field, suffix="..", max_tokens=5, field="s")])
    assert a.fingerprint == b.fingerprint == "4576e85b3ab2efb1"


def test_stage_order_changes_the_fingerprint():
    s1, s2 = stage(select, fields=["a"]), stage(dedupe, key="a")
    assert pipeline([s1, s2]).fingerprint != pipeline([s2, s1]).fingerprint


def test_a_bound_parameter_changes_the_fingerprint():
    one = pipeline([stage(trim_to_budget, max_tokens=100)])
    two = pipeline([stage(trim_to_budget, max_tokens=101)])
    assert one.fingerprint != two.fingerprint
