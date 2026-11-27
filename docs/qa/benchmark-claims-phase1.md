> Filed 2026-11-27 from the QA of the branch head 9234c25 (branch `docs/benchmark-claims-phase1`). Sanitised: no user name, home or temporary path, e-mail address or agent identifier. The report text is kept as written. The one failed criterion (the 73-character subject of commit c27218d) is left for the human to waive or to reword before pushing. D1, D2 and G2 were fixed in the final fix wave; see `docs/plans/foundation-hardening.md` and the CHANGELOG.

# QA Report: benchmark-claims-phase1 @ 9234c25

**QA Engineer** (fresh-context verifier) · **Date:** 2026-11-26
**Build under test:** `9234c25544eca9482af61619388e8ec08d0c1086` (branch `docs/benchmark-claims-phase1`), base `main` 1825844. This is a detached scratch worktree `<wt>`, clean at start and at end (`git status -sb` gives `## HEAD (no branch)` and nothing else). Python 3.12.7 was run as `PYTHONPATH=<wt> python` (`contexel.__file__` resolves into `<wt>`). Python 3.9 was also available (`py -3.9`). No network was used. Every mutation and safety probe ran on scratch copies outside `<wt>`. The main checkout was not modified (`git status --porcelain` there gives 0 lines).

## Verdict

**QA verdict: FAIL.** One acceptance-criterion item is not met: AC7 says commit subjects are at most 72 characters, and commit `c27218d` has 73. Every other criterion passes. Two Low defects in the `--write` path are not blocking. Both are pre-existing code, now also reached by the new `write_reports`. The coverage gaps found by mutation are informational: none of them is a number carrying a benchmark unit.

