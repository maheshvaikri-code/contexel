"""Deterministic context-economy stages.

A *record* is a plain ``dict``; a collection is a ``list`` of dicts -- the shape
almost every tool returns. Each stage takes a list of records and returns a new
list, so stages compose by passing one's output into the next. Stages never
mutate their input.

All of these are deterministic and free (no model calls). Model-augmented stages
(relevance ranking, summarization, semantic dedupe) layer on top of these.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from . import tokens
from .trace import traced

Record = Dict[str, Any]
Records = List[Record]

Fields = Union[str, Sequence[str]]


def _field_list(fields: Fields) -> List[str]:
    """A bare string means ONE field, not its characters — the common
    JSON-boundary mistake ``fields="snippet"`` would otherwise silently
    look up fields named "s", "n", "i", ... (mirrors ``dedupe(key=str)``)."""
    return [fields] if isinstance(fields, str) else list(fields)


def _fingerprint(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def _typed_tuple(value: Any) -> Any:
    """A hashable, type-qualified mirror of a value (1, 1.0, and True differ).

    Unordered collections are sorted by repr so equal sets fingerprint
    identically regardless of insertion history or hash seed — set iteration
    order is not deterministic, and a fingerprint must be.
    """
    if isinstance(value, dict):
        return ("dict",
                tuple(sorted((k, _typed_tuple(v)) for k, v in value.items())))
    if isinstance(value, (list, tuple)):
        # one sequence tag: [1, 2] and (1, 2) are the same JSON data, but
        # {} and [] must not collide (untagged, both were the empty tuple)
        return ("list", tuple(_typed_tuple(v) for v in value))
    if isinstance(value, (set, frozenset)):
        return (type(value).__name__,
                tuple(sorted((_typed_tuple(v) for v in value), key=repr)))
    return (type(value).__name__, value)


def _dedupe_fp(value: Any) -> Any:
    """Fast hashable fingerprint; falls back to canonical JSON when needed."""
    try:
        fp = _typed_tuple(value)
        hash(fp)
        return fp
    except TypeError:
        return _fingerprint(value)


@traced
def select(records: Records, fields: Fields) -> Records:
    """Keep only ``fields`` on each record. The fastest way to cut tool-output bloat."""
    keep = _field_list(fields)
    return [{k: r[k] for k in keep if k in r} for r in records]


@traced
def dedupe(records: Records, key: Optional[Union[str, Sequence[str]]] = None) -> Records:
    """Drop duplicate records, keeping the first occurrence and preserving order.

    ``key=None`` dedupes on the whole record; a str or list of strs dedupes on
    those field(s).
    """
    if isinstance(key, str):
        keys: Optional[List[str]] = [key]
    elif key is None:
        keys = None
    else:
        keys = list(key)

    seen = set()
    out: Records = []
    for r in records:
        fp = _dedupe_fp(r if keys is None else [r.get(k) for k in keys])
        if fp in seen:
            continue
        seen.add(fp)
        out.append(r)
    return out


@traced
def rank(records: Records, by: Union[str, Callable[[Record], Any]], desc: bool = True) -> Records:
    """Sort records by a field name or key function. Records missing the field go last.

    Use before :func:`trim_to_budget` so the least important records are dropped.
    Values of ``by`` must be mutually comparable.
    """
    if callable(by):
        return sorted(list(records), key=by, reverse=desc)
    present = [r for r in records if by in r]
    missing = [r for r in records if by not in r]
    present.sort(key=lambda r: r[by], reverse=desc)
    return present + missing


@traced
def allowlist(records: Records, field: str, allowed: Sequence[Any]) -> Records:
    """Provenance gate: keep only records whose ``field`` value is in
    ``allowed``. The strongest injection control a shaper can offer is
    refusing content from sources you did not approve — apply this FIRST,
    before any relevance logic, so untrusted records never compete for the
    budget. Fail closed: a record carrying an unhashable value is dropped,
    and a record missing the field reads as ``None`` — dropped unless
    ``None`` is explicitly in ``allowed``. Deterministic; dropped records
    appear in the trace/audit with this stage as the reason.
    """
    allowed_set = set(allowed)
    out: Records = []
    for r in records:
        try:
            ok = r.get(field) in allowed_set
        except TypeError:
            ok = False
        if ok:
            out.append(r)
    return out


_INJECTION_PATTERNS = (
    r"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier)\s+"
    r"(?:instructions|messages|prompts|context)",
    r"disregard\s+(?:all\s+|the\s+)?(?:previous|prior|above|earlier)",
    r"you\s+are\s+now\s+",
    r"new\s+instructions\s*:",
    r"system\s+prompt",
    r"</?\s*(?:system|assistant|instructions?)\s*>",
)


@traced
def quarantine(records: Records, fields: Fields = ("snippet",),
               patterns: Optional[Sequence[str]] = None,
               action: str = "drop", into: str = "quarantined") -> Records:
    """Deterministic tripwire for the crudest prompt-injection markers
    ("ignore all previous instructions", role-reset phrases, system-prompt
    tags) in the given text ``fields``.

    ``action="drop"`` removes matching records (traced/audited);
    ``action="flag"`` keeps every record and writes a boolean to ``into``
    so downstream policy — or the harness — decides.

    Honest scope: this is NOT a security boundary. A paraphrased attack
    passes; a benign document quoting an attack trips it. Provenance
    gating (:func:`allowlist`) is the stronger control; this one makes the
    loud, literal cases visible in the audit trail instead of letting them
    compete for the budget silently. Caller-supplied ``patterns`` are the
    caller's responsibility (including their regex complexity).
    """
    if action not in ("drop", "flag"):
        raise ValueError(f"action must be 'drop' or 'flag', got {action!r}")
    field_list = _field_list(fields)
    matcher = re.compile("|".join(patterns or _INJECTION_PATTERNS),
                         re.IGNORECASE)
    out: Records = []
    for r in records:
        text = " ".join(str(r.get(f, "")) for f in field_list)
        hit = matcher.search(text) is not None
        if action == "flag":
            out.append({**r, into: hit})
        elif not hit:
            out.append(r)
    return out


_TOKEN = re.compile(r"[^\W_]+")  # word tokens; underscores split snake_case


@traced
def rescore(records: Records, query: Union[str, Sequence[str]],
            fields: Fields = ("snippet",), into: str = "score",
            proximity: bool = True, match: str = "word") -> Records:
    """Replace the tool's relevance score with a deterministic lexical one.

    Ranking by a tool-provided score means inheriting that tool's ranking
    quality: a weak score buries the record you actually need and a budget
    trim then faithfully cuts it. ``rescore`` derives relevance from the
    ``query`` and the records' own ``fields`` instead — a BM25-style score
    computed within the batch: per-term IDF (rare terms weigh more) times a
    saturating term frequency (k1 = 1.5), so covering *all* the query's terms
    beats repeating one. With ``proximity`` (default on), consecutive query
    terms co-occurring *in order* within an 80-character window earn a bonus
    — the source a query was phrased from usually carries its terms in
    sequence.

    ``match="word"`` (default) counts exact word occurrences, the way BM25 /
    Lucene do — ``value`` does not match ``values`` — with underscores
    treated as boundaries so snake_case splits. ``match="substring"`` counts
    raw substring occurrences instead: more forgiving of morphology, more
    decoy-prone. Writes the score to ``into`` on a copy of each record; use
    before :func:`rank`.

    Deterministic and dependency-free by construction — and therefore
    *lexical*: synonyms and paraphrase are invisible to it. When you need
    semantic relevance, a model reranker belongs in front; this stage removes
    the need to trust a tool's score, not the value of semantics.
    """
    terms = _TOKEN.findall(query.lower()) if isinstance(query, str) else [
        t for part in query for t in _TOKEN.findall(str(part).lower())
    ]
    terms = list(dict.fromkeys(terms))
    if not terms or not records:
        return [{**r, into: 0.0} for r in records]

    texts = [
        " ".join(str(r.get(f, "")) for f in _field_list(fields)).lower()
        for r in records
    ]
    if match == "word":
        # one boundary-guarded alternation, scanned once per text at C speed;
        # underscores count as boundaries, so snake_case splits
        alt = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
        finder = re.compile(rf"(?<![^\W_])(?:{alt})(?![^\W_])").finditer
    n = len(records)
    tfs: List[Dict[str, int]] = []           # one pass: tf per term, df for free
    positions: List[Dict[str, int]] = []     # first char position per term
    df = dict.fromkeys(terms, 0)
    for text in texts:
        row: Dict[str, int] = {}
        first: Dict[str, int] = {}
        if match == "word":
            for found in finder(text):
                t = found.group(0)
                row[t] = row.get(t, 0) + 1
                first.setdefault(t, found.start())
        else:
            for t in terms:
                count = text.count(t)
                if count:
                    row[t] = count
                    first[t] = text.find(t)
        for t in row:
            df[t] += 1
        tfs.append(row)
        positions.append(first)
    idf = {t: math.log((n - df[t] + 0.5) / (df[t] + 0.5) + 1.0) for t in terms}

    k1 = 1.5
    window = 80  # characters, either mode
    out: Records = []
    for r, row, first in zip(records, tfs, positions):
        score = sum(idf[t] * (tf / (tf + k1)) for t, tf in row.items())
        if proximity and len(row) > 1:
            for t1, t2 in zip(terms, terms[1:]):
                if t1 in first and t2 in first:
                    gap = first[t2] - first[t1]
                    if 0 < gap <= window:
                        score += (idf[t1] + idf[t2]) / 4
        out.append({**r, into: round(score, 6)})
    return out


def _truncate_text(text: str, max_tokens: int, tokenizer: Any, suffix: str) -> str:
    if tokens.count(text, tokenizer) <= max_tokens:
        return text
    budget = max(1, max_tokens - tokens.count(suffix, tokenizer))
    if tokens.is_heuristic(tokenizer):
        # ceil(len/4) is invertible: the longest prefix within budget is
        # exactly 4*budget chars — same result as the search, in O(1).
        return text[: 4 * budget].rstrip() + suffix
    # Binary search the longest prefix whose token count fits the budget.
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if tokens.count(text[:mid], tokenizer) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + suffix


@traced
def truncate_field(records: Records, field: str, max_tokens: int,
                   tokenizer: Any = None, suffix: str = "\u2026") -> Records:
    """Clip a long text field on each record down to ~``max_tokens``.

    Non-string values pass through untouched.
    """
    out: Records = []
    for r in records:
        value = r.get(field)
        if isinstance(value, str):
            r = {**r, field: _truncate_text(value, max_tokens, tokenizer, suffix)}
        out.append(r)
    return out


@traced
def trim_to_budget(records: Records, max_tokens: int, tokenizer: Any = None,
                   min_records: int = 0) -> Records:
    """Keep records from the front until the token budget is reached; drop the rest.

    Assumes records are already ordered by importance (e.g. via :func:`rank`). A
    greedy prefix: a record is kept only if adding it stays within ``max_tokens``.
    If even the first record exceeds the budget, the result is empty -- run
    :func:`truncate_field` first for oversized records.

    ``min_records`` guards the silent-failure edge where a too-small budget
    returns ``[]``, indistinguishable from "nothing matched" to the caller:
    the first ``min_records`` records (the best ones, post-:func:`rank`) are
    kept even when they exceed the budget. The overrun is visible in the
    trace/audit token counts.
    """
    out: Records = []
    used = 0
    for r in records:
        cost = tokens.count(r, tokenizer) + 2  # +2 approximates per-item list framing
        if used + cost > max_tokens and len(out) >= min_records:
            break
        out.append(r)
        used += cost
    return out


def merge(*sources: Records,
          schema: Optional[Dict[str, Union[str, Sequence[str]]]] = None,
          dedupe_key: Optional[str] = None) -> Records:
    """Normalize and combine record-lists from different tools into one list.

    ``schema`` maps a unified field name to a source field name, or to a list of
    candidate names tried in order -- handling tools that label the same thing
    differently::

        merge(web, docs, schema={"title": ["title", "name", "headline"],
                                 "url":   ["url", "link", "href"]})

    With ``schema=None`` the sources are concatenated unchanged. ``dedupe_key``
    optionally removes duplicates across the merged result.

    (``merge`` is a combiner / entry point rather than a single-collection
    transform, so it is not auto-traced.)
    """
    combined: Records = []
    for src in sources:
        for r in src:
            if schema is None:
                combined.append(r)
                continue
            mapped: Record = {}
            for unified, candidates in schema.items():
                names = [candidates] if isinstance(candidates, str) else list(candidates)
                for name in names:
                    if name in r:
                        mapped[unified] = r[name]
                        break
            combined.append(mapped)
    if dedupe_key is not None:
        combined = dedupe(combined, key=dedupe_key)
    return combined
