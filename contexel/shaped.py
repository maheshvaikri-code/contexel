"""Apply a contexel pipeline at the tool boundary.

`@shaped` wraps a tool so its record-list return value is run through a pipeline
before it returns. The model calls the tool normally and never writes the
reshaping itself, which makes the shaping deterministic and identical on every
call — the same lens on the repo, run after run.
"""
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Dict, List, Sequence, Union

from .pipeline import pipeline

Records = List[Dict[str, Any]]
StageFn = Callable[[Records], Records]


def shaped(pipe: Union[StageFn, Sequence[StageFn]]) -> Callable[[Callable[..., Records]], Callable[..., Records]]:
    """Decorator: run a tool's record-list output through a contexel pipeline.

    ``pipe`` may be a single ``records -> records`` callable (e.g. the result of
    :func:`contexel.pipeline`) or a list of stages, which is composed for you.

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
    runner: StageFn = pipe if callable(pipe) else pipeline(list(pipe))

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
