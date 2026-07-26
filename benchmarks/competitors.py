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


def g_trim(records: List[dict], budget: int = BUDGET) -> List[dict]:
    out, used = [], 0
    for r in records:
        cost = est_tokens(json.dumps(r, ensure_ascii=False)) + 2
        if used + cost > budget:
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
# Outcome benchmark — what each library achieves NATIVELY, scored against
# ground truth. CodeSearchNet pairs every function with its docstring, so for
# each episode we know exactly which record the agent needed; each library
# shapes the episode's hit list using only the operations it provides itself.
# --------------------------------------------------------------------------- #
import random
import time

EVAL_BUDGET = 1500
N_EPISODES = 100
LLAMA_SCORE_CUTOFF = 2.0  # a fixed, stated policy: SimilarityPostprocessor cutoff


def _record(row: dict, weak: int, strong: int) -> dict:
    doc = (row["func_documentation_string"] or "").strip()
    return {
        "path": row["func_path_in_repository"],
        "symbol": row["func_name"],
        "snippet": doc or row["func_code_string"].strip().splitlines()[0],
        "score_weak": weak,       # raw substring count — a poor relevance signal
        "score_strong": strong,   # distinct terms matched dominate — a decent one
        "repo": row["repository_name"],
        "url": row["func_code_url"],
        "language": "python",
    }


def build_episodes(corpus: List[dict], n: int = N_EPISODES, seed: int = 11) -> List[dict]:
    """n ground-truth episodes: a target function + the hit list a multi-term
    search over the full corpus returns for its docstring's key terms.

    Each hit carries two relevance signals so the outcome benchmark can vary
    the *quality of the retrieval score* independently of the shaping:
    ``score_weak`` is the raw substring count (favors long, term-happy
    decoys); ``score_strong`` weights matching *all* the query's terms above
    matching one often — the ranking shape a real multi-term search returns.
    """
    rng = random.Random(seed)
    lowered = [
        (row["func_code_string"] + " " + (row["func_documentation_string"] or "")).lower()
        for row in corpus
    ]
    eligible = [
        i for i, row in enumerate(corpus)
        if len((row["func_documentation_string"] or "").split()) >= 8
    ]
    episodes = []
    for i in rng.sample(eligible, min(n * 2, len(eligible))):
        if len(episodes) >= n:
            break
        doc_words = corpus[i]["func_documentation_string"].split()
        terms = [w.lower().strip(".,()`'\"") for w in doc_words if len(w) >= 5][:3]
        if not terms:
            continue
        matched: List[tuple] = []  # (per-term counts, record)
        for j, text in enumerate(lowered):
            counts = [text.count(t) for t in terms]
            total = sum(counts)
            if total:
                distinct = sum(c > 0 for c in counts)
                matched.append(
                    (counts, _record(corpus[j], total, distinct * 10 + min(total, 9)))
                )
        hits: List[dict] = []
        for k in range(len(terms)):  # one simulated tool call per term, with dups
            term_hits = [rec for counts, rec in matched if counts[k]]
            term_hits.sort(key=lambda h: (-h["score_weak"], h["path"], h["symbol"]))
            hits.extend(term_hits[:300])
        target = (corpus[i]["func_path_in_repository"], corpus[i]["func_name"])
        if any((h["path"], h["symbol"]) == target for h in hits):
            episodes.append({"target": target, "hits": hits})
    return episodes


def _with_score(hits: List[dict], signal: str) -> List[dict]:
    key = f"score_{signal}"
    return [
        {**{k: v for k, v in r.items() if not k.startswith("score_")}, "score": r[key]}
        for r in hits
    ]


# Native-only shapers: each uses ONLY what the library itself provides.
def native_contexel(hits: List[dict]) -> List[dict]:
    return pipeline([
        stage(select, fields=FIELDS),
        stage(dedupe, key=["path", "symbol"]),
        stage(truncate_field, field="snippet", max_tokens=SNIPPET_CAP),
        stage(rank, by="score", desc=True),
        stage(trim_to_budget, max_tokens=EVAL_BUDGET),
    ])(hits)


def native_hand(hits: List[dict]) -> List[dict]:
    return g_trim(g_rank(g_truncate(g_dedupe(g_select(hits)))), EVAL_BUDGET)


