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
published from a file that failed it. The digest reads every line ending as LF
so that it does not depend on the operating system and still verifies a cache
that an earlier version wrote with CRLF on Windows (new caches are written
with LF).

The pin is read before anything is downloaded. Only listed URLs of the plain
form https://huggingface.co/<path> are requested (DatasetSourceError
otherwise), and the redirects Hugging Face answers them with are followed. The
download has no size cap and the parquet file's own digest is not pinned: the
parquet files are parsed before the derived JSONL can be verified, so the
``benchmarks`` extra requires a pyarrow without CVE-2023-47248 (14.0.1 or
later).

    python -m benchmarks.fetch_dataset
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path
from typing import List, Optional

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


MAX_LISTED_FILES = 64     # the split is one parquet file today; a longer listing is refused
SOURCE_HOST = "huggingface.co"
# A listed URL must be exactly this shape. It is matched as text rather than parsed with
# urllib.parse, which disagrees with requests/urllib3 on URLs such as
# "https://evil.example\@huggingface.co/..." (urllib.parse sees huggingface.co, requests
# connects to evil.example): no user, port, query, fragment, backslash, space or control
# character can appear.
LISTED_URL = re.compile(r"https://huggingface\.co/[A-Za-z0-9._~%/-]+")


class DatasetChecksumError(RuntimeError):
    """The dataset (or the committed digest) is not what the benchmark expects."""


class DatasetSourceError(RuntimeError):
    """The download listing is not a short list of https URLs on huggingface.co."""


def digest(path: Path) -> str:
    """SHA-256 of the file with every CRLF line ending read as LF."""
    sha = hashlib.sha256()
    with path.open("rb") as fh:
        for line in fh:
            if line.endswith(b"\r\n"):
                line = line[:-2] + b"\n"
            sha.update(line)
    return sha.hexdigest()


def expected_digest(pin: Optional[Path] = None) -> str:
    """The committed digest, read from ``pin`` (default: benchmarks/dataset.sha256).

    The file must be exactly one line: a 64-character lower-case hexadecimal
    SHA-256, optionally followed by two spaces and the cache's file name, with at
    most one trailing newline (LF or CRLF). A missing, empty or malformed file is
    an error: the check fails closed rather than passing because nothing (or
    something ambiguous) was pinned."""
    source = CHECKSUM_FILE if pin is None else pin
    try:
        text = source.read_bytes().decode("ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise DatasetChecksumError(
            f"cannot read the committed checksum {source.name}: {exc}") from exc
    if not text:
        raise DatasetChecksumError(f"{source.name} is empty: it must hold the dataset's SHA-256")
    line = re.fullmatch(
        r"([0-9a-f]{64})(?:  " + re.escape(DATA_FILE.name) + r")?(?:\r\n|\n)?", text)
    if line is None:
        raise DatasetChecksumError(
            f"{source.name} must be one line: a 64-character lower-case hexadecimal "
            f"SHA-256, optionally followed by two spaces and {DATA_FILE.name}; "
            f"got {text[:120]!r}")
    return line.group(1)


def verify(path: Optional[Path] = None) -> str:
    """Return the digest of ``path`` (default: the cache) when it equals the
    committed one; raise DatasetChecksumError when it does not (or when the file
    cannot be read)."""
    target = DATA_FILE if path is None else path
    want = expected_digest()
    try:
        got = digest(target)
    except OSError as exc:
        raise DatasetChecksumError(
            f"cannot read {target.name} to verify it ({exc}); fetch it with "
            f"python -m benchmarks.fetch_dataset") from exc
    if got != want:
        raise DatasetChecksumError(
            f"{target.name}: SHA-256 {got} does not match the committed "
            f"{want} ({CHECKSUM_FILE.name}). Delete the cached file and fetch it "
            f"again; if the upstream dataset legitimately changed, review the "
            f"change and then update {CHECKSUM_FILE.name}.")
    return got


def checked_urls(listing: object) -> List[str]:
    """The parquet URLs of the listing response, refused (DatasetSourceError) unless
    it is a list of at most MAX_LISTED_FILES strings, each matching LISTED_URL (a
    plain https URL on huggingface.co). Nothing is downloaded until the whole
    listing passes."""
    if not isinstance(listing, list) or not 1 <= len(listing) <= MAX_LISTED_FILES:
        raise DatasetSourceError(
            f"the parquet listing must be a list of 1 to {MAX_LISTED_FILES} URLs, "
            f"got {type(listing).__name__} {str(listing)[:120]!r}")
    for url in listing:
        if not isinstance(url, str):
            raise DatasetSourceError(f"the parquet listing holds a non-URL entry {url!r:.120}")
        if LISTED_URL.fullmatch(url) is None:
            raise DatasetSourceError(
                f"refusing to download {url[:200]!r}: only plain https URLs on {SOURCE_HOST} "
                f"(no user, port, query, fragment, backslash or space) are requested")
    return list(listing)


def _download_rows() -> list:
    """Download every row of the split (needs the network, pyarrow, requests)."""
    import pyarrow.parquet as pq  # only needed on first fetch
    import requests

    listing = requests.get(
        f"https://{SOURCE_HOST}/api/datasets/{DATASET}/parquet/{CONFIG}/{SPLIT}",
        timeout=60,
    )
    listing.raise_for_status()
    rows: list = []
    for url in checked_urls(listing.json()):
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
    expected_digest()  # a missing or malformed pin fails before anything is downloaded
    rows = _download_rows()
    print(f"  {len(rows)} rows")
    DATA_DIR.mkdir(exist_ok=True)
    partial = DATA_FILE.with_name(DATA_FILE.name + ".part")
    try:
        with partial.open("w", encoding="utf-8", newline="\n") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        verify(partial)
    except BaseException:
        # whatever failed (the write, the encoding, the check, an interrupt), the
        # temporary file is removed; only a verified download is moved into place
        partial.unlink(missing_ok=True)
        raise
    partial.replace(DATA_FILE)
    return DATA_FILE


def load() -> list:
    path = fetch()
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


if __name__ == "__main__":
    print(f"cached at {fetch()} (SHA-256 verified)")
