"""AC 36: the differential fuzz generator (parity/generate_fuzz.py). Nothing here needs
TypeScript or C#: the replays have their own tests (ts/test/fuzz.test.ts,
csharp/Contexel.Tests/FuzzTests.cs). What is pinned here is what makes the corpus worth
replaying: it is deterministic, it stays inside the documented parity envelope, it covers every
kind of case, and the checks that keep it inside the envelope can fail."""
import hashlib
import json
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "parity"))

import generate_fuzz as gf  # noqa: E402
from parity_cases import ALLOWED_KEYS, assert_in_envelope, outcome  # noqa: E402

SMALL = 400
LARGE = 2000
# random() is the only generator method Python promises to keep stable across versions: these
# draws and this digest of the first 300 cases (their inputs and arguments, not the canon's answers)
# are the same on every Python and operating system. Change them only with the generator.
PINNED_DRAWS = [323, 150, 650, 72, 535, 365]
PINNED_FIRST_300 = "b0094c7ee3bd7ec0b69c1693a7b4e44290cc4440b22b4dd6372966c363c63635"
ERROR_CODES = {"config.contradictory", "config.empty", "config.invalid_pattern",
               "config.invalid_value", "input.field_conflict", "input.not_mapping"}


@pytest.fixture(scope="module")
def small():
    return gf.build(gf.DEFAULT_SEED, SMALL)


@pytest.fixture(scope="module")
def large():
    return gf.build(gf.DEFAULT_SEED, LARGE)


def _run_cli(*args, hashseed="0"):
    env = {**os.environ, "PYTHONHASHSEED": hashseed, "PYTHONPATH": str(ROOT)}
    return subprocess.run([sys.executable, str(ROOT / "parity" / "generate_fuzz.py"), *args],
                          capture_output=True, check=True, env=env, cwd=str(ROOT))


def test_fuzz_corpus_is_deterministic_and_inside_the_envelope(small, tmp_path):
    again = gf.build(gf.DEFAULT_SEED, SMALL)
    assert gf.dumps(small) == gf.dumps(again)
    assert gf.dumps(small).isascii()                      # one byte stream on every platform
    for hashseed in ("0", "1"):                           # the corpus never depends on hash order
        out = tmp_path / f"corpus-{hashseed}.json"
        _run_cli("--cases", str(SMALL), "--out", str(out), hashseed=hashseed)
        assert out.read_bytes() == gf.dumps(small).encode("ascii")
    ids = set()
    for case in small["cases"]:
        assert set(case) <= ALLOWED_KEYS, case["id"]
        assert case["id"] not in ids
        ids.add(case["id"])
        stored = {k: case[k] for k in ("expect", "expect_error") if k in case}
        assert outcome(case, []) == stored, case["id"]    # the canon still gives the same answer
        assert gf.outside_envelope(case, stored) is None, case["id"]
        for part, where in ((case["input"], "input"), (case["args"], "args"), (stored.get("expect"), "expect")):
            assert_in_envelope(part, case["id"] + "." + where)
    assert small["_meta"]["case_count"] == SMALL == len(small["cases"])