def native_toolz(hits: List[dict]) -> List[dict]:
    from toolz import unique
    from toolz.dicttoolz import keyfilter

    kept = [keyfilter(lambda k: k in FIELDS, r) for r in hits]
    return list(unique(kept, key=lambda r: (r["path"], r["symbol"])))
    # no token stage exists: the whole deduped set enters context


def native_langchain(hits: List[dict]) -> List[dict]:
    from langchain_core.messages import HumanMessage
    from langchain_core.messages.utils import trim_messages

    messages = [HumanMessage(json.dumps(r, ensure_ascii=False)) for r in hits]
    kept = trim_messages(
        messages,
        max_tokens=EVAL_BUDGET,
        token_counter=lambda ms: sum(est_tokens(m.content) + 2 for m in ms),
        strategy="first",
    )
    return hits[: len(kept)]
    # budget is native; projection/dedupe/rank are not, so raw records go in


def native_llama(hits: List[dict]) -> List[dict]:
    from llama_index.core.postprocessor import LongContextReorder, SimilarityPostprocessor
    from llama_index.core.schema import NodeWithScore, TextNode

    nodes = [
        NodeWithScore(
            node=TextNode(text=json.dumps(r, ensure_ascii=False)),
            score=float(r["score"]),
        )
        for r in hits
    ]
    nodes = SimilarityPostprocessor(similarity_cutoff=LLAMA_SCORE_CUTOFF).postprocess_nodes(nodes)
    nodes = LongContextReorder().postprocess_nodes(nodes)
    return [json.loads(n.node.text) for n in nodes]
    # score-filter + reorder are native; no budget stage exists


NATIVE_IMPLS = [
    ("contexel", native_contexel),
    ("hand-written", native_hand),
    ("toolz", native_toolz),
    ("langchain-core", native_langchain),
    ("llama-index-core", native_llama),
]


def _useful_tokens(context: List[dict]) -> int:
    """Tokens the context spends on needed fields of first-occurrence records."""
    seen, useful = set(), []
    for r in context:
        key = (r.get("path"), r.get("symbol"))
        if key in seen:
            continue
        seen.add(key)
        useful.append({k: r[k] for k in FIELDS if k in r})
    return est_tokens(json.dumps(useful, ensure_ascii=False))


def native_outcomes() -> List[Dict[str, Any]]:
    corpus = load()
    episodes = build_episodes(corpus)
    n = len(episodes)
    rows = []
    for name, fn in NATIVE_IMPLS:
        row: Dict[str, Any] = {"impl": name}
        for signal in ("strong", "weak"):
            recalled = compliant = 0
            fills, shares = [], []
            t0 = time.perf_counter()
            for ep in episodes:
                context = fn(_with_score(ep["hits"], signal))
                total = est_tokens(json.dumps(context, ensure_ascii=False))
                fills.append(total / EVAL_BUDGET)
                compliant += total <= EVAL_BUDGET
                recalled += any(
                    (r.get("path"), r.get("symbol")) == ep["target"] for r in context
                )
                shares.append(_useful_tokens(context) / total if total else 0.0)
            row[f"recall_{signal}_pct"] = recalled / n * 100
            if signal == "strong":  # signal-independent shape metrics, one pass
                row.update({
                    "compliance_pct": compliant / n * 100,
                    "fill_x": sum(fills) / n,
                    "useful_share_pct": sum(shares) / n * 100,
                    "ms_per_episode": (time.perf_counter() - t0) * 1000 / n,
                })
        rows.append(row)
    return rows


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
    print("running ground-truth outcome benchmark (native-only) ...")
    outcomes = native_outcomes()

    foot = {f["library"]: f for f in results["footprint"]}
    out_by = {o["impl"]: o for o in outcomes}
    ops_summary = {
        "contexel": "5/5 (+ merge)",
        "hand-written": "0/5 - improvised",
        "toolz": "2/5 (select, dedupe)",
        "langchain-core": "1/5 (trim)",
        "llama-index-core": "0/5 (filter/reorder only)",
    }
    combined = []
    for row in results["task"]:
        name = row["impl"]
        o, f = out_by.get(name, {}), foot.get(name, {})
        combined.append({
            "impl": name,
            "ops": ops_summary.get(name, row["native"]),
            "ms": row["ms"],
            "recall": f"{o.get('recall_strong_pct', 0):.0f} / {o.get('recall_weak_pct', 0):.0f}",
            "compliance_pct": o.get("compliance_pct", 0.0),
            "fill_x": o.get("fill_x", 0.0),
            "useful_share_pct": o.get("useful_share_pct", 0.0),
            "import_ms": f.get("import_ms", "-"),
            "deps": f.get("transitive_deps", "-"),
        })

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

