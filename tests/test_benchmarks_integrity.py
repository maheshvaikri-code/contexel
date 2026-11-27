"""AC 26: every published benchmark number equals the generated results, and a
number that does not is reported. The tests that exercise a competitor library skip
when it is not installed."""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks import competitors, publish, suites_report  # noqa: E402

SITE_PAGES = (
    "site/index.html", "site/benchmarks.html", "site/stages.html", "site/architecture.html",
    "site/getting-started.html", "site/contract.html",
)
PUBLISHED = (
    "README.md", "README_PYPI.md", *SITE_PAGES,
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
    """A copy of the published files under ``tmp_path / "tree"`` (the rest of tmp_path is
    "outside the root" for the tests of ``write``)."""
    root = tmp_path / "tree"
    for rel in PUBLISHED:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    return root


def _write(path, text):
    """Write ``text`` (LF line endings) as UTF-8 bytes. ``Path.write_text`` has no
    ``newline`` argument before Python 3.10, and CI runs these tests on 3.9."""
    path.write_bytes(text.encode("utf-8"))


def _replace(root, rel, old, new, count=1):
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) >= 1, (rel, old)
    _write(path, text.replace(old, new, count))


def test_the_copy_of_the_tree_used_below_is_clean(tree):
    assert publish.check(tree) == []


def test_the_check_is_the_same_on_a_checkout_with_crlf_line_endings(tree):
    for rel in PUBLISHED:  # what a Windows checkout with autocrlf writes
        path = tree / rel
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert publish.check(tree) == []
    assert publish.write(tree) == []  # and --write has nothing to change
    assert publish.write_reports(tree) == []


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
    _replace(tree, "site/index.html", "slowest\nbudget-compliant rows", "slowest compliant rows")
    assert any("two slowest budget-compliant rows" in p and "not found" in p for p in publish.check(tree))


def test_a_false_qualitative_claim_is_reported(tree):
    results = tree / "benchmarks" / "COMPARISON.json"
    data = json.loads(results.read_text(encoding="utf-8"))
    for row in data["outcomes"]:
        if row["impl"] == "hand-written":
            row["ms_per_episode"] = 10_000.0  # now a third row is one of the two slowest
    _write(results, json.dumps(data, indent=2, ensure_ascii=False) + chr(10))
    _write(tree / "benchmarks" / "COMPARISON.md", competitors.render_report(data))
    problems = publish.check(tree)
    assert any("two slowest budget-compliant rows" in p and "not true" in p for p in problems), problems


def test_a_stale_report_is_reported(tree):
    comparison = tree / "benchmarks" / "COMPARISON.md"
    _write(comparison, comparison.read_text(encoding="utf-8").replace("contexel", "contexel ", 1))
    assert any("COMPARISON.md" in p and "not the report rendered" in p for p in publish.check(tree))
    results = tree / "benchmarks" / "RESULTS.md"
    _write(results, results.read_text(encoding="utf-8") + "x")
    assert any("RESULTS.md" in p for p in publish.check(tree))


def test_results_made_with_another_dataset_are_reported(tree):
    results = tree / "benchmarks" / "COMPARISON.json"
    data = json.loads(results.read_text(encoding="utf-8"))
    data["dataset"]["sha256"] = "0" * 64
    _write(results, json.dumps(data, indent=2, ensure_ascii=False) + chr(10))
    _write(tree / "benchmarks" / "COMPARISON.md", competitors.render_report(data))
    assert any("dataset digest" in p for p in publish.check(tree))


def test_a_pin_that_is_not_one_line_is_reported_by_the_check(tree):
    pin = tree / "benchmarks" / "dataset.sha256"
    _write(pin, pin.read_text(encoding="ascii") + "0" * 64 + "\n")  # a second line
    problems = publish.check(tree)
    assert any("dataset.sha256" in p and "must be one line" in p for p in problems), problems
    _write(pin, "")
    assert any("dataset.sha256" in p and "is empty" in p for p in publish.check(tree))


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


# --- a number with a unit is found however it is written -------------------------------
_ANCHOR = "Both are noise next to a"


@pytest.mark.parametrize("written", [
    "10x faster", "12&nbsp;ms", "3&times;", "40&#37;", "12  ms", "12 msec", "12 milliseconds",
    "40 percent", "12" + chr(0xA0) + "ms",
])
def test_every_way_of_writing_a_number_with_a_unit_is_reported(tree, written):
    _replace(tree, "README.md", _ANCHOR, f"Both are noise ({written}) next to a")
    problems = publish.check(tree)
    assert any("unregistered benchmark number" in p and "README.md" in p for p in problems), (written, problems)


@pytest.mark.parametrize("tag", [
    '<abbr title="12 ms">i</abbr>', '<img alt="12 ms">', '<span aria-label="40%">i</span>',
    '<meta name="description" content="3&times; faster">',
])
def test_a_number_inside_an_attribute_is_reported(tree, tag):
    _replace(tree, "site/index.html", "<h2>The record, at a glance</h2>",
             "<h2>The record, at a glance</h2>\n" + tag)
    problems = publish.check(tree)
    assert any("unregistered benchmark number" in p and "site/index.html" in p for p in problems), (tag, problems)


def test_a_bare_number_in_a_table_cell_outside_a_block_is_reported(tree):
    _replace(tree, "README.md", "How to read each column, plainly:",
             "| Implementation | Score |\n|---|---|\n| contexel | 12 |\n\nHow to read each column, plainly:")
    assert any("README.md" in p and "table cell" in p and "'12'" in p for p in publish.check(tree))
    _replace(tree, "site/benchmarks.html", "<h3>How to read it</h3>",
             "<table><tr><td>12</td></tr></table>\n<h3>How to read it</h3>")
    assert any("site/benchmarks.html" in p and "table cell" in p for p in publish.check(tree))


