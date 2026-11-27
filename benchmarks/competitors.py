"""Comparative benchmark against the prior-art libraries named in the README.

    python -m benchmarks.competitors   (writes COMPARISON.md and COMPARISON.json)

Dataset: real, public functions — CodeSearchNet (python/test) via the Hugging
Face datasets-server (see fetch_dataset.py, which verifies a committed
SHA-256). Tool output is simulated: several fixed, overlapping substring
searches over the corpus, whose hit lists contain duplicates.

Fairness rules:
- One canonical task for everyone: project 5 fields, dedupe by key, clip the
  snippet to ~24 tokens, rank by score, fit a 2,000-token budget.
- Every implementation that lacks a native stage uses the SAME hand-written
  glue helpers (for langchain-core and llama-index-core, converting the records
  to the library's message or node type is part of the time).
- Whether a step enters a library's own code is detected (opcount.py: a step
  counts as native when running it enters the library's package). Which library
  functions each implementation uses, and which operation each step serves, are
  written by hand below: the counts describe these wirings, not the libraries.
- The hand-written baseline exists in two forms: one that trusts the tool's
  score, and one with its own term-overlap scorer, so contexel's rescoring is
  compared with another rescorer, not only with none.
- The original episodes query with the target's own words. The inflected
  episodes query with deterministic inflections of them (inflection.py) and are
  reported separately: they measure inflection robustness, not semantic
  paraphrase.
- The competitor libraries are imported only inside their steps, so this module
  imports without them; running the benchmark needs them all (a missing library
  is an ImportError: install the ``benchmarks`` extra). Semantic tools
  (embedding dedupe, LLMLingua, rerankers) are matrix-only: contexel concedes
  semantic quality by design.

The run collects every number into one dictionary (``collect``), writes it as
COMPARISON.json, and renders COMPARISON.md from that dictionary alone
(``render_report``), so the published tables can be checked against the data
(tools/check_benchmark_numbers.py).
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import random
import re
import subprocess
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import date
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import contexel
from contexel import (
    dedupe, pipeline, rank, rescore, select, stage, trim_to_budget, truncate_field,
)

from . import fetch_dataset
from .fetch_dataset import load
from .inflection import inflect, inflectable, words
from .opcount import OPS, Step, count
from .opcount import run as run_steps
from .suites import _best_of
from .tables import table

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
EVAL_BUDGET = 1500
N_EPISODES = 100
# SimilarityPostprocessor cutoff. Every strong score is at least 11 (distinct terms x 10 +
# min(total, 9), build_episodes), so it removes nothing under the strong signal; under the
# weak one (the raw count) it drops the hits whose query terms occur once in total.
LLAMA_SCORE_CUTOFF = 2.0
MIN_STRONG_SCORE = 11  # the lowest score_strong build_episodes gives (the report cites it)
TIMED_OPS = ("select", "dedupe", "truncate", "rank", "trim")  # the query-free task


# --------------------------------------------------------------------------- #
# Real tool output from the public corpus
# --------------------------------------------------------------------------- #
def build_tool_output(corpus: Optional[List[dict]] = None) -> List[dict]:
    """Overlapping search queries over CodeSearchNet -> duplicate-bearing hits."""
    if corpus is None:
        corpus = load()
    out: List[dict] = []
    for query in QUERIES:
        hits = []
        for row in corpus:
            count_ = row["func_code_string"].lower().count(query)
            if not count_:
                continue
            doc = (row["func_documentation_string"] or "").strip()
            snippet = doc or row["func_code_string"].strip().splitlines()[0]
            hits.append({
                "path": row["func_path_in_repository"],
                "symbol": row["func_name"],
                "snippet": snippet,
                "score": count_,
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


_HAND_WORD = re.compile(r"[a-z0-9]+")


def g_score_overlap(records: List[dict], terms: List[str]) -> List[dict]:
    """The hand-written term-overlap scorer: how many of the query's distinct
    words occur, as whole words, in the record's snippet, symbol and path.

    It is what a model improvises when asked to rank hits by a query: lower-case
    both sides, split on anything that is not a letter or digit, count the
    overlap. It replaces the tool's score; ties keep the incoming order."""
    want = set(_HAND_WORD.findall(" ".join(terms).lower()))
    out = []
    for r in records:
        text = " ".join(str(r.get(k, "")) for k in ("snippet", "symbol", "path")).lower()
        have = set(_HAND_WORD.findall(text))
        out.append({**r, "score": len(want & have)})
    return out


def sample_records() -> List[dict]:
    """A tiny fixed tool output that every step can run on (duplicates, long
    snippets, mixed scores). The native-operation count runs each implementation
    over it, so the count needs neither the dataset nor the network."""
    return [
        {
            "path": f"src/mod{i % 8}.py",
            "symbol": f"func_{i % 8}",
            "snippet": ("parse the request and return the value " * (1 + i % 3)).strip(),
            "score": 10 - i,
            "repo": "r",
            "url": f"u{i}",
            "language": "python",
        }
        for i in range(12)
    ]


SAMPLE_TERMS = ["parse", "value"]


# --------------------------------------------------------------------------- #
# The implementations, as ordered steps. The list is what runs AND what is counted.
# --------------------------------------------------------------------------- #
def run_pipeline(steps: Sequence[Step], data: Any) -> Any:
    """contexel's own composition: the steps' stages through pipeline()."""
    return pipeline([s.fn for s in steps])(data)


def _contexel_stage_steps(trim: int) -> List[Step]:
    return [
        Step("select", stage(select, fields=FIELDS), "select"),
        Step("dedupe", stage(dedupe, key=["path", "symbol"]), "dedupe"),
        Step("truncate", stage(truncate_field, field="snippet", max_tokens=SNIPPET_CAP),
             "truncate"),
        Step("rank", stage(rank, by="score", desc=True), "rank"),
        Step("trim", stage(trim_to_budget, max_tokens=trim), "trim"),
    ]


def contexel_timed() -> List[Step]:
    return _contexel_stage_steps(BUDGET)


def contexel_outcome(terms: List[str], match: str = "word") -> List[Step]:
    """The standard contract: relevance derived from the query via rescore,
    never trusted from the tool's score."""
    stages = _contexel_stage_steps(EVAL_BUDGET)
    rescoring = Step("rescore", stage(rescore, query=terms, fields=("snippet", "symbol", "path"),
                                      match=match), "rescore")
    return stages[:2] + [rescoring] + stages[2:]


