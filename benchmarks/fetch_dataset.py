"""Fetch the public dataset used by the competitor comparison.

Source: CodeSearchNet (python, test split — all 22,176 rows) — real
code-search records:

    https://huggingface.co/datasets/code-search-net/code_search_net

The full split is downloaded once as the Hugging Face parquet export (a
single file) and cached under benchmarks/data/ (gitignored) as JSONL; delete
the cache to re-fetch.

    python -m benchmarks.fetch_dataset
"""
from __future__ import annotations

import io
import json
from pathlib import Path

DATASET = "code-search-net/code_search_net"
CONFIG, SPLIT = "python", "test"

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_FILE = DATA_DIR / "codesearchnet_python_test_full.jsonl"

_KEEP = (
    "repository_name",
    "func_path_in_repository",
    "func_name",
    "func_code_string",
    "func_documentation_string",
    "func_code_url",
)


def fetch() -> Path:
    """Download and cache the full split; return the cache path."""
    if DATA_FILE.exists():
        return DATA_FILE
    import pyarrow.parquet as pq  # only needed on first fetch
    import requests

    DATA_DIR.mkdir(exist_ok=True)
    listing = requests.get(
        f"https://huggingface.co/api/datasets/{DATASET}/parquet/{CONFIG}/{SPLIT}",
        timeout=60,
    )
    listing.raise_for_status()
    rows: list[dict] = []
    for url in listing.json():
        print(f"  downloading {url}")
        blob = requests.get(url, timeout=600)
        blob.raise_for_status()
        table = pq.read_table(io.BytesIO(blob.content), columns=list(_KEEP))
        rows.extend(table.to_pylist())
    print(f"  {len(rows)} rows")
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
