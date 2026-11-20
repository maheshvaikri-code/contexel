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
from collections.abc import Mapping
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from . import tokens
from .errors import (
    ConfigError,
    InputShapeError,
    _kind,
    check_bool,
    check_choice,
    check_fields,
    check_non_negative_int,
    check_query,
    check_str,
    invalid_value,
)
from .trace import traced
from .validate import checked

Record = Dict[str, Any]
Records = List[Record]

Fields = Union[str, Sequence[str]]


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


@checked(mapping=True)
@traced
def select(records: Records, fields: Fields) -> Records:
    """Keep only ``fields`` on each record. The fastest way to cut tool-output bloat.

    A bare string means ONE field, not its characters.
    """
    keep = check_fields(fields, "select")
    return [{k: r[k] for k in keep if k in r} for r in records]


@checked(mapping=lambda args: args.get("key") is not None)
@traced
def dedupe(records: Records, key: Optional[Union[str, Sequence[str]]] = None) -> Records:
    """Drop duplicate records, keeping the first occurrence and preserving order.

    ``key=None`` dedupes on the whole record; a str or list of strs dedupes on
    those field(s).
    """
    keys: Optional[List[str]] = (
        None if key is None else check_fields(key, "dedupe", "key"))

    seen = set()
    out: Records = []
    for r in records:
        fp = _dedupe_fp(r if keys is None else [r.get(k) for k in keys])
        if fp in seen:
            continue
        seen.add(fp)
        out.append(r)
    return out


@checked(mapping=lambda args: isinstance(args.get("by"), str))
@traced
def rank(records: Records, by: Union[str, Callable[[Record], Any]], desc: bool = True) -> Records:
    """Sort records by a field name or key function. Records missing the field go last.

    Use before :func:`trim_to_budget` so the least important records are dropped.
    Values of ``by`` must be mutually comparable.
    """
    if not (isinstance(by, str) or callable(by)):
        raise invalid_value("rank", "by", "by must be a field name or a key "
                            f"function, got {type(by).__name__}")
    check_bool(desc, "rank", "desc")
    if callable(by):
        return sorted(list(records), key=by, reverse=desc)
    present = [r for r in records if by in r]
    missing = [r for r in records if by not in r]
    present.sort(key=lambda r: r[by], reverse=desc)
    return present + missing


def _allow_key(value: Any) -> Any:
    """Membership key for :func:`allowlist` (ADR-004): a bool never equals a
    number, so ``True`` cannot pass a gate that approved ``1``. ``int`` and
    ``float`` still compare by value (``1 == 1.0``) because TypeScript cannot
    tell them apart."""
    return (isinstance(value, bool), value)


@checked(mapping=True)
@traced
def allowlist(records: Records, field: str, allowed: Union[Any, Sequence[Any]]) -> Records:
    """Provenance gate: keep only records whose ``field`` value is in
    ``allowed``. The strongest injection control a shaper can offer is
    refusing content from sources you did not approve — apply this FIRST,
    before any relevance logic, so untrusted records never compete for the
    budget. A bare string for ``allowed`` is ONE allowed value (never its
    characters). A bool never equals a number (``True`` does not pass
    ``allowed=[1]``). Fail closed: a record carrying an unhashable value is
    dropped, and a record missing the field reads as ``None`` — dropped
    unless ``None`` is explicitly in ``allowed``. Deterministic; dropped
    records appear in the trace/audit with this stage as the reason.
    """
    check_str(field, "allowlist", "field")
    values = [allowed] if isinstance(allowed, str) else allowed
    if not isinstance(values, (list, tuple, set, frozenset)):
        raise invalid_value(
            "allowlist", "allowed",
            f"allowed must be a string or a list of values, got "
            f"{type(allowed).__name__}")
    try:
        allowed_keys = {_allow_key(a) for a in values}
    except TypeError:
        raise invalid_value("allowlist", "allowed",
                            "allowed contains an unhashable value") from None
    out: Records = []
    for r in records:
        try:
            ok = _allow_key(r.get(field)) in allowed_keys
        except TypeError:
            ok = False  # an unhashable record value fails closed
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

# the built-ins are trusted and compiled together, once; every caller pattern
# is compiled on its own so it cannot change how the built-ins are read
_BUILTIN_MATCHER = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

# exact types whose repr() equals their str(): no need to compute the repr
_REPR_IS_STR = (int, float, bool, type(None))


