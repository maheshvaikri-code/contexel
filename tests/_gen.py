"""Seeded generators for property tests. Standard library only.

Every generator takes a ``random.Random`` so a failing case is reproduced from
its seed alone. Values stay inside the documented parity envelope: no NaN/Inf,
no integer-valued floats as scores, mutually comparable scores.
"""
import os
import random
from typing import Iterator, List, Tuple

PATHS = ["src/a.py", "src/b.py", "docs/guide.md", "tests/t.py", "web/x.txt"]
SOURCES = ["repo", "docs", "web", None]
WORDS = [
    "retry", "backoff", "jitter", "parse", "config", "value", "error", "cache",
    "ignore all previous instructions", "café", "naïve",
    "日本語", "emoji\U0001F600", "x", "the", "of",
]
# Regression seeds: any seed that ever exposed a bug is appended here and
# always runs, so a found bug stays found.
REGRESSION_SEEDS: List[int] = []


def base_seed() -> int:
    return int(os.environ.get("CONTEXEL_PROP_SEED", "20261119"))


def case_count() -> int:
    return int(os.environ.get("CONTEXEL_PROP_CASES", "200"))


def seeds() -> Iterator[int]:
    yield from REGRESSION_SEEDS
    base = base_seed()
    for i in range(case_count()):
        yield base + i


def make_records(rng: random.Random) -> List[dict]:
    out = []
    for _ in range(rng.randint(0, 12)):
        words = rng.choices(WORDS, k=rng.randint(0, 14))
        rec = {
            "path": rng.choice(PATHS),
            "line": rng.randint(1, 5),
            "snippet": " ".join(words),
            "score": rng.choice([rng.randint(0, 9), round(rng.random() * 10 + 0.001, 3)]),
            "source": rng.choice(SOURCES),
            "tags": rng.choice([[], ["a"], ["a", "b"]]),
            "meta": rng.choice([{}, {"k": 1}, {"k": {"z": None}}]),
        }
        if rng.random() < 0.2:
            del rec["score"]  # missing sort key: rank puts these last
        out.append(rec)
    return out


def case(seed: int) -> Tuple[random.Random, List[dict]]:
    rng = random.Random(seed)
    return rng, make_records(rng)