def test_a_year_or_a_version_is_not_a_benchmark_number(tree):
    _replace(tree, "README.md", _ANCHOR, "Both are noise (since the 1990s, in 0x1f, version 3.12) next to a")
    assert publish.check(tree) == []


# --- the registered claims follow the data ---------------------------------------------
def _edit_comparison(tree, edit):
    path = tree / "benchmarks" / "COMPARISON.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    edit(data)
    _write(path, json.dumps(data, indent=2, ensure_ascii=False) + chr(10))
    _write(tree / "benchmarks" / "COMPARISON.md", competitors.render_report(data))


def _outcome(data, impl):
    return next(r for r in data["outcomes"] if r["impl"] == impl)


def test_the_two_slowest_compliant_rows_may_swap_places(tree):
    top = max(o["ms_per_episode"] for o in json.loads(
        (tree / "benchmarks" / "COMPARISON.json").read_text(encoding="utf-8"))["outcomes"])

    def edit(data):
        _outcome(data, "hand-written (term overlap)")["ms_per_episode"] = top + 100.0

    _edit_comparison(tree, edit)
    assert not [p for p in publish.check(tree) if "slowest" in p]


def test_a_third_row_among_the_two_slowest_compliant_rows_is_reported(tree):
    _edit_comparison(tree, lambda data: _outcome(data, "langchain-core").__setitem__("ms_per_episode", 10_000.0))
    assert any("two slowest budget-compliant rows" in p and "not true" in p for p in publish.check(tree))


def test_an_inflection_drop_smaller_than_thirty_points_is_not_a_collapse(tree):
    def edit(data):
        row = next(r for r in data["inflected"]["rows"] if r["shaper"] == "contexel")
        row["recall_inflected_pct"] = row["recall_original_pct"] - 10

    _edit_comparison(tree, edit)
    assert any("word mode drops on inflected queries" in p and "not true" in p for p in publish.check(tree))


def test_a_stem_row_far_from_its_original_recall_is_not_a_recovery(tree):
    def edit(data):
        row = next(r for r in data["inflected"]["rows"] if r["shaper"] == "contexel (match=stem)")
        row["recall_inflected_pct"] = row["recall_original_pct"] - 20
        word = next(r for r in data["inflected"]["rows"] if r["shaper"] == "contexel")
        word["recall_inflected_pct"] = 0

    _edit_comparison(tree, edit)
    assert any("word mode drops on inflected queries" in p and "not true" in p for p in publish.check(tree))


def test_a_changed_number_in_the_readme_inflected_block_is_reported(tree):
    _replace(tree, "README.md", "| contexel (match=stem) | 98 | 98 |", "| contexel (match=stem) | 98 | 97 |")
    assert any("README.md" in p and "benchmark:inflected" in p for p in publish.check(tree))


def test_a_changed_number_in_the_home_page_table_is_reported(tree):
    comparison = json.loads((tree / "benchmarks" / "COMPARISON.json").read_text(encoding="utf-8"))
    ms = publish._n0(comparison["task"][0]["ms"])
    _replace(tree, "site/index.html", f"<td>{ms}</td>", f"<td>{int(ms.replace(',', '')) + 1}</td>")
    assert any("site/index.html" in p and "benchmark:glance" in p for p in publish.check(tree))


@pytest.mark.parametrize("rel, old, new", [
    ("README_PYPI.md", "import of about 20 ms", "import of about 90 ms"),
    ("site/index.html", "about 20&nbsp;ms import", "about 90&nbsp;ms import"),
])
def test_a_wrong_import_time_is_reported(tree, rel, old, new):
    _replace(tree, rel, old, new)
    assert any(rel in p and "import time" in p for p in publish.check(tree))


def test_another_about_n_ms_sentence_does_not_stand_in_for_the_import_claim(tree):
    _replace(tree, "README_PYPI.md", "import of about 20 ms", "start-up of about 20 ms")
    problems = publish.check(tree)
    assert any("import time" in p and "not found" in p for p in problems), problems


@pytest.mark.parametrize("old, new, label", [
    ("reaches\n97% recall", "reaches\n96% recall", "term-overlap baseline recall"),
    ("finds the record in 99% of those", "finds the record in 98% of those", "default matching, original terms"),
    ("own words and in 35% with inflections", "own words and in 34% with inflections",
     "default matching, inflected terms"),
    ("finds it in 98% with the inflections", "finds it in 97% with the inflections",
     "stem matching, inflected terms"),
])
def test_a_wrong_number_in_the_pypi_comparison_sentences_is_reported(tree, old, new, label):
    _replace(tree, "README_PYPI.md", old, new)
    problems = publish.check(tree)
    assert any("README_PYPI.md" in p and label in p for p in problems), problems


def test_the_pypi_stem_caveat_and_the_second_set_of_episodes_are_registered(tree):
    _replace(tree, "README_PYPI.md", "not\nhow many English inflections", "not\nhow much of English")
    assert any("README_PYPI.md" in p and "not a coverage figure" in p and "not found" in p
               for p in publish.check(tree))
    _replace(tree, "README_PYPI.md", "On a second set of episodes", "On other episodes")
    assert any("README_PYPI.md" in p and "second set of episodes" in p and "not found" in p
               for p in publish.check(tree))


def test_the_all_six_operations_claim_needs_a_total_of_six(tree):
    def edit(data):
        for row in data["operations"]:
            if row["impl"] == "contexel":
                row["native"] = row["native"] + ["extra"]  # seven of seven: still "all", no longer six

    _edit_comparison(tree, edit)
    problems = publish.check(tree)
    assert any("README_PYPI.md" in p and "only row with every operation native" in p and "not true" in p
               for p in problems), problems


# --- the unit scan: case, underscores, "per cent", the ASCII x ----------------------------
@pytest.mark.parametrize("written", [
    "10X faster", "12 MS", "12 Ms", "40 PERCENT", "40 per cent", "_12 ms_", "1.5x", "2.95x",
])
def test_more_ways_of_writing_a_number_with_a_unit_are_reported(tree, written):
    _replace(tree, "README.md", _ANCHOR, f"Both are noise ({written}) next to a")
    problems = publish.check(tree)
    assert any("unregistered benchmark number" in p and "README.md" in p for p in problems), (written, problems)