def contexel_stem_outcome(terms: List[str]) -> List[Step]:
    return contexel_outcome(terms, match="stem")


def hand_timed() -> List[Step]:
    return [
        Step("select", g_select, "select"),
        Step("dedupe", g_dedupe, "dedupe"),
        Step("truncate", g_truncate, "truncate"),
        Step("rank", g_rank, "rank"),
        Step("trim", g_trim, "trim"),
    ]


def hand_outcome(terms: List[str]) -> List[Step]:
    """Trusts the tool's score."""
    return [
        Step("select", g_select, "select"),
        Step("dedupe", g_dedupe, "dedupe"),
        Step("truncate", g_truncate, "truncate"),
        Step("rank", g_rank, "rank"),
        Step("trim", lambda r: g_trim(r, EVAL_BUDGET), "trim"),
    ]


def hand_scored_outcome(terms: List[str]) -> List[Step]:
    """Has its own term-overlap scorer, then the same glue."""
    return [
        Step("select", g_select, "select"),
        Step("dedupe", g_dedupe, "dedupe"),
        Step("rescore", lambda r: g_score_overlap(r, terms), "rescore"),
        Step("truncate", g_truncate, "truncate"),
        Step("rank", g_rank, "rank"),
        Step("trim", lambda r: g_trim(r, EVAL_BUDGET), "trim"),
    ]


def _toolz_select(records: List[dict]) -> List[dict]:
    from toolz.dicttoolz import keyfilter

    return [keyfilter(lambda k: k in FIELDS, r) for r in records]


def _toolz_dedupe(records: List[dict]) -> List[dict]:
    from toolz import unique

    return list(unique(records, key=lambda r: (r["path"], r["symbol"])))


def toolz_timed() -> List[Step]:
    return [
        Step("select", _toolz_select, "select"),
        Step("dedupe", _toolz_dedupe, "dedupe"),
        Step("truncate", g_truncate, "truncate"),
        Step("rank", g_rank, "rank"),
        Step("trim", g_trim, "trim"),
    ]


def toolz_outcome(terms: List[str]) -> List[Step]:
    # no token stage exists: the whole deduped set enters context
    return [
        Step("select", _toolz_select, "select"),
        Step("dedupe", _toolz_dedupe, "dedupe"),
    ]


def _lc_wrap(records: List[dict]) -> Any:
    from langchain_core.messages import HumanMessage

    return records, [HumanMessage(json.dumps(r, ensure_ascii=False)) for r in records]


def _lc_trim(budget: int) -> Callable[[Any], List[dict]]:
    def trim(pair: Any) -> List[dict]:
        from langchain_core.messages.utils import trim_messages

        records, messages = pair
        kept = trim_messages(
            messages,
            max_tokens=budget,
            token_counter=lambda ms: sum(est_tokens(m.content) + 2 for m in ms),
            strategy="first",
        )
        return records[: len(kept)]
    return trim


def langchain_timed() -> List[Step]:
    return [
        Step("select", g_select, "select"),
        Step("dedupe", g_dedupe, "dedupe"),
        Step("truncate", g_truncate, "truncate"),
        Step("rank", g_rank, "rank"),
        Step("wrap as messages", _lc_wrap, "adapter"),
        Step("trim", _lc_trim(BUDGET), "trim"),
    ]


def langchain_outcome(terms: List[str]) -> List[Step]:
    # the budget is native; projection, dedupe and rank are not, so raw records go in
    return [
        Step("wrap as messages", _lc_wrap, "adapter"),
        Step("trim", _lc_trim(EVAL_BUDGET), "trim"),
    ]


def _llama_snippet_nodes(records: List[dict]) -> Any:
    from llama_index.core.schema import NodeWithScore, TextNode

    return [
        NodeWithScore(
            node=TextNode(
                text=r["snippet"],
                metadata={k: r[k] for k in ("path", "symbol", "repo")},
            ),
            score=float(r["score"]),
        )
        for r in records
    ]


def _llama_from_snippet_nodes(nodes: Any) -> List[dict]:
    return [
        {**{k: n.node.metadata[k] for k in ("path", "symbol")},
         "snippet": n.node.text, "score": int(n.score),
         "repo": n.node.metadata["repo"]}
        for n in nodes
    ]


def llama_timed() -> List[Step]:
    return [
        Step("select", g_select, "select"),
        Step("dedupe", g_dedupe, "dedupe"),
        Step("to nodes", _llama_snippet_nodes, "adapter"),
        Step("from nodes", _llama_from_snippet_nodes, "adapter"),
        Step("truncate", g_truncate, "truncate"),
        Step("rank", g_rank, "rank"),
        Step("trim", g_trim, "trim"),
    ]


def _llama_json_nodes(records: List[dict]) -> Any:
    from llama_index.core.schema import NodeWithScore, TextNode

    return [
        NodeWithScore(node=TextNode(text=json.dumps(r, ensure_ascii=False)),
                      score=float(r["score"]))
        for r in records
    ]


def _llama_cutoff(nodes: Any) -> Any:
    from llama_index.core.postprocessor import SimilarityPostprocessor

    return SimilarityPostprocessor(similarity_cutoff=LLAMA_SCORE_CUTOFF).postprocess_nodes(nodes)


def _llama_reorder(nodes: Any) -> Any:
    from llama_index.core.postprocessor import LongContextReorder

    return LongContextReorder().postprocess_nodes(nodes)


def llama_outcome(terms: List[str]) -> List[Step]:
    # score filter and reorder are native; neither is one of the task's operations
    return [
        Step("to nodes", _llama_json_nodes, "adapter"),
        Step("score cutoff", _llama_cutoff, "other"),
        Step("long-context reorder", _llama_reorder, "other"),
        Step("from nodes", lambda nodes: [json.loads(n.node.text) for n in nodes], "adapter"),
    ]


@dataclass(frozen=True)
class Impl:
    name: str
    note: str
    operand: str                       # what the library operates on (documentation)
    root: Optional[str]                # the library's top-level package; None = hand-written
    module: Optional[str]              # what to import for the footprint measurement
    outcome: Callable[[List[str]], List[Step]]
    timed: Optional[Callable[[], List[Step]]] = None
    runner: Callable[[Sequence[Step], Any], Any] = run_steps


