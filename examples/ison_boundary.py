"""Pattern 5 — shape-then-encode (contexel + ISON).

contexel decides *what survives*; the encoding decides *what the survivors
cost*. Budgets are encoding-relative: ``trim_to_budget`` prices each record by
its serialized text, so if the boundary emits an ISON table (ison.dev) instead
of JSON, plug that encoding in via ``tokens.set_serializer`` — budgets are then
priced in the encoding that actually enters context, and the same budget holds
roughly 3x more records.

``select`` makes the pairing work: projecting every record onto the same field
set yields exactly the uniform rows ISON's table syntax compresses best.

    python ison_boundary.py
"""
from contexel import pipeline, select, stage, tokens, trim_to_budget


def ison_table(records: list[dict], name: str = "records") -> str:
    """Render uniform records as an ISON table.

    A minimal subset of the ISON spec (ison.dev): a ``table.<name>`` header,
    one field line, whitespace-separated rows, values quoted only when they
    contain whitespace or quotes. For the full format (types, blocks, ``:id``
    references, ISONL streaming), use the ISON libraries.
    """
    if not records:
        return f"table.{name}"
    fields = list(records[0])

    def cell(value) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        text = str(value)
        if any(ch.isspace() for ch in text) or '"' in text:
            return '"' + text.replace('"', '\\"') + '"'
        return text

    rows = ["  ".join(cell(r.get(f, "")) for f in fields) for r in records]
    return "\n".join([f"table.{name}", "  ".join(fields), *rows])


def ison_serializer(value) -> str:
    """Price a record list as a table and a single record as one table row."""
    if isinstance(value, list) and all(isinstance(x, dict) for x in value):
        return ison_table(value)
    if isinstance(value, dict):
        return "  ".join(str(v) for v in value.values())
    return str(value)


def _repo_search(query: str) -> list[dict]:
    return [
        {"path": f"src/mod_{i % 7}.py", "line": 10 + i, "symbol": "retry_backoff",
         "snippet": "def retry_backoff(...):  # " + "x " * 30,
         "score": (i * 7) % 11, "commit": "abc123", "blob_sha": "deadbeef"}
        for i in range(200)
    ]


SHAPE = pipeline([
    stage(select, fields=["path", "line", "symbol", "score"]),   # uniform rows
    stage(trim_to_budget, max_tokens=400),
])


if __name__ == "__main__":
    raw = _repo_search("retry")

    kept_json = SHAPE(raw)                       # budget priced in JSON (default)

    tokens.set_serializer(ison_serializer)       # budget priced in ISON
    kept_ison = SHAPE(raw)
    tokens.set_serializer(None)                  # always restore the default

    print(f"same contract, same 400-token budget:")
    print(f"  JSON boundary: {len(kept_json)} records survive")
    print(f"  ISON boundary: {len(kept_ison)} records survive")
    print()
    print("what actually enters context under ISON:")
    print(ison_table(kept_ison[:4]))