def test_the_generator_and_the_first_cases_are_pinned():
    g = gf.Gen(7)
    assert [g.below(1000) for _ in range(6)] == PINNED_DRAWS
    cases = [gf.make_case(gf.DEFAULT_SEED, i) for i in range(300)]
    drawn = [{k: c.get(k) for k in ("id", "stage", "args", "input", "strict")} for c in cases]
    digest = hashlib.sha256(json.dumps(drawn, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
    assert digest.hexdigest() == PINNED_FIRST_300


def test_every_kind_error_code_and_strict_mode_is_covered(large):
    meta = large["_meta"]
    assert set(meta["kind_counts"]) == set(gf.KINDS)
    assert min(meta["kind_counts"].values()) >= 20, meta["kind_counts"]
    assert set(meta["error_codes"]) == ERROR_CODES
    assert min(meta["error_codes"].values()) >= 1, meta["error_codes"]
    assert meta["strict_cases"] >= 100
    wide = [c for c in large["cases"] if any(ord(ch) > 0xFFFF for ch in json.dumps(c["input"], ensure_ascii=False))]
    assert len(wide) >= 100                               # astral text really is generated (in `note`)
    assert sum(1 for c in large["cases"] if c["stage"] == "rescore" and c["args"].get("match") == "stem") >= 10


def _walk(value, key=None):
    """Every string in the value, with the record key it sits under (None at the top level)."""
    if isinstance(value, str):
        yield key, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _walk(v, k)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v, key)


def _stage_specs(case):
    if case["stage"] in gf.RECORD_KINDS:
        yield case
    for spec in case["args"].get("stages", []):
        yield spec


def test_the_domain_rules_hold_in_every_case(large):
    excluded = set(gf.EXCLUDED)
    for case in large["cases"]:
        for key, text in list(_walk(case["input"])) + list(_walk(case["args"])):
            assert not excluded & set(text), (case["id"], "a case-special character")
            for ch in text:
                if ord(ch) > 0xFFFF and unicodedata.category(ch).startswith("L"):
                    assert key == "note", (case["id"], "an astral letter outside `note`", key)
            assert not any(0xD800 <= ord(ch) <= 0xDFFF for ch in text), "a lone surrogate"
        for spec in _stage_specs(case):
            if spec["stage"] == "rescore":
                assert "note" not in spec["args"].get("fields", []), case["id"]
        items = case["input"] if case["stage"] in gf.RECORD_KINDS + ["pipeline", "shaped", "join",
                                                                    "trace_report", "trace_dropped_ids"] else []
        if any(not isinstance(i, dict) for i in items):
            assert case.get("expect_error", {}).get("code") == "input.not_mapping", case["id"]


def test_a_case_depends_on_its_seed_and_index_alone(large):
    for index in (0, 17, 1999):
        assert gf.make_case(gf.DEFAULT_SEED, index) == large["cases"][index]
    shown = json.loads(_run_cli("--seed", str(gf.DEFAULT_SEED), "--show", "17").stdout.decode("ascii"))
    assert shown == large["cases"][17]
    assert gf.make_case(gf.DEFAULT_SEED + 1, 17) != large["cases"][17]


def test_the_envelope_check_can_fail():
    def verdict(case):
        return gf.outside_envelope(case, outcome(case, []))

    base = {"id": "x", "stage": "select", "args": {"fields": ["a"]}, "input": [{"a": 1}]}
    assert verdict(base) is None
    assert "integer-valued float" in verdict({**base, "input": [{"a": 1.0}]})
    assert "NaN" in verdict({**base, "input": [{"a": float("nan")}]})
    assert "integer beyond 2**53" in verdict({**base, "input": [{"a": 2 ** 53 + 1}]})
    # an empty query scores every record 0.0. A final stage that drops the score hides it from the
    # expectation; the intermediate check still sees it
    assert verdict({"id": "z", "stage": "rescore", "args": {"query": ""}, "input": [{"snippet": "a"}]}
                   ).startswith("expect: integer-valued float")
    pipe = {"id": "y", "stage": "pipeline", "input": [{"snippet": "zzz"}],
            "args": {"stages": [{"stage": "rescore", "args": {"query": "", "fields": ["snippet"]}},
                                {"stage": "select", "args": {"fields": ["snippet"]}}]}}
    assert outcome(pipe, [])["expect"] == [{"snippet": "zzz"}]
    assert verdict(pipe).startswith("intermediate: integer-valued float")


def test_a_redraw_is_counted_and_a_hopeless_case_is_an_error(monkeypatch):
    real = gf.draw_case
    calls = {"n": 0}

    def flaky(seed, index, attempt):
        calls["n"] += 1
        if attempt < 2:
            return {"id": "x", "stage": "select", "args": {"fields": ["a"]}, "input": [{"a": 1.0}]}
        return real(seed, index, attempt)

    monkeypatch.setattr(gf, "draw_case", flaky)
    redrawn = {}
    gf.make_case(gf.DEFAULT_SEED, 3, redrawn)
    assert redrawn == {"input: integer-valued float 1.0": 2}
    monkeypatch.setattr(gf, "draw_case", lambda seed, index, attempt: {
        "id": "x", "stage": "select", "args": {"fields": ["a"]}, "input": [{"a": 1.0}]})
    with pytest.raises(AssertionError, match="no case inside the envelope"):
        gf.make_case(gf.DEFAULT_SEED, 3)


def test_the_redraws_of_the_corpus_are_few_and_explained(large):
    redrawn = large["_meta"]["redrawn"]
    assert sum(redrawn.values()) < LARGE // 20, redrawn   # under 5% of the cases
    assert all(reason.startswith(("expect:", "intermediate:", "input:", "args:", "canon raised"))
               for reason in redrawn), redrawn
