"""AC 27: the benchmark dataset is verified against a committed SHA-256."""
import sys
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
    pinned = (ROOT / "benchmarks" / "dataset.sha256").read_text(encoding="ascii").split()[0]
    assert len(pinned) == 64 and set(pinned) <= set("0123456789abcdef")
    cache = ROOT / "benchmarks" / "data" / "codesearchnet_python_test_full.jsonl"
    if not cache.exists():
        pytest.skip("the dataset cache is not downloaded (CI never downloads it)")
    assert fetch_dataset.digest(cache) == pinned
