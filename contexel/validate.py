"""Strict mode: opt-in validation of the *shape* of stage input (ADR-003).

The original stages are lenient about data shape (a non-list fails somewhere
inside, or worse, silently produces nonsense). That stays the default, so valid
input and today's callers keep byte-identical behavior. Switch strict mode on to
get a typed :class:`~contexel.errors.InputShapeError` that names the stage (and
the item index) instead::

    with contexel.strict():
        shape(records)                      # ambient: this context only

    pipe = contexel.pipeline([...], strict=True)   # also holds on worker threads

Strict never changes a successful result and is not part of a pipeline's
fingerprint.
"""
from __future__ import annotations

import contextvars
import functools
import inspect
from collections.abc import Mapping
from typing import Any, Callable, Dict, Union

from .errors import InputShapeError, _kind

_strict: "contextvars.ContextVar[bool]" = contextvars.ContextVar(
    "contexel_strict", default=False
)


class _StrictContext:
    def __init__(self) -> None:
        # a stack, so the SAME object can be entered again while active (and
        # reused): each exit restores the value its own enter replaced
        self._tokens: list = []

    def __enter__(self) -> None:
        self._tokens.append(_strict.set(True))

    def __exit__(self, *exc: Any) -> None:
        _strict.reset(self._tokens.pop())


def strict() -> _StrictContext:
    """Context manager: strict shape validation for the stages called inside.

    The flag lives in a ``ContextVar``: it follows ``await`` and
    ``contextvars.copy_context()`` but is NOT inherited by a plain
    ``threading.Thread`` or executor worker. ``pipeline(..., strict=True)`` and
    ``shaped(..., strict=True)`` enter strict mode inside their own run, so
    they are safe on worker threads. A ``with strict():`` around a ``yield``
    keeps strict on in the caller while the generator is suspended (standard
    ``ContextVar`` behaviour).
    """
    return _StrictContext()


def is_strict() -> bool:
    """Whether strict mode is active in the current context."""
    return _strict.get()


def check_records(records: Any, stage: str, mapping: bool) -> None:
    """Raise unless ``records`` is a list (or tuple) -- and, when ``mapping``,
    unless every item is a mapping. The message names the stage and the index."""
    if not isinstance(records, (list, tuple)):
        raise InputShapeError(
            "input.not_list",
            f"{stage}: records must be a list, got {_kind(records)}",
            stage=stage)
    if mapping:
        for i, item in enumerate(records):
            if not isinstance(item, Mapping):
                raise InputShapeError(
                    "input.not_mapping",
                    f"{stage}: item {i} must be a mapping, got {_kind(item)}",
                    stage=stage)


def check_stage_output(out: Any, stage: str, index: int) -> None:
    """Strict pipelines: a stage must hand the next one a list."""
    if not isinstance(out, (list, tuple)):
        raise InputShapeError(
            "input.not_list",
            f"stage {index} ({stage}) returned {_kind(out)}, not a list",
            stage=stage)


NeedsMapping = Union[bool, Callable[[Dict[str, Any]], bool]]


def checked(mapping: NeedsMapping = False,
            always: bool = False) -> Callable[[Callable], Callable]:
    """Decorator for a record stage: in strict mode, validate its input before
    the stage (and ``traced``) touches it.

    Apply it OUTSIDE ``@traced``: ``traced`` calls ``len(records)`` first, so a
    non-list would otherwise raise a raw error under a trace instead of the
    typed one. ``mapping`` is ``True`` when the stage always indexes items as
    mappings, or a callable taking the bound arguments (``{"key": ...}``) for
    stages that only sometimes need one (``dedupe`` with a ``key``, ``rank``
    with a field name). ``always=True`` validates in every mode, not only in
    strict mode: the payload stages (:mod:`contexel.text`) are new, so they have
    no lenient behavior to stay compatible with.
    """

    def decorate(fn: Callable) -> Callable:
        name = getattr(fn, "__name__", "stage")

        @functools.wraps(fn)
        def wrapper(records: Any, *args: Any, **kwargs: Any) -> Any:
            if always or _strict.get():
                need = mapping
                if callable(mapping):
                    try:
                        bound = inspect.signature(fn).bind(records, *args, **kwargs)
                        need = bool(mapping(dict(bound.arguments)))
                    except TypeError:
                        need = False  # a bad call: let the stage report it
                check_records(records, name, bool(need))
            return fn(records, *args, **kwargs)

        return wrapper

    return decorate
