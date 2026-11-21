"""Apply a contexel pipeline at the tool boundary.

`@shaped` wraps a tool so its record-list return value is run through a pipeline
before it returns. The model calls the tool normally and never writes the
reshaping itself, which makes the shaping deterministic and identical on every
call — the same lens on the repo, run after run.
"""
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Dict, List, Sequence, Union, cast

from .errors import InputShapeError, check_bool
from .pipeline import pipeline
from .validate import strict as strict_mode

Records = List[Dict[str, Any]]
StageFn = Callable[[Records], Records]


def shaped(pipe: Union[StageFn, Sequence[StageFn]],
           strict: bool = False) -> Callable[[Callable[..., Records]], Callable[..., Records]]:
    """Decorator: run a tool's record-list output through a contexel pipeline.

    ``pipe`` may be a single ``records -> records`` callable (e.g. the result of
    :func:`contexel.pipeline`) or a list of stages, which is composed for you.

    ``strict=True`` validates the tool's return value is a list (an
    ``InputShapeError`` with stage ``"shaped"`` otherwise -- a tool that returns
    ``None`` would else surface as an obscure error inside the first stage) and
    runs the pipeline in strict mode, entered inside this wrapper so it holds on
    worker threads. When ``pipe`` is a list of stages it is composed with
    ``pipeline(..., strict=True)``, which also checks each stage's output.

    Async tools work too: a coroutine function is awaited and its returned
    records shaped (detected via ``inspect.iscoroutinefunction`` — a sync
    function that merely *returns* an awaitable is not detected).

    Example::

        from contexel import shaped, stage, select, dedupe, trim_to_budget

        @shaped([
            stage(select, fields=["path", "line", "snippet"]),
            stage(dedupe, key=["path", "line"]),
            stage(trim_to_budget, max_tokens=2000),
        ])
        def search_code(query: str) -> list[dict]:
            return repo.search(query)           # raw, heavy

        results = search_code("retry_backoff")  # already shaped, deterministically
    """
    check_bool(strict, "shaped", "strict")
    base: StageFn = pipe if callable(pipe) else pipeline(list(pipe), strict=strict)

    def runner(records: Any) -> Records:
        if not strict:
            return base(records)
        if not isinstance(records, (list, tuple)):
            raise InputShapeError(
                "input.not_list",
                f"shaped: the tool must return a list, got {type(records).__name__}",
                stage="shaped")
        with strict_mode():
            return base(cast(Records, records))

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrapper(*args: Any, **kwargs: Any) -> Records:
                return runner(await fn(*args, **kwargs))

            return awrapper

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Records:
            return runner(fn(*args, **kwargs))

        return wrapper

    return decorator
