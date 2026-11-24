"""AC 27: the benchmark dataset is verified against a committed SHA-256."""
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks import fetch_dataset  # noqa: E402


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    """A tiny cached dataset and a committed checksum for it, in a temporary tree."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    data = data_dir / "cache.jsonl"
    data.write_bytes(b'{"a": 1}\n{"a": 2}\n')
    checksum = tmp_path / "dataset.sha256"
    monkeypatch.setattr(fetch_dataset, "DATA_DIR", data_dir)
    monkeypatch.setattr(fetch_dataset, "DATA_FILE", data)
    monkeypatch.setattr(fetch_dataset, "CHECKSUM_FILE", checksum)
    checksum.write_text(fetch_dataset.digest(data) + "  cache.jsonl" + chr(10), encoding="ascii")
    return data


def test_dataset_checksum_match_passes(dataset):
    assert fetch_dataset.verify() == fetch_dataset.digest(dataset)
    assert fetch_dataset.fetch() == dataset
    assert fetch_dataset.load() == [{"a": 1}, {"a": 2}]


def test_dataset_checksum_mismatch_fails(dataset):
    dataset.write_bytes(b'{"a": 1}\n{"a": 3}\n')  # one byte differs
    with pytest.raises(fetch_dataset.DatasetChecksumError) as info:
        fetch_dataset.fetch()
    message = str(info.value)
    assert fetch_dataset.digest(dataset) in message
    assert fetch_dataset.expected_digest() in message
    with pytest.raises(fetch_dataset.DatasetChecksumError):
        fetch_dataset.load()  # nothing is read from a file that failed the check
    assert dataset.exists()  # a mismatch reports; it does not delete the cache


def test_verifying_a_missing_cache_is_a_checksum_error(dataset):
    dataset.unlink()
    with pytest.raises(fetch_dataset.DatasetChecksumError, match="cannot read cache.jsonl"):
        fetch_dataset.verify()


def test_dataset_digest_does_not_depend_on_the_line_ending(dataset, tmp_path):
    lf = tmp_path / "lf.jsonl"
    lf.write_bytes(b'{"a": 1}\n{"a": 2}\n')
    crlf = tmp_path / "crlf.jsonl"
    crlf.write_bytes(b'{"a": 1}\r\n{"a": 2}\r\n')
    assert fetch_dataset.digest(lf) == fetch_dataset.digest(crlf)
    dataset.write_bytes(crlf.read_bytes())
    assert fetch_dataset.verify() == fetch_dataset.digest(lf)  # a Windows cache passes
    other = tmp_path / "other.jsonl"
    other.write_bytes(b'{"a": 1}\n{"a": 2}\n\n')
    assert fetch_dataset.digest(other) != fetch_dataset.digest(lf)


@pytest.mark.parametrize("content", ["", "not-a-digest", "A" * 64, "0" * 63, "0" * 65 + "x"])
def test_dataset_checksum_fails_closed_on_a_missing_or_malformed_pin(dataset, content):
    fetch_dataset.CHECKSUM_FILE.write_text(content, encoding="ascii")
    with pytest.raises(fetch_dataset.DatasetChecksumError):
        fetch_dataset.expected_digest()  # the pin itself is rejected, not just a mismatch
    with pytest.raises(fetch_dataset.DatasetChecksumError):
        fetch_dataset.verify()
    fetch_dataset.CHECKSUM_FILE.unlink()
    with pytest.raises(fetch_dataset.DatasetChecksumError):
        fetch_dataset.verify()


def test_a_download_is_verified_before_it_is_kept(dataset, monkeypatch):
    rows = [{"a": 1}, {"a": 2}]
    monkeypatch.setattr(fetch_dataset, "_download_rows", lambda: rows)
    dataset.unlink()
    path = fetch_dataset.fetch()  # same rows as the pinned file: kept
    assert path == dataset and path.read_bytes() == b'{"a": 1}\n{"a": 2}\n'  # LF on every OS
    assert not path.with_name(path.name + ".part").exists()

    dataset.unlink()
    monkeypatch.setattr(fetch_dataset, "_download_rows", lambda: [{"a": 1}, {"a": 999}])
    with pytest.raises(fetch_dataset.DatasetChecksumError):
        fetch_dataset.fetch()
    assert not dataset.exists()  # an unverified download is never left behind
    assert not dataset.with_name(dataset.name + ".part").exists()


def test_the_committed_checksum_is_well_formed_and_matches_a_local_cache():
    pinned = fetch_dataset.expected_digest(ROOT / "benchmarks" / "dataset.sha256")  # the strict parser
    assert len(pinned) == 64 and set(pinned) <= set("0123456789abcdef")
    cache = ROOT / "benchmarks" / "data" / "codesearchnet_python_test_full.jsonl"
    if not cache.exists():
        pytest.skip("the dataset cache is not downloaded (CI never downloads it)")
    assert fetch_dataset.digest(cache) == pinned


# --- the pin is exactly one line --------------------------------------------------------
_DIGEST = "0123456789abcdef" * 4


@pytest.mark.parametrize("content", [
    _DIGEST, _DIGEST + "\n", _DIGEST + "\r\n", _DIGEST + "  cache.jsonl",
    _DIGEST + "  cache.jsonl\n", _DIGEST + "  cache.jsonl\r\n",
])
def test_a_one_line_pin_is_accepted(dataset, content):
    fetch_dataset.CHECKSUM_FILE.write_bytes(content.encode("ascii"))
    assert fetch_dataset.expected_digest() == _DIGEST


@pytest.mark.parametrize("content, why", [
    (_DIGEST + "\n" + "f" * 64 + "\n", "a second line"),
    (" " + _DIGEST + "\n", "a leading space"),
    ("\n" + _DIGEST + "\n", "a leading blank line"),
    (_DIGEST + "\n\n", "a trailing blank line"),
    (_DIGEST + " \n", "a trailing space"),
    (_DIGEST + "  cache.jsonl extra\n", "trailing text after the name"),
    (_DIGEST + "  other.jsonl\n", "another file name"),
    (_DIGEST + " cache.jsonl\n", "one space before the name"),
    (_DIGEST + "\r", "a lone carriage return"),
])
def test_a_pin_that_is_not_exactly_one_line_is_rejected(dataset, content, why):
    fetch_dataset.CHECKSUM_FILE.write_bytes(content.encode("ascii"))
    with pytest.raises(fetch_dataset.DatasetChecksumError, match="must be one line"):
        fetch_dataset.expected_digest()
    assert why


def test_an_empty_pin_says_it_is_empty(dataset):
    fetch_dataset.CHECKSUM_FILE.write_bytes(b"")
    with pytest.raises(fetch_dataset.DatasetChecksumError, match="is empty"):
        fetch_dataset.expected_digest()


# --- the download: the pin first, then only https URLs on huggingface.co ----------------
def test_a_missing_pin_fails_before_anything_is_downloaded(dataset, monkeypatch):
    calls = []
    monkeypatch.setattr(fetch_dataset, "_download_rows", lambda: calls.append("download") or [])
    dataset.unlink()
    fetch_dataset.CHECKSUM_FILE.unlink()
    with pytest.raises(fetch_dataset.DatasetChecksumError):
        fetch_dataset.fetch()
    assert calls == []


_PARQUET = "https://huggingface.co/api/datasets/code-search-net/code_search_net/parquet/python/test/0.parquet"


def test_a_listing_of_https_urls_on_huggingface_is_followed():
    assert fetch_dataset.checked_urls([_PARQUET]) == [_PARQUET]


@pytest.mark.parametrize("listing", [
    ["http://huggingface.co/api/datasets/x/parquet/python/test/0.parquet"],
    ["https://example.com/0.parquet"],
    ["https://huggingface.co.example.com/0.parquet"],
    ["file:///etc/passwd"],
    [_PARQUET, 7],
    [_PARQUET] * (fetch_dataset.MAX_LISTED_FILES + 1),
    [],
    {"url": _PARQUET},
    _PARQUET,
])
def test_a_listing_outside_huggingface_https_is_refused(listing):
    with pytest.raises(fetch_dataset.DatasetSourceError):
        fetch_dataset.checked_urls(listing)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_the_download_refuses_the_listing_before_following_any_url(monkeypatch):
    fetched = []

    def get(url, timeout):
        fetched.append(url)
        return _Response(["http://huggingface.co/0.parquet"])

    parquet = types.ModuleType("pyarrow.parquet")
    pyarrow = types.ModuleType("pyarrow")
    pyarrow.parquet = parquet  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(get=get))
    monkeypatch.setitem(sys.modules, "pyarrow", pyarrow)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", parquet)
    with pytest.raises(fetch_dataset.DatasetSourceError, match="only https URLs on huggingface.co"):
        fetch_dataset._download_rows()
    assert len(fetched) == 1 and fetched[0].startswith("https://huggingface.co/api/")  # the listing only


# --- a failed download never leaves its temporary file -----------------------------------
def _part(dataset):
    return dataset.with_name(dataset.name + ".part")


@pytest.mark.parametrize("rows, error", [
    ([{"a": chr(0xD800)}], UnicodeEncodeError),  # a lone surrogate cannot be written as UTF-8
    ([{"a": object()}], TypeError),               # not a JSON value
])
def test_a_download_that_cannot_be_written_leaves_no_partial_file(dataset, monkeypatch, rows, error):
    monkeypatch.setattr(fetch_dataset, "_download_rows", lambda: rows)
    dataset.unlink()
    with pytest.raises(error):
        fetch_dataset.fetch()
    assert not _part(dataset).exists() and not dataset.exists()


def test_a_download_whose_check_fails_to_run_leaves_no_partial_file(dataset, monkeypatch):
    def broken(path=None):
        raise OSError("disk went away")

    monkeypatch.setattr(fetch_dataset, "_download_rows", lambda: [{"a": 1}, {"a": 2}])
    monkeypatch.setattr(fetch_dataset, "verify", broken)
    dataset.unlink()
    with pytest.raises(OSError, match="disk went away"):
        fetch_dataset.fetch()
    assert not _part(dataset).exists() and not dataset.exists()


# --- the results record the digest that was verified -------------------------------------
def test_the_results_record_the_digest_verify_returned(monkeypatch):
    from benchmarks import competitors

    monkeypatch.setattr(fetch_dataset, "verify", lambda path=None: "the verified digest")
    monkeypatch.setattr(fetch_dataset, "expected_digest", lambda pin=None: "the pin")
    info = competitors.dataset_info([{}, {}, {}], 7)
    assert info["sha256"] == "the verified digest"
    assert info["rows"] == 3 and info["records"] == 7