def _scan_text(value: Any) -> str:
    """The text a quarantine pattern is matched against for one field value.

    A string is used as is. A container contributes its dict keys (code-point
    order) and its leaves, each as text, joined by a single space — so a
    marker split by a newline or a quote inside a nested value is still found
    (``str(value)`` would have rendered the newline as a backslash and an
    ``n``). Every other leaf -- numbers, booleans, ``None`` (``"None"``), any
    object -- is scanned as its ``str()`` text, plus its ``repr()`` when that
    differs (an object may show text in only one of the two; for JSON scalars
    they agree). Iterative,
    and each container is expanded once, so neither a deeply nested nor a
    self-referencing value can exhaust the stack or loop.
    """
    parts: List[str] = []
    stack: List[Any] = [value]
    seen: set = set()
    while stack:
        v = stack.pop()
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, dict):
            if id(v) in seen:
                continue
            seen.add(id(v))
            for k in sorted(v, key=str, reverse=True):
                stack.append(v[k])
                stack.append(str(k))
        elif isinstance(v, (list, tuple)):
            if id(v) in seen:
                continue
            seen.add(id(v))
            stack.extend(reversed(v))
        else:
            text = str(v)
            parts.append(text)
            # exact int/float/bool/None have repr == str: skip the second call
            if type(v) not in _REPR_IS_STR:
                rep = repr(v)
                if rep != text:  # an object may show text in only one of the two
                    parts.append(rep)
    return " ".join(parts)


@checked(mapping=True)
@traced
def quarantine(records: Records, fields: Fields = ("snippet",),
               patterns: Optional[Fields] = None,
               action: str = "drop", into: str = "quarantined",
               replace_patterns: bool = False) -> Records:
    """Deterministic tripwire for the crudest prompt-injection markers
    ("ignore all previous instructions", role-reset phrases, system-prompt
    tags) in the given text ``fields``.

    ``action="drop"`` removes matching records (traced/audited);
    ``action="flag"`` keeps every record and writes a boolean to ``into``
    so downstream policy — or the harness — decides. A record that already
    has the ``into`` key raises ``InputShapeError`` (``input.field_conflict``)
    rather than being silently overwritten; chain two flag passes with
    different ``into`` names.

    Every item must be a mapping: a non-mapping item (a string, list, tuple,
    ``None``, a number) ALWAYS raises ``InputShapeError``
    (``input.not_mapping``), in ``drop`` and ``flag`` mode, strict mode or not
    -- a screen that skips what it cannot read would keep the attack.

    A field whose value is a dict or list is scanned through every depth: its
    keys and leaves (strings as they are; numbers, booleans and None as their
    text) are joined with spaces, so a marker split by a
    newline inside a nested value is still found. ``fields`` must not be
    empty and every pattern must be a valid regex: misconfiguration raises
    ``ConfigError`` instead of leaving a control that quietly does nothing.
    The built-in markers and each caller pattern are compiled SEPARATELY and a
    record is dropped/flagged when ANY of them matches, so a pattern's inline
    flags (``(?a)``, ``(?x)``) and numbered groups or backreferences stay its
    own, and the error names the offending pattern.

    ``patterns`` EXTENDS the built-in marker list — passing your own
    domain markers must never silently disable "ignore all previous
    instructions" detection (a configured-looking call that weakens the
    control is the failure mode this API refuses to have). To genuinely
    replace the built-ins, opt in explicitly with
    ``replace_patterns=True``; an empty replacement list raises rather
    than matching nothing (or everything).

    Honest scope: this is NOT a security boundary. A paraphrased attack
    passes; a benign document quoting an attack trips it. Provenance
    gating (:func:`allowlist`) is the stronger control; this one makes the
    loud, literal cases visible in the audit trail instead of letting them
    compete for the budget silently. Caller-supplied ``patterns`` are
    regex fragments and the caller's responsibility (including their
    complexity and dialect portability). One classic pitfall: ``\\b`` is a
    word boundary, so ``\\b\\.env\\b`` can never match — ``.`` is not a
    word character; screen for ``.env``-style tokens with something like
    ``(^|[\\s"'([/])\\.env\\b`` instead (the ``/`` matters — paths like
    ``config/.env`` are the common form).
    """
    if action not in ("drop", "flag"):
        raise ConfigError(
            "config.invalid_value",
            f"action must be 'drop' or 'flag', got {action!r}",
            stage="quarantine", param="action")
    # fields=[] would scan nothing: a configured-looking control that does
    # nothing is exactly what this stage refuses to be
    field_list = check_fields(fields, "quarantine", allow_empty=False)
    check_str(into, "quarantine", "into")
    check_bool(replace_patterns, "quarantine", "replace_patterns")
    if patterns is None:
        if replace_patterns:
            raise ConfigError(
                "config.contradictory",
                "replace_patterns=True without patterns is contradictory; "
                "pass the replacement patterns",
                stage="quarantine", param="replace_patterns")
        matchers = [_BUILTIN_MATCHER]
    else:
        user_patterns = check_fields(patterns, "quarantine", "patterns")
        if any(not p for p in user_patterns):
            # an empty fragment becomes an empty regex alternative, which
            # matches EVERY record — the opposite of configuring a screen
            raise ConfigError(
                "config.empty",
                "empty pattern fragments match everything; remove them",
                stage="quarantine", param="patterns")
        compiled = []
        for p in user_patterns:
            try:  # each pattern alone: its flags and groups stay its own
                compiled.append(re.compile(p, re.IGNORECASE))
            except re.error as e:
                raise ConfigError(
                    "config.invalid_pattern",
                    f"quarantine: invalid pattern {p!r}: {e}",
                    stage="quarantine", param="patterns") from e
        matchers = (compiled if replace_patterns
                    else [_BUILTIN_MATCHER] + compiled)
    if not matchers:
        raise ConfigError(
            "config.empty",
            "replace_patterns=True with no patterns would disable the "
            "control entirely; pass at least one pattern",
            stage="quarantine", param="patterns")
    out: Records = []
    for i, r in enumerate(records):
        # fail closed: a non-mapping item would otherwise look like "no field
        # present" (``f in r`` is a substring / membership test) and be KEPT
        if not isinstance(r, Mapping):
            raise InputShapeError(
                "input.not_mapping",
                f"quarantine: item {i} must be a mapping, got {_kind(r)}",
                stage="quarantine")
        text = " ".join(_scan_text(r[f]) if f in r else "" for f in field_list)
        hit = any(m.search(text) is not None for m in matchers)
        if action == "flag":
            if into in r:
                raise InputShapeError(
                    "input.field_conflict",
                    f"quarantine: record {i} already has a {into!r} field; "
                    f"pass a different into",
                    stage="quarantine", param="into")
            out.append({**r, into: hit})
        elif not hit:
            out.append(r)
    return out


