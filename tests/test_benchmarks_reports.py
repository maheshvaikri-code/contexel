"""The benchmark reports are rendered from a dictionary and from nothing else, so the
published numbers can be checked against that dictionary (AC 26). Nothing here runs a
benchmark: the dictionaries are small fixtures."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks import suites_report, tables  # noqa: E402


def _suites():
    return {
        "schema": 1,
        "generated": "2026-01-02",
        "environment": {"python": "3.12.0", "platform": "Linux (x86_64)", "contexel": "0.1.17"},
        "determinism": {"same_process": True, "raw_noise_differs": True, "noise_neutralized": True,
                        "cross_process": True, "hash_prefix": "0123456789abcdef"},
        "budget": {
            "trim": [{"budget": 500, "shaped_with": "heuristic", "records_kept": 10,
                      "heuristic_tokens": 479, "actual_tokens": 500},
                     {"budget": 500, "shaped_with": "tiktoken", "records_kept": 8,
                      "heuristic_tokens": 514, "actual_tokens": 472}],
            "truncate": [{"shaped_with": "heuristic", "cap": 24, "worst_field_tokens": 24},
                         {"shaped_with": "tiktoken", "cap": 24, "worst_field_tokens": 24}],
        },
        "speed": {"stages": [{"n": 1000, "stage": "select", "ms": 0.5, "records_per_sec": 2000000.0}],
                  "trace": {"off_ms": 10.0, "on_ms": 30.0, "ratio": 3.0}},
        "accuracy": [{"sample": "json (x)", "actual": 100, "heuristic": 70, "error_pct": -30.0}],
        "reduction": [{"dup_rate": 0.0, "budget": 1000, "records": "10 -> 5", "tokens": "100 -> 50",
                       "lossless_pct": 10.0, "by_choice_pct": 40.0, "total_pct": 50.0}],
        "encoding": [{"encoding": "json", "budget": 500, "records_kept": 8, "actual_tokens": 400,
                      "tokens_per_record": 50.0}],
    }


def test_the_table_helper_formats_numbers_and_text():
    out = tables.table([{"a": 1234, "b": 1.5, "c": "x"}], [("a", "A"), ("b", "B"), ("c", "C")])
    assert out.splitlines() == ["| A | B | C |", "|---|---|---|", "| 1,234 | 1.50 | x |"]


def test_the_suites_report_is_rendered_from_its_dictionary_alone():
    results = _suites()
    text = suites_report.render(results)
    assert text == suites_report.render(json.loads(json.dumps(results)))  # nothing else is read
    assert "Generated 2026-01-02" in text and "`0123456789abcdef`" in text
    assert "| same process, same input -> identical output | PASS |" in text
    assert "10.0 ms inactive vs 30.0 ms active (3.00x)" in text
    assert "| json (x) | 100 | 70 | -30.00 |" in text
    assert "benchmarks/RESULTS.json" in text and "tools/check_benchmark_numbers.py" in text


def test_a_failed_determinism_check_is_rendered_as_fail():
    results = copy.deepcopy(_suites())
    results["determinism"]["cross_process"] = False
    rows = suites_report.determinism_rows(results["determinism"])
    assert [r["result"] for r in rows] == ["PASS", "PASS", "PASS", "FAIL"]
    assert "| 3 fresh interpreters (PYTHONHASHSEED 0/1/2) -> same hash | FAIL |" in suites_report.render(results)
