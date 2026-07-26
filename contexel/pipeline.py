"""In-language composition.

This is plain function composition -- not a spec an engine interprets. Any
callable ``records -> records`` (including a bare lambda) is a valid stage, and
you can breakpoint or step inside any of them.

Every pipeline carries a **fingerprint**: a stable hash of its stage names and
bound parameters, exposed as ``pipe.fingerprint`` and recorded into any active
:func:`contexel.trace` -- so an audit trail can say *which version of the
policy* shaped a given context. Coverage, precisely: primitives, lists,
tuples, and dicts are hashed by value; callables by ``__name__`` (distinct
lambdas collide as ``<lambda>`` -- name your key functions); any other object
contributes only its type name. Bind parameters through :func:`stage` when the
fingerprint should cover them; opaque stage callables contribute only their
``__name__``.
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable, Dict, List

from .trace import current_trace

Records = List[Dict[str, Any]]
StageFn = Callable[[Records], Records]


def _stable_repr(value: Any) -> str:
    """A repr that never embeds memory addresses (stable across runs)."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_stable_repr(v) for v in value) + "]"
    if isinstance(value, dict):
        items = sorted(
            value.items(), key=lambda kv: (type(kv[0]).__name__, repr(kv[0]))
        )
        return "{" + ",".join(
            f"{k!r}:{_stable_repr(v)}" for k, v in items
        ) + "}"
    if callable(value):
        return getattr(value, "__name__", type(value).__name__)
    return type(value).__name__


def stage(fn: Callable, **kwargs: Any) -> StageFn:
    """Bind keyword args to a stage so it slots into a pipeline as a ``records -> records`` step."""

    def run(records: Records) -> Records:
        return fn(records, **kwargs)

    run.__name__ = getattr(fn, "__name__", "stage")
    run.__contexel_desc__ = (  # type: ignore[attr-defined]
        run.__name__,
        tuple(sorted((k, _stable_repr(v)) for k, v in kwargs.items())),
    )
    return run


def pipeline(stages: List[StageFn]) -> StageFn:
    """Compose stages left-to-right into one callable: ``pipeline([...])(records)``.

    The returned callable exposes ``.fingerprint`` -- a stable policy hash.
    """
    descs = tuple(
        getattr(s, "__contexel_desc__", (getattr(s, "__name__", "callable"),))
        for s in stages
    )
    fingerprint = hashlib.sha256(repr(descs).encode()).hexdigest()[:16]

    def run(records: Records) -> Records:
        tr = current_trace()
        if tr is not None and fingerprint not in tr.policies:
            tr.policies.append(fingerprint)
        for s in stages:
            records = s(records)
        return records

    run.fingerprint = fingerprint  # type: ignore[attr-defined]
    return run
