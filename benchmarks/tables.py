"""Markdown table rendering shared by the benchmark reports."""
from __future__ import annotations

from typing import Any, List, Tuple


def table(rows: List[dict], columns: List[Tuple[str, str]]) -> str:
    """Render rows as a GitHub-flavored markdown table.

    ``columns`` is a list of (key, header); float values are formatted to a
    sensible precision, everything else via str().
    """
    def fmt(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:,.2f}"
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)

    head = "| " + " | ".join(h for _, h in columns) + " |"
    rule = "|" + "|".join("---" for _ in columns) + "|"
    body = "\n".join(
        "| " + " | ".join(fmt(r[k]) for k, _ in columns) + " |" for r in rows
    )
    return "\n".join([head, rule, body])
