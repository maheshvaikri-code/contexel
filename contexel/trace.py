"""Per-stage observability: see what each stage did to your context budget.

Wrap a sequence of stage calls in :func:`trace` and every stage records its
input/output record counts and tokens before/after. Tracing is opt-in and costs
nothing when no trace is active.
"""
from __future__ import annotations

import contextvars
import functools
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from . import tokens

_current: "contextvars.ContextVar[Optional[Trace]]" = contextvars.ContextVar(
    "contexel_trace", default=None
)


@dataclass
class Entry:
    stage: str
    in_count: int
    out_count: int
    tokens_before: int
    tokens_after: int
    dropped_ids: List[Any] = field(default_factory=list)


@dataclass
class Trace:
    entries: List[Entry] = field(default_factory=list)
    policies: List[str] = field(default_factory=list)  # pipeline fingerprints
    id_field: Optional[str] = None

    def _add(self, stage: str, in_count: int, out_count: int,
             tokens_before: int, tokens_after: int,
             dropped_ids: Optional[List[Any]] = None) -> None:
        self.entries.append(Entry(stage, in_count, out_count,
                                  tokens_before, tokens_after,
                                  dropped_ids or []))

    @property
    def tokens_before(self) -> int:
        return self.entries[0].tokens_before if self.entries else 0

    @property
    def tokens_after(self) -> int:
        return self.entries[-1].tokens_after if self.entries else 0

    @property
    def reduction(self) -> float:
        """Fraction of tokens removed across the traced stages, 0.0-1.0."""
        before = self.tokens_before
        return 0.0 if before == 0 else 1.0 - (self.tokens_after / before)

    def report(self) -> str:
        if not self.entries:
            return "(no stages traced)"
        lines = [
            f"{e.stage:<16} {e.in_count:>5} -> {e.out_count:<5} "
            f"{e.tokens_before:>7,} -> {e.tokens_after:<7,} tokens"
            for e in self.entries
        ]
        lines.append("-" * 56)
        pct = round(self.reduction * 100)
        lines.append(
            f"{'total':<16} {'':>5}    {'':<5} "
            f"{self.tokens_before:>7,} -> {self.tokens_after:<7,} tokens  ({pct}% reduction)"
        )
        return "\n".join(lines)

    def audit(self) -> dict:
        """A JSON-able governance record of this run: which policy versions
        shaped the context (pipeline fingerprints), what every stage did,
        and — when the trace was opened with ``id_field`` — which records
        each stage dropped, attributed by that field's value (the stage name
        is the removal reason; records lacking the field are untracked).
        """
        return {
            "policies": list(self.policies),
            "id_field": self.id_field,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "reduction": round(self.reduction, 4),
            "stages": [
                {
                    "stage": e.stage,
                    "records_in": e.in_count,
                    "records_out": e.out_count,
                    "tokens_before": e.tokens_before,
                    "tokens_after": e.tokens_after,
                    "dropped_ids": list(e.dropped_ids),
                }
                for e in self.entries
            ],
        }


class _TraceContext:
    def __init__(self, id_field: Optional[str] = None) -> None:
        self.trace = Trace(id_field=id_field)
        self._token: Any = None

    def __enter__(self) -> Trace:
        self._token = _current.set(self.trace)
        return self.trace

    def __exit__(self, *exc: Any) -> None:
        _current.reset(self._token)


def trace(id_field: Optional[str] = None) -> _TraceContext:
    """Context manager. Within it, every stage records what it did.

    Pass ``id_field`` (e.g. ``"url"``, ``"path"``) to additionally record
    *which* records each stage dropped, by that field — the audit trail for
    "did the relevant context even reach the model?". Attribution is by the
    id value: records lacking the field are untracked, and keeping the id
    field in every ``select`` gives full attribution. Example::

        with trace(id_field="url") as t:
            r = pipeline([
                stage(dedupe, key="url"),
                stage(trim_to_budget, max_tokens=1500),
            ])(r)
        print(t.report())
        log.info(t.audit())   # policies, per-stage drops, token movement
    """
    return _TraceContext(id_field)


def current_trace() -> Optional[Trace]:
    """The trace currently in effect, or ``None``."""
    return _current.get()


def traced(fn: Callable) -> Callable:
    """Decorator: auto-record a stage's effect when a trace is active; zero cost otherwise."""

    @functools.wraps(fn)
    def wrapper(records, *args: Any, **kwargs: Any):
        tr = _current.get()
        if tr is None:
            return fn(records, *args, **kwargs)
        before_n = len(records)
        before_tok = tokens.count(records)
        out = fn(records, *args, **kwargs)
        dropped: list = []
        if tr.id_field and isinstance(out, list):
            fid = tr.id_field

            def id_key(value: Any) -> Any:
                try:
                    hash(value)
                    return value
                except TypeError:
                    return repr(value)

            remaining: dict = {}
            unidentified = 0  # surviving records without the id field
            for r in out:
                if isinstance(r, dict) and fid in r:
                    key = id_key(r[fid])
                    remaining[key] = remaining.get(key, 0) + 1
                else:
                    unidentified += 1
            for r in records:
                if isinstance(r, dict) and fid in r:
                    original = r[fid]
                    key = id_key(original)
                    if remaining.get(key, 0) > 0:
                        remaining[key] -= 1
                    elif unidentified > 0:
                        # a survivor lost the id field (e.g. select dropped
                        # it) — that is not a dropped record
                        unidentified -= 1
                    else:
                        dropped.append(original)
        tr._add(getattr(fn, "__name__", "stage"),
                before_n, len(out), before_tok, tokens.count(out), dropped)
        return out

    return wrapper
