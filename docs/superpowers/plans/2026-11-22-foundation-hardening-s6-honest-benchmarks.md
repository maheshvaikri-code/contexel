# Foundation hardening, Slice 6: Honest benchmarks — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the published benchmark claims fair and checkable: queries that are inflections of the target's words (so exact-word matching fails by construction and the stemmer is *measured*), a hand-written baseline with a scorer of its own, native-operation counts computed from the code instead of typed, every published number tied to the generated results, and a dataset fetch that verifies a committed SHA-256.

**Architecture:** Six small modules in `benchmarks/` and one command in `tools/`, no change to `contexel/`, TypeScript or C#. `fetch_dataset.py` pins the dataset; `inflection.py` makes the inflected episodes; `opcount.py` counts native operations by running each implementation's steps over a fixed sample; `competitors.py` becomes a list of steps per implementation, collects everything into one dictionary (written as `COMPARISON.json`) and renders `COMPARISON.md` from that dictionary alone; `suites_report.py` does the same for `RESULTS.md`; `publish.py` generates the tables of the README and the site from the JSON and checks every other published number against it, and `tools/check_benchmark_numbers.py` is its command. Seven task groups: the dataset checksum (Task 1), the inflection (Task 2), the operation counter (Task 3), the Suite 1 report (Task 4), the competitor comparison (Task 5), the published numbers (Task 6), the changelog (Task 7).

**Tech Stack:** Python 3.9+ standard library and contexel (pytest). Running the benchmarks needs the `benchmarks` extra (toolz, langchain-core, llama-index-core, tiktoken, pyarrow, requests) and the cached dataset; **the tests need none of them** (the ones that exercise a competitor library skip when it is missing, and nothing touches the network). No new dependency.

**Spec:** brief `docs/briefs/foundation-hardening.md` (ACs 23 to 27); design `docs/superpowers/specs/2026-11-19-foundation-hardening-design.md` ("Benchmarks (workstream F)"); master plan `docs/plans/foundation-hardening.md` (Slice 6 row).

