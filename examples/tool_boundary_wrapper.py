"""Pattern 2 — the tool-boundary wrapper (@shaped).

Apply the pipeline inside the tool, so the model calls it normally and never
writes the reshaping. The shaping is deterministic and identical on every call —
the same lens on the repo, run after run.

    python tool_boundary_wrapper.py
"""
from contexel import shaped, stage, select, dedupe, truncate_field, rank, trim_to_budget


def _repo_search(query: str) -> list[dict]:
    return [
        {"path": f"src/mod_{i % 5}.py", "line": 10 + i, "symbol": "retry_backoff",
         "snippet": "def retry_backoff(...):  # " + "x " * 30,
         "score": (i * 7) % 11, "commit": "abc123", "blob_sha": "deadbeef"}
        for i in range(24)
    ]


@shaped([
    stage(select, fields=["path", "line", "symbol", "snippet", "score"]),
    stage(dedupe, key=["path", "line"]),
    stage(truncate_field, field="snippet", max_tokens=30),
    stage(rank, by="score", desc=True),
    stage(trim_to_budget, max_tokens=1200),
])
def search_code(query: str) -> list[dict]:
    return _repo_search(query)   # raw, heavy — shaped automatically on the way out


if __name__ == "__main__":
    hits = search_code("where is retry_backoff used")
    print(f"{len(hits)} shaped hits (identical every call):")
    for h in hits[:3]:
        print("  ", h["path"], "L" + str(h["line"]), "score", h["score"])