IMPLEMENTATIONS = [
    Impl("contexel", "full pipeline", "list[dict]", "contexel", "contexel",
         contexel_outcome, contexel_timed, run_pipeline),
    Impl("hand-written", "what model-improvised shaping looks like (trusts the tool's score)",
         "list[dict]", None, None, hand_outcome, hand_timed),
    Impl("hand-written (term overlap)", "the same glue plus its own term-overlap scorer",
         "list[dict]", None, None, hand_scored_outcome),
    Impl("toolz", "keyfilter + unique; token stages are glue", "any dicts",
         "toolz", "toolz", toolz_outcome, toolz_timed),
    Impl("langchain-core", "trim_messages on records wrapped as messages", "BaseMessage",
         "langchain_core", "langchain_core", langchain_outcome, langchain_timed),
    Impl("llama-index-core", "node round-trip tax; postprocessors fit no stage",
         "NodeWithScore", "llama_index", "llama_index.core", llama_outcome, llama_timed),
]

# The same shapers measured on the inflected episodes: the ones that read the query,
# and the hand-written one that does not (the control: inflection cannot touch it).
CONTEXEL_STEM = Impl("contexel (match=stem)", "rescore with the opt-in stemmer", "list[dict]",
                     "contexel", "contexel", contexel_stem_outcome, None, run_pipeline)
INFLECTION_SHAPERS = [
    IMPLEMENTATIONS[0], CONTEXEL_STEM, IMPLEMENTATIONS[2], IMPLEMENTATIONS[1],
]


# --------------------------------------------------------------------------- #
# Footprint: import time (fresh interpreter) + installed dependency closure
# --------------------------------------------------------------------------- #
IMPORT_REPEATS = 5


def _import_once_ms(module: str) -> float:
    """Milliseconds one fresh interpreter spends importing ``module``."""
    code = (
        "import time; t0 = time.perf_counter(); "
        f"import {module}; print((time.perf_counter() - t0) * 1000)"
    )
    run = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, check=True, cwd=ROOT)
    return float(run.stdout.strip())


