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
from typing import Any, Callable, Optional

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


def use_tiktoken(encoding: str = "cl100k_base") -> None:
    """Switch the default tokenizer to tiktoken (requires the ``accurate`` extra)."""
    import tiktoken

    enc = tiktoken.get_encoding(encoding)
    set_tokenizer(lambda text: len(enc.encode(text)))


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
    return _default_serializer(value)


def count(value: Any, tokenizer: Optional[Tokenizer] = None) -> int:
    """Estimate the token cost of any serializable value (str, dict, list, ...)."""
    tok = tokenizer or _default
    return tok(_to_text(value))
