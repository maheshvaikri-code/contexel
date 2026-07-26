"""Pattern 1 — inside programmatic tool calling.

The agent writes code in a sandbox that calls a tool and shapes the result
before returning the distilled version to its context.

    python programmatic_tool_calling.py
"""
from contexel import select, dedupe, truncate_field, rank, trim_to_budget, trace


def search_tool(query: str) -> list[dict]:
    # Stand-in for a real, verbose search tool: 30 results, each with distinct
    # text plus a little real-world URL duplication (~10 of 30 repeat).
    topics = ["retry", "timeout", "backoff", "circuit breaker", "rate limit", "jitter"]
    return [
        {"title": f"{topics[i % len(topics)]} guide #{i}",
         "url": f"https://site/{i % 20}",
         "snippet": (f"How {topics[i % len(topics)]} works in distributed systems. "
                     * (2 + i % 4)) + f"Example {i}: configure the policy with care.",
         "score": ((i * 37) % 100) / 100,
         "rank": i, "blob_sha": f"sha{i:04d}", "fetched_at": "2026-06-07"}
        for i in range(30)
    ]


def gather_context(query: str) -> list[dict]:
    raw = search_tool(query)
    with trace() as t:
        r = select(raw, ["title", "url", "snippet", "score"])  # drop rank/sha/fetched_at
        r = dedupe(r, key="url")
        r = truncate_field(r, "snippet", max_tokens=40)
        r = rank(r, by="score", desc=True)
        r = trim_to_budget(r, max_tokens=800)
    print(t.report())          # goes to your logs — never to the model
    return r


if __name__ == "__main__":
    results = gather_context("how does retry work")
    print(f"\nreturned {len(results)} records to context")