def import_ms(module: str, repeats: int = IMPORT_REPEATS) -> float:
    """The median of ``repeats`` fresh-interpreter imports of ``module``.

    One import is too noisy to publish (the same import measured 20 to 46 ms
    within minutes on one idle machine: file cache, antivirus, scheduling), so
    the figure is the median of several, each in its own interpreter."""
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    return statistics.median(_import_once_ms(module) for _ in range(repeats))


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
# The timed canonical task
# --------------------------------------------------------------------------- #
def _digest(records: List[dict]) -> str:
    return hashlib.sha256(
        json.dumps(records, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def time_task(data: List[dict]) -> Dict[str, Any]:
    rows, footprints = [], []
    sample = sample_records()
    for impl in IMPLEMENTATIONS:
        if impl.timed is None:
            continue
        steps = impl.timed()
        native = count(steps, impl.root, sample, TIMED_OPS).native

        def fn(records: List[dict], steps: List[Step] = steps,
               runner: Callable[[Sequence[Step], Any], Any] = impl.runner) -> Any:
            return runner(steps, records)

        label = f"{len(native)}/{len(TIMED_OPS)}"
        out_a, out_b = fn(data), fn(data)  # a missing or broken library is an error
        secs = _best_of(lambda: fn(data))
        rows.append({
            "impl": impl.name,
            "native": label,
            "note": impl.note,
            "ms": secs * 1000,
            "kept": len(out_a),
            "tokens_out": est_tokens(json.dumps(out_a, ensure_ascii=False)),
            "deterministic": "yes" if _digest(out_a) == _digest(out_b) else "NO",
        })
        if impl.module:
            footprints.append({
                "library": impl.name,
                "import_ms": import_ms(impl.module),
                "transitive_deps": dep_closure(_DIST[impl.module]),
            })
    return {"records_in": len(data), "task": rows, "footprint": footprints}


# --------------------------------------------------------------------------- #
# Outcome benchmark — what each library achieves NATIVELY, scored against
# ground truth. CodeSearchNet pairs every function with its docstring, so for
# each episode we know exactly which record the agent needed; each library
# shapes the episode's hit list using only the operations it provides itself.
# --------------------------------------------------------------------------- #
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


def build_episodes(corpus: List[dict], n: int = N_EPISODES, seed: int = 11,
                   term_ok: Optional[Callable[[str, set], bool]] = None,
                   pool: int = 2) -> List[dict]:
    """n ground-truth episodes: a target function + the hit list a multi-term
    search over the full corpus returns for its docstring's key terms.

    Each hit carries two relevance signals so the outcome benchmark can vary
    the *quality of the retrieval score* independently of the shaping:
    ``score_weak`` is the raw substring count (favors long, term-happy
    decoys); ``score_strong`` weights matching *all* the query's terms above
    matching one often — the ranking shape a real multi-term search returns.

    ``term_ok(term, target_words)`` (optional) keeps only the docstring terms it
    accepts; the target's words are those of its code, docstring, path and
    symbol, i.e. every field the shapers score. ``pool`` is how many candidate
    functions are sampled per episode wanted. The defaults reproduce the
    original episodes exactly.
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
    for i in rng.sample(eligible, min(n * pool, len(eligible))):
        if len(episodes) >= n:
            break
        doc_words = corpus[i]["func_documentation_string"].split()
        candidates = [w.lower().strip(".,()`'\"") for w in doc_words if len(w) >= 5]
        if term_ok is not None:
            target_words = words(
                lowered[i] + " " + corpus[i]["func_path_in_repository"]
                + " " + corpus[i]["func_name"])
            candidates = [w for w in candidates if term_ok(w, target_words)]
        terms = candidates[:3]
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
            episodes.append({"target": target, "terms": terms, "hits": hits})
    return episodes


def build_inflected_episodes(corpus: List[dict], n: int = N_EPISODES,
                             seed: int = 11) -> List[dict]:
    """Episodes whose terms can all be inflected (inflection.inflectable). The hit
    lists come from the original terms; ``inflected`` is what the shaper is asked."""
    episodes = build_episodes(corpus, n, seed, term_ok=inflectable, pool=4)
    for ep in episodes:
        ep["inflected"] = [inflect(t) for t in ep["terms"]]
    return episodes


def _with_score(hits: List[dict], signal: str) -> List[dict]:
    key = f"score_{signal}"
    return [
        {**{k: v for k, v in r.items() if not k.startswith("score_")}, "score": r[key]}
        for r in hits
    ]


def _has_target(context: List[dict], ep: dict) -> bool:
    return any((r.get("path"), r.get("symbol")) == ep["target"] for r in context)


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


def native_outcomes(episodes: List[dict]) -> List[Dict[str, Any]]:
    if not episodes:
        raise ValueError("native_outcomes needs at least one episode")
    n = len(episodes)
    rows = []
    for impl in IMPLEMENTATIONS:
        row: Dict[str, Any] = {"impl": impl.name}
        for signal in ("strong", "weak"):
            recalled = compliant = 0
            fills, shares = [], []
            t0 = time.perf_counter()
            for ep in episodes:
                context = impl.runner(impl.outcome(ep["terms"]), _with_score(ep["hits"], signal))
                total = est_tokens(json.dumps(context, ensure_ascii=False))
                fills.append(total / EVAL_BUDGET)
                compliant += total <= EVAL_BUDGET
                recalled += _has_target(context, ep)
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


def _recall_pct(impl: Impl, episodes: List[dict], key: str, signal: str = "strong") -> float:
    hit = 0
    for ep in episodes:
        context = impl.runner(impl.outcome(ep[key]), _with_score(ep["hits"], signal))
        hit += _has_target(context, ep)
    return hit / len(episodes) * 100


def inflected_outcomes(episodes: List[dict]) -> Dict[str, Any]:
    if not episodes:
        raise ValueError("inflected_outcomes needs at least one episode")
    rows = []
    for impl in INFLECTION_SHAPERS:
        row = {
            "shaper": impl.name,
            "recall_original_pct": _recall_pct(impl, episodes, "terms"),
            "recall_inflected_pct": _recall_pct(impl, episodes, "inflected"),
        }
        if impl.name == "hand-written":  # the one that trusts the tool: weak signal too
            row["recall_original_weak_pct"] = _recall_pct(impl, episodes, "terms", "weak")
            row["recall_inflected_weak_pct"] = _recall_pct(impl, episodes, "inflected", "weak")
        rows.append(row)
    examples = []
    for ep in episodes:
        for term, inflected in zip(ep["terms"], ep["inflected"]):
            if (term, inflected) not in examples:
                examples.append((term, inflected))
    return {
        "episodes": len(episodes),
        "terms": sum(len(ep["terms"]) for ep in episodes),
        "examples": [list(pair) for pair in examples[:6]],
        "rows": rows,
    }


# --------------------------------------------------------------------------- #
# Collect everything into one dictionary
# --------------------------------------------------------------------------- #
def _version(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "not installed"


def operations(names: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """The computed native/glue/missing operations of each implementation (or of
    the named ones: a library that is not installed need not be asked)."""
    sample = sample_records()
    rows = []
    for impl in IMPLEMENTATIONS:
        if names is not None and impl.name not in names:
            continue
        c = count(impl.outcome(SAMPLE_TERMS), impl.root, sample, OPS)
        rows.append({"impl": impl.name, "operand": impl.operand, **c.as_dict()})
    return rows


def dataset_info(corpus: List[dict], records: int) -> Dict[str, Any]:
    """The dataset entry of the results. The digest is the one ``verify`` computes
    for the cache, not the pin copied: what was measured, not what was expected."""
    return {
        "name": "CodeSearchNet python/test",
        "rows": len(corpus),
        "sha256": fetch_dataset.verify(),
        "queries": len(QUERIES),
        "per_query_cap": PER_QUERY_CAP,
        "records": records,
    }


def collect() -> Dict[str, Any]:
    corpus = load()
    data = build_tool_output(corpus)
    timed = time_task(data)
    episodes = build_episodes(corpus)
    outcomes = native_outcomes(episodes)
    inflected = inflected_outcomes(build_inflected_episodes(corpus))
    return {
        "schema": 1,
        "generated": date.today().isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": f"{platform.system()} ({platform.machine()})",
            "contexel": contexel.__version__,
            "libraries": {d: _version(d) for d in ("toolz", "langchain-core", "llama-index-core")},
        },
        "dataset": dataset_info(corpus, timed["records_in"]),
        "settings": {
            "fields": len(FIELDS),
            "snippet_cap": SNIPPET_CAP,
            "budget": BUDGET,
            "eval_budget": EVAL_BUDGET,
            "episodes": len(episodes),
            "llama_cutoff": LLAMA_SCORE_CUTOFF,
        },
        "operations": operations(),
        "task": timed["task"],
        "outcomes": outcomes,
        "footprint": timed["footprint"],
        "inflected": inflected,
    }


# --------------------------------------------------------------------------- #
# Report — rendered from the collected dictionary alone
# --------------------------------------------------------------------------- #
# Libraries this benchmark does not run: what their documentation says they offer.
NOT_RUN = [
    {"library": "haystack-ai (DocumentJoiner, MetaFieldRanker, LostInTheMiddleRanker)",
     "select": "no",
     "dedupe_key": "by document id (DocumentJoiner)", "rescore_lex": "no",
     "rank": "by a meta field (MetaFieldRanker); rank fusion (DocumentJoiner)",
     "truncate_tok": "no",
     "trim_budget": "word-count budget (LostInTheMiddleRanker; keeps the document that crosses it)",
     "merge_schema": "no (uniform Document)",
     "operand": "Document",
     "ran": "not run in this benchmark"},
    {"library": "langchain-community EmbeddingsRedundantFilter", "select": "no",
     "dedupe_key": "by embedding similarity", "rescore_lex": "no", "rank": "no",
     "truncate_tok": "no",
     "trim_budget": "no", "merge_schema": "no", "operand": "Document",
     "ran": "not run: needs an embedding model; results depend on the model and the threshold"},
    # microsoft/LLMLingua llmlingua/prompt_compressor.py (main): compress_prompt ranks the
    # contexts with get_rank_results (rank_method), keeps the higher-ranked ones within the
    # budget (use_context_level_filter, on by default), can reorder them (reorder_context)
    # and then compresses tokens.
    {"library": "LLMLingua", "select": "no",
     "dedupe_key": "no",
     "rescore_lex": "BM25 context ranking (`rank_method=\"bm25\"`; the default ranks by the "
                    "compressor's language model)",
     "rank": "ranks contexts by `rank_method` (the compressor's language model by default; also "
             "BM25, gzip, embedding and reranker methods) and can reorder them (`reorder_context`)",
     "truncate_tok": "removes tokens a small language model scores as non-essential",
     "trim_budget": "keeps the higher-ranked contexts, then compresses tokens, to "
                    "`target_token` or `rate`", "merge_schema": "no",
     "operand": "text",
     "ran": "not run: its token compression needs a language model"},
    {"library": "ColBERT, cross-encoder rerankers", "select": "no",
     "dedupe_key": "no", "rescore_lex": "no (learned relevance)",
     "rank": "by learned relevance, top-k", "truncate_tok": "no",
     "trim_budget": "no token budget", "merge_schema": "no", "operand": "query and passages",
     "ran": "not run: out of scope by design (contexel is lexical and deterministic)"},
    {"library": "context-engineering-toolkit", "select": "-", "dedupe_key": "-",
     "rescore_lex": "-",
     "rank": "-", "truncate_tok": "-", "trim_budget": "-", "merge_schema": "-",
     "operand": "-",
     "ran": "not on PyPI as of 2026-11-26 (`pip index versions context-engineering-toolkit`)"},
]


_TIMES, _DIVIDE = chr(0xD7), chr(0xF7)  # the multiplication and division signs
ISSUES = "https://github.com/maheshvaikri-code/contexel/issues"


def _by(rows: List[dict], key: str, value: str) -> dict:
    for row in rows:
        if row[key] == value:
            return row
    raise KeyError(value)


def _p(value: float) -> str:
    return f"{value:.0f}"


def within_budget_on_average(fill: float) -> bool:
    """"Fill at most 1.00" as the tables show it: the mean fill rounded to two decimals. The
    report's list of full rows and publish.py's highlighting and claims use this one rule."""
    return round(fill, 2) <= 1


def _list(items: Sequence[str]) -> str:
    return ", ".join(items) if items else "-"


def glance_rows(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One row per outcome implementation, joining timing, outcome and footprint."""
    task = {r["impl"]: r for r in results["task"]}
    foot = {f["library"]: f for f in results["footprint"]}
    ops = {o["impl"]: o for o in results["operations"]}
    rows = []
    for o in results["outcomes"]:
        name = o["impl"]
        t, f = task.get(name), foot.get(name)
        rows.append({
            "impl": name,
            "ops": ops[name]["label"],
            "ms": t["ms"] if t and t["ms"] is not None else "-",
            "ms_ep": o["ms_per_episode"],
            "recall": f"{_p(o['recall_strong_pct'])} / {_p(o['recall_weak_pct'])}",
            "compliance_pct": o["compliance_pct"],
            "fill_x": o["fill_x"],
            "useful_share_pct": o["useful_share_pct"],
            "import_ms": f["import_ms"] if f else "-",
            "deps": f["transitive_deps"] if f else "-",
        })
    return rows


def render_report(results: Dict[str, Any]) -> str:
    d, s = results["dataset"], results["settings"]
    out_rows, inflected = results["outcomes"], results["inflected"]
    glance = glance_rows(results)
    k = f"{d['records'] // 1000}k"
    contexel_o = _by(out_rows, "impl", "contexel")
    hand_o = _by(out_rows, "impl", "hand-written")
    scored_o = _by(out_rows, "impl", "hand-written (term overlap)")
    toolz_o = _by(out_rows, "impl", "toolz")
    lc_o = _by(out_rows, "impl", "langchain-core")
    llama_o = _by(out_rows, "impl", "llama-index-core")
    ops = {o["impl"]: o for o in results["operations"]}
    timed_ops = len(TIMED_OPS)
    # Full marks without the Compliance column: the record kept under both signals, contexts
    # within the budget on average (Fill at most 1) and no tokens on duplicates or bloat.
    all_full = [
        r["impl"] for r in out_rows
        if r["recall_strong_pct"] == 100 and r["recall_weak_pct"] == 100
        and within_budget_on_average(r["fill_x"]) and r["useful_share_pct"] == 100
    ]
    sample = (f"{s['episodes']} episodes and one episode seed"
              + (": a gap of a few points is a few episodes." if s["episodes"] == 100 else "."))
    within = "the rows whose every context fits the budget as the estimator counts it"
    compliant = [g for g in glance if g["compliance_pct"] == 100]
    slowest = max(compliant, key=lambda g: g["ms_ep"])
    if slowest["impl"] == "contexel":
        slow_line = f"contexel is the slowest of {within} ({slowest['ms_ep']:.1f} ms)"
    else:
        slow_line = (f"the slowest of {within} is {slowest['impl']} "
                     f"({slowest['ms_ep']:.1f} ms); contexel's is "
                     f"{contexel_o['ms_per_episode']:.1f} ms")
    cutoff = s["llama_cutoff"]
    cutoff_line = (
        f"The cutoff ({cutoff}) removes nothing under the strong signal, where every score is "
        f"at least {MIN_STRONG_SCORE}; under the weak signal it drops the hits whose raw count "
        "is below it." if cutoff < MIN_STRONG_SCORE else
        f"The cutoff ({cutoff}) applies under both signals.")
    fill_header = f"Fill {_TIMES} (estimated tokens {_DIVIDE} budget)"

    ops_table = table(
        [{
            "impl": o["impl"], "native": o["label"], "glue": _list(o["glue"]),
            "missing": _list(o["missing"]), "other": _list(o["other_native"]),
            "adapters": _list(o["adapters"]), "operand": o["operand"],
        } for o in results["operations"]],
        [("impl", "Implementation"), ("native", "Native operations"),
         ("glue", "Done by hand-written glue"), ("missing", "Not done at all"),
         ("other", "Other native steps"), ("adapters", "Operand conversion"),
         ("operand", "Operand")],
    )
    not_run_table = table(NOT_RUN, [
        ("library", "Library"), ("select", "select"), ("dedupe_key", "dedupe(key)"),
        ("rescore_lex", "rescore(lexical)"), ("rank", "rank"),
        ("truncate_tok", "truncate(tok)"), ("trim_budget", "trim(budget)"),
        ("merge_schema", "merge(schema)"), ("operand", "Operand"), ("ran", "Status"),
    ])
    inflected_table = table(
        [{"shaper": r["shaper"], "orig": r["recall_original_pct"],
          "infl": r["recall_inflected_pct"]} for r in inflected["rows"]],
        [("shaper", "Shaper"), ("orig", "Recall % (original terms)"),
         ("infl", "Recall % (inflected terms)")],
    )
    word_row = _by(inflected["rows"], "shaper", "contexel")
    stem_row = _by(inflected["rows"], "shaper", "contexel (match=stem)")
    scored_row = _by(inflected["rows"], "shaper", "hand-written (term overlap)")
    trust_row = _by(inflected["rows"], "shaper", "hand-written")
    lost = word_row["recall_original_pct"] - stem_row["recall_original_pct"]
    cost_line = (
        f" Opting in to the stemmer costs {lost:g} point{'s' if lost != 1 else ''} "
        f"on the original terms." if lost > 0 else "")
    examples = ", ".join(f"`{a}` -> `{b}`" for a, b in inflected["examples"])
    deterministic = all(r["deterministic"] == "yes" for r in results["task"])
    contexel_t = _by(results["task"], "impl", "contexel")
    others_native = max(
        int(r["native"].split("/")[0]) for r in results["task"] if r["impl"] != "contexel")
    contexel_native = int(contexel_t["native"].split("/")[0])
    only_full = contexel_native == timed_ops and others_native < timed_ops

    same_recall = contexel_o["recall_strong_pct"] == contexel_o["recall_weak_pct"]
    same_scored = scored_o["recall_strong_pct"] == scored_o["recall_weak_pct"]

    return f"""# contexel and other libraries: comparative benchmark

Numbers generated {results["generated"]} by `python -m benchmarks.competitors`; the report text
is rendered from `benchmarks/COMPARISON.json`. `tools/check_benchmark_numbers.py`
fails when the README or the site disagree with it.

This benchmark was written by contexel's author. The comparison wirings are our
best effort, one dataset, {s["episodes"]} episodes; corrections from the maintainers of the
compared libraries are welcome ([open an issue]({ISSUES})).

Environment: Python {results["environment"]["python"]} on {results["environment"]["platform"]},
contexel {results["environment"]["contexel"]}; toolz {results["environment"]["libraries"]["toolz"]},
langchain-core {results["environment"]["libraries"]["langchain-core"]}, llama-index-core
{results["environment"]["libraries"]["llama-index-core"]}. The `benchmarks` extra does not pin
these versions; to install the ones measured here, add the constraints file:
`pip install -e ".[benchmarks]" -c benchmarks/constraints.txt`.

**Dataset (public):** [CodeSearchNet](https://huggingface.co/datasets/code-search-net/code_search_net)
python/test split in full ({d["rows"]:,} rows) via the Hugging Face parquet export
(`benchmarks/fetch_dataset.py`, which verifies the committed SHA-256
`{d["sha256"]}` before anything is read). The functions are real; the tool calls
are simulated: {d["queries"]} fixed, overlapping substring searches over the corpus, hit
lists capped at {d["per_query_cap"]}/query -> {d["records"]:,} records. Almost all of
the duplicates are the same function matched by several searches; a few are different
functions from different repositories that share a path and a symbol.

**Canonical task:** project {s["fields"]} fields, dedupe by (path, symbol),
clip `snippet` to ~{s["snippet_cap"]} tokens, rank by score, fit a {s["budget"]:,}-token
budget.

**Tokens:** every budget, cap and price in this benchmark, and the Fill and Useful
columns, are counted with contexel's default estimator (about four characters per
token), the same one the hand-written glue uses. The estimator is for soft budgeting: a
hard limit needs an exact tokenizer (`contexel[accurate]` and `tokens.use_tiktoken()`,
or the provider's own counter). Measured with an exact tokenizer, most of the contexts
that fill the budget here run over the estimated budget by a noticeable margin (the size is
not generated by this benchmark).

**Fairness, and its limits:** in the timed canonical task every implementation missing
a native stage uses the *same* hand-written glue helpers. The hand-written rows stand in
for shaping code written per task (one trusting the tool's score, one with its own
term-overlap scorer). The task is contexel's own six stages and it is scored with
contexel's estimator, field list and dedupe key, so it measures how much of that task
each library covers in these wirings, not how good each library is at its own job.
Semantic tools are not run (what their documentation offers is listed under
"Operations"): contexel concedes semantic quality by design.

## At a glance — all the benchmarks clubbed

One row per implementation, joining the tables below: **native operations**
(how many of the outcome task's six operations — select, dedupe, rescore,
truncate, rank, trim — the library performed itself in the wiring this benchmark
chose: see "Operations" below), **speed** on the
{d["records"]:,}-record canonical task, the ground-truth **outcome** metrics (recall under a
strong / weak retrieval signal; *fill* = mean estimated context tokens {_DIVIDE} the
{s["eval_budget"]:,}-token budget, over 1.00 when the contexts run over it; *useful* =
share of context tokens on needed fields of unique records), and **footprint**
(import time; transitive deps = the installed dependency closure, no extras).

{table(glance, [
    ("impl", "Implementation"), ("ops", "Native ops (in this wiring)"),
    ("ms", f"ms @{k}"), ("ms_ep", "ms/episode"), ("recall", "Recall % s/w"),
    ("fill_x", fill_header),
    ("useful_share_pct", "Useful %"), ("import_ms", "Import ms"),
    ("deps", "Transitive deps"),
])}

Recall columns come from the ground-truth outcome benchmark, where contexel's
standard contract includes `rescore` (relevance derived from the query, not
trusted from the tool); `ms @{k}` is the query-free canonical task, which has no
rescore stage ("-" where a row has no timed task).

- On this task, defined by contexel's six stages and scored with contexel's
  estimator, field list and dedupe key, the rows that keep the needed record under
  both retrieval signals, stay within the budget on average as the estimator counts it
  (Fill at most 1.00) and spend no tokens on duplicates or bloat: {_list(all_full)}.
- `ms/episode` is the mean wall time per episode of the shaping plus the benchmark's
  own scoring of the result (one pass), so a row whose contexts are very large also
  pays for scoring them: {slow_line}. contexel does the most per episode (projecting
  fields, deduping on a key, deriving relevance from each record's own text with
  batch IDF, saturating term frequency and in-order proximity, clipping, ranking,
  enforcing the budget stage by stage); a cheaper row is cheaper by doing less.
  Every cap and price is computed with the active tokenizer, here the default
  estimate of ~4 characters per token, the same estimate the hand-written glue
  uses.
- These timings are from one run on one machine ("best of 5" within the run
  where a column says so, and the import time is the median of
  {IMPORT_REPEATS} fresh interpreters): they are published as measured, and they vary with
  the machine's load and from run to run. The recall, fill and useful-share columns
  do not vary.

## Operations: native versus hand-written, in the wiring this benchmark chose

Each implementation is an ordered list of steps (`benchmarks/competitors.py`).
A step is **native** when running it enters a Python function of the library's own
package, **glue** when it is hand-written code in this benchmark, and an
**adapter** when it only converts the operand to the shape the library requires.
Whether a step enters library code is detected automatically (`benchmarks/opcount.py`
runs each step over a small fixed sample); which library functions each implementation
uses, and which operation each step serves, are the benchmark author's choices. The
counts therefore describe these wirings, not what each library can do. The hand-written
rows do their operations in plain code (see the table), so their 0/6 counts library steps
only and is zero by definition. Other wirings exist and are not counted here: toolz's
`topk` and `accumulate` can express a rank and a running budget cut; for langchain-core,
a Python sort can come before `trim_messages`, and `langchain_core.indexing.index` dedupes
documents at ingestion (it needs a vector store and a record manager); and llama-index-core
has metadata exclusion (`excluded_llm_metadata_keys`), ingestion dedupe
(`IngestionPipeline` with a docstore) and a token-limited chat memory
(`llama_index.core.memory.Memory` with a `token_limit`, which replaces the deprecated
`ChatMemoryBuffer`).

{ops_table}

Libraries this benchmark does not run (what their documentation says; they are
not counted above):

{not_run_table}

## Canonical task on real records

{table(results["task"], [
    ("impl", "Implementation"), ("native", f"Native stages (of {timed_ops}, in this wiring)"),
    ("ms", "ms (best of 5)"), ("kept", "Records kept"),
    ("tokens_out", "Tokens out"), ("deterministic", "Deterministic"),
])}

For langchain-core and llama-index-core most of this time is converting the records to
the library's message or node type (and, for llama-index-core, back): in llama-index-core's
row the only llama-index code that runs is building and unbuilding its node objects, and
langchain-core's one native step is `trim_messages`.

## What each achieves natively (ground-truth outcome benchmark)

The tables above hold the *policy* constant and let glue fill the gaps. This
one asks **was the output useful?** and lets each library act only through the
operations this benchmark wired for it (listed above): a different wiring can change
these rows, and they do not rate the libraries at their own jobs. {s["episodes"]} episodes with
known ground truth: a target function, plus the hit list a
multi-term docstring search over the full corpus returns (the target is
always present in the raw hits, so every miss below is a *shaping* loss, not
a retrieval loss). Budget: {s["eval_budget"]:,} tokens, as the default estimator counts
them. The queries are the target's own words: up to the first three whitespace-separated
tokens of its docstring that are at least five characters long (measured before
stripping), lower-cased and stripped of surrounding periods, commas, parentheses, quotes
and backticks, in their order. The next section changes the words.
{sample}

Every hit carries two retrieval scores, because outcome quality depends on
the ranking signal the search tool hands the shaper: **strong** ranks
matching all the query's terms above matching one term often (the shape a
real multi-term search returns); **weak** is a raw substring count, which
buries the target under term-happy decoys. The two signals differ only in the score
value: the hit lists arrive in the same order under both (per search term, by the weak
count), so a row that never reads the score has identical columns by construction.

- **Recall@budget** — the record the agent actually needed survived into the
  final context, under each signal.
- **Fill** — mean estimated context tokens {_DIVIDE} budget (over 1.00 = the contexts
  run over the budget).
- **Useful share** — fraction of context tokens spent on needed fields of
  first-occurrence records (the rest is duplicates and field bloat). The needed fields
  and the dedupe key are contexel's, so a row that projects to those fields and dedupes
  on that key scores 100% by construction. A context that is empty counts as fully
  useful by the current scoring. langchain-core returns an empty context in a large share
  of the episodes (when its first record alone exceeds the budget), so this scoring
  flatters its useful share (the share over its non-empty contexts is lower; neither
  figure is generated by this benchmark).

{table(out_rows, [
    ("impl", "Implementation"),
    ("recall_strong_pct", "Recall % (strong)"),
    ("recall_weak_pct", "Recall % (weak)"),
    ("fill_x", fill_header),
    ("useful_share_pct", "Useful share %"), ("ms_per_episode", "ms/episode"),
])}

What the numbers say, row by row:

- **contexel** (select, dedupe, `rescore`, truncate, rank, trim): recall
  {_p(contexel_o["recall_strong_pct"])}% / {_p(contexel_o["recall_weak_pct"])}%, fill
  {contexel_o["fill_x"]:.2f}, useful share {_p(contexel_o["useful_share_pct"])}%.{" Its two recall columns are identical by construction: `rescore` replaces the tool's score with relevance derived from the query and the records' own fields (batch BM25: exact word tokens, IDF x saturating tf, in-order proximity), and the two signals differ only in that score. This shows that `rescore` does not depend on the tool's score; any row that ignores the score has equal columns." if same_recall else " Its recall differs between the two signals."}
- **hand-written** is the same pipeline written by hand: it trusts
  the tool's score, so its recall tracks that score's quality
  ({_p(hand_o["recall_strong_pct"])}% / {_p(hand_o["recall_weak_pct"])}%). It stands in for
  shaping code a model writes per task; when such code is rewritten, its field choices
  and truncation can differ (a claim, not measured here).
- **hand-written (term overlap)** adds a scorer such code might write:
  recall {_p(scored_o["recall_strong_pct"])}% / {_p(scored_o["recall_weak_pct"])}%{" (the two columns agree because it, too, ignores the tool's score)" if same_scored else ""}.
  This is the closest comparison for `rescore` in this benchmark (another rescorer, not
  none), with one caveat: contexel's lead over it comes from `rescore`'s in-order proximity
  bonus. The episode queries keep the target's word order, which that bonus rewards, and
  with the bonus switched off contexel's recall on these episodes is below the
  term-overlap baseline's (this benchmark does not generate that row).
- Recall@budget has a ceiling no shaper escapes, semantic or not: when a
  query legitimately describes more records than the budget can hold, some
  valid record is cut. Where contexel's recall in these tables falls short
  of 100%, that is most likely this ambiguity (not analysed per episode).
- **toolz** performs {len(ops["toolz"]["native"])} of the six operations
  ({_list(ops["toolz"]["native"])}) in this wiring; no step here performs
  {_list(ops["toolz"]["missing"])}, so the context runs over the budget by the fill factor
  shown ({toolz_o["fill_x"]:.1f}x). toolz has no token concept, but its `topk` and
  `accumulate` can express a rank and a budget cut (not wired here). In this wiring it
  does fast lossless projection and dedupe and leaves the budget to something else.
- **langchain-core** in this wiring: `trim_messages` ({_list(ops["langchain-core"]["native"])})
  over the raw records wrapped as messages. `trim_messages` trims a message list to a
  token count; it does not see the records inside a message, and no langchain-core step
  in this wiring projects or dedupes them, so the budget fills with field bloat and
  duplicates that its own operations here do not remove (useful share
  {lc_o["useful_share_pct"]:.1f}%). This langchain-core wiring never reads the score (the
  outcome rows get no Python glue, and no langchain-core step in it ranks records), so
  whether the target makes the cut depends on the incoming order, the same weak per-term
  order under both signals (recall {_p(lc_o["recall_strong_pct"])}%); with a Python sort by
  score before the same `trim_messages`, its recall would be much higher under the strong
  signal and much lower under the weak one (not wired here).
- **llama-index-core** offers related operations on its node, text and chat-message types:
  a score cutoff (`SimilarityPostprocessor`), a score-ordered reorder (`LongContextReorder`),
  rerankers with `top_n`, metadata exclusion, docstore dedupe, `PromptHelper` (shortens
  every text chunk evenly to fit the context window) and a token-limited chat memory
  (`llama_index.core.memory.Memory`). This benchmark wires two of them
  (the score cutoff and the reorder) and counts neither as one of the six stages.
  {cutoff_line} No budget step is wired, so recall
  ({_p(llama_o["recall_strong_pct"])}%) comes from keeping nearly everything, at a fill
  factor of {llama_o["fill_x"]:.1f}x; llama-index-core's response synthesizers fit text to the
  context window with `PromptHelper`, which this wiring does not use.

## Inflected-query episodes (inflection robustness, not semantic paraphrase)

The episodes above query with the target's own words, so exact-word matching
is never tested: a query saying "parse" always meets a document saying "parse".
These {inflected["episodes"]} episodes keep the same kind of hit lists (the
retrieval tool searched with the target's original terms) but hand the shaper a
deterministic **inflection** of each term ({examples}). An exact-word
shaper fails on them by construction; a stem-matching one is *measured*, not
assumed. The rule (`benchmarks/inflection.py`) is three lines, and a term is
used only when it is a plain lower-case word, its inflection differs from it,
the frozen stemmer maps both to one stem, and the inflection is not a word of
the target's own text. The inflections are synthetic — some are words nobody
writes — so this measures what the stemmer reaches on inflection and nothing
else: **not synonyms, not paraphrase, not meaning.**

{inflected_table}

- `rescore(match="word")` (the default): {_p(word_row["recall_original_pct"])}% with the
  original terms, {_p(word_row["recall_inflected_pct"])}% with the inflected ones.
- `rescore(match="stem")`: {_p(stem_row["recall_original_pct"])}% with the original terms,
  {_p(stem_row["recall_inflected_pct"])}% with the inflected ones.{cost_line}
- The hand-written term-overlap scorer matches whole words too:
  {_p(scored_row["recall_original_pct"])}% with the original terms,
  {_p(scored_row["recall_inflected_pct"])}% with the inflected ones.
- The hand-written baseline that trusts the tool's score never reads the query,
  so inflection cannot touch it: {_p(trust_row["recall_original_pct"])}% and
  {_p(trust_row["recall_inflected_pct"])}% (it is the control).

## Footprint

Import time is the median of {IMPORT_REPEATS} fresh interpreters, each importing
only the library's top-level package (interpreter start-up excluded; the modules a
task uses can cost more, and the time varies with the machine's load). Transitive
deps counts the installed distributions the package requires, recursively: the
installed closure, with environment markers evaluated for this machine and no extras.

{table(results["footprint"], [
    ("library", "Library"), ("import_ms", "Import ms"),
    ("transitive_deps", "Transitive deps"),
])}

## Reading the results

- {"In the wirings used here, no library in the timed set performs more than " + str(others_native) + f" of the {timed_ops} stages natively on tool-output records; contexel is the only {timed_ops}/{timed_ops} (its stages define the task)." if only_full else "Native stages in the timed set: see the table above."} That
  coverage of this task, not raw speed, is what this comparison tests.
- contexel is slower than the hand-written glue on this task. Its time includes
  the checks each stage runs on its input and the pipeline's plumbing (how much
  of the gap each accounts for is not measured), while the cuts are of the same
  kind. Both clip and price with the ~4 characters per token estimate here;
  `truncate_field` finds the longest prefix that fits the cap in closed form for
  the built-in estimator and by binary search for a custom tokenizer. All rows
  are microseconds per record — negligible next to a single model call.
- {"All timed implementations are deterministic on this task: mechanical shaping is reproducible whoever provides it." if deterministic else "At least one timed implementation was NOT deterministic on this task: see the table."}
  What contexel adds is a fixed, versioned contract: shaping code a model writes per
  task can differ each time it is rewritten (a claim, not measured here), and the
  semantic alternatives depend on a model; these libraries' primitives are not the
  source of nondeterminism.
- `context-engineering-toolkit` was not on PyPI as of 2026-11-26
  (`pip index versions context-engineering-toolkit` finds no distribution). Other
  standalone context-shaping libraries exist, for example keli-wen/context-kit (GitHub)
  and `ctxeng` (PyPI); this benchmark did not run them.
"""


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main() -> None:
    print("building tool output from CodeSearchNet ...")
    results = collect()
    here = Path(__file__).resolve().parent
    _write(here / "COMPARISON.json", json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    _write(here / "COMPARISON.md", render_report(results))
    print(f"wrote {here / 'COMPARISON.json'} and {here / 'COMPARISON.md'}")


if __name__ == "__main__":
    main()
