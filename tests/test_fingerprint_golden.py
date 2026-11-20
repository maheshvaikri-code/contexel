"""Golden policy fingerprints, recorded from the 0.1.17 canon (2026-11-19).

These pin the compatibility promise of ADR-008 / AC 29: a pipeline that binds
none of {sets, nested pipelines, a tiktoken tokenizer} keeps its EXACT current
fingerprint after the audit-truthfulness change. Do not regenerate these values
to make a test pass: a change here is a behavior change that needs an ADR.
"""
import os
import sys

import pytest

from contexel import (allowlist, dedupe, pipeline, quarantine, rank, rescore,
                      select, stage, trim_to_budget, truncate_field)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "parity"))
import generate_vectors  # noqa: E402  (the standard contract lives there)


def key(r):  # a NAMED callable: callables fingerprint by __name__
    return r["a"]


SHAPES = {
    "contract": (lambda: generate_vectors.contract(), "0a312755f913d64b"),
    "primitives": (lambda: pipeline([
        stage(select, fields=["a", "b"]), stage(dedupe, key="a"),
        stage(rank, by="score", desc=True), stage(trim_to_budget, max_tokens=100)]),
        "24b66acf41ad058f"),
    "nested_dict_and_none": (lambda: pipeline([
        stage(allowlist, field="s", allowed=["x", None, 1, 2.5, True]),
        stage(quarantine, fields=("snippet",), patterns=None, action="drop")]),
        "3e55e84d283957fb"),
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
