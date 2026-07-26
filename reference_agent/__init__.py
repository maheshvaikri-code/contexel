"""A full, runnable reference implementation of a code-execution agent that uses
contexel as the deterministic context-economy layer at the tool -> context boundary.

Run the demo:  python -m reference_agent
"""
from . import shaping, tools
from .agent import SANDBOX_GLOBALS, Agent, AgentResult, SandboxError, run_code
from .context import ContextWindow, Observation
from .model import (
    Action,
    AnthropicClient,
    Finish,
    ModelClient,
    RunCode,
    ScriptedClient,
)

__all__ = [
    "Agent",
    "AgentResult",
    "SandboxError",
    "run_code",
    "SANDBOX_GLOBALS",
    "ContextWindow",
    "Observation",
    "Action",
    "ModelClient",
    "ScriptedClient",
    "AnthropicClient",
    "RunCode",
    "Finish",
    "tools",
    "shaping",
]
