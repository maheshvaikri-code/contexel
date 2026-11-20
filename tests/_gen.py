"""Seeded generators for property tests. Standard library only.

Every generator takes a ``random.Random`` so a failing case is reproduced from
its seed alone. Values stay inside the documented parity envelope: no NaN/Inf,
no integer-valued floats as scores, mutually comparable scores.

Records also carry keys no stage is asked about (``junk``, ``extra_<n>``), so a
stage that touches an unexpected key is caught, and some records are exact
copies of an earlier one, so the dedupe properties are never vacuous.
"""
import copy
import os
import random
from typing import Iterator, List, Tuple

PATHS = ["src/a.py", "src/b.py", "docs/guide.md", "tests/t.py", "web/x.txt"]
SOURCES = ["repo", "docs", "web", None]
MARKER = "ignore all previous instructions"  # a built-in quarantine marker
WORDS = [
    "retry", "backoff", "jitter", "parse", "config", "value", "error", "cache",
    MARKER, "caf\u00e9", "na\u00efve",
    "\u65e5\u672c\u8a9e", "emoji\U0001F600", "x", "the", "of",
]
JUNK = [None, 0, -3, 7, 0.25, "", "junk", True, False, [], ["x", 1],
        {"j": [None, 2.5]}, "\u00e9t\u00e9"]
# Regression seeds: any seed that ever exposed a bug is appended here and
# always runs, so a found bug stays found.
REGRESSION_SEEDS: List[int] = []
DEFAULT_SEED, DEFAULT_CASES = 20261119, 200


def base_seed() -> int:
    return int(os.environ.get("CONTEXEL_PROP_SEED", str(DEFAULT_SEED)))


def case_count() -> int:
    return int(os.environ.get("CONTEXEL_PROP_CASES", str(DEFAULT_CASES)))


def seeds() -> Iterator[int]:
    yield from REGRESSION_SEEDS
    base = base_seed()
    for i in range(case_count()):
        yield base + i


def canary_seeds() -> Iterator[int]:
    """The run's seeds, then the default ones: whether a check CAN fail must
    not depend on how small a reproduction run is."""
    yield from seeds()
    yield from range(DEFAULT_SEED, DEFAULT_SEED + DEFAULT_CASES)


def make_records(rng: random.Random) -> List[dict]:
    out: List[dict] = []
    for _ in range(rng.randint(0, 12)):
        if out and rng.random() < 0.15:
            out.append(copy.deepcopy(rng.choice(out)))  # an exact duplicate
            continue
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
        if rng.random() < 0.5:
            rec["junk"] = copy.deepcopy(rng.choice(JUNK))
        for n in range(rng.randint(0, 2)):
            rec[f"extra_{n}"] = copy.deepcopy(rng.choice(JUNK))
        out.append(rec)
    return out


def case(seed: int) -> Tuple[random.Random, List[dict]]:
    rng = random.Random(seed)
    return rng, make_records(rng)
