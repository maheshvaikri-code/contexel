"""AC 25: native-operation counts are computed from the code that defines each
implementation, not typed."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks import opcount  # noqa: E402
from contexel import select, stage  # noqa: E402

SAMPLE = [{"path": f"p{i}.py", "symbol": "s", "snippet": "x", "score": i} for i in range(3)]
TIMED = ("select", "dedupe", "truncate", "rank", "trim")  # the query-free task has no rescore


def test_native_op_counts_are_computed_from_definitions():
    steps = [
        opcount.Step("select", stage(select, fields=["path", "symbol"]), "select"),  # contexel code
        opcount.Step("dedupe", lambda r: r, "dedupe"),                                 # hand-written
        opcount.Step("convert", lambda r: r, "adapter"),
        opcount.Step("cutoff", stage(select, fields=["path"]), "other"),
    ]
    c = opcount.count(steps, "contexel", SAMPLE)
    assert c.native == ("select",) and c.glue == ("dedupe",)
    assert c.missing == ("rescore", "truncate", "rank", "trim")
    assert c.other_native == ("cutoff",) and c.adapters == ("convert",)
    assert c.label == "1/6 (select)"

    # the count follows the definition: make the dedupe step library code and it is native
    swapped = [steps[0], opcount.Step("dedupe", stage(select, fields=["path"]), "dedupe")] + steps[2:]
    assert opcount.count(swapped, "contexel", SAMPLE).native == ("select", "dedupe")
    # and the same steps are all glue for a library that none of them enters
    assert opcount.count(steps, "toolz_not_used_here", SAMPLE).native == ()
    # hand-written code has no native steps by definition
    assert opcount.count(steps, None, SAMPLE).native == ()
    # the denominator is the task's operations
    five = opcount.count(steps, "contexel", SAMPLE, ops=TIMED)
    assert five.label == "1/5 (select)" and five.missing == ("truncate", "rank", "trim")


def test_a_step_must_name_an_operation_or_a_kind():
    with pytest.raises(ValueError):
        opcount.Step("x", lambda r: r, "filter")


def test_run_applies_the_steps_in_order():
    steps = [opcount.Step("a", lambda r: r + [1], "select"), opcount.Step("b", lambda r: r + [2], "dedupe")]
    assert opcount.run(steps, []) == [1, 2]
    assert opcount.run([], "unchanged") == "unchanged"


def test_profiling_a_step_returns_its_output_and_restores_the_previous_profiler():
    events = []

    def profiler(frame, event, arg):
        events.append(event)

    sys.setprofile(profiler)
    try:
        entered, out = opcount.enters_library(lambda d: d + 1, 1, "contexel")
        assert (entered, out) == (False, 2)
        assert sys.getprofile() is profiler
        entered, out = opcount.enters_library(stage(select, fields=["path"]), SAMPLE, "contexel")
        assert entered and out == [{"path": f"p{i}.py"} for i in range(3)]
    finally:
        sys.setprofile(None)


def test_a_failing_step_still_restores_the_profiler():
    def boom(_):
        raise RuntimeError("boom")

    before = sys.getprofile()
    with pytest.raises(RuntimeError):
        opcount.enters_library(boom, 1, "contexel")
    assert sys.getprofile() is before
