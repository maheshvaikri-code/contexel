"""Synthetic, seeded datasets for the benchmark suites.

Everything is generated from seeded ``random.Random`` instances so that every
run — on any machine — operates on byte-identical input data. The records
imitate what a code-search tool actually returns: a few fields the agent
needs, several it does not, and nondeterministic noise (request ids,
timestamps) that a context contract is expected to drop.

Base content and noise are drawn from *separate* RNGs, so two datasets built
with the same ``seed`` but different ``noise_seed`` values differ only in
their noise fields — exactly the shape of the determinism claim.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List

Record = Dict[str, Any]

_WORDS = (
    "retry backoff jitter client session request response handler parse "
    "config timeout attempt delay socket buffer stream token budget index "
    "cache commit branch merge search symbol module import export wrapper"
).split()


def search_hits(
    n: int,
    *,
    dup_rate: float = 0.0,
    snippet_words: int = 12,
    seed: int = 7,
    noise_seed: int = 1,
) -> List[Record]:
    """``n`` code-search-hit records; ``dup_rate`` of them duplicate an
    earlier record's content (same ``path``/``line``, fresh noise)."""
    base_rng = random.Random(seed)
    noise_rng = random.Random(noise_seed)
    content: List[Record] = []
    out: List[Record] = []
    for i in range(n):
        if content and base_rng.random() < dup_rate:
            rec = dict(base_rng.choice(content))
        else:
            rec = {
                "path": f"src/{base_rng.choice(_WORDS)}/{base_rng.choice(_WORDS)}.py",
                "line": base_rng.randint(1, 500),
                "symbol": base_rng.choice(_WORDS),
                "snippet": " ".join(
                    base_rng.choice(_WORDS) for _ in range(snippet_words)
                ),
                "score": round(base_rng.random() * 10, 3),
                "blob_sha": f"{base_rng.getrandbits(64):016x}",
                "commit": f"{base_rng.getrandbits(28):07x}",
                "lang": "python",
            }
            content.append(rec)
        rec = dict(rec)
        rec["request_id"] = f"{noise_rng.getrandbits(64):016x}"
        rec["fetched_at"] = f"2026-07-26T{i % 24:02d}:{i % 60:02d}:00Z"
        out.append(rec)
    return out
