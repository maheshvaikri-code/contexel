"""The agent's running context window.

Every observation appended here has already passed through a contexel contract,
so the window stays bounded. It reports its token cost with the same tokenizer
contexel uses, which makes the context economy measurable rather than asserted.
A window-level budget provides a second guard on top of the per-tool contracts:
if usage exceeds the budget, the oldest observations are evicted (FIFO).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, List

from contexel import tokens


@dataclass
class Observation:
    step: int
    code: str
    records: List[dict]

    @property
    def tokens(self) -> int:
        return tokens.count(json.dumps(self.records, ensure_ascii=False, default=str))


@dataclass
class ContextWindow:
    budget: int
    observations: List[Observation] = field(default_factory=list)
    evicted: List[int] = field(default_factory=list)

    def add(self, obs: Observation) -> None:
        self.observations.append(obs)
        self._enforce()

    def _enforce(self) -> None:
        while self.used > self.budget and len(self.observations) > 1:
            self.evicted.append(self.observations.pop(0).step)

    @property
    def used(self) -> int:
        return sum(o.tokens for o in self.observations)

    @property
    def remaining(self) -> int:
        return self.budget - self.used

    def render(self) -> str:
        """The compact view the model sees each step — never the raw dumps."""
        if not self.observations:
            return "(no observations yet)"
        out = [f"context: {self.used}/{self.budget} tokens used"]
        for o in self.observations:
            out.append(f"[step {o.step}] {len(o.records)} records ({o.tokens} tokens)")
            for r in o.records[:3]:
                preview = ", ".join(f"{k}={_short(v)}" for k, v in list(r.items())[:3])
                out.append(f"    - {preview}")
        return "\n".join(out)

    def report(self) -> str:
        ev = f", evicted steps {self.evicted}" if self.evicted else ""
        return f"{self.used}/{self.budget} tokens, {len(self.observations)} observations{ev}"


def _short(v: Any, n: int = 48) -> str:
    s = str(v).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "\u2026"
