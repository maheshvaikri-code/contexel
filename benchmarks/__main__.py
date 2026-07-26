"""Run every suite and write benchmarks/RESULTS.md.

    python -m benchmarks
"""
from __future__ import annotations

import platform
from datetime import date
from pathlib import Path

from . import suites


def _table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    """Render rows as a GitHub-flavored markdown table.

    ``columns`` is a list of (key, header); float values are formatted to a
    sensible precision, everything else via str().
    """
    def fmt(value) -> str:
        if isinstance(value, float):
            return f"{value:,.2f}"
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)

    head = "| " + " | ".join(h for _, h in columns) + " |"
    rule = "|" + "|".join("---" for _ in columns) + "|"
    body = "\n".join(
        "| " + " | ".join(fmt(r[k]) for k, _ in columns) + " |" for r in rows
    )
    return "\n".join([head, rule, body])


def main() -> None:
    print("running determinism suite ...")
    det = suites.determinism()
    print("running budget-tightness suite ...")
    budget = suites.budget_tightness()
    print("running speed suite ...")
    spd = suites.speed()
    print("running tokenizer-accuracy suite ...")
    acc = suites.tokenizer_accuracy()
    print("running reduction-characterization suite ...")
    red = suites.reduction()
    print("running encoding-pairing suite ...")
    enc = suites.encoding_pairing()

    check = lambda ok: "PASS" if ok else "FAIL"
    det_rows = [
        {"check": "same process, same input -> identical output",
         "result": check(det["same_process"])},
        {"check": "raw inputs differ (fresh request ids / timestamps)",
         "result": check(det["raw_noise_differs"])},
        {"check": "shaped outputs identical despite that noise",
         "result": check(det["noise_neutralized"])},
        {"check": "3 fresh interpreters (PYTHONHASHSEED 0/1/2) -> same hash",
         "result": check(det["cross_process"])},
    ]

    report = f"""# contexel benchmark results

Generated {date.today().isoformat()} by `python -m benchmarks`.

Environment: Python {platform.python_version()} on {platform.system()} \
({platform.machine()}), single process, wall-clock via `perf_counter`, \
best of 5 runs. Datasets are seeded and byte-identical across machines \
(`benchmarks/datasets.py`).

## What this measures, and deliberately doesn't

contexel's claims are **determinism** (a versioned context contract: the same
shaping on every run), **budget enforcement**, and **zero inference cost** —
not compression magnitude. Per the README ("How much does it cut?") and the
prior-art review, a headline reduction percentage is a property of the data
and the budget, not of the library, so suite 5 *characterizes* reduction
across data profiles instead of advertising one number. Semantic quality
(vs. LLMLingua, ColBERT, cross-encoder rerankers) is explicitly out of scope:
contexel is deterministic and non-semantic by design.

## 1. Determinism (the core claim)

SHA-256 of the shaped output of the standard contract over 5,000 search-hit
records (30% duplicates), hash prefix `{det["hash_prefix"]}`:

{_table(det_rows, [("check", "Check"), ("result", "Result")])}

## 2. Budget tightness

`trim_to_budget` shaped with the default heuristic tokenizer vs an exact
tiktoken tokenizer, then measured with tiktoken (`cl100k_base`). "Actual"
is the token cost of the serialized output that would enter context.

{_table(budget["trim"], [
    ("budget", "Budget"), ("shaped_with", "Shaped with"),
    ("records_kept", "Records kept"),
    ("heuristic_tokens", "Heuristic tokens"), ("actual_tokens", "Actual tokens"),
])}

`truncate_field` with `max_tokens=24` on 120-word snippets — worst clipped
field, measured with the tokenizer that shaped it (docstring claims
"~max_tokens"):

{_table(budget["truncate"], [
    ("shaped_with", "Shaped with"), ("cap", "Cap"),
    ("worst_field_tokens", "Worst field tokens"),
])}

## 3. Speed (no model calls, plain Python)

{_table(spd["stages"], [
    ("n", "Records"), ("stage", "Stage"), ("ms", "ms (best of 5)"),
    ("records_per_sec", "Records/sec"),
])}

Trace overhead on the full contract over 10,000 records: \
{spd["trace"]["off_ms"]:.1f} ms inactive vs {spd["trace"]["on_ms"]:.1f} ms \
active ({spd["trace"]["ratio"]:.2f}x). Inactive tracing is the "zero cost" \
claim; active tracing token-counts every stage boundary and is priced \
accordingly.

## 4. Default tokenizer accuracy (heuristic vs tiktoken cl100k_base)

Positive error = the heuristic over-estimates (conservative for budgets).

{_table(acc, [
    ("sample", "Sample"), ("actual", "Actual"), ("heuristic", "Heuristic"),
    ("error_pct", "Error %"),
])}

## 5. Reduction characterization (a property of the data, not the library)

Standard contract over 2,000 records with 60-word snippets. Lossless =
`select` + `dedupe` (pure redundancy); by-choice = `truncate_field` +
`trim_to_budget` (budget enforcement you dialed in).

{_table(red, [
    ("dup_rate", "Dup rate"), ("budget", "Budget"), ("records", "Records"),
    ("tokens", "Tokens"), ("lossless_pct", "Lossless %"),
    ("by_choice_pct", "By-choice %"), ("total_pct", "Total %"),
])}

## 6. Encoding pairing (shape-then-encode)

Budgets are encoding-relative: `trim_to_budget` prices each record by its
serialized text. The same contract and budget, with the boundary priced and
serialized as JSON (contexel's default) vs a minimal ISON table
([ison.dev](https://ison.dev)) via `tokens.set_serializer`. `select` first
projects records onto a uniform field set — exactly the rows ISON's table
syntax encodes without repeating keys. Actual cost measured with tiktoken.

{_table(enc, [
    ("encoding", "Encoding"), ("budget", "Budget"),
    ("records_kept", "Records kept"), ("actual_tokens", "Actual tokens"),
    ("tokens_per_record", "Tokens/record"),
])}
"""

    out = Path(__file__).resolve().parent / "RESULTS.md"
    out.write_text(report, encoding="utf-8")
    print(f"\nwrote {out}")
    print("\ndeterminism:", ", ".join(f"{r['check']}: {r['result']}" for r in det_rows))


if __name__ == "__main__":
    main()
