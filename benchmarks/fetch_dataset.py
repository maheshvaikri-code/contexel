"""Fetch the public dataset used by the competitor comparison.

Source: CodeSearchNet (python, test split — all 22,176 rows) — real
code-search records:

    https://huggingface.co/datasets/code-search-net/code_search_net

The full split is downloaded once as the Hugging Face parquet export (a
single file) and cached under benchmarks/data/ (gitignored) as JSONL; delete
the cache to re-fetch.

The cache is never trusted on sight: its SHA-256 is compared with the digest
committed in benchmarks/dataset.sha256 every time it is used, and a download
is written to a temporary name and only moved into place once that comparison
passes. A mismatch raises DatasetChecksumError; nothing is read, shaped or
published from a file that failed it. The digest reads every line ending as LF,
because the cache is written by Python, which ends lines with CRLF on Windows
and LF elsewhere, and the digest must not depend on the operating system.

    python -m benchmarks.fetch_dataset
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path
from typing import Optional

DATASET = "code-search-net/code_search_net"
CONFIG, SPLIT = "python", "test"

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
DATA_FILE = DATA_DIR / "codesearchnet_python_test_full.jsonl"
CHECKSUM_FILE = HERE / "dataset.sha256"

_KEEP = (
    "repository_name",
    "func_path_in_repository",
    "func_name",
    "func_code_string",
    "func_documentation_string",
    "func_code_url",
)


class DatasetChecksumError(RuntimeError):
    """The dataset (or the committed digest) is not what the benchmark expects."""


def digest(path: Path) -> str:
    """SHA-256 of the file with every CRLF line ending read as LF."""
    sha = hashlib.sha256()
    with path.open("rb") as fh:
        for line in fh:
            if line.endswith(b"\r\n"):
                line = line[:-2] + b"\n"
            sha.update(line)
    return sha.hexdigest()


def expected_digest() -> str:
    """The committed digest. A missing, empty or malformed file is an error:
    the check fails closed rather than passing because nothing was pinned."""
    try:
        text = CHECKSUM_FILE.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise DatasetChecksumError(
            f"cannot read the committed checksum {CHECKSUM_FILE.name}: {exc}") from exc
    words = text.split()
    if not words or not re.fullmatch(r"[0-9a-f]{64}", words[0]):
        raise DatasetChecksumError(
            f"{CHECKSUM_FILE.name} must start with a 64-character lower-case "
            f"hexadecimal SHA-256, got {text.strip()[:80]!r}")
    return words[0]


def verify(path: Optional[Path] = None) -> str:
    """Return the digest of ``path`` (default: the cache) when it equals the
    committed one; raise DatasetChecksumError when it does not."""
    target = DATA_FILE if path is None else path
    want = expected_digest()
    got = digest(target)
    if got != want:
        raise DatasetChecksumError(
            f"{target.name}: SHA-256 {got} does not match the committed "
            f"{want} ({CHECKSUM_FILE.name}). Delete the cached file and fetch it "
            f"again; if the upstream dataset legitimately changed, review the "
            f"change and then update {CHECKSUM_FILE.name}.")
    return got


def _download_rows() -> list:
    """Download every row of the split (needs the network, pyarrow, requests)."""
    import pyarrow.parquet as pq  # only needed on first fetch
    import requests

    listing = requests.get(
        f"https://huggingface.co/api/datasets/{DATASET}/parquet/{CONFIG}/{SPLIT}",
        timeout=60,
    )
    listing.raise_for_status()
    rows: list = []
    for url in listing.json():
        print(f"  downloading {url}")
        blob = requests.get(url, timeout=600)
        blob.raise_for_status()
        table = pq.read_table(io.BytesIO(blob.content), columns=list(_KEEP))
        rows.extend(table.to_pylist())
    return rows


def fetch() -> Path:
    """Return the verified cache path, downloading it first when it is absent."""
    if DATA_FILE.exists():
        verify(DATA_FILE)
        return DATA_FILE
    rows = _download_rows()
    print(f"  {len(rows)} rows")
    DATA_DIR.mkdir(exist_ok=True)
    partial = DATA_FILE.with_name(DATA_FILE.name + ".part")
    with partial.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    try:
        verify(partial)
    except DatasetChecksumError:
        partial.unlink()  # never leave an unverified file behind
        raise
    partial.replace(DATA_FILE)
    return DATA_FILE


def load() -> list:
    path = fetch()
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


if __name__ == "__main__":
    print(f"cached at {fetch()} (SHA-256 verified)")