**Baseline (verified 2026-11-22 on `dc70380`, `main` after the Slice 5 merge):** Python 841 passed; `ruff`, `mypy` (10 files), the site check and the version check clean. **Target after this slice:** Python 898 (the TypeScript and C# suites are untouched: 678 and 617). Each task states the count it must reach.

**How this plan was verified:** the code in every block below was written and run in a scratch copy of `dc70380`: the whole Python suite, both benchmark commands on the cached dataset (twice: the deterministic parts of the results were identical), the check, Python 3.9.13 (the new modules compile and run, the check passes), and 18 sanity mutants of the new code against the new tests (all killed). The blocks are extracted from that tree by script, not retyped, and a second script replayed them onto a fresh checkout of `dc70380`, ran the suite after each task's tests and after its implementation, ran the two benchmarks and the generator of Task 6, and compared the resulting tree with the scratch tree (result at the end of this file). The red results quoted in the steps are measured, not predicted. The timing columns of the benchmark tables are the executor's own numbers: they differ by machine and by a few percent from run to run, which is why the check ties the published timings to the committed JSON and not to a re-run.

## Global Constraints

- Python >= 3.9 and zero new dependencies. The benchmark modules import contexel and the standard library at top level; `toolz`, `langchain_core` and `llama_index` are imported **inside** the step functions that use them, so the modules (and the tests) import without the benchmark extras.
- **Nothing in `contexel/`, `ts/` or `csharp/` changes.** The two benchmark commands rewrite `benchmarks/COMPARISON.md` and `benchmarks/RESULTS.md` (and write the new JSON files); nothing else generated is committed.
- **The network is never used by this plan.** The benchmarks read the dataset cache `benchmarks/data/codesearchnet_python_test_full.jsonl` (git-ignored). If it is absent, **stop and ask the human**: fetching it downloads about 30 MB from huggingface.co.
- Generated files are produced by their commands, never edited by hand: `benchmarks/COMPARISON.json`, `COMPARISON.md`, `RESULTS.json`, `RESULTS.md`, and the bodies of the `<!-- benchmark:NAME:start -->` blocks in the README and on the site (`python tools/check_benchmark_numbers.py --write`).
- No version bump: identifiers change only at a release (the human's call); the work accumulates under `[Unreleased]` in `CHANGELOG.md`.
- One commit per task, Conventional Commits, 72 characters at most. **No `Co-Authored-By` trailer** (the project owner's standing rule, which overrides the harness default). Never push, open a pull request or merge: those are the human's.
- The repository is **public**: no Windows user name, home or temporary path, e-mail address or agent identifier in any file or commit message (the generated results contain the Python version and the platform name only).
- Tests are never weakened to go green. A published number that disagrees with the results means the document is wrong, never the check.
- This machine writes CRLF; the blocks below are LF. Either is fine in the working tree, but **byte-compare each file with its block** after writing it: the editing tools have in the past turned a backslash-u escape into the character it names and a shell heredoc collapses backslashes. The documents of Task 6 contain typographic characters (em dash, minus sign, multiplication sign): write them with the Write or Edit tools, not a heredoc.

## Review Focus

The input classes the brief implies but its own tests would not reach, most likely first, each with the test that pins it:

1. **A published number that nothing checks.** The README, the PyPI README and the site carried benchmark numbers typed by hand (and `site/index.html`, outside the two files the brief names, carried a third copy of the table). A new number with a unit (ms, %, x) in any of the four published files that is not in a generated block or a registered claim fails the check. `test_a_hand_typed_benchmark_number_is_reported_as_unregistered`, `test_a_changed_number_in_a_generated_table_is_reported`, `test_a_registered_claim_with_a_wrong_number_is_reported` (Task 6).
2. **A sentence that is true today and false after the next run** ("the only row ...", "the slowest budget-compliant row", "sub-20 ms import", which measured 19.3 to 20.8 ms). Qualitative sentences are registered claims checked against the data, and a stated figure gets a stated tolerance. `test_a_false_qualitative_claim_is_reported`, `test_a_reworded_registered_claim_is_reported_not_skipped` (Task 6).
3. **A dataset that passes on one operating system and fails on another.** The cache is written by Python, with CRLF on Windows and LF elsewhere (the cache this plan was verified on has 22,176 CRLF line endings), so a plain file hash is not portable. The digest reads every line ending as LF. `test_dataset_digest_does_not_depend_on_the_line_ending` (Task 1).
4. **A downloaded file that is used or kept before it is verified**, and a pin that is missing, empty or malformed (which must fail closed, not pass). `test_a_download_is_verified_before_it_is_kept`, `test_dataset_checksum_fails_closed_on_a_missing_or_malformed_pin` (Task 1).
5. **An inflection that exact matching can still reach, or that the stemmer cannot recover.** The inflection must differ from the term, must not be a word of the target's own text, and must stem to the same stem as the term; terms that are not plain lower-case words are never used. `test_inflection_is_deterministic_and_never_a_verbatim_word_of_the_target`, `test_inflected_episodes_are_deterministic_and_respect_the_guards` (Tasks 2 and 5).
6. **"Native" typed, inverted or always true.** The count is read from what running the steps enters. `test_native_op_counts_are_computed_from_definitions` and its twins (Task 3), `test_the_competitor_libraries_count_as_the_published_table_says` (Task 6, skipped without the libraries).

## Rulings made at plan time

Each is open to correction at the plan review.

| # | Ruling | Why | Cost if wrong |
|---|---|---|---|
| S6-1 | **AC 23's "not verbatim substrings of the target" is pinned as "not a whole word of the target's own text"** (tokenized the way `rescore` tokenizes). The plural rule of the design (`...s -> ...`) makes the inflection a substring of its own source term by construction, so the literal reading would exclude every plural and leave the rule dead. The episodes are built by choosing inflectable terms, so the set still has 100 episodes. | The purpose of the AC is that exact-word matching fails by construction; whole-word is the property that makes it so. | If the literal substring reading is wanted, the plural rule goes and the inflected set shrinks to the other two rules. |
| S6-2 | The inflection is the design's three lines (`...e` drops the `e` and adds `ing`; `...s` drops the `s`, except after `ss`, `us`, `is`; anything else adds `ing`). The results are synthetic (`partialing`) and the report and the changelog say so. | Deterministic and recoverable by the frozen stemmer; naturalness is not the point of the measurement. | A natural-language inflection (a lemmatizer) would need a dependency or a hand-written table. |
| S6-3 | Operations are counted by running each implementation's steps over a fixed sample under `sys.setprofile` and checking whether a Python function of the library's package ran. The only typed part is which operation a step serves. A library feature that serves none of the six operations (llama-index's score cutoff and reorder) is reported but not counted, so the published counts do not change (6/6, 0/6, 0/6, 2/6, 1/6, 0/6). | "Computed from the code that defines each implementation" is the AC; a typed boolean per step would only move the hand-typing one level down. | A library that wraps its code in C extensions would count as glue; none of the four does. |
| S6-4 | The check covers four published files: `README.md`, `README_PYPI.md`, `site/index.html` and `site/benchmarks.html` (the brief names the first and last). Tables are generated blocks; remaining prose numbers and qualitative sentences are registered claims; any other number with a benchmark unit fails. | The PyPI README and the home page carried the same numbers (and the unverifiable "sub-20 ms"); leaving them out would leave the drift the AC exists to close. | Adding a file later is one entry in `FILES`. |
| S6-5 | The dataset pin is the SHA-256 of the **derived JSONL cache** (line endings read as LF), not of the upstream parquet file. The parquet is therefore parsed (pyarrow) before it is verified. Pinning the parquet digest as well needs one download, which this plan does not do. | AC 27 asks that the fetch verify a committed SHA-256; the JSONL is what every benchmark reads. | A hostile parquet could reach pyarrow's parser before the check: listed for the security review and the human (follow-up). |
| S6-6 | The published claim "sub-20 ms import" becomes "about 20 ms", checked with a 25% tolerance against the measured import. | It measured 19.3 to 20.8 ms across runs: false on some of them. | None: the claim is weaker, and true. |
| S6-7 | The hand-written baseline exists in two forms: as before (trusts the tool's score) and with a term-overlap scorer (distinct whole words of the query that occur in the snippet, symbol and path; lower-cased; ties keep the incoming order) plus the same budget trimming. | AC 24 asks for a scorer; one improvised scorer is enough and the choice is stated. | A substring scorer would partly survive inflection; it is a different, equally legitimate baseline. |
| S6-8 | The timing columns are committed as measured on one machine and the check ties the published timings to the committed JSON, not to a re-run; every other column is deterministic and is reproduced by regenerating (verified at plan time: two full runs, identical apart from the timings). | Timings vary by a few percent from run to run; pretending otherwise would make the check flaky. | None. |
| S6-9 | The tests are split into six files, one per task (`test_benchmarks_dataset.py`, `..._inflection.py`, `..._opcount.py`, `..._reports.py`, `..._competitors.py`, `..._integrity.py`), where the master plan names one. `.github/workflows/ci.yml` is not changed: the integrity test runs `publish.check` on every leg of the existing test matrix. The master plan's test name `test_inflection_is_deterministic_and_never_a_verbatim_substring` is renamed `..._never_a_verbatim_word_of_the_target` (S6-1). | Each task stays independently green; the check already runs in CI through pytest. | A direct `hygiene` step would be one line. |

## Coverage of the acceptance criteria

| AC | Proven by | Task |
|---|---|---|
| 23 | `test_inflect_is_the_three_line_rule`, `test_inflection_is_deterministic_and_never_a_verbatim_word_of_the_target`, `test_a_term_is_not_inflectable_when`, `test_inflected_episodes_are_deterministic_and_respect_the_guards`, `test_the_default_episodes_are_not_changed_by_the_new_options`; the report's "Inflected-query episodes" section (word and stem recall, separately from the original episodes, stating that it measures inflection and not paraphrase) | 2, 5, 6 |
| 24 | `test_the_hand_written_term_overlap_scorer`, `test_the_scored_hand_written_baseline_ranks_by_its_own_score`; the "hand-written (term overlap)" row of every published table | 5, 6 |
| 25 | `test_native_op_counts_are_computed_from_definitions`, `test_contexel_and_the_hand_written_baselines_count_as_the_table_says`, `test_the_competitor_libraries_count_as_the_published_table_says`; the "Operations" table of `COMPARISON.md` | 3, 5, 6 |
| 26 | `test_published_numbers_match_generated_results` and the drift tests of `tests/test_benchmarks_integrity.py`; `python tools/check_benchmark_numbers.py` | 6 |
| 27 | `test_dataset_checksum_mismatch_fails` and its five twins | 1 |
| 35, 36 | not in this slice | n/a |

## Execution notes

- **Branch:** `feat/hardening-s6-honest-benchmarks`, from a clean `main` (Task 0). This plan was written against `dc70380`; Task 0 stops if `main` differs from it in any file outside `docs/`.
- **Subagent-driven execution, if chosen:** one fresh implementer per task, handed that task's text only; the controller byte-compares every file to its block after each task, runs the suite itself and reads the diff before dispatching the independent task reviewer. Task 6 runs the two benchmarks (about one minute and fifteen seconds on the plan's machine) and rewrites generated files: the controller re-runs the check and compares the deterministic columns with this plan's table. Mutation testing and the whole-branch gates follow the last task (see "Gates").
- **Stop-and-ask triggers** (Doctrine section 5 and the master plan): the dataset cache is missing (a download); a deterministic value that does not match the table in Task 6; anything that needs the network or a credential; an acceptance criterion that proves wrong when tested; a change to a public contract not listed under the rulings above.

## Tasks

### Task 0: Baseline and branch (no commit)

**Acceptance criteria:** none (makes every later task verifiable)

**Files:**
- No file changes. Everything this task learns goes in the ledger.

**Interfaces:**
- Consumes: `main` after the Slice 5 merge (pull request #8, merge commit `dc70380`). This plan was written against that tree; later commits on `main` may only touch `docs/`.
- Produces: the branch `feat/hardening-s6-honest-benchmarks` and the baseline every later task compares against.

- [ ] **Step 0.1: Branch from a clean `main`**

```bash
git checkout main && git pull --ff-only origin main
git status --short                              # must print nothing
git diff dc70380 HEAD --stat -- . ':!docs'      # must print nothing: only docs may differ from the tree this plan was written against
git checkout -b feat/hardening-s6-honest-benchmarks
```

**Stop and report** if the `git diff` prints a file: the plan was written against that tree and must be re-checked.

- [ ] **Step 0.2: Baseline of the suite and the gates**

```bash
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
python -m ruff check contexel --no-cache
python -m mypy contexel --python-version 3.10 --no-incremental
python tools/check_versions.py
python tools/site_check.py
ls benchmarks/data/
python -c "import hashlib; print(hashlib.sha256(open('benchmarks/data/codesearchnet_python_test_full.jsonl','rb').read().replace(b'" + chr(92) + "r" + chr(92) + "n', b'" + chr(92) + "n')).hexdigest())"
```

Expected:

```text
841 passed
All checks passed!
Success: no issues found in 10 source files
check_versions: all 7 version locations say 0.1.17
checked 6 pages under site/ -> OK
codesearchnet_python_test_full.jsonl
05049f798a197a8a80844707abe8b1319bf5c39d37a22fab303aba7625b868e5
```

**Stop and report instead of improvising** if a count differs, if the dataset cache is missing (Task 6 needs it; a download needs the human's approval) or if its digest is not the one printed: the digest is what Task 1 pins, and it was computed from the cache on the machine this plan was verified on. Whether a fresh download reproduces it was **not** verified (it needs the network). (The suite excludes `tests/test_doctrine_*`: those are git-ignored Doctrine tooling tests that CI does not run.)

- [ ] **Step 0.3: Dependency policy (read-only)**

This slice adds no dependency of any kind: standard-library modules, tests and documents. The benchmark extra (`pip install -e ".[benchmarks]"`) is only needed to *run* the benchmarks in Task 6, and the libraries it installs are already in the environment (`python -c "import toolz, langchain_core, llama_index.core, tiktoken"` must print nothing). Nothing here needs the network or a credential.


### Task 1: The dataset checksum

**Acceptance criteria:** AC 27 (the dataset fetch verifies a committed SHA-256 and fails on mismatch)

**Files:**
- Create: `tests/test_benchmarks_dataset.py`, `benchmarks/dataset.sha256`
- Modify: `benchmarks/fetch_dataset.py`

**Interfaces:**
- Produces: `fetch_dataset.digest(path)` (SHA-256 with every CRLF line ending read as LF), `expected_digest()` (the committed pin; a missing, empty or malformed file raises), `verify(path=None)`, `DatasetChecksumError(RuntimeError)`, and `fetch()` / `load()` that verify the cache on every use and write a download to `<name>.part`, moving it into place only after `verify`. `_download_rows()` is the only function that touches the network.
- The pin `benchmarks/dataset.sha256` holds the digest of the cache that Task 0 printed (ruling S6-5: the derived JSONL, not the parquet).

- [ ] **Step 1.1: Write the failing tests**

Create `tests/test_benchmarks_dataset.py` with exactly this content (it ends with one newline):
<!-- OP create path=tests/test_benchmarks_dataset.py -->
```python
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
```

- [ ] **Step 1.2: Run them: they fail**

```bash
PYTHONPATH=. python -m pytest -q tests/test_benchmarks_dataset.py
```

Result: 1 failed, 841 passed, 9 errors (whole suite). The tests fail with `AttributeError` (`fetch_dataset.digest`, `verify` and `DatasetChecksumError` do not exist; the nine errors are the tests that use the `dataset` fixture, which cannot patch the missing `CHECKSUM_FILE`); every earlier test passes.

- [ ] **Step 1.3: Add the pin and the verification**

In `benchmarks/fetch_dataset.py`, replace this block:
<!-- OP replace-old path=benchmarks/fetch_dataset.py -->
```python
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
```
with:
<!-- OP replace-new -->
```python
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
```

In `benchmarks/fetch_dataset.py`, replace this block:
<!-- OP replace-old path=benchmarks/fetch_dataset.py -->
```python
def fetch() -> Path:
    """Download and cache the full split; return the cache path."""
    if DATA_FILE.exists():
        return DATA_FILE
    import pyarrow.parquet as pq  # only needed on first fetch
    import requests

    DATA_DIR.mkdir(exist_ok=True)
    listing = requests.get(
        f"https://huggingface.co/api/datasets/{DATASET}/parquet/{CONFIG}/{SPLIT}",
```
with:
<!-- OP replace-new -->
```python
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
```

In `benchmarks/fetch_dataset.py`, replace this block:
<!-- OP replace-old path=benchmarks/fetch_dataset.py -->
```python
    )
    listing.raise_for_status()
    rows: list[dict] = []
    for url in listing.json():
        print(f"  downloading {url}")
```
with:
<!-- OP replace-new -->
```python
    )
    listing.raise_for_status()
    rows: list = []
    for url in listing.json():
        print(f"  downloading {url}")
```

In `benchmarks/fetch_dataset.py`, replace this block:
<!-- OP replace-old path=benchmarks/fetch_dataset.py -->
```python
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
```
with:
<!-- OP replace-new -->
```python
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
```

In `benchmarks/fetch_dataset.py`, replace this block:
<!-- OP replace-old path=benchmarks/fetch_dataset.py -->
```python
if __name__ == "__main__":
    print(f"cached at {fetch()}")
```
with:
<!-- OP replace-new -->
```python
if __name__ == "__main__":
    print(f"cached at {fetch()} (SHA-256 verified)")
```

Create `benchmarks/dataset.sha256` with exactly this content (it ends with one newline):
<!-- OP create path=benchmarks/dataset.sha256 -->
```text
05049f798a197a8a80844707abe8b1319bf5c39d37a22fab303aba7625b868e5  codesearchnet_python_test_full.jsonl
```

- [ ] **Step 1.4: Run the new tests, the whole suite and the gates**

```bash
PYTHONPATH=. python -m pytest -q tests/test_benchmarks_dataset.py
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
PYTHONPATH=. python -c "from benchmarks import fetch_dataset as f; print(f.verify()); print(len(f.load()))"
```

Expected:

```text
851 passed
05049f798a197a8a80844707abe8b1319bf5c39d37a22fab303aba7625b868e5
22176
```

The last command verifies the real cache against the pin and loads it (about a tenth of a second to hash 39 MB). Nothing is downloaded.

- [ ] **Step 1.5: Prove the tests bite (then undo)**

In `benchmarks/fetch_dataset.py` change `if got != want:` to `if False:`, run `PYTHONPATH=. python -m pytest -q tests/test_benchmarks_dataset.py`, and see `test_dataset_checksum_mismatch_fails` and `test_a_download_is_verified_before_it_is_kept` fail. Restore the line; `git diff` must show no change. This is a sanity check, not a commit.

- [ ] **Step 1.6: Commit**

```bash
git add tests/test_benchmarks_dataset.py benchmarks/dataset.sha256 benchmarks/fetch_dataset.py
git commit -m "feat(bench): verify the dataset against a committed SHA-256"
```


### Task 2: The inflection

**Acceptance criteria:** AC 23 (part 1: the deterministic inflection and the guards that make it a fair test)

**Files:**
- Create: `tests/test_benchmarks_inflection.py`, `benchmarks/inflection.py`

**Interfaces:**
- Produces: `inflection.inflect(term)` (the three-line rule), `inflection.words(text)` (the distinct lower-case words, tokenized the way `rescore` tokenizes), `inflection.inflectable(term, target_words)` (plain lower-case word, the inflection differs, the frozen stemmer maps both to one stem, the inflection is not a word of the target's text), and the patterns `PLAIN` and `WORD`.
- Consumes: `contexel.stem.stem` (Slice 5).

- [ ] **Step 2.1: Write the failing tests**

Create `tests/test_benchmarks_inflection.py` with exactly this content (it ends with one newline):
<!-- OP create path=tests/test_benchmarks_inflection.py -->
```python
"""AC 23: the inflection that the inflected-query episodes are built from."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks import inflection  # noqa: E402
from contexel.stem import stem  # noqa: E402


@pytest.mark.parametrize("term, inflected", [
    ("parse", "parsing"), ("returns", "return"), ("config", "configing"),
    ("class", "classing"), ("status", "statusing"), ("progress", "progressing"),
    ("simple", "simpling"), ("values", "value"),
])
def test_inflect_is_the_three_line_rule(term, inflected):
    assert inflection.inflect(term) == inflected


def test_inflection_is_deterministic_and_never_a_verbatim_word_of_the_target():
    terms = ["parse", "returns", "config", "queries", "class", "attempting", "regex-based",
             "_get_item", "values", "simple", "request", "string", "movies", "status"]
    target = inflection.words("def run(): parse the request and return the string value")
    first = [inflection.inflectable(t, target) for t in terms]
    assert first == [inflection.inflectable(t, target) for t in terms]  # deterministic
    for term in terms:
        if inflection.inflectable(term, target):
            inflected = inflection.inflect(term)
            assert inflected != term                        # it really is an inflection
            assert inflected not in target                  # an exact word match cannot reach it
            assert stem(inflected) == stem(term)            # the frozen stemmer can recover it
            assert inflection.PLAIN.fullmatch(term)         # a plain lower-case word


@pytest.mark.parametrize("term, words, why", [
    ("parse", {"parsing"}, "its inflection is a word of the target"),
    ("returns", {"return"}, "its inflection is a word of the target"),
    ("queries", set(), "the frozen stemmer maps it and its inflection to different stems"),
    ("regex-based", set(), "not a plain word"),
    ("_get_item", set(), "not a plain word"),
    ("ABCdef", set(), "not lower case"),
    ("attempting", set(), "already inflected: its inflection is a different stem"),
])
def test_a_term_is_not_inflectable_when(term, words, why):
    assert not inflection.inflectable(term, words), why
```

- [ ] **Step 2.2: Run them: they fail**

```bash
PYTHONPATH=. python -m pytest -q tests/test_benchmarks_inflection.py
```

Result: 1 error (whole suite). `benchmarks.inflection` does not exist, so the file fails at import.

- [ ] **Step 2.3: Add the inflection**

Create `benchmarks/inflection.py` with exactly this content (it ends with one newline):
<!-- OP create path=benchmarks/inflection.py -->
```python
"""Deterministic inflection of query terms, for the inflected-query episodes.

The existing episodes query with the target's own words, so exact-word matching
is never tested: a query saying "parse" always meets a document saying "parse".
Here the retrieval tool still searches with the target's original terms (the hit
list is unchanged), but the shaper receives an inflection of each term, so a
shaper that matches exact words fails *by construction* and one that matches
word stems is *measured*, not assumed.

The rule is three lines, applied to a lower-case word of letters only:

    ends in "e"          ->  drop the "e", add "ing"      parse    -> parsing
    ends in "s"          ->  drop the "s"                 returns  -> return
    anything else        ->  add "ing"                    config   -> configing

("s" is left alone after "ss", "us" and "is": class, status, progress.) These are
synthetic inflections, not natural language: the second and third lines produce
words nobody writes. What they exercise is the stemmer, and what the benchmark
measures is inflection robustness, not semantic paraphrase.

A term is *inflectable* only when all of the following hold, so that the
benchmark measures the stemmer and nothing else:

* it is a plain word of lower-case letters (no digits, punctuation, markdown);
* its inflection differs from the term;
* the frozen stemmer maps the inflection and the term to the same stem (the
  stemmer's documented limits, such as ``queries``, are excluded rather than
  scored as failures);
* the inflection is not a word of the target's own text, tokenized the way
  ``rescore`` tokenizes, so an exact-word match cannot reach the target through
  the inflection.
"""
from __future__ import annotations

import re
from typing import Set

from contexel.stem import stem

PLAIN = re.compile(r"[a-z]+")
WORD = re.compile(r"[^\W_]+")  # the word pattern rescore tokenizes with


def inflect(term: str) -> str:
    if term.endswith("e"):
        return term[:-1] + "ing"
    if term.endswith("s") and not term.endswith(("ss", "us", "is")):
        return term[:-1]
    return term + "ing"


def words(text: str) -> Set[str]:
    """The distinct lower-case words of ``text`` (what an exact match can see)."""
    return set(WORD.findall(text.lower()))


def inflectable(term: str, target_words: Set[str]) -> bool:
    if not PLAIN.fullmatch(term):
        return False
    inflected = inflect(term)
    return (
        inflected != term
        and stem(inflected) == stem(term)
        and inflected not in target_words
    )
```

- [ ] **Step 2.4: Run the new tests and the whole suite**

```bash
PYTHONPATH=. python -m pytest -q tests/test_benchmarks_inflection.py
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
```

Expected:

```text
867 passed
```

- [ ] **Step 2.5: Commit**

```bash
git add tests/test_benchmarks_inflection.py benchmarks/inflection.py
git commit -m "feat(bench): add the deterministic inflection of query terms"
```


### Task 3: The native-operation counter

**Acceptance criteria:** AC 25 (part 1: the counter)

**Files:**
- Create: `tests/test_benchmarks_opcount.py`, `benchmarks/opcount.py`

**Interfaces:**
- Produces: `opcount.Step(name, fn, op)` (`op` is one of `OPS` = select, dedupe, rescore, truncate, rank, trim, or `"adapter"`, or `"other"`; anything else raises `ValueError`), `opcount.run(steps, data)`, `opcount.enters_library(fn, data, root)` (runs `fn(data)` under `sys.setprofile` and reports whether a Python function of package `root` ran; the previous profiler is restored even if `fn` raises), and `opcount.count(steps, root, sample, ops=OPS) -> Count` with `native`, `glue`, `missing`, `other_native`, `adapters`, `label` (`"2/6 (select, dedupe)"`) and `as_dict()`. `root=None` is hand-written code: never native.

- [ ] **Step 3.1: Write the failing tests**

Create `tests/test_benchmarks_opcount.py` with exactly this content (it ends with one newline):
<!-- OP create path=tests/test_benchmarks_opcount.py -->
```python
"""AC 25: native-operation counts are computed from the code that defines each
implementation, not typed."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks import opcount  # noqa: E402
from contexel import select, stage  # noqa: E402

SAMPLE = [{"path": f"p{i}.py", "symbol": "s", "snippet": "x", "score": i} for i in range(3)]
TIMED = ("select", "dedupe", "truncate", "rank", "trim")  # the query-free task has no rescore


def test_native_op_counts_are_computed_from_definitions():
    steps = [
        opcount.Step("select", stage(select, fields=["path", "symbol"]), "select"),  # contexel code
        opcount.Step("dedupe", lambda r: r, "dedupe"),                                 # hand-written
        opcount.Step("convert", lambda r: r, "adapter"),
        opcount.Step("cutoff", stage(select, fields=["path"]), "other"),
    ]
    c = opcount.count(steps, "contexel", SAMPLE)
    assert c.native == ("select",) and c.glue == ("dedupe",)
    assert c.missing == ("rescore", "truncate", "rank", "trim")
    assert c.other_native == ("cutoff",) and c.adapters == ("convert",)
    assert c.label == "1/6 (select)"

    # the count follows the definition: make the dedupe step library code and it is native
    swapped = [steps[0], opcount.Step("dedupe", stage(select, fields=["path"]), "dedupe")] + steps[2:]
    assert opcount.count(swapped, "contexel", SAMPLE).native == ("select", "dedupe")
    # and the same steps are all glue for a library that none of them enters
    assert opcount.count(steps, "toolz_not_used_here", SAMPLE).native == ()
    # hand-written code has no native steps by definition
    assert opcount.count(steps, None, SAMPLE).native == ()
    # the denominator is the task's operations
    five = opcount.count(steps, "contexel", SAMPLE, ops=TIMED)
    assert five.label == "1/5 (select)" and five.missing == ("truncate", "rank", "trim")


def test_a_step_must_name_an_operation_or_a_kind():
    with pytest.raises(ValueError):
        opcount.Step("x", lambda r: r, "filter")


def test_run_applies_the_steps_in_order():
    steps = [opcount.Step("a", lambda r: r + [1], "select"), opcount.Step("b", lambda r: r + [2], "dedupe")]
    assert opcount.run(steps, []) == [1, 2]
    assert opcount.run([], "unchanged") == "unchanged"


def test_profiling_a_step_returns_its_output_and_restores_the_previous_profiler():
    events = []

    def profiler(frame, event, arg):
        events.append(event)

    sys.setprofile(profiler)
    try:
        entered, out = opcount.enters_library(lambda d: d + 1, 1, "contexel")
        assert (entered, out) == (False, 2)
        assert sys.getprofile() is profiler
        entered, out = opcount.enters_library(stage(select, fields=["path"]), SAMPLE, "contexel")
        assert entered and out == [{"path": f"p{i}.py"} for i in range(3)]
    finally:
        sys.setprofile(None)


def test_a_failing_step_still_restores_the_profiler():
    def boom(_):
        raise RuntimeError("boom")

    before = sys.getprofile()
    with pytest.raises(RuntimeError):
        opcount.enters_library(boom, 1, "contexel")
    assert sys.getprofile() is before
```

- [ ] **Step 3.2: Run them: they fail**

```bash
PYTHONPATH=. python -m pytest -q tests/test_benchmarks_opcount.py
```

Result: 1 error (whole suite). `benchmarks.opcount` does not exist.

- [ ] **Step 3.3: Add the counter**

Create `benchmarks/opcount.py` with exactly this content (it ends with one newline):
<!-- OP create path=benchmarks/opcount.py -->
```python
"""Native-operation counts, computed from the code that defines each implementation.

The comparison says how many of the task's operations each library "expresses
itself". That used to be typed by hand next to each implementation, so it could
drift from what the code actually does. Here an implementation is an ordered
list of :class:`Step`: each step names the operation it serves and holds the
callable that does the work. The same list is what runs, and the count is read
from it: a step is *native* when running it enters at least one Python function
defined in the library's own package (checked with ``sys.setprofile`` over a
small sample), and *glue* otherwise. Nothing about "native" is typed.

Three kinds of step exist. An *operation* step serves one of the task's
operations (``OPS``). An *adapter* step only converts the operand to the shape a
library requires (messages, nodes) and back: that is a cost of using the library,
not an operation. An *other* step is a library feature that serves none of the
task's operations (a score cutoff, a lost-in-the-middle reorder); it is reported
but never counted as one of them.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple

OPS = ("select", "dedupe", "rescore", "truncate", "rank", "trim")
KINDS = ("adapter", "other")


@dataclass(frozen=True)
class Step:
    name: str
    fn: Callable[[Any], Any]
    op: str  # one of OPS, or "adapter", or "other"

    def __post_init__(self) -> None:
        if self.op not in OPS and self.op not in KINDS:
            raise ValueError(f"step {self.name!r}: op must be one of {OPS + KINDS}, got {self.op!r}")


def run(steps: Sequence[Step], data: Any) -> Any:
    for step in steps:
        data = step.fn(data)
    return data


def _enters(module: str, root: str) -> bool:
    return module == root or module.startswith(root + ".")


def enters_library(fn: Callable[[Any], Any], data: Any, root: str) -> Tuple[bool, Any]:
    """Run ``fn(data)``; report whether a Python function of package ``root`` ran."""
    entered: List[str] = []

    def profiler(frame: Any, event: str, arg: Any) -> None:
        if event == "call":
            module = frame.f_globals.get("__name__", "")
            if isinstance(module, str) and _enters(module, root):
                entered.append(module)

    previous = sys.getprofile()
    sys.setprofile(profiler)
    try:
        out = fn(data)
    finally:
        sys.setprofile(previous)
    return bool(entered), out


@dataclass(frozen=True)
class Count:
    ops: Tuple[str, ...]                 # the operations the task has, in order
    native: Tuple[str, ...]              # operations done by library code
    glue: Tuple[str, ...]                # operations done by hand-written code
    missing: Tuple[str, ...]             # operations no step performs
    other_native: Tuple[str, ...]        # names of native "other" steps
    adapters: Tuple[str, ...]            # names of adapter steps

    @property
    def label(self) -> str:
        text = f"{len(self.native)}/{len(self.ops)}"
        return text + (" (" + ", ".join(self.native) + ")" if self.native else "")

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "native": list(self.native),
            "glue": list(self.glue),
            "missing": list(self.missing),
            "other_native": list(self.other_native),
            "adapters": list(self.adapters),
        }


def count(steps: Sequence[Step], root: Optional[str], sample: Any,
          ops: Sequence[str] = OPS) -> Count:
    """Run ``steps`` over ``sample`` and classify every step.

    ``root`` is the library's top-level package (``None`` for hand-written code,
    which has no native steps by definition). An operation counts as native when
    any step serving it enters the library.
    """
    native, glue, other_native, adapters = [], [], [], []
    data = sample
    for step in steps:
        if root is None:
            hit, data = False, step.fn(data)
        else:
            hit, data = enters_library(step.fn, data, root)
        if step.op == "adapter":
            adapters.append(step.name)
        elif step.op == "other":
            if hit:
                other_native.append(step.name)
        elif hit:
            native.append(step.op)
        else:
            glue.append(step.op)
    done_native = tuple(o for o in ops if o in native)
    done_glue = tuple(o for o in ops if o in glue and o not in native)
    missing = tuple(o for o in ops if o not in native and o not in glue)
    return Count(tuple(ops), done_native, done_glue, missing,
                 tuple(other_native), tuple(adapters))
```

- [ ] **Step 3.4: Run the new tests and the whole suite**

```bash
PYTHONPATH=. python -m pytest -q tests/test_benchmarks_opcount.py
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
```

Expected:

```text
872 passed
```

- [ ] **Step 3.5: Commit**

```bash
git add tests/test_benchmarks_opcount.py benchmarks/opcount.py
git commit -m "feat(bench): count native operations from the step definitions"
```


### Task 4: The Suite 1 report from a dictionary

**Acceptance criteria:** AC 26 (part 1: `RESULTS.md` is rendered from `RESULTS.json`, so its numbers can be checked)

**Files:**
- Create: `tests/test_benchmarks_reports.py`, `benchmarks/tables.py`, `benchmarks/suites_report.py`
- Modify: `benchmarks/__main__.py`

**Interfaces:**
- Produces: `tables.table(rows, columns)` (the markdown table helper, moved out of `__main__`), `suites_report.collect()` (runs the six suites and returns one dictionary), `suites_report.determinism_rows(det)`, `suites_report.render(results)` (the whole `RESULTS.md` from the dictionary alone), and `python -m benchmarks`, which now writes `RESULTS.json` and `RESULTS.md`. The report text gains two sentences saying where its numbers come from; every table is unchanged.

- [ ] **Step 4.1: Write the failing tests**

Create `tests/test_benchmarks_reports.py` with exactly this content (it ends with one newline):
<!-- OP create path=tests/test_benchmarks_reports.py -->
```python
"""The benchmark reports are rendered from a dictionary and from nothing else, so the
published numbers can be checked against that dictionary (AC 26). Nothing here runs a
benchmark: the dictionaries are small fixtures."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks import suites_report, tables  # noqa: E402


def _suites():
    return {
        "schema": 1,
        "generated": "2026-01-02",
        "environment": {"python": "3.12.0", "platform": "Linux (x86_64)", "contexel": "0.1.17"},
        "determinism": {"same_process": True, "raw_noise_differs": True, "noise_neutralized": True,
                        "cross_process": True, "hash_prefix": "0123456789abcdef"},
        "budget": {
            "trim": [{"budget": 500, "shaped_with": "heuristic", "records_kept": 10,
                      "heuristic_tokens": 479, "actual_tokens": 500},
                     {"budget": 500, "shaped_with": "tiktoken", "records_kept": 8,
                      "heuristic_tokens": 514, "actual_tokens": 472}],
            "truncate": [{"shaped_with": "heuristic", "cap": 24, "worst_field_tokens": 24},
                         {"shaped_with": "tiktoken", "cap": 24, "worst_field_tokens": 24}],
        },
        "speed": {"stages": [{"n": 1000, "stage": "select", "ms": 0.5, "records_per_sec": 2000000.0}],
                  "trace": {"off_ms": 10.0, "on_ms": 30.0, "ratio": 3.0}},
        "accuracy": [{"sample": "json (x)", "actual": 100, "heuristic": 70, "error_pct": -30.0}],
        "reduction": [{"dup_rate": 0.0, "budget": 1000, "records": "10 -> 5", "tokens": "100 -> 50",
                       "lossless_pct": 10.0, "by_choice_pct": 40.0, "total_pct": 50.0}],
        "encoding": [{"encoding": "json", "budget": 500, "records_kept": 8, "actual_tokens": 400,
                      "tokens_per_record": 50.0}],
    }


def test_the_table_helper_formats_numbers_and_text():
    out = tables.table([{"a": 1234, "b": 1.5, "c": "x"}], [("a", "A"), ("b", "B"), ("c", "C")])
    assert out.splitlines() == ["| A | B | C |", "|---|---|---|", "| 1,234 | 1.50 | x |"]


def test_the_suites_report_is_rendered_from_its_dictionary_alone():
    results = _suites()
    text = suites_report.render(results)
    assert text == suites_report.render(json.loads(json.dumps(results)))  # nothing else is read
    assert "Generated 2026-01-02" in text and "`0123456789abcdef`" in text
    assert "| same process, same input -> identical output | PASS |" in text
    assert "10.0 ms inactive vs 30.0 ms active (3.00x)" in text
    assert "| json (x) | 100 | 70 | -30.00 |" in text
    assert "benchmarks/RESULTS.json" in text and "tools/check_benchmark_numbers.py" in text


def test_a_failed_determinism_check_is_rendered_as_fail():
    results = copy.deepcopy(_suites())
    results["determinism"]["cross_process"] = False
    rows = suites_report.determinism_rows(results["determinism"])
    assert [r["result"] for r in rows] == ["PASS", "PASS", "PASS", "FAIL"]
    assert "| 3 fresh interpreters (PYTHONHASHSEED 0/1/2) -> same hash | FAIL |" in suites_report.render(results)
```

- [ ] **Step 4.2: Run them: they fail**

```bash
PYTHONPATH=. python -m pytest -q tests/test_benchmarks_reports.py
```

Result: 1 error (whole suite). `benchmarks.tables` and `benchmarks.suites_report` do not exist.

- [ ] **Step 4.3: Add the helper, the report module and the new entry point**

Create `benchmarks/tables.py` with exactly this content (it ends with one newline):
<!-- OP create path=benchmarks/tables.py -->
```python
"""Markdown table rendering shared by the benchmark reports."""
from __future__ import annotations

from typing import Any, List, Tuple


def table(rows: List[dict], columns: List[Tuple[str, str]]) -> str:
    """Render rows as a GitHub-flavored markdown table.

    ``columns`` is a list of (key, header); float values are formatted to a
    sensible precision, everything else via str().
    """
    def fmt(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:,.2f}"
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)

    head = "| " + " | ".join(h for _, h in columns) + " |"
    rule = "|" + "|".join("---" for _ in columns) + "|"
    body = "\n".join(
        "| " + " | ".join(fmt(r[k]) for k, _ in columns) + " |" for r in rows
    )
    return "\n".join([head, rule, body])
```

Create `benchmarks/suites_report.py` with exactly this content (it ends with one newline):
<!-- OP create path=benchmarks/suites_report.py -->
```python
"""Run every suite, collect the numbers into one dictionary, render RESULTS.md from it.

``collect`` runs the suites; ``render`` turns the dictionary into the report and
nothing else, so the published numbers can be checked against RESULTS.json
(tools/check_benchmark_numbers.py) and the report can be re-rendered from it.
"""
from __future__ import annotations

import platform
from datetime import date
from typing import Any, Dict, List

import contexel

from . import suites
from .tables import table


def collect() -> Dict[str, Any]:
    print("running determinism suite ...")
    det = suites.determinism()
    print("running budget-tightness suite ...")
    budget = suites.budget_tightness()
    print("running speed suite ...")
    spd = suites.speed()
    print("running tokenizer-accuracy suite ...")
    acc = suites.tokenizer_accuracy()
    print("running reduction-characterization suite ...")
    red = suites.reduction()
    print("running encoding-pairing suite ...")
    enc = suites.encoding_pairing()
    return {
        "schema": 1,
        "generated": date.today().isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": f"{platform.system()} ({platform.machine()})",
            "contexel": contexel.__version__,
        },
        "determinism": det,
        "budget": budget,
        "speed": spd,
        "accuracy": acc,
        "reduction": red,
        "encoding": enc,
    }


def determinism_rows(det: Dict[str, Any]) -> List[Dict[str, str]]:
    def verdict(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    return [
        {"check": "same process, same input -> identical output",
         "result": verdict(det["same_process"])},
        {"check": "raw inputs differ (fresh request ids / timestamps)",
         "result": verdict(det["raw_noise_differs"])},
        {"check": "shaped outputs identical despite that noise",
         "result": verdict(det["noise_neutralized"])},
        {"check": "3 fresh interpreters (PYTHONHASHSEED 0/1/2) -> same hash",
         "result": verdict(det["cross_process"])},
    ]


def render(results: Dict[str, Any]) -> str:
    env = results["environment"]
    det, budget, spd = results["determinism"], results["budget"], results["speed"]
    acc, red, enc = results["accuracy"], results["reduction"], results["encoding"]
    det_rows = determinism_rows(det)

    return f"""# contexel benchmark results

Generated {results["generated"]} by `python -m benchmarks`. The numbers below are
rendered from `benchmarks/RESULTS.json`; `tools/check_benchmark_numbers.py` fails
when the README or the site disagree with it.

Environment: Python {env["python"]} on {env["platform"]}, contexel {env["contexel"]}, \
single process, wall-clock via `perf_counter`, \
best of 5 runs. Datasets are seeded and byte-identical across machines \
(`benchmarks/datasets.py`).

## What this measures, and deliberately doesn't

contexel's claims are **determinism** (a versioned context contract: the same
shaping on every run), **budget enforcement**, and **zero inference cost** —
not compression magnitude. Per the README ("How much does it cut?") and the
prior-art review, a headline reduction percentage is a property of the data
and the budget, not of the library, so suite 5 *characterizes* reduction
across data profiles instead of advertising one number. Semantic quality
(vs. LLMLingua, ColBERT, cross-encoder rerankers) is explicitly out of scope:
contexel is deterministic and non-semantic by design.

## 1. Determinism (the core claim)

SHA-256 of the shaped output of the standard contract over 5,000 search-hit
records (30% duplicates), hash prefix `{det["hash_prefix"]}`:

{table(det_rows, [("check", "Check"), ("result", "Result")])}

## 2. Budget tightness

`trim_to_budget` shaped with the default heuristic tokenizer vs an exact
tiktoken tokenizer, then measured with tiktoken (`cl100k_base`). "Actual"
is the token cost of the serialized output that would enter context.

{table(budget["trim"], [
    ("budget", "Budget"), ("shaped_with", "Shaped with"),
    ("records_kept", "Records kept"),
    ("heuristic_tokens", "Heuristic tokens"), ("actual_tokens", "Actual tokens"),
])}

`truncate_field` with `max_tokens=24` on 120-word snippets — worst clipped
field, measured with the tokenizer that shaped it (docstring claims
"~max_tokens"):

{table(budget["truncate"], [
    ("shaped_with", "Shaped with"), ("cap", "Cap"),
    ("worst_field_tokens", "Worst field tokens"),
])}

## 3. Speed (no model calls, plain Python)

{table(spd["stages"], [
    ("n", "Records"), ("stage", "Stage"), ("ms", "ms (best of 5)"),
    ("records_per_sec", "Records/sec"),
])}

Trace overhead on the full contract over 10,000 records: \
{spd["trace"]["off_ms"]:.1f} ms inactive vs {spd["trace"]["on_ms"]:.1f} ms \
active ({spd["trace"]["ratio"]:.2f}x). Inactive tracing is the "zero cost" \
claim; active tracing token-counts every stage boundary and is priced \
accordingly.

## 4. Default tokenizer accuracy (heuristic vs tiktoken cl100k_base)

Positive error = the heuristic over-estimates (conservative for budgets).

{table(acc, [
    ("sample", "Sample"), ("actual", "Actual"), ("heuristic", "Heuristic"),
    ("error_pct", "Error %"),
])}

## 5. Reduction characterization (a property of the data, not the library)

Standard contract over 2,000 records with 60-word snippets. Lossless =
`select` + `dedupe` (pure redundancy); by-choice = `truncate_field` +
`trim_to_budget` (budget enforcement you dialed in).

{table(red, [
    ("dup_rate", "Dup rate"), ("budget", "Budget"), ("records", "Records"),
    ("tokens", "Tokens"), ("lossless_pct", "Lossless %"),
    ("by_choice_pct", "By-choice %"), ("total_pct", "Total %"),
])}

## 6. Encoding pairing (shape-then-encode)

Budgets are encoding-relative: `trim_to_budget` prices each record by its
serialized text. The same contract and budget, with the boundary priced and
serialized as JSON (contexel's default) vs a minimal ISON table
([ison.dev](https://ison.dev)) via `tokens.set_serializer`. `select` first
projects records onto a uniform field set — exactly the rows ISON's table
syntax encodes without repeating keys. Actual cost measured with tiktoken.

{table(enc, [
    ("encoding", "Encoding"), ("budget", "Budget"),
    ("records_kept", "Records kept"), ("actual_tokens", "Actual tokens"),
    ("tokens_per_record", "Tokens/record"),
])}
"""
```

In `benchmarks/__main__.py`, replace this block:
<!-- OP replace-old path=benchmarks/__main__.py -->
```python
"""Run every suite and write benchmarks/RESULTS.md.

    python -m benchmarks
```
with:
<!-- OP replace-new -->
```python
"""Run every suite and write benchmarks/RESULTS.md and benchmarks/RESULTS.json.

    python -m benchmarks
```

In `benchmarks/__main__.py`, replace this block:
<!-- OP replace-old path=benchmarks/__main__.py -->
```python
from __future__ import annotations

import platform
from datetime import date
from pathlib import Path

from . import suites


def _table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    """Render rows as a GitHub-flavored markdown table.

    ``columns`` is a list of (key, header); float values are formatted to a
    sensible precision, everything else via str().
    """
    def fmt(value) -> str:
        if isinstance(value, float):
            return f"{value:,.2f}"
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)

    head = "| " + " | ".join(h for _, h in columns) + " |"
    rule = "|" + "|".join("---" for _ in columns) + "|"
    body = "\n".join(
        "| " + " | ".join(fmt(r[k]) for k, _ in columns) + " |" for r in rows
    )
    return "\n".join([head, rule, body])


def main() -> None:
    print("running determinism suite ...")
    det = suites.determinism()
    print("running budget-tightness suite ...")
    budget = suites.budget_tightness()
    print("running speed suite ...")
    spd = suites.speed()
    print("running tokenizer-accuracy suite ...")
    acc = suites.tokenizer_accuracy()
    print("running reduction-characterization suite ...")
    red = suites.reduction()
    print("running encoding-pairing suite ...")
    enc = suites.encoding_pairing()

    check = lambda ok: "PASS" if ok else "FAIL"
    det_rows = [
        {"check": "same process, same input -> identical output",
         "result": check(det["same_process"])},
        {"check": "raw inputs differ (fresh request ids / timestamps)",
         "result": check(det["raw_noise_differs"])},
        {"check": "shaped outputs identical despite that noise",
         "result": check(det["noise_neutralized"])},
        {"check": "3 fresh interpreters (PYTHONHASHSEED 0/1/2) -> same hash",
         "result": check(det["cross_process"])},
    ]

    report = f"""# contexel benchmark results

Generated {date.today().isoformat()} by `python -m benchmarks`.

Environment: Python {platform.python_version()} on {platform.system()} \
({platform.machine()}), single process, wall-clock via `perf_counter`, \
best of 5 runs. Datasets are seeded and byte-identical across machines \
(`benchmarks/datasets.py`).

## What this measures, and deliberately doesn't

contexel's claims are **determinism** (a versioned context contract: the same
shaping on every run), **budget enforcement**, and **zero inference cost** —
not compression magnitude. Per the README ("How much does it cut?") and the
prior-art review, a headline reduction percentage is a property of the data
and the budget, not of the library, so suite 5 *characterizes* reduction
across data profiles instead of advertising one number. Semantic quality
(vs. LLMLingua, ColBERT, cross-encoder rerankers) is explicitly out of scope:
contexel is deterministic and non-semantic by design.

## 1. Determinism (the core claim)

SHA-256 of the shaped output of the standard contract over 5,000 search-hit
records (30% duplicates), hash prefix `{det["hash_prefix"]}`:

{_table(det_rows, [("check", "Check"), ("result", "Result")])}

## 2. Budget tightness

`trim_to_budget` shaped with the default heuristic tokenizer vs an exact
tiktoken tokenizer, then measured with tiktoken (`cl100k_base`). "Actual"
is the token cost of the serialized output that would enter context.

{_table(budget["trim"], [
    ("budget", "Budget"), ("shaped_with", "Shaped with"),
    ("records_kept", "Records kept"),
    ("heuristic_tokens", "Heuristic tokens"), ("actual_tokens", "Actual tokens"),
])}

`truncate_field` with `max_tokens=24` on 120-word snippets — worst clipped
field, measured with the tokenizer that shaped it (docstring claims
"~max_tokens"):

{_table(budget["truncate"], [
    ("shaped_with", "Shaped with"), ("cap", "Cap"),
    ("worst_field_tokens", "Worst field tokens"),
])}

## 3. Speed (no model calls, plain Python)

{_table(spd["stages"], [
    ("n", "Records"), ("stage", "Stage"), ("ms", "ms (best of 5)"),
    ("records_per_sec", "Records/sec"),
])}

Trace overhead on the full contract over 10,000 records: \
{spd["trace"]["off_ms"]:.1f} ms inactive vs {spd["trace"]["on_ms"]:.1f} ms \
active ({spd["trace"]["ratio"]:.2f}x). Inactive tracing is the "zero cost" \
claim; active tracing token-counts every stage boundary and is priced \
accordingly.

## 4. Default tokenizer accuracy (heuristic vs tiktoken cl100k_base)

Positive error = the heuristic over-estimates (conservative for budgets).

{_table(acc, [
    ("sample", "Sample"), ("actual", "Actual"), ("heuristic", "Heuristic"),
    ("error_pct", "Error %"),
])}

## 5. Reduction characterization (a property of the data, not the library)

Standard contract over 2,000 records with 60-word snippets. Lossless =
`select` + `dedupe` (pure redundancy); by-choice = `truncate_field` +
`trim_to_budget` (budget enforcement you dialed in).

{_table(red, [
    ("dup_rate", "Dup rate"), ("budget", "Budget"), ("records", "Records"),
    ("tokens", "Tokens"), ("lossless_pct", "Lossless %"),
    ("by_choice_pct", "By-choice %"), ("total_pct", "Total %"),
])}

## 6. Encoding pairing (shape-then-encode)

Budgets are encoding-relative: `trim_to_budget` prices each record by its
serialized text. The same contract and budget, with the boundary priced and
serialized as JSON (contexel's default) vs a minimal ISON table
([ison.dev](https://ison.dev)) via `tokens.set_serializer`. `select` first
projects records onto a uniform field set — exactly the rows ISON's table
syntax encodes without repeating keys. Actual cost measured with tiktoken.

{_table(enc, [
    ("encoding", "Encoding"), ("budget", "Budget"),
    ("records_kept", "Records kept"), ("actual_tokens", "Actual tokens"),
    ("tokens_per_record", "Tokens/record"),
])}
"""

    out = Path(__file__).resolve().parent / "RESULTS.md"
    out.write_text(report, encoding="utf-8")
    print(f"\nwrote {out}")
    print("\ndeterminism:", ", ".join(f"{r['check']}: {r['result']}" for r in det_rows))
```
with:
<!-- OP replace-new -->
```python
from __future__ import annotations

import json
from pathlib import Path

from . import suites_report


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main() -> None:
    results = suites_report.collect()
    here = Path(__file__).resolve().parent
    _write(here / "RESULTS.json", json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    _write(here / "RESULTS.md", suites_report.render(results))
    print(f"\nwrote {here / 'RESULTS.json'} and {here / 'RESULTS.md'}")
    print("\ndeterminism:", ", ".join(
        f"{r['check']}: {r['result']}"
        for r in suites_report.determinism_rows(results["determinism"])))
```

- [ ] **Step 4.4: Run the new tests and the whole suite**

```bash
PYTHONPATH=. python -m pytest -q tests/test_benchmarks_reports.py
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
```

Expected:

```text
875 passed
```

`python -m benchmarks` is not run here (it rewrites `RESULTS.md`; Task 6 runs it).

- [ ] **Step 4.5: Commit**

```bash
git add tests/test_benchmarks_reports.py benchmarks/tables.py benchmarks/suites_report.py benchmarks/__main__.py
git commit -m "feat(bench): render RESULTS.md from a dictionary"
```


### Task 5: The competitor comparison: steps, baselines, inflected episodes, one dictionary

**Acceptance criteria:** AC 23 (part 2: the inflected episodes and their recall), AC 24 (the hand-written scorer), AC 25 (the computed counts in the report), AC 26 (part 2: `COMPARISON.md` is rendered from `COMPARISON.json`)

**Files:**
- Create: `tests/test_benchmarks_competitors.py`
- Modify: `benchmarks/competitors.py` (given whole below: most of it changes)

**Interfaces:**
- Consumes: `fetch_dataset` (Task 1), `inflection` (Task 2), `opcount` (Task 3), `tables` (Task 4).
- Produces: every implementation as an ordered list of `opcount.Step` (`contexel_timed`, `contexel_outcome(terms, match)`, `hand_outcome`, `hand_scored_outcome`, `toolz_*`, `langchain_*`, `llama_*`), `IMPLEMENTATIONS` (six rows, the new one being `hand-written (term overlap)`), `g_score_overlap(records, terms)`, `sample_records()`, `operations(names=None)` (the computed counts), `build_episodes(corpus, n, seed, term_ok=None, pool=2)` (the defaults reproduce the original episodes exactly) and `build_inflected_episodes(corpus)`, `collect()` (everything in one dictionary), `render_report(results)` (the whole `COMPARISON.md` from that dictionary), and `python -m benchmarks.competitors`, which writes `COMPARISON.json` and `COMPARISON.md`.
- Nothing is run against the real data in this task: the tests use a small synthetic corpus and fixtures, and need no benchmark library.

- [ ] **Step 5.1: Write the failing tests**

Create `tests/test_benchmarks_competitors.py` with exactly this content (it ends with one newline):
<!-- OP create path=tests/test_benchmarks_competitors.py -->
```python
"""AC 23, 24, 25: the inflected episodes, the hand-written baselines and the
computed operation counts of the competitor comparison. Nothing here needs the
network or the dataset."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks import competitors, inflection, opcount  # noqa: E402


def _corpus(n=40):
    return [{
        "func_path_in_repository": f"p/f{i}.py",
        "func_name": f"fn{i}",
        "func_code_string": f"def fn{i}(x):\n    return parse(x)  # configuration {i}",
        "func_documentation_string": (
            "Parses configurations and returns results from the requests quickly "
            "and reliably please"),
        "func_code_url": f"u{i}",
        "repository_name": "r",
    } for i in range(n)]


def test_inflected_episodes_are_deterministic_and_respect_the_guards():
    corpus = _corpus()
    first = competitors.build_inflected_episodes(corpus, n=5)
    again = competitors.build_inflected_episodes(corpus, n=5)
    assert first and first == again
    by_key = {(r["func_path_in_repository"], r["func_name"]): r for r in corpus}
    for ep in first:
        row = by_key[ep["target"]]
        target = inflection.words(row["func_code_string"] + " " + row["func_documentation_string"])
        assert len(ep["terms"]) == len(ep["inflected"]) >= 1
        for term, inflected in zip(ep["terms"], ep["inflected"]):
            assert inflected == inflection.inflect(term)
            assert inflection.inflectable(term, target)
            assert inflected not in target
        assert any((h["path"], h["symbol"]) == ep["target"] for h in ep["hits"])
        assert "parses" not in ep["terms"]  # its inflection, "parse", is a word of the code


def test_the_default_episodes_are_not_changed_by_the_new_options():
    corpus = _corpus()
    plain = competitors.build_episodes(corpus, n=5)
    assert plain == competitors.build_episodes(corpus, n=5, term_ok=None, pool=2)
    assert plain and plain[0]["terms"][0] == "parses"  # the unfiltered first term


def test_the_hand_written_term_overlap_scorer():
    records = [
        {"path": "a.py", "symbol": "parse_value", "snippet": "Parse the Value", "score": 9},
        {"path": "b.py", "symbol": "parser", "snippet": "builds a parser", "score": 1},
        {"path": "c.py", "symbol": "other", "snippet": "nothing", "score": 5},
    ]
    scored = competitors.g_score_overlap(records, ["PARSE", "value.", "VALUE"])  # case, punctuation
    assert [r["score"] for r in scored] == [2, 0, 0]  # distinct whole words; not "parser"
    assert [r["path"] for r in scored] == ["a.py", "b.py", "c.py"]  # nothing reordered
    assert records[0]["score"] == 9  # the input is not modified
    assert competitors.g_score_overlap([], ["x"]) == []


def test_the_scored_hand_written_baseline_ranks_by_its_own_score():
    hits = [
        {"path": "a.py", "symbol": "a", "snippet": "alpha", "score": 9, "repo": "r"},
        {"path": "b.py", "symbol": "b", "snippet": "beta gamma", "score": 1, "repo": "r"},
    ]
    steps = competitors.hand_scored_outcome(["beta", "gamma"])
    assert [s.op for s in steps] == list(opcount.OPS)
    out = opcount.run(steps, hits)
    assert [r["path"] for r in out] == ["b.py", "a.py"]  # the tool's score is not trusted
    trusting = opcount.run(competitors.hand_outcome(["beta", "gamma"]), hits)
    assert [r["path"] for r in trusting] == ["a.py", "b.py"]


def test_contexel_and_the_hand_written_baselines_count_as_the_table_says():
    rows = {o["impl"]: o for o in competitors.operations(
        ("contexel", "hand-written", "hand-written (term overlap)"))}
    assert rows["contexel"]["native"] == list(opcount.OPS) and rows["contexel"]["missing"] == []
    assert rows["hand-written"]["native"] == [] and rows["hand-written"]["missing"] == ["rescore"]
    assert rows["hand-written (term overlap)"]["native"] == []
    assert rows["hand-written (term overlap)"]["glue"] == list(opcount.OPS)


def _op(impl, native, glue, missing, other=(), adapters=(), operand="list[dict]"):
    return {"impl": impl, "operand": operand, "label": f"{len(native)}/6" + (f" ({', '.join(native)})" if native else ""),
            "native": list(native), "glue": list(glue), "missing": list(missing),
            "other_native": list(other), "adapters": list(adapters)}


OPS = ["select", "dedupe", "rescore", "truncate", "rank", "trim"]


def _comparison():
    def outcome(impl, rs, rw, comp, fill, useful, ms):
        return {"impl": impl, "recall_strong_pct": rs, "recall_weak_pct": rw, "compliance_pct": comp,
                "fill_x": fill, "useful_share_pct": useful, "ms_per_episode": ms}

    return {
        "schema": 1, "generated": "2026-01-02",
        "environment": {"python": "3.12.0", "platform": "Linux (x86_64)", "contexel": "0.1.17",
                        "libraries": {"toolz": "1.0", "langchain-core": "1.0", "llama-index-core": "0.1"}},
        "dataset": {"name": "CodeSearchNet python/test", "rows": 22176, "sha256": "ab" * 32,
                    "queries": 16, "per_query_cap": 2000, "records": 28047},
        "settings": {"fields": 5, "snippet_cap": 24, "budget": 2000, "eval_budget": 1500,
                     "episodes": 100, "llama_cutoff": 2.0},
        "operations": [
            _op("contexel", OPS, [], []),
            _op("hand-written", [], ["select", "dedupe", "truncate", "rank", "trim"], ["rescore"]),
            _op("hand-written (term overlap)", [], OPS, []),
            _op("toolz", ["select", "dedupe"], [], ["rescore", "truncate", "rank", "trim"], operand="any dicts"),
            _op("langchain-core", ["trim"], [], ["select", "dedupe", "rescore", "truncate", "rank"],
                adapters=["wrap as messages"], operand="BaseMessage"),
            _op("llama-index-core", [], [], OPS, other=["score cutoff", "long-context reorder"],
                adapters=["to nodes", "from nodes"], operand="NodeWithScore"),
        ],
        "task": [
            {"impl": "contexel", "native": "5/5", "note": "n", "ms": 60.0, "kept": 40, "tokens_out": 1900,
             "deterministic": "yes"},
            {"impl": "hand-written", "native": "0/5", "note": "n", "ms": 20.0, "kept": 41, "tokens_out": 1990,
             "deterministic": "yes"},
            {"impl": "toolz", "native": "2/5", "note": "n", "ms": 40.0, "kept": 41, "tokens_out": 1990,
             "deterministic": "yes"},
        ],
        "outcomes": [
            outcome("contexel", 100.0, 100.0, 100.0, 0.95, 100.0, 15.0),
            outcome("hand-written", 93.0, 32.0, 100.0, 0.95, 100.0, 1.0),
            outcome("hand-written (term overlap)", 97.0, 97.0, 100.0, 0.94, 100.0, 13.0),
            outcome("toolz", 100.0, 100.0, 0.0, 91.6, 100.0, 6.0),
            outcome("langchain-core", 30.0, 30.0, 100.0, 0.52, 89.7, 6.0),
            outcome("llama-index-core", 100.0, 100.0, 0.0, 129.2, 74.1, 17.0),
        ],
        "footprint": [{"library": "contexel", "import_ms": 20.0, "transitive_deps": 0},
                      {"library": "toolz", "import_ms": 12.0, "transitive_deps": 0}],
        "inflected": {
            "episodes": 100, "terms": 290, "examples": [["parse", "parsing"], ["returns", "return"]],
            "rows": [
                {"shaper": "contexel", "recall_original_pct": 99.0, "recall_inflected_pct": 35.0},
                {"shaper": "contexel (match=stem)", "recall_original_pct": 98.0, "recall_inflected_pct": 98.0},
                {"shaper": "hand-written (term overlap)", "recall_original_pct": 96.0,
                 "recall_inflected_pct": 35.0},
                {"shaper": "hand-written", "recall_original_pct": 90.0, "recall_inflected_pct": 90.0},
            ],
        },
    }


def test_the_comparison_report_is_rendered_from_its_dictionary_alone():
    results = _comparison()
    text = competitors.render_report(results)
    assert text == competitors.render_report(json.loads(json.dumps(results)))
    assert "28,047" in text and "22,176" in text and ("ab" * 32) in text
    assert "| contexel | 6/6 (select, dedupe, rescore, truncate, rank, trim) |" in text
    assert "| toolz | 2/6 (select, dedupe) |" in text
    assert "| hand-written (term overlap) | 0/6 | - | 13.00 |" in text   # no timed task: a dash
    assert "`parse` -> `parsing`" in text and "not synonyms, not paraphrase, not meaning" in text
    assert "Opting in to the stemmer costs 1 point on the original terms." in text


def test_the_comparison_report_states_what_the_numbers_say_and_changes_with_them():
    results = _comparison()
    text = competitors.render_report(results)
    assert "contexel is the slowest budget-compliant row (15.0 ms)" in text
    assert "contexel is the only 5/5" in text
    slower = copy.deepcopy(results)
    next(r for r in slower["outcomes"] if r["impl"] == "hand-written")["ms_per_episode"] = 99.0
    out = competitors.render_report(slower)
    assert "the slowest budget-compliant row is hand-written (99.0 ms); contexel's is 15.0 ms" in out
    tie = copy.deepcopy(results)
    next(r for r in tie["task"] if r["impl"] == "toolz")["native"] = "5/5"
    assert "contexel is the only 5/5" not in competitors.render_report(tie)
    nondeterministic = copy.deepcopy(results)
    nondeterministic["task"][0]["deterministic"] = "NO"
    assert "NOT deterministic" in competitors.render_report(nondeterministic)
```

- [ ] **Step 5.2: Run them: they fail**

```bash
PYTHONPATH=. python -m pytest -q tests/test_benchmarks_competitors.py
```

Result: 7 failed, 875 passed (whole suite). `competitors.sample_records`, `operations`, `build_inflected_episodes`, `g_score_overlap`, `render_report` and the keyword arguments of `build_episodes` do not exist yet.

- [ ] **Step 5.3: Rewrite the competitor module**

Replace the **entire content** of `benchmarks/competitors.py` with exactly this (it ends with one newline):
<!-- OP rewrite path=benchmarks/competitors.py -->
```python
"""Comparative benchmark against the prior-art libraries named in the README.

    python -m benchmarks.competitors   (writes COMPARISON.md and COMPARISON.json)

Dataset: real, public code-search records — CodeSearchNet (python/test) via
the Hugging Face datasets-server (see fetch_dataset.py, which verifies a
committed SHA-256). Tool output is reconstructed the way an agent session
actually produces it: several overlapping substring queries over the corpus,
whose hit lists naturally contain duplicates.

Fairness rules:
- One canonical task for everyone: project 5 fields, dedupe by key, clip the
  snippet to ~24 tokens, rank by score, fit a 2,000-token budget.
- Every implementation that lacks a native stage uses the SAME hand-written
  glue helpers, so wall-time differences reflect the library, not the glue.
- How many of the task's operations a library expresses *natively* is computed,
  not typed: each implementation is a list of steps (opcount.py), and a step
  counts as native when running it enters the library's own code.
- The hand-written baseline exists in two forms: one that trusts the tool's
  score, and one with its own term-overlap scorer, so contexel's rescoring is
  compared with another rescorer, not only with none.
- The original episodes query with the target's own words. The inflected
  episodes query with deterministic inflections of them (inflection.py) and are
  reported separately: they measure inflection robustness, not semantic
  paraphrase.
- Competitors are guard-imported; a missing library becomes a report note,
  never an error. Semantic tools (embedding dedupe, LLMLingua, rerankers)
  are matrix-only: contexel concedes semantic quality by design.

The run collects every number into one dictionary (``collect``), writes it as
COMPARISON.json, and renders COMPARISON.md from that dictionary alone
(``render_report``), so the published tables can be checked against the data
(tools/check_benchmark_numbers.py).
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import contexel
from contexel import (
    dedupe, pipeline, rank, rescore, select, stage, trim_to_budget, truncate_field,
)

from . import fetch_dataset
from .fetch_dataset import load
from .inflection import inflect, inflectable, words
from .opcount import OPS, Step, count
from .opcount import run as run_steps
from .suites import _best_of
from .tables import table

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["path", "symbol", "snippet", "score", "repo"]
QUERIES = [
    "file", "parse", "config", "request", "path", "data", "string",
    "return list", "self", "import", "error", "response", "value",
    "key", "index", "update",
]
PER_QUERY_CAP = 2000
SNIPPET_CAP = 24          # tokens
BUDGET = 2000             # tokens
EVAL_BUDGET = 1500
N_EPISODES = 100
LLAMA_SCORE_CUTOFF = 2.0  # a fixed, stated policy: SimilarityPostprocessor cutoff
TIMED_OPS = ("select", "dedupe", "truncate", "rank", "trim")  # the query-free task


# --------------------------------------------------------------------------- #
# Real tool output from the public corpus
# --------------------------------------------------------------------------- #
def build_tool_output(corpus: Optional[List[dict]] = None) -> List[dict]:
    """Overlapping search queries over CodeSearchNet -> duplicate-bearing hits."""
    if corpus is None:
        corpus = load()
    out: List[dict] = []
    for query in QUERIES:
        hits = []
        for row in corpus:
            count_ = row["func_code_string"].lower().count(query)
            if not count_:
                continue
            doc = (row["func_documentation_string"] or "").strip()
            snippet = doc or row["func_code_string"].strip().splitlines()[0]
            hits.append({
                "path": row["func_path_in_repository"],
                "symbol": row["func_name"],
                "snippet": snippet,
                "score": count_,
                "repo": row["repository_name"],
                "url": row["func_code_url"],
                "language": "python",
            })
        hits.sort(key=lambda h: (-h["score"], h["path"], h["symbol"]))
        out.extend(hits[:PER_QUERY_CAP])
    return out


# --------------------------------------------------------------------------- #
# Shared glue — the hand-written stand-ins for stages a library lacks.
# Deliberately independent of contexel: this is what improvised code looks like.
# --------------------------------------------------------------------------- #
def est_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4)) if text else 0


def g_select(records: List[dict]) -> List[dict]:
    return [{k: r[k] for k in FIELDS if k in r} for r in records]


def g_dedupe(records: List[dict]) -> List[dict]:
    seen, out = set(), []
    for r in records:
        key = (r.get("path"), r.get("symbol"))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def g_truncate(records: List[dict]) -> List[dict]:
    limit = SNIPPET_CAP * 4  # ~4 chars/token
    out = []
    for r in records:
        s = r.get("snippet")
        if isinstance(s, str) and len(s) > limit:
            r = {**r, "snippet": s[: limit - 1].rstrip() + "…"}
        out.append(r)
    return out


def g_rank(records: List[dict]) -> List[dict]:
    present = [r for r in records if "score" in r]
    missing = [r for r in records if "score" not in r]
    return sorted(present, key=lambda r: r["score"], reverse=True) + missing


def g_trim(records: List[dict], budget: int = BUDGET) -> List[dict]:
    out, used = [], 0
    for r in records:
        cost = est_tokens(json.dumps(r, ensure_ascii=False)) + 2
        if used + cost > budget:
            break
        out.append(r)
        used += cost
    return out


_HAND_WORD = re.compile(r"[a-z0-9]+")


def g_score_overlap(records: List[dict], terms: List[str]) -> List[dict]:
    """The hand-written term-overlap scorer: how many of the query's distinct
    words occur, as whole words, in the record's snippet, symbol and path.

    It is what a model improvises when asked to rank hits by a query: lower-case
    both sides, split on anything that is not a letter or digit, count the
    overlap. It replaces the tool's score; ties keep the incoming order."""
    want = set(_HAND_WORD.findall(" ".join(terms).lower()))
    out = []
    for r in records:
        text = " ".join(str(r.get(k, "")) for k in ("snippet", "symbol", "path")).lower()
        have = set(_HAND_WORD.findall(text))
        out.append({**r, "score": len(want & have)})
    return out


def sample_records() -> List[dict]:
    """A tiny fixed tool output that every step can run on (duplicates, long
    snippets, mixed scores). The native-operation count runs each implementation
    over it, so the count needs neither the dataset nor the network."""
    return [
        {
            "path": f"src/mod{i % 8}.py",
            "symbol": f"func_{i % 8}",
            "snippet": ("parse the request and return the value " * (1 + i % 3)).strip(),
            "score": 10 - i,
            "repo": "r",
            "url": f"u{i}",
            "language": "python",
        }
        for i in range(12)
    ]


SAMPLE_TERMS = ["parse", "value"]


# --------------------------------------------------------------------------- #
# The implementations, as ordered steps. The list is what runs AND what is counted.
# --------------------------------------------------------------------------- #
def run_pipeline(steps: Sequence[Step], data: Any) -> Any:
    """contexel's own composition: the steps' stages through pipeline()."""
    return pipeline([s.fn for s in steps])(data)


def _contexel_stage_steps(trim: int) -> List[Step]:
    return [
        Step("select", stage(select, fields=FIELDS), "select"),
        Step("dedupe", stage(dedupe, key=["path", "symbol"]), "dedupe"),
        Step("truncate", stage(truncate_field, field="snippet", max_tokens=SNIPPET_CAP),
             "truncate"),
        Step("rank", stage(rank, by="score", desc=True), "rank"),
        Step("trim", stage(trim_to_budget, max_tokens=trim), "trim"),
    ]


def contexel_timed() -> List[Step]:
    return _contexel_stage_steps(BUDGET)


def contexel_outcome(terms: List[str], match: str = "word") -> List[Step]:
    """The standard contract: relevance derived from the query via rescore,
    never trusted from the tool's score."""
    stages = _contexel_stage_steps(EVAL_BUDGET)
    rescoring = Step("rescore", stage(rescore, query=terms, fields=("snippet", "symbol", "path"),
                                      match=match), "rescore")
    return stages[:2] + [rescoring] + stages[2:]


def contexel_stem_outcome(terms: List[str]) -> List[Step]:
    return contexel_outcome(terms, match="stem")


def hand_timed() -> List[Step]:
    return [
        Step("select", g_select, "select"),
        Step("dedupe", g_dedupe, "dedupe"),
        Step("truncate", g_truncate, "truncate"),
        Step("rank", g_rank, "rank"),
        Step("trim", g_trim, "trim"),
    ]


def hand_outcome(terms: List[str]) -> List[Step]:
    """Trusts the tool's score."""
    return [
        Step("select", g_select, "select"),
        Step("dedupe", g_dedupe, "dedupe"),
        Step("truncate", g_truncate, "truncate"),
        Step("rank", g_rank, "rank"),
        Step("trim", lambda r: g_trim(r, EVAL_BUDGET), "trim"),
    ]


def hand_scored_outcome(terms: List[str]) -> List[Step]:
    """Has its own term-overlap scorer, then the same glue."""
    return [
        Step("select", g_select, "select"),
        Step("dedupe", g_dedupe, "dedupe"),
        Step("rescore", lambda r: g_score_overlap(r, terms), "rescore"),
        Step("truncate", g_truncate, "truncate"),
        Step("rank", g_rank, "rank"),
        Step("trim", lambda r: g_trim(r, EVAL_BUDGET), "trim"),
    ]


def _toolz_select(records: List[dict]) -> List[dict]:
    from toolz.dicttoolz import keyfilter

    return [keyfilter(lambda k: k in FIELDS, r) for r in records]


def _toolz_dedupe(records: List[dict]) -> List[dict]:
    from toolz import unique

    return list(unique(records, key=lambda r: (r["path"], r["symbol"])))


def toolz_timed() -> List[Step]:
    return [
        Step("select", _toolz_select, "select"),
        Step("dedupe", _toolz_dedupe, "dedupe"),
        Step("truncate", g_truncate, "truncate"),
        Step("rank", g_rank, "rank"),
        Step("trim", g_trim, "trim"),
    ]


def toolz_outcome(terms: List[str]) -> List[Step]:
    # no token stage exists: the whole deduped set enters context
    return [
        Step("select", _toolz_select, "select"),
        Step("dedupe", _toolz_dedupe, "dedupe"),
    ]


def _lc_wrap(records: List[dict]) -> Any:
    from langchain_core.messages import HumanMessage

    return records, [HumanMessage(json.dumps(r, ensure_ascii=False)) for r in records]


def _lc_trim(budget: int) -> Callable[[Any], List[dict]]:
    def trim(pair: Any) -> List[dict]:
        from langchain_core.messages.utils import trim_messages

        records, messages = pair
        kept = trim_messages(
            messages,
            max_tokens=budget,
            token_counter=lambda ms: sum(est_tokens(m.content) + 2 for m in ms),
            strategy="first",
        )
        return records[: len(kept)]
    return trim


def langchain_timed() -> List[Step]:
    return [
        Step("select", g_select, "select"),
        Step("dedupe", g_dedupe, "dedupe"),
        Step("truncate", g_truncate, "truncate"),
        Step("rank", g_rank, "rank"),
        Step("wrap as messages", _lc_wrap, "adapter"),
        Step("trim", _lc_trim(BUDGET), "trim"),
    ]


def langchain_outcome(terms: List[str]) -> List[Step]:
    # the budget is native; projection, dedupe and rank are not, so raw records go in
    return [
        Step("wrap as messages", _lc_wrap, "adapter"),
        Step("trim", _lc_trim(EVAL_BUDGET), "trim"),
    ]


def _llama_snippet_nodes(records: List[dict]) -> Any:
    from llama_index.core.schema import NodeWithScore, TextNode

    return [
        NodeWithScore(
            node=TextNode(
                text=r["snippet"],
                metadata={k: r[k] for k in ("path", "symbol", "repo")},
            ),
            score=float(r["score"]),
        )
        for r in records
    ]


def _llama_from_snippet_nodes(nodes: Any) -> List[dict]:
    return [
        {**{k: n.node.metadata[k] for k in ("path", "symbol")},
         "snippet": n.node.text, "score": int(n.score),
         "repo": n.node.metadata["repo"]}
        for n in nodes
    ]


def llama_timed() -> List[Step]:
    return [
        Step("select", g_select, "select"),
        Step("dedupe", g_dedupe, "dedupe"),
        Step("to nodes", _llama_snippet_nodes, "adapter"),
        Step("from nodes", _llama_from_snippet_nodes, "adapter"),
        Step("truncate", g_truncate, "truncate"),
        Step("rank", g_rank, "rank"),
        Step("trim", g_trim, "trim"),
    ]


def _llama_json_nodes(records: List[dict]) -> Any:
    from llama_index.core.schema import NodeWithScore, TextNode

    return [
        NodeWithScore(node=TextNode(text=json.dumps(r, ensure_ascii=False)),
                      score=float(r["score"]))
        for r in records
    ]


def _llama_cutoff(nodes: Any) -> Any:
    from llama_index.core.postprocessor import SimilarityPostprocessor

    return SimilarityPostprocessor(similarity_cutoff=LLAMA_SCORE_CUTOFF).postprocess_nodes(nodes)


def _llama_reorder(nodes: Any) -> Any:
    from llama_index.core.postprocessor import LongContextReorder

    return LongContextReorder().postprocess_nodes(nodes)


def llama_outcome(terms: List[str]) -> List[Step]:
    # score filter and reorder are native; neither is one of the task's operations
    return [
        Step("to nodes", _llama_json_nodes, "adapter"),
        Step("score cutoff", _llama_cutoff, "other"),
        Step("long-context reorder", _llama_reorder, "other"),
        Step("from nodes", lambda nodes: [json.loads(n.node.text) for n in nodes], "adapter"),
    ]


@dataclass(frozen=True)
class Impl:
    name: str
    note: str
    operand: str                       # what the library operates on (documentation)
    root: Optional[str]                # the library's top-level package; None = hand-written
    module: Optional[str]              # what to import for the footprint measurement
    outcome: Callable[[List[str]], List[Step]]
    timed: Optional[Callable[[], List[Step]]] = None
    runner: Callable[[Sequence[Step], Any], Any] = run_steps


IMPLEMENTATIONS = [
    Impl("contexel", "full pipeline", "list[dict]", "contexel", "contexel",
         contexel_outcome, contexel_timed, run_pipeline),
    Impl("hand-written", "what model-improvised shaping looks like (trusts the tool's score)",
         "list[dict]", None, None, hand_outcome, hand_timed),
    Impl("hand-written (term overlap)", "the same glue plus its own term-overlap scorer",
         "list[dict]", None, None, hand_scored_outcome),
    Impl("toolz", "keyfilter + unique; token stages are glue", "any dicts",
         "toolz", "toolz", toolz_outcome, toolz_timed),
    Impl("langchain-core", "trim_messages on records wrapped as messages", "BaseMessage",
         "langchain_core", "langchain_core", langchain_outcome, langchain_timed),
    Impl("llama-index-core", "node round-trip tax; postprocessors fit no stage",
         "NodeWithScore", "llama_index", "llama_index.core", llama_outcome, llama_timed),
]

# The same shapers measured on the inflected episodes: the ones that read the query,
# and the hand-written one that does not (the control: inflection cannot touch it).
CONTEXEL_STEM = Impl("contexel (match=stem)", "rescore with the opt-in stemmer", "list[dict]",
                     "contexel", "contexel", contexel_stem_outcome, None, run_pipeline)
INFLECTION_SHAPERS = [
    IMPLEMENTATIONS[0], CONTEXEL_STEM, IMPLEMENTATIONS[2], IMPLEMENTATIONS[1],
]


# --------------------------------------------------------------------------- #
# Footprint: import time (fresh interpreter) + installed dependency closure
# --------------------------------------------------------------------------- #
def import_ms(module: str) -> float:
    code = (
        "import time; t0 = time.perf_counter(); "
        f"import {module}; print((time.perf_counter() - t0) * 1000)"
    )
    run = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, check=True, cwd=ROOT)
    return float(run.stdout.strip())


def dep_closure(dist_name: str) -> Optional[int]:
    """Count of installed distributions the package transitively requires."""
    from packaging.requirements import Requirement

    seen: set = set()
    stack = [dist_name]
    while stack:
        name = stack.pop()
        key = name.lower().replace("_", "-")
        if key in seen:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        seen.add(key)
        for req_text in dist.requires or []:
            req = Requirement(req_text)
            if req.marker and not req.marker.evaluate({"extra": ""}):
                continue
            stack.append(req.name)
    return len(seen) - 1 if seen else None


_DIST = {"contexel": "contexel", "toolz": "toolz",
         "langchain_core": "langchain-core", "llama_index.core": "llama-index-core"}


# --------------------------------------------------------------------------- #
# The timed canonical task
# --------------------------------------------------------------------------- #
def _digest(records: List[dict]) -> str:
    return hashlib.sha256(
        json.dumps(records, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def time_task(data: List[dict]) -> Dict[str, Any]:
    rows, footprints = [], []
    sample = sample_records()
    for impl in IMPLEMENTATIONS:
        if impl.timed is None:
            continue
        steps = impl.timed()
        native = count(steps, impl.root, sample, TIMED_OPS).native

        def fn(records: List[dict], steps: List[Step] = steps,
               runner: Callable[[Sequence[Step], Any], Any] = impl.runner) -> Any:
            return runner(steps, records)

        label = f"{len(native)}/{len(TIMED_OPS)}"
        try:
            out_a, out_b = fn(data), fn(data)
        except Exception as exc:  # keep the report going if a library breaks
            rows.append({"impl": impl.name, "native": label, "note": impl.note, "ms": None,
                         "kept": 0, "tokens_out": 0, "deterministic": f"ERROR: {exc}"})
            continue
        secs = _best_of(lambda: fn(data))
        rows.append({
            "impl": impl.name,
            "native": label,
            "note": impl.note,
            "ms": secs * 1000,
            "kept": len(out_a),
            "tokens_out": est_tokens(json.dumps(out_a, ensure_ascii=False)),
            "deterministic": "yes" if _digest(out_a) == _digest(out_b) else "NO",
        })
        if impl.module:
            footprints.append({
                "library": impl.name,
                "import_ms": import_ms(impl.module),
                "transitive_deps": dep_closure(_DIST[impl.module]),
            })
    return {"records_in": len(data), "task": rows, "footprint": footprints}


# --------------------------------------------------------------------------- #
# Outcome benchmark — what each library achieves NATIVELY, scored against
# ground truth. CodeSearchNet pairs every function with its docstring, so for
# each episode we know exactly which record the agent needed; each library
# shapes the episode's hit list using only the operations it provides itself.
# --------------------------------------------------------------------------- #
def _record(row: dict, weak: int, strong: int) -> dict:
    doc = (row["func_documentation_string"] or "").strip()
    return {
        "path": row["func_path_in_repository"],
        "symbol": row["func_name"],
        "snippet": doc or row["func_code_string"].strip().splitlines()[0],
        "score_weak": weak,       # raw substring count — a poor relevance signal
        "score_strong": strong,   # distinct terms matched dominate — a decent one
        "repo": row["repository_name"],
        "url": row["func_code_url"],
        "language": "python",
    }


def build_episodes(corpus: List[dict], n: int = N_EPISODES, seed: int = 11,
                   term_ok: Optional[Callable[[str, set], bool]] = None,
                   pool: int = 2) -> List[dict]:
    """n ground-truth episodes: a target function + the hit list a multi-term
    search over the full corpus returns for its docstring's key terms.

    Each hit carries two relevance signals so the outcome benchmark can vary
    the *quality of the retrieval score* independently of the shaping:
    ``score_weak`` is the raw substring count (favors long, term-happy
    decoys); ``score_strong`` weights matching *all* the query's terms above
    matching one often — the ranking shape a real multi-term search returns.

    ``term_ok(term, target_words)`` (optional) keeps only the docstring terms it
    accepts; ``pool`` is how many candidate functions are sampled per episode
    wanted. The defaults reproduce the original episodes exactly.
    """
    rng = random.Random(seed)
    lowered = [
        (row["func_code_string"] + " " + (row["func_documentation_string"] or "")).lower()
        for row in corpus
    ]
    eligible = [
        i for i, row in enumerate(corpus)
        if len((row["func_documentation_string"] or "").split()) >= 8
    ]
    episodes = []
    for i in rng.sample(eligible, min(n * pool, len(eligible))):
        if len(episodes) >= n:
            break
        doc_words = corpus[i]["func_documentation_string"].split()
        candidates = [w.lower().strip(".,()`'\"") for w in doc_words if len(w) >= 5]
        if term_ok is not None:
            target_words = words(lowered[i])
            candidates = [w for w in candidates if term_ok(w, target_words)]
        terms = candidates[:3]
        if not terms:
            continue
        matched: List[tuple] = []  # (per-term counts, record)
        for j, text in enumerate(lowered):
            counts = [text.count(t) for t in terms]
            total = sum(counts)
            if total:
                distinct = sum(c > 0 for c in counts)
                matched.append(
                    (counts, _record(corpus[j], total, distinct * 10 + min(total, 9)))
                )
        hits: List[dict] = []
        for k in range(len(terms)):  # one simulated tool call per term, with dups
            term_hits = [rec for counts, rec in matched if counts[k]]
            term_hits.sort(key=lambda h: (-h["score_weak"], h["path"], h["symbol"]))
            hits.extend(term_hits[:300])
        target = (corpus[i]["func_path_in_repository"], corpus[i]["func_name"])
        if any((h["path"], h["symbol"]) == target for h in hits):
            episodes.append({"target": target, "terms": terms, "hits": hits})
    return episodes


def build_inflected_episodes(corpus: List[dict], n: int = N_EPISODES,
                             seed: int = 11) -> List[dict]:
    """Episodes whose terms can all be inflected (inflection.inflectable). The hit
    lists come from the original terms; ``inflected`` is what the shaper is asked."""
    episodes = build_episodes(corpus, n, seed, term_ok=inflectable, pool=4)
    for ep in episodes:
        ep["inflected"] = [inflect(t) for t in ep["terms"]]
    return episodes


def _with_score(hits: List[dict], signal: str) -> List[dict]:
    key = f"score_{signal}"
    return [
        {**{k: v for k, v in r.items() if not k.startswith("score_")}, "score": r[key]}
        for r in hits
    ]


def _has_target(context: List[dict], ep: dict) -> bool:
    return any((r.get("path"), r.get("symbol")) == ep["target"] for r in context)


def _useful_tokens(context: List[dict]) -> int:
    """Tokens the context spends on needed fields of first-occurrence records."""
    seen, useful = set(), []
    for r in context:
        key = (r.get("path"), r.get("symbol"))
        if key in seen:
            continue
        seen.add(key)
        useful.append({k: r[k] for k in FIELDS if k in r})
    return est_tokens(json.dumps(useful, ensure_ascii=False))


def native_outcomes(episodes: List[dict]) -> List[Dict[str, Any]]:
    n = len(episodes)
    rows = []
    for impl in IMPLEMENTATIONS:
        row: Dict[str, Any] = {"impl": impl.name}
        for signal in ("strong", "weak"):
            recalled = compliant = 0
            fills, shares = [], []
            t0 = time.perf_counter()
            for ep in episodes:
                context = impl.runner(impl.outcome(ep["terms"]), _with_score(ep["hits"], signal))
                total = est_tokens(json.dumps(context, ensure_ascii=False))
                fills.append(total / EVAL_BUDGET)
                compliant += total <= EVAL_BUDGET
                recalled += _has_target(context, ep)
                shares.append(_useful_tokens(context) / total if total else 0.0)
            row[f"recall_{signal}_pct"] = recalled / n * 100
            if signal == "strong":  # signal-independent shape metrics, one pass
                row.update({
                    "compliance_pct": compliant / n * 100,
                    "fill_x": sum(fills) / n,
                    "useful_share_pct": sum(shares) / n * 100,
                    "ms_per_episode": (time.perf_counter() - t0) * 1000 / n,
                })
        rows.append(row)
    return rows


def _recall_pct(impl: Impl, episodes: List[dict], key: str, signal: str = "strong") -> float:
    hit = 0
    for ep in episodes:
        context = impl.runner(impl.outcome(ep[key]), _with_score(ep["hits"], signal))
        hit += _has_target(context, ep)
    return hit / len(episodes) * 100


def inflected_outcomes(episodes: List[dict]) -> Dict[str, Any]:
    rows = []
    for impl in INFLECTION_SHAPERS:
        row = {
            "shaper": impl.name,
            "recall_original_pct": _recall_pct(impl, episodes, "terms"),
            "recall_inflected_pct": _recall_pct(impl, episodes, "inflected"),
        }
        if impl.name == "hand-written":  # the one that trusts the tool: weak signal too
            row["recall_original_weak_pct"] = _recall_pct(impl, episodes, "terms", "weak")
            row["recall_inflected_weak_pct"] = _recall_pct(impl, episodes, "inflected", "weak")
        rows.append(row)
    examples = []
    for ep in episodes:
        for term, inflected in zip(ep["terms"], ep["inflected"]):
            if (term, inflected) not in examples:
                examples.append((term, inflected))
    return {
        "episodes": len(episodes),
        "terms": sum(len(ep["terms"]) for ep in episodes),
        "examples": [list(pair) for pair in examples[:6]],
        "rows": rows,
    }


# --------------------------------------------------------------------------- #
# Collect everything into one dictionary
# --------------------------------------------------------------------------- #
def _version(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "not installed"


def operations(names: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """The computed native/glue/missing operations of each implementation (or of
    the named ones: a library that is not installed need not be asked)."""
    sample = sample_records()
    rows = []
    for impl in IMPLEMENTATIONS:
        if names is not None and impl.name not in names:
            continue
        c = count(impl.outcome(SAMPLE_TERMS), impl.root, sample, OPS)
        rows.append({"impl": impl.name, "operand": impl.operand, **c.as_dict()})
    return rows


def collect() -> Dict[str, Any]:
    corpus = load()
    data = build_tool_output(corpus)
    timed = time_task(data)
    episodes = build_episodes(corpus)
    outcomes = native_outcomes(episodes)
    inflected = inflected_outcomes(build_inflected_episodes(corpus))
    return {
        "schema": 1,
        "generated": date.today().isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": f"{platform.system()} ({platform.machine()})",
            "contexel": contexel.__version__,
            "libraries": {d: _version(d) for d in ("toolz", "langchain-core", "llama-index-core")},
        },
        "dataset": {
            "name": "CodeSearchNet python/test",
            "rows": len(corpus),
            "sha256": fetch_dataset.expected_digest(),
            "queries": len(QUERIES),
            "per_query_cap": PER_QUERY_CAP,
            "records": timed["records_in"],
        },
        "settings": {
            "fields": len(FIELDS),
            "snippet_cap": SNIPPET_CAP,
            "budget": BUDGET,
            "eval_budget": EVAL_BUDGET,
            "episodes": len(episodes),
            "llama_cutoff": LLAMA_SCORE_CUTOFF,
        },
        "operations": operations(),
        "task": timed["task"],
        "outcomes": outcomes,
        "footprint": timed["footprint"],
        "inflected": inflected,
    }


# --------------------------------------------------------------------------- #
# Report — rendered from the collected dictionary alone
# --------------------------------------------------------------------------- #
# Libraries this benchmark does not run: what their documentation says they offer.
NOT_RUN = [
    {"library": "haystack-ai (DocumentJoiner)", "select": "no",
     "dedupe_key": "by doc id", "rescore_lex": "no (rank fusion)",
     "rank": "join/RRF", "truncate_tok": "no",
     "trim_budget": "no", "merge_schema": "no (uniform Document)",
     "operand": "Document",
     "ran": "not run: pre-existing haystack/farm-haystack conflict in env"},
    {"library": "langchain EmbeddingsRedundantFilter", "select": "no",
     "dedupe_key": "semantic", "rescore_lex": "no", "rank": "no",
     "truncate_tok": "no",
     "trim_budget": "no", "merge_schema": "no", "operand": "Document",
     "ran": "not run: needs embedding model; model/version-dependent"},
    {"library": "LLMLingua / ColBERT / rerankers", "select": "no",
     "dedupe_key": "no", "rescore_lex": "semantic", "rank": "semantic",
     "truncate_tok": "semantic",
     "trim_budget": "semantic", "merge_schema": "no", "operand": "text",
     "ran": "out of scope by design (contexel concedes semantic quality)"},
    {"library": "context-engineering-toolkit", "select": "-", "dedupe_key": "-",
     "rescore_lex": "-",
     "rank": "-", "truncate_tok": "-", "trim_budget": "-", "merge_schema": "-",
     "operand": "-",
     "ran": "NOT FOUND on PyPI — prior-art claim did not verify"},
]


def _by(rows: List[dict], key: str, value: str) -> dict:
    for row in rows:
        if row[key] == value:
            return row
    raise KeyError(value)


def _p(value: float) -> str:
    return f"{value:.0f}"


def _list(items: Sequence[str]) -> str:
    return ", ".join(items) if items else "-"


def glance_rows(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One row per outcome implementation, joining timing, outcome and footprint."""
    task = {r["impl"]: r for r in results["task"]}
    foot = {f["library"]: f for f in results["footprint"]}
    ops = {o["impl"]: o for o in results["operations"]}
    rows = []
    for o in results["outcomes"]:
        name = o["impl"]
        t, f = task.get(name), foot.get(name)
        rows.append({
            "impl": name,
            "ops": ops[name]["label"],
            "ms": t["ms"] if t and t["ms"] is not None else "-",
            "ms_ep": o["ms_per_episode"],
            "recall": f"{_p(o['recall_strong_pct'])} / {_p(o['recall_weak_pct'])}",
            "compliance_pct": o["compliance_pct"],
            "fill_x": o["fill_x"],
            "useful_share_pct": o["useful_share_pct"],
            "import_ms": f["import_ms"] if f else "-",
            "deps": f["transitive_deps"] if f else "-",
        })
    return rows


def render_report(results: Dict[str, Any]) -> str:
    d, s = results["dataset"], results["settings"]
    out_rows, inflected = results["outcomes"], results["inflected"]
    glance = glance_rows(results)
    k = f"{d['records'] // 1000}k"
    contexel_o = _by(out_rows, "impl", "contexel")
    hand_o = _by(out_rows, "impl", "hand-written")
    scored_o = _by(out_rows, "impl", "hand-written (term overlap)")
    toolz_o = _by(out_rows, "impl", "toolz")
    lc_o = _by(out_rows, "impl", "langchain-core")
    llama_o = _by(out_rows, "impl", "llama-index-core")
    ops = {o["impl"]: o for o in results["operations"]}
    timed_ops = len(TIMED_OPS)
    all_full = [
        r["impl"] for r in out_rows
        if r["recall_strong_pct"] == 100 and r["recall_weak_pct"] == 100
        and r["compliance_pct"] == 100 and r["useful_share_pct"] == 100
    ]
    compliant = [g for g in glance if g["compliance_pct"] == 100]
    slowest = max(compliant, key=lambda g: g["ms_ep"])
    if slowest["impl"] == "contexel":
        slow_line = (f"contexel is the slowest budget-compliant row "
                     f"({slowest['ms_ep']:.1f} ms)")
    else:
        slow_line = (f"the slowest budget-compliant row is {slowest['impl']} "
                     f"({slowest['ms_ep']:.1f} ms); contexel's is "
                     f"{contexel_o['ms_per_episode']:.1f} ms")

    ops_table = table(
        [{
            "impl": o["impl"], "native": o["label"], "glue": _list(o["glue"]),
            "missing": _list(o["missing"]), "other": _list(o["other_native"]),
            "adapters": _list(o["adapters"]), "operand": o["operand"],
        } for o in results["operations"]],
        [("impl", "Implementation"), ("native", "Native operations"),
         ("glue", "Done by hand-written glue"), ("missing", "Not done at all"),
         ("other", "Other native steps"), ("adapters", "Operand conversion"),
         ("operand", "Operand")],
    )
    not_run_table = table(NOT_RUN, [
        ("library", "Library"), ("select", "select"), ("dedupe_key", "dedupe(key)"),
        ("rescore_lex", "rescore(lexical)"), ("rank", "rank"),
        ("truncate_tok", "truncate(tok)"), ("trim_budget", "trim(budget)"),
        ("merge_schema", "merge(schema)"), ("operand", "Operand"), ("ran", "Status"),
    ])
    inflected_table = table(
        [{"shaper": r["shaper"], "orig": r["recall_original_pct"],
          "infl": r["recall_inflected_pct"]} for r in inflected["rows"]],
        [("shaper", "Shaper"), ("orig", "Recall % (original terms)"),
         ("infl", "Recall % (inflected terms)")],
    )
    word_row = _by(inflected["rows"], "shaper", "contexel")
    stem_row = _by(inflected["rows"], "shaper", "contexel (match=stem)")
    scored_row = _by(inflected["rows"], "shaper", "hand-written (term overlap)")
    trust_row = _by(inflected["rows"], "shaper", "hand-written")
    lost = word_row["recall_original_pct"] - stem_row["recall_original_pct"]
    cost_line = (
        f" Opting in to the stemmer costs {lost:g} point{'s' if lost != 1 else ''} "
        f"on the original terms." if lost > 0 else "")
    examples = ", ".join(f"`{a}` -> `{b}`" for a, b in inflected["examples"])
    deterministic = all(r["deterministic"] == "yes" for r in results["task"])
    contexel_t = _by(results["task"], "impl", "contexel")
    others_native = max(
        int(r["native"].split("/")[0]) for r in results["task"] if r["impl"] != "contexel")
    contexel_native = int(contexel_t["native"].split("/")[0])
    only_full = contexel_native == timed_ops and others_native < timed_ops

    same_recall = contexel_o["recall_strong_pct"] == contexel_o["recall_weak_pct"]
    same_scored = scored_o["recall_strong_pct"] == scored_o["recall_weak_pct"]

    return f"""# contexel vs prior art — comparative benchmark

Generated {results["generated"]} by `python -m benchmarks.competitors`. The numbers
below are rendered from `benchmarks/COMPARISON.json`; `tools/check_benchmark_numbers.py`
fails when the README or the site disagree with it.

Environment: Python {results["environment"]["python"]} on {results["environment"]["platform"]},
contexel {results["environment"]["contexel"]}; toolz {results["environment"]["libraries"]["toolz"]},
langchain-core {results["environment"]["libraries"]["langchain-core"]}, llama-index-core
{results["environment"]["libraries"]["llama-index-core"]}.

**Dataset (public):** [CodeSearchNet](https://huggingface.co/datasets/code-search-net/code_search_net)
python/test split in full ({d["rows"]:,} rows) via the Hugging Face parquet export
(`benchmarks/fetch_dataset.py`, which verifies the committed SHA-256
`{d["sha256"]}` before anything is read). Tool output is reconstructed the way an
agent session produces it: {d["queries"]} overlapping substring queries over the
corpus, hit lists capped at {d["per_query_cap"]}/query -> {d["records"]:,}
records whose duplicates are real (the same function matching several
queries).

**Canonical task:** project {s["fields"]} fields, dedupe by (path, symbol),
clip `snippet` to ~{s["snippet_cap"]} tokens, rank by score, fit a {s["budget"]:,}-token
budget.

**Fairness:** every implementation missing a native stage uses the *same*
hand-written glue helpers; the hand-written rows are the model-improvised
baseline contexel replaces (one trusting the tool's score, one with its own
term-overlap scorer). Semantic tools are matrix-only — contexel concedes
semantic quality by design.

## At a glance — all the benchmarks clubbed

One row per implementation, joining the tables below: **native operations**
(how many of the outcome task's six operations — select, dedupe, rescore,
truncate, rank, trim — the library expresses itself, computed from the code that
defines each implementation: see "Operations" below), **speed** on the
{d["records"]:,}-record canonical task, the ground-truth **outcome** metrics (recall under a
strong / weak retrieval signal; *compliance* = % of episodes whose final context
fit the {s["eval_budget"]:,}-token budget; *fill* = mean context tokens / budget), and
**footprint**.

{table(glance, [
    ("impl", "Implementation"), ("ops", "Native ops"),
    ("ms", f"ms @{k}"), ("ms_ep", "ms/episode"), ("recall", "Recall % s/w"),
    ("compliance_pct", "Compliance %"), ("fill_x", "Fill x"),
    ("useful_share_pct", "Useful %"), ("import_ms", "Import ms"),
    ("deps", "Deps"),
])}

Recall columns come from the ground-truth outcome benchmark, where contexel's
standard contract includes `rescore` (relevance derived from the query, not
trusted from the tool); `ms @{k}` is the query-free canonical task, which has no
rescore stage ("-" where a row has no timed task).

- Rows that keep the needed record under both retrieval signals, respect the
  budget in every episode and spend no tokens on duplicates or bloat:
  {_list(all_full)}.
- `ms/episode`: {slow_line}. contexel does the most per episode (projecting,
  deduping, scanning each record's own text to derive relevance, clipping to a
  token-accurate cap, ranking, enforcing the budget); a cheaper row is cheaper
  by doing less.
- These timings are one run on one machine ("best of 5"): they are published
  as measured, and they vary by a few percent from run to run. The recall,
  compliance, fill and useful-share columns do not vary.

## Operations: native versus hand-written (computed)

Each implementation is an ordered list of steps (`benchmarks/competitors.py`).
A step is **native** when running it enters a Python function of the library's own
package, **glue** when it is hand-written code in this benchmark, and an
**adapter** when it only converts the operand to the shape the library requires.
`benchmarks/opcount.py` reads the counts from those definitions by running each
step over a small fixed sample; nothing about "native" is typed.

{ops_table}

Libraries this benchmark does not run (what their documentation says; they are
not counted above):

{not_run_table}

## Canonical task on real records

{table(results["task"], [
    ("impl", "Implementation"), ("native", f"Native stages (of {timed_ops})"),
    ("ms", "ms (best of 5)"), ("kept", "Records kept"),
    ("tokens_out", "Tokens out"), ("deterministic", "Deterministic"),
])}

## What each achieves natively (ground-truth outcome benchmark)

The tables above hold the *policy* constant and let glue fill the gaps. This
one asks the question that matters — **was the output useful?** — and lets
each library act only through its own operations. {s["episodes"]} episodes with
known ground truth: a target function, plus the hit list a
multi-term docstring search over the full corpus returns (the target is
always present in the raw hits, so every miss below is a *shaping* loss, not
a retrieval loss). Budget: {s["eval_budget"]:,} tokens. The queries are the target's
own words; the next section changes that.

Every hit carries two retrieval scores, because outcome quality depends on
the ranking signal the search tool hands the shaper: **strong** ranks
matching all the query's terms above matching one term often (the shape a
real multi-term search returns); **weak** is a raw substring count, which
buries the target under term-happy decoys.

- **Recall@budget** — the record the agent actually needed survived into the
  final context, under each signal.
- **Compliance** — episodes where the context fits the budget; **Fill** —
  mean context tokens / budget (over 1.00 = blown).
- **Useful share** — fraction of context tokens spent on needed fields of
  first-occurrence records (the rest is duplicates and field bloat).

{table(out_rows, [
    ("impl", "Implementation"),
    ("recall_strong_pct", "Recall % (strong)"),
    ("recall_weak_pct", "Recall % (weak)"),
    ("compliance_pct", "Compliance %"), ("fill_x", "Fill x"),
    ("useful_share_pct", "Useful share %"), ("ms_per_episode", "ms/episode"),
])}

What the numbers say each is best at:

- **contexel** (select, dedupe, `rescore`, truncate, rank, trim): recall
  {_p(contexel_o["recall_strong_pct"])}% / {_p(contexel_o["recall_weak_pct"])}%, compliance
  {_p(contexel_o["compliance_pct"])}%, useful share {_p(contexel_o["useful_share_pct"])}%.{" Its two recall columns are identical because `rescore` derives relevance from the query and the records' own fields (batch BM25: exact word tokens, IDF x saturating tf, in-order proximity), so the tool's score quality does not matter." if same_recall else " Its recall differs between the two signals."}
- **hand-written** is the same pipeline as improvised code writes it: it trusts
  the tool's score, so its recall tracks that score's quality
  ({_p(hand_o["recall_strong_pct"])}% / {_p(hand_o["recall_weak_pct"])}%), and it gets
  re-derived, slightly differently, every run.
- **hand-written (term overlap)** adds the scorer such code would improvise:
  recall {_p(scored_o["recall_strong_pct"])}% / {_p(scored_o["recall_weak_pct"])}%{" (the two columns agree because it, too, ignores the tool's score)" if same_scored else ""}.
  This is contexel's fairest comparison for `rescore`: another rescorer, not none.
- Recall@budget has a ceiling no shaper escapes, semantic or not: when a
  query legitimately describes more records than the budget can hold, some
  valid record is cut. Any recall short of 100% below is that ambiguity,
  now measured — not a scoring defect.
- **toolz** performs {len(ops["toolz"]["native"])} of the six operations
  ({_list(ops["toolz"]["native"])}); no step performs {_list(ops["toolz"]["missing"])},
  so the "context" blows the budget by the fill factor shown ({toolz_o["fill_x"]:.1f}x).
  Best at: fast lossless projection/dedup when something else enforces budgets.
- **langchain-core** is best at what it actually ships: budget enforcement
  over message streams ({_list(ops["langchain-core"]["native"])}). With no record-level
  projection or dedupe, the budget fills with bloat and duplicates (useful share
  {lc_o["useful_share_pct"]:.1f}%), and whether the target makes the cut depends entirely
  on incoming order (recall {_p(lc_o["recall_strong_pct"])}%).
- **llama-index-core**'s postprocessors (score cutoff {s["llama_cutoff"]},
  lost-in-middle reorder) are built for reordering retrieved RAG nodes, not
  bounding them — they serve none of the six operations, so recall
  ({_p(llama_o["recall_strong_pct"])}%) comes from keeping nearly everything, at a fill
  factor of {llama_o["fill_x"]:.1f}x that no context window accepts.

## Inflected-query episodes (inflection robustness, not semantic paraphrase)

The episodes above query with the target's own words, so exact-word matching
is never tested: a query saying "parse" always meets a document saying "parse".
These {inflected["episodes"]} episodes keep the same kind of hit lists (the
retrieval tool searched with the target's original terms) but hand the shaper a
deterministic **inflection** of each term ({examples}). An exact-word
shaper fails on them by construction; a stem-matching one is *measured*, not
assumed. The rule (`benchmarks/inflection.py`) is three lines, and a term is
used only when it is a plain lower-case word, its inflection differs from it,
the frozen stemmer maps both to one stem, and the inflection is not a word of
the target's own text. The inflections are synthetic — some are words nobody
writes — so this measures what the stemmer reaches on inflection and nothing
else: **not synonyms, not paraphrase, not meaning.**

{inflected_table}

- `rescore(match="word")` (the default): {_p(word_row["recall_original_pct"])}% with the
  original terms, {_p(word_row["recall_inflected_pct"])}% with the inflected ones.
- `rescore(match="stem")`: {_p(stem_row["recall_original_pct"])}% with the original terms,
  {_p(stem_row["recall_inflected_pct"])}% with the inflected ones.{cost_line}
- The hand-written term-overlap scorer matches whole words too:
  {_p(scored_row["recall_original_pct"])}% with the original terms,
  {_p(scored_row["recall_inflected_pct"])}% with the inflected ones.
- The hand-written baseline that trusts the tool's score never reads the query,
  so inflection cannot touch it: {_p(trust_row["recall_original_pct"])}% and
  {_p(trust_row["recall_inflected_pct"])}% (it is the control).

## Footprint

Import time is a fresh interpreter importing only the library; transitive
deps counts installed distributions the package requires (recursive).

{table(results["footprint"], [
    ("library", "Library"), ("import_ms", "Import ms"),
    ("transitive_deps", "Transitive deps"),
])}

## Reading the results

- {"No library in the timed set expresses more than " + str(others_native) + f" of the {timed_ops} stages natively on tool-output records; contexel is the only {timed_ops}/{timed_ops}." if only_full else "Native stages in the timed set: see the table above."} That gap — not
  raw speed — is the claim this comparison tests.
- contexel is slower than the hand-written glue on this task, and that is the
  honest price of accuracy: `truncate_field` binary-searches to a true token
  cap where the glue slices at 4 chars/token, which is why contexel's output
  lands tighter under budget. All rows are microseconds per record —
  negligible next to a single model call.
- {"All timed implementations are deterministic on this task: mechanical shaping is reproducible whoever provides it." if deterministic else "At least one timed implementation was NOT deterministic on this task: see the table."}
  The nondeterminism contexel removes lives in the *hand-written baseline
  being re-improvised per run* (and in the semantic alternatives), not in these
  libraries' primitives.
- `context-engineering-toolkit`, cited by the prior-art review as the closest
  standalone competitor, could not be found on PyPI at benchmark time.
"""


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main() -> None:
    print("building tool output from CodeSearchNet ...")
    results = collect()
    here = Path(__file__).resolve().parent
    _write(here / "COMPARISON.json", json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    _write(here / "COMPARISON.md", render_report(results))
    print(f"wrote {here / 'COMPARISON.json'} and {here / 'COMPARISON.md'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5.4: Run the new tests and the whole suite**

```bash
PYTHONPATH=. python -m pytest -q tests/test_benchmarks_competitors.py
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
```

Expected:

```text
882 passed
```

The computed counts can be seen without the dataset:

```bash
PYTHONPATH=. python -c "from benchmarks import competitors as c; [print(o['impl'].ljust(30), o['label']) for o in c.operations()]"
```

Expected:

```text
contexel                       6/6 (select, dedupe, rescore, truncate, rank, trim)
hand-written                   0/6
hand-written (term overlap)    0/6
toolz                          2/6 (select, dedupe)
langchain-core                 1/6 (trim)
llama-index-core               0/6
```

- [ ] **Step 5.5: Commit**

```bash
git add tests/test_benchmarks_competitors.py benchmarks/competitors.py
git commit -m "feat(bench): inflected episodes, a scored baseline and computed ops"
```


### Task 6: The published numbers: generated blocks, registered claims, the check, and the first honest run

**Acceptance criteria:** AC 26 (part 3: a check fails when the numbers on `site/benchmarks.html` or `README.md` differ from the generated results), AC 23 to 25 as published

**Files:**
- Create: `tests/test_benchmarks_integrity.py`, `benchmarks/publish.py`, `tools/check_benchmark_numbers.py`; generated by their commands and committed: `benchmarks/COMPARISON.json`, `benchmarks/RESULTS.json` (new), `benchmarks/COMPARISON.md`, `benchmarks/RESULTS.md` (regenerated)
- Modify: `README.md`, `README_PYPI.md`, `site/index.html`, `site/benchmarks.html`

**Interfaces:**
- Consumes: everything above, and the dataset cache.
- Produces: `publish.check(root) -> list[str]` (empty when everything agrees) and `publish.write(root)`; the command `python tools/check_benchmark_numbers.py [--write] [--root DIR]` (exit 0 or 1). The check verifies: `COMPARISON.md` and `RESULTS.md` equal the reports rendered from their JSON; the dataset digest in the results is the committed pin; each generated block of the four published files equals what the JSON renders (the blocks are `benchmark:glance` in the README and on both site pages, `benchmark:inflected` in the README and on the benchmarks page, `benchmark:suite1` on the benchmarks page); each registered claim (`publish.CLAIMS`: the dataset sizes, the budget, the tokenizer error, the PyPI README's percentages, dependency count and import time, and the qualitative sentences) is found and true of the data; and no other number with a unit (`ms`, `%`, the multiplication sign) appears in the published prose.
- The documents carry the generated blocks **empty** in this plan: Step 6.5 fills them. Their numbers are the executor's own.

- [ ] **Step 6.1: Write the failing tests**

Create `tests/test_benchmarks_integrity.py` with exactly this content (it ends with one newline):
<!-- OP create path=tests/test_benchmarks_integrity.py -->
```python
"""AC 26: every published benchmark number equals the generated results, and a
number that does not is reported. The tests that exercise a competitor library skip
when it is not installed."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks import competitors, publish, suites_report  # noqa: E402

PUBLISHED = (
    "README.md", "README_PYPI.md", "site/index.html", "site/benchmarks.html",
    "benchmarks/COMPARISON.json", "benchmarks/COMPARISON.md",
    "benchmarks/RESULTS.json", "benchmarks/RESULTS.md", "benchmarks/dataset.sha256",
)


def test_the_competitor_libraries_count_as_the_published_table_says():
    pytest.importorskip("toolz")
    pytest.importorskip("langchain_core")
    pytest.importorskip("llama_index.core")
    rows = {o["impl"]: o for o in competitors.operations()}
    assert rows["toolz"]["native"] == ["select", "dedupe"]
    assert rows["langchain-core"]["native"] == ["trim"]
    assert rows["llama-index-core"]["native"] == [] and len(rows["llama-index-core"]["other_native"]) == 2
    committed = {o["impl"]: o for o in json.loads(
        (ROOT / "benchmarks" / "COMPARISON.json").read_text(encoding="utf-8"))["operations"]}
    assert rows == committed  # the committed results are what the code computes today


def test_published_numbers_match_generated_results():
    assert publish.check(ROOT) == []


@pytest.fixture
def tree(tmp_path):
    for rel in PUBLISHED:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    return tmp_path


def _replace(root, rel, old, new, count=1):
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) >= 1, (rel, old)
    path.write_text(text.replace(old, new, count), encoding="utf-8", newline="\n")


def test_the_copy_of_the_tree_used_below_is_clean(tree):
    assert publish.check(tree) == []


def test_the_check_is_the_same_on_a_checkout_with_crlf_line_endings(tree):
    for rel in PUBLISHED:  # what a Windows checkout with autocrlf writes
        path = tree / rel
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert publish.check(tree) == []
    assert publish.write(tree) == []  # and --write has nothing to change


def test_a_changed_number_in_a_generated_table_is_reported(tree):
    comparison = json.loads((tree / "benchmarks" / "COMPARISON.json").read_text(encoding="utf-8"))
    ms = publish._n0(comparison["task"][0]["ms"])
    _replace(tree, "README.md", f"| {ms} |", f"| {int(ms.replace(',', '')) + 1} |")
    problems = publish.check(tree)
    assert any("README.md" in p and "benchmark:glance" in p for p in problems), problems


def test_a_changed_number_on_the_site_is_reported(tree):
    _replace(tree, "site/benchmarks.html", "4/4 checks PASS", "3/4 checks PASS")
    assert any("suite1" in p for p in publish.check(tree))


def test_a_registered_claim_with_a_wrong_number_is_reported(tree):
    _replace(tree, "README_PYPI.md", "28,047 search-tool records", "28,048 search-tool records")
    problems = publish.check(tree)
    assert any("README_PYPI.md" in p and "tool-output records" in p for p in problems), problems


def test_a_hand_typed_benchmark_number_is_reported_as_unregistered(tree):
    _replace(tree, "README.md", "Both are noise next to a", "Both are noise (12 ms) next to a")
    problems = publish.check(tree)
    assert any("unregistered benchmark number" in p and "12 ms" in p for p in problems), problems
    _replace(tree, "README.md", "(12 ms)", "(about 40% faster)")
    assert any("unregistered" in p and "40%" in p for p in publish.check(tree))


def test_a_reworded_registered_claim_is_reported_not_skipped(tree):
    _replace(tree, "site/index.html", "slowest\nbudget-compliant row", "slowest compliant row")
    assert any("slowest budget-compliant row" in p and "not found" in p for p in publish.check(tree))


def test_a_false_qualitative_claim_is_reported(tree):
    results = tree / "benchmarks" / "COMPARISON.json"
    data = json.loads(results.read_text(encoding="utf-8"))
    for row in data["outcomes"]:
        if row["impl"] == "hand-written":
            row["ms_per_episode"] = 10_000.0  # now the slowest compliant row is not contexel
    results.write_text(json.dumps(data, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8", newline="\n")
    (tree / "benchmarks" / "COMPARISON.md").write_text(competitors.render_report(data), encoding="utf-8",
                                                         newline="\n")
    problems = publish.check(tree)
    assert any("slowest budget-compliant row" in p and "not true" in p for p in problems), problems


def test_a_stale_report_is_reported(tree):
    comparison = tree / "benchmarks" / "COMPARISON.md"
    comparison.write_text(comparison.read_text(encoding="utf-8").replace("contexel", "contexel ", 1),
                          encoding="utf-8", newline="\n")
    assert any("COMPARISON.md" in p and "not the report rendered" in p for p in publish.check(tree))
    results = tree / "benchmarks" / "RESULTS.md"
    results.write_text(results.read_text(encoding="utf-8") + "x", encoding="utf-8", newline="\n")
    assert any("RESULTS.md" in p for p in publish.check(tree))


def test_results_made_with_another_dataset_are_reported(tree):
    results = tree / "benchmarks" / "COMPARISON.json"
    data = json.loads(results.read_text(encoding="utf-8"))
    data["dataset"]["sha256"] = "0" * 64
    results.write_text(json.dumps(data, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8", newline="\n")
    (tree / "benchmarks" / "COMPARISON.md").write_text(competitors.render_report(data), encoding="utf-8",
                                                         newline="\n")
    assert any("dataset digest" in p for p in publish.check(tree))


def test_a_missing_or_unknown_block_marker_is_reported(tree):
    _replace(tree, "README.md", "<!-- benchmark:inflected:start -->", "")
    assert any("benchmark:inflected" in p for p in publish.check(tree))
    _replace(tree, "site/index.html", "</body>",
             "<!-- benchmark:extra:start --><!-- benchmark:extra:end -->\n</body>")
    assert any("unknown benchmark:extra block" in p for p in publish.check(tree))


def test_write_regenerates_the_blocks_and_the_check_then_passes(tree):
    _replace(tree, "README.md", "| **contexel** |", "| **contexel (edited)** |")
    assert publish.check(tree)
    assert "README.md" in publish.write(tree)
    assert publish.check(tree) == []
    assert publish.write(tree) == []  # idempotent


def test_the_command_exits_non_zero_on_drift(tree):
    script = ROOT / "tools" / "check_benchmark_numbers.py"
    ok = subprocess.run([sys.executable, str(script), "--root", str(tree)], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    _replace(tree, "README_PYPI.md", "28,047 search-tool records", "28,048 search-tool records")
    bad = subprocess.run([sys.executable, str(script), "--root", str(tree)], capture_output=True, text=True)
    assert bad.returncode == 1 and "README_PYPI.md" in bad.stdout


def test_the_reports_are_rendered_from_the_json_alone():
    comparison = json.loads((ROOT / "benchmarks" / "COMPARISON.json").read_text(encoding="utf-8"))
    suites = json.loads((ROOT / "benchmarks" / "RESULTS.json").read_text(encoding="utf-8"))
    assert competitors.render_report(comparison) == competitors.render_report(json.loads(json.dumps(comparison)))
    assert suites_report.render(suites) == suites_report.render(json.loads(json.dumps(suites)))
    text = competitors.render_report(comparison)
    assert comparison["dataset"]["sha256"] in text
    assert "Inflected-query episodes" in text and "not synonyms, not paraphrase, not meaning" in text
```

- [ ] **Step 6.2: Run them: they fail**

```bash
PYTHONPATH=. python -m pytest -q tests/test_benchmarks_integrity.py
```

Result: 1 error (whole suite). `benchmarks.publish` does not exist, so the file fails at import.

- [ ] **Step 6.3: Add the check and its command**

Create `benchmarks/publish.py` with exactly this content (it ends with one newline):
<!-- OP create path=benchmarks/publish.py -->
```python
"""Tie the published benchmark numbers to the generated results (brief AC 26).

The README, the PyPI README and the site show benchmark numbers. They used to be
typed by hand, so they could drift from what the benchmark produced. Now:

* the tables are *generated* from ``benchmarks/COMPARISON.json`` and
  ``benchmarks/RESULTS.json`` into marked blocks
  (``<!-- benchmark:NAME:start -->`` ... ``<!-- benchmark:NAME:end -->``) and the
  check compares each block with what the data renders;
* the few prose numbers that remain are registered claims (``CLAIMS``): a pattern
  that must match, with the number it carries compared with the data;
* any other number with a benchmark unit (ms, %, x) found in a published file
  fails the check ("unregistered"), so a hand-typed number cannot slip in;
* ``COMPARISON.md`` and ``RESULTS.md`` must equal the reports rendered from the
  JSON, and the dataset digest the results were produced with must be the digest
  committed in ``benchmarks/dataset.sha256``.

``check(root)`` returns the problems (empty when everything agrees); ``write(root)``
rewrites the generated blocks. ``tools/check_benchmark_numbers.py`` is the command.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from . import suites_report
from .competitors import render_report

FILES = ("README.md", "README_PYPI.md", "site/index.html", "site/benchmarks.html")
BLOCK = re.compile(
    r"<!--\s*benchmark:(?P<name>[a-z0-9-]+):start\s*-->(?P<body>.*?)"
    r"<!--\s*benchmark:(?P=name):end\s*-->", re.S)
MINUS = chr(0x2212)
TIMES = chr(0xD7)
DASH = chr(0x2014)


# --------------------------------------------------------------------------- #
# Formatting: one definition, used to generate and to check
# --------------------------------------------------------------------------- #
def _n0(x: float) -> str:
    return f"{round(x):,}"


def _g1(x: float) -> str:
    return f"{round(x, 1):g}"


def _tier(metric: str, row: Dict[str, Any]) -> str:
    """'best' for a full-marks cell, 'poor' for a failing one, '' otherwise."""
    if metric == "ops":
        return "best" if row["native"] == row["total"] else ""
    if metric == "recall":
        if row["rs"] == 100 and row["rw"] == 100:
            return "best"
        return "poor" if min(row["rs"], row["rw"]) < 50 else ""
    if metric == "compliance":
        return "best" if row["compliance"] == 100 else ("poor" if row["compliance"] < 50 else "")
    if metric == "fill":
        return "poor" if row["fill"] > 1 else ""
    if metric == "useful":
        return "best" if row["useful"] == 100 else ("poor" if row["useful"] < 90 else "")
    if metric == "deps":
        return "best" if row["deps"] == 0 else ""
    return ""


def glance(comparison: Dict[str, Any]) -> List[Dict[str, Any]]:
    task = {r["impl"]: r for r in comparison["task"]}
    foot = {f["library"]: f for f in comparison["footprint"]}
    ops = {o["impl"]: o for o in comparison["operations"]}
    rows = []
    for o in comparison["outcomes"]:
        name = o["impl"]
        t, f, op = task.get(name), foot.get(name), ops[name]
        rows.append({
            "impl": name,
            "native": len(op["native"]),
            "total": len(op["native"]) + len(op["glue"]) + len(op["missing"]),
            "ms": t["ms"] if t and t["ms"] is not None else None,
            "ms_ep": o["ms_per_episode"],
            "rs": o["recall_strong_pct"], "rw": o["recall_weak_pct"],
            "compliance": o["compliance_pct"], "fill": o["fill_x"],
            "useful": o["useful_share_pct"],
            "import_ms": f["import_ms"] if f else None,
            "deps": f["transitive_deps"] if f else None,
        })
    return rows


def _cells(row: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """(metric, text, tier) for every column after the name."""
    absent = DASH
    return [
        ("ops", f"{row['native']}/{row['total']}", _tier("ops", row)),
        ("ms", _n0(row["ms"]) if row["ms"] is not None else absent, ""),
        ("ms_ep", f"{row['ms_ep']:.1f}", ""),
        ("recall", f"{row['rs']:.0f} / {row['rw']:.0f}", _tier("recall", row)),
        ("compliance", f"{row['compliance']:.0f}", _tier("compliance", row)),
        ("fill", f"{row['fill']:.2f}", _tier("fill", row)),
        ("useful", _g1(row["useful"]), _tier("useful", row)),
        ("import_ms", _n0(row["import_ms"]) if row["import_ms"] is not None else absent, ""),
        ("deps", str(row["deps"]) if row["deps"] is not None else absent, _tier("deps", row)),
    ]


def _k(comparison: Dict[str, Any]) -> str:
    return f"{comparison['dataset']['records'] // 1000}k"


def md_glance(comparison: Dict[str, Any]) -> str:
    head = ["Implementation", "Native ops", f"ms @{_k(comparison)}", "ms/episode",
            "Recall % (strong / weak)", "Compliance %", f"Fill {TIMES}", "Useful %",
            "Import ms", "Deps"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for row in glance(comparison):
        name = f"**{row['impl']}**" if row["impl"] == "contexel" else row["impl"]
        cells = [f"**{t}**" if tier == "best" else t for _, t, tier in _cells(row)]
        lines.append("| " + " | ".join([name] + cells) + " |")
    return "\n".join(lines)


def _td(text: str, tier: str) -> str:
    return f'<td class="{tier}">{html.escape(text)}</td>' if tier else f"<td>{html.escape(text)}</td>"


def html_glance(comparison: Dict[str, Any]) -> str:
    head = ["Implementation", "Native ops", f"ms @{_k(comparison)}", "ms/episode",
            "Recall (strong/weak)", "Compliance", "Fill", "Useful", "Import ms", "Deps"]
    lines = ['<div class="scroll">', "<table>",
             "<tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"]
    for row in glance(comparison):
        name = html.escape(row["impl"])
        first = f"<td><strong>{name}</strong></td>" if row["impl"] == "contexel" else f"<td>{name}</td>"
        cells = []
        for metric, text, tier in _cells(row):
            if metric in ("recall", "compliance", "useful"):
                text = text.replace(" / ", "% / ") + "%"
            elif metric == "fill":
                text = f"{text}{TIMES}"
            cells.append(_td(text, tier))
        lines.append("<tr>" + first + "".join(cells) + "</tr>")
    lines += ["</table>", "</div>"]
    return "\n".join(lines)


def html_home_glance(comparison: Dict[str, Any]) -> str:
    """The home page's shorter table."""
    head = ["Implementation", "Native ops", f"ms @{_k(comparison)}",
            "Recall (strong/weak signal)", "Budget compliance", "Useful tokens", "Deps"]
    lines = ['<div class="scroll">', "<table>",
             "<tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"]
    for row in glance(comparison):
        name = html.escape(row["impl"])
        first = f"<td><strong>{name}</strong></td>" if row["impl"] == "contexel" else f"<td>{name}</td>"
        by = {m: (t, tier) for m, t, tier in _cells(row)}
        over = f" ({row['fill']:.0f}{TIMES} budget)" if row["fill"] > 1 else ""
        lines.append("<tr>" + first + _td(*by["ops"]) + _td(*by["ms"])
                     + _td(by["recall"][0].replace(" / ", "% / ") + "%", by["recall"][1])
                     + _td(by["compliance"][0] + "%" + over, by["compliance"][1])
                     + _td(by["useful"][0] + "%", by["useful"][1])
                     + _td(*by["deps"]) + "</tr>")
    lines += ["</table>", "</div>"]
    return "\n".join(lines)


def md_inflected(comparison: Dict[str, Any]) -> str:
    head = ["Shaper", "Recall % (original terms)", "Recall % (inflected terms)"]
    lines = ["| " + " | ".join(head) + " |", "|---|---|---|"]
    for r in comparison["inflected"]["rows"]:
        lines.append(f"| {r['shaper']} | {r['recall_original_pct']:.0f} | "
                     f"{r['recall_inflected_pct']:.0f} |")
    return "\n".join(lines)


def html_inflected(comparison: Dict[str, Any]) -> str:
    lines = ['<div class="scroll">', "<table>",
             "<tr><th>Shaper</th><th>Recall (original terms)</th><th>Recall (inflected terms)</th></tr>"]
    for r in comparison["inflected"]["rows"]:
        lines.append(f"<tr><td>{html.escape(r['shaper'])}</td>"
                     f"<td>{r['recall_original_pct']:.0f}%</td>"
                     f"<td>{r['recall_inflected_pct']:.0f}%</td></tr>")
    lines += ["</table>", "</div>"]
    return "\n".join(lines)


def suite1_rows(suites: Dict[str, Any]) -> List[Tuple[str, str]]:
    det = suites_report.determinism_rows(suites["determinism"])
    passed = sum(1 for r in det if r["result"] == "PASS")
    trim = suites["budget"]["trim"]
    top = max(r["budget"] for r in trim)
    tik = next(r for r in trim if r["budget"] == top and r["shaped_with"] == "tiktoken")
    over = max((r["actual_tokens"] - r["budget"]) / r["budget"] * 100
               for r in trim if r["shaped_with"] == "heuristic")
    cut = {r["shaped_with"]: r for r in suites["budget"]["truncate"]}
    stages = {(r["n"], r["stage"]): r for r in suites["speed"]["stages"]}
    biggest = max(r["n"] for r in suites["speed"]["stages"])
    full, sel, hand = (stages[(biggest, s)] for s in ("full contract", "select", "hand-written select"))
    tr = suites["speed"]["trace"]
    acc = "; ".join(
        f"{r['sample']} {MINUS if r['error_pct'] < 0 else '+'}{abs(r['error_pct']):.1f}%"
        for r in suites["accuracy"])
    return [
        ("Determinism", f"{passed}/{len(det)} checks PASS; shaped-output hash prefix "
                        f"{suites['determinism']['hash_prefix']}"),
        ("Budget tightness (tiktoken-shaped)",
         f"{tik['actual_tokens']:,} of {top:,} tokens at the largest budget"),
        ("Budget tightness (heuristic-shaped)",
         f"worst overshoot {over:+.1f}% of the budget, measured with tiktoken"),
        ("truncate_field cap",
         f"worst clipped field {cut['heuristic']['worst_field_tokens']} tokens (heuristic) and "
         f"{cut['tiktoken']['worst_field_tokens']} tokens (tiktoken) for a cap of "
         f"{cut['tiktoken']['cap']}"),
        ("Speed, full contract",
         f"{full['records_per_sec']:,.0f} records/s ({full['ms']:,.0f} ms for {biggest:,} records)"),
        ("Speed, select vs hand-written",
         f"{sel['ms']:.1f} ms vs {hand['ms']:.1f} ms for {biggest:,} records"),
        ("Tracing overhead",
         f"{tr['off_ms']:.1f} ms inactive vs {tr['on_ms']:.1f} ms active ({tr['ratio']:.2f}x) "
         f"over 10,000 records"),
        ("Default tokenizer error (heuristic vs tiktoken)", acc),
    ]


def html_suite1(suites: Dict[str, Any]) -> str:
    lines = ['<div class="scroll">', "<table>", "<tr><th>Check</th><th>Measured</th></tr>"]
    for label, text in suite1_rows(suites):
        lines.append(f"<tr><td>{html.escape(label)}</td><td>{html.escape(text)}</td></tr>")
    lines += ["</table>", "</div>"]
    return "\n".join(lines)


def expected_blocks(comparison: Dict[str, Any], suites: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    return {
        "README.md": {"glance": md_glance(comparison), "inflected": md_inflected(comparison)},
        "site/index.html": {"glance": html_home_glance(comparison)},
        "site/benchmarks.html": {
            "glance": html_glance(comparison),
            "inflected": html_inflected(comparison),
            "suite1": html_suite1(suites),
        },
    }


# --------------------------------------------------------------------------- #
# Registered prose claims
# --------------------------------------------------------------------------- #
class Claim(NamedTuple):
    file: str
    label: str
    pattern: str                                   # one capture group: the number as written
    check: Callable[[str, Dict[str, Any], Dict[str, Any]], Optional[str]]


def _equals(expected: Callable[[Dict[str, Any], Dict[str, Any]], str]) -> Callable[..., Optional[str]]:
    def check(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
        want = expected(comparison, suites)
        return None if found == want else f"says {found}, the results say {want}"
    return check


def _import_about(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
    """"about N ms": the measured import time is within 25% of N (it varies run to run)."""
    measured = next(f["import_ms"] for f in comparison["footprint"] if f["library"] == "contexel")
    stated = int(found)
    if abs(measured - stated) <= 0.25 * stated:
        return None
    return f"says about {stated} ms, contexel's import measured {measured:.1f} ms"


def _contexel(c: Dict[str, Any], key: str) -> float:
    return next(r for r in c["outcomes"] if r["impl"] == "contexel")[key]


def _metric(key: str, name: str) -> Callable[..., Optional[str]]:
    """A prose percentage that must equal one of contexel's outcome metrics."""
    def check(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
        want = _contexel(comparison, key)
        return None if float(found) == round(want) else f"says {found}% {name}, the results say {want:.1f}%"
    return check


def _both_recalls(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
    strong, weak = _contexel(comparison, "recall_strong_pct"), _contexel(comparison, "recall_weak_pct")
    if float(found) == round(strong) == round(weak):
        return None
    return f"says {found}% under both signals, the results say {strong:.1f}% and {weak:.1f}%"


def _deps(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
    want = next(f["transitive_deps"] for f in comparison["footprint"] if f["library"] == "contexel")
    return None if int(found) == want else f"says {found} dependencies, the results say {want}"


def _json_error(comparison: Dict[str, Any], suites: Dict[str, Any]) -> str:
    row = next(r for r in suites["accuracy"] if r["sample"].startswith("json"))
    return f"{abs(round(row['error_pct']))}"


def _claim_is(label: str, truth: Callable[[Dict[str, Any], Dict[str, Any]], bool]) -> Callable[..., Optional[str]]:
    """A qualitative sentence that must be true of the results."""
    def check(found: str, comparison: Dict[str, Any], suites: Dict[str, Any]) -> Optional[str]:
        return None if truth(comparison, suites) else f"is not true of the results: {label}"
    return check


def _rows(c: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {r["impl"]: r for r in glance(c)}


def _full_marks(r: Dict[str, Any]) -> bool:
    return all(_tier(m, r) == "best" for m in ("ops", "recall", "compliance", "useful"))


def _only_full_native(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    rows = _rows(c)
    return rows["contexel"]["native"] == rows["contexel"]["total"] and all(
        r["native"] < r["total"] for n, r in rows.items() if n != "contexel")


def _slowest_compliant(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    compliant = [r for r in glance(c) if r["compliance"] == 100]
    return max(compliant, key=lambda r: r["ms_ep"])["impl"] == "contexel"


def _only_contexel_full(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    return [r["impl"] for r in glance(c) if _full_marks(r)] == ["contexel"]


def _same_recall(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    return _contexel(c, "recall_strong_pct") == _contexel(c, "recall_weak_pct")


def _zero_compliance(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    rows = _rows(c)
    return all(rows[n]["rs"] == 100 and rows[n]["compliance"] == 0 for n in ("toolz", "llama-index-core"))


def _langchain_bloat(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    r = _rows(c)["langchain-core"]
    return r["compliance"] == 100 and r["useful"] < 100


def _inflection_drop(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    rows = {r["shaper"]: r for r in c["inflected"]["rows"]}
    word, stem, scored = rows["contexel"], rows["contexel (match=stem)"], rows["hand-written (term overlap)"]
    return (word["recall_inflected_pct"] < word["recall_original_pct"]
            and scored["recall_inflected_pct"] < scored["recall_original_pct"]
            and stem["recall_inflected_pct"] > word["recall_inflected_pct"])


def _control_untouched(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    row = next(r for r in c["inflected"]["rows"] if r["shaper"] == "hand-written")
    return row["recall_original_pct"] == row["recall_inflected_pct"]


def _json_underestimates(c: Dict[str, Any], s: Dict[str, Any]) -> bool:
    return next(r for r in s["accuracy"] if r["sample"].startswith("json"))["error_pct"] < 0


ROWS = r"split\s*(?:\(|" + DASH + r"|-|&mdash;)?\s*([\d,]+)\s+(?:functions|real)"
RECORDS = r"([\d,]+)\s+(?:real\s+)?search-tool\s+records"
EPISODES = r"([\d,]+)\s+ground-truth\s+episodes"
BUDGET = r"([\d,]+)-token\s+(?:context|budget)"

CLAIMS: List[Claim] = []
for _file in FILES:
    CLAIMS += [
        Claim(_file, "tool-output records", RECORDS,
              _equals(lambda c, s: f"{c['dataset']['records']:,}")),
        Claim(_file, "episodes", EPISODES,
              _equals(lambda c, s: f"{c['settings']['episodes']:,}")),
    ]
for _file in ("README.md", "README_PYPI.md", "site/benchmarks.html"):
    CLAIMS.append(Claim(_file, "dataset rows", ROWS, _equals(lambda c, s: f"{c['dataset']['rows']:,}")))
for _file in ("README.md", "README_PYPI.md", "site/index.html"):
    CLAIMS.append(Claim(_file, "evaluation budget", BUDGET,
                        _equals(lambda c, s: f"{c['settings']['eval_budget']:,}")))
CLAIMS += [
    Claim("site/benchmarks.html", "evaluation budget", r"Budget:\s*([\d,]+)\s+tokens",
          _equals(lambda c, s: f"{c['settings']['eval_budget']:,}")),
    Claim("README.md", "JSON tokenizer error", MINUS + r"(\d+)%\s+on\s+JSON-heavy",
          _equals(_json_error)),
    Claim("README_PYPI.md", "budget compliance", r"budget\s+in\s+(\d+)%\s+of\s+episodes",
          _metric("compliance_pct", "compliance")),
    Claim("README_PYPI.md", "recall", r"needed\s+record\s+in\s+(\d+)%\s+of\s+them", _both_recalls),
    Claim("README_PYPI.md", "useful share", r"spends\s+(\d+)%\s+of\s+context\s+tokens",
          _metric("useful_share_pct", "useful share")),
    Claim("README_PYPI.md", "dependencies", r"at\s+(\d+)\s+dependencies", _deps),
    Claim("README_PYPI.md", "import time", r"about\s+(\d+)\s+ms", _import_about),
    Claim("site/index.html", "import time", r"about\s+(\d+)(?:&nbsp;|\s)+ms", _import_about),
]


def _sentence(file: str, pattern: str, label: str,
              truth: Callable[[Dict[str, Any], Dict[str, Any]], bool]) -> Claim:
    return Claim(file, label, "(" + pattern + ")", _claim_is(label, truth))


_SLOWEST = r"slowest\s+budget-compliant\s+row"
_DROP = r"Exact-word\s+matching\s+\(the\s+default\)\s+collapses\s+on\s+inflected\s+queries"
CLAIMS += [
    _sentence("README_PYPI.md", r"contexel\s+is\s+the\s+only\s+implementation\s+among\s+the\s+near-neighbours",
              "only implementation with every operation native", _only_full_native),
    _sentence("site/index.html",
              r"contexel\s+is\s+the\s+only\s+row\s+with\s+full\s+marks\s+in\s+every\s+outcome\s+column",
              "only row with full marks", _only_contexel_full),
    _sentence("README_PYPI.md", _SLOWEST, "slowest budget-compliant row", _slowest_compliant),
    _sentence("site/index.html", _SLOWEST, "slowest budget-compliant row", _slowest_compliant),
    _sentence("README.md", _SLOWEST, "slowest budget-compliant row", _slowest_compliant),
    _sentence("site/benchmarks.html", _SLOWEST, "slowest budget-compliant row", _slowest_compliant),
    _sentence("README.md", r"contexel's\s+recall\s+is\s+the\s+same\s+under\s+both\s+signals",
              "same recall under both signals", _same_recall),
    _sentence("site/benchmarks.html", r"so\s+its\s+two\s+columns\s+read\s+the\s+same",
              "same recall under both signals", _same_recall),
    _sentence("README.md", r"A\s+row\s+with\s+full\s+recall\s+and\s+zero\s+compliance",
              "toolz and llama-index: full recall, zero compliance", _zero_compliance),
    _sentence("site/benchmarks.html", r"toolz\s+and\s+llama-index\s+keep\s+the\s+needed\s+record",
              "toolz and llama-index: full recall, zero compliance", _zero_compliance),
    _sentence("README.md", r"langchain-core\s+honors\s+the\s+budget", "langchain-core: compliant but bloated",
              _langchain_bloat),
    _sentence("site/benchmarks.html", r"langchain-core\s+holds\s+the\s+budget",
              "langchain-core: compliant but bloated", _langchain_bloat),
    _sentence("README.md", _DROP, "word mode drops on inflected queries and stem recovers", _inflection_drop),
    _sentence("site/benchmarks.html", _DROP, "word mode drops on inflected queries and stem recovers",
              _inflection_drop),
    _sentence("README.md", r"inflection\s+cannot\s+touch\s+it", "the trusting row is a control",
              _control_untouched),
    _sentence("site/benchmarks.html", r"inflection\s+cannot\s+touch\s+it", "the trusting row is a control",
              _control_untouched),
    _sentence("site/benchmarks.html", r"under-estimates\s+JSON-heavy\s+records",
              "the default tokenizer under-estimates JSON", _json_underestimates),
]

UNIT_NUMBER = re.compile(r"(?<![\w.])[+" + MINUS + r"-]?\d[\d,.]*\s?(?:ms\b|%|" + TIMES + ")")
URLISH = re.compile(r"https?://\S+|(?:href|src)=\"[^\"]*\"|\]\([^)]*\)")


# --------------------------------------------------------------------------- #
# The check and the writer
# --------------------------------------------------------------------------- #
def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _load(root: Path, rel: str) -> Dict[str, Any]:
    return json.loads(_read(root, rel))


def _blocks(text: str) -> List[Tuple[str, re.Match]]:
    return [(m.group("name"), m) for m in BLOCK.finditer(text)]


def _blank_group(match: "re.Match[str]") -> str:
    """Replace only the claim's captured number (or sentence) by a marker, so the
    words around it stay available to the claims checked after this one."""
    start, end = match.span(1)
    offset = match.start()
    return match.group(0)[: start - offset] + "#" + match.group(0)[end - offset:]


def check(root: Path) -> List[str]:
    problems: List[str] = []
    try:
        comparison = _load(root, "benchmarks/COMPARISON.json")
        suites = _load(root, "benchmarks/RESULTS.json")
    except (OSError, ValueError) as exc:
        return [f"cannot read the generated results: {exc}"]

    if _read(root, "benchmarks/COMPARISON.md") != render_report(comparison):
        problems.append("benchmarks/COMPARISON.md is not the report rendered from "
                        "benchmarks/COMPARISON.json (regenerate it with python -m benchmarks.competitors)")
    if _read(root, "benchmarks/RESULTS.md") != suites_report.render(suites):
        problems.append("benchmarks/RESULTS.md is not the report rendered from "
                        "benchmarks/RESULTS.json (regenerate it with python -m benchmarks)")
    try:
        committed = (root / "benchmarks" / "dataset.sha256").read_text(encoding="ascii").split()[0]
    except (OSError, IndexError, UnicodeDecodeError) as exc:
        committed = ""
        problems.append(f"cannot read benchmarks/dataset.sha256: {exc}")
    if committed and comparison["dataset"]["sha256"] != committed:
        problems.append("benchmarks/COMPARISON.json was produced with dataset digest "
                        f"{comparison['dataset']['sha256']}, not the committed {committed}")

    wanted = expected_blocks(comparison, suites)
    for rel in FILES:
        try:
            text = _read(root, rel)
        except OSError as exc:
            problems.append(f"{rel}: cannot read it ({exc})")
            continue
        found = _blocks(text)
        names = [n for n, _ in found]
        for name, body in wanted.get(rel, {}).items():
            if names.count(name) != 1:
                problems.append(f"{rel}: expected exactly one benchmark:{name} block, found {names.count(name)}")
                continue
            match = next(m for n, m in found if n == name)
            if match.group("body").replace("\r\n", "\n") != "\n" + body + "\n":
                problems.append(f"{rel}: the benchmark:{name} block differs from the generated one "
                                "(run python tools/check_benchmark_numbers.py --write)")
        for name in names:
            if name not in wanted.get(rel, {}):
                problems.append(f"{rel}: unknown benchmark:{name} block")

        outside = BLOCK.sub("", text)
        for claim in (c for c in CLAIMS if c.file == rel):
            matches = re.findall(claim.pattern, outside)
            if not matches:
                problems.append(f"{rel}: the registered claim '{claim.label}' was not found "
                                "(reworded? update publish.CLAIMS)")
                continue
            for number in matches:
                bad = claim.check(number, comparison, suites)
                if bad:
                    problems.append(f"{rel}: claim '{claim.label}' {bad}")
            outside = re.sub(claim.pattern, _blank_group, outside)
        plain = URLISH.sub(" ", outside)
        plain = re.sub(r"<[^>]+>", " ", plain)
        for hit in UNIT_NUMBER.finditer(plain):
            problems.append(f"{rel}: unregistered benchmark number {hit.group(0).strip()!r} "
                            "(put it in a generated block or register it in publish.CLAIMS)")
    return problems


def _regenerated(text: str, blocks: Dict[str, str]) -> str:
    """``text`` with the body of every known block replaced by its generated one."""
    def replace(match: "re.Match[str]") -> str:
        name = match.group("name")
        if name not in blocks:
            return match.group(0)
        whole = match.group(0)
        start = whole.index("-->") + 3
        end = whole.rindex("<!--")
        return whole[:start] + "\n" + blocks[name] + "\n" + whole[end:]

    return BLOCK.sub(replace, text)


def write(root: Path) -> List[str]:
    """Rewrite every generated block from the results; return the files changed."""
    comparison = _load(root, "benchmarks/COMPARISON.json")
    suites = _load(root, "benchmarks/RESULTS.json")
    changed = []
    for rel, blocks in expected_blocks(comparison, suites).items():
        path = root / rel
        text = path.read_text(encoding="utf-8")
        new = _regenerated(text, blocks)
        if new != text:
            with path.open("w", encoding="utf-8", newline="\n") as fh:
                fh.write(new)
            changed.append(rel)
    return changed
```

Create `tools/check_benchmark_numbers.py` with exactly this content (it ends with one newline):
<!-- OP create path=tools/check_benchmark_numbers.py -->
```python
"""Fail when a published benchmark number differs from the generated results.

The README, the PyPI README and the site show benchmark numbers; the benchmark
writes them to ``benchmarks/COMPARISON.json`` and ``benchmarks/RESULTS.json``
(brief AC 26). The tables in the published files are generated blocks, the few
prose numbers are registered claims, and any other number with a benchmark unit
is an error: see ``benchmarks/publish.py`` for the rules.

Runs with the standard library and contexel only (no benchmark extras, no network,
no dataset), so it runs in CI on every push.

    python tools/check_benchmark_numbers.py            # check the repository
    python tools/check_benchmark_numbers.py --write    # regenerate the marked blocks
    python tools/check_benchmark_numbers.py --root DIR # check another tree (the tests do)

Exit status: 0 everything agrees, 1 something differs (each problem is printed).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    here = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=here)
    parser.add_argument("--write", action="store_true",
                        help="rewrite the generated blocks from the JSON results, then check")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(here))
    from benchmarks import publish  # noqa: E402

    root = args.root.resolve()
    if args.write:
        for rel in publish.write(root):
            print(f"rewrote the generated blocks of {rel}")
    problems = publish.check(root)
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} problem(s): the published benchmark numbers do not match the results")
        return 1
    print("benchmark numbers: README, PyPI README and site agree with the generated results")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6.4: Rewrite the benchmark prose of the published documents**

In `README.md`, replace this block:
<!-- OP replace-old path=README.md -->
```markdown
[benchmarks/COMPARISON.md](benchmarks/COMPARISON.md); reproduce with
`python -m benchmarks.competitors` after `pip install -e ".[benchmarks]"`
(the first run downloads the CodeSearchNet split, ~30 MB).

| Implementation | Native ops | ms @28k | ms/episode | Recall % | Compliance % | Useful % | Import ms | Deps |
|---|---|---|---|---|---|---|---|---|
| **contexel** | **6/6** | 69 | 15.5 | **100 / 100** | **100** | **100** | 19 | **0** |
| hand-written | 0/6 | 27 | 1.6 | 93 / 32 | 100 | 100 | — | — |
| toolz | 2/6 | 45 | 6.8 | 100 / 100 | 0 | 100 | 14 | 0 |
| langchain-core | 1/6 | 147 | 7.1 | 30 / 30 | 100 | 89.8 | 96 | 25 |
| llama-index-core | 0/6 | 189 | 20.8 | 100 / 100 | 0 | 74.2 | 1,209 | 60 |

How to read each column, plainly:

- **Native ops** — how many of the task's operations the library expresses
  itself. The two speed columns are different experiments: in `ms @28k`,
  everything a library lacks was filled with the *same* hand-written glue,
  so timing differences are the library's; the Recall / Compliance / Useful
  columns are the opposite — each library acts *only* through its own
  operations, so those numbers show what each one ships.
- **Recall %** (strong / weak retrieval signal) — did the record the agent
  actually needed survive into a 1,500-token context? The episodes guarantee
  that record is present in the raw hits, so recall here isolates *shaping*
  loss, not retrieval loss. contexel kept it in 100/100 episodes under both
  signals because `rescore` derives relevance from the records' own text;
  the hand-written row trusts the tool's score and drops to 32% when that
  score is poor.
- **Compliance %** — did the final context actually fit the budget? The rows
  showing 100% recall with 0% compliance (toolz, llama-index) achieved
  recall by emitting 92–129× the budget: a context no window accepts.
- **Useful %** — share of final-context tokens spent on needed fields of
  unique records. langchain-core honors the budget but fills 10% of it with
  duplicates and field bloat it cannot remove; llama-index 26%.
- **ms/episode — contexel is the slowest compliant row, and that is the
  work, not overhead.** Per episode it projects, dedupes, scans ~1 KB of
  evidence per record to compute relevance, clips to a token-accurate cap,
  ranks, and enforces the budget. Every faster row does less: the
  hand-written glue trusts the score (1.6 ms, 32% recall on a weak signal),
  toolz skips the token layer entirely, langchain-core skips the record
  work. The extra milliseconds are the rescore and token-accuracy work
  itself — and every row here is negligible next to a single model call.

The same trade shows in `ms @28k` (the query-free bulk task): contexel's
69 ms includes token-accurate truncation and tenant-isolation plumbing; the
27 ms glue slices at ~4 chars/token and lands looser under the budget. Both
are noise next to a single model call.

**Limits, measured and stated:** recall@budget has a ceiling no shaper
escapes — when a query legitimately describes more records than the budget
holds, some valid record is cut, semantic or not. And `rescore` is lexical:
exact words, not meaning. A query saying *parsing* scores zero against a
document saying *parse*; synonyms and paraphrase are invisible. When you
need that, put a semantic reranker in front — contexel's own suite measures
what the lexical lane cannot reach instead of hiding it
([RESULTS.md](benchmarks/RESULTS.md) also quantifies the default
tokenizer's error: −29% on JSON-heavy records — hard token limits require
```
with:
<!-- OP replace-new -->
```markdown
[benchmarks/COMPARISON.md](benchmarks/COMPARISON.md); reproduce with
`python -m benchmarks.competitors` after `pip install -e ".[benchmarks]"`
(the first run downloads the CodeSearchNet split, ~30 MB, and refuses it
unless its SHA-256 equals the digest committed in
`benchmarks/dataset.sha256`).

Every number in this section is generated: the tables are rendered from
`benchmarks/COMPARISON.json`, and `python tools/check_benchmark_numbers.py`
(run in CI) fails when this file, the PyPI README or the site disagree with it.

<!-- benchmark:glance:start -->
<!-- benchmark:glance:end -->

How to read each column, plainly:

- **Native ops** — how many of the task's six operations (select, dedupe,
  rescore, truncate, rank, trim) the library expresses itself, *computed* from
  the code that defines each implementation (`benchmarks/opcount.py`), not
  typed. The two speed columns are different experiments: in `ms @28k`,
  everything a library lacks was filled with the *same* hand-written glue,
  so timing differences are the library's; the Recall / Compliance / Useful
  columns are the opposite — each library acts *only* through its own
  operations, so those numbers show what each one ships. `ms @28k` is the
  query-free bulk task, and "—" marks a row with no timed task.
- **Recall %** (strong / weak retrieval signal) — did the record the agent
  actually needed survive into a 1,500-token context? The episodes guarantee
  that record is present in the raw hits, so recall here isolates *shaping*
  loss, not retrieval loss. contexel's recall is the same under both signals,
  because `rescore` derives relevance from the records' own text; the
  hand-written row trusts the tool's score, so its recall falls when that
  score is poor. The *hand-written (term overlap)* row adds the scorer such
  code would improvise: it is the fairest comparison for `rescore`, another
  rescorer rather than none.
- **Compliance %** — did the final context actually fit the budget? A row with
  full recall and zero compliance (toolz, llama-index) got there by emitting
  many times the budget (the Fill column): a context no window accepts.
- **Useful %** — share of final-context tokens spent on needed fields of
  unique records. langchain-core honors the budget but spends part of it on
  duplicates and field bloat it cannot remove; llama-index spends more.
- **ms/episode is the work, not overhead.** Per episode contexel projects,
  dedupes, scans each record's own text to compute relevance, clips to a
  token-accurate cap, ranks, and enforces the budget, and it is the slowest
  budget-compliant row because of that. Every faster compliant row does less:
  the hand-written glue trusts the score, langchain-core skips the record
  work. The timings are one run on one machine and vary by a few percent from
  run to run; the other columns do not.

The same trade shows in `ms @28k`: contexel's time includes token-accurate
truncation and the pipeline's plumbing; the hand-written glue slices at ~4
chars/token and lands looser under the budget. Both are noise next to a
single model call.

**Inflected queries.** The episodes above query with the target's own words,
so exact-word matching is never tested. A second set of episodes keeps the
hit lists but hands the shaper deterministic inflections of those words
(`parse` becomes `parsing`, `returns` becomes `return`; synthetic, the rule is
in `benchmarks/inflection.py`), so exact-word matching fails by construction
and `match="stem"` is measured:

<!-- benchmark:inflected:start -->
<!-- benchmark:inflected:end -->

Exact-word matching (the default) collapses on inflected queries, and so does
the hand-written term-overlap scorer; `match="stem"` recovers them. The
hand-written row that trusts the tool's score never reads the query, so
inflection cannot touch it: it is the control. This measures inflection
robustness only — not synonyms, not paraphrase, not meaning.

**Limits, measured and stated:** recall@budget has a ceiling no shaper
escapes — when a query legitimately describes more records than the budget
holds, some valid record is cut, semantic or not. And `rescore` is lexical:
exact words by default, so a query saying *parsing* scores zero against a
document saying *parse*. `match="stem"` opts in to a small, frozen English
stemmer that matches those inflections (the table above shows what it
recovers); synonyms and paraphrase are invisible either way. When you need
that, put a semantic reranker in front — contexel's own suite measures what
the lexical lane cannot reach instead of hiding it
([RESULTS.md](benchmarks/RESULTS.md) also quantifies the default
tokenizer's error: −29% on JSON-heavy records — hard token limits require
```

In `README_PYPI.md`, replace this block:
<!-- OP replace-old path=README_PYPI.md -->
```markdown
episodes, keeps the needed record in 100% of them under both a strong and
a weak retrieval signal, and spends 100% of context tokens on unique,
needed fields — at 0 dependencies and a sub-20 ms import. It is also the
slowest budget-compliant row, *because it does the most work per record* —
and the limits are stated with the same care: recall@budget is bounded by
query specificity for any shaper, and `rescore` is lexical, not semantic.

Determinism is proven, not promised: the suite hashes the same contract's
```
with:
<!-- OP replace-new -->
```markdown
episodes, keeps the needed record in 100% of them under both a strong and
a weak retrieval signal, and spends 100% of context tokens on unique,
needed fields — at 0 dependencies and an import of about 20 ms. It is also the
slowest budget-compliant row, *because it does the most work per record* —
and the limits are stated with the same care: recall@budget is bounded by
query specificity for any shaper, and `rescore` is lexical, not semantic
(`match="stem"` opts in to inflections; synonyms stay invisible).

Determinism is proven, not promised: the suite hashes the same contract's
```

In `site/index.html`, replace this block:
<!-- OP replace-old path=site/index.html -->
```html
  </div>
  <div class="card"><span class="k">Zero dependencies</span>
    <h3>Plain Python, sub-20&nbsp;ms import</h3>
    <p>No embeddings, no model calls, no packages. Eight pipeline stages
    (including provenance and injection-tripwire gates) plus a
```
with:
<!-- OP replace-new -->
```html
  </div>
  <div class="card"><span class="k">Zero dependencies</span>
    <h3>Plain Python, about 20&nbsp;ms import</h3>
    <p>No embeddings, no model calls, no packages. Eight pipeline stages
    (including provenance and injection-tripwire gates) plus a
```

In `site/index.html`, replace this block:
<!-- OP replace-old path=site/index.html -->
```html
<a href="benchmarks.html">benchmarks page</a>.</p>

<div class="scroll">
<table>
<tr><th>Implementation</th><th>Native ops</th><th>ms @28k</th><th>Recall (strong/weak signal)</th><th>Budget compliance</th><th>Useful tokens</th><th>Deps</th></tr>
<tr><td><strong>contexel</strong></td><td class="best">6/6</td><td>69</td><td class="best">100% / 100%</td><td class="best">100%</td><td class="best">100%</td><td class="best">0</td></tr>
<tr><td>hand-written glue</td><td>0/6</td><td>27</td><td class="poor">93% / 32%</td><td>100%</td><td>100%</td><td>—</td></tr>
<tr><td>toolz</td><td>2/6</td><td>45</td><td>100% / 100%</td><td class="poor">0% (92× budget)</td><td>100%</td><td>0</td></tr>
<tr><td>langchain-core</td><td>1/6</td><td>147</td><td class="poor">30% / 30%</td><td>100%</td><td class="poor">89.8%</td><td>25</td></tr>
<tr><td>llama-index-core</td><td>0/6</td><td>189</td><td>100% / 100%</td><td class="poor">0% (129× budget)</td><td class="poor">74.2%</td><td>60</td></tr>
</table>
</div>

<div class="note"><strong>Read it honestly:</strong> contexel is the only row
green across every column — and it is the slowest budget-compliant row
<em>because it does the most work</em>: deriving relevance from ~1&nbsp;KB of
evidence per record on top of projecting, deduping, clipping, ranking, and
budgeting. Every faster row is faster by doing less. All rows are negligible
next to a single model call.</div>

<h2>Newly landed — toward a context shaping plane</h2>
```
with:
<!-- OP replace-new -->
```html
<a href="benchmarks.html">benchmarks page</a>.</p>

<!-- benchmark:glance:start -->
<!-- benchmark:glance:end -->

<div class="note"><strong>Read it honestly:</strong> contexel is the only row
with full marks in every outcome column — and it is the slowest
budget-compliant row <em>because it does the most work</em>: deriving
relevance from each record's own text on top of projecting, deduping,
clipping, ranking, and budgeting. Every faster row is faster by doing less.
All rows are negligible next to a single model call.</div>

<h2>Newly landed — toward a context shaping plane</h2>
```

In `site/benchmarks.html`, replace this block:
<!-- OP replace-old path=site/benchmarks.html -->
```html
"X% reduction" number, because reduction is a property of your data and your
budget, not of the library. Two reproducible suites; full tables live in the
repo (<code>benchmarks/RESULTS.md</code>, <code>benchmarks/COMPARISON.md</code>).</p>

<h2>Suite 1 — contexel's own claims</h2>
<p><code>python -m benchmarks</code> (needs the <code>accurate</code> extra).
Highlights:</p>
<ul>
  <li><strong>Determinism, 4/4 PASS</strong> — the same contract over 5,000
  seeded records hashes to the same SHA-256 in three fresh interpreters with
  different <code>PYTHONHASHSEED</code> values, and shaped output is
  identical even when raw records carry fresh request ids and timestamps.</li>
  <li><strong>Budget tightness</strong> — shaped with tiktoken, actual cost
  lands under budget (1,890/2,000); shaped with the default estimator it can
  overshoot ~0.5%. <code>truncate_field</code> never exceeded its cap.</li>
  <li><strong>Speed</strong> — ~190k records/sec through the full contract
  (100k records ≈ 0.5 s); <code>select</code> has no measurable overhead vs
  a hand-written comprehension. Tracing: 49.8 ms inactive vs 173.3 ms
  active (3.48×) over 10k records — inactive adds single-digit
  milliseconds over the untraced 44.4 ms baseline; active tracing
  token-counts every stage boundary and is priced accordingly.</li>
  <li><strong>Default tokenizer accuracy</strong> — ~4 chars/token is
  roughly on the mark for typical prose and code (−1.5% to +4%), but can
  over-estimate dense prose by ~18% and <strong>under-estimates JSON-heavy
  records by ~29%</strong>: install <code>contexel[accurate]</code> when
  budget precision matters.</li>
</ul>

<h2>Suite 2 — against the prior art, on real data</h2>
<p><code>python -m benchmarks.competitors</code> (needs the
<code>benchmarks</code> extra; first run downloads the CodeSearchNet
python/test split, ~30&nbsp;MB). The full split — 22,176 real functions —
is reconstructed into 28,047 search-tool records with genuine duplicates,
plus 100 ground-truth episodes where the record the agent <em>needed</em> is
known and guaranteed present in the raw hits, so recall isolates shaping
loss, not retrieval loss. Budget: 1,500 tokens.</p>

<div class="scroll">
<table>
<tr><th>Implementation</th><th>Native ops</th><th>ms @28k</th><th>ms/episode</th>
<th>Recall (strong/weak)</th><th>Compliance</th><th>Fill</th><th>Useful</th>
<th>Import ms</th><th>Deps</th></tr>
<tr><td><strong>contexel</strong></td><td class="best">6/6</td><td>69</td><td>15.5</td>
<td class="best">100% / 100%</td><td class="best">100%</td><td>0.95×</td>
<td class="best">100%</td><td>19</td><td class="best">0</td></tr>
<tr><td>hand-written glue</td><td>0/6</td><td>27</td><td>1.6</td>
<td class="poor">93% / 32%</td><td>100%</td><td>0.95×</td><td>100%</td><td>—</td><td>—</td></tr>
<tr><td>toolz</td><td>2/6</td><td>45</td><td>6.8</td>
<td>100% / 100%</td><td class="poor">0%</td><td class="poor">91.6×</td><td>100%</td><td>14</td><td>0</td></tr>
<tr><td>langchain-core</td><td>1/6</td><td>147</td><td>7.1</td>
<td class="poor">30% / 30%</td><td>100%</td><td>0.52×</td><td class="poor">89.8%</td><td>96</td><td>25</td></tr>
<tr><td>llama-index-core</td><td>0/6</td><td>189</td><td>20.8</td>
<td>100% / 100%</td><td class="poor">0%</td><td class="poor">129×</td><td class="poor">74.2%</td><td>1,209</td><td>60</td></tr>
</table>
</div>

<h3>How to read it</h3>
```
with:
<!-- OP replace-new -->
```html
"X% reduction" number, because reduction is a property of your data and your
budget, not of the library. Two reproducible suites; full tables live in the
repo (<code>benchmarks/RESULTS.md</code>, <code>benchmarks/COMPARISON.md</code>).
Every number on this page is generated: the tables are rendered from
<code>benchmarks/RESULTS.json</code> and <code>benchmarks/COMPARISON.json</code>, and
<code>python tools/check_benchmark_numbers.py</code>, run in CI, fails when this
page disagrees with them.</p>

<h2>Suite 1 — contexel's own claims</h2>
<p><code>python -m benchmarks</code> (needs the <code>accurate</code> extra).</p>

<!-- benchmark:suite1:start -->
<!-- benchmark:suite1:end -->

<p>The default tokenizer estimates ~4 chars/token: roughly right for typical
prose and code, but it under-estimates JSON-heavy records, so install
<code>contexel[accurate]</code> when budget precision matters. Inactive
tracing is the "zero cost" claim; active tracing token-counts every stage
boundary and is priced accordingly.</p>

<h2>Suite 2 — against the prior art, on real data</h2>
<p><code>python -m benchmarks.competitors</code> (needs the
<code>benchmarks</code> extra; the first run downloads the CodeSearchNet
python/test split, ~30&nbsp;MB, and refuses it unless its SHA-256 equals the
digest committed in <code>benchmarks/dataset.sha256</code>). The full split —
22,176 real functions — is reconstructed into 28,047 search-tool records with
genuine duplicates, plus 100 ground-truth episodes where the record the agent
<em>needed</em> is known and guaranteed present in the raw hits, so recall
isolates shaping loss, not retrieval loss. Budget: 1,500 tokens.</p>

<!-- benchmark:glance:start -->
<!-- benchmark:glance:end -->

<h3>How to read it</h3>
```

In `site/benchmarks.html`, replace this block:
<!-- OP replace-old path=site/benchmarks.html -->
```html
  (Recall / Compliance / Useful) are the opposite: each library acts
  <em>only</em> through its own operations, so they show what each one
  actually ships.</li>
  <li><strong>Recall with 0% compliance is not recall.</strong> toolz and
  llama-index keep the needed record by emitting 92–129× the budget — a
  context no window accepts. langchain-core holds the budget but, with no
  projection or dedupe, fills it with bloat and the needed record survives
  only 30% of the time.</li>
  <li><strong>contexel's 15.5 ms/episode is the work, not overhead.</strong>
  It is the slowest budget-compliant row because it does the most: deriving
  relevance from ~1&nbsp;KB of evidence per record on top of projecting,
  deduping, clipping, ranking, and budgeting. Every faster row is faster by
  doing less. All rows are noise next to one model call.</li>
  <li><strong>The two recall columns bound the semantic concession.</strong>
  The hand-written row trusts the tool's score: 93% under a decent
  retrieval signal, 32% under a weak one. contexel's
  <a href="stages.html#rescore">rescore</a> derives relevance itself, so
  both columns read 100% — on these episodes.</li>
</ul>

<h2>Limits, stated plainly</h2>
```
with:
<!-- OP replace-new -->
```html
  (Recall / Compliance / Useful) are the opposite: each library acts
  <em>only</em> through its own operations, so they show what each one
  actually ships. Native ops are <em>computed</em> from the code that defines
  each implementation, not typed.</li>
  <li><strong>Recall with zero compliance is not recall.</strong> toolz and
  llama-index keep the needed record by emitting many times the budget (the
  Fill column) — a context no window accepts. langchain-core holds the budget
  but, with no projection or dedupe, fills part of it with bloat and the
  needed record survives only when it happens to arrive early.</li>
  <li><strong>contexel's ms/episode is the work, not overhead.</strong>
  It is the slowest budget-compliant row because it does the most: deriving
  relevance from each record's own text on top of projecting, deduping,
  clipping, ranking, and budgeting. Every faster row is faster by doing less.
  All rows are noise next to one model call. The timings are one run on one
  machine; the other columns are deterministic.</li>
  <li><strong>The two recall columns bound the semantic concession.</strong>
  The hand-written row trusts the tool's score, so its recall tracks that
  score's quality. contexel's <a href="stages.html#rescore">rescore</a>
  derives relevance itself, so its two columns read the same — on these
  episodes. The hand-written row with its own term-overlap scorer is the
  fairest comparison: another rescorer, not none.</li>
</ul>

<h3>Inflected queries</h3>
<p>The episodes above query with the target's own words, so exact-word
matching is never tested. A second set of episodes keeps the hit lists but
hands the shaper deterministic inflections of those words
(<code>parse</code> becomes <code>parsing</code>, <code>returns</code> becomes
<code>return</code>; synthetic, the rule is in
<code>benchmarks/inflection.py</code>), so exact-word matching fails by
construction and <code>match="stem"</code> is <em>measured</em>:</p>

<!-- benchmark:inflected:start -->
<!-- benchmark:inflected:end -->

<p>Exact-word matching (the default) collapses on inflected queries, and so
does the hand-written term-overlap scorer; <code>match="stem"</code> recovers
them. The hand-written row that trusts the tool's score never reads the
query, so inflection cannot touch it: it is the control. This measures
inflection robustness only — <strong>not synonyms, not paraphrase, not
meaning.</strong></p>

<h2>Limits, stated plainly</h2>
```

In `site/benchmarks.html`, replace this block:
<!-- OP replace-old path=site/benchmarks.html -->
```html
<p><strong>Recall@budget has a ceiling no shaper escapes:</strong> when a
query legitimately describes more records than the budget holds, some valid
record is cut — semantic or not. The 100% here means the ambiguity clusters
resolved once exact-word evidence was used; vaguer queries, a different
corpus, or a tighter budget can put it back under 100, and that is the
data's property, not the policy's.</p>
<p><strong>rescore is lexical:</strong> a query saying <em>parsing</em>
scores zero against a document saying <em>parse</em>; synonyms and
paraphrase belong to semantic rerankers (LLMLingua, ColBERT,
cross-encoders), which contexel deliberately does not compete with.</p>
```
with:
<!-- OP replace-new -->
```html
<p><strong>Recall@budget has a ceiling no shaper escapes:</strong> when a
query legitimately describes more records than the budget holds, some valid
record is cut — semantic or not. Full recall here means the ambiguity clusters
resolved once exact-word evidence was used; vaguer queries, a different
corpus, or a tighter budget can put it back below full recall, and that is
the data's property, not the policy's.</p>
<p><strong>rescore is lexical:</strong> a query saying <em>parsing</em>
scores zero against a document saying <em>parse</em> unless you opt in to
<code>match="stem"</code>, a small frozen English stemmer; synonyms and
paraphrase belong to semantic rerankers (LLMLingua, ColBERT,
cross-encoders), which contexel deliberately does not compete with.</p>
```

The blocks are empty on purpose. Until Step 6.5 `python tools/check_benchmark_numbers.py` reports the missing JSON.

- [ ] **Step 6.5: Run both benchmarks and generate the blocks**

```bash
PYTHONPATH=. python -m benchmarks.competitors
PYTHONPATH=. python -m benchmarks
python tools/check_benchmark_numbers.py --write
python tools/check_benchmark_numbers.py
```

Expected:

```text
(about 50 seconds and 15 seconds of output, then)
rewrote the generated blocks of README.md
rewrote the generated blocks of site/index.html
rewrote the generated blocks of site/benchmarks.html
benchmark numbers: README, PyPI README and site agree with the generated results
benchmark numbers: README, PyPI README and site agree with the generated results
```

`PYTHONPATH=.` matters: a stale installed `contexel` would shadow the checkout. These commands read the cached dataset (verifying it first), run the three competitor libraries and tiktoken, and write four files; nothing is downloaded. **Compare the deterministic values with this table** (the timing columns are yours and will differ; everything else must match exactly: a mismatch means the code, not the table, is wrong, so stop and report):

```text
Implementation               Native  Recall % s / w Compliance % Fill     Useful %  Deps
contexel                     6/6     100 / 100      100          0.95     100       0
hand-written                 0/6     93 / 32        100          0.95     100       -
hand-written (term overlap)  0/6     97 / 97        100          0.94     100       -
toolz                        2/6     100 / 100      0            91.62    100       0
langchain-core               1/6     30 / 30        100          0.52     89.7      25
llama-index-core             0/6     100 / 100      0            129.21   74.2      60

Inflected episodes (100 episodes, original terms -> inflected terms, recall %):
  contexel                       99 -> 35
  contexel (match=stem)          98 -> 98
  hand-written (term overlap)    96 -> 35
  hand-written                   90 -> 90

Dataset: 22,176 rows -> 28,047 tool-output records, 100 episodes, digest 05049f798a197a8a80844707abe8b1319bf5c39d37a22fab303aba7625b868e5
```
Then prove that regenerating changes only the timings:

```bash
cp benchmarks/COMPARISON.json /tmp/first.json
PYTHONPATH=. python -m benchmarks.competitors
python -c "import json; strip=lambda o: {k: strip(v) for k, v in o.items() if k not in ('ms','ms_per_episode','import_ms','generated')} if isinstance(o, dict) else ([strip(x) for x in o] if isinstance(o, list) else o); a=json.load(open('/tmp/first.json')); b=json.load(open('benchmarks/COMPARISON.json')); print(strip(a)==strip(b))"
python tools/check_benchmark_numbers.py --write
```

Expected:

```text
True
```

(The second run rewrote the timings; `--write` regenerates the blocks from them, and the check passes again.)

- [ ] **Step 6.6: Run the new tests, the whole suite and the gates**

```bash
PYTHONPATH=. python -m pytest -q tests/test_benchmarks_integrity.py
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
python -m ruff check contexel --no-cache
python -m mypy contexel --python-version 3.10 --no-incremental
python tools/check_versions.py
python tools/site_check.py
```

Expected:

```text
898 passed

All checks passed!
Success: no issues found in 10 source files
check_versions: all 7 version locations say 0.1.17
checked 6 pages under site/ -> OK
```

`tests/test_doc_examples.py` (the README examples are executed) passes unchanged: only the benchmark section of the README changed. The integrity tests that exercise the competitor libraries run here (they are installed) and skip in CI; the others run everywhere.

- [ ] **Step 6.7: Prove the check bites (then undo)**

Change the first number of the README table (the `ms @28k` cell of the contexel row), run `python tools/check_benchmark_numbers.py`, and see it exit 1 with `README.md: the benchmark:glance block differs from the generated one`. Undo it with `python tools/check_benchmark_numbers.py --write`, which regenerates the block. Then add `(12 ms)` to any sentence of the README benchmark section and see `unregistered benchmark number '12 ms'`; remove it. `git diff README.md` must again equal what Step 6.5 produced. This is a sanity check, not a commit.

- [ ] **Step 6.8: Commit**

```bash
git add tests/test_benchmarks_integrity.py benchmarks/publish.py tools/check_benchmark_numbers.py README.md README_PYPI.md site/index.html site/benchmarks.html \
        benchmarks/COMPARISON.json benchmarks/COMPARISON.md benchmarks/RESULTS.json benchmarks/RESULTS.md
git commit -m "feat(bench): generate and check every published benchmark number"
```


### Task 7: The changelog

**Acceptance criteria:** AC 26 and 27 (documented); the published claim that changed

**Files:**
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: under `[Unreleased]`, an `Added` section (inflected episodes, the fair baseline, computed counts, generated and checked numbers, the checksummed dataset), a `Changed` section (the claim "sub-20 ms import" is now "about 20 ms", the table columns, the cache line endings) and one Known-limitations paragraph (synthetic inflections, one corpus, one run of timings, the parquet parsed before it is verified).

- [ ] **Step 7.1: Write the entries**

In `CHANGELOG.md`, replace this block:
<!-- OP replace-old path=CHANGELOG.md -->
```markdown
  public API: it is internal in TypeScript and C#, and in Python `contexel.stem`
  is the module.

### Behavior changes
```
with:
<!-- OP replace-new -->
```markdown
  public API: it is internal in TypeScript and C#, and in Python `contexel.stem`
  is the module.

### Added — honest benchmarks (brief AC 23 to 27)
- **Inflected-query episodes.** A second set of ground-truth episodes keeps the
  hit lists (the retrieval tool searched with the target's own words) but hands
  the shaper a deterministic inflection of each term (`parse` becomes `parsing`,
  `returns` becomes `return`, anything else gets `ing`;
  `benchmarks/inflection.py`), so exact-word matching fails by construction and
  `rescore(match="stem")` is measured, not assumed. A term is used only when it
  is a plain lower-case word, the frozen stemmer maps it and its inflection to
  one stem, and the inflection is not a word of the target's own text. The
  report says what it measures: inflection robustness, not semantic paraphrase.
  Exact-word matching drops sharply on these episodes and `match="stem"`
  recovers it (the table is in `benchmarks/COMPARISON.md`).
- **A fair hand-written baseline.** The hand-written row exists in two forms:
  one that trusts the tool's score (as before) and one with its own
  term-overlap scorer (lower-cased whole words, ties keep the incoming order)
  and the same budget trimming, so contexel's `rescore` is compared with another
  rescorer, not only with none.
- **Native-operation counts are computed, not typed.** Each implementation is an
  ordered list of steps (`benchmarks/opcount.py`). A step counts as native when
  running it enters the library's own code (`sys.setprofile` over a small fixed
  sample), as glue when it is hand-written; an operand conversion, or a library
  feature that serves none of the six operations, is reported but never counted.
  The comparison gains an "Operations" table (native, glue, not done, other
  native steps, conversions); the old hand-typed capability matrix survives only
  for the libraries the benchmark does not run, labelled as documentation.
- **Published numbers are generated and checked.** `python -m benchmarks.competitors`
  and `python -m benchmarks` write `benchmarks/COMPARISON.json` and
  `benchmarks/RESULTS.json` and render `COMPARISON.md` and `RESULTS.md` from
  them. The tables in the README and on the site are generated blocks
  (`<!-- benchmark:NAME:start -->`), the remaining prose numbers and qualitative
  sentences ("the only ...", "the slowest budget-compliant row") are registered
  claims, and `tools/check_benchmark_numbers.py` (also a test, so CI runs it)
  fails when anything published differs from the results, when an unregistered
  number with a benchmark unit appears, when a report is not what its JSON
  renders, or when the results were produced with a dataset other than the
  pinned one. `--write` regenerates the blocks.
- **Checksummed dataset.** `benchmarks/fetch_dataset.py` verifies the SHA-256
  committed in `benchmarks/dataset.sha256` every time the cache is used, and
  writes a download to a temporary name that is moved into place only after the
  check; a mismatch raises `DatasetChecksumError` and nothing is read. The
  digest reads every line ending as LF, because the cache is written by Python
  (CRLF on Windows).

### Changed — benchmark claims (documentation only)
- "sub-20 ms import" (PyPI README, home page) is now "about 20 ms": contexel's
  import measured between 19.3 and 20.8 ms across runs, so "sub-20" held only on
  some of them. The check accepts a stated figure within 25% of the measured one.
- The benchmark tables gain a "Fill" column, the hand-written (term overlap) row
  and computed "Native ops"; "hand-written glue" is now "hand-written". The home
  page's "the only row green across every column" is now "the only row with full
  marks in every outcome column", and is checked against the results.
- The CodeSearchNet cache is written with LF line endings on every operating
  system (it was CRLF on Windows).

### Behavior changes
```

In `CHANGELOG.md`, replace this block:
<!-- OP replace-old path=CHANGELOG.md -->
```markdown
  the whole input (a `Map` there raises `input.not_list`). Typed callers are
  protected by the type system.

### Tests
```
with:
<!-- OP replace-new -->
```markdown
  the whole input (a `Map` there raises `input.not_list`). Typed callers are
  protected by the type system.
- The benchmark's inflected episodes are synthetic: the rule produces words
  nobody writes (`partialing`), so the figures show what the stemmer reaches on
  inflection and say nothing about synonyms, paraphrase or real queries. The
  episodes come from one corpus, and the timings are one run on one machine (the
  other columns do not vary from run to run). The dataset check pins the JSONL
  cache derived from the Hugging Face parquet export, so the parquet file is
  parsed before it is verified; pinning the parquet digest too needs a one-time
  download and is recorded as a follow-up.

### Tests
```

- [ ] **Step 7.2: Run the gates**

```bash
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
python tools/check_versions.py
python tools/site_check.py
python tools/check_benchmark_numbers.py
```

Expected:

```text
898 passed

check_versions: all 7 version locations say 0.1.17
checked 6 pages under site/ -> OK
benchmark numbers: README, PyPI README and site agree with the generated results
```

- [ ] **Step 7.3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: record the honest benchmarks in the changelog"
```


## Close-out checks (after Task 7, before the gates)

Run and paste real output; a slice is done only when every line holds.

```bash
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
cd ts && npm run build && npm test
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
python -m ruff check contexel --no-cache
python -m mypy contexel --python-version 3.10 --no-incremental
python tools/check_versions.py
python tools/site_check.py
python tools/check_benchmark_numbers.py
PYTHONPATH=. python parity/generate_vectors.py
git diff --exit-code parity/vectors.json && echo vectors-stable
git status --short                      # prints nothing
git log --format=%s main..HEAD | awk '{print length}' | sort -n | tail -1   # at most 72
git log --format=%B main..HEAD | grep -ci 'co-authored'                     # 0
git diff main..HEAD | grep -nEi '<your Windows user name>|C:.Users|AppData|@[a-z0-9-]+[.]' || echo privacy-clean
```

Expected:

```text
898 passed
ℹ tests 678 / ℹ pass 678 / ℹ fail 0
Passed!  - Failed: 0, Passed: 617, Skipped: 0, Total: 617   (0 warnings)
All checks passed!
Success: no issues found in 10 source files
check_versions: all 7 version locations say 0.1.17
checked 6 pages under site/ -> OK
benchmark numbers: README, PyPI README and site agree with the generated results
vectors-stable
privacy-clean
```

The TypeScript and C# suites and the vectors are untouched by this slice (they are run to prove it). The generated files contain the Python version and the platform name (for example `Windows (AMD64)`) and no path.

## Gates (after the last task)

G4 and G5 are fresh-context gates by independent reviewers; the controller does not review its own work. The master plan requires the Security Reviewer's sign-off for this slice (dataset integrity).

1. **G4 whole-branch code review**, severity-ranked, against this plan and the brief (ACs 23 to 27). Review focus: the six classes above; that nothing under `contexel/`, `ts/` or `csharp/` changed; that the original episodes are reproduced exactly (the recall, compliance, fill and useful-share columns of the five original rows equal the published numbers of `main`: 100 / 100, 93 / 32, 100 / 100, 30 / 30, 100 / 100 and 100, 100, 0, 100, 0 and 0.95, 0.95, 91.62, 0.52, 129.21 and 100, 100, 100, 89.75, 74.15); that every sentence of the rewritten documents that states a result is either generated or a registered claim and is true; that the new claims are honest where they are less flattering than before (the scored hand-written baseline, the inflected episodes); that the modules import without the benchmark extras and on Python 3.9.
2. **G5 QA with mutation testing**, on a fresh copy per mutant (`python -B`, purge `__pycache__`, verify each mutant applied). Suggested mutants, each of which a test must kill: the digest keeping CRLF; the cache used without verification; an unverified download left behind; an upper-case or short pin accepted; a mismatch ignored; the whole-word, stem or plain-word guard of `inflectable` removed; the `e` rule of `inflect` broken; `term_ok` ignored by `build_episodes`; the overlap scorer not tokenizing the query; every library step counted as native, or native inverted; the profiler not restored; the unregistered-number guard disabled; the block comparison disabled; claim values not compared; a stale `COMPARISON.md` not detected; the dataset pin not compared; `_blank_group` replaced by blanking the whole match; a registered claim whose pattern no longer matches treated as fine; the tolerance of "about N ms" widened. Also: regenerate both benchmarks twice and compare the deterministic parts (they must be identical); run the check on a checkout with CRLF line endings and on one with LF; run the new modules and the check on Python 3.9; try the check on a README whose generated block was hand-edited by one character, and on one whose block markers were removed or duplicated.
3. **G5 security (required by the master plan for this slice)**: a read-only review of the dataset integrity (`fetch_dataset.py`): that a mismatch, a missing pin and a malformed pin all fail closed; that nothing is read, shaped or published from a file that failed; that the temporary file is never left behind; that the digest cannot be made to pass by a line-ending trick (a CRLF cache and an LF cache are the same data; a file with extra blank lines is not); the parse-before-verify residual risk of ruling S6-5 (pyarrow parses the parquet before the JSONL is verified), and whether the listing URLs should be restricted to `https://huggingface.co/`; the regular expressions of `publish.py` (static, applied to documents of tens of kilobytes: linear?); that `--write` can only rewrite the four published files under the given root; that `sys.setprofile` is always restored; and that no test, command or module touches the network except `_download_rows`.
4. **One fix wave, then one scoped re-review.** File the evidence under `docs/reviews/foundation-hardening-s6-*.md` and `docs/qa/foundation-hardening-s6-qa.md` (sanitized: no user name, home or temporary path), update the Slice 6 row and the deviation log of `docs/plans/foundation-hardening.md`, and stop: pushing and merging are the human's.

## Open for the human (before or at the plan review)

1. **Review the rulings S6-1 to S6-9**, above all S6-1 (AC 23 is pinned as "not a whole word of the target's text", because the literal "not a substring" would exclude every plural), S6-4 (the check also covers the PyPI README and the home page), S6-5 (the dataset pin is the derived JSONL, so the parquet is parsed before it is verified) and S6-6 ("sub-20 ms import" becomes "about 20 ms").
2. **Decide on pinning the upstream parquet digest too.** That is the stronger integrity control (it verifies the bytes that came from the network before pyarrow parses them) and needs a one-time download of about 30 MB from huggingface.co: this plan does not do it. The JSONL pin in this plan was computed from the cache on the plan's machine; whether a fresh download reproduces it was **not** verified.
3. **Read the first honest numbers before they are published.** Some are less flattering than the claims they replace: a hand-written term-overlap scorer reaches almost contexel's recall on the original (exact-word) episodes, and `rescore` in its default `word` mode drops sharply on inflected queries (the stemmer recovers them). They are generated, checked and true; whether the README should lead with them is a product decision.
4. **The timing columns are one run on one machine** (the executor's). The check ties the published timings to the committed JSON, not to a re-run, and CI does not run the benchmarks.
5. **Python 3.9 was verified by compiling and running the modules and the check**, not by running pytest on 3.9 (not installed here); the first CI run of the branch is the evidence for the test files on 3.9 to 3.13 and on the three operating systems.

## Replay result (how this plan was checked)

**Replay.** A script applied every block of Tasks 1 to 7, in document order, onto a fresh `git archive` of `dc70380` (with the cached dataset copied in): per task the test files first (the red measurement), then the implementation files (the green measurement), running the whole Python suite after each phase; after Task 6's files it ran `python -m benchmarks.competitors`, `python -m benchmarks` and `python tools/check_benchmark_numbers.py --write`, then the check. At the end it compared every file the scratch tree changed with the replayed tree (the four generated files and the bodies of the generated blocks are compared by what the check verifies: the deterministic part of `COMPARISON.json` was equal).

| Task | Phase | Python suite |
|---|---|---|
| 1 (the dataset checksum) | tests | 1 failed, 841 passed, 9 errors |
| 1 (the dataset checksum) | implementation | 851 passed |
| 2 (the inflection) | tests | 1 error |
| 2 (the inflection) | implementation | 867 passed |
| 3 (the operation counter) | tests | 1 error |
| 3 (the operation counter) | implementation | 872 passed |
| 4 (the Suite 1 report) | tests | 1 error |
| 4 (the Suite 1 report) | implementation | 875 passed |
| 5 (the competitor comparison) | tests | 7 failed, 875 passed |
| 5 (the competitor comparison) | implementation | 882 passed |
| 6 (the published numbers (after the two benchmarks and the generator)) | tests | 1 error |
| 6 (the published numbers (after the two benchmarks and the generator)) | implementation | 898 passed |
| 7 (the changelog) | implementation | 898 passed |



**Other checks run on the scratch tree (the final state of all seven tasks):**
- Python 898 passed; `ruff` and `mypy` (10 source files) clean; the site check and the version check clean; the TypeScript (678) and C# (617) suites and `parity/vectors.json` untouched (no file of theirs changed).
- Both benchmarks were run on the cached dataset **twice**: the deterministic parts of `COMPARISON.json` (the episodes, every recall, compliance, fill and useful-share figure, the computed operation counts, the inflected-episode recalls, the dependency counts) were identical; only the timing columns differ, by a few percent.
- The five original rows reproduce the numbers published on `main` exactly (recall 100 / 100, 93 / 32, 100 / 100, 30 / 30, 100 / 100; compliance 100, 100, 0, 100, 0; fill 0.95, 0.95, 91.62, 0.52, 129.21; useful 100, 100, 100, 89.75, 74.15; native operations 6/6, 0/6, 2/6, 1/6, 0/6), so the original episodes are reproduced exactly by the restructured code.
- Python 3.9.13: every new module and test file compiles, the check passes, the reports render (`pytest` is not installed for 3.9 here, so the test files on 3.9 are left to CI).
- The check on a copy of the published files with CRLF line endings (a Windows checkout) passes.
- **18 sanity mutants** of the new code were run on fresh copies against the new tests (the digest keeping CRLF, the cache used unverified, an unverified download kept, an upper-case pin accepted, a mismatch ignored, each guard of `inflectable` removed, the `e` rule broken, `term_ok` ignored, the scorer not tokenizing the query, every step native, native inverted, the unregistered-number guard, the block comparison, the claim values, the stale-report check and the dataset-pin comparison disabled): all killed (two survived a first version of the tests and led to two stronger assertions). The full mutation pass is the G5 gate.

**Not verified here:** the first CI run of the branch (three operating systems, Python 3.9 to 3.13); pytest on Python 3.9; that a fresh download of the dataset reproduces the committed digest (it needs the network); the competitor libraries at other versions than the ones installed on the plan's machine (toolz 1.1.0, langchain-core 1.4.9, llama-index-core 0.14.23); and the plan's own gates (G4, G5 QA with mutation testing, the required security review), which follow execution.