@pytest.mark.parametrize("written", ["a 3 x 4 grid", "Python 3.x", "a12 ms", "0x1f", "a 1990s sample"])
def test_text_that_is_not_a_number_with_a_unit_is_not_reported(tree, written):
    _replace(tree, "README.md", _ANCHOR, f"Both are noise ({written}) next to a")
    assert publish.check(tree) == [], written


# --- the bare-cell guard sees through formatting -------------------------------------------
@pytest.mark.parametrize("rel, anchor, cell", [
    ("README.md", "How to read each column, plainly:", "| a | `12` |"),
    ("README.md", "How to read each column, plainly:", "| a | ~12 |"),
    ("README.md", "How to read each column, plainly:", "| a | 12"),
    ("README.md", "How to read each column, plainly:", "| a | **12** |"),
    ("site/benchmarks.html", "<h3>How to read it</h3>", "<table><tr><td><b>12</b></td></tr></table>"),
    ("site/benchmarks.html", "<h3>How to read it</h3>", "<table><tr><td>&nbsp;12 </td></tr></table>"),
])
def test_a_bare_number_cell_is_reported_however_it_is_formatted(tree, rel, anchor, cell):
    _replace(tree, rel, anchor, cell + "\n\n" + anchor)
    problems = publish.check(tree)
    assert any(rel in p and "table cell" in p and "'12'" in p for p in problems), (cell, problems)


def test_a_bare_number_cell_in_italics_is_reported(tree):
    _replace(tree, "README.md", "How to read each column, plainly:",
             "| a | _12_ |\n\nHow to read each column, plainly:")
    assert any("README.md" in p and "table cell" in p and "'12'" in p for p in publish.check(tree))


def test_a_table_cell_with_words_or_a_version_is_not_a_bare_number(tree):
    _replace(tree, "README.md", "How to read each column, plainly:",
             "| a | 6/6 |\n| b | v2 |\n|---|---|\n\nHow to read each column, plainly:")
    assert publish.check(tree) == []


# --- the scan sees through Unicode tricks, covers microseconds and more attributes -------
@pytest.mark.parametrize("written", [
    "12 " + chr(0xB5) + "s", "12 " + chr(0x3BC) + "s", "12 &micro;s", "12 us", "12 ns", "12ns",
    "12 " + chr(0x39C) + "S", "12 Microseconds", "12 NANOSECONDS",  # these stay case-insensitive
    "12 microseconds", "12 nanoseconds", "40" + chr(0xFF05), chr(0xFF11) + chr(0xFF12) + " ms",
    "12" + chr(0x200B) + "ms", "12" + chr(0xAD) + "ms", "12" + chr(0x2060) + "ms",
    "12" + chr(0x200C) + " ms", "40" + chr(0x200D) + "%", "12" + chr(0xFEFF) + "ms", "12&#8203;ms",
])
def test_a_number_split_or_disguised_by_unicode_or_in_microseconds_is_reported(tree, written):
    _replace(tree, "README.md", _ANCHOR, f"Both are noise ({written}) next to a")
    problems = publish.check(tree)
    assert any("unregistered benchmark number" in p and "README.md" in p for p in problems), (written, problems)


@pytest.mark.parametrize("tag", [
    '<input placeholder="12 ms">', '<span data-tip="40%">i</span>',
    "<span data-cost-per-record='3&times;'>i</span>",
])
def test_a_number_inside_a_placeholder_or_data_attribute_is_reported(tree, tag):
    _replace(tree, "site/index.html", "<h2>The record, at a glance</h2>",
             "<h2>The record, at a glance</h2>\n" + tag)
    problems = publish.check(tree)
    assert any("unregistered benchmark number" in p and "site/index.html" in p for p in problems), (tag, problems)


@pytest.mark.parametrize("written", [
    "a 3 x 4 grid", "Python 3.x", "12 users", "5 nodes", "12 usb ports", "the US market",
    "a 12-step plan", "50 US states", "8 NS records", "a12 ms",
])
def test_words_that_start_like_a_unit_are_not_reported(tree, written):
    _replace(tree, "README.md", _ANCHOR, f"Both are noise ({written}) next to a")
    assert publish.check(tree) == [], written


@pytest.mark.parametrize("written", ["fast,12 ms", "a,40%", chr(0x2026) + "12 ms"])
def test_a_number_after_a_comma_or_an_ellipsis_is_reported(tree, written):
    # a comma or dot blocks a start only when a digit precedes it (inside "1,234" or "3.12");
    # NFKC turns the ellipsis into three dots, which must not hide the number after them
    _replace(tree, "README.md", _ANCHOR, f"Both are noise ({written}) next to a")
    problems = publish.check(tree)
    assert any("unregistered benchmark number" in p and "README.md" in p for p in problems), (written, problems)


# --- linear time on adversarial text; an oversized file is refused --------------------------
# Sizes: the earlier patterns took 150 s or more on 40,000 digits and 11 to 55 s on 160,000
# characters of the other four; the linear ones take well under a second on all of them.
_ADVERSARIAL = {
    "a run of digits": "1" * 40_000,
    "1, repeated": "1," * 20_000,
    "unclosed td cells": "<td>" * 40_000,
    "unclosed block start markers": "<!-- benchmark:glance:start -->" * 5_200,
    "a run of <": "<" * 160_000,
    "unclosed Markdown link targets": "](" * 80_000,
    "1,, repeated": "1,," * 53_000,
    # a claim's leading word followed by a long run of spaces (ROWS took about 2 minutes)
    "split and spaces": "split" + " " * 160_000,
    "about and spaces": "about" + " " * 160_000,
    "Budget: and spaces": "Budget:" + " " * 160_000,
    "import and spaces": "import" + " " * 160_000,
    "slowest and spaces": "slowest" + " " * 160_000,
    "contexel and spaces": "contexel" + " " * 160_000,
    "one dataset and digits": "one dataset, " + "1," * 80_000,
}


