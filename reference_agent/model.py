"""Model clients for the reference agent.

`ScriptedClient` is a deterministic stand-in so the whole loop runs with no API
key (used by the demo and the tests). `AnthropicClient` is a drop-in replacement
backed by a real model. Both satisfy the same `next_action` contract: given the
task and the current (already shaped) context view, return the next Action —
either code to run or a final answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Protocol, Union

from .tools import tool_signatures


@dataclass
class RunCode:
    code: str


@dataclass
class Finish:
    answer: str


Action = Union[RunCode, Finish]


class ModelClient(Protocol):
    def next_action(self, task: str, context_view: str, step: int) -> Action: ...


class ScriptedClient:
    """Deterministic stand-in for a model so the reference runs with no API key.

    Feed it a fixed list of Actions; it returns them in order (repeating the last).
    """

    def __init__(self, script: List[Action]):
        self.script = script

    def next_action(self, task: str, context_view: str, step: int) -> Action:
        return self.script[min(step, len(self.script) - 1)]


_SYSTEM = """You are a coding agent that works by writing Python.

You have these tools available in your sandbox (each already returns compact,
shaped records — do not try to fetch raw data around them):

{tools}

The contexel context-economy stages are also in scope: select, dedupe, rank,
truncate_field, trim_to_budget, merge, pipeline, stage. Use them to distil any
result before you return it.

Each turn, respond with EXACTLY ONE of:
  1. a single ```python code block that ends by assigning the distilled output
     to a variable named `result`; or
  2. a line `FINAL: <answer>` once you can answer the task.

Keep `result` small — it is folded back into your context verbatim."""

_CODE_RE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)


class AnthropicClient:
    """Live model client (needs the `anthropic` SDK and an API key).

    A genuine drop-in for ScriptedClient: same `next_action` contract, real model
    behind it. Set ANTHROPIC_API_KEY in the environment, or pass api_key=...
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: Optional[str] = None,
        max_tokens: int = 1024,
    ):
        import anthropic  # pip install anthropic

        self._client = anthropic.Anthropic(api_key=api_key)  # reads env if None
        self._model = model
        self._max_tokens = max_tokens
        self._messages: list = []

    def next_action(self, task: str, context_view: str, step: int) -> Action:
        self._messages.append({
            "role": "user",
            "content": f"Task: {task}\n\nCurrent context:\n{context_view}\n\nYour move:",
        })
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=_SYSTEM.format(tools=tool_signatures()),
            messages=self._messages,
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        )
        self._messages.append({"role": "assistant", "content": text})

        match = _CODE_RE.search(text)
        if match:
            return RunCode(match.group(1).strip())
        if "FINAL:" in text:
            return Finish(text.split("FINAL:", 1)[1].strip())
        return Finish(text.strip())
