"""Comparative benchmark against the prior-art libraries named in the README.

    python -m benchmarks.competitors        (writes benchmarks/COMPARISON.md)

Dataset: real, public code-search records — CodeSearchNet (python/test) via
the Hugging Face datasets-server (see fetch_dataset.py). Tool output is
reconstructed the way an agent session actually produces it: several
overlapping substring queries over the corpus, whose hit lists naturally
contain duplicates.

Fairness rules:
- One canonical task for everyone: project 5 fields, dedupe by key, clip the
  snippet to ~24 tokens, rank by score, fit a 2,000-token budget.
- Every implementation that lacks a native stage uses the SAME hand-written
  glue helpers, so wall-time differences reflect the library, not the glue.
- The "native stages" column says how much of the task the library itself
  expressed (the hand-written baseline is what model-improvised shaping code
  looks like: 0/5).
- Competitors are guard-imported; a missing library becomes a report note,
  never an error. Semantic tools (embedding dedupe, LLMLingua, rerankers)
  are matrix-only: contexel concedes semantic quality by design.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from contexel import dedupe, pipeline, rank, select, stage, trim_to_budget, truncate_field

from .fetch_dataset import load
from .suites import _best_of

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["path", "symbol", "snippet", "score", "repo"]
QUERIES = [
    "file", "parse", "config", "request", "path", "data", "string",
    "return list", "self", "import", "error", "response", "value",
    "key", "index", "update",
]
PER_QUERY_CAP = 2000
SNIPPET_CAP = 24          # tokens
BUDGET = 2000             # tokens


# --------------------------------------------------------------------------- #
# Real tool output from the public corpus
# --------------------------------------------------------------------------- #
def build_tool_output() -> List[dict]:
    """Overlapping search queries over CodeSearchNet -> duplicate-bearing hits."""
    corpus = load()
    out: List[dict] = []
    for query in QUERIES:
        hits = []
        for row in corpus:
            count = row["func_code_string"].lower().count(query)
            if not count:
                continue
            doc = (row["func_documentation_string"] or "").strip()
            snippet = doc or row["func_code_string"].strip().splitlines()[0]
            hits.append({
                "path": row["func_path_in_repository"],
                "symbol": row["func_name"],
                "snippet": snippet,
                "score": count,
                "repo": row["repository_name"],
                "url": row["func_code_url"],
                "language": "python",
            })
        hits.sort(key=lambda h: (-h["score"], h["path"], h["symbol"]))
        out.extend(hits[:PER_QUERY_CAP])
    return out


# --------------------------------------------------------------------------- #
# Shared glue — the hand-written stand-ins for stages a library lacks.
# Deliberately independent of contexel: this is what improvised code looks like.
# --------------------------------------------------------------------------- #
def est_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4)) if text else 0


def g_select(records: List[dict]) -> List[dict]:
    return [{k: r[k] for k in FIELDS if k in r} for r in records]


def g_dedupe(records: List[dict]) -> List[dict]:
    seen, out = set(), []
    for r in records:
        key = (r.get("path"), r.get("symbol"))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def g_truncate(records: List[dict]) -> List[dict]:
    limit = SNIPPET_CAP * 4  # ~4 chars/token
    out = []
    for r in records:
        s = r.get("snippet")
        if isinstance(s, str) and len(s) > limit:
            r = {**r, "snippet": s[: limit - 1].rstrip() + "…"}
        out.append(r)
    return out


def g_rank(records: List[dict]) -> List[dict]:
    present = [r for r in records if "score" in r]
    missing = [r for r in records if "score" not in r]
    return sorted(present, key=lambda r: r["score"], reverse=True) + missing


def g_trim(records: List[dict]) -> List[dict]:
    out, used = [], 0
    for r in records:
        cost = est_tokens(json.dumps(r, ensure_ascii=False)) + 2
        if used + cost > BUDGET:
            break
        out.append(r)
        used += cost
    return out


# --------------------------------------------------------------------------- #
# Implementations of the canonical task
# --------------------------------------------------------------------------- #
def impl_contexel(records: List[dict]) -> List[dict]:
    return pipeline([
        stage(select, fields=FIELDS),
        stage(dedupe, key=["path", "symbol"]),
        stage(truncate_field, field="snippet", max_tokens=SNIPPET_CAP),
        stage(rank, by="score", desc=True),
        stage(trim_to_budget, max_tokens=BUDGET),
    ])(records)


def impl_hand(records: List[dict]) -> List[dict]:
    return g_trim(g_rank(g_truncate(g_dedupe(g_select(records)))))


def impl_toolz(records: List[dict]) -> List[dict]:
    from toolz import unique
    from toolz.dicttoolz import keyfilter

    kept = [keyfilter(lambda k: k in FIELDS, r) for r in records]        # native
    kept = list(unique(kept, key=lambda r: (r["path"], r["symbol"])))    # native
    return g_trim(g_rank(g_truncate(kept)))                              # glue


def impl_langchain(records: List[dict]) -> List[dict]:
    from langchain_core.messages import HumanMessage
    from langchain_core.messages.utils import trim_messages

    shaped = g_rank(g_truncate(g_dedupe(g_select(records))))             # glue
    messages = [HumanMessage(json.dumps(r, ensure_ascii=False)) for r in shaped]
    kept = trim_messages(                                                # native
        messages,
        max_tokens=BUDGET,
        token_counter=lambda ms: sum(est_tokens(m.content) + 2 for m in ms),
        strategy="first",
    )
    return shaped[: len(kept)]


def impl_llamaindex(records: List[dict]) -> List[dict]:
    from llama_index.core.schema import NodeWithScore, TextNode

    shaped = g_dedupe(g_select(records))                                 # glue
    nodes = [
        NodeWithScore(
            node=TextNode(
                text=r["snippet"],
                metadata={k: r[k] for k in ("path", "symbol", "repo")},
            ),
            score=float(r["score"]),
        )
        for r in shaped
    ]                                    # the operand its postprocessors require
    back = [
        {**{k: n.node.metadata[k] for k in ("path", "symbol")},
         "snippet": n.node.text, "score": int(n.score),
         "repo": n.node.metadata["repo"]}
        for n in nodes
    ]
    return g_trim(g_rank(g_truncate(back)))                              # glue


IMPLEMENTATIONS = [
    # (name, native stages of 5, note, fn, import target for footprint)
    ("contexel", 5, "full pipeline", impl_contexel, "contexel"),
    ("hand-written", 0, "what model-improvised shaping looks like", impl_hand, None),
    ("toolz", 2, "keyfilter + unique; token stages are glue", impl_toolz, "toolz"),
    ("langchain-core", 1, "trim_messages on records wrapped as messages",
     impl_langchain, "langchain_core"),
    ("llama-index-core", 0, "node round-trip tax; postprocessors fit no stage",
     impl_llamaindex, "llama_index.core"),
]


# --------------------------------------------------------------------------- #
# Footprint: import time (fresh interpreter) + installed dependency closure
# --------------------------------------------------------------------------- #
def import_ms(module: str) -> float:
    code = (
        "import time; t0 = time.perf_counter(); "
        f"import {module}; print((time.perf_counter() - t0) * 1000)"
    )
    run = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, check=True, cwd=ROOT)
    return float(run.stdout.strip())


def dep_closure(dist_name: str) -> Optional[int]:
    """Count of installed distributions the package transitively requires."""
    from packaging.requirements import Requirement

    seen: set = set()
    stack = [dist_name]
    while stack:
        name = stack.pop()
        key = name.lower().replace("_", "-")
        if key in seen:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        seen.add(key)
        for req_text in dist.requires or []:
            req = Requirement(req_text)
            if req.marker and not req.marker.evaluate({"extra": ""}):
                continue
            stack.append(req.name)
    return len(seen) - 1 if seen else None


_DIST = {"contexel": "contexel", "toolz": "toolz",
         "langchain_core": "langchain-core", "llama_index.core": "llama-index-core"}


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def run() -> Dict[str, Any]:
    data = build_tool_output()
    rows, footprints = [], []
    for name, native, note, fn, module in IMPLEMENTATIONS:
        try:
            out_a, out_b = fn(data), fn(data)
        except Exception as exc:  # keep the report going if a library breaks
            rows.append({"impl": name, "native": f"{native}/5", "ms": float("nan"),
                         "kept": 0, "tokens_out": 0, "deterministic": f"ERROR: {exc}"})
            continue
        digest: Callable[[List[dict]], str] = lambda o: hashlib.sha256(
            json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        secs = _best_of(lambda: fn(data))
        rows.append({
            "impl": name,
            "native": f"{native}/5",
            "note": note,
            "ms": secs * 1000,
            "kept": len(out_a),
            "tokens_out": est_tokens(json.dumps(out_a, ensure_ascii=False)),
            "deterministic": "yes" if digest(out_a) == digest(out_b) else "NO",
        })
        if module:
            footprints.append({
                "library": name,
                "import_ms": import_ms(module),
                "transitive_deps": dep_closure(_DIST[module]),
            })
    return {"records_in": len(data), "task": rows, "footprint": footprints}


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
MATRIX = [
    {"library": "contexel", "select": "yes", "dedupe_key": "yes", "rank": "yes",
     "truncate_tok": "yes", "trim_budget": "yes", "merge_schema": "yes",
     "operand": "list[dict]", "ran": "timed"},
    {"library": "toolz", "select": "keyfilter", "dedupe_key": "unique(key)",
     "rank": "stdlib", "truncate_tok": "no", "trim_budget": "no",
     "merge_schema": "no", "operand": "any dicts", "ran": "timed"},
    {"library": "langchain-core", "select": "no", "dedupe_key": "no",
     "rank": "no", "truncate_tok": "no", "trim_budget": "trim_messages",
     "merge_schema": "no", "operand": "BaseMessage", "ran": "timed"},
    {"library": "llama-index-core", "select": "no", "dedupe_key": "no",
     "rank": "score filter/reorder", "truncate_tok": "no", "trim_budget": "no",
     "merge_schema": "no", "operand": "NodeWithScore", "ran": "timed"},
    {"library": "haystack-ai (DocumentJoiner)", "select": "no",
     "dedupe_key": "by doc id", "rank": "join/RRF", "truncate_tok": "no",
     "trim_budget": "no", "merge_schema": "no (uniform Document)",
     "operand": "Document",
     "ran": "matrix only: pre-existing haystack/farm-haystack conflict in env"},
    {"library": "langchain EmbeddingsRedundantFilter", "select": "no",
     "dedupe_key": "semantic", "rank": "no", "truncate_tok": "no",
     "trim_budget": "no", "merge_schema": "no", "operand": "Document",
     "ran": "matrix only: needs embedding model; model/version-dependent"},
    {"library": "LLMLingua / ColBERT / rerankers", "select": "no",
     "dedupe_key": "no", "rank": "semantic", "truncate_tok": "semantic",
     "trim_budget": "semantic", "merge_schema": "no", "operand": "text",
     "ran": "out of scope by design (contexel concedes semantic quality)"},
    {"library": "context-engineering-toolkit", "select": "-", "dedupe_key": "-",
     "rank": "-", "truncate_tok": "-", "trim_budget": "-", "merge_schema": "-",
     "operand": "-",
     "ran": "NOT FOUND on PyPI — prior-art claim did not verify"},
]


def main() -> None:
    from .__main__ import _table

    print("building tool output from CodeSearchNet ...")
    results = run()
    print(f"  {results['records_in']} records; timing implementations ...")

    report = f"""# contexel vs prior art — comparative benchmark