@pytest.mark.parametrize("name", sorted(_ADVERSARIAL))
def test_the_check_runs_in_linear_time_on_adversarial_text(tree, name):
    # the earlier patterns backtracked quadratically: seconds to minutes on these. The text
    # goes into every published file, so every file's registered claims see it.
    for rel in publish.FILES:
        path = tree / rel
        _write(path, path.read_text(encoding="utf-8") + "\n" + _ADVERSARIAL[name] + "\n")
    start = time.perf_counter()
    publish.check(tree)
    assert time.perf_counter() - start < 2.0, name


def test_a_published_file_larger_than_two_megabytes_is_refused_not_scanned(tree):
    path = tree / "README.md"
    _write(path, path.read_text(encoding="utf-8") + "x" * publish.MAX_PUBLISHED_BYTES)
    problems = publish.check(tree)
    assert any("README.md" in p and "larger than" in p for p in problems), problems


def test_an_oversized_file_is_refused_before_it_is_read(tree, monkeypatch):
    path = tree / "README.md"
    _write(path, "x" * (publish.MAX_PUBLISHED_BYTES + 1))  # one byte over the cap
    read = []
    real = Path.read_bytes

    def recording(self):
        read.append(self.name)
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", recording)
    problems = publish.check(tree)
    assert any("README.md" in p and "larger than" in p for p in problems), problems
    assert "README.md" not in read  # its size was checked first; it was never loaded
    assert "README_PYPI.md" in read  # (the other files were read as usual)


def test_a_block_marker_without_its_pair_is_reported(tree):
    _replace(tree, "README.md", "<!-- benchmark:glance:start -->",
             "<!-- benchmark:glance:start -->\n<!-- benchmark:glance:start -->")
    problems = publish.check(tree)
    assert any("README.md" in p and "marker without its pair" in p for p in problems), problems


# --- values from the results are escaped in the Markdown blocks ----------------------------
def test_names_from_the_results_are_escaped_in_the_markdown_blocks(tree):
    poison = "<script>x|y</script>"
    path = tree / "benchmarks" / "COMPARISON.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("outcomes", "operations"):
        next(r for r in data[key] if r["impl"] == "toolz")["impl"] = poison
    next(r for r in data["inflected"]["rows"] if r["shaper"] == "hand-written")["shaper"] = poison
    _write(path, json.dumps(data, indent=2, ensure_ascii=False) + chr(10))
    publish.write(tree)
    readme = (tree / "README.md").read_text(encoding="utf-8")
    for name in ("glance", "inflected"):
        block = next(m.group("body") for m in publish.BLOCK.finditer(readme) if m.group("name") == name)
        assert "<script>" not in block and "&lt;script&gt;x\\|y&lt;/script&gt;" in block, name
        rows = [line for line in block.strip().splitlines()]
        widths = {len(re.split(r"(?<!\\)\|", line)) for line in rows}
        assert len(widths) == 1, (name, rows)  # no row gained a column


# --- write: never through a link, never outside the root, through a temporary file --------
def _link_directory(link, target):
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    try:  # a Windows junction needs no privilege
        import _winapi
        _winapi.CreateJunction(str(target), str(link))  # type: ignore[attr-defined]
        return True
    except (ImportError, AttributeError, OSError):
        return False


def test_write_refuses_a_symbolic_link(tree, tmp_path):
    readme = tree / "README.md"
    target = tmp_path / "outside" / "README.md"  # outside the root, inside the test's directory
    target.parent.mkdir()
    _write(target, readme.read_text(encoding="utf-8").replace("| **contexel** |", "| **edited** |"))
    readme.unlink()
    try:
        readme.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links cannot be created here")
    before = target.read_bytes()
    try:
        with pytest.raises(publish.PublishError, match="symbolic link"):
            publish.write(tree)
        assert target.read_bytes() == before
    finally:
        readme.unlink()


def test_write_refuses_a_file_that_resolves_outside_the_root(tree, tmp_path):
    outside = tmp_path / "outside" / "site"
    shutil.copytree(str(tree / "site"), str(outside))
    shutil.rmtree(str(tree / "site"))
    if not _link_directory(tree / "site", outside):
        pytest.skip("neither a directory symlink nor a junction can be created here")
    try:
        with pytest.raises(publish.PublishError, match="outside"):
            publish.write(tree)
    finally:
        try:
            os.unlink(str(tree / "site"))
        except OSError:
            os.rmdir(str(tree / "site"))


def test_write_refuses_a_target_that_is_not_a_file(tree):
    readme = tree / "README.md"
    readme.unlink()
    readme.mkdir()
    with pytest.raises(publish.PublishError, match="not a regular file"):
        publish.write(tree)
    assert any("README.md" in p and "cannot read" in p for p in publish.check(tree))
    script = ROOT / "tools" / "check_benchmark_numbers.py"
    run = subprocess.run([sys.executable, str(script), "--root", str(tree), "--write"],
                         capture_output=True, text=True)
    assert run.returncode == 1 and "cannot write" in run.stdout and "Traceback" not in run.stderr


def test_write_goes_through_a_temporary_file_and_leaves_none_behind(tree):
    _replace(tree, "README.md", "| **contexel** |", "| **contexel (edited)** |")
    assert publish.write(tree) == ["README.md"]
    assert publish.check(tree) == []
    assert not [p.name for p in tree.rglob("*.tmp")]
    assert (tree / "README.md").read_bytes().count(b"\r") == 0  # LF


# --- malformed or missing inputs are reported, not a traceback ------------------------------
@pytest.mark.parametrize("rel", ["benchmarks/COMPARISON.md", "benchmarks/RESULTS.md"])
def test_a_missing_report_is_reported(tree, rel):
    (tree / rel).unlink()
    problems = publish.check(tree)
    assert any(rel in p and "cannot read" in p for p in problems), problems


