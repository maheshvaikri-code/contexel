"""Token measurement for context-economy stages.

A pluggable tokenizer abstraction. The default needs no native dependency: it
estimates tokens from a canonical serialization of the value (~4 chars/token for
English). Install the ``accurate`` extra and call :func:`use_tiktoken` for exact
counts, or :func:`set_tokenizer` to plug in your own.
"""
from __future__ import annotations

import json
import math
from typing import Any, Callable, Optional

# A tokenizer is any callable mapping text -> token count.
Tokenizer = Callable[[str], int]


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


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def count(value: Any, tokenizer: Optional[Tokenizer] = None) -> int:
    """Estimate the token cost of any JSON-able value (str, dict, list, ...)."""
    tok = tokenizer or _default
    return tok(_to_text(value))
