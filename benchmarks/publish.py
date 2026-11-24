"""Tie the published benchmark numbers to the generated results (brief AC 26).

The README, the PyPI README and the site show benchmark numbers. They used to be
typed by hand, so they could drift from what the benchmark produced. Now:

* the tables are *generated* from ``benchmarks/COMPARISON.json`` and
  ``benchmarks/RESULTS.json`` into marked blocks
  (``<!-- benchmark:NAME:start -->`` ... ``<!-- benchmark:NAME:end -->``) and the
  check compares each block with what the data renders;
* the few prose numbers that remain are registered claims (``CLAIMS``): a pattern
  that must match, with the number it carries compared with the data;
* any other number with a benchmark unit (ms, %, x) found in a published file
  fails the check ("unregistered"), so a hand-typed number cannot slip in;
* ``COMPARISON.md`` and ``RESULTS.md`` must equal the reports rendered from the
  JSON, and the dataset digest the results were produced with must be the digest
  committed in ``benchmarks/dataset.sha256``.

``check(root)`` returns the problems (empty when everything agrees); ``write(root)``
rewrites the generated blocks. ``tools/check_benchmark_numbers.py`` is the command.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from . import suites_report
from .competitors import render_report
from .fetch_dataset import DatasetChecksumError, expected_digest

FILES = ("README.md", "README_PYPI.md", "site/index.html", "site/benchmarks.html")
BLOCK = re.compile(
    r"<!--\s*benchmark:(?P<name>[a-z0-9-]+):start\s*-->(?P<body>.*?)"
    r"<!--\s*benchmark:(?P=name):end\s*-->", re.S)
MINUS = chr(0x2212)
TIMES = chr(0xD7)
DASH = chr(0x2014)


# --------------------------------------------------------------------------- #
# Formatting: one definition, used to generate and to check
# --------------------------------------------------------------------------- #
def _n0(x: float) -> str:
    return f"{round(x):,}"


def _g1(x: float) -> str:
    return f"{round(x, 1):g}"


def _tier(metric: str, row: Dict[str, Any]) -> str:
    """'best' for a full-marks cell, 'poor' for a failing one, '' otherwise."""
    if metric == "ops":
        return "best" if row["native"] == row["total"] else ""
    if metric == "recall":
        if row["rs"] == 100 and row["rw"] == 100:
            return "best"
        return "poor" if min(row["rs"], row["rw"]) < 50 else ""
    if metric == "compliance":
        return "best" if row["compliance"] == 100 else ("poor" if row["compliance"] < 50 else "")
    if metric == "fill":
        return "poor" if row["fill"] > 1 else ""
    if metric == "useful":
        return "best" if row["useful"] == 100 else ("poor" if row["useful"] < 90 else "")
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
        ("compliance", f"{row['compliance']:.0f}", _tier("compliance", row)),
        ("fill", f"{row['fill']:.2f}", _tier("fill", row)),
        ("useful", _g1(row["useful"]), _tier("useful", row)),
        ("import_ms", _n0(row["import_ms"]) if row["import_ms"] is not None else absent, ""),
        ("deps", str(row["deps"]) if row["deps"] is not None else absent, _tier("deps", row)),
    ]


def _k(comparison: Dict[str, Any]) -> str:
    return f"{comparison['dataset']['records'] // 1000}k"


def md_glance(comparison: Dict[str, Any]) -> str:
    head = ["Implementation", "Native ops", f"ms @{_k(comparison)}", "ms/episode",
            "Recall % (strong / weak)", "Compliance %", f"Fill {TIMES}", "Useful %",
            "Import ms", "Deps"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for row in glance(comparison):
        name = f"**{row['impl']}**" if row["impl"] == "contexel" else row["impl"]
        cells = [f"**{t}**" if tier == "best" else t for _, t, tier in _cells(row)]
        lines.append("| " + " | ".join([name] + cells) + " |")
    return "\n".join(lines)


def _td(text: str, tier: str) -> str:
    return f'<td class="{tier}">{html.escape(text)}</td>' if tier else f"<td>{html.escape(text)}</td>"


def html_glance(comparison: Dict[str, Any]) -> str:
    head = ["Implementation", "Native ops", f"ms @{_k(comparison)}", "ms/episode",
            "Recall (strong/weak)", "Compliance", "Fill", "Useful", "Import ms", "Deps"]
    lines = ['<div class="scroll">', "<table>",
             "<tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"]
    for row in glance(comparison):
        name = html.escape(row["impl"])
        first = f"<td><strong>{name}</strong></td>" if row["impl"] == "contexel" else f"<td>{name}</td>"
        cells = []
        for metric, text, tier in _cells(row):
            if metric in ("recall", "compliance", "useful"):
                text = text.replace(" / ", "% / ") + "%"
            elif metric == "fill":
                text = f"{text}{TIMES}"
            cells.append(_td(text, tier))
        lines.append("<tr>" + first + "".join(cells) + "</tr>")
    lines += ["</table>", "</div>"]
    return "\n".join(lines)


def html_home_glance(comparison: Dict[str, Any]) -> str:
    """The home page's shorter table."""
    head = ["Implementation", "Native ops", f"ms @{_k(comparison)}",
            "Recall (strong/weak signal)", "Budget compliance", "Useful tokens", "Deps"]
    lines = ['<div class="scroll">', "<table>",
             "<tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"]
    for row in glance(comparison):
        name = html.escape(row["impl"])
        first = f"<td><strong>{name}</strong></td>" if row["impl"] == "contexel" else f"<td>{name}</td>"
        by = {m: (t, tier) for m, t, tier in _cells(row)}
        over = f" ({row['fill']:.0f}{TIMES} budget)" if row["fill"] > 1 else ""
        lines.append("<tr>" + first + _td(*by["ops"]) + _td(*by["ms"])
                     + _td(by["recall"][0].replace(" / ", "% / ") + "%", by["recall"][1])
                     + _td(by["compliance"][0] + "%" + over, by["compliance"][1])
                     + _td(by["useful"][0] + "%", by["useful"][1])
                     + _td(*by["deps"]) + "</tr>")
    lines += ["</table>", "</div>"]
    return "\n".join(lines)


