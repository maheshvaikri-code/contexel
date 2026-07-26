"""In-language composition.

This is plain function composition -- not a spec an engine interprets. Any
callable ``records -> records`` (including a bare lambda) is a valid stage, and
you can breakpoint or step inside any of them.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

Records = List[Dict[str, Any]]
StageFn = Callable[[Records], Records]


def stage(fn: Callable, **kwargs: Any) -> StageFn:
    """Bind keyword args to a stage so it slots into a pipeline as a ``records -> records`` step."""

    def run(records: Records) -> Records:
        return fn(records, **kwargs)

    run.__name__ = getattr(fn, "__name__", "stage")
    return run


def pipeline(stages: List[StageFn]) -> StageFn:
    """Compose stages left-to-right into one callable: ``pipeline([...])(records)``."""

    def run(records: Records) -> Records:
        for s in stages:
            records = s(records)
        return records

    return run
