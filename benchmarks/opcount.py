"""Native-operation counts, computed from the code that defines each implementation.

The comparison says how many of the task's operations each library "expresses
itself". That used to be typed by hand next to each implementation, so it could
drift from what the code actually does. Here an implementation is an ordered
list of :class:`Step`: each step names the operation it serves and holds the
callable that does the work. The same list is what runs, and the count is read
from it: a step is *native* when running it enters at least one Python function
defined in the library's own package (checked with ``sys.setprofile`` over a
small sample), and *glue* otherwise. Nothing about "native" is typed. The steps
are run once unmeasured first, so that importing a library inside a step is never
mistaken for using it.

Three kinds of step exist. An *operation* step serves one of the task's
operations (``OPS``). An *adapter* step only converts the operand to the shape a
library requires (messages, nodes) and back: that is a cost of using the library,
not an operation. An *other* step is a library feature that serves none of the
task's operations (a score cutoff, a lost-in-the-middle reorder); it is reported
but never counted as one of them.
"""
from __future__ import annotations

import copy
import sys
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple

OPS = ("select", "dedupe", "rescore", "truncate", "rank", "trim")
KINDS = ("adapter", "other")


@dataclass(frozen=True)
class Step:
    name: str
    fn: Callable[[Any], Any]
    op: str  # one of OPS, or "adapter", or "other"

    def __post_init__(self) -> None:
        if self.op not in OPS and self.op not in KINDS:
            raise ValueError(f"step {self.name!r}: op must be one of {OPS + KINDS}, got {self.op!r}")


def run(steps: Sequence[Step], data: Any) -> Any:
    for step in steps:
        data = step.fn(data)
    return data


def _enters(module: str, root: str) -> bool:
    return module == root or module.startswith(root + ".")


def enters_library(fn: Callable[[Any], Any], data: Any, root: str) -> Tuple[bool, Any]:
    """Run ``fn(data)``; report whether a Python function of package ``root`` ran."""
    entered: List[str] = []

    def profiler(frame: Any, event: str, arg: Any) -> None:
        if event == "call" and frame.f_code.co_name != "<module>":
            module = frame.f_globals.get("__name__", "")
            if isinstance(module, str) and _enters(module, root):
                entered.append(module)

    previous = sys.getprofile()
    sys.setprofile(profiler)
    try:
        out = fn(data)
    finally:
        sys.setprofile(previous)
    return bool(entered), out


@dataclass(frozen=True)
class Count:
    ops: Tuple[str, ...]                 # the operations the task has, in order
    native: Tuple[str, ...]              # operations done by library code
    glue: Tuple[str, ...]                # operations done by hand-written code
    missing: Tuple[str, ...]             # operations no step performs
    other_native: Tuple[str, ...]        # names of native "other" steps
    adapters: Tuple[str, ...]            # names of adapter steps

    @property
    def label(self) -> str:
        text = f"{len(self.native)}/{len(self.ops)}"
        return text + (" (" + ", ".join(self.native) + ")" if self.native else "")

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "native": list(self.native),
            "glue": list(self.glue),
            "missing": list(self.missing),
            "other_native": list(self.other_native),
            "adapters": list(self.adapters),
        }


def count(steps: Sequence[Step], root: Optional[str], sample: Any,
          ops: Sequence[str] = OPS) -> Count:
    """Run ``steps`` over ``sample`` and classify every step.

    ``root`` is the library's top-level package (``None`` for hand-written code,
    which has no native steps by definition). An operation counts as native when
    any step serving it enters the library.
    """
    if root is not None:
        run(steps, copy.deepcopy(sample))  # first imports and lazy loads happen here, not in the measured pass
    native, glue, other_native, adapters = [], [], [], []
    data = sample
    for step in steps:
        if root is None:
            hit, data = False, step.fn(data)
        else:
            hit, data = enters_library(step.fn, data, root)
        if step.op == "adapter":
            adapters.append(step.name)
        elif step.op == "other":
            if hit:
                other_native.append(step.name)
        elif hit:
            native.append(step.op)
        else:
            glue.append(step.op)
    done_native = tuple(o for o in ops if o in native)
    done_glue = tuple(o for o in ops if o in glue and o not in native)
    missing = tuple(o for o in ops if o not in native and o not in glue)
    return Count(tuple(ops), done_native, done_glue, missing,
                 tuple(other_native), tuple(adapters))
