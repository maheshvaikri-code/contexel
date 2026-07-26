"""Token measurement for context-economy stages.

A pluggable tokenizer abstraction. The default needs no native dependency: it
estimates tokens from a canonical serialization of the value (~4 chars/token for
English). Install the ``accurate`` extra and call :func:`use_tiktoken` for exact
counts, or :func:`set_tokenizer` to plug in your own.

Counting is *encoding-relative*: a record's cost is the token count of its
serialized text. The default serialization is canonical JSON; if your boundary
emits a different encoding (e.g. an ISON table — see ison.dev), plug it in via
:func:`set_serializer` so budgets are priced in the encoding that actually
enters context.
"""
from __future__ import annotations

import json
import math
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator, Optional

# A tokenizer is any callable mapping text -> token count.
Tokenizer = Callable[[str], int]

# A serializer maps a non-string value to the text that will enter context.
Serializer = Callable[[Any], str]


def _heuristic(text: str) -> int:
    """Rough token estimate with no native dependency (~4 chars/token)."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


_default: Tokenizer = _heuristic


def set_tokenizer(tokenizer: Optional[Tokenizer]) -> None:
    """Set the process-wide default tokenizer. Pass ``None`` to reset to the heuristic."""
    global _default
    _default = tokenizer or _heuristic


# Context-local overlays: per-task / per-tenant isolation on top of the
# process defaults. Resolution order everywhere: explicit argument ->
# scoped() overlay -> process default (set_tokenizer/set_serializer) ->
# built-in (heuristic / canonical JSON).
_ctx_tokenizer: "ContextVar[Optional[Tokenizer]]" = ContextVar(
    "contexel_ctx_tokenizer", default=None
)
_ctx_serializer: "ContextVar[Optional[Serializer]]" = ContextVar(
    "contexel_ctx_serializer", default=None
)


def _active_tokenizer() -> Tokenizer:
    return _ctx_tokenizer.get() or _default


@contextmanager
def scoped(tokenizer: Optional[Tokenizer] = None,
           serializer: Optional["Serializer"] = None) -> Iterator[None]:
    """Context-local token accounting — safe for concurrent tenants.

    Overrides apply only within this context (and async tasks / copied
    contexts spawned inside it); other tasks and tenants are untouched,
    unlike the process-wide setters. Threads and executor workers started
    inside the scope do NOT inherit the overlay (they begin with a fresh
    context) — run such work via ``contextvars.copy_context().run(...)`` or
    open ``scoped()`` inside the worker. Example::

        with tokens.scoped(tokenizer=tokens.tiktoken_tokenizer()):
            shaped = contract(records)     # this tenant counts exactly
    """
    tok_reset = _ctx_tokenizer.set(tokenizer) if tokenizer is not None else None
    ser_reset = _ctx_serializer.set(serializer) if serializer is not None else None
    try:
        yield
    finally:
        if tok_reset is not None:
            _ctx_tokenizer.reset(tok_reset)
        if ser_reset is not None:
            _ctx_serializer.reset(ser_reset)


def is_heuristic(tokenizer: Optional[Tokenizer] = None) -> bool:
    """True when the tokenizer in effect is the built-in ~4-chars estimator.

    Lets stages take exact fast paths that are only valid for the estimator
    (its count, ``ceil(len/4)``, is invertible).
    """
    return (tokenizer or _active_tokenizer()) is _heuristic


def tiktoken_tokenizer(encoding: str = "cl100k_base",
                       model: Optional[str] = None) -> Tokenizer:
    """A tiktoken-backed tokenizer (requires the ``accurate`` extra), for
    ``set_tokenizer`` or ``scoped``. Exact for the models tiktoken covers
    (OpenAI encodings); for other providers it is a better approximation
    than the built-in estimate — when you need provider-exact counts, plug
    that provider's own counter in via ``set_tokenizer``/``scoped``. Pass
    ``model=`` for tiktoken's model-specific encoding (an unknown model
    raises ``KeyError``). Hard token limits demand an exact tokenizer —
    the built-in estimate is for soft budgeting only (it undercounts
    JSON-heavy records by ~29% in the benchmark).
    """
    import tiktoken

    enc = (tiktoken.encoding_for_model(model) if model
           else tiktoken.get_encoding(encoding))
    return lambda text: len(enc.encode(text))


def use_tiktoken(encoding: str = "cl100k_base",
                 model: Optional[str] = None) -> None:
    """Switch the process-default tokenizer to tiktoken (``accurate`` extra)."""
    set_tokenizer(tiktoken_tokenizer(encoding, model))


def _json_serializer(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


_default_serializer: Serializer = _json_serializer


def set_serializer(serializer: Optional[Serializer]) -> None:
    """Set the process-wide default serializer. Pass ``None`` to reset to JSON.

    Strings are always counted as-is; the serializer only renders non-string
    values (records, record lists). Keep it deterministic — it is part of the
    context contract.
    """
    global _default_serializer
    _default_serializer = serializer or _json_serializer


def serialize(value: Any) -> str:
    """Render a value exactly the way token counting will price it."""
    return _to_text(value)


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return (_ctx_serializer.get() or _default_serializer)(value)


def count(value: Any, tokenizer: Optional[Tokenizer] = None) -> int:
    """Estimate the token cost of any serializable value (str, dict, list, ...)."""
    tok = tokenizer or _active_tokenizer()
    return tok(_to_text(value))
