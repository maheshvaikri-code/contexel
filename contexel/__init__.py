"""contexel -- the context element. Keep the signal, drop the noise.

A small, dependency-free library of context-economy stages for code-writing
agents: reshape, dedupe, rank, and trim tool output to fit a token budget before
it ever reaches the model's context window.
"""
from . import tokens
from .pipeline import pipeline, stage
from .shaped import shaped
from .stages import (
    allowlist,
    dedupe,
    merge,
    quarantine,
    rank,
    rescore,
    select,
    trim_to_budget,
    truncate_field,
)
from .trace import Trace, trace

__version__ = "0.1.16"

__all__ = [
    "select",
    "dedupe",
    "allowlist",
    "quarantine",
    "rank",
    "rescore",
    "truncate_field",
    "trim_to_budget",
    "merge",
    "pipeline",
    "stage",
    "shaped",
    "trace",
    "Trace",
    "tokens",
]
