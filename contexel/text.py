"""Payload stages: carry text through the record stages and back (ADR-005).

Every other stage takes a list of mappings. A log, a web page or a plain string
is none of that, so three small stages convert at the edges::

    chunks = split(as_records(log_text), by="lines")     # text -> records
    ...                                                  # dedupe, rescore, rank, trim
    text = join(chunks)                                  # records -> text

``as_records`` and ``join`` are the entry and exit points: call them outside
:func:`contexel.pipeline` (like :func:`contexel.merge`), because a pipeline
hands every stage a list. ``split`` is an ordinary traced stage and belongs in
a pipeline.

Unlike the original stages, these validate the *shape* of their input in every
mode, not only in strict mode: they are new, so there is no lenient behavior to
stay compatible with.

Boundaries are explicit and identical in Python, TypeScript and C#: a line ends
after ``"\\n"`` only (so ``"\\r\\n"`` is one boundary and a lone ``"\\r"`` is none;
Python's wider ``str.splitlines`` set is not used), a paragraph ends after a
run of two or more newlines (``(?:\\r?\\n){2,}``), and sizes and offsets count
code points.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Dict, Iterator, List, Optional, cast

from . import tokens
from .errors import (
    ConfigError,
    InputShapeError,
    _kind,
    check_choice,
    check_str,
    invalid_value,
)
from .trace import traced
from .validate import checked

Record = Dict[str, Any]
Records = List[Record]

_PARAGRAPH_RUN = re.compile(r"(?:\r?\n){2,}")


def as_records(x: Any, field: str = "text") -> Records:
    """Turn a payload into a list of records, the shape every stage takes.

    A string becomes ``[{field: x}]``; a mapping becomes ``[x]`` (the same
    object, not a copy); a list or tuple keeps each mapping item and wraps every
    other item as ``{field: item}`` (nested JSON values are allowed). ``None``,
    bytes and every other type raise ``InputShapeError`` (``input.not_list``).
    ``field`` must be a non-empty string (``ConfigError``,
    ``config.invalid_value``). Not traced: it is an entry point.
    """
    if not isinstance(x, (str, Mapping, list, tuple)):
        raise InputShapeError(
            "input.not_list",
            f"as_records: expected a string, a mapping or a list, got {_kind(x)}",
            stage="as_records")
    check_str(field, "as_records", "field")
    if field == "":
        raise invalid_value("as_records", "field", "field must not be empty")
    if isinstance(x, str):
        return [{field: x}]
    if isinstance(x, Mapping):
        return [cast(Record, x)]
    return [cast(Record, item) if isinstance(item, Mapping) else {field: item}
            for item in x]


def _ends(text: str, by: str, size: Optional[int]) -> Iterator[int]:
    """The end offset (exclusive, in code points) of every chunk of ``text``."""
    n = len(text)
    if by == "size":
        assert size is not None
        yield from range(size, n, size)
        if n:
            yield n
        return
    last = 0
    if by == "lines":
        pos = text.find("\n")
        while pos != -1:
            last = pos + 1
            yield last
            pos = text.find("\n", last)
    else:
        for match in _PARAGRAPH_RUN.finditer(text):
            last = match.end()
            yield last
    if last < n:  # the remainder after the last boundary is a chunk
        yield n


@checked(mapping=True, always=True)
@traced(keeps_ids=True)
def split(records: Records, field: str = "text", by: str = "lines",
          size: Optional[int] = None, into: str = "chunk") -> Records:
    """Cut the text in ``field`` into chunk records.

    ``by="lines"`` ends a chunk after each ``"\\n"``; ``by="paragraphs"`` after
    each run of two or more newlines; ``by="size"`` every ``size`` code points
    (``size`` must then be a positive integer). Every chunk keeps its trailing
    separator, so joining the chunks with ``""`` reproduces the text exactly.

    Each chunk is ``{**parent, field: chunk_text, into: {"index": i, "start":
    s, "end": e}}``: ``index`` counts from 0 within its parent and ``[start,
    end)`` are code-point offsets into the original text, so ``text[start:end]``
    is the chunk. A record whose ``field`` is not a string passes through
    untouched; a string that is empty yields no chunks (that record
    disappears). A string-valued record that already has the ``into`` key
    raises ``InputShapeError`` (``input.field_conflict``).

    ``by`` must be ``"lines"``, ``"paragraphs"`` or ``"size"`` and ``size``
    must be omitted for the first two (``ConfigError``: ``config.invalid_value``
    and ``config.contradictory``). Items must be mappings: this stage checks
    its input in every mode.

    ``rank`` reorders chunks by score. To restore reading order before
    :func:`join`, rank again with ``by=lambda r: r["chunk"]["start"]`` and
    ``desc=False``.
    """
    check_str(field, "split", "field")
    check_choice(by, "split", "by", ("lines", "paragraphs", "size"))
    check_str(into, "split", "into")
    if by == "size":
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise invalid_value(
                "split", "size",
                f"size must be a positive integer when by='size', got {size!r}")
    elif size is not None:
        raise ConfigError(
            "config.contradictory",
            f"split: size={size!r} only applies to by='size', got by={by!r}",
            stage="split", param="size")
    out: Records = []
    for i, r in enumerate(records):
        text = r.get(field)
        if not isinstance(text, str):
            out.append(r)
            continue
        if into in r:
            raise InputShapeError(
                "input.field_conflict",
                f"split: record {i} already has a {into!r} field; "
                f"pass a different into",
                stage="split", param="into")
        start = 0
        for index, end in enumerate(_ends(text, by, size)):
            out.append({**r, field: text[start:end],
                        into: {"index": index, "start": start, "end": end}})
            start = end
    return out


@checked(mapping=True, always=True)
def join(records: Records, field: str = "text", sep: str = "") -> str:
    """Join the ``field`` of every record into one string.

    A record without ``field`` is skipped; a string value is used as it is; any
    other value is rendered with :func:`contexel.tokens.serialize`, the text the
    token budget priced. The parts are joined with ``sep``. Items must be
    mappings (checked in every mode). Not traced: it is an exit point.
    """
    check_str(field, "join", "field")
    check_str(sep, "join", "sep")
    parts: List[str] = []
    for r in records:
        if field not in r:
            continue
        value = r[field]
        parts.append(value if isinstance(value, str) else tokens.serialize(value))
    return sep.join(parts)
