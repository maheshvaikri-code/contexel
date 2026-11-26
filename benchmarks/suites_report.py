"""Run every suite, collect the numbers into one dictionary, render RESULTS.md from it.

``collect`` runs the suites; ``render`` turns the dictionary into the report and
nothing else, so the published numbers can be checked against RESULTS.json
(tools/check_benchmark_numbers.py) and the report can be re-rendered from it.
"""
from __future__ import annotations

import platform
from datetime import date
from typing import Any, Dict, List

import contexel

from . import suites
from .tables import table


def collect() -> Dict[str, Any]:
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
    return {
        "schema": 1,
        "generated": date.today().isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": f"{platform.system()} ({platform.machine()})",
            "contexel": contexel.__version__,
        },
        "determinism": det,
        "budget": budget,
        "speed": spd,
        "accuracy": acc,
        "reduction": red,
        "encoding": enc,
    }


def determinism_rows(det: Dict[str, Any]) -> List[Dict[str, str]]:
    def verdict(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    return [
        {"check": "same process, same input -> identical output",
         "result": verdict(det["same_process"])},
        {"check": "raw inputs differ (fresh request ids / timestamps)",
         "result": verdict(det["raw_noise_differs"])},
        {"check": "shaped outputs identical despite that noise",
         "result": verdict(det["noise_neutralized"])},
        {"check": "3 fresh interpreters (PYTHONHASHSEED 0/1/2) -> same hash",
         "result": verdict(det["cross_process"])},
    ]


def render(results: Dict[str, Any]) -> str:
    env = results["environment"]
    det, budget, spd = results["determinism"], results["budget"], results["speed"]
    acc, red, enc = results["accuracy"], results["reduction"], results["encoding"]
    det_rows = determinism_rows(det)

    return f"""# contexel benchmark results

Generated {results["generated"]} by `python -m benchmarks`. The numbers below are
rendered from `benchmarks/RESULTS.json`; `tools/check_benchmark_numbers.py` fails
when the README or the site disagree with it.

Environment: Python {env["python"]} on {env["platform"]}, contexel {env["contexel"]}, \
single process, wall-clock via `perf_counter`, \
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

{table(det_rows, [("check", "Check"), ("result", "Result")])}

## 2. Budget tightness

`trim_to_budget` shaped with the default heuristic tokenizer vs an exact
tiktoken tokenizer, then measured with tiktoken (`cl100k_base`). "Actual"
is the token cost of the serialized output that would enter context.

{table(budget["trim"], [
    ("budget", "Budget"), ("shaped_with", "Shaped with"),
    ("records_kept", "Records kept"),
    ("heuristic_tokens", "Heuristic tokens"), ("actual_tokens", "Actual tokens"),
])}

`truncate_field` with `max_tokens=24` on 120-word snippets — worst clipped
field, measured with the tokenizer that shaped it (docstring claims
"~max_tokens"):

{table(budget["truncate"], [
    ("shaped_with", "Shaped with"), ("cap", "Cap"),
    ("worst_field_tokens", "Worst field tokens"),
])}

## 3. Speed (no model calls, plain Python)

{table(spd["stages"], [
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

{table(acc, [
    ("sample", "Sample"), ("actual", "Actual"), ("heuristic", "Heuristic"),
    ("error_pct", "Error %"),
])}

## 5. Reduction characterization (a property of the data, not the library)

Standard contract over 2,000 records with 60-word snippets. Lossless =
`select` + `dedupe` (pure redundancy); by-choice = `truncate_field` +
`trim_to_budget` (budget enforcement you dialed in).

{table(red, [
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

{table(enc, [
    ("encoding", "Encoding"), ("budget", "Budget"),
    ("records_kept", "Records kept"), ("actual_tokens", "Actual tokens"),
    ("tokens_per_record", "Tokens/record"),
])}
"""