@pytest.mark.parametrize("rel, edit", [
    ("benchmarks/COMPARISON.json", lambda d: d.pop("inflected")),
    ("benchmarks/COMPARISON.json", lambda d: d.__setitem__("outcomes", 5)),
    ("benchmarks/COMPARISON.json", lambda d: d["dataset"].pop("sha256")),
    ("benchmarks/COMPARISON.json", lambda d: d.__setitem__("operations", [])),
    ("benchmarks/RESULTS.json", lambda d: d.pop("accuracy")),
    ("benchmarks/RESULTS.json", lambda d: d["speed"].__setitem__("stages", [])),
])
def test_malformed_results_are_reported(tree, rel, edit):
    path = tree / rel
    data = json.loads(path.read_text(encoding="utf-8"))
    edit(data)
    _write(path, json.dumps(data, indent=2) + chr(10))
    problems = publish.check(tree)
    assert any("malformed" in p for p in problems), problems
    script = ROOT / "tools" / "check_benchmark_numbers.py"
    run = subprocess.run([sys.executable, str(script), "--root", str(tree)], capture_output=True, text=True)
    assert run.returncode == 1 and "Traceback" not in run.stderr, run.stderr


def _set_trim_budget_zero(data):
    data["budget"]["trim"][0]["budget"] = 0


@pytest.mark.parametrize("rel, edit, error", [
    ("benchmarks/COMPARISON.json", lambda d: d["task"][0].__setitem__("native", None), "AttributeError"),
    ("benchmarks/COMPARISON.json", lambda d: d.__setitem__("outcomes", []), "StopIteration"),
    ("benchmarks/RESULTS.json", _set_trim_budget_zero, "ZeroDivisionError"),
])
def test_results_that_raise_attribute_iteration_or_arithmetic_errors_are_reported(tree, rel, edit, error):
    path = tree / rel
    data = json.loads(path.read_text(encoding="utf-8"))
    edit(data)
    _write(path, json.dumps(data, indent=2) + chr(10))
    problems = publish.check(tree)
    assert any("malformed" in p and error in p for p in problems), problems
    script = ROOT / "tools" / "check_benchmark_numbers.py"
    run = subprocess.run([sys.executable, str(script), "--root", str(tree)], capture_output=True, text=True)
    assert run.returncode == 1 and "Traceback" not in run.stderr, run.stderr


def test_a_published_file_that_is_not_utf8_is_reported(tree):
    readme = tree / "README.md"
    readme.write_bytes(readme.read_bytes() + b"\xff\xfe broken")
    problems = publish.check(tree)
    assert any("README.md" in p and "not valid UTF-8" in p for p in problems), problems


# --- the Compliance column is gone from every published table (ruling P1-1) -----------------
# compliance_pct stays in the results (it is a record, and two claims still read it), but no
# generated table shows it and no claim scores a row by it: it was counted with the same
# ~4 characters per token estimate the rows cut with, so it could not tell them apart.
def _committed():
    return json.loads((ROOT / "benchmarks" / "COMPARISON.json").read_text(encoding="utf-8"))


FILL_HEADER = "Fill " + chr(0xD7) + " (estimated tokens " + chr(0xF7) + " budget)"


def _md_rows(block):
    return [re.split(r"(?<!\\)\|", line.strip().strip("|")) for line in block.splitlines()]


def test_no_generated_table_has_a_compliance_column():
    comparison = _committed()
    tables = {
        "README glance": publish.md_glance(comparison),
        "site glance": publish.html_glance(comparison),
        "home glance": publish.html_home_glance(comparison),
        "README inflected": publish.md_inflected(comparison),
        "site inflected": publish.html_inflected(comparison),
    }
    for name, text in tables.items():
        assert "compliance" not in text.lower(), name


def test_the_generated_tables_do_not_change_with_compliance():
    comparison = _committed()
    edited = json.loads(json.dumps(comparison))
    for row in edited["outcomes"]:
        row["compliance_pct"] = 50.0
    for render in (publish.md_glance, publish.html_glance, publish.html_home_glance):
        assert render(edited) == render(comparison), render.__name__


def test_the_fill_column_is_labelled_as_estimated_tokens_over_the_budget():
    comparison = _committed()
    md = publish.md_glance(comparison)
    rows = _md_rows(md)
    assert FILL_HEADER in [c.strip() for c in rows[0]]
    assert len({len(r) for r in rows}) == 1  # every row has a cell under every header
    for render in (publish.html_glance, publish.html_home_glance):
        html_table = render(comparison)
        assert f"<th>{FILL_HEADER}</th>" in html_table, render.__name__
        assert "<td>91.62" + chr(0xD7) + "</td>" in html_table, render.__name__


def test_native_ops_and_deps_headers_say_what_they_count():
    comparison = _committed()
    head = [c.strip() for c in _md_rows(publish.md_glance(comparison))[0]]
    assert "Native ops (in this wiring)" in head and "Transitive deps" in head
    assert "Deps" not in head and "Native ops" not in head
    for render in (publish.html_glance, publish.html_home_glance):
        text = render(comparison)
        assert "<th>Native ops (in this wiring)</th>" in text and "<th>Transitive deps</th>" in text


def test_recall_is_not_marked_best_on_a_row_that_runs_over_the_budget():
    # facts:S9: toolz and llama-index-core keep the record by emitting about 92 and 129 times
    # the budget; their recall cells are not highlighted as the best result
    comparison = _committed()
    rows = {r["impl"]: r for r in publish.glance(comparison)}
    assert publish._tier("recall", rows["contexel"]) == "best"
    for name in ("toolz", "llama-index-core"):
        assert rows[name]["fill"] > 1 and publish._tier("recall", rows[name]) == "", name
    md = {r[0].strip().strip("*"): r for r in _md_rows(publish.md_glance(comparison))[2:]}
    recall = 4  # Implementation, Native ops, ms @28k, ms/episode, Recall
    assert md["contexel"][recall].strip() == "**100 / 100**"
    assert md["toolz"][recall].strip() == "100 / 100"
    assert md["llama-index-core"][recall].strip() == "100 / 100"
    site = publish.html_glance(comparison)
    toolz_row = next(line for line in site.splitlines() if "<td>toolz</td>" in line)
    assert '<td class="best">100% / 100%</td>' not in toolz_row
    assert "<td>100% / 100%</td>" in toolz_row


