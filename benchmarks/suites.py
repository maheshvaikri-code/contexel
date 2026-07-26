"""The benchmark suites. Each maps to a claim the docs actually make.

1. determinism        — "identical input through the same pipeline yields
                         byte-identical output" (the context-contract claim),
                         including across fresh interpreters and against
                         nondeterministic noise in the raw records.
2. budget_tightness   — "trim tool output to fit a token budget": how tight is
                         the budget really, shaped with the default heuristic
                         vs an exact tokenizer, measured with tiktoken.
3. speed              — "deterministic and free (no model calls)": per-stage
                         throughput, abstraction overhead vs hand-written
                         code, and the trace-inactive "zero cost" claim.
4. tokenizer_accuracy — the ~4-chars/token default estimate vs tiktoken
                         cl100k_base, on prose, code, and JSON records.
5. reduction          — README "How much does it cut?": reduction is a
                         property of the data and the budget, reported as
                         lossless (select+dedupe) vs by-choice (truncate+trim).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

from contexel import (
    dedupe,
    pipeline,
    rank,
    select,
    stage,
    tokens,
    trace,
    trim_to_budget,
    truncate_field,
)

from .datasets import search_hits

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["path", "line", "symbol", "snippet", "score"]


def contract(budget: int, tokenizer: Any = None) -> Callable:
    """The standard benchmark contract (mirrors the reference agent's)."""
    return pipeline([
        stage(select, fields=FIELDS),
        stage(dedupe, key=["path", "line"]),
        stage(truncate_field, field="snippet", max_tokens=24, tokenizer=tokenizer),
        stage(rank, by="score", desc=True),
        stage(trim_to_budget, max_tokens=budget, tokenizer=tokenizer),
    ])


def _hash(records: List[dict]) -> str:
    payload = json.dumps(records, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _exact_tokenizer() -> Callable[[str], int]:
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    return lambda text: len(enc.encode(text))


# --------------------------------------------------------------------------- #
# 1. Determinism
# --------------------------------------------------------------------------- #
def determinism() -> Dict[str, Any]:
    data = search_hits(5000, dup_rate=0.3)
    reference = _hash(contract(2000)(data))

    # Same content, different request ids / timestamps: raw input differs,
    # shaped output must not.
    a = search_hits(5000, dup_rate=0.3, noise_seed=1)
    b = search_hits(5000, dup_rate=0.3, noise_seed=2)

    # Fresh interpreters with different hash randomization.
    child = (
        "import json, hashlib; "
        "from benchmarks.suites import contract; "
        "from benchmarks.datasets import search_hits; "
        "out = contract(2000)(search_hits(5000, dup_rate=0.3)); "
        "print(hashlib.sha256(json.dumps(out, sort_keys=True, "
        "ensure_ascii=False).encode()).hexdigest())"
    )
    child_hashes = []
    for seed in ("0", "1", "2"):
        run = subprocess.run(
            [sys.executable, "-c", child],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True, text=True, check=True, cwd=ROOT,
        )
        child_hashes.append(run.stdout.strip())

    return {
        "same_process": _hash(contract(2000)(data)) == reference,
        "raw_noise_differs": _hash(a) != _hash(b),
        "noise_neutralized": _hash(contract(2000)(a)) == _hash(contract(2000)(b)),
        "cross_process": set(child_hashes) == {reference},
        "hash_prefix": reference[:16],
    }


# --------------------------------------------------------------------------- #
# 2. Budget tightness
# --------------------------------------------------------------------------- #
def budget_tightness() -> Dict[str, Any]:
    exact = _exact_tokenizer()
    data = search_hits(5000, dup_rate=0.2, snippet_words=60)

    trim_rows = []
    for budget in (500, 1000, 2000):
        for mode, tok in (("heuristic", None), ("tiktoken", exact)):
            out = contract(budget, tokenizer=tok)(data)
            payload = json.dumps(out, ensure_ascii=False)
            trim_rows.append({
                "budget": budget,
                "shaped_with": mode,
                "records_kept": len(out),
                "heuristic_tokens": tokens.count(payload),
                "actual_tokens": exact(payload),
            })

    truncate_rows = []
    long_snippets = search_hits(2000, snippet_words=120)
    for mode, tok, measure in (
        ("heuristic", None, tokens.count),
        ("tiktoken", exact, exact),
    ):
        cut = truncate_field(long_snippets, "snippet", max_tokens=24, tokenizer=tok)
        truncate_rows.append({
            "shaped_with": mode,
            "cap": 24,
            "worst_field_tokens": max(measure(r["snippet"]) for r in cut),
        })
    return {"trim": trim_rows, "truncate": truncate_rows}


# --------------------------------------------------------------------------- #
# 3. Speed
# --------------------------------------------------------------------------- #
def _best_of(fn: Callable[[], Any], repeats: int = 5) -> float:
    best = float("inf")
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def speed() -> Dict[str, Any]:
    stage_rows = []
    for n in (1_000, 10_000, 100_000):
        data = search_hits(n, dup_rate=0.2)
        keep_all = n * 1000  # budget loose enough that trim scans everything
        cases = [
            ("select", lambda d=data: select(d, FIELDS)),
            ("hand-written select", lambda d=data: [
                {k: r[k] for k in FIELDS if k in r} for r in d
            ]),
            ("dedupe (key)", lambda d=data: dedupe(d, key=["path", "line"])),
            ("rank", lambda d=data: rank(d, by="score")),
            ("truncate_field", lambda d=data: truncate_field(
                d, "snippet", max_tokens=8)),
            ("trim_to_budget", lambda d=data, b=keep_all: trim_to_budget(
                d, max_tokens=b)),
            ("full contract", lambda d=data, b=keep_all: contract(b)(d)),
        ]
        for name, fn in cases:
            secs = _best_of(fn)
            stage_rows.append({
                "n": n,
                "stage": name,
                "ms": secs * 1000,
                "records_per_sec": n / secs,
            })

    data = search_hits(10_000, dup_rate=0.2)
    pipe = contract(10_000 * 1000)
    off = _best_of(lambda: pipe(data))

    def run_traced() -> None:
        with trace():
            pipe(data)

    on = _best_of(run_traced)
    return {
        "stages": stage_rows,
        "trace": {"off_ms": off * 1000, "on_ms": on * 1000, "ratio": on / off},
    }


# --------------------------------------------------------------------------- #
# 4. Tokenizer accuracy
# --------------------------------------------------------------------------- #
def tokenizer_accuracy() -> List[Dict[str, Any]]:
    exact = _exact_tokenizer()
    samples = {
        "prose (README.md)": (ROOT / "README.md").read_text(encoding="utf-8"),
        "prose (the-context-contract.md)": (
            ROOT / "the-context-contract.md").read_text(encoding="utf-8"),
        "code (contexel/stages.py)": (
            ROOT / "contexel" / "stages.py").read_text(encoding="utf-8"),
        "code (reference_agent/tools.py)": (
            ROOT / "reference_agent" / "tools.py").read_text(encoding="utf-8"),
        "json (500 search-hit records)": json.dumps(
            search_hits(500), ensure_ascii=False),
    }
    rows = []
    for name, text in samples.items():
        actual = exact(text)
        est = tokens.count(text)
        rows.append({
            "sample": name,
            "actual": actual,
            "heuristic": est,
            "error_pct": (est - actual) / actual * 100,
        })
    return rows


# --------------------------------------------------------------------------- #
# 5. Reduction characterization
# --------------------------------------------------------------------------- #
def reduction() -> List[Dict[str, Any]]:
    rows = []
    for dup in (0.0, 0.25, 0.5):
        for budget in (1000, 4000):
            data = search_hits(2000, dup_rate=dup, snippet_words=60)
            with trace() as t:
                out = contract(budget)(data)
            by = {e.stage: e for e in t.entries}
            total_in = t.tokens_before
            lossless = sum(
                by[s].tokens_before - by[s].tokens_after
                for s in ("select", "dedupe")
            )
            by_choice = sum(
                by[s].tokens_before - by[s].tokens_after
                for s in ("truncate_field", "trim_to_budget")
            )
            rows.append({
                "dup_rate": dup,
                "budget": budget,
                "records": f"{len(data)} -> {len(out)}",
                "tokens": f"{total_in:,} -> {t.tokens_after:,}",
                "lossless_pct": lossless / total_in * 100,
                "by_choice_pct": by_choice / total_in * 100,
                "total_pct": t.reduction * 100,
            })
    return rows