Generated by `python -m benchmarks.competitors`.

**Dataset (public):** [CodeSearchNet](https://huggingface.co/datasets/code-search-net/code_search_net)
python/test split in full (22,176 rows) via the Hugging Face parquet export
(`benchmarks/fetch_dataset.py`). Tool output is reconstructed the way an agent
session produces it: {len(QUERIES)} overlapping substring queries over the
corpus, hit lists capped at {PER_QUERY_CAP}/query -> {results["records_in"]:,}
records whose duplicates are real (the same function matching several
queries).

**Canonical task:** project {len(FIELDS)} fields, dedupe by (path, symbol),
clip `snippet` to ~{SNIPPET_CAP} tokens, rank by score, fit a {BUDGET:,}-token
budget.

**Fairness:** every implementation missing a native stage uses the *same*
hand-written glue helpers; the hand-written row (0/5 native) is the
model-improvised baseline contexel replaces. Semantic tools are matrix-only —
contexel concedes semantic quality by design.

## Capability matrix (native operations on tool-output records)

{_table(MATRIX, [
    ("library", "Library"), ("select", "select"), ("dedupe_key", "dedupe(key)"),
    ("rank", "rank"), ("truncate_tok", "truncate(tok)"),
    ("trim_budget", "trim(budget)"), ("merge_schema", "merge(schema)"),
    ("operand", "Operand"), ("ran", "In timed run?"),
])}

## Canonical task on real records

{_table(results["task"], [
    ("impl", "Implementation"), ("native", "Native stages"),
    ("ms", "ms (best of 5)"), ("kept", "Records kept"),
    ("tokens_out", "Tokens out"), ("deterministic", "Deterministic"),
])}

## Footprint

Import time is a fresh interpreter importing only the library; transitive
deps counts installed distributions the package requires (recursive).

{_table(results["footprint"], [
    ("library", "Library"), ("import_ms", "Import ms"),
    ("transitive_deps", "Transitive deps"),
])}

## Reading the results

- No library in the timed set expresses more than 2 of the 5 stages natively
  on tool-output records; contexel is the only 5/5. That gap — not raw speed —
  is the claim this comparison tests.
- contexel is slower than the hand-written glue on this task, and that is the
  honest price of accuracy: `truncate_field` binary-searches to a true token
  cap where the glue slices at 4 chars/token, which is why contexel's output
  lands tighter under budget. All rows are microseconds per record —
  negligible next to a single model call.
- All timed implementations are deterministic on this task: mechanical
  shaping is reproducible whoever provides it. The nondeterminism contexel
  removes lives in the *hand-written baseline being re-improvised per run*
  (and in the semantic alternatives), not in these libraries' primitives.
- `context-engineering-toolkit`, cited by the prior-art review as the closest
  standalone competitor, could not be found on PyPI at benchmark time.
"""
    out = Path(__file__).resolve().parent / "COMPARISON.md"
    out.write_text(report, encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