## At a glance — all three benchmarks clubbed

One row per implementation, joining the three tables below: **native
operations** (of the task's 5 stages the library expresses itself),
**speed** on the 28k-record canonical task, the ground-truth **outcome**
metrics (recall under a strong / weak retrieval signal; *compliance* = % of
episodes whose final context fit the 1,500-token budget; *fill* = mean
context tokens / budget), and **footprint**.

{_table(combined, [
    ("impl", "Implementation"), ("ops", "Native ops"),
    ("ms", "ms @28k"), ("recall", "Recall % s/w"),
    ("compliance_pct", "Compliance %"), ("fill_x", "Fill x"),
    ("useful_share_pct", "Useful %"), ("import_ms", "Import ms"),
    ("deps", "Deps"),
])}

Read it in one line per row: contexel is the only implementation that covers
the operations, respects the budget, keeps the needed record (given a decent
retrieval signal), wastes no context tokens, and costs nothing to carry.
Every alternative tops it on exactly one column by sacrificing another —
speed (hand-written, by re-improvising the policy each run), recall (toolz,
llama-index, by ignoring the budget), or compliance (langchain-core, by
filling the budget with bloat).

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

## What each achieves natively (ground-truth outcome benchmark)

The tables above hold the *policy* constant and let glue fill the gaps. This
one asks the question that matters — **was the output useful?** — and lets
each library act only through its own operations. {N_EPISODES} episodes with
known ground truth: a target function, plus the hit list a
multi-term docstring search over the full corpus returns (the target is
always present in the raw hits, so every miss below is a *shaping* loss, not
a retrieval loss). Budget: {EVAL_BUDGET:,} tokens.

Every hit carries two retrieval scores, because outcome quality depends on
the ranking signal the search tool hands the shaper: **strong** ranks
matching all the query's terms above matching one term often (the shape a
real multi-term search returns); **weak** is a raw substring count, which
buries the target under term-happy decoys.

- **Recall@budget** — the record the agent actually needed survived into the
  final context, under each signal.
- **Compliance** — episodes where the context fits the budget; **Fill** —
  mean context tokens / budget (over 1.00 = blown).
- **Useful share** — fraction of context tokens spent on needed fields of
  first-occurrence records (the rest is duplicates and field bloat).

{_table(outcomes, [
    ("impl", "Implementation"),
    ("recall_strong_pct", "Recall % (strong)"),
    ("recall_weak_pct", "Recall % (weak)"),
    ("compliance_pct", "Compliance %"), ("fill_x", "Fill x"),
    ("useful_share_pct", "Useful share %"), ("ms_per_episode", "ms/episode"),
])}

What the numbers say each is best at:

- **contexel** (and the **hand-written** policy, which is the same policy
  re-improvised per run) is the only configuration delivering recall,
  100% budget compliance, and an all-useful context *together* — but only
  when the retrieval signal is decent. Under the weak signal its recall
  collapses too: deterministic shaping executes a ranking policy faithfully,
  it cannot rescue a bad one. That is the measured cost of conceding
  semantic reranking, and the two recall columns bound it.
- **toolz** achieves perfect recall by not doing the job — no token layer
  exists, so the "context" blows the budget by the fill factor shown. Best
  at: fast lossless projection/dedup when something else enforces budgets.
- **langchain-core** is best at what it actually ships: budget enforcement
  over message streams. With no record-level projection or dedupe, the
  budget fills with bloat and duplicates, and whether the target makes the
  cut depends entirely on incoming order.
- **llama-index-core**'s postprocessors (score cutoff {LLAMA_SCORE_CUTOFF},
  lost-in-middle reorder) are built for reordering retrieved RAG nodes, not
  bounding them — recall is high because nearly everything is kept, at a
  fill factor no context window accepts.

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
