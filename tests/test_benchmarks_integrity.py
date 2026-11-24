"""AC 26: every published benchmark number equals the generated results, and a
number that does not is reported. The tests that exercise a competitor library skip
when it is not installed."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks import competitors, publish, suites_report  # noqa: E402

PUBLISHED = (
    "README.md", "README_PYPI.md", "site/index.html", "site/benchmarks.html",
    "benchmarks/COMPARISON.json", "benchmarks/COMPARISON.md",
    "benchmarks/RESULTS.json", "benchmarks/RESULTS.md", "benchmarks/dataset.sha256",
)


def test_the_competitor_libraries_count_as_the_published_table_says():
    pytest.importorskip("toolz")
    pytest.importorskip("langchain_core")
    pytest.importorskip("llama_index.core")
    rows = {o["impl"]: o for o in competitors.operations()}
    assert rows["toolz"]["native"] == ["select", "dedupe"]
    assert rows["langchain-core"]["native"] == ["trim"]
    assert rows["llama-index-core"]["native"] == [] and len(rows["llama-index-core"]["other_native"]) == 2
    committed = {o["impl"]: o for o in json.loads(
        (ROOT / "benchmarks" / "COMPARISON.json").read_text(encoding="utf-8"))["operations"]}
    assert rows == committed  # the committed results are what the code computes today


def test_published_numbers_match_generated_results():
    assert publish.check(ROOT) == []


@pytest.fixture
def tree(tmp_path):
    for rel in PUBLISHED:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    return tmp_path


def _replace(root, rel, old, new, count=1):
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) >= 1, (rel, old)
    path.write_text(text.replace(old, new, count), encoding="utf-8", newline="\n")


def test_the_copy_of_the_tree_used_below_is_clean(tree):
    assert publish.check(tree) == []


def test_the_check_is_the_same_on_a_checkout_with_crlf_line_endings(tree):
    for rel in PUBLISHED:  # what a Windows checkout with autocrlf writes
        path = tree / rel
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert publish.check(tree) == []
    assert publish.write(tree) == []  # and --write has nothing to change


def test_a_changed_number_in_a_generated_table_is_reported(tree):
    comparison = json.loads((tree / "benchmarks" / "COMPARISON.json").read_text(encoding="utf-8"))
    ms = publish._n0(comparison["task"][0]["ms"])
    _replace(tree, "README.md", f"| {ms} |", f"| {int(ms.replace(',', '')) + 1} |")
    problems = publish.check(tree)
    assert any("README.md" in p and "benchmark:glance" in p for p in problems), problems


def test_a_changed_number_on_the_site_is_reported(tree):
    _replace(tree, "site/benchmarks.html", "4/4 checks PASS", "3/4 checks PASS")
    assert any("suite1" in p for p in publish.check(tree))


def test_a_registered_claim_with_a_wrong_number_is_reported(tree):
    _replace(tree, "README_PYPI.md", "28,047 search-tool records", "28,048 search-tool records")
    problems = publish.check(tree)
    assert any("README_PYPI.md" in p and "tool-output records" in p for p in problems), problems


def test_a_hand_typed_benchmark_number_is_reported_as_unregistered(tree):
    _replace(tree, "README.md", "Both are noise next to a", "Both are noise (12 ms) next to a")
    problems = publish.check(tree)
    assert any("unregistered benchmark number" in p and "12 ms" in p for p in problems), problems
    _replace(tree, "README.md", "(12 ms)", "(about 40% faster)")
    assert any("unregistered" in p and "40%" in p for p in publish.check(tree))


def test_a_reworded_registered_claim_is_reported_not_skipped(tree):
    _replace(tree, "site/index.html", "slowest\nbudget-compliant row", "slowest compliant row")
    assert any("slowest budget-compliant row" in p and "not found" in p for p in publish.check(tree))


def test_a_false_qualitative_claim_is_reported(tree):
    results = tree / "benchmarks" / "COMPARISON.json"
    data = json.loads(results.read_text(encoding="utf-8"))
    for row in data["outcomes"]:
        if row["impl"] == "hand-written":
            row["ms_per_episode"] = 10_000.0  # now the slowest compliant row is not contexel
    results.write_text(json.dumps(data, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8", newline="\n")
    (tree / "benchmarks" / "COMPARISON.md").write_text(competitors.render_report(data), encoding="utf-8",
                                                         newline="\n")
    problems = publish.check(tree)
    assert any("slowest budget-compliant row" in p and "not true" in p for p in problems), problems


def test_a_stale_report_is_reported(tree):
    comparison = tree / "benchmarks" / "COMPARISON.md"
    comparison.write_text(comparison.read_text(encoding="utf-8").replace("contexel", "contexel ", 1),
                          encoding="utf-8", newline="\n")
    assert any("COMPARISON.md" in p and "not the report rendered" in p for p in publish.check(tree))
    results = tree / "benchmarks" / "RESULTS.md"
    results.write_text(results.read_text(encoding="utf-8") + "x", encoding="utf-8", newline="\n")
    assert any("RESULTS.md" in p for p in publish.check(tree))


def test_results_made_with_another_dataset_are_reported(tree):
    results = tree / "benchmarks" / "COMPARISON.json"
    data = json.loads(results.read_text(encoding="utf-8"))
    data["dataset"]["sha256"] = "0" * 64
    results.write_text(json.dumps(data, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8", newline="\n")
    (tree / "benchmarks" / "COMPARISON.md").write_text(competitors.render_report(data), encoding="utf-8",
                                                         newline="\n")
    assert any("dataset digest" in p for p in publish.check(tree))


def test_a_missing_or_unknown_block_marker_is_reported(tree):
    _replace(tree, "README.md", "<!-- benchmark:inflected:start -->", "")
    assert any("benchmark:inflected" in p for p in publish.check(tree))
    _replace(tree, "site/index.html", "</body>",
             "<!-- benchmark:extra:start --><!-- benchmark:extra:end -->\n</body>")
    assert any("unknown benchmark:extra block" in p for p in publish.check(tree))


def test_write_regenerates_the_blocks_and_the_check_then_passes(tree):
    _replace(tree, "README.md", "| **contexel** |", "| **contexel (edited)** |")
    assert publish.check(tree)
    assert "README.md" in publish.write(tree)
    assert publish.check(tree) == []
    assert publish.write(tree) == []  # idempotent


def test_the_command_exits_non_zero_on_drift(tree):
    script = ROOT / "tools" / "check_benchmark_numbers.py"
    ok = subprocess.run([sys.executable, str(script), "--root", str(tree)], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    _replace(tree, "README_PYPI.md", "28,047 search-tool records", "28,048 search-tool records")
    bad = subprocess.run([sys.executable, str(script), "--root", str(tree)], capture_output=True, text=True)
    assert bad.returncode == 1 and "README_PYPI.md" in bad.stdout


def test_the_reports_are_rendered_from_the_json_alone():
    comparison = json.loads((ROOT / "benchmarks" / "COMPARISON.json").read_text(encoding="utf-8"))
    suites = json.loads((ROOT / "benchmarks" / "RESULTS.json").read_text(encoding="utf-8"))
    assert competitors.render_report(comparison) == competitors.render_report(json.loads(json.dumps(comparison)))
    assert suites_report.render(suites) == suites_report.render(json.loads(json.dumps(suites)))
    text = competitors.render_report(comparison)
    assert comparison["dataset"]["sha256"] in text
    assert "Inflected-query episodes" in text and "not synonyms, not paraphrase, not meaning" in text
