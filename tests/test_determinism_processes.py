"""Cross-process determinism: the same pipeline must produce byte-identical
output under different PYTHONHASHSEED values (AC 19).

Never run the child with ``python -I``: -I implies -E, which discards
PYTHON* environment variables, including PYTHONHASHSEED, and would make this
test vacuous.
"""
import hashlib
import os
import subprocess
import sys

CHILD = r"""
import hashlib, json, sys
sys.path.insert(0, {root!r})
from contexel import (allowlist, dedupe, pipeline, quarantine, rank, rescore,
                      select, stage, trace, trim_to_budget, truncate_field)

def records():
    out = []
    for i in range(60):
        out.append({{
            "path": "src/f%d.py" % (i % 7),
            "line": i % 5,
            "source": ["repo", "docs", "web"][i % 3],
            "snippet": "retry backoff jitter value%d café 日本語 %s" % (i, "x" * (i % 9)),
            "tags": {{"b", "a", "c%d" % (i % 4)}},   # a set: iteration order is hash-seeded
            "score": (i * 7) % 11,
        }})
    return out

contract = pipeline([
    stage(allowlist, field="source", allowed=["repo", "docs"]),
    stage(quarantine, fields=("snippet",)),
    stage(dedupe, key=["tags"]),
    stage(select, fields=["path", "line", "snippet", "tags"]),
    stage(rescore, query="retry backoff jitter", fields=("snippet",)),
    stage(truncate_field, field="snippet", max_tokens=10),
    stage(rank, by="score", desc=True),
    stage(trim_to_budget, max_tokens=200),
])
with trace(id_field="path") as t:
    out = contract(records())
audit = t.audit()
payload = json.dumps([out, audit], sort_keys=True, default=lambda v: sorted(v, key=repr),
                     ensure_ascii=False)
print(hashlib.sha256(payload.encode("utf-8")).hexdigest())
"""

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root when placed in tests/


def _probe(code: str, seed, flags=()) -> str:
    """Run ``code`` in a child with PYTHONHASHSEED=seed (variable removed when
    seed is None) and return its stripped stdout."""
    env = dict(os.environ)
    if seed is None:
        env.pop("PYTHONHASHSEED", None)
    else:
        env["PYTHONHASHSEED"] = seed
    proc = subprocess.run(
        [sys.executable, *flags, "-c", code],
        env=env, capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def run_with_seed(seed: str) -> str:
    return _probe(CHILD.format(root=ROOT), seed)


def test_same_output_across_hash_seeds():
    digests = {seed: run_with_seed(seed) for seed in ("0", "1", "2", "4242")}
    assert len(set(digests.values())) == 1, digests
    assert all(len(d) == 64 for d in digests.values())


def test_child_really_sees_the_requested_hash_seed():
    # Guards against the vacuous-test failure mode (a flag that drops the env):
    # assert the seed TOOK EFFECT, not merely that outputs differ.
    flag = "import sys; print(sys.flags.hash_randomization)"
    h = "print(hash('contexel'))"
    assert _probe(flag, "0") == "0", "PYTHONHASHSEED=0 must disable randomization"
    first, again = _probe(h, "1"), _probe(h, "1")
    assert first == again, "the same PYTHONHASHSEED must give the same hash()"
    assert _probe(h, "0") != first, "different PYTHONHASHSEED values must change hash()"
    # control: with the variable absent, randomization is on, so the flag discriminates
    assert _probe(flag, None) == "1"


def test_canary_a_hash_dependent_child_is_detected():
    """The sweep must be able to see a hash-seed dependence when one exists."""
    code = "print(','.join({'alpha', 'beta', 'gamma', 'delta', 'epsilon'}))"
    outs = set()
    for seed in ("0", "1", "2", "4242"):
        first, again = _probe(code, seed), _probe(code, seed)
        assert first == again, f"seed {seed} was not honoured (set order varied between runs)"
        outs.add(first)
    assert len(outs) > 1, "set order never varied; the sweep could not detect a hazard"