def md_inflected(comparison: Dict[str, Any]) -> str:
    head = ["Shaper", "Recall % (original terms)", "Recall % (inflected terms)"]
    lines = ["| " + " | ".join(head) + " |", "|---|---|---|"]
    for r in comparison["inflected"]["rows"]:
        lines.append(f"| {r['shaper']} | {r['recall_original_pct']:.0f} | "
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


def _full_marks(r: Dict[str, Any]) -> bool:
    return all(_tier(m, r) == "best" for m in ("ops", "recall", "compliance", "useful"))


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


def _only_contexel_full(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    return [r["impl"] for r in glance(c) if _full_marks(r)] == ["contexel"]


def _same_recall(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    return _contexel(c, "recall_strong_pct") == _contexel(c, "recall_weak_pct")


def _zero_compliance(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    rows = _rows(c)
    return all(rows[n]["rs"] == 100 and rows[n]["compliance"] == 0 for n in ("toolz", "llama-index-core"))


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


SIX_OPERATIONS = 6     # the PyPI README says "all six operations": the total must be six
COLLAPSE_POINTS = 30  # "collapses": recall falls by at least this many percentage points
RECOVER_POINTS = 5     # "recovers": the stem row's inflected recall is within this of its original

ROWS = r"split\s*(?:\(|" + DASH + r"|-|&mdash;)?\s*([\d,]+)\s+(?:functions|real)"
RECORDS = r"([\d,]+)\s+(?:real\s+)?search-tool\s+records"
EPISODES = r"([\d,]+)\s+ground-truth\s+episodes"
BUDGET = r"([\d,]+)-token\s+(?:context|budget)"

CLAIMS: List[Claim] = []
for _file in FILES:
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
CLAIMS += [
    Claim("site/benchmarks.html", "evaluation budget", r"Budget:\s*([\d,]+)\s+tokens",
          _equals(lambda c, s: f"{c['settings']['eval_budget']:,}")),
    Claim("README.md", "JSON tokenizer error", MINUS + r"(\d+)%\s+on\s+JSON-heavy",
          _equals(_json_error)),
    Claim("README_PYPI.md", "budget compliance", r"budget\s+in\s+(\d+)%\s+of\s+episodes",
          _metric("compliance_pct", "compliance")),
    Claim("README_PYPI.md", "recall", r"needed\s+record\s+in\s+(\d+)%\s+of\s+them", _both_recalls),
    Claim("README_PYPI.md", "useful share", r"spends\s+(\d+)%\s+of\s+context\s+tokens",
          _metric("useful_share_pct", "useful share")),
    Claim("README_PYPI.md", "dependencies", r"at\s+(\d+)\s+dependencies", _deps),
    Claim("README_PYPI.md", "import time", r"import\s+of\s+about\s+(\d+)\s+ms", _import_about),
    Claim("site/index.html", "import time", r"about\s+(\d+)(?:&nbsp;|\s)+ms\s+import", _import_about),
    Claim("README_PYPI.md", "term-overlap baseline recall",
          r"term-overlap\s+baseline\s+\(a\s+hand-written\s+scorer\s+in\s+place\s+of\s+`rescore`\)\s+reaches\s+(\d+)%\s+recall",
          _scored_value("recall", "recall")),
    Claim("README_PYPI.md", "term-overlap baseline compliance", r"recall\s+and\s+(\d+)%\s+budget\s+compliance",
          _scored_value("compliance_pct", "compliance")),
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
    _sentence("README_PYPI.md", r"contexel\s+expresses\s+all\s+six\s+operations\s+natively,\s+which\s+no\s+other\s+compared\s+row\s+does",
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
    _sentence("site/index.html",
              r"contexel\s+is\s+the\s+only\s+row\s+with\s+full\s+marks\s+in\s+every\s+outcome\s+column",
              "only row with full marks", _only_contexel_full),
    _sentence("README_PYPI.md", _SLOWEST, _SLOWEST_LABEL, _two_slowest_compliant),
    _sentence("site/index.html", _SLOWEST, _SLOWEST_LABEL, _two_slowest_compliant),
    _sentence("README.md", _SLOWEST, _SLOWEST_LABEL, _two_slowest_compliant),
    _sentence("site/benchmarks.html", _SLOWEST, _SLOWEST_LABEL, _two_slowest_compliant),
    _sentence("README.md", r"contexel's\s+recall\s+is\s+the\s+same\s+under\s+both\s+signals",
              "same recall under both signals", _same_recall),
    _sentence("site/benchmarks.html", r"so\s+its\s+two\s+columns\s+read\s+the\s+same",
              "same recall under both signals", _same_recall),
    _sentence("README.md", r"A\s+row\s+with\s+full\s+recall\s+and\s+zero\s+compliance",
              "toolz and llama-index: full recall, zero compliance", _zero_compliance),
    _sentence("site/benchmarks.html", r"toolz\s+and\s+llama-index\s+keep\s+the\s+needed\s+record",
              "toolz and llama-index: full recall, zero compliance", _zero_compliance),
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
]

# A number with a benchmark unit, in any case: ms (msec, milliseconds), a percentage
# (% / percent / per cent), the multiplication sign (whitespace of any kind may sit between
# the number and these), or an ASCII x written straight after the number ("2.95x", "10x";
# "3 x 4" and "3.x" are not). A bare "s" is deliberately not a unit ("1990s"), and neither is
# "seconds": the README's stemmer-throughput prose ("2 seconds per million chunks") is not
# benchmark-section data and is not covered by this check. A number is not one when a letter
# or digit comes right before it ("a12 ms"), but an underscore does not count as a letter
# (Markdown italics: "_12 ms_").
_END = r"(?![^\W_])"
UNIT_NUMBER = re.compile(
    r"(?<![^\W_])(?<!\.)[+" + MINUS + r"-]?(?:"
    r"\d[\d,.]*\s*(?:(?:msec|ms|milliseconds?|percent|per\s+cent)" + _END + r"|%|" + TIMES + r")"
    r"|\d[\d,]*(?:\.\d+)?x" + _END + r")", re.I)
URLISH = re.compile(r"https?://\S+|(?:href|src)=\"[^\"]*\"|\]\([^)]*\)")
# Attributes whose value is shown to a reader (a tooltip, alt text, the page description).
ATTRIBUTE = re.compile(r"""\b(?:title|alt|aria-label|content)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
# A table cell that is only a number: a Markdown row ("| a | 12 |", "| a | 12", "| `~12` |")
# or an HTML cell ("<td>12</td>", "<td><b>12</b></td>"). Tags, backticks, emphasis stars and a
# leading "~" do not hide it.
BARE_NUMBER = re.compile(r"[+" + MINUS + r"-]?\d[\d,]*(?:\.\d+)?%?")
HTML_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)


def _cell_text(raw: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", raw)).replace(chr(0xA0), " ")
    return re.sub(r"[`*]", "", text).strip().lstrip("~").strip()


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
    dropped, the values of title/alt/aria-label/content attributes kept, tags stripped,
    entities (&nbsp;, &times;, &#37;) decoded, non-breaking spaces made plain."""
    plain = URLISH.sub(" ", outside)
    attributes = [a or b for a, b in ATTRIBUTE.findall(plain)]
    plain = re.sub(r"<[^>]+>", " ", plain)
    return html.unescape(" ".join([plain] + attributes)).replace(chr(0xA0), " ")


# --------------------------------------------------------------------------- #
# The check and the writer
# --------------------------------------------------------------------------- #
def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _load(root: Path, rel: str) -> Dict[str, Any]:
    return json.loads(_read(root, rel))


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

    if _read(root, "benchmarks/COMPARISON.md") != render_report(comparison):
        problems.append("benchmarks/COMPARISON.md is not the report rendered from "
                        "benchmarks/COMPARISON.json (regenerate it with python -m benchmarks.competitors)")
    if _read(root, "benchmarks/RESULTS.md") != suites_report.render(suites):
        problems.append("benchmarks/RESULTS.md is not the report rendered from "
                        "benchmarks/RESULTS.json (regenerate it with python -m benchmarks)")
    try:
        committed = expected_digest(root / "benchmarks" / "dataset.sha256")
    except DatasetChecksumError as exc:
        committed = ""
        problems.append(f"benchmarks/dataset.sha256: {exc}")
    if committed and comparison["dataset"]["sha256"] != committed:
        problems.append("benchmarks/COMPARISON.json was produced with dataset digest "
                        f"{comparison['dataset']['sha256']}, not the committed {committed}")

    wanted = expected_blocks(comparison, suites)
    for rel in FILES:
        try:
            text = _read(root, rel)
        except OSError as exc:
            problems.append(f"{rel}: cannot read it ({exc})")
            continue
        found = _blocks(text)
        names = [n for n, _ in found]
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
    return problems


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


def write(root: Path) -> List[str]:
    """Rewrite every generated block from the results; return the files changed."""
    comparison = _load(root, "benchmarks/COMPARISON.json")
    suites = _load(root, "benchmarks/RESULTS.json")
    changed = []
    for rel, blocks in expected_blocks(comparison, suites).items():
        path = root / rel
        text = path.read_text(encoding="utf-8")
        new = _regenerated(text, blocks)
        if new != text:
            with path.open("w", encoding="utf-8", newline="\n") as fh:
                fh.write(new)
            changed.append(rel)
    return changed
