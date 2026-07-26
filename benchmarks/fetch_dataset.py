"""Fetch the public dataset used by the competitor comparison.

Source: CodeSearchNet (python, test split) — real code-search records —
served row-by-row by the free Hugging Face datasets-server REST API:

    https://huggingface.co/datasets/code-search-net/code_search_net

Fixed offsets 0..N make the sample reproducible. The file is cached under
benchmarks/data/ (gitignored); delete it to re-fetch.

    python -m benchmarks.fetch_dataset
"""
from __future__ import annotations

import json
from pathlib import Path

DATASET = "code-search-net/code_search_net"
CONFIG, SPLIT = "python", "test"
N_ROWS = 2000
PAGE = 100  # datasets-server maximum page size

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_FILE = DATA_DIR / "codesearchnet_python_test.jsonl"

_KEEP = (
    "repository_name",
    "func_path_in_repository",
    "func_name",
    "func_code_string",
    "func_documentation_string",
    "func_code_url",
)


def fetch(n_rows: int = N_ROWS) -> Path:
    """Download and cache ``n_rows`` rows; return the cache path."""
    if DATA_FILE.exists():
        return DATA_FILE
    import requests  # only needed on first fetch

    DATA_DIR.mkdir(exist_ok=True)
    rows: list[dict] = []
    for offset in range(0, n_rows, PAGE):
        resp = requests.get(
            "https://datasets-server.huggingface.co/rows",
            params={"dataset": DATASET, "config": CONFIG, "split": SPLIT,
                    "offset": offset, "length": PAGE},
            timeout=60,
        )
        resp.raise_for_status()
        for item in resp.json()["rows"]:
            row = item["row"]
            rows.append({k: row[k] for k in _KEEP})
        print(f"  fetched {len(rows)}/{n_rows}")
    with DATA_FILE.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return DATA_FILE


def load() -> list[dict]:
    path = fetch()
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


if __name__ == "__main__":
    print(f"cached at {fetch()}")