To turn this into a PASS, do one of these:
- reword the subject of c27218d (a history rewrite on an unpushed branch, so it is the human's call), or
- have the human waive it.

| # | Criterion | Result |
|---|---|---|
| 1 | No measurement changed | PASS |
| 2 | Generated text is a function of the committed JSON; idempotent; LF/CRLF preserved | PASS |
| 3 | Suites, ruff, mypy, versions, site_check, Python 3.9 | PASS (informational: E501 count in non-linted benchmark files 87 -> 100) |
| 4 | Checker guards published text (mutation) | PASS for every number with a benchmark unit; gaps for qualitative words, listed |
| 5 | Site integrity | PASS (only intended text changes inside `<head>` meta content and one `<script>` string) |
| 6 | Reproduction hint | PASS |
| 7 | Text hygiene | **FAIL**: one subject is 73 characters; everything else clean |
| 8 | write / write_reports safety | PASS on the letter (no traceback, no half-written file); two Low defects D1, D2 |

## Acceptance criteria verification

### AC1: No measurement changed (PASS)

```
$ git diff 1825844 HEAD -- benchmarks/COMPARISON.json benchmarks/RESULTS.json | wc -c
0
benchmarks/COMPARISON.json main=2155d0939cd85737 head=2155d0939cd85737 blob_main=1d469c6b0c465538d477f0bdfff4a38cec60c6bd blob_head=1d469c6b0c465538d477f0bdfff4a38cec60c6bd
benchmarks/RESULTS.json    main=2fdca1dae9841e3c head=2fdca1dae9841e3c blob_main=a1fe2da1d7196cf6d2a25f3ee2d8895379a4957f blob_head=a1fe2da1d7196cf6d2a25f3ee2d8895379a4957f
```
These are sha256 prefixes of `git show <rev>:<file>`. The working-tree files differ only by autocrlf: they have 324 and 341 CRLF lines, and with CR stripped their sha256 equals the blob's (`2155d093...` and `2fdca1da...`).

### AC2: Regeneration is a pure function of the JSON (PASS)

In `<wt>`:
```
$ python tools/check_benchmark_numbers.py ; echo exit=$?
benchmark numbers: README, PyPI README and site agree with the generated results
exit=0
--- write 1 / write 2: both exit=0, same message; `git status --porcelain` empty after each
```
I then made LF and CRLF copies: every tracked UTF-8 text file was converted, and `--root <copy>` was used. After that:
- `--write` #1 and #2 produced no byte change (a sha256 snapshot of every file is identical).
- A stronger probe: every generated block body (2 in README.md, 1 in site/index.html, 3 in site/benchmarks.html) was replaced by `STALE`, and COMPARISON.md and RESULTS.md were truncated. That gave 8 problems. `--write` then restored the copy to **byte-identical** files, each file keeping its own line endings:
```
=== lf    ... rewrote the generated blocks of README.md / site/index.html / site/benchmarks.html
          re-rendered benchmarks/COMPARISON.md / benchmarks/RESULTS.md from the committed results
          exit=0   lf: bytes identical to the pre-stale copy
=== crlf  ... (same)  exit=0   crlf: bytes identical to the pre-stale copy
keep (autocrlf checkout): restored bytes identical to HEAD checkout
```
The same stale-and-restore on the CRLF copy under real **Python 3.9** is also byte-identical.

### AC3: Suites and tooling (PASS)

```
$ PYTHONPATH=<wt> python -m pytest -q --ignore-glob='tests/test_doctrine_*'
1133 passed, 1 skipped in 84.68s (0:01:24)
$ python -m pytest -q -rs tests/test_benchmarks_*.py
SKIPPED [1] tests\test_benchmarks_integrity.py:536: symbolic links cannot be created here
281 passed, 1 skipped in 42.03s
$ python -m ruff check contexel          -> All checks passed!  exit=0
$ python -m mypy                         -> Success: no issues found in 10 source files
$ python tools/check_versions.py         -> check_versions: all 7 version locations say 0.1.17
$ python tools/site_check.py             -> checked 6 pages under site/ -> OK
```
The test count matches the implementers' 1133 passed, 1 skipped. The dataset cache in `<wt>/benchmarks/data` is used. The one skip is the symlink test: this Windows account cannot create symlinks (WinError 1314).

**Python 3.9.** I ran `ast.parse(..., feature_version=(3,9))` plus `compile()` with `-W error` on the 7 changed Python files (`benchmarks/publish.py`, `benchmarks/competitors.py`, `benchmarks/suites_report.py`, the three changed `tests/test_benchmarks_*.py`, `tools/check_benchmark_numbers.py`). All gave OK, and all also compile on a **real Python 3.9** interpreter.

The one-liner in the brief emits a `ResourceWarning` (its own unclosed `open()`) under `-W error`. That is an artefact of the one-liner, not of the files, so I re-ran it with a `with` block, which is clean.

A grep for 3.10+ features found nothing: `match`, `X | None`, `zip(strict=)`, `removeprefix`, `kw_only`/`slots=`, `itertools.pairwise`, `tomllib`, `ExceptionGroup`. The checker itself runs under 3.9: `py -3.9 tools/check_benchmark_numbers.py`, exit 0. pytest is not installed for 3.9, so the test files were syntax/compile-checked only on 3.9. CI has 3.9 legs.

Informational: `ruff check` on the changed non-package files reports 100 E501 against 87 E501 for main's versions of the same files. CI lints only `contexel`, so this is not a gate.

### AC4: Mutation testing (PASS for numbers; qualitative gaps listed)

Each mutant was applied to a fresh copy of `<wt>` outside the repository tree, then checked with `python <wt>/tools/check_benchmark_numbers.py --root <copy>`.

| Mutant | Change | Checker message (trimmed) | Result |
|---|---|---|---|
| M1 | README glance: contexel ms@28k 67 -> 68 | README.md: the benchmark:glance block differs from the generated one | CAUGHT |
| M2a | site/stages.html: insert "12.3 ms" | site/stages.html: unregistered benchmark number '12.3 ms' | CAUGHT |
| M2b | site/architecture.html: insert "7x" | site/architecture.html: unregistered benchmark number '7x' | CAUGHT |
| M2c | site/contract.html: insert "500 MB" | (exit 0) | SURVIVED (MB is not a benchmark unit, by design: publish.py docstring) |
| M2d | site/getting-started.html: insert "40%" | unregistered benchmark number '40%' | CAUGHT |
| M2e | site/contract.html: a title attribute "30 percent faster" | unregistered benchmark number '30 percent' | CAUGHT |
| M2f | site/stages.html: "2.5" followed by the times entity | unregistered benchmark number '2.5×' | CAUGHT |
| M2g | site/stages.html: "1", an empty b element, "2", a narrow no-break space entity, "ms" | unregistered benchmark number '2 ms' | CAUGHT |
| M3a | README.md disclosure 100 -> 99 episodes | README.md: claim 'disclosure episodes' says 99, the results say 100 | CAUGHT |
| M3b | README_PYPI.md disclosure 100 -> 99 | README_PYPI.md: claim 'disclosure episodes' says 99, the results say 100 | CAUGHT |
| M3c | site/index.html disclosure 100 -> 99 | site/index.html: claim 'disclosure episodes' says 99, the results say 100 | CAUGHT |
| M3d | site/benchmarks.html disclosure 100 -> 99 | site/benchmarks.html: claim 'disclosure episodes' says 99, the results say 100 | CAUGHT |
| M3e | COMPARISON.md disclosure 100 -> 99 | benchmarks/COMPARISON.md is not the report rendered from benchmarks/COMPARISON.json | CAUGHT |
| M4a | index.html note: "in every episode" -> "in most episodes" | the registered claim 'contexel alone: full recall under both signals, within the budget, no duplicates or bloat' was not found | CAUGHT |
| M4b | index.html note: "spends no tokens" -> "spends few tokens" | (same claim) was not found | CAUGHT |
| M4c | index.html note: "Fill at most 1.00" -> "2.00" | (same claim) was not found | CAUGHT |
| M4d | index.html note: "On it, contexel is the row" -> "On it, toolz and not contexel is the row" | (exit 0) | SURVIVED (a negation outside the registered pattern) |
| M5a | README.md two-slowest sentence: term-overlap scorer -> langchain-core | (exit 0) | SURVIVED |
| M5b | README_PYPI.md: "It and contexel are the two slowest" -> "It and toolz" | (exit 0) | SURVIVED |
| M5c | index.html: term-overlap scorer -> llama-index-core in the two-slowest sentence | (exit 0) | SURVIVED |
| M5d | benchmarks.html: "two slowest" -> "two fastest" | the registered claim 'two slowest budget-compliant rows' was not found | CAUGHT |
| M5e | README_PYPI.md: "performs all six operations" -> "all five" | the registered claim 'only row with every operation native' was not found | CAUGHT |
| M5f | README_PYPI.md: "no other compared row does" -> "one other compared row does" | (same) was not found | CAUGHT |
| M5g | README_PYPI.md: drop "toolz" from the row list after the six-ops sentence | (exit 0) | SURVIVED |
| M6a | README glance block header gains "Compliance %" | README.md: the benchmark:glance block differs from the generated one | CAUGHT |
| M6b | README prose "Compliance: 100% in every row." | README.md: unregistered benchmark number '100%' | CAUGHT |
| M6c | README: a hand table with a "Compliance" column and cell 100 outside the block | unregistered benchmark number '100' in a table cell outside a generated block | CAUGHT |
| M6d | COMPARISON.md header "Implementation (Compliance)" | benchmarks/COMPARISON.md is not the report rendered from benchmarks/COMPARISON.json | CAUGHT |
| M16 | README prose "Every row is budget compliant." (no number) | (exit 0) | SURVIVED (words are not checked) |
| M7a | COMPARISON.md one character (first "toolz" -> "toolZ") | benchmarks/COMPARISON.md is not the report rendered from benchmarks/COMPARISON.json | CAUGHT |
| M7b | RESULTS.md one character (first "e" -> "E") | benchmarks/RESULTS.md is not the report rendered from benchmarks/RESULTS.json | CAUGHT |
| M7c | COMPARISON.md: one trailing space at EOF | benchmarks/COMPARISON.md is not the report rendered ... | CAUGHT |
| M8a | site/benchmarks.html: disclosure sentence deleted | the registered claim 'disclosure episodes' was not found | CAUGHT |
| M8b | site/index.html: disclosure sentence deleted | the registered claim 'disclosure episodes' was not found | CAUGHT |
| M8c | README.md: "written by contexel's author" -> "written independently" | (exit 0) | SURVIVED |
| M8d | README.md: disclosure issue link changed to another URL | (exit 0) | SURVIVED |
| M9a | COMPARISON.md prose: toolz Fill "91.6x" -> "19.6x" | benchmarks/COMPARISON.md is not the report rendered ... | CAUGHT |
| M9b | README prose "emitting many times the budget" -> "emitting 19.6x the budget" | README.md: unregistered benchmark number '19.6x' | CAUGHT |
| M9c | README prose -> "emitting about 19.6 times the budget" | (exit 0) | SURVIVED ("times" is not a unit, by design) |
| M9d | benchmarks.html prose -> "emitting 20 times" | (exit 0) | SURVIVED (same) |
| M10 | README_PYPI term-overlap recall 97% -> 98% | claim 'term-overlap baseline recall' says 98% recall, the results say 97.0% and 97.0% | CAUGHT |
| M11a | index.html "about 20 ms import" -> "about 30" | claim 'import time' says about 30 ms, contexel's import measured 21.0 ms | CAUGHT |
| M11b | index.html "about 20" -> "about 25" | (exit 0) | SURVIVED (inside the documented 25% tolerance) |
| M12 | README "0.07 s per episode" | (exit 0) | SURVIVED (seconds are not a unit, by design) |
| M13 | stages.html "2.62x" next to the Tracing-overhead reference | unregistered benchmark number '2.62x' | CAUGHT |
| M14 | README inflected end marker removed | expected exactly one benchmark:inflected block, found 0; marker without its pair; 8 bare table cells | CAUGHT |
| M15 | README second glance block | expected exactly one benchmark:glance block, found 2 | CAUGHT |
| M17 | README_PYPI "needed record in 100%" -> 99% | claim 'recall' says 99% under both signals, the results say 100.0% and 100.0% | CAUGHT |
| M18 | README_PYPI "at 0 dependencies" -> 1 | claim 'dependencies' says 1 dependencies, the results say 0 | CAUGHT |
| M19 | README "−29% on JSON-heavy" -> −30% | claim 'JSON tokenizer error' says 30, the results say 29 | CAUGHT |
| M20 | stages.html "4n characters" -> "4x characters" | unregistered benchmark number '4x' | CAUGHT |

**Unprotected published text (coverage gaps; informational, none is a number with a benchmark unit):**
- **G1. Row names inside the registered qualitative sentences** (M5a, M5b, M5c, M5g, M4d). The "two slowest budget-compliant rows" claim checks only that the phrase exists and that the fact holds for contexel plus the hand-written term-overlap row. Which rows the sentence *names* is not checked on any of the 4 pages, so "It and toolz are the two slowest" passes. The same holds for the row list after the PyPI six-operations sentence, and for a negation placed before "contexel is the row that ..." on the home page. These are false comparative statements that the checker would let through. Consider extending the patterns to include the names.
- **G2. The disclosure's wording beyond the episode count** (M8c, M8d): "written by contexel's author" and the issue link are not checked. Deleting the whole sentence is caught (M8a/M8b), because the claim is anchored on "one dataset, N episodes".
- **G3. By design** (publish.py docstring): numbers without a listed unit (MB, seconds, "times", words) and the 25% import-time tolerance (M2c, M9c, M9d, M11b, M12, M16).

### AC5: Site integrity (PASS)

`python tools/site_check.py` gives `checked 6 pages under site/ -> OK`. My own `html.parser` pass (void elements excluded; tags inside script/style are not data) compared each page with `git show 1825844:site/<page>`:

```
architecture.html      tags-balanced=True head/script/nav/style-tags-same=True anchors=0  missing=[] rel-links=11 missing=[]
benchmarks.html        tags-balanced=True head tag sequence identical except one meta content value  rel-links=11 missing=[]
contract.html          tags-balanced=True head/script/nav/style-tags-same=True rel-links=11 missing=[]
getting-started.html   tags-balanced=True head/script/nav/style-tags-same=True rel-links=14 missing=[]
index.html             tags-balanced=True head/script/nav/style-tags-same=True rel-links=18 missing=[]
stages.html            tags-balanced=True head/script/nav/style-tags-same=True anchors=16 missing=[] rel-links=11 missing=[]
```

Block-element counts are identical to main on every page. This covers div, p, section, table, tr, ul, ol, li, h1-h4, pre, nav, header, footer, for example `benchmarks.html: 8 div; 1 footer; 1 h1; 3 h2; 2 h3; 1 header; 4 li; 1 nav; 9 p; 3 table; 21 tr; 1 ul` on both main and HEAD.

The only cell-level change is on benchmarks.html: td goes from 88 to 82 and th from 15 to 14. That is the Compliance column leaving the 6-row glance table (ruling P1-1).

Other checks on every page:
- `<head>` is identical modulo `content="..."` values.
- `<nav>` is byte-identical to main.
- The stylesheet link is unchanged.
- No added or removed `<script>`, `<style>`, `<link>`, `<nav>` or `class=` lines in the diff.
- All 16 in-page anchors on stages.html have ids, and every relative link target exists.

Two intended text changes sit inside protected regions; neither is a tag or attribute-name change:
1. On `site/benchmarks.html`, the meta description content was reworded ("Measured, not asserted ..." becomes "Determinism, budget tightness, ... with the method and its limits."). This is facts:S4.
2. On `site/architecture.html`, the `STAGES` string in the inline `<script>` was reworded ("the fastest lossless cut" becomes "a cheap lossless cut", facts:S8).

### AC6: Reproduction hint (PASS)

```
$ cat benchmarks/constraints.txt  (data lines)
toolz==1.1.0
langchain-core==1.4.9
llama-index-core==0.14.23
environment.libraries = {'toolz': '1.1.0', 'langchain-core': '1.4.9', 'llama-index-core': '0.14.23'}
equal: True
$ python -m pip install --dry-run --no-index -c benchmarks/constraints.txt toolz langchain-core llama-index-core
Requirement already satisfied: toolz in <user site-packages> (1.1.0)
Requirement already satisfied: langchain-core in <user site-packages> (1.4.9)
Requirement already satisfied: llama-index-core in <user site-packages> (0.14.23)
(71 "Requirement already satisfied" lines, 0 "Would install")   pip exit=0
```
`--no-index` guarantees that no network was used. The install line `pip install -e ".[benchmarks]" -c benchmarks/constraints.txt` is in README.md:94 (and :773), README_PYPI.md:164, site/benchmarks.html:82 and benchmarks/COMPARISON.md:16. The test `test_the_constraints_file_pins_the_measured_versions` pins the file to the JSON. I did not try the editable install line itself, because it would need build isolation or the network and would write build artefacts into `<wt>`.

### AC7: Text hygiene (FAIL, one item)

- **Branch diff** (`git diff 1825844 HEAD`, 3641 lines):
  - no Windows user name, user-profile or home directory path, temporary path, `/tmp/` or `/home/` hits;
  - no e-mail address (the only `@` hits are `@pytest.mark.parametrize`);
  - no agent or session identifiers;
  - "subagent" appears only as the plan header boilerplate ("superpowers:subagent-driven-development") and in an unchanged context line of docs/plans/foundation-hardening.md.
  - The long hex strings in added lines are the dataset sha256 and the audit's output digests.
- **Commit messages:** `git log 1825844..HEAD --format=%B | grep -i -c co-authored` gives `0`. No paths or e-mail addresses. Author and committer are the repository owner on all 10 commits.
- **Subject lengths:** 70, 62, 51, **73**, 69, 48, 72, 67, 37, 35. **`c27218d docs(site): correct the comparison claims and cite only generated numbers` is 73 characters (ASCII), over the 72 limit.**
- **Compliance mentions:** `grep -rn -i compliance README.md README_PYPI.md site/*.html benchmarks/COMPARISON.md benchmarks/RESULTS.md` is empty. The wider `complian` grep finds 6 hits:
  - "budget-compliant rows (every context within the budget as the estimator counts it)" at README.md:203, README_PYPI.md:130, site/benchmarks.html:175 and site/index.html:126. These are intentional, each qualified by the estimator.
  - "Every other compliant row is faster" at site/benchmarks.html:184 and site/index.html:130. These refer back to that qualified phrase in the same paragraph. True of the data: compliant rows are contexel 37.6, term overlap 33.9, langchain-core 17.9 and hand-written 3.1 ms/episode; llama-index-core at 49.6 is not compliant.
- **CHANGELOG:** the entry "### Changed — benchmark claims (documentation and report rendering only; no measurement changed)" is under `## [Unreleased]`.

### AC8: write / write_reports safety (PASS on the letter; defects D1, D2)

Each scenario ran on a fresh scratch copy with `python <wt>/tools/check_benchmark_numbers.py --root <copy> --write`. For each one I recorded the exit code, whether a traceback was printed, which files changed (sha256 snapshot before and after) and any leftover `*.tmp` files.

| Scenario | rc | Traceback | Files changed | Message (trimmed) |
|---|---|---|---|---|
| S1 README.md read-only, block stale | 1 | no | **`.README.md.<rand>.tmp` left behind** | cannot write the generated blocks: PermissionError: [WinError 5] Access is denied: (path of .README.md.<rand>.tmp) |
| S2 COMPARISON.md read-only and stale | 1 | no | **`benchmarks/.COMPARISON.md.<rand>.tmp` left behind** | PermissionError ... (path of .COMPARISON.md.<rand>.tmp) |
| S3 README stale (writable), site/index.html stale and read-only | 1 | no | README.md rewritten, **`site/.index.html.<rand>.tmp` left behind** | PermissionError ... |
| S4 README mixed CRLF/LF (412 + 412), block stale | 0 | no | README.md (now 824 CRLF, 0 bare LF) | rewrote the generated blocks of README.md; check passes |
| S5 README mixed endings, content current | 0 | no | none | check passes (mixed endings left alone) |
| S5b COMPARISON.md mixed endings and stale | 0 | no | COMPARISON.md (all CRLF) | re-rendered ... |
| S5c README CR-only endings, block stale | 0 | no | README.md, **rewritten with LF** (0 CR) | rewrote ... |
| S6 README glance start marker deleted | 1 | no | none | expected exactly one benchmark:glance block, found 0; a benchmark marker without its pair; bare cells |
| S7 benchmarks.html suite1 end marker deleted | 1 | no | none | expected exactly one benchmark:suite1 block, found 0; marker without its pair; unregistered numbers |
| S8 COMPARISON.json empty | 1 | no | none | cannot write the generated blocks: JSONDecodeError: Expecting value: line 1 column 1 (char 0) |
| S9 RESULTS.json empty | 1 | no | none | JSONDecodeError ... |
| S10 COMPARISON.json without outcomes | 1 | no | none | KeyError: 'outcomes' |
| S11 an outcome row without fill_x | 1 | no | none | KeyError: 'fill_x' |
| S12 RESULTS.json without speed.trace | 1 | no | none | KeyError: 'trace' |
| S13 outcomes = [] | 1 | no | **README.md, site/index.html, site/benchmarks.html rewritten with header-only tables** | rewrote the generated blocks of README.md / site/index.html / site/benchmarks.html; cannot write the generated blocks: KeyError: 'contexel' |
| S14 budget.trim = [] | 1 | no | none | ValueError: max() iterable argument is empty |
| S15 COMPARISON.json is a JSON list | 1 | no | none | TypeError: list indices must be integers or slices, not str |
| S16 COMPARISON.md deleted | 1 | no | none | PublishError: benchmarks/COMPARISON.md: not a regular file; refusing to write it |
| S17 RESULTS.md is a directory | 1 | no | none | PublishError: benchmarks/RESULTS.md: not a regular file; refusing to write it |
| S18 site/ is a directory junction to a folder outside the root | 1 | no | none (outside copy untouched) | PublishError: site/index.html: resolves to (outside folder)/index.html, outside (copy root); refusing to write it |
| S19 README.md hard-linked to a file outside the root | 0 | no | README.md (os.replace swaps the link, so the outside file is not written through) | rewrote ... |
| S20 README.md over 2 MiB | 1 | no | none | OSError: 2,145,572 bytes is larger than the 2,097,152 bytes the check reads; refusing to scan it |
| S21 site/index.html invalid UTF-8 | 1 | no | none | UnicodeDecodeError: 'utf-8' codec cannot decode byte 0xff ... |
| --root a missing directory (check, and --write) | 1 | no | none | cannot read the generated results: [WinError 3] ... / cannot write the generated blocks: FileNotFoundError ... |

**Symlink target: not executable on this machine.** `os.symlink` fails with WinError 1314 (privilege not held), and the suite's own symlink test skips for the same reason. As the closest substitute, the directory junction (S18) is refused by the `resolve()` check. The `is_symlink()` branch was read but not executed. It runs in CI on Linux and macOS.

No scenario crashed with a traceback, and no target file was ever half written: `_replace_file` writes a temporary file and calls `os.replace`. The two defects below are about what is left behind or written *around* a failure.

## Bugs found

| # | Repro steps (minimal) | Severity | Fixed @ | Re-verified | Regression test |
|---|---|---|---|---|---|
| D1 | On Windows, with a stale block in a read-only README.md: `attrib +R README.md` (or `os.chmod(p, stat.S_IREAD)`), then `python tools/check_benchmark_numbers.py --root <copy> --write`. It exits 1 with PermissionError on `.README.md.<rand>.tmp`, and a read-only (0o444) `.README.md.<rand>.tmp` holding the full new text is left next to the target. Direct repro: `publish._replace_file(Path(<read-only file>), "new")` raises PermissionError on the .tmp path, its `__context__` is the failed `os.replace(tmp -> target)`, and the directory then holds `.target.md.<rand>.tmp` (0o444) and `target.md` (0o444); the target is unchanged. **Cause:** `os.chmod(tmp, <target mode>)` runs *before* `os.replace`. On Windows, replacing a read-only destination fails, and the cleanup `os.unlink(tmp)` then fails because tmp is itself read-only now. The cleanup error masks the real error, and its message names the temp file, not the target. This code is pre-existing on main, and the new `write_reports` (S2) now reaches it too. | Low (Windows only; reported, rc 1; leaves an untracked stray file in the tree) | open | n/a | none (suggest: chmod after the replace or clear the read-only bit before unlink, and a test with a read-only target) |
| D2 | Set `"outcomes": []` in a copy's COMPARISON.json, then run `--write`. README.md, site/index.html and site/benchmarks.html get their glance blocks rewritten to header-only tables, and only then does `write_reports` fail (KeyError 'contexel', rc 1). Separately, S3 shows the multi-file write is not transactional: README.md was rewritten, then site/index.html failed. **Cause:** `write()` renders and replaces file by file, and nothing validates the results or renders the reports before the first file is replaced. Each file is replaced atomically, so no file is half written, but published files are rewritten from malformed results. This is pre-existing `write()` behaviour; the branch adds `write_reports` after it. | Low (needs malformed committed JSON; the failure is reported and visible in git diff) | open | n/a | none (suggest: render every block and both reports, and run check on the in-memory result, before replacing any file) |
| D3 | `git log 1825844..HEAD --format=%s` piped to `awk 'length>72'` lists `docs(site): correct the comparison claims and cite only generated numbers` (73 characters, commit c27218d). | Low (convention; AC7 item) | open: rewording needs a history rewrite of the unpushed branch, which is the human's decision | n/a | n/a |

Informational, not defects:
- A file with mixed endings is normalised to CRLF when it is rewritten, as documented in `_newline` ("CRLF when it has any"). A CR-only file is rewritten with LF.
- The checker's error messages print absolute paths. That is console output only; nothing is committed.

## Adversarial and edge matrix (summary)

- Line endings: LF tree, CRLF tree, mixed, CR-only.
- Results files: empty JSON, JSON list, missing top-level, row and suite keys, empty lists.
- Report files: missing, directory, read-only.
- Targets: read-only, junction escaping the root, hard link outside, over 2 MiB, invalid UTF-8.
- Markers: missing start, missing end, duplicate block.
- Hiding tricks: entity units, tag-split numbers, narrow no-break space, numbers in attributes.
- Python 3.9 interpreter.

Results are in the AC4 and AC8 tables.

## Regression

`PYTHONPATH=<wt> python -m pytest -q --ignore-glob='tests/test_doctrine_*'` gives **1133 passed, 1 skipped** on the final candidate 9234c25 (the skip is the symlink test, which this Windows account cannot exercise). No flakes were seen in one full run plus one benchmark-only run (281 passed, 1 skipped).

## Security sweep (scope: this branch)

- **Secrets / private strings:** none in the diff or the commit messages (AC7).
- **Write path:** refuses symlinks (code read; not executable here), refuses targets that resolve outside the root (a junction was executed and refused), refuses non-regular files and inputs over 2 MiB. It fails closed with rc 1 on malformed results. D1 and D2 are robustness issues, not security issues.
- **Dependencies:** none added; constraints.txt only records versions.
- **Injection:** values from the results are escaped for Markdown and HTML cells (`_md`, `html.escape`). This was read, not fuzzed, in this pass.

**Security verdict:** no veto from QA. The Security Reviewer signs separately.

**QA verdict:** FAIL, returned for one item: AC7 commit subject c27218d is 73 characters, over the 72 limit. The human can waive it or reword the subject; rewording is a history rewrite of the unpushed branch. All other acceptance criteria are demonstrably met. D1 and D2 (Low, pre-existing code) and the coverage gaps G1 and G2 are recommended follow-ups, not blockers.
