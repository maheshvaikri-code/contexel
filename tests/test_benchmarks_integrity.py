"""AC 26: every published benchmark number equals the generated results, and a
number that does not is reported. The tests that exercise a competitor library skip
when it is not installed."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
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
    ("recall and 100% budget compliance", "recall and 99% budget compliance", "term-overlap baseline compliance"),
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
    "12 " + chr(0xB5) + "s", "12 " + chr(0x3BC) + "s", "12 &micro;s", "12 us", "12 US", "12ns",
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
    "a 12-step plan",
])
def test_words_that_start_like_a_unit_are_not_reported(tree, written):
    _replace(tree, "README.md", _ANCHOR, f"Both are noise ({written}) next to a")
    assert publish.check(tree) == [], written


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
}


@pytest.mark.parametrize("name", sorted(_ADVERSARIAL))
def test_the_check_runs_in_linear_time_on_adversarial_text(tree, name):
    # the earlier patterns backtracked quadratically: seconds to minutes on these
    path = tree / "README.md"
    _write(path, path.read_text(encoding="utf-8") + "\n" + _ADVERSARIAL[name] + "\n")
    start = time.perf_counter()
    publish.check(tree)
    assert time.perf_counter() - start < 2.0, name


def test_a_published_file_larger_than_two_megabytes_is_refused_not_scanned(tree):
    path = tree / "README.md"
    _write(path, path.read_text(encoding="utf-8") + "x" * publish.MAX_PUBLISHED_BYTES)
    problems = publish.check(tree)
    assert any("README.md" in p and "larger than" in p for p in problems), problems


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


def test_write_refuses_a_symbolic_link(tree):
    readme = tree / "README.md"
    with tempfile.TemporaryDirectory() as other:
        target = Path(other) / "README.md"
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


def test_write_refuses_a_file_that_resolves_outside_the_root(tree):
    with tempfile.TemporaryDirectory() as other:
        outside = Path(other) / "site"
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


def test_a_published_file_that_is_not_utf8_is_reported(tree):
    readme = tree / "README.md"
    readme.write_bytes(readme.read_bytes() + b"\xff\xfe broken")
    problems = publish.check(tree)
    assert any("README.md" in p and "not valid UTF-8" in p for p in problems), problems


# --- the qualitative claims read only the columns they name ---------------------------------
def test_the_only_full_marks_claim_reads_only_the_outcome_columns(tree):
    def edit(data):
        row = _outcome(data, "hand-written (term overlap)")
        row["recall_strong_pct"] = row["recall_weak_pct"] = 100.0  # 0/6 native ops, but full outcomes

    _edit_comparison(tree, edit)
    problems = publish.check(tree)
    assert any("site/index.html" in p and "only row with full marks" in p and "not true" in p
               for p in problems), problems
