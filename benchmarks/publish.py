"""Tie the published benchmark numbers to the generated results (brief AC 26).

The README, the PyPI README and the site show benchmark numbers. They used to be
typed by hand, so they could drift from what the benchmark produced. Now:

* the tables are *generated* from ``benchmarks/COMPARISON.json`` and
  ``benchmarks/RESULTS.json`` into marked blocks
  (``<!-- benchmark:NAME:start -->`` ... ``<!-- benchmark:NAME:end -->``) and the
  check compares each block with what the data renders;
* the few prose numbers that remain are registered claims (``CLAIMS``): a pattern
  that must match, with the number it carries compared with the data;
* outside the generated blocks and the registered claims, any number carrying a
  benchmark unit (ms, microseconds, ns, %, x and their spellings), in the text or in an
  attribute a reader sees, and any table cell that is only a number, is reported
  ("unregistered"). Other prose is not checked: a number written without one of
  those units (in seconds, or in words) is not caught;
* ``COMPARISON.md`` and ``RESULTS.md`` must equal the reports rendered from the
  JSON, and the dataset digest the results were produced with must be the digest
  committed in ``benchmarks/dataset.sha256``.

``check(root)`` returns the problems (empty when everything agrees): a missing,
unreadable or oversized file, and results with a missing key, a value of the wrong
type, an empty list or a zero divisor (``MALFORMED``), are problems too, not a
traceback. ``write(root)`` rewrites the generated blocks, ``write_reports(root)``
re-renders the two reports from the committed JSON, and ``write_all(root)`` does both as
one rewrite (none runs a benchmark). Each renders everything first and changes all of its
files or none: malformed results or a refused (read-only, linked, outside) target leave
every file as it was, and no temporary file is left behind.
``tools/check_benchmark_numbers.py`` is the command.

No published table has a Compliance column: the share of contexts that fit the budget was
counted with the same estimator (about four characters per token) the rows cut with, so
every row with a budget step scored 100% by construction. The results keep
``compliance_pct``; Fill (mean estimated tokens / budget) is the column that shows a row
running over the budget.
"""
from __future__ import annotations

import html
import json
import os
import re
import stat
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from . import suites_report
from .competitors import ISSUES, render_report, within_budget_on_average
from .fetch_dataset import DatasetChecksumError, expected_digest

# The four surfaces that publish the comparison (the dataset sentence, the disclosure) ...
RESULT_PAGES = ("README.md", "README_PYPI.md", "site/index.html", "site/benchmarks.html")
# ... and every file the check reads: the other site pages carry timing and token figures
# too (numbers:D3 was a wrong one on site/stages.html), so they are scanned the same way.
FILES = RESULT_PAGES + ("site/stages.html", "site/architecture.html", "site/getting-started.html",
                        "site/contract.html")
MAX_PUBLISHED_BYTES = 2 * 1024 * 1024  # a larger published file is refused, not scanned
_START = r"<!--\s*benchmark:[a-z0-9-]+:start"
# A block's body never contains another start marker (tempered), so an unclosed start
# marker costs one scan to the next marker, not to the end of the file.
BLOCK = re.compile(
    r"<!--\s*benchmark:(?P<name>[a-z0-9-]+):start\s*-->(?P<body>(?:(?!" + _START + r").)*?)"
    r"<!--\s*benchmark:(?P=name):end\s*-->", re.S)
MARKER = re.compile(r"<!--\s*benchmark:[a-z0-9-]+:(?:start|end)\s*-->")
MINUS = chr(0x2212)
TIMES = chr(0xD7)
DIVIDE = chr(0xF7)
DASH = chr(0x2014)
# The column headers that say what they count: the native operations are counted over the
# step lists benchmarks/competitors.py chose; Fill is measured with the default estimator;
# the dependency count is the installed transitive closure.
OPS_HEADER = "Native ops (in this wiring)"
FILL_HEADER = f"Fill {TIMES} (estimated tokens {DIVIDE} budget)"
DEPS_HEADER = "Transitive deps"


# --------------------------------------------------------------------------- #
# Formatting: one definition, used to generate and to check
# --------------------------------------------------------------------------- #
def _n0(x: float) -> str:
    return f"{round(x):,}"


def _g1(x: float) -> str:
    return f"{round(x, 1):g}"


def _tier(metric: str, row: Dict[str, Any]) -> str:
    """'best' for a full-marks cell, '' otherwise. No cell is styled as a failing one: the
    outcome columns measure the wirings this benchmark chose, not the libraries at their own
    jobs (re-audit R21). Recall is not 'best' on a row whose contexts run over the budget
    (Fill above 1.00 as rendered): keeping the record by emitting many times the budget is
    not the best result."""
    if metric == "ops":
        return "best" if row["native"] == row["total"] else ""
    if metric == "recall":
        full = row["rs"] == 100 and row["rw"] == 100
        return "best" if full and within_budget_on_average(row["fill"]) else ""
    if metric == "useful":
        return "best" if row["useful"] == 100 else ""
    if metric == "deps":
        return "best" if row["deps"] == 0 else ""
    return ""


def glance(comparison: Dict[str, Any]) -> List[Dict[str, Any]]:
    task = {r["impl"]: r for r in comparison["task"]}
    foot = {f["library"]: f for f in comparison["footprint"]}
    ops = {o["impl"]: o for o in comparison["operations"]}
    rows = []
    for o in comparison["outcomes"]:
        name = o["impl"]
        t, f, op = task.get(name), foot.get(name), ops[name]
        rows.append({
            "impl": name,
            "native": len(op["native"]),
            "total": len(op["native"]) + len(op["glue"]) + len(op["missing"]),
            "ms": t["ms"] if t and t["ms"] is not None else None,
            "ms_ep": o["ms_per_episode"],
            "rs": o["recall_strong_pct"], "rw": o["recall_weak_pct"],
            # not rendered (no published table has a Compliance column); two claims read it
            "compliance": o["compliance_pct"], "fill": o["fill_x"],
            "useful": o["useful_share_pct"],
            "import_ms": f["import_ms"] if f else None,
            "deps": f["transitive_deps"] if f else None,
        })
    return rows


