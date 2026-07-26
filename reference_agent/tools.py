"""A small, deterministic toolset over an in-memory repository.

Each tool returns verbose ``list[dict]`` records — exactly what a real search /
filesystem / VCS tool emits, including nondeterministic noise (a fresh
``request_id`` and ``fetched_at`` per call). Each tool is wrapped with
``@shaped(<contract>)`` so its output is reshaped and bounded *before* it ever
reaches the agent's context. The contracts drop the noise, so what lands in
context is identical on every call even though the raw layer is not.
"""
from __future__ import annotations

import hashlib
import inspect
import uuid
from datetime import datetime, timezone
from typing import List

from contexel import shaped

from .shaping import FILE_CONTRACT, GREP_CONTRACT, LISTING_CONTRACT, SEARCH_CONTRACT

# --------------------------------------------------------------------------- #
# In-memory repository the agent works against.
# --------------------------------------------------------------------------- #
_REPO = {
    "src/retry.py": '''"""Retry helpers: exponential backoff with optional jitter."""
import random
import time

from .config import (RETRY_MAX_ATTEMPTS, RETRY_BASE_DELAY_S,
                     RETRY_MAX_DELAY_S, RETRY_JITTER)


class TransientError(Exception):
    """Raised for errors that are safe to retry (timeouts, 5xx, etc.)."""


def retry_backoff(max_retries=RETRY_MAX_ATTEMPTS, base_delay=RETRY_BASE_DELAY_S,
                  max_delay=RETRY_MAX_DELAY_S, jitter=RETRY_JITTER):
    """Decorate a callable to retry it with exponential backoff.

    Delay for attempt n is ``base_delay * 2 ** (n - 1)`` capped at ``max_delay``;
    with ``jitter`` the delay is drawn uniformly from ``[0, delay]`` (full jitter).
    """
    def decorator(fn):
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return fn(*args, **kwargs)
                except TransientError:
                    attempt += 1
                    if attempt > max_retries:
                        raise
                    delay = min(max_delay, base_delay * 2 ** (attempt - 1))
                    if jitter:
                        delay = random.uniform(0, delay)
                    time.sleep(delay)
        return wrapper
    return decorator
''',
    "src/config.py": '''"""Tunable retry policy for outbound calls."""
RETRY_MAX_ATTEMPTS = 5
RETRY_BASE_DELAY_S = 0.2
RETRY_MAX_DELAY_S = 10.0
RETRY_JITTER = True
''',
    "src/http_client.py": '''"""A small HTTP client that retries transient failures."""
from .retry import retry_backoff, TransientError


class HttpClient:
    def __init__(self, session):
        self.session = session

    @retry_backoff(max_retries=3, base_delay=0.1)
    def get(self, url):
        resp = self.session.request("GET", url)
        if resp.status >= 500:
            raise TransientError("server error %s" % resp.status)
        return resp
''',
    "tests/test_retry.py": '''"""Tests for retry_backoff."""
from src.retry import retry_backoff, TransientError


def test_eventually_succeeds():
    calls = {"n": 0}

    @retry_backoff(max_retries=3, base_delay=0)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError("nope")
        return "ok"

    assert flaky() == "ok"
''',
    "README.md": "# example-service\n\nTiny service used as the agent's working "
                 "repository. See `src/retry.py` for the retry/backoff policy.\n",
}


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _iter_lines():
    for path, text in _REPO.items():
        for i, line in enumerate(text.splitlines(), start=1):
            yield path, i, line


def _symbol_for(line: str) -> str:
    s = line.strip()
    if s.startswith("def "):
        return s[4:].split("(")[0]
    if s.startswith("class "):
        return s[6:].split("(")[0].rstrip(":")
    return ""


def _sha(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:8]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Tools — raw output is verbose and partly nondeterministic; the contract tames it.
# --------------------------------------------------------------------------- #
@shaped(SEARCH_CONTRACT)
def search_code(query: str) -> List[dict]:
    """Search repository source for a substring; returns ranked hits."""
    q = query.lower()
    out: List[dict] = []
    for path, i, line in _iter_lines():
        if q in line.lower():
            out.append({
                "path": path, "line": i, "symbol": _symbol_for(line),
                "snippet": line.strip(),
                "score": round(line.lower().count(q) + 1.0 / i, 3),
                "blob_sha": _sha(f"{path}:{i}"), "commit": "c0ffee1",
                "request_id": uuid.uuid4().hex, "fetched_at": _now(),
            })
    return out


@shaped(FILE_CONTRACT)
def read_files(paths: List[str]) -> List[dict]:
    """Read whole files by path; returns one record per existing file."""
    out: List[dict] = []
    for p in paths:
        text = _REPO.get(p)
        if text is None:
            continue
        out.append({
            "path": p, "content": text, "size": len(text),
            "lines": text.count("\n") + 1, "encoding": "utf-8",
            "blob_sha": _sha(p), "request_id": uuid.uuid4().hex, "fetched_at": _now(),
        })
    return out


@shaped(GREP_CONTRACT)
def grep(pattern: str) -> List[dict]:
    """Line-level search; returns path/line/preview matches."""
    out: List[dict] = []
    for path, i, line in _iter_lines():
        if pattern in line:
            out.append({
                "path": path, "line": i, "preview": line.strip(),
                "col": line.find(pattern), "request_id": uuid.uuid4().hex,
            })
    return out


@shaped(LISTING_CONTRACT)
def list_dir(prefix: str = "") -> List[dict]:
    """List entries under a path prefix (one level deep)."""
    seen, out = set(), []
    for path in _REPO:
        if not path.startswith(prefix):
            continue
        rest = path[len(prefix):].lstrip("/")
        top = rest.split("/")[0]
        kind = "dir" if "/" in rest else "file"
        name = (prefix.rstrip("/") + "/" + top).lstrip("/") if prefix else top
        if name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "kind": kind, "perm": "rw-r--r--", "owner": "agent"})
    return out


TOOLS = {
    "search_code": search_code,
    "read_files": read_files,
    "grep": grep,
    "list_dir": list_dir,
}


def tool_signatures() -> str:
    """A human-readable signature list for the live model's system prompt."""
    lines = []
    for name, fn in TOOLS.items():
        raw = getattr(fn, "__wrapped__", fn)
        sig = inspect.signature(raw)
        doc = (raw.__doc__ or "").strip().splitlines()[0] if raw.__doc__ else ""
        lines.append(f"  {name}{sig} — {doc}")
    return "\n".join(lines)
