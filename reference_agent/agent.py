"""A reference code-execution agent.

The loop: the model proposes either Python code to run or a final answer. Code
runs in a sandbox namespace that exposes the tools and the contexel stages; only
the distilled ``result`` it produces is folded back into context. This is the
"code execution with MCP" / programmatic-tool-calling pattern, with contexel as
the deterministic context-economy layer at the tool -> context boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

from contexel import (
    dedupe,
    merge,
    pipeline,
    rank,
    select,
    stage,
    trace,
    trim_to_budget,
    truncate_field,
)

from .context import ContextWindow, Observation
from .model import Finish, ModelClient, RunCode
from .tools import TOOLS

# Everything model-authored code may reference inside the sandbox.
SANDBOX_GLOBALS = {
    **TOOLS,
    "select": select,
    "dedupe": dedupe,
    "rank": rank,
    "truncate_field": truncate_field,
    "trim_to_budget": trim_to_budget,
    "merge": merge,
    "pipeline": pipeline,
    "stage": stage,
}


class SandboxError(RuntimeError):
    pass


def run_code(code: str) -> Any:
    """Execute model-authored code in a constrained namespace; return ``result``.

    NOTE — this is a *reference* runner, not a security boundary. ``exec`` runs
    the code in-process. A production system must isolate untrusted model output
    (subprocess, container, gVisor/seccomp, a microVM, ...). The contexel pattern
    at the tool -> context boundary is identical regardless of how you isolate.
    """
    ns: dict = dict(SANDBOX_GLOBALS)
    ns["result"] = None
    try:
        exec(compile(code, "<agent-code>", "exec"), ns)
    except Exception as exc:  # surface to the loop; don't crash the agent
        raise SandboxError(f"{type(exc).__name__}: {exc}") from exc
    return ns.get("result")


def _as_records(value: Any) -> List[dict]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list) and all(isinstance(x, dict) for x in value):
        return value
    return [{"value": value}]


@dataclass
class AgentResult:
    answer: str
    steps: int
    context: ContextWindow
    traces: List[str] = field(default_factory=list)


class Agent:
    """A reference code-execution agent with contexel at the tool -> context boundary."""

    def __init__(self, model: ModelClient, budget: int = 6000, max_steps: int = 8):
        self.model = model
        self.budget = budget
        self.max_steps = max_steps

    def run(self, task: str) -> AgentResult:
        ctx = ContextWindow(budget=self.budget)
        traces: List[str] = []
        for step in range(self.max_steps):
            action = self.model.next_action(task, ctx.render(), step)
            if isinstance(action, Finish):
                return AgentResult(action.answer, step, ctx, traces)

            # RunCode: shaping happens inside the tools (@shaped) and/or the code.
            with trace() as t:
                try:
                    result = run_code(action.code)
                except SandboxError as exc:
                    result = [{"error": str(exc)}]
            ctx.add(Observation(step=step, code=action.code, records=_as_records(result)))
            traces.append(t.report())

        return AgentResult(
            "(max steps reached without a final answer)", self.max_steps, ctx, traces
        )