def _cells(row: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """(metric, text, tier) for every column after the name."""
    absent = DASH
    return [
        ("ops", f"{row['native']}/{row['total']}", _tier("ops", row)),
        ("ms", _n0(row["ms"]) if row["ms"] is not None else absent, ""),
        ("ms_ep", f"{row['ms_ep']:.1f}", ""),
        ("recall", f"{row['rs']:.0f} / {row['rw']:.0f}", _tier("recall", row)),
        ("fill", f"{row['fill']:.2f}", _tier("fill", row)),
        ("useful", _g1(row["useful"]), _tier("useful", row)),
        ("import_ms", _n0(row["import_ms"]) if row["import_ms"] is not None else absent, ""),
        ("deps", str(row["deps"]) if row["deps"] is not None else absent, _tier("deps", row)),
    ]


def _k(comparison: Dict[str, Any]) -> str:
    return f"{comparison['dataset']['records'] // 1000}k"


def _md(text: str) -> str:
    """A value from the results made safe for a Markdown table cell: a ``|`` cannot
    split the row and no markup (a ``<script>``, a block marker) can be injected."""
    return text.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


def md_glance(comparison: Dict[str, Any]) -> str:
    head = ["Implementation", OPS_HEADER, f"ms @{_k(comparison)}", "ms/episode",
            "Recall % (strong / weak)", FILL_HEADER, "Useful %", "Import ms", DEPS_HEADER]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for row in glance(comparison):
        name = f"**{_md(row['impl'])}**" if row["impl"] == "contexel" else _md(row["impl"])
        cells = [f"**{_md(t)}**" if tier == "best" else _md(t) for _, t, tier in _cells(row)]
        lines.append("| " + " | ".join([name] + cells) + " |")
    return "\n".join(lines)


def _td(text: str, tier: str) -> str:
    return f'<td class="{tier}">{html.escape(text)}</td>' if tier else f"<td>{html.escape(text)}</td>"


def html_glance(comparison: Dict[str, Any]) -> str:
    head = ["Implementation", OPS_HEADER, f"ms @{_k(comparison)}", "ms/episode",
            "Recall (strong/weak)", FILL_HEADER, "Useful", "Import ms", DEPS_HEADER]
    lines = ['<div class="scroll">', "<table>",
             "<tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"]
    for row in glance(comparison):
        name = html.escape(row["impl"])
        first = f"<td><strong>{name}</strong></td>" if row["impl"] == "contexel" else f"<td>{name}</td>"
        cells = []
        for metric, text, tier in _cells(row):
            if metric in ("recall", "useful"):
                text = text.replace(" / ", "% / ") + "%"
            elif metric == "fill":
                text = f"{text}{TIMES}"
            cells.append(_td(text, tier))
        lines.append("<tr>" + first + "".join(cells) + "</tr>")
    lines += ["</table>", "</div>"]
    return "\n".join(lines)


def html_home_glance(comparison: Dict[str, Any]) -> str:
    """The home page's shorter table."""
    head = ["Implementation", OPS_HEADER, f"ms @{_k(comparison)}",
            "Recall (strong/weak signal)", FILL_HEADER, "Useful tokens", DEPS_HEADER]
    lines = ['<div class="scroll">', "<table>",
             "<tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"]
    for row in glance(comparison):
        name = html.escape(row["impl"])
        first = f"<td><strong>{name}</strong></td>" if row["impl"] == "contexel" else f"<td>{name}</td>"
        by = {m: (t, tier) for m, t, tier in _cells(row)}
        lines.append("<tr>" + first + _td(*by["ops"]) + _td(*by["ms"])
                     + _td(by["recall"][0].replace(" / ", "% / ") + "%", by["recall"][1])
                     + _td(by["fill"][0] + TIMES, by["fill"][1])
                     + _td(by["useful"][0] + "%", by["useful"][1])
                     + _td(*by["deps"]) + "</tr>")
    lines += ["</table>", "</div>"]
    return "\n".join(lines)


def md_inflected(comparison: Dict[str, Any]) -> str:
    head = ["Shaper", "Recall % (original terms)", "Recall % (inflected terms)"]
    lines = ["| " + " | ".join(head) + " |", "|---|---|---|"]
    for r in comparison["inflected"]["rows"]:
        lines.append(f"| {_md(r['shaper'])} | {r['recall_original_pct']:.0f} | "
                     f"{r['recall_inflected_pct']:.0f} |")
    return "\n".join(lines)


def html_inflected(comparison: Dict[str, Any]) -> str:
    lines = ['<div class="scroll">', "<table>",
             "<tr><th>Shaper</th><th>Recall (original terms)</th><th>Recall (inflected terms)</th></tr>"]
    for r in comparison["inflected"]["rows"]:
        lines.append(f"<tr><td>{html.escape(r['shaper'])}</td>"
                     f"<td>{r['recall_original_pct']:.0f}%</td>"
                     f"<td>{r['recall_inflected_pct']:.0f}%</td></tr>")
    lines += ["</table>", "</div>"]
    return "\n".join(lines)


def suite1_rows(suites: Dict[str, Any]) -> List[Tuple[str, str]]:
    det = suites_report.determinism_rows(suites["determinism"])
    passed = sum(1 for r in det if r["result"] == "PASS")
    trim = suites["budget"]["trim"]
    top = max(r["budget"] for r in trim)
    tik = next(r for r in trim if r["budget"] == top and r["shaped_with"] == "tiktoken")
    over = max((r["actual_tokens"] - r["budget"]) / r["budget"] * 100
               for r in trim if r["shaped_with"] == "heuristic")
    cut = {r["shaped_with"]: r for r in suites["budget"]["truncate"]}
    stages = {(r["n"], r["stage"]): r for r in suites["speed"]["stages"]}
    biggest = max(r["n"] for r in suites["speed"]["stages"])
    full, sel, hand = (stages[(biggest, s)] for s in ("full contract", "select", "hand-written select"))
    tr = suites["speed"]["trace"]
    acc = "; ".join(
        f"{r['sample']} {MINUS if r['error_pct'] < 0 else '+'}{abs(r['error_pct']):.1f}%"
        for r in suites["accuracy"])
    return [
        ("Determinism", f"{passed}/{len(det)} checks PASS; shaped-output hash prefix "
                        f"{suites['determinism']['hash_prefix']}"),
        ("Budget tightness (tiktoken-shaped)",
         f"{tik['actual_tokens']:,} of {top:,} tokens at the largest budget"),
        ("Budget tightness (heuristic-shaped)",
         f"worst overshoot {over:+.1f}% of the budget, measured with tiktoken"),
        ("truncate_field cap",
         f"worst clipped field {cut['heuristic']['worst_field_tokens']} tokens (heuristic) and "
         f"{cut['tiktoken']['worst_field_tokens']} tokens (tiktoken) for a cap of "
         f"{cut['tiktoken']['cap']}"),
        ("Speed, full contract",
         f"{full['records_per_sec']:,.0f} records/s ({full['ms']:,.0f} ms for {biggest:,} records)"),
        ("Speed, select vs hand-written",
         f"{sel['ms']:.1f} ms vs {hand['ms']:.1f} ms for {biggest:,} records"),
        ("Tracing overhead",
         f"{tr['off_ms']:.1f} ms inactive vs {tr['on_ms']:.1f} ms active ({tr['ratio']:.2f}x) "
         f"over 10,000 records"),
        ("Default tokenizer error (heuristic vs tiktoken)", acc),
    ]


def html_suite1(suites: Dict[str, Any]) -> str:
    lines = ['<div class="scroll">', "<table>", "<tr><th>Check</th><th>Measured</th></tr>"]
    for label, text in suite1_rows(suites):
        lines.append(f"<tr><td>{html.escape(label)}</td><td>{html.escape(text)}</td></tr>")
    lines += ["</table>", "</div>"]
    return "\n".join(lines)


def expected_blocks(comparison: Dict[str, Any], suites: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    return {
        "README.md": {"glance": md_glance(comparison), "inflected": md_inflected(comparison)},
        "site/index.html": {"glance": html_home_glance(comparison)},
        "site/benchmarks.html": {
            "glance": html_glance(comparison),
            "inflected": html_inflected(comparison),
            "suite1": html_suite1(suites),
        },
    }


# --------------------------------------------------------------------------- #
# Registered prose claims
# --------------------------------------------------------------------------- #
class Claim(NamedTuple):
    file: str
    label: str
    pattern: str                                   # one capture group: the number as written
    check: Callable[[str, Dict[str, Any], Dict[str, Any]], Optional[str]]


def _equals(expected: Callable[[Dict[str, Any], Dict[str, Any]], str]) -> Callable[..., Optional[str]]:
    def check(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
        want = expected(comparison, suites)
        return None if found == want else f"says {found}, the results say {want}"
    return check


def _import_about(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
    """"about N ms": the measured import time is within 25% of N (it varies run to run)."""
    measured = next(f["import_ms"] for f in comparison["footprint"] if f["library"] == "contexel")
    stated = int(found)
    if abs(measured - stated) <= 0.25 * stated:
        return None
    return f"says about {stated} ms, contexel's import measured {measured:.1f} ms"


def _contexel(c: Dict[str, Any], key: str) -> float:
    return next(r for r in c["outcomes"] if r["impl"] == "contexel")[key]


def _metric(key: str, name: str) -> Callable[..., Optional[str]]:
    """A prose percentage that must equal one of contexel's outcome metrics."""
    def check(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
        want = _contexel(comparison, key)
        return None if float(found) == round(want) else f"says {found}% {name}, the results say {want:.1f}%"
    return check


def _both_recalls(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
    strong, weak = _contexel(comparison, "recall_strong_pct"), _contexel(comparison, "recall_weak_pct")
    if float(found) == round(strong) == round(weak):
        return None
    return f"says {found}% under both signals, the results say {strong:.1f}% and {weak:.1f}%"


def _deps(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
    want = next(f["transitive_deps"] for f in comparison["footprint"] if f["library"] == "contexel")
    return None if int(found) == want else f"says {found} dependencies, the results say {want}"


def _json_error(comparison: Dict[str, Any], suites: Dict[str, Any]) -> str:
    row = next(r for r in suites["accuracy"] if r["sample"].startswith("json"))
    return f"{abs(round(row['error_pct']))}"


def _claim_is(label: str, truth: Callable[[Dict[str, Any], Dict[str, Any]], bool]) -> Callable[..., Optional[str]]:
    """A qualitative sentence that must be true of the results."""
    def check(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
        return None if truth(comparison, suites) else f"is not true of the results: {label}"
    return check


def _rows(c: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {r["impl"]: r for r in glance(c)}


def _only_full_native(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    rows = _rows(c)
    return rows["contexel"]["native"] == rows["contexel"]["total"] == SIX_OPERATIONS and all(
        r["native"] < r["total"] for n, r in rows.items() if n != "contexel")


def _two_slowest_compliant(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    """The two budget-compliant rows with the highest ms/episode are contexel and the
    hand-written term-overlap scorer, in either order (their order is run to run noise)."""
    compliant = sorted((r for r in glance(c) if r["compliance"] == 100),
                       key=lambda r: r["ms_ep"], reverse=True)
    return {r["impl"] for r in compliant[:2]} == {"contexel", "hand-written (term overlap)"}


def _same_recall(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    return _contexel(c, "recall_strong_pct") == _contexel(c, "recall_weak_pct")


def _langchain_bloat(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    r = _rows(c)["langchain-core"]
    return r["compliance"] == 100 and r["useful"] < 100


def _inflection_drop(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    rows = {r["shaper"]: r for r in c["inflected"]["rows"]}
    word, stem, scored = rows["contexel"], rows["contexel (match=stem)"], rows["hand-written (term overlap)"]
    return (word["recall_original_pct"] - word["recall_inflected_pct"] >= COLLAPSE_POINTS
            and scored["recall_original_pct"] - scored["recall_inflected_pct"] >= COLLAPSE_POINTS
            and stem["recall_inflected_pct"] > word["recall_inflected_pct"]
            and stem["recall_original_pct"] - stem["recall_inflected_pct"] <= RECOVER_POINTS)


def _inflected_value(shaper: str, key: str, name: str) -> Callable[..., Optional[str]]:
    """A prose percentage that must equal one cell of the inflected-episodes table."""
    def check(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
        want = next(r for r in comparison["inflected"]["rows"] if r["shaper"] == shaper)[key]
        return None if float(found) == round(want) else f"says {found}% {name}, the results say {want:.1f}%"
    return check


def _scored_value(key: str, name: str) -> Callable[..., Optional[str]]:
    """A prose percentage that must equal the hand-written term-overlap row's outcome metric
    (for recall, under both signals)."""
    keys = ("recall_strong_pct", "recall_weak_pct") if key == "recall" else (key,)

    def check(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
        row = next(r for r in comparison["outcomes"] if r["impl"] == "hand-written (term overlap)")
        if all(float(found) == round(row[k]) for k in keys):
            return None
        return f"says {found}% {name}, the results say " + " and ".join(f"{row[k]:.1f}%" for k in keys)
    return check


def _control_untouched(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    row = next(r for r in c["inflected"]["rows"] if r["shaper"] == "hand-written")
    return row["recall_original_pct"] == row["recall_inflected_pct"]


def _json_underestimates(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    return next(r for r in s["accuracy"] if r["sample"].startswith("json"))["error_pct"] < 0


def _clean_full_recall(r: Dict[str, Any]) -> bool:
    """The record in every episode under both signals, within the budget on average (Fill at
    most 1.00 as rendered) and no tokens on duplicates or bloat (Useful 100%)."""
    return (r["rs"] == 100 and r["rw"] == 100 and within_budget_on_average(r["fill"])
            and r["useful"] == 100)


def _only_clean_full_recall(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    """contexel is "the row that" keeps the record in every episode, stays within the budget
    and spends nothing on duplicates or bloat: it does all three and no other row does."""
    rows = _rows(c)
    return _clean_full_recall(rows["contexel"]) and not any(
        _clean_full_recall(r) for n, r in rows.items() if n != "contexel")


def _hand_written_in_plain_code(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    """The hand-written rows run no library step (their 0/6 is zero by definition), the
    term-overlap one does all six operations in glue and the trusting one all but rescore."""
    ops = {o["impl"]: o for o in c["operations"]}
    hand, scored = ops["hand-written"], ops["hand-written (term overlap)"]
    return (not hand["native"] and not scored["native"] and hand["missing"] == ["rescore"]
            and len(scored["glue"]) == SIX_OPERATIONS and not scored["missing"])


def _libraries_at_most_two(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    """No compared library (a row that is neither contexel nor hand-written) performs more
    than two of the operations natively in this wiring."""
    return all(r["native"] <= LIBRARY_NATIVE_AT_MOST for n, r in _rows(c).items()
               if n != "contexel" and not n.startswith("hand-written"))


def _versions(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
    """"measured with toolz X, langchain-core Y, llama-index-core Z": each version is the one
    the results record in ``environment.libraries``."""
    libs = comparison["environment"]["libraries"]
    want = ", ".join(f"{name} {libs[name]}" for name in ("toolz", "langchain-core", "llama-index-core"))
    said = " ".join(found.split())
    return None if said == want else f"says {said}, the results say {want}"


SIX_OPERATIONS = 6     # the PyPI README says "all six operations": the total must be six
LIBRARY_NATIVE_AT_MOST = 2  # "no library performs more than two"
COLLAPSE_POINTS = 30  # "collapses": recall falls by at least this many percentage points
RECOVER_POINTS = 5     # "recovers": the stem row's inflected recall is within this of its original

# One whitespace run before the optional separator and one after it, never two runs that
# can share the same spaces ("split" followed by a long run of spaces stays linear).
ROWS = r"split\s*(?:(?:\(|" + DASH + r"|-|&mdash;)\s*)?([\d,]+)\s+(?:functions|real)"
# (?<![\d,]): a capture starts only where a number starts, never inside a run of digits
# and commas, so a long run costs one scan instead of one per position (linear time).
RECORDS = r"(?<![\d,])([\d,]+)\s+(?:real\s+)?search-tool\s+records"
EPISODES = r"(?<![\d,])([\d,]+)\s+ground-truth\s+episodes"
BUDGET = r"(?<![\d,])([\d,]+)-token\s+(?:context|budget)"
# The whole disclosure sentence: the author, the episode count (the capture) and the issues
# link, as a Markdown link or an HTML anchor.
DISCLOSURE = (r"This\s+benchmark\s+was\s+written\s+by\s+contexel's\s+author\.\s+The\s+comparison"
              r"\s+wirings\s+are\s+our\s+best\s+effort,\s+one\s+dataset,\s+([\d,]+)\s+episodes;"
              r"\s+corrections\s+from\s+the\s+maintainers\s+of\s+the\s+compared\s+libraries\s+are"
              r"\s+welcome\s+\((?:\[open\s+an\s+issue\]\(|<a\s+href=\")" + re.escape(ISSUES) + r"[)\"]")
# "measured with toolz 1.1.0, langchain-core 1.4.9, llama-index-core 0.14.23; newer releases
# are not measured": the three versions are one capture, compared with environment.libraries
VERSIONS = (r"measured\s+with\s+(toolz\s+[^\s,;]+,\s+langchain-core\s+[^\s,;]+,\s+"
            r"llama-index-core\s+[^\s,;]+);\s+newer\s+releases\s+are\s+not\s+measured")
# "100 episodes and one episode seed: a gap of a few points is a few episodes" (true of 100)
SAMPLE = (r"(?<![\d,])([\d,]+)\s+episodes\s+and\s+one\s+episode\s+seed:\s+a\s+gap\s+of\s+a\s+few"
          r"\s+points\s+is\s+a\s+few\s+episodes")

CLAIMS: List[Claim] = []
for _file in RESULT_PAGES:  # the dataset sentence: the other pages do not describe the dataset
    CLAIMS += [
        Claim(_file, "tool-output records", RECORDS,
              _equals(lambda c, s: f"{c['dataset']['records']:,}")),
        Claim(_file, "episodes", EPISODES,
              _equals(lambda c, s: f"{c['settings']['episodes']:,}")),
    ]
for _file in ("README.md", "README_PYPI.md", "site/benchmarks.html"):
    CLAIMS.append(Claim(_file, "dataset rows", ROWS, _equals(lambda c, s: f"{c['dataset']['rows']:,}")))
for _file in ("README.md", "README_PYPI.md", "site/index.html"):
    CLAIMS.append(Claim(_file, "evaluation budget", BUDGET,
                        _equals(lambda c, s: f"{c['settings']['eval_budget']:,}")))
for _file in RESULT_PAGES:  # the authorship disclosure (ruling P1-5, QA G2), on every surface
    CLAIMS.append(Claim(_file, "authorship disclosure", DISCLOSURE,
                        _equals(lambda c, s: f"{c['settings']['episodes']:,}")))
for _file in RESULT_PAGES:  # the measured versions (re-audit R10) and the sample (R18)
    CLAIMS += [
        Claim(_file, "measured versions", VERSIONS, _versions),
        Claim(_file, "sample size", SAMPLE, _equals(lambda c, s: f"{c['settings']['episodes']:,}")),
    ]
CLAIMS += [
    Claim("site/benchmarks.html", "evaluation budget", r"Budget:\s*([\d,]+)\s+tokens",
          _equals(lambda c, s: f"{c['settings']['eval_budget']:,}")),
    Claim("README.md", "JSON tokenizer error", MINUS + r"(\d+)%\s+on\s+JSON-heavy",
          _equals(_json_error)),
    Claim("README_PYPI.md", "recall", r"needed\s+record\s+in\s+(\d+)%\s+of\s+them", _both_recalls),
    Claim("README_PYPI.md", "useful share", r"spends\s+(\d+)%\s+of\s+context\s+tokens",
          _metric("useful_share_pct", "useful share")),
    Claim("README_PYPI.md", "dependencies", r"at\s+(\d+)\s+dependencies", _deps),
    Claim("README_PYPI.md", "import time", r"import\s+of\s+about\s+(\d+)\s+ms", _import_about),
    Claim("site/index.html", "import time", r"about\s+(\d+)(?:&nbsp;|\s)+ms\s+import", _import_about),
    Claim("README_PYPI.md", "term-overlap baseline recall",
          r"term-overlap\s+baseline\s+\(a\s+hand-written\s+scorer\s+in\s+place\s+of\s+`rescore`\)\s+reaches\s+(\d+)%\s+recall",
          _scored_value("recall", "recall")),
    Claim("README_PYPI.md", "default matching, original terms", r"finds\s+the\s+record\s+in\s+(\d+)%\s+of\s+those",
          _inflected_value("contexel", "recall_original_pct", "with the original terms")),
    Claim("README_PYPI.md", "default matching, inflected terms", r"own\s+words\s+and\s+in\s+(\d+)%\s+with\s+inflections",
          _inflected_value("contexel", "recall_inflected_pct", "with the inflected terms")),
    Claim("README_PYPI.md", "stem matching, inflected terms", r"`match=\"stem\"`\s+finds\s+it\s+in\s+(\d+)%",
          _inflected_value("contexel (match=stem)", "recall_inflected_pct", "with the inflected terms")),
]


def _sentence(file: str, pattern: str, label: str,
              truth: Callable[[Dict[str, Any], Dict[str, Any]], bool]) -> Claim:
    return Claim(file, label, "(" + pattern + ")", _claim_is(label, truth))


_SLOWEST = r"two\s+slowest\s+budget-compliant\s+rows"
_SLOWEST_LABEL = "two slowest budget-compliant rows"
_DROP = r"Exact-word\s+matching\s+\(the\s+default\)\s+collapses\s+on\s+inflected\s+queries"
CLAIMS += [
    _sentence("README_PYPI.md", r"contexel\s+performs\s+all\s+six\s+operations\s+with\s+its\s+own\s+stages",
              "only row with every operation native", _only_full_native),
    _sentence("README_PYPI.md", r"one\s+corpus\s+and\s+one\s+task", "scope: one corpus, one task",
              lambda c, s: bool(c["dataset"]["sha256"])),
    _sentence("README_PYPI.md", r"the\s+default\s+exact-word\s+matching",
              "word mode drops on inflected queries and stem recovers", _inflection_drop),
    _sentence("README_PYPI.md", r"On\s+a\s+second\s+set\s+of\s+episodes",
              "the inflected figures come from a second set of episodes",
              lambda c, s: c["inflected"]["episodes"] > 0 and bool(c["inflected"]["rows"])),
    _sentence("README_PYPI.md", r"not\s+how\s+many\s+English\s+inflections\s+the\s+stemmer\s+covers",
              "the stem figure is not a coverage figure", lambda c, s: bool(c["inflected"]["rows"])),
    _sentence("README_PYPI.md", _SLOWEST, _SLOWEST_LABEL, _two_slowest_compliant),
    _sentence("site/index.html", _SLOWEST, _SLOWEST_LABEL, _two_slowest_compliant),
    _sentence("README.md", _SLOWEST, _SLOWEST_LABEL, _two_slowest_compliant),
    _sentence("site/benchmarks.html", _SLOWEST, _SLOWEST_LABEL, _two_slowest_compliant),
    _sentence("README.md", r"contexel's\s+recall\s+is\s+the\s+same\s+under\s+both\s+signals",
              "same recall under both signals", _same_recall),
    _sentence("site/benchmarks.html", r"so\s+its\s+two\s+columns\s+read\s+the\s+same",
              "same recall under both signals", _same_recall),
    _sentence("README.md", r"langchain-core\s+honors\s+the\s+budget", "langchain-core: compliant but bloated",
              _langchain_bloat),
    _sentence("site/benchmarks.html", r"langchain-core\s+holds\s+the\s+budget",
              "langchain-core: compliant but bloated", _langchain_bloat),
    _sentence("README.md", _DROP, "word mode drops on inflected queries and stem recovers", _inflection_drop),
    _sentence("site/benchmarks.html", _DROP, "word mode drops on inflected queries and stem recovers",
              _inflection_drop),
    _sentence("README.md", r"inflection\s+cannot\s+touch\s+it", "the trusting row is a control",
              _control_untouched),
    _sentence("site/benchmarks.html", r"inflection\s+cannot\s+touch\s+it", "the trusting row is a control",
              _control_untouched),
    _sentence("site/benchmarks.html", r"under-estimates\s+JSON-heavy\s+records",
              "the default tokenizer under-estimates JSON", _json_underestimates),
    # the home page's reading note (numbers audit section 8, Task 4 review M-4)
    _sentence("site/index.html",
              r"contexel\s+is\s+the\s+row\s+that\s+keeps\s+the\s+needed\s+record\s+in\s+every\s+episode"
              r"\s+under\s+both\s+retrieval\s+signals,\s+stays\s+within\s+the\s+budget\s+on\s+average"
              r"\s+as\s+the\s+estimator\s+counts\s+it\s+\(Fill\s+at\s+most\s+1\.00\)\s+and\s+spends\s+no"
              r"\s+tokens\s+on\s+duplicates\s+or\s+bloat",
              "contexel alone: full recall under both signals, within the budget, no duplicates or bloat",
              _only_clean_full_recall),
]

# What the hand-written rows' 0/6 means, and that no library performs more than two (re-audit
# R13), wherever the 0/6 is explained in prose.
for _file in ("README.md", "README_PYPI.md", "site/benchmarks.html"):
    CLAIMS += [
        _sentence(_file, r"so\s+their\s+0/6\s+counts\s+library\s+steps\s+only",
                  "hand-written rows: no library steps", _hand_written_in_plain_code),
        _sentence(_file, r"no\s+library\s+(?:\(toolz,\s+langchain-core,\s+llama-index-core\)\s+)?performs"
                  r"\s+more\s+than\s+two", "no library performs more than two", _libraries_at_most_two),
    ]

# A number with a benchmark unit, in any case: ms (msec, milliseconds), microseconds (the
# micro sign or the Greek mu followed by s, us, microsecond(s)), ns (nanosecond(s)), a
# percentage (% / percent / per cent), the multiplication sign (whitespace of any kind may sit
# between the number and these), or an ASCII x written straight after the number ("2.95x",
# "10x"; "3 x 4" and "3.x" are not). A bare "s" is deliberately not a unit ("1990s"), and
# neither is "sec" or "seconds": the README's stemmer-throughput prose ("2 seconds per million
# chunks") is not benchmark-section data and is not covered by this check. A number is not one
# when a letter or digit comes right before it ("a12 ms"), but an underscore does not count as
# a letter (Markdown italics: "_12 ms_"). Nor does it start inside a number (right after a
# digit, or after a digit and a comma or dot), but it does start after a comma or dot that
# follows anything else ("fast,12 ms", "...12 ms"). The digits it reads may be separated by
# single commas or dots only, so no start can scan past a run of separators: linear time.
# "us" and "ns" count in lower case only ("50 US states" and "8 NS records" are not
# timings); every other unit is matched in any case.
_END = r"(?![^\W_])"
_MICRO = chr(0xB5) + chr(0x3BC)  # the micro sign and the Greek small letter mu
UNIT_NUMBER = re.compile(
    r"(?<![^\W_])(?<!\d[,.])[+" + MINUS + r"-]?(?:"
    r"\d(?:[,.]?\d)*[,.]?\s*(?:(?:msec|ms|milliseconds?|[" + _MICRO + r"]s|(?-i:us|ns)"
    r"|microseconds?|nanoseconds?|percent|per\s+cent)" + _END + r"|%|" + TIMES + r")"
    r"|\d(?:,?\d)*(?:\.\d+)?x" + _END + r")", re.I)
# A Markdown link target stops at the next "]" too, so an unclosed "](" run stays linear.
URLISH = re.compile(r"https?://\S+|(?:href|src)=\"[^\"]*\"|\]\([^)\]]*\)")
# Attributes whose value is shown to a reader (a tooltip, alt text, the page description, a
# form placeholder) or carried for scripts to show (data-*).
ATTRIBUTE = re.compile(
    r"""(?<![\w-])(?:title|alt|aria-label|content|placeholder|data-[\w-]+)\s*=\s*"""
    r"""(?:"([^"]*)"|'([^']*)')""", re.I)
# A table cell that is only a number: a Markdown row ("| a | 12 |", "| a | 12", "| `~12` |")
# or an HTML cell ("<td>12</td>", "<td><b>12</b></td>"). Tags, backticks, emphasis stars and
# underscores and a leading "~" do not hide it. A cell never spans another cell's start tag
# (tempered), so an unclosed "<td>" costs one scan to the next cell, not to the end.
BARE_NUMBER = re.compile(r"[+" + MINUS + r"-]?\d[\d,]*(?:\.\d+)?%?")
HTML_CELL = re.compile(r"<t[dh]\b[^<>]*>((?:(?!</?t[dh]\b).)*)</t[dh]>", re.I | re.S)
# A tag: it stops at the next "<", so a run of "<" stays linear.
TAG = re.compile(r"<[^<>]+>")
# Characters that render as nothing (zero-width space, non-joiner and joiner, word joiner,
# soft hyphen, byte-order mark): deleted before the scan so they cannot split a number.
INVISIBLE = dict.fromkeys([0x200B, 0x200C, 0x200D, 0x2060, 0x00AD, 0xFEFF])


def _plain(text: str) -> str:
    """Entities decoded, compatibility forms folded (fullwidth digits and percent sign,
    the micro sign), invisible characters deleted, non-breaking spaces made plain."""
    text = unicodedata.normalize("NFKC", html.unescape(text))
    return text.translate(INVISIBLE).replace(chr(0xA0), " ")


def _cell_text(raw: str) -> str:
    text = _plain(TAG.sub("", raw))
    return re.sub(r"[`*_]", "", text).strip().lstrip("~").strip()


def _bare_cells(text: str) -> List[str]:
    """The table cells of ``text`` (outside the generated blocks) that are only a number."""
    raw: List[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            raw += line.strip().strip("|").split("|")
    raw += [m.group(1) for m in HTML_CELL.finditer(text)]
    return [c for c in map(_cell_text, raw) if BARE_NUMBER.fullmatch(c)]


def _visible(outside: str) -> str:
    """What a reader sees of ``outside``, for the scan for unregistered numbers: URLs
    dropped, the values of title/alt/aria-label/content/placeholder/data-* attributes
    kept, tags stripped, entities (&nbsp;, &times;, &#37;) decoded, compatibility forms
    folded (NFKC: fullwidth digits and percent sign, the micro sign), zero-width
    characters and soft hyphens deleted, non-breaking spaces made plain."""
    plain = URLISH.sub(" ", outside)
    attributes = [a or b for a, b in ATTRIBUTE.findall(plain)]
    plain = TAG.sub(" ", plain)
    return _plain(" ".join([plain] + attributes))


# --------------------------------------------------------------------------- #
# The check and the writer
# --------------------------------------------------------------------------- #
# What rendering and comparing malformed results raise: a missing key or index, a value of
# the wrong type (TypeError, AttributeError, ValueError), an empty list searched with next()
# (StopIteration), a zero where a divisor was expected (ArithmeticError).
MALFORMED = (KeyError, TypeError, ValueError, IndexError, AttributeError, StopIteration,
             ArithmeticError)


class PublishError(RuntimeError):
    """``write`` refused a target (a symbolic link, a path outside the root, not a file)."""


def _read(root: Path, rel: str) -> str:
    """The file's text with universal newlines; OSError and UnicodeDecodeError propagate.
    The size is checked before the file is read, so an oversized file is never loaded."""
    path = root / rel
    size = path.stat().st_size
    if size > MAX_PUBLISHED_BYTES:
        raise OSError(f"{size:,} bytes is larger than the {MAX_PUBLISHED_BYTES:,} bytes "
                      "the check reads; refusing to scan it")
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def _text(problems: List[str], root: Path, rel: str) -> Optional[str]:
    """``_read``, with a problem line instead of an exception."""
    try:
        return _read(root, rel)
    except UnicodeDecodeError as exc:
        problems.append(f"{rel}: not valid UTF-8 ({exc})")
    except OSError as exc:
        problems.append(f"{rel}: cannot read it ({exc})")
    return None


def _load(root: Path, rel: str) -> Dict[str, Any]:
    return json.loads(_read(root, rel))


def _malformed(where: str, exc: BaseException) -> str:
    return (f"{where}: cannot be checked, the results are malformed "
            f"(benchmarks/COMPARISON.json or benchmarks/RESULTS.json: {type(exc).__name__}: {exc})")


def _blocks(text: str) -> List[Tuple[str, re.Match]]:
    return [(m.group("name"), m) for m in BLOCK.finditer(text)]


def _blank_group(match: "re.Match[str]") -> str:
    """Replace only the claim's captured number (or sentence) by a marker, so the
    words around it stay available to the claims checked after this one."""
    start, end = match.span(1)
    offset = match.start()
    return match.group(0)[: start - offset] + "#" + match.group(0)[end - offset:]


def check(root: Path) -> List[str]:
    problems: List[str] = []
    try:
        comparison = _load(root, "benchmarks/COMPARISON.json")
        suites = _load(root, "benchmarks/RESULTS.json")
    except (OSError, ValueError) as exc:
        return [f"cannot read the generated results: {exc}"]

    # The hint re-renders from the committed JSON; the benchmark commands would re-measure.
    command = "python tools/check_benchmark_numbers.py --write"
    reports = (
        ("benchmarks/COMPARISON.md", "benchmarks/COMPARISON.json", lambda: render_report(comparison)),
        ("benchmarks/RESULTS.md", "benchmarks/RESULTS.json", lambda: suites_report.render(suites)),
    )
    for rel, source, render in reports:
        report = _text(problems, root, rel)
        if report is None:
            continue
        try:
            rendered = render()
        except MALFORMED as exc:
            problems.append(_malformed(rel, exc))
            continue
        if report != rendered:
            problems.append(f"{rel} is not the report rendered from {source} "
                            f"(regenerate it with {command})")
    try:
        committed = expected_digest(root / "benchmarks" / "dataset.sha256")
    except DatasetChecksumError as exc:
        committed = ""
        problems.append(f"benchmarks/dataset.sha256: {exc}")
    try:
        if committed and comparison["dataset"]["sha256"] != committed:
            problems.append("benchmarks/COMPARISON.json was produced with dataset digest "
                            f"{comparison['dataset']['sha256']}, not the committed {committed}")
    except MALFORMED as exc:
        problems.append(_malformed("benchmarks/dataset.sha256", exc))

    try:
        wanted: Optional[Dict[str, Dict[str, str]]] = expected_blocks(comparison, suites)
    except MALFORMED as exc:
        problems.append(_malformed("the generated blocks", exc))
        wanted = None
    for rel in FILES:
        text = _text(problems, root, rel)
        if text is None:
            continue
        try:
            _check_file(problems, rel, text, wanted, comparison, suites)
        except MALFORMED as exc:
            problems.append(_malformed(rel, exc))
    return problems


def _check_file(problems: List[str], rel: str, text: str, wanted: Optional[Dict[str, Dict[str, str]]],
                comparison: Dict[str, Any], suites: Dict[str, Any]) -> None:
    """The checks of one published file: its blocks, its claims, then the scan."""
    found = _blocks(text)
    names = [n for n, _ in found]
    if wanted is not None:  # None: the blocks could not be rendered (already reported)
        for name, body in wanted.get(rel, {}).items():
            if names.count(name) != 1:
                problems.append(f"{rel}: expected exactly one benchmark:{name} block, found {names.count(name)}")
                continue
            match = next(m for n, m in found if n == name)
            if match.group("body").replace("\r\n", "\n") != "\n" + body + "\n":
                problems.append(f"{rel}: the benchmark:{name} block differs from the generated one "
                                "(run python tools/check_benchmark_numbers.py --write)")
        for name in names:
            if name not in wanted.get(rel, {}):
                problems.append(f"{rel}: unknown benchmark:{name} block")

    outside = BLOCK.sub("", text)
    for stray in MARKER.finditer(outside):
        problems.append(f"{rel}: a benchmark marker without its pair, or inside another block: "
                        f"{stray.group(0)!r}")
    for claim in (c for c in CLAIMS if c.file == rel):
        matches = re.findall(claim.pattern, outside)
        if not matches:
            problems.append(f"{rel}: the registered claim '{claim.label}' was not found "
                            "(reworded? update publish.CLAIMS)")
            continue
        for number in matches:
            bad = claim.check(number, comparison, suites)
            if bad:
                problems.append(f"{rel}: claim '{claim.label}' {bad}")
        outside = re.sub(claim.pattern, _blank_group, outside)
    for hit in UNIT_NUMBER.finditer(_visible(outside)):
        problems.append(f"{rel}: unregistered benchmark number {hit.group(0).strip()!r} "
                        "(put it in a generated block or register it in publish.CLAIMS)")
    for cell in _bare_cells(outside):
        problems.append(f"{rel}: unregistered benchmark number {cell!r} in a table cell "
                        "outside a generated block (generate the table or register the number)")


def _regenerated(text: str, blocks: Dict[str, str]) -> str:
    """``text`` with the body of every known block replaced by its generated one."""
    def replace(match: "re.Match[str]") -> str:
        name = match.group("name")
        if name not in blocks:
            return match.group(0)
        whole = match.group(0)
        start = whole.index("-->") + 3
        end = whole.rindex("<!--")
        return whole[:start] + "\n" + blocks[name] + "\n" + whole[end:]

    return BLOCK.sub(replace, text)


def _target(root: Path, rel: str) -> Path:
    """The file ``write`` may rewrite: a regular file inside ``root``, not a symbolic
    link and not reached through one that leads outside the root (PublishError)."""
    path = root / rel
    if path.is_symlink():
        raise PublishError(f"{rel}: refusing to write through a symbolic link")
    base, resolved = root.resolve(), path.resolve()
    if base not in resolved.parents:
        raise PublishError(f"{rel}: resolves to {resolved}, outside {base}; refusing to write it")
    if not path.is_file():
        raise PublishError(f"{rel}: not a regular file; refusing to write it")
    return path


def _newline(path: Path) -> str:
    """The line ending ``path`` uses now: CRLF when it has any (a Windows checkout with
    autocrlf), LF otherwise. ``write`` keeps it, so a rewrite changes only content."""
    return "\r\n" if b"\r\n" in path.read_bytes() else "\n"


class _Change(NamedTuple):
    rel: str
    path: Path
    text: str


def _plan(root: Path, blocks: bool = True, reports: bool = True) -> List[_Change]:
    """The rewrites asked for (the files whose generated blocks change, then the reports that
    change), rendered in memory with nothing written. Rendering all of them first means
    malformed results (MALFORMED) or a refused target (PublishError) stop the write before
    any file is touched (QA D2)."""
    comparison = _load(root, "benchmarks/COMPARISON.json")
    suites = _load(root, "benchmarks/RESULTS.json")
    wanted_blocks = expected_blocks(comparison, suites) if blocks else {}
    rendered_reports = _reports(comparison, suites) if reports else []
    changes: List[_Change] = []
    for rel, wanted in wanted_blocks.items():
        path = _target(root, rel)
        text = _read(root, rel)
        new = _regenerated(text, wanted)
        if new != text:
            changes.append(_Change(rel, path, new))
    for rel, rendered in rendered_reports:
        path = _target(root, rel)
        if _read(root, rel) != rendered:  # equal line endings aside: left alone
            changes.append(_Change(rel, path, rendered))
    return changes


def _writable(change: _Change) -> None:
    """A read-only target is refused before anything is written (by its mode bits, which
    hold on Windows and for a superuser alike)."""
    if not stat.S_IMODE(change.path.stat().st_mode) & stat.S_IWUSR:
        raise PublishError(f"{change.rel}: the file is read-only; refusing to write it "
                           "(no file was changed)")


def _discard(tmp: str) -> None:
    """Remove a temporary file; one left read-only is made writable first."""
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        return
    except OSError:
        os.chmod(tmp, stat.S_IREAD | stat.S_IWRITE)
        os.unlink(tmp)


def _stage(path: Path, text: str) -> str:
    """Write ``text`` (LF-normalized; written with the line ending ``path`` already uses,
    UTF-8) to a temporary file next to ``path`` and return its name. The temporary file
    keeps its default (writable) mode, so it can always be removed (QA D1)."""
    newline = _newline(path)
    data = text.replace("\r\n", "\n")
    if newline != "\n":
        data = data.replace("\n", newline)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data.encode("utf-8"))
    except BaseException:
        _discard(tmp)
        raise
    return tmp


def _apply(changes: List[_Change]) -> List[str]:
    """Replace every planned file, or none: each target is checked writable and each new text
    staged in a temporary file before the first replace; a replace the system refuses puts
    back the files already replaced. The temporary files never outlive the call. A failure is
    a PublishError that names the file."""
    for change in changes:
        _writable(change)
    staged: List[Tuple[_Change, str, bytes, int]] = []
    replaced: List[Tuple[_Change, bytes, int]] = []
    try:
        for change in changes:
            original = change.path.read_bytes()
            mode = stat.S_IMODE(change.path.stat().st_mode)
            staged.append((change, _stage(change.path, change.text), original, mode))
        for change, tmp, original, mode in staged:
            try:
                os.replace(tmp, str(change.path))
            except OSError as exc:
                raise PublishError(f"{change.rel}: cannot replace it ({exc}); the files already "
                                   "rewritten were restored") from exc
            replaced.append((change, original, mode))
            os.chmod(str(change.path), mode)  # keep the file's permissions
    except BaseException as exc:
        unrestored = []
        for change, original, mode in reversed(replaced):
            try:
                _restore(change.path, original, mode)
            except OSError:
                unrestored.append(change.rel)
        if unrestored:
            raise PublishError(f"could not restore {', '.join(unrestored)} after the write "
                               f"failed: {exc}") from exc
        raise
    finally:
        for _, tmp, _, _ in staged:
            _discard(tmp)
    return [change.rel for change in changes]


def _restore(path: Path, original: bytes, mode: int) -> None:
    """Put back a file's bytes and mode after a later replace failed."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(original)
        os.replace(tmp, str(path))
        os.chmod(str(path), mode)
    finally:
        _discard(tmp)


def write(root: Path) -> List[str]:
    """Rewrite every generated block from the results; return the files changed, all of
    them or none (``_apply``). Raises PublishError for a target it refuses (see ``_target``
    and ``_apply``)."""
    return _apply(_plan(root, reports=False))


def _reports(comparison: Dict[str, Any], suites: Dict[str, Any]) -> List[Tuple[str, str]]:
    """(path, text) of the two reports rendered from the committed results."""
    return [("benchmarks/COMPARISON.md", render_report(comparison)),
            ("benchmarks/RESULTS.md", suites_report.render(suites))]


def write_reports(root: Path) -> List[str]:
    """Re-render ``COMPARISON.md`` and ``RESULTS.md`` from the committed JSON (no benchmark
    runs, so no measurement changes); return the files changed. A report that already equals
    its rendering (line endings aside) is left alone. Raises PublishError like ``write``."""
    return _apply(_plan(root, blocks=False))


def write_all(root: Path) -> Tuple[List[str], List[str]]:
    """``write`` and ``write_reports`` as one all-or-nothing rewrite (what ``--write`` runs):
    return the files whose blocks changed and the reports that changed."""
    blocks, reports = _plan(root, reports=False), _plan(root, blocks=False)
    _apply(blocks + reports)
    return [c.rel for c in blocks], [c.rel for c in reports]
