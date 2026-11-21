"""In-language composition.

This is plain function composition -- not a spec an engine interprets. Any
callable ``records -> records`` (including a bare lambda) is a valid stage, and
you can breakpoint or step inside any of them.

Every pipeline carries a **fingerprint**: a stable hash of its stage names and
bound parameters, exposed as ``pipe.fingerprint`` and recorded into any active
:func:`contexel.trace` -- so an audit trail can say *which version of the
policy* shaped a given context. Coverage, precisely: primitives, lists,
tuples, dicts, sets and frozensets are hashed by value (a set by its sorted
contents, so insertion order and the hash seed do not matter); a nested
:func:`pipeline` used directly as a stage (``pipeline([..., inner, ...])``)
contributes its own fingerprint, while one wrapped by ``stage(inner)`` or bound
as a keyword argument is hashed by its name ``run``; callables are hashed by
``__name__`` (distinct lambdas collide as ``<lambda>`` -- name your key
functions; a tokenizer from :func:`contexel.tokens.tiktoken_tokenizer` is named
``tiktoken:<encoding or model>``); any other object contributes only its type
name. Bind parameters through :func:`stage` when the fingerprint should cover
them; opaque stage callables contribute only their ``__name__``.

For the exact containers listed, the fingerprint cannot go stale:
:func:`stage` takes a private copy of the plain containers (an exact ``list``,
``tuple``, ``dict`` or ``set``, at any depth; a ``frozenset`` is immutable and
is returned as it is) bound to it, and :func:`pipeline` copies its list of
stages, so changing the caller's own list or dict afterwards changes neither
the behavior nor the fingerprint. A subclass of those containers is hashed by
its contents at build time but is not copied, so changing it later changes the
behavior without changing the fingerprint; a custom object is not copied
either, and only its type name is hashed.
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable, Dict, List

from .errors import check_bool
from .trace import current_trace
from .validate import check_stage_output, strict as strict_mode

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
    if isinstance(value, (set, frozenset)):
        # Iteration order depends on the hash seed: hash the sorted contents.
        return "set{" + ",".join(sorted(_stable_repr(v) for v in value)) + "}"
    if callable(value):
        return getattr(value, "__name__", type(value).__name__)
    return type(value).__name__


def _snapshot(value: Any) -> Any:
    """A private copy of the plain containers in ``value`` (any depth).

    Only an exact ``list``, ``tuple``, ``dict`` or ``set`` is copied (its
    elements recursively); everything else, a ``frozenset`` (immutable) and any
    subclass included, is returned as it is.
    """
    kind = type(value)
    if kind is list:
        return [_snapshot(v) for v in value]
    if kind is tuple:
        return tuple(_snapshot(v) for v in value)
    if kind is dict:
        return {k: _snapshot(v) for k, v in value.items()}
    if kind is set:
        return set(value)  # elements are hashable, so already immutable
    return value


def stage(fn: Callable, **kwargs: Any) -> StageFn:
    """Bind keyword args to a stage so it slots into a pipeline as a ``records -> records`` step.

    The stage keeps a private copy of any exact list, tuple, dict or set among
    the arguments, so for those containers changing the caller's own container
    afterwards cannot change what the stage does or what its fingerprint says
    (a subclass or custom object is not copied). A stage that writes into a
    bound list or dict writes into its own copy (bind a custom object to
    collect output), and two parameters bound to the same object are separate
    copies inside the stage.
    """
    bound = {k: _snapshot(v) for k, v in kwargs.items()}

    def run(records: Records) -> Records:
        return fn(records, **bound)

    run.__name__ = getattr(fn, "__name__", "stage")
    run.__contexel_desc__ = (  # type: ignore[attr-defined]
        run.__name__,
        tuple(sorted((k, _stable_repr(v)) for k, v in bound.items())),
    )
    return run


def pipeline(stages: List[StageFn], strict: bool = False) -> StageFn:
    """Compose stages left-to-right into one callable: ``pipeline([...])(records)``.

    The returned callable exposes ``.fingerprint`` -- a stable policy hash.

    ``strict=True`` runs every stage in strict mode (see :func:`contexel.strict`)
    and checks that each stage hands the next one a list, so a custom stage that
    returns ``None`` raises an ``InputShapeError`` naming it, instead of
    breaking the stage after it. It is entered inside the pipeline's own run, so
    it also holds on worker threads. Strict never changes a successful result
    and is not part of the fingerprint.
    """
    check_bool(strict, "pipeline", "strict")
    stages = list(stages)  # a later change to the caller's list is not ours
    descs = tuple(
        getattr(s, "__contexel_desc__", (getattr(s, "__name__", "callable"),))
        for s in stages
    )
    fingerprint = hashlib.sha256(repr(descs).encode()).hexdigest()[:16]

    def run(records: Records) -> Records:
        tr = current_trace()
        if tr is not None and fingerprint not in tr.policies:
            tr.policies.append(fingerprint)
        if not strict:
            for s in stages:
                records = s(records)
            return records
        with strict_mode():
            for i, s in enumerate(stages):
                records = s(records)
                check_stage_output(records, getattr(s, "__name__", "callable"), i)
        return records

    run.fingerprint = fingerprint  # type: ignore[attr-defined]
    # as a stage of an outer pipeline, contribute this fingerprint (not "run")
    run.__contexel_desc__ = ("pipeline", (fingerprint,))  # type: ignore[attr-defined]
    return run