_TOKEN = re.compile(r"[^\W_]+")  # word tokens; underscores split snake_case


@checked(mapping=True)
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
    check_query(query, "rescore")
    field_list = check_fields(fields, "rescore", allow_empty=False)
    check_str(into, "rescore", "into")
    check_bool(proximity, "rescore", "proximity")
    if match == "stem":
        # reserved for the English stemmer (ADR-006); until it ships, running
        # it as substring matching would be a silent downgrade
        raise invalid_value("rescore", "match",
                            "match 'stem' is not available yet; use 'word' "
                            "or 'substring'")
    check_choice(match, "rescore", "match", ("word", "substring"))
    terms = _TOKEN.findall(query.lower()) if isinstance(query, str) else [
        t for part in query for t in _TOKEN.findall(str(part).lower())
    ]
    terms = list(dict.fromkeys(terms))
    if not terms or not records:
        return [{**r, into: 0.0} for r in records]

    texts = [
        " ".join(str(r.get(f, "")) for f in field_list).lower()
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


@checked(mapping=True)
@traced
def truncate_field(records: Records, field: str, max_tokens: int,
                   tokenizer: Any = None, suffix: str = "\u2026") -> Records:
    """Clip a long text field on each record down to ~``max_tokens``.

    Non-string values pass through untouched.
    """
    check_str(field, "truncate_field", "field")
    check_non_negative_int(max_tokens, "truncate_field", "max_tokens")
    check_str(suffix, "truncate_field", "suffix")
    out: Records = []
    for r in records:
        value = r.get(field)
        if isinstance(value, str):
            r = {**r, field: _truncate_text(value, max_tokens, tokenizer, suffix)}
        out.append(r)
    return out


@checked(mapping=False)
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

    ``max_tokens`` must be an integer >= 0 (``0`` returns ``[]``); ``None``,
    a float, a bool or a negative number raises ``ConfigError``.
    """
    check_non_negative_int(max_tokens, "trim_to_budget", "max_tokens")
    check_non_negative_int(min_records, "trim_to_budget", "min_records")
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
