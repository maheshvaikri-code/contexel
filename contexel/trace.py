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


@dataclass
class Trace:
    entries: List[Entry] = field(default_factory=list)

    def _add(self, stage: str, in_count: int, out_count: int,
             tokens_before: int, tokens_after: int) -> None:
        self.entries.append(Entry(stage, in_count, out_count, tokens_before, tokens_after))

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


class _TraceContext:
    def __init__(self) -> None:
        self.trace = Trace()
        self._token: Any = None

    def __enter__(self) -> Trace:
        self._token = _current.set(self.trace)
        return self.trace

    def __exit__(self, *exc: Any) -> None:
        _current.reset(self._token)


def trace() -> _TraceContext:
    """Context manager. Within it, every stage records what it did.

    Example::

        with trace() as t:
            r = dedupe(r, key="url")
            r = trim_to_budget(r, max_tokens=1500)
        print(t.report())
    """
    return _TraceContext()


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
        tr._add(getattr(fn, "__name__", "stage"),
                before_n, len(out), before_tok, tokens.count(out))
        return out

    return wrapper
