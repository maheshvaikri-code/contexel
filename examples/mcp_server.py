"""Pattern 3 — shaping inside an MCP server.

The server shapes its own large responses with contexel, so every client gets
the distilled result and no client needs to change. The contexel logic lives in
`shape_search`; the MCP wiring around it is shown with a guarded import, so this
file still runs (and demos the shaping) even without the MCP SDK installed.

    python mcp_server.py
"""
from contexel import select, dedupe, truncate_field, trim_to_budget, pipeline, stage

shape_search = pipeline([
    stage(select, fields=["title", "url", "snippet"]),  # drop internal_id / acl
    stage(dedupe, key="url"),
    stage(truncate_field, field="snippet", max_tokens=50),
    stage(trim_to_budget, max_tokens=1500),
])


def _raw_search(query: str) -> list[dict]:
    return [{"title": f"Doc {i}", "url": f"https://kb/{i % 6}",
             "snippet": "long passage " * 30, "internal_id": i, "acl": "team"}
            for i in range(20)]


try:
    from mcp.server.fastmcp import FastMCP   # pip install mcp

    mcp = FastMCP("knowledge-base")

    @mcp.tool()
    def search(query: str) -> list[dict]:
        """Search the knowledge base; results are shaped before they reach the model."""
        return shape_search(_raw_search(query))

    # if __name__ == "__main__": mcp.run()
except ImportError:
    pass


if __name__ == "__main__":
    out = shape_search(_raw_search("billing"))
    print(f"server would return {len(out)} shaped records (down from 20 raw):")
    for r in out[:3]:
        print("  ", r["url"], "-", r["title"])