def test_no_claim_scores_a_row_by_its_compliance():
    labels = {c.label for c in publish.CLAIMS}
    assert "only row with full marks" not in labels
    assert "toolz and llama-index: full recall, zero compliance" not in labels


def test_full_compliance_for_toolz_breaks_no_published_claim(tree):
    # the claims that read "full recall and zero compliance" are gone: toolz's compliance no
    # longer decides whether a published sentence is true (toolz is not among the slowest
    # rows, so the "two slowest budget-compliant rows" sentence is unaffected)
    _edit_comparison(tree, lambda data: _outcome(data, "toolz").update(compliance_pct=100.0))
    assert publish.check(tree) == []


def test_the_reports_have_no_compliance_column_and_the_new_fill_label():
    comparison = _committed()
    text = competitors.render_report(comparison)
    assert "compliance" not in text.lower()
    assert FILL_HEADER in text
    for line in text.splitlines():
        if line.startswith("| Implementation |"):
            assert "Fill x" not in line


# --- --write regenerates the two reports from the committed JSON too ------------------------
def test_write_reports_rerenders_a_stale_report_and_is_idempotent(tree):
    for rel in ("benchmarks/COMPARISON.md", "benchmarks/RESULTS.md"):
        path = tree / rel
        _write(path, path.read_text(encoding="utf-8") + "stale\n")
    assert len([p for p in publish.check(tree) if "not the report rendered" in p]) == 2
    rewritten = sorted(publish.write_reports(tree))
    assert rewritten == ["benchmarks/COMPARISON.md", "benchmarks/RESULTS.md"]
    assert publish.check(tree) == []
    assert publish.write_reports(tree) == []  # idempotent
    assert not [p.name for p in tree.rglob("*.tmp")]


def test_the_write_command_regenerates_the_reports(tree):
    path = tree / "benchmarks" / "COMPARISON.md"
    _write(path, path.read_text(encoding="utf-8") + "stale\n")
    script = ROOT / "tools" / "check_benchmark_numbers.py"
    run = subprocess.run([sys.executable, str(script), "--root", str(tree), "--write"],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "benchmarks/COMPARISON.md" in run.stdout
    comparison = json.loads((tree / "benchmarks" / "COMPARISON.json").read_text(encoding="utf-8"))
    assert path.read_text(encoding="utf-8") == competitors.render_report(comparison)


def test_a_stale_report_hint_never_reruns_a_benchmark(tree):
    # regenerating a report from the committed JSON is --write; the benchmark commands
    # would re-measure and change the published timings
    for rel in ("benchmarks/COMPARISON.md", "benchmarks/RESULTS.md"):
        path = tree / rel
        _write(path, path.read_text(encoding="utf-8") + "stale\n")
    hints = [p for p in publish.check(tree) if "not the report rendered" in p]
    assert len(hints) == 2
    for hint in hints:
        assert "python tools/check_benchmark_numbers.py --write" in hint, hint
        assert "python -m benchmarks" not in hint, hint


@pytest.mark.parametrize("newline", [b"\r\n", b"\n"])
def test_write_keeps_each_files_line_endings(tree, newline):
    # a CRLF checkout stays CRLF and an LF one stays LF, for the blocks and the reports
    rels = ("README.md", "site/index.html", "benchmarks/COMPARISON.md", "benchmarks/RESULTS.md")
    for rel in rels:
        path = tree / rel
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", newline))
    _replace(tree, "README.md", "| **contexel** |", "| **contexel (edited)** |")
    _replace(tree, "site/index.html", "<td><strong>contexel</strong></td>", "<td>x</td>")
    for rel in ("benchmarks/COMPARISON.md", "benchmarks/RESULTS.md"):
        path = tree / rel
        path.write_bytes(path.read_bytes() + b"stale" + newline)
    if newline == b"\r\n":  # _replace wrote LF: put the edited files back to CRLF
        for rel in ("README.md", "site/index.html"):
            path = tree / rel
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert sorted(publish.write(tree)) == ["README.md", "site/index.html"]
    assert len(publish.write_reports(tree)) == 2
    for rel in rels:
        data = (tree / rel).read_bytes()
        lf_only = data.count(b"\n") - data.count(b"\r\n")
        if newline == b"\r\n":
            assert lf_only == 0 and data.count(b"\r\n") > 0, rel
        else:
            assert b"\r" not in data, rel
    assert publish.check(tree) == []
    assert publish.write(tree) == [] and publish.write_reports(tree) == []  # idempotent


def test_write_reports_refuses_a_target_that_is_not_a_file(tree):
    report = tree / "benchmarks" / "RESULTS.md"
    report.unlink()
    report.mkdir()
    with pytest.raises(publish.PublishError, match="not a regular file"):
        publish.write_reports(tree)


# --- reproducibility: the measured versions are recorded as constraints (P1-9) ---------------
def test_the_constraints_file_pins_the_measured_versions():
    measured = _committed()["environment"]["libraries"]
    lines = (ROOT / "benchmarks" / "constraints.txt").read_text(encoding="utf-8").splitlines()
    pins = dict(line.split("==") for line in lines if line.strip() and not line.startswith("#"))
    assert pins == measured


def test_no_benchmark_source_cites_a_readme_section_that_does_not_exist():
    # numbers:D11: the README has no "How much does it cut?" section
    for rel in ("benchmarks/__init__.py", "benchmarks/suites.py", "benchmarks/suites_report.py",
                "benchmarks/RESULTS.md"):
        assert "How much does it cut" not in (ROOT / rel).read_text(encoding="utf-8"), rel


# --- the check reads every site page, not only the two with tables (ruling P1-10) -----------
# numbers:D3 was a wrong figure on site/stages.html, which nothing scanned.
def test_the_check_covers_both_readmes_and_every_site_page():
    assert set(publish.FILES) == {"README.md", "README_PYPI.md", *SITE_PAGES}
    assert len(publish.FILES) == 8
    on_disk = {p.relative_to(ROOT).as_posix() for p in (ROOT / "site").glob("*.html")}
    assert on_disk <= set(publish.FILES), sorted(on_disk - set(publish.FILES))


@pytest.mark.parametrize("rel", [
    "site/stages.html", "site/architecture.html", "site/getting-started.html", "site/contract.html",
])
def test_a_hand_typed_benchmark_number_on_another_site_page_is_reported(tree, rel):
    _replace(tree, rel, "</body>", "<p>about 12 ms per call, 40% fewer tokens</p>\n</body>")
    problems = publish.check(tree)
    assert any(rel in p and "unregistered benchmark number" in p and "12 ms" in p for p in problems), problems
    assert any(rel in p and "unregistered benchmark number" in p and "40%" in p for p in problems), problems


def test_a_table_cell_that_is_only_a_number_on_the_stage_reference_is_reported(tree):
    _replace(tree, "site/stages.html", "</body>", "<table><tr><td>166.5</td></tr></table>\n</body>")
    problems = publish.check(tree)
    assert any("site/stages.html" in p and "table cell" in p and "'166.5'" in p for p in problems), problems


# --- the hand-written sentences that were true but unchecked (numbers audit section 8) -------
_DISCLOSED = ("README.md", "README_PYPI.md", "site/index.html", "site/benchmarks.html")


def _replace_words(root, rel, old, new):
    """Replace the one occurrence of the words ``old`` however the file wraps them over lines
    (each space in ``old`` matches any run of whitespace)."""
    path = root / rel
    pattern = r"\s+".join(re.escape(word) for word in old.split(" "))
    text, count = re.subn(pattern, lambda _: new, path.read_text(encoding="utf-8"))
    assert count == 1, (rel, old, count)
    _write(path, text)


@pytest.mark.parametrize("rel", _DISCLOSED)
def test_the_disclosure_episode_count_follows_the_results(tree, rel):
    _replace_words(tree, rel, "one dataset, 100 episodes", "one dataset, 99 episodes")
    problems = publish.check(tree)
    assert f"{rel}: claim 'disclosure episodes' says 99, the results say 100" in problems, problems


@pytest.mark.parametrize("rel", _DISCLOSED)
def test_a_missing_disclosure_is_reported_not_skipped(tree, rel):
    _replace_words(tree, rel, "one dataset, 100 episodes", "one dataset")
    problems = publish.check(tree)
    assert any(rel in p and "'disclosure episodes'" in p and "not found" in p for p in problems), problems


def test_the_disclosure_is_registered_on_every_surface_that_carries_it():
    covered = {c.file for c in publish.CLAIMS if c.label == "disclosure episodes"}
    assert covered == set(_DISCLOSED)


_HOME_NOTE = "the row that keeps the needed record in every episode"
_HOME_LABEL = "contexel alone: full recall under both signals, within the budget, no duplicates or bloat"


def test_the_home_page_reading_note_is_registered_and_true():
    assert any(c.file == "site/index.html" and c.label == _HOME_LABEL for c in publish.CLAIMS)
    assert not [p for p in publish.check(ROOT) if _HOME_LABEL in p]


def test_a_reworded_home_page_reading_note_is_reported(tree):
    _replace_words(tree, "site/index.html", _HOME_NOTE,
                   "the row that keeps the needed record in most episodes")
    problems = publish.check(tree)
    assert any("site/index.html" in p and _HOME_LABEL in p and "not found" in p for p in problems), problems


@pytest.mark.parametrize("edit", [
    lambda data: _outcome(data, "contexel").update(recall_weak_pct=99.0),     # not every episode
    lambda data: _outcome(data, "contexel").update(recall_strong_pct=99.0),
    lambda data: _outcome(data, "contexel").update(useful_share_pct=99.0),    # tokens on bloat
    lambda data: _outcome(data, "contexel").update(fill_x=1.01),              # over the budget
    lambda data: _outcome(data, "toolz").update(fill_x=0.9),                  # no longer the only row
], ids=["weak recall", "strong recall", "useful share", "fill", "another row qualifies"])
def test_the_home_page_reading_note_fails_when_the_results_disagree(tree, edit):
    _edit_comparison(tree, edit)
    problems = publish.check(tree)
    assert any("site/index.html" in p and _HOME_LABEL in p and "not true" in p for p in problems), problems


# --- the re-audit's corrections stay corrected (docs/reviews/benchmark-claims-reaudit.md) ------
def _published_words(rel):
    """The file's text with its line breaks and runs of spaces folded, so a phrase is found
    however the file wraps it."""
    return " ".join((ROOT / rel).read_text(encoding="utf-8").split())


_PROSE = ("README.md", "README_PYPI.md", "site/index.html", "site/benchmarks.html",
          "benchmarks/COMPARISON.md")


@pytest.mark.parametrize("rel", _PROSE)
def test_no_published_text_offers_a_deprecated_class_or_a_shipped_approach(rel):
    text = _published_words(rel)
    # R1: ChatMemoryBuffer is deprecated in llama-index-core 0.14.23 (its class docstring says
    # to use llama_index.core.memory.Memory); it is named, if at all, as the deprecated one
    assert text.count("ChatMemoryBuffer") == text.count("the deprecated `ChatMemoryBuffer`") + text.count(
        "the deprecated <code>ChatMemoryBuffer</code>"), rel
    assert "on its node types" not in text, rel
    # R11: "code execution with MCP" describes an approach; it is not said to ship
    assert "ship the execution mechanism" not in text and "ship the execution" not in text, rel
    # code review: the full-recall caveat is not attributed to the data without evidence
    assert "the data's property" not in text, rel


# --- re-audit R21: the competitor rows are not graded "poor" ---------------------------------
def test_no_generated_cell_is_styled_poor():
    comparison = _committed()
    for render in (publish.html_glance, publish.html_home_glance):
        assert 'class="poor"' not in render(comparison), render.__name__
    for row in publish.glance(comparison):
        for metric in ("ops", "recall", "fill", "useful", "deps"):
            assert publish._tier(metric, row) in ("best", ""), (row["impl"], metric)
    # "best" stays as it was
    rows = {r["impl"]: r for r in publish.glance(comparison)}
    assert publish._tier("useful", rows["contexel"]) == "best"
    assert publish._tier("ops", rows["contexel"]) == "best"


# --- code review minor 5: one "Fill at most 1.00" rule for the tables, the claims and the report
@pytest.mark.parametrize("fill, within", [(1.0, True), (1.004, True), (1.006, False), (0.5, True)])
def test_one_fill_rule_for_highlighting_claims_and_the_report(fill, within):
    assert publish.within_budget_on_average is competitors.within_budget_on_average
    assert publish.within_budget_on_average(fill) is within
    row = {**{r["impl"]: r for r in publish.glance(_committed())}["contexel"], "fill": fill}
    assert (publish._tier("recall", row) == "best") is within
    assert publish._clean_full_recall(row) is within


# --- re-audit R10: the measured versions are stated and tied to the results -----------------
_VERSIONED = ("README.md", "README_PYPI.md", "site/index.html", "site/benchmarks.html")


def test_the_measured_versions_are_registered_on_every_comparison_surface_and_true():
    covered = {c.file for c in publish.CLAIMS if c.label == "measured versions"}
    assert covered == set(_VERSIONED)
    assert not [p for p in publish.check(ROOT) if "measured versions" in p]
    for rel in _VERSIONED:
        assert ("measured with toolz 1.1.0, langchain-core 1.4.9, llama-index-core 0.14.23; newer "
                "releases are not measured") in _published_words(rel), rel


@pytest.mark.parametrize("rel", _VERSIONED)
def test_a_measured_version_that_differs_from_the_results_is_reported(tree, rel):
    _edit_comparison(tree, lambda data: data["environment"]["libraries"].__setitem__("toolz", "1.2.0"))
    problems = publish.check(tree)
    assert any(p.startswith(f"{rel}: claim 'measured versions'") and "toolz 1.2.0" in p
               for p in problems), problems


@pytest.mark.parametrize("rel", _VERSIONED)
def test_a_missing_versions_sentence_is_reported(tree, rel):
    _replace_words(tree, rel, "newer releases are not measured", "newer releases exist")
    problems = publish.check(tree)
    assert any(rel in p and "'measured versions'" in p and "not found" in p for p in problems), problems


# --- re-audit R18: the sample size, registered where the recall comparison is introduced ------
_SAMPLED = ("README.md", "README_PYPI.md", "site/index.html", "site/benchmarks.html")


@pytest.mark.parametrize("rel", _SAMPLED)
def test_the_sample_size_sentence_follows_the_results(tree, rel):
    assert "100 episodes and one episode seed: a gap of a few points is a few episodes" in _published_words(rel)
    _replace_words(tree, rel, "100 episodes and one episode seed", "99 episodes and one episode seed")
    problems = publish.check(tree)
    assert f"{rel}: claim 'sample size' says 99, the results say 100" in problems, problems


# --- re-audit R13: what 0/6 means for the hand-written rows -----------------------------------
_ZERO_EXPLAINED = ("README.md", "README_PYPI.md", "site/benchmarks.html")


def test_the_zero_of_six_sentences_are_registered_and_true():
    for label in ("hand-written rows: no library steps", "no library performs more than two"):
        assert {c.file for c in publish.CLAIMS if c.label == label} == set(_ZERO_EXPLAINED), label
    assert not [p for p in publish.check(ROOT) if "library steps" in p or "more than two" in p]


def _toolz_does_rank(data):
    row = next(o for o in data["operations"] if o["impl"] == "toolz")
    row["native"].append("rank")
    row["missing"].remove("rank")


def test_a_library_with_three_native_operations_breaks_the_more_than_two_claim(tree):
    _edit_comparison(tree, _toolz_does_rank)
    problems = publish.check(tree)
    for rel in _ZERO_EXPLAINED:
        assert any(rel in p and "no library performs more than two" in p and "not true" in p
                   for p in problems), (rel, problems)


def test_a_hand_written_row_with_a_library_step_breaks_the_zero_of_six_claim(tree):
    def edit(data):
        row = next(o for o in data["operations"] if o["impl"] == "hand-written")
        row["native"].append("select")
        row["glue"].remove("select")

    _edit_comparison(tree, edit)
    problems = publish.check(tree)
    for rel in _ZERO_EXPLAINED:
        assert any(rel in p and "hand-written rows: no library steps" in p and "not true" in p
                   for p in problems), (rel, problems)


def test_the_pypi_operations_sentence_no_longer_reads_as_if_the_baseline_did_nothing():
    text = _published_words("README_PYPI.md")
    assert "no other compared row does" not in text
    assert "contexel performs all six operations with its own stages" in text


# --- re-audit R7: the home page's reading note says the estimator counts the budget -----------
def test_the_home_page_reading_note_says_how_the_budget_is_counted(tree):
    assert ("stays within the budget on average as the estimator counts it (Fill at most 1.00)"
            in _published_words("site/index.html"))
    _replace_words(tree, "site/index.html", "on average as the estimator counts it (Fill",
                   "on average (Fill")
    problems = publish.check(tree)
    assert any("site/index.html" in p and _HOME_LABEL in p and "not found" in p for p in problems), problems
