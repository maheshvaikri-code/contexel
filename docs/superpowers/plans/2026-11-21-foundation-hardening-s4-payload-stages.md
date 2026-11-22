# Foundation hardening, Slice 4: Payload stages — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Execution record (2026-11-22):** this plan was executed as written, with the deviations listed in the master plan's deviation log (`docs/plans/foundation-hardening.md`) and the evidence in `docs/reviews/foundation-hardening-s4-code-review.md`. The counts quoted below are the plan-time targets; the final totals are Python 685, TypeScript 536, C# 475 and 130 shared vector cases (review-driven additions: 51 new cases instead of 44, a one-pass Python paragraph scanner, C# `AsRecords` and key-comparer fixes, corrected documentation wording).

**Goal:** Let text (a log, a web page, a plain string) go through every existing stage and back, by adding three stages, `as_records`, `split` and `join`, whose boundaries are lossless and identical in Python, TypeScript and C#.

**Architecture:** Python is the canon and each port follows it, held together by the shared vectors (new case kinds `as_records`, `join` and `text_pipeline`, and `split` as a stage vocabulary entry). Two small internals support the new stages: an `always` option on the existing strict wrapper (the new stages check their input in every mode) and a `keeps_ids` declaration on the trace wrapper (exact dropped-id attribution for the one stage that turns one record into several). Five task groups: the Python canon (Task 1), TypeScript (Task 2), C# (Task 3), the shared vectors and the runners that replay them (Task 4), documentation (Task 5).

**Tech Stack:** Python 3.9+ standard library (pytest), TypeScript 5 on Node 22 (`node:test`), C# 12 on .NET 8 (xunit). No new dependency.

**Spec:** brief `docs/briefs/foundation-hardening.md` (ACs 10 to 15; AC 34 for the documentation); design `docs/superpowers/specs/2026-11-19-foundation-hardening-design.md` section 5; `docs/adr/005-payload-stage-family.md` (accepted by this slice); `docs/adr/008-policy-fingerprint-and-trace-attribution.md` (amended); master plan `docs/plans/foundation-hardening.md` (Slice 4 row).

**Baseline (verified 2026-11-21 on `ece5687`, the head of the Slice 3 branch, which is `main` once pull request #4 is merged):** Python 537 passed; TypeScript 354 pass (`tsc` clean); C# 315 passed (0 warnings); `parity/vectors.json` 79 cases. **Targets after this slice:** Python 673, TypeScript 528, C# 464, 123 vector cases. Each task states the count it must reach.

**How this plan was verified:** the code in every block below was written and run in a scratch copy of `ece5687` (all three suites, vectors regenerated twice with an identical hash, ruff, mypy, the site check, the version check, every README example executed). The blocks are extracted from that tree by script, not retyped, and a second script replayed them onto a fresh checkout of `ece5687`, ran the suites after each task's tests and after its implementation, and compared the resulting tree with the scratch tree (result at the end of this file). The red results quoted in the steps are measured, not predicted. A separate randomized differential run of the three ports against the Python canon (not part of the repository; see "Gates") found no divergence.

## Global Constraints

- Python >= 3.9 and zero runtime dependencies. No `X | Y` annotations evaluated at runtime, no `match`, no `tomllib`.
- **Nothing that works today changes.** Every existing stage's output and every existing policy fingerprint stay as they are; the 79 existing vector cases and every other vector section stay byte-identical (the generator appends the new cases, and only `_meta.case_count` changes). The golden fingerprints of Slice 3 stay green unchanged. The only edit to an existing behavior is internal: the strict wrapper gains an option and the trace wrapper gains an option, both defaulting to today's behavior.
- Python is canon; TypeScript and C# match it through the shared vectors. The new stages check their input in every mode (they are new, so there is no lenient behavior to keep), and shape is checked before configuration.
- No version bump: identifiers change only at a release (the human's call); the work accumulates under `[Unreleased]` in `CHANGELOG.md`.
- One commit per task, Conventional Commits, 72 characters at most. **No `Co-Authored-By` trailer** (the project owner's standing rule, which overrides the harness default). Never push, open a pull request or merge: those are the human's.
- The repository is **public**: no Windows user name, home or temporary path, e-mail address or agent identifier in any file or commit message.
- Tests are never weakened to go green. A failing golden fingerprint or vector means behavior changed: stop and report.
- Regenerate vectors only with `PYTHONPATH=. python parity/generate_vectors.py` (a stale installed `contexel` shadows the checkout otherwise); never edit `parity/vectors.json` by hand.
- This machine writes CRLF; the blocks below are LF. Either is fine in the working tree, but **byte-compare each file with its block** after writing it: the editing tools have in the past turned a backslash-u escape into the character it names, and a shell heredoc collapses backslashes. The new tests therefore build non-ASCII text with `chr(...)`, `String.fromCodePoint(...)` and `char.ConvertFromUtf32(...)`; the regular expression `(?:\r?\n){2,}` and the `"\n"` literals are the places that need backslashes.

## Review Focus

The input classes the brief implies but its own tests would not reach, most likely first, each with the test that pins it:

1. **A stage that turns one record into several, beside id-less records, under `trace(id_field=...)`.** The Slice 3 rule (`lost = max(0, unidentified_out - unidentified_in)`) read an id-less record's extra chunks as ids lost by survivors and hid a real drop; this was found while planning, by a failing test. Pinned by `test_split_is_traced_and_an_expansion_is_not_a_drop`, `test_traced_keeps_ids_makes_attribution_exact_and_the_default_is_unchanged` and the shared vector `trace_dropped_ids/an_expanding_split_never_hides_a_dropped_id` (Tasks 1, 2, 3, 4).
2. **Characters outside the Basic Multilingual Plane and offsets.** Python indexes code points; TypeScript and C# strings are UTF-16, so the classic bug is counting `size` or `start`/`end` in UTF-16 units. `test_split_size_counts_code_points`, `test_split_offsets_index_back_into_the_text`, the vectors `split/size_astral` and `split/lines_*`, and the per-language twins (Tasks 1 to 4).
3. **Newline variety.** `"\r\n"` is one boundary and a lone `"\r"` is none; the characters `str.splitlines()` also cuts at (0x0B, 0x0C, 0x1C, 0x85, U+2028, U+2029) are not boundaries; a paragraph break is a run of two or more newlines of either style, including a run that starts the text or ends it. `test_split_paragraphs_boundaries` (12 texts), `test_split_lines_ignores_the_wider_splitlines_separators`, the vectors `split/paragraphs_mixed_newlines`, `split/paragraph_runs_at_the_edges_and_single_newlines`.
4. **Huge and adversarial input.** One million characters in every mode, and a million characters made only of near-matching separators (`"\r"`, `"\r\n"`, `"\n\r"`), must complete: `test_split_completes_on_a_million_characters_and_round_trips`, `test_split_stays_linear_on_adversarial_separators` and the twins.
5. **Object-key and type hazards in the ports.** A TypeScript `field` or `into` named `__proto__` or an inherited name (`constructor`) must be an ordinary key, never re-parent a chunk or fire a false conflict; `as_records` must refuse a `Map`, `Set`, `Date`, `Buffer`/typed array and class instance (not just `null`); C# `byte[]` is not a list of records; a list item that is `null` or a nested list is wrapped, not dropped. Per-language tests in Tasks 2 and 3.
6. **The empty and the absent.** Empty text yields no chunks (the record vanishes); a missing, `null` or non-string field passes through untouched even if it already has the `into` key; an empty text that already has the `into` key still raises. `test_split_a_passthrough_record_may_already_have_the_into_key`, `test_split_existing_into_key_raises_field_conflict`, the vectors `split/an_empty_text_*` and `split/non_string_values_pass_through_untouched`.

## Rulings made at plan time

Each is open to correction at the plan review; none changes a security control. S4-4 changes the audit behavior of Slice 3 code for one new stage only.

| # | Ruling | Why | Cost if wrong |
|---|---|---|---|
| S4-1 | `as_records` and `join` are called **outside** `pipeline` in all three languages; `split` is an ordinary stage inside it. | `as_records` takes a non-list and `join` returns a string, but a pipeline hands every stage a list, TypeScript and C# type it `Records -> Records`, and a strict pipeline rejects a stage whose output is not a list (R7 of Slice 2). The design already calls them entry and exit points, "as `merge`". A `join` inside a strict pipeline raises `input.not_list` naming `join` (pinned by a test), which is the right message. | A caller wanting one callable writes a three-line wrapper. A pipeline option for ramps would be additive later. |
| S4-2 | The new stages check shape in **every** mode, through an internal `always` option of the strict wrapper (Python `checked(..., always=True)`, TypeScript a trailing parameter of `checked`, C# a parameter of `Strict.CheckRecords`); shape is checked **before** configuration, as the legacy stages do under strict mode. | Design section 3: new stages validate always. Order keeps one rule everywhere. | A call that is wrong in both ways reports the shape error first. |
| S4-3 | A record whose text field is a **string** and that already has the `into` key raises `input.field_conflict`, even when its text is empty; a record whose field is not a string passes through untouched and is never checked. | The design says "a parent that already has the `into` key raises"; refusing before knowing the chunk count keeps the rule independent of the text. | A caller who tolerates a clash on empty text must pick another `into`. |
| S4-4 | `split` is traced with a new declaration, `keeps_ids` (`traced(keeps_ids=True)`, `traced(name, fn, { keepsIds: true })`, `Trace.Traced(..., keepsIds: true)`): its `lost` is 0, so its attribution is exact. All other stages keep the Slice 3 rule. | The failing test in Task 1 shows the Slice 3 rule hides a real drop when `split` expands an id-less record. `split` never removes an id (a chunk is a copy of its parent), so `lost = 0` is correct for it. | If a later stage that expands records strips ids, it must not declare `keeps_ids`. ADR-008 records this. |
| S4-5 | "Mapping" is per language: Python `Mapping`, TypeScript a plain object, C# `Dictionary<string, object?>`; a C# list is any non-string, non-`byte[]`, non-dictionary enumerable. | Each language's own record type; the Slice 2 rulings (R22) already treat non-plain TypeScript objects as not mappings. | None beyond documentation (changelog "Known limitations"). |
| S4-6 | `join` skips a record that **lacks** the field and renders a present non-string, including `null`, with `tokens.serialize` (so `null` becomes `null`). | Design section 5; "the text the budget priced". | A caller who wants nulls skipped filters first. |
| S4-7 | The shared vectors keep one flat case table: `split` becomes a stage in the vocabulary (usable in nested `pipeline` and trace cases) and three new kinds are added: `as_records`, `join`, `text_pipeline` (`as_records`, then the stages, then `join`). The AC 15 case is `text_pipeline/log_text_end_to_end` (the master plan's draft name `pipeline/log_text_end_to_end` is superseded). | The off-ramp returns a string and the on-ramp takes one, so neither fits the `pipeline` kind. | A fourth runner adapter in each port (small). |
| S4-8 | The README's executed examples gain a section; the test helper that finds a section now ends it at the next heading of the same or a higher level (it ended only at a `##` heading, so two `###` sections would have swallowed each other's examples). | AC 34: documentation cannot drift from behavior. | None. |

## Coverage of the acceptance criteria

| AC | Proven by | Task |
|---|---|---|
| 10 | `test_split_lines_keeps_separators`, `test_split_paragraphs_boundaries`, `test_split_size_counts_code_points`, `test_split_chunks_carry_the_parent_fields`; vectors `split/*`; twins in TypeScript and C# | 1, 2, 3, 4 |
| 11 | `test_split_is_lossless_and_its_offsets_index_back_for_random_texts` (seeded property, with canaries), `test_join_roundtrips_split_for_every_mode`; twins | 1, 2, 3 |
| 12 | `test_split_empty_text_yields_nothing_and_a_separator_free_text_is_one_chunk`, `test_split_completes_on_a_million_characters_and_round_trips`, `test_split_by_size_requires_a_positive_integer_size`, `test_split_size_with_another_mode_is_contradictory`, `test_split_existing_into_key_raises_field_conflict`; vectors for every error code | 1, 2, 3, 4 |
| 13 | `test_as_records_wraps_a_string`, `..._a_single_mapping`, `..._list_items`, `test_as_records_none_bytes_and_other_types_raise_not_list`; vectors `as_records/*` | 1, 2, 3, 4 |
| 14 | `test_join_skips_missing_keeps_strings_and_serializes_the_rest`, `test_join_roundtrips_split_for_every_mode`; vectors `join/*` | 1, 2, 3, 4 |
| 15 | vector `text_pipeline/log_text_end_to_end` replayed in all three languages; `test_the_end_to_end_log_case_fits_its_budget_and_keeps_the_best_lines_first` measures the budget | 4 |
| 34 | README section with two executed examples (`tests/test_doc_examples.py`), the site reference, the TypeScript and C# READMEs and their doc-example tests, changelog, ADR-005 accepted, ADR-008 amended | 5 |
| 35, 36 | not in this slice (the CI matrix is proven by the human's push; fuzz is Slice 7) | n/a |

## Execution notes

- **Branch:** `feat/hardening-s4-payload-stages`, from a clean `main` that contains the Slice 3 merge (Task 0). This plan was written against the Slice 3 branch head `ece5687`; Task 0 stops if `main` differs from it in any file outside `docs/`.
- **Subagent-driven execution, if chosen:** one fresh implementer per task, handed this file's task text only; the controller byte-compares every file to its block after each task, runs the three suites itself and reads the diff before dispatching the independent task reviewer. Mutation testing and the whole-branch gates follow the last task (see "Gates").
- **Stop-and-ask triggers** (Doctrine section 5 and the master plan): a count or golden value that does not match; anything that needs the network or a credential; an acceptance criterion that proves wrong when tested; a change to a public contract not listed under the rulings above.

## Tasks

### Task 0: Baseline and branch (no commit)

**Acceptance criteria:** none (makes every later task verifiable)

**Files:**
- No file changes. Everything this task learns goes in the ledger.

**Interfaces:**
- Consumes: `main` containing the Slice 3 merge (pull request #4). This plan was written against the Slice 3 branch head `ece5687`; later commits on `main` may only touch `docs/`.
- Produces: the branch `feat/hardening-s4-payload-stages` and the baseline counts every later task compares against.

- [ ] **Step 0.1: Branch from a clean `main`**

```bash
git checkout main && git pull --ff-only origin main
git status --short                              # must print nothing
git diff ece5687 HEAD --stat -- . ':!docs'      # must print nothing: only docs may differ from the Slice 3 head
git checkout -b feat/hardening-s4-payload-stages
```

**Stop and report** if the `git diff` prints a file: the plan was written against that tree and must be re-checked.

- [ ] **Step 0.2: Baseline of all three suites and the gates**

```bash
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
cd ts && npm run build && npm test
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
python -m ruff check contexel --no-cache
python -m mypy contexel --python-version 3.10 --no-incremental
python tools/check_versions.py
python tools/site_check.py
python -c "import json; print(json.load(open('parity/vectors.json', encoding='utf-8'))['_meta']['case_count'])"
```

Expected:

```text
537 passed
ℹ tests 354 / ℹ pass 354 / ℹ fail 0   (tsc clean)
Passed!  - Failed: 0, Passed: 315, Skipped: 0, Total: 315   (0 warnings)
All checks passed!
Success: no issues found in 8 source files
check_versions: all 7 version locations say 0.1.17
checked 6 pages under site/ -> OK
79
```

**Stop and report instead of improvising** if any count differs: this plan was written against exactly these numbers. (The suites exclude `tests/test_doctrine_*`: those are git-ignored Doctrine tooling tests that CI does not run.)

- [ ] **Step 0.3: Dependency policy (read-only)**

This slice adds no dependency of any kind: three modules, tests and documentation, in the standard library of each language. Nothing here needs the network or a credential.


### Task 1: Python canon: `as_records`, `split`, `join`

**Acceptance criteria:** AC 10, 11, 12, 13, 14 (Python canon); the trace finding of Review Focus 1

**Files:**
- Create: `tests/test_text_stages.py`, `contexel/text.py`
- Modify: `contexel/validate.py` (the `always` option), `contexel/trace.py` (the `keeps_ids` declaration), `contexel/__init__.py` (exports)

**Interfaces:**
- Produces: `contexel.as_records(x, field="text")`, `contexel.split(records, field="text", by="lines", size=None, into="chunk")`, `contexel.join(records, field="text", sep="")`; `checked(mapping=False, always=False)` in `contexel/validate.py`; `traced(fn=None, *, keeps_ids=False)` in `contexel/trace.py`. These are the canon behavior the shared vectors of Task 4 are generated from.
- Behavior (the contract, identical in all three languages): shape is checked first, in every mode, then configuration; `by="lines"` ends a chunk after each `"\n"` only; `by="paragraphs"` after each maximal run of `(?:\r?\n){2,}`; `by="size"` every `size` code points; the remainder after the last boundary is a chunk; empty text yields none; every chunk keeps its separator and carries `{index, start, end}` (code points) under `into`; a record whose field is not a string passes through; a string-valued record that already has `into` raises `input.field_conflict`; `join` skips records lacking the field and renders non-strings with `tokens.serialize`.

- [ ] **Step 1.1: Write the failing tests**

Create `tests/test_text_stages.py` with exactly this content (it ends with one newline):
<!-- OP create path=tests/test_text_stages.py -->
```python
"""Payload stages (ADR-005, brief AC 10-14): ``as_records`` / ``split`` / ``join``
carry text through the record stages and back, losslessly, with the same
boundaries in every language. Property checks are seeded (``CONTEXEL_PROP_SEED``,
``CONTEXEL_PROP_CASES``) and each has a canary proving the check can fail.
Non-ASCII text is built with ``chr`` so no editor can rewrite it."""
import copy
import random
import re

import pytest

from contexel import (ConfigError, ContexelError, InputShapeError, as_records,
                      dedupe, join, pipeline, split, stage, tokens, trace)
from contexel.trace import traced
from contexel.validate import checked, is_strict

from _gen import canary_seeds, seeds

ASTRAL = chr(0x1F600)
E_ACUTE = chr(0xE9)
# every character str.splitlines() treats as a line end, other than \n and \r
WIDE_LINE_ENDS = "".join(chr(c) for c in (0x0B, 0x0C, 0x1C, 0x1D, 0x1E, 0x85, 0x2028, 0x2029))


def chunks_of(text, **kw):
    return split(as_records(text), **kw)


def texts(chunks):
    return [c["text"] for c in chunks]


def spans(chunks):
    return [(c["chunk"]["start"], c["chunk"]["end"]) for c in chunks]


def code_of(exc_info):
    return exc_info.value.code


# ------------------------------------------------------------- as_records ----

def test_as_records_wraps_a_string():
    assert as_records("hello") == [{"text": "hello"}]
    assert as_records("x", field="body") == [{"body": "x"}]
    assert as_records("") == [{"text": ""}]


def test_as_records_a_single_mapping():
    m = {"a": 1}
    out = as_records(m)
    assert out == [{"a": 1}]
    assert out[0] is m  # the same object, not a copy


def test_as_records_list_items():
    keep = {"a": 1}
    nested = {"k": {"z": [1, 2]}}
    out = as_records([keep, "s", 5, None, ["n", 1], nested, True])
    assert out == [{"a": 1}, {"text": "s"}, {"text": 5}, {"text": None},
                   {"text": ["n", 1]}, {"k": {"z": [1, 2]}}, {"text": True}]
    assert out[0] is keep and out[5] is nested
    assert as_records(({"a": 1}, "t")) == [{"a": 1}, {"text": "t"}]
    assert as_records([]) == []


def test_as_records_does_not_mutate_a_list():
    items = [{"a": 1}, "s"]
    before = copy.deepcopy(items)
    as_records(items)
    assert items == before


@pytest.mark.parametrize("bad", [None, b"bytes", bytearray(b"x"), 5, 2.5, True,
                                 {1, 2}, iter([1])])
def test_as_records_none_bytes_and_other_types_raise_not_list(bad):
    with pytest.raises(InputShapeError) as e:
        as_records(bad)
    assert (e.value.code, e.value.stage) == ("input.not_list", "as_records")
    assert isinstance(e.value, ContexelError) and isinstance(e.value, TypeError)


@pytest.mark.parametrize("bad", ["", 5, None, ["text"]])
def test_as_records_field_must_be_a_non_empty_string(bad):
    with pytest.raises(ConfigError) as e:
        as_records("x", field=bad)
    assert (e.value.code, e.value.param) == ("config.invalid_value", "field")
    assert isinstance(e.value, ValueError)


def test_as_records_checks_the_shape_before_the_field_name():
    with pytest.raises(InputShapeError):
        as_records(None, field="")


# ------------------------------------------------------------------- split ----

def test_split_lines_keeps_separators():
    c = chunks_of("one\ntwo\nthree", by="lines")
    assert texts(c) == ["one\n", "two\n", "three"]
    assert spans(c) == [(0, 4), (4, 8), (8, 13)]
    assert [x["chunk"]["index"] for x in c] == [0, 1, 2]
    assert texts(chunks_of("a\n")) == ["a\n"]  # no empty remainder
    assert texts(chunks_of("\n")) == ["\n"]
    assert texts(chunks_of("\n\n")) == ["\n", "\n"]


def test_split_crlf_is_one_boundary_and_lone_cr_is_not():
    assert texts(chunks_of("a\r\nb\rc\nd")) == ["a\r\n", "b\rc\n", "d"]
    assert texts(chunks_of("a\rb")) == ["a\rb"]
    assert texts(chunks_of("\r")) == ["\r"]
    assert texts(chunks_of("a\r\n")) == ["a\r\n"]


def test_split_lines_ignores_the_wider_splitlines_separators():
    text = "a" + WIDE_LINE_ENDS + "b"
    assert len(text.splitlines()) > 1  # str.splitlines would have cut here
    assert texts(chunks_of(text, by="lines")) == [text]


@pytest.mark.parametrize("text,expected", [
    ("a\n\nb", ["a\n\n", "b"]),
    ("a\n\n\nb", ["a\n\n\n", "b"]),
    ("a\r\n\r\nb", ["a\r\n\r\n", "b"]),
    ("a\n\r\nb", ["a\n\r\n", "b"]),
    ("a\r\r\n\nb", ["a\r\r\n\n", "b"]),
    ("a\nb", ["a\nb"]),
    ("a\r\nb", ["a\r\nb"]),
    ("a\n \nb", ["a\n \nb"]),
    ("\n\nabc", ["\n\n", "abc"]),
    ("abc\n\n", ["abc\n\n"]),
    ("a\n\nb\n\nc", ["a\n\n", "b\n\n", "c"]),
    ("\n\n\n\n", ["\n\n\n\n"]),
])
def test_split_paragraphs_boundaries(text, expected):
    assert texts(chunks_of(text, by="paragraphs")) == expected


def test_split_size_counts_code_points():
    text = "ab" + ASTRAL * 3 + "c"  # 6 code points, 9 UTF-16 units, 15 UTF-8 bytes
    c = chunks_of(text, by="size", size=2)
    assert texts(c) == ["ab", ASTRAL * 2, ASTRAL + "c"]
    assert spans(c) == [(0, 2), (2, 4), (4, 6)]
    assert texts(chunks_of("abcdef", by="size", size=3)) == ["abc", "def"]
    assert texts(chunks_of("abc", by="size", size=10)) == ["abc"]
    assert texts(chunks_of("ab", by="size", size=1)) == ["a", "b"]


@pytest.mark.parametrize("kw", [{"by": "lines"}, {"by": "paragraphs"},
                                {"by": "size", "size": 3}])
def test_split_empty_text_yields_nothing_and_a_separator_free_text_is_one_chunk(kw):
    assert split([{"text": "", "id": 1}], **kw) == []
    out = split([{"id": 0, "text": "xyz"}, {"id": 1, "text": ""}, {"id": 2, "text": "q"}], **kw)
    assert [(c["id"], c["text"]) for c in out] == [(0, "xyz"), (2, "q")]
    only = chunks_of("abc", **kw)
    assert texts(only) == ["abc"] and spans(only) == [(0, 3)]


def test_split_offsets_index_back_into_the_text():
    text = "caf" + E_ACUTE + "\r\nna\nve" + ASTRAL + "\n\nz"
    for kw in ({"by": "lines"}, {"by": "paragraphs"}, {"by": "size", "size": 3}):
        for c in chunks_of(text, **kw):
            assert text[c["chunk"]["start"]:c["chunk"]["end"]] == c["text"]


def test_split_chunks_carry_the_parent_fields():
    parent = {"id": 7, "text": "a\nb", "meta": {"k": 1}, "tags": ["t"]}
    before = copy.deepcopy(parent)
    out = split([parent])
    assert out == [
        {"id": 7, "text": "a\n", "meta": {"k": 1}, "tags": ["t"],
         "chunk": {"index": 0, "start": 0, "end": 2}},
        {"id": 7, "text": "b", "meta": {"k": 1}, "tags": ["t"],
         "chunk": {"index": 1, "start": 2, "end": 3}},
    ]
    assert parent == before  # the input is never mutated


def test_split_index_restarts_for_each_parent_and_parents_keep_their_order():
    out = split([{"id": "a", "text": "1\n2\n"}, {"id": "b", "text": "x\ny\nz"}])
    assert [(c["id"], c["chunk"]["index"]) for c in out] == [
        ("a", 0), ("a", 1), ("b", 0), ("b", 1), ("b", 2)]


def test_split_passes_through_a_record_without_a_string_field():
    records = [{"id": 1}, {"id": 2, "text": None}, {"id": 3, "text": 5},
               {"id": 4, "text": ["a\nb"]}, {"id": 5, "text": "k\nl"}]
    out = split(records)
    assert out[:4] == records[:4]
    assert all(out[i] is records[i] for i in range(4))
    assert [c["text"] for c in out[4:]] == ["k\n", "l"]


def test_split_a_passthrough_record_may_already_have_the_into_key():
    record = {"text": 5, "chunk": "x"}
    assert split([record]) == [record]


def test_split_existing_into_key_raises_field_conflict():
    with pytest.raises(InputShapeError) as e:
        split([{"text": "ok\nok"}, {"text": "a\nb", "chunk": 1}])
    assert (e.value.code, e.value.stage, e.value.param) == (
        "input.field_conflict", "split", "into")
    assert "record 1" in str(e.value)
    # a different into name is the way out
    out = split([{"text": "a\nb", "chunk": 1}], into="part")
    assert [c["chunk"] for c in out] == [1, 1] and out[0]["part"]["index"] == 0
    # an empty text yields no chunks, but the clash is still refused
    with pytest.raises(InputShapeError):
        split([{"text": "", "chunk": 1}])
    # into equal to field clashes with the very text being split
    with pytest.raises(InputShapeError):
        split([{"text": "a"}], into="text")


@pytest.mark.parametrize("size", [None, 0, -1, True, 2.5, "3"])
def test_split_by_size_requires_a_positive_integer_size(size):
    with pytest.raises(ConfigError) as e:
        split([{"text": "abc"}], by="size", size=size)
    assert (e.value.code, e.value.param) == ("config.invalid_value", "size")


@pytest.mark.parametrize("by,size", [("lines", 3), ("paragraphs", 3), ("lines", 0)])
def test_split_size_with_another_mode_is_contradictory(by, size):
    with pytest.raises(ConfigError) as e:
        split([{"text": "abc"}], by=by, size=size)
    assert (e.value.code, e.value.param) == ("config.contradictory", "size")


@pytest.mark.parametrize("by", ["words", "", None, 3, ["lines"]])
def test_split_unknown_by_raises(by):
    with pytest.raises(ConfigError) as e:
        split([{"text": "abc"}], by=by)
    assert (e.value.code, e.value.param) == ("config.invalid_value", "by")


@pytest.mark.parametrize("kw", [{"field": 5}, {"into": None}, {"into": 3}])
def test_split_field_and_into_must_be_strings(kw):
    with pytest.raises(ConfigError) as e:
        split([{"text": "abc"}], **kw)
    assert e.value.code == "config.invalid_value"


def test_split_checks_its_input_in_every_mode():
    assert not is_strict()
    for bad in (None, "abc", 5, {"text": "a"}):
        with pytest.raises(InputShapeError) as e:
            split(bad)
        assert (e.value.code, e.value.stage) == ("input.not_list", "split")
    with pytest.raises(InputShapeError) as e:
        split([{"text": "a"}, "x"])
    assert (e.value.code, e.value.stage) == ("input.not_mapping", "split")
    assert "item 1" in str(e.value)
    assert texts(split(({"text": "a\nb"},))) == ["a\n", "b"]  # a tuple is a list here


def test_split_checks_the_shape_before_the_configuration():
    with pytest.raises(InputShapeError):
        split(None, by="bogus")


def test_split_under_a_trace_reports_a_non_list_with_the_typed_error():
    with trace():
        with pytest.raises(InputShapeError):
            split(None)


def test_split_does_not_mutate_its_input_for_any_mode():
    records = [{"text": "a\n\nb\nc", "meta": {"k": [1]}}]
    before = copy.deepcopy(records)
    for kw in ({"by": "lines"}, {"by": "paragraphs"}, {"by": "size", "size": 2}):
        split(records, **kw)
    assert records == before


def test_split_is_traced_and_an_expansion_is_not_a_drop():
    records = [{"id": "a", "text": "1\n2\n3"}, {"id": "b", "text": ""},
               {"id": "c", "text": "z"}, {"text": "no id\nhere"}]
    with trace(id_field="id") as t:
        out = split(records)
    entry = t.entries[0]
    assert (entry.stage, entry.in_count, entry.out_count) == ("split", 4, len(out))
    assert len(out) == 3 + 1 + 2  # a: 3 chunks, b: none, c: 1, no-id: 2
    # b vanished (documented) and is reported; a and c were expanded or kept
    assert entry.dropped_ids == ["b"]


def test_traced_keeps_ids_makes_attribution_exact_and_the_default_is_unchanged():
    # a stage that expands an id-less record into two and drops the record "b"
    def expand_and_drop(records):
        return [{"t": "x"}, {"t": "y"}, {"id": "a"}]

    records = [{"id": "a"}, {"id": "b"}, {"t": "one"}]
    exact = traced(keeps_ids=True)(expand_and_drop)
    default = traced(expand_and_drop)
    with trace(id_field="id") as t:
        exact(records)
        default(records)
    # exact: "b" has no survivor, so it is reported; the default rule explains
    # it away as an id lost by one of the id-less records the stage added
    assert [e.dropped_ids for e in t.entries] == [["b"], []]


def test_split_stage_policies_are_part_of_the_fingerprint():
    def fp(**kw):
        return pipeline([stage(split, **kw)]).fingerprint

    assert fp(by="size", size=3) == fp(by="size", size=3)
    assert fp(by="size", size=3) != fp(by="size", size=4)
    assert fp(by="lines") != fp(by="paragraphs")


def test_split_runs_in_a_strict_pipeline_and_strict_changes_nothing():
    text = "a\nb\n\nc"
    stages = [stage(split, by="paragraphs"), stage(dedupe, key="text")]
    assert (pipeline(stages, strict=True)(as_records(text))
            == pipeline(stages)(as_records(text)))


def test_an_off_ramp_inside_a_strict_pipeline_names_the_stage():
    # join returns a string, so it belongs OUTSIDE the pipeline (docs)
    with pytest.raises(InputShapeError) as e:
        pipeline([stage(split), stage(join)], strict=True)(as_records("a\nb"))
    assert (e.value.code, e.value.stage) == ("input.not_list", "join")


def test_checked_always_validates_without_strict_mode():
    @checked(mapping=True, always=True)
    def always(records):
        return records

    @checked(mapping=True)
    def lenient(records):
        return records

    with pytest.raises(InputShapeError):
        always(None)
    with pytest.raises(InputShapeError):
        always([1])
    assert lenient(None) is None  # strict is off: no check
    assert always([{"a": 1}]) == [{"a": 1}]


# -------------------------------------------------------------------- join ----

def test_join_skips_missing_keeps_strings_and_serializes_the_rest():
    records = [{"text": "a"}, {"other": 1}, {"text": {"k": 1}}, {"text": [1, "x"]},
               {"text": None}, {"text": True}, {"text": 2.5}]
    assert join(records, sep="|") == 'a|{"k": 1}|[1, "x"]|null|true|2.5'
    assert join(records) == 'a{"k": 1}[1, "x"]nulltrue2.5'


def test_join_field_sep_and_empty():
    assert join([{"body": "x"}, {"text": "no"}, {"body": "y"}], field="body", sep="\n") == "x\ny"
    assert join([]) == ""
    assert join([{"other": 1}]) == ""
    assert join([{"text": ""}, {"text": ""}], sep="-") == "-"


def test_join_renders_non_strings_with_the_active_serializer():
    with tokens.scoped(serializer=lambda v: "<" + type(v).__name__ + ">"):
        assert join([{"text": {"k": 1}}, {"text": "s"}], sep=" ") == "<dict> s"


def test_join_checks_its_input_in_every_mode():
    for bad in (None, "abc", 5, {"text": "a"}):
        with pytest.raises(InputShapeError) as e:
            join(bad)
        assert (e.value.code, e.value.stage) == ("input.not_list", "join")
    with pytest.raises(InputShapeError) as e:
        join([{"text": "a"}, None])
    assert (e.value.code, e.value.stage) == ("input.not_mapping", "join")
    assert join(({"text": "a"}, {"text": "b"})) == "ab"


@pytest.mark.parametrize("kw", [{"field": 5}, {"sep": None}, {"sep": 1}])
def test_join_field_and_sep_must_be_strings(kw):
    with pytest.raises(ConfigError) as e:
        join([{"text": "a"}], **kw)
    assert e.value.code == "config.invalid_value"


def test_join_roundtrips_split_for_every_mode():
    text = "line one\r\nline two\n\n\npara " + ASTRAL + "\rlone cr\n" + E_ACUTE
    for kw in ({"by": "lines"}, {"by": "paragraphs"}, {"by": "size", "size": 5}):
        assert join(chunks_of(text, **kw)) == text


# ------------------------------------------------- properties (AC 11, 12) ----

ALPHABET = ["a", "b", " ", "\n", "\n", "\r", "\r\n", "\r\n", "\n\n", ASTRAL, E_ACUTE, "x"]


def random_text(rng):
    return "".join(rng.choices(ALPHABET, k=rng.randint(0, 40)))


def check_split(text, by, size, chunks):
    """Every promise of ``split`` about one text; raises AssertionError."""
    assert "".join(c["text"] for c in chunks) == text, "chunks do not rebuild the text"
    assert [c["chunk"]["index"] for c in chunks] == list(range(len(chunks))), "bad index"
    position = 0
    for c in chunks:
        start, end = c["chunk"]["start"], c["chunk"]["end"]
        assert start == position and end > start, "offsets are not contiguous"
        assert text[start:end] == c["text"], "offsets do not index the text"
        position = end
    assert position == len(text), "offsets do not cover the text"
    body = chunks[:-1]
    if by == "lines":
        for c in body:
            assert c["text"].endswith("\n") and c["text"].count("\n") == 1, "line boundary"
        if chunks:
            assert chunks[-1]["text"].count("\n") <= 1, "line boundary"
    elif by == "paragraphs":
        run = re.compile(r"(?:\r?\n){2,}")
        for c in chunks:
            m = run.search(c["text"])
            assert m is None or m.end() == len(c["text"]), "paragraph boundary"
        for c in body:
            assert run.search(c["text"]) is not None, "paragraph boundary"
    else:
        for c in body:
            assert len(c["text"]) == size, "size boundary"
        if chunks:
            assert 1 <= len(chunks[-1]["text"]) <= size, "size boundary"


def test_split_is_lossless_and_its_offsets_index_back_for_random_texts():
    for seed in seeds():
        rng = random.Random(seed)
        text = random_text(rng)
        size = rng.randint(1, 6)
        for by, sz in (("lines", None), ("paragraphs", None), ("size", size)):
            try:
                chunks = chunks_of(text, by=by, size=sz) if sz else chunks_of(text, by=by)
                check_split(text, by, sz, chunks)
            except Exception as exc:  # name the seed, whatever failed
                raise AssertionError(f"seed {seed} by={by} text={text!r}: {exc!r}") from exc


def _drop_last_char(chunks):
    return [{**c, "text": c["text"][:-1]} if i == len(chunks) - 1 else c
            for i, c in enumerate(chunks)]


def _shift_offsets(chunks):
    return [{**c, "chunk": {**c["chunk"], "start": c["chunk"]["start"] + 1,
                            "end": c["chunk"]["end"] + 1}} for c in chunks]


def _reverse(chunks):
    return list(reversed(chunks))


def _cut_one_too_soon(chunks):
    if not chunks:
        return chunks
    first = chunks[0]
    return [{**first, "text": first["text"][:-1],
             "chunk": {**first["chunk"], "end": first["chunk"]["end"] - 1}}] + chunks[1:]


@pytest.mark.parametrize("corrupt", [_drop_last_char, _shift_offsets, _reverse,
                                     _cut_one_too_soon])
def test_the_split_check_rejects_a_broken_split(corrupt):
    caught = 0
    for seed in canary_seeds():
        text = random_text(random.Random(seed))
        if len(text) < 4:
            continue
        for by, size in (("lines", None), ("paragraphs", None), ("size", 2)):
            chunks = chunks_of(text, by=by, size=size) if size else chunks_of(text, by=by)
            check_split(text, by, size, chunks)  # the real split passes
            broken = corrupt(chunks)
            if broken == chunks:
                continue  # nothing to corrupt on this text
            with pytest.raises(AssertionError):
                check_split(text, by, size, broken)
            caught += 1
        if caught:
            return
    raise AssertionError("no seed produced a text the corruption could change")


def test_split_completes_on_a_million_characters_and_round_trips():
    lines = "abcdefghi\n" * 100_000  # exactly 1,000,000 characters
    assert len(lines) == 1_000_000
    c = chunks_of(lines, by="lines")
    assert len(c) == 100_000 and spans(c)[-1] == (999_990, 1_000_000)
    assert join(c) == lines

    paragraphs = "para\n\n" * 166_666 + "tail"
    p = chunks_of(paragraphs, by="paragraphs")
    assert len(p) == 166_667 and join(p) == paragraphs

    sized = chunks_of(lines, by="size", size=1000)
    assert len(sized) == 1000 and join(sized) == lines
    assert spans(sized)[-1] == (999_000, 1_000_000)


@pytest.mark.parametrize("unit", ["\r", "\r\n", "\n\r", "\n", "a"])
def test_split_stays_linear_on_adversarial_separators(unit):
    # a million characters of separators that almost match: must just complete
    text = unit * (1_000_000 // len(unit))
    for by in ("lines", "paragraphs"):
        assert join(chunks_of(text, by=by)) == text
```

- [ ] **Step 1.2: Run them and watch them fail to import**

```bash
PYTHONPATH=. python -m pytest -q tests/test_text_stages.py
```

Expected:

```text
E   ImportError: cannot import name 'as_records' from 'contexel' (<repo>/contexel/__init__.py)
ERROR tests/test_text_stages.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.39s
```

Nothing runs yet: the names `as_records`, `split` and `join` do not exist. (Collection fails, so the red count is the one error.)

- [ ] **Step 1.3: Add the `always` option to the strict wrapper**

In `contexel/validate.py`, replace this block:
<!-- OP replace-old path=contexel/validate.py -->
```python
def checked(mapping: NeedsMapping = False) -> Callable[[Callable], Callable]:
    """Decorator for a record stage: in strict mode, validate its input before
    the stage (and ``traced``) touches it.
```
with:
<!-- OP replace-new -->
```python
def checked(mapping: NeedsMapping = False,
            always: bool = False) -> Callable[[Callable], Callable]:
    """Decorator for a record stage: in strict mode, validate its input before
    the stage (and ``traced``) touches it.
```

In `contexel/validate.py`, replace this block:
<!-- OP replace-old path=contexel/validate.py -->
```python
    mappings, or a callable taking the bound arguments (``{"key": ...}``) for
    stages that only sometimes need one (``dedupe`` with a ``key``, ``rank``
    with a field name).
    """
```
with:
<!-- OP replace-new -->
```python
    mappings, or a callable taking the bound arguments (``{"key": ...}``) for
    stages that only sometimes need one (``dedupe`` with a ``key``, ``rank``
    with a field name). ``always=True`` validates in every mode, not only in
    strict mode: the payload stages (:mod:`contexel.text`) are new, so they have
    no lenient behavior to stay compatible with.
    """
```

In `contexel/validate.py`, replace this block:
<!-- OP replace-old path=contexel/validate.py -->
```python
        @functools.wraps(fn)
        def wrapper(records: Any, *args: Any, **kwargs: Any) -> Any:
            if _strict.get():
                need = mapping
                if callable(mapping):
```
with:
<!-- OP replace-new -->
```python
        @functools.wraps(fn)
        def wrapper(records: Any, *args: Any, **kwargs: Any) -> Any:
            if always or _strict.get():
                need = mapping
                if callable(mapping):
```

- [ ] **Step 1.4: Add the `keeps_ids` declaration to the trace wrapper**

In `contexel/trace.py`, replace this block:
<!-- OP replace-old path=contexel/trace.py -->
```python
    directions for a black-box stage that adds or removes id-less records (see
    the CHANGELOG).
    Example::
```
with:
<!-- OP replace-new -->
```python
    directions for a black-box stage that adds or removes id-less records (see
    the CHANGELOG).
    A stage that never removes the id field can declare it with
    ``traced(keeps_ids=True)`` and is then attributed exactly (``split``, which
    turns one record into several, does).
    Example::
```

In `contexel/trace.py`, replace this block:
<!-- OP replace-old path=contexel/trace.py -->
```python
def traced(fn: Callable) -> Callable:
    """Decorator: auto-record a stage's effect when a trace is active; zero cost otherwise."""

    @functools.wraps(fn)
    def wrapper(records, *args: Any, **kwargs: Any):
```
with:
<!-- OP replace-new -->
```python
def traced(fn: Optional[Callable] = None, *, keeps_ids: bool = False) -> Any:
    """Decorator: auto-record a stage's effect when a trace is active; zero cost otherwise.

    ``keeps_ids=True`` declares that the stage never removes the id field from a
    record it keeps (it may still emit several records for one input, as
    :func:`contexel.split` does). Attribution is then exact: every input id
    with no surviving record is reported dropped, and the id-less-record
    allowance described under :func:`trace` is not applied. Use it as
    ``@traced(keeps_ids=True)``; plain ``@traced`` is unchanged.
    """

    def decorate(fn: Callable) -> Callable:
        return _traced(fn, keeps_ids)

    return decorate if fn is None else decorate(fn)


def _traced(fn: Callable, keeps_ids: bool) -> Callable:
    @functools.wraps(fn)
    def wrapper(records, *args: Any, **kwargs: Any):
```

In `contexel/trace.py`, replace this block:
<!-- OP replace-old path=contexel/trace.py -->
```python
            # dropped. (Black-box stages leave which ones ambiguous: the first
            # ``lost`` in input order are the ones absorbed.)
            lost = max(0, unidentified_out - unidentified_in)
            dropped = unmatched[lost:]
        tr._add(getattr(fn, "__name__", "stage"),
```
with:
<!-- OP replace-new -->
```python
            # dropped. (Black-box stages leave which ones ambiguous: the first
            # ``lost`` in input order are the ones absorbed.)
            lost = 0 if keeps_ids else max(0, unidentified_out - unidentified_in)
            dropped = unmatched[lost:]
        tr._add(getattr(fn, "__name__", "stage"),
```

- [ ] **Step 1.5: Add the three stages and export them**

Create `contexel/text.py` with exactly this content (it ends with one newline):
<!-- OP create path=contexel/text.py -->
```python
"""Payload stages: carry text through the record stages and back (ADR-005).

Every other stage takes a list of mappings. A log, a web page or a plain string
is none of that, so three small stages convert at the edges::

    chunks = split(as_records(log_text), by="lines")     # text -> records
    ...                                                  # dedupe, rescore, rank, trim
    text = join(chunks)                                  # records -> text

``as_records`` and ``join`` are the entry and exit points: call them outside
:func:`contexel.pipeline` (like :func:`contexel.merge`), because a pipeline
hands every stage a list. ``split`` is an ordinary traced stage and belongs in
a pipeline.

Unlike the original stages, these validate the *shape* of their input in every
mode, not only in strict mode: they are new, so there is no lenient behavior to
stay compatible with.

Boundaries are explicit and identical in Python, TypeScript and C#: a line ends
after ``"\\n"`` only (so ``"\\r\\n"`` is one boundary and a lone ``"\\r"`` is none;
Python's wider ``str.splitlines`` set is not used), a paragraph ends after a
run of two or more newlines (``(?:\\r?\\n){2,}``), and sizes and offsets count
code points.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Dict, Iterator, List, Optional, cast

from . import tokens
from .errors import (
    ConfigError,
    InputShapeError,
    _kind,
    check_choice,
    check_str,
    invalid_value,
)
from .trace import traced
from .validate import checked

Record = Dict[str, Any]
Records = List[Record]

_PARAGRAPH_RUN = re.compile(r"(?:\r?\n){2,}")


def as_records(x: Any, field: str = "text") -> Records:
    """Turn a payload into a list of records, the shape every stage takes.

    A string becomes ``[{field: x}]``; a mapping becomes ``[x]`` (the same
    object, not a copy); a list or tuple keeps each mapping item and wraps every
    other item as ``{field: item}`` (nested JSON values are allowed). ``None``,
    bytes and every other type raise ``InputShapeError`` (``input.not_list``).
    ``field`` must be a non-empty string (``ConfigError``,
    ``config.invalid_value``). Not traced: it is an entry point.
    """
    if not isinstance(x, (str, Mapping, list, tuple)):
        raise InputShapeError(
            "input.not_list",
            f"as_records: expected a string, a mapping or a list, got {_kind(x)}",
            stage="as_records")
    check_str(field, "as_records", "field")
    if field == "":
        raise invalid_value("as_records", "field", "field must not be empty")
    if isinstance(x, str):
        return [{field: x}]
    if isinstance(x, Mapping):
        return [cast(Record, x)]
    return [cast(Record, item) if isinstance(item, Mapping) else {field: item}
            for item in x]


def _ends(text: str, by: str, size: Optional[int]) -> Iterator[int]:
    """The end offset (exclusive, in code points) of every chunk of ``text``."""
    n = len(text)
    if by == "size":
        assert size is not None
        yield from range(size, n, size)
        if n:
            yield n
        return
    last = 0
    if by == "lines":
        pos = text.find("\n")
        while pos != -1:
            last = pos + 1
            yield last
            pos = text.find("\n", last)
    else:
        for match in _PARAGRAPH_RUN.finditer(text):
            last = match.end()
            yield last
    if last < n:  # the remainder after the last boundary is a chunk
        yield n


@checked(mapping=True, always=True)
@traced(keeps_ids=True)
def split(records: Records, field: str = "text", by: str = "lines",
          size: Optional[int] = None, into: str = "chunk") -> Records:
    """Cut the text in ``field`` into chunk records.

    ``by="lines"`` ends a chunk after each ``"\\n"``; ``by="paragraphs"`` after
    each run of two or more newlines; ``by="size"`` every ``size`` code points
    (``size`` must then be a positive integer). Every chunk keeps its trailing
    separator, so joining the chunks with ``""`` reproduces the text exactly.

    Each chunk is ``{**parent, field: chunk_text, into: {"index": i, "start":
    s, "end": e}}``: ``index`` counts from 0 within its parent and ``[start,
    end)`` are code-point offsets into the original text, so ``text[start:end]``
    is the chunk. A record whose ``field`` is not a string passes through
    untouched; a string that is empty yields no chunks (that record
    disappears). A string-valued record that already has the ``into`` key
    raises ``InputShapeError`` (``input.field_conflict``).

    ``by`` must be ``"lines"``, ``"paragraphs"`` or ``"size"`` and ``size``
    must be omitted for the first two (``ConfigError``: ``config.invalid_value``
    and ``config.contradictory``). Items must be mappings: this stage checks
    its input in every mode.

    ``rank`` reorders chunks by score. To restore reading order before
    :func:`join`, rank again with ``by=lambda r: r["chunk"]["start"]`` and
    ``desc=False``.
    """
    check_str(field, "split", "field")
    check_choice(by, "split", "by", ("lines", "paragraphs", "size"))
    check_str(into, "split", "into")
    if by == "size":
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise invalid_value(
                "split", "size",
                f"size must be a positive integer when by='size', got {size!r}")
    elif size is not None:
        raise ConfigError(
            "config.contradictory",
            f"split: size={size!r} only applies to by='size', got by={by!r}",
            stage="split", param="size")
    out: Records = []
    for i, r in enumerate(records):
        text = r.get(field)
        if not isinstance(text, str):
            out.append(r)
            continue
        if into in r:
            raise InputShapeError(
                "input.field_conflict",
                f"split: record {i} already has a {into!r} field; "
                f"pass a different into",
                stage="split", param="into")
        start = 0
        for index, end in enumerate(_ends(text, by, size)):
            out.append({**r, field: text[start:end],
                        into: {"index": index, "start": start, "end": end}})
            start = end
    return out


@checked(mapping=True, always=True)
def join(records: Records, field: str = "text", sep: str = "") -> str:
    """Join the ``field`` of every record into one string.

    A record without ``field`` is skipped; a string value is used as it is; any
    other value is rendered with :func:`contexel.tokens.serialize`, the text the
    token budget priced. The parts are joined with ``sep``. Items must be
    mappings (checked in every mode). Not traced: it is an exit point.
    """
    check_str(field, "join", "field")
    check_str(sep, "join", "sep")
    parts: List[str] = []
    for r in records:
        if field not in r:
            continue
        value = r[field]
        parts.append(value if isinstance(value, str) else tokens.serialize(value))
    return sep.join(parts)
```

In `contexel/__init__.py`, replace this block:
<!-- OP replace-old path=contexel/__init__.py -->
```python
    truncate_field,
)
from .trace import Trace, trace
from .validate import strict
```
with:
<!-- OP replace-new -->
```python
    truncate_field,
)
from .text import as_records, join, split
from .trace import Trace, trace
from .validate import strict
```

In `contexel/__init__.py`, replace this block:
<!-- OP replace-old path=contexel/__init__.py -->
```python
    "trim_to_budget",
    "merge",
    "pipeline",
    "stage",
```
with:
<!-- OP replace-new -->
```python
    "trim_to_budget",
    "merge",
    "as_records",
    "split",
    "join",
    "pipeline",
    "stage",
```

- [ ] **Step 1.6: Run the new tests, the whole suite and the lint gates**

```bash
PYTHONPATH=. python -m pytest -q tests/test_text_stages.py
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
python -m ruff check contexel --no-cache
python -m mypy contexel --python-version 3.10 --no-incremental
```

Expected:

```text
88 passed
625 passed
All checks passed!
Success: no issues found in 9 source files
```

Every existing test passes unchanged: nothing in this task changes an existing stage's output, and `tests/test_fingerprint_golden.py` is among them.

- [ ] **Step 1.7: Prove the `keeps_ids` mechanism took effect (then undo)**

In `contexel/text.py` change `@traced(keeps_ids=True)` to plain `@traced`, run `PYTHONPATH=. python -m pytest -q tests/test_text_stages.py`, and see exactly `test_split_is_traced_and_an_expansion_is_not_a_drop` fail with `assert [] == ['b']` (the id-less record's extra chunk was read as the id that record `b` lost). Restore the line; `git diff` must show no change. This is a sanity check, not a commit.

- [ ] **Step 1.8: Commit**

```bash
git add tests/test_text_stages.py contexel/text.py contexel/validate.py contexel/trace.py contexel/__init__.py
git commit -m "feat(py): add as_records, split and join payload stages"
```


### Task 2: TypeScript port: `asRecords`, `split`, `join`

**Acceptance criteria:** AC 10 to 14 (TypeScript)

**Files:**
- Create: `ts/test/text.test.ts`, `ts/src/text.ts`
- Modify: `ts/package.json` (the test list), `ts/src/validate.ts` (`always`), `ts/src/trace.ts` (`keepsIds`), `ts/src/index.ts` (exports)

**Interfaces:**
- Consumes: the Python canon of Task 1 (its tests and behavior).
- Produces: `asRecords(x, { field })`, `split(records, { field, by, size, into })`, `join(records, { field, sep })` exported from `ts/src/index.ts`; `checked(name, needsMapping, fn, always = false)`; `traced(name, fn, { keepsIds })`. Options are camelCase; the behavior is the contract of Task 1.

- [ ] **Step 2.1: Write the failing tests**

Create `ts/test/text.test.ts` with exactly this content (it ends with one newline):
<!-- OP create path=ts/test/text.test.ts -->
```typescript
/**
 * Payload stages (ADR-005): `asRecords` / `split` / `join` carry text through
 * the record stages and back, losslessly, with the same boundaries in every
 * language. Mirrors tests/test_text_stages.py. Property checks are seeded
 * (CONTEXEL_PROP_SEED, CONTEXEL_PROP_CASES) from a tiny generator of our own,
 * and each check has a canary proving it can fail. Non-ASCII text is built with
 * String.fromCodePoint so no editor can rewrite it.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ConfigError,
  ContexelError,
  InputShapeError,
  asRecords,
  dedupe,
  isStrict,
  join,
  pipeline,
  split,
  stage,
  tokens,
  trace,
  type Rec,
  type Records,
} from "../src/index.js";
import { traced } from "../src/trace.js";
import { checked } from "../src/validate.js";

const NL = String.fromCharCode(10);
const CR = String.fromCharCode(13);
const ASTRAL = String.fromCodePoint(0x1f600);
const E_ACUTE = String.fromCodePoint(0xe9);
// every character Python's str.splitlines() treats as a line end, other than LF and CR
const WIDE_LINE_ENDS = [0x0b, 0x0c, 0x1c, 0x1d, 0x1e, 0x85, 0x2028, 0x2029]
  .map((c) => String.fromCodePoint(c))
  .join("");

type SplitOptions = { field?: string; by?: string; size?: unknown; into?: string };

// the stages take loosely typed input on purpose in these tests (null, numbers)
const asRec = (x: unknown) => asRecords(x as never);
const splitOf = (records: unknown, options?: SplitOptions): Records =>
  split(records as Records, options as never);
const joinOf = (records: unknown, options?: { field?: unknown; sep?: unknown }): string =>
  join(records as Records, options as never);
const chunksOf = (text: string, options?: SplitOptions): Records =>
  splitOf(asRecords(text), options);
const texts = (chunks: Records) => chunks.map((c) => c.text);
const chunkOf = (c: Rec) => c.chunk as { index: number; start: number; end: number };
const spans = (chunks: Records) => chunks.map((c) => [chunkOf(c).start, chunkOf(c).end]);

/** Assert `fn` throws a `cls` error with this code (and, when given, stage and param). */
function raises(
  fn: () => unknown,
  cls: typeof ConfigError | typeof InputShapeError,
  code: string,
  where: { stage?: string; param?: string } = {}
): void {
  assert.throws(fn, (e: unknown) => {
    assert.ok(e instanceof cls, `expected ${cls.name}, got ${String(e)}`);
    assert.ok(e instanceof ContexelError);
    assert.strictEqual(e.code, code);
    if (where.stage !== undefined) assert.strictEqual(e.stage, where.stage);
    if (where.param !== undefined) assert.strictEqual(e.param, where.param);
    return true;
  });
}

/** A record with an own data property of this name (also "__proto__"). */
function recordWith(props: Record<string, unknown>): Rec {
  const r: Rec = {};
  for (const [k, v] of Object.entries(props)) {
    Object.defineProperty(r, k, { value: v, writable: true, enumerable: true, configurable: true });
  }
  return r;
}

/* ------------------------------------------------------------- asRecords ---- */

test("asRecords wraps a string", () => {
  assert.deepStrictEqual(asRecords("hello"), [{ text: "hello" }]);
  assert.deepStrictEqual(asRecords("x", { field: "body" }), [{ body: "x" }]);
  assert.deepStrictEqual(asRecords(""), [{ text: "" }]);
});

test("asRecords: a single mapping is one record, the same object", () => {
  const m = { a: 1 };
  const out = asRecords(m);
  assert.deepStrictEqual(out, [{ a: 1 }]);
  assert.strictEqual(out[0], m); // the same object, not a copy
  const bare = Object.create(null) as Rec;
  bare.a = 1;
  assert.strictEqual(asRecords(bare)[0], bare); // a null-prototype object is a mapping
});

test("asRecords: a list keeps mappings and wraps everything else", () => {
  const keep = { a: 1 };
  const nested = { k: { z: [1, 2] } };
  const out = asRecords([keep, "s", 5, null, ["n", 1], nested, true]);
  assert.deepStrictEqual(out, [
    { a: 1 },
    { text: "s" },
    { text: 5 },
    { text: null },
    { text: ["n", 1] },
    { k: { z: [1, 2] } },
    { text: true },
  ]);
  assert.strictEqual(out[0], keep);
  assert.strictEqual(out[5], nested);
  assert.deepStrictEqual(asRecords([]), []);
});

test("asRecords does not mutate a list", () => {
  const items = [{ a: 1 }, "s"];
  const before = structuredClone(items);
  asRecords(items);
  assert.deepStrictEqual(items, before);
});

class Point {
  x = 1;
}

const NOT_A_LIST: Array<[string, unknown]> = [
  ["null", null],
  ["undefined", undefined],
  ["Uint8Array", new Uint8Array([1])],
  ["Buffer", Buffer.from("x")],
  ["an integer", 5],
  ["a float", 2.5],
  ["a boolean", true],
  ["a bigint", 5n],
  ["a Set", new Set([1, 2])],
  ["a Map", new Map([[1, 2]])],
  ["a Date", new Date(0)],
  ["a class instance", new Point()],
  ["a function", () => 1],
];

for (const [label, bad] of NOT_A_LIST) {
  test(`asRecords: ${label} raises input.not_list`, () => {
    raises(() => asRec(bad), InputShapeError, "input.not_list", { stage: "as_records" });
  });
}

test("asRecords: a class instance inside a list is wrapped, not kept", () => {
  const p = new Point();
  const out = asRecords([p]);
  assert.strictEqual(out[0].text, p);
});

for (const bad of ["", 5, null, ["text"]]) {
  test(`asRecords: field ${JSON.stringify(bad)} must be a non-empty string`, () => {
    raises(
      () => asRecords("x", { field: bad as never }),
      ConfigError,
      "config.invalid_value",
      { stage: "as_records", param: "field" }
    );
  });
}

test("asRecords checks the shape before the field name", () => {
  raises(() => asRecords(null as never, { field: "" }), InputShapeError, "input.not_list");
});

test("asRecords: a field named __proto__ is an ordinary own property", () => {
  const [wrapped] = asRecords("x", { field: "__proto__" });
  assert.ok(Object.hasOwn(wrapped, "__proto__"));
  assert.strictEqual(Object.getPrototypeOf(wrapped), Object.prototype);
  const [item] = asRecords([5], { field: "__proto__" });
  assert.ok(Object.hasOwn(item, "__proto__"));
  assert.strictEqual(Object.getPrototypeOf(item), Object.prototype);
});

/* ------------------------------------------------------------------ split ---- */

test("split by lines keeps the separators", () => {
  const c = chunksOf("one" + NL + "two" + NL + "three", { by: "lines" });
  assert.deepStrictEqual(texts(c), ["one" + NL, "two" + NL, "three"]);
  assert.deepStrictEqual(spans(c), [[0, 4], [4, 8], [8, 13]]);
  assert.deepStrictEqual(c.map((x) => chunkOf(x).index), [0, 1, 2]);
  assert.deepStrictEqual(texts(chunksOf("a" + NL)), ["a" + NL]); // no empty remainder
  assert.deepStrictEqual(texts(chunksOf(NL)), [NL]);
  assert.deepStrictEqual(texts(chunksOf(NL + NL)), [NL, NL]);
});

test("split: CRLF is one boundary and a lone CR is none", () => {
  assert.deepStrictEqual(texts(chunksOf("a" + CR + NL + "b" + CR + "c" + NL + "d")), [
    "a" + CR + NL,
    "b" + CR + "c" + NL,
    "d",
  ]);
  assert.deepStrictEqual(texts(chunksOf("a" + CR + "b")), ["a" + CR + "b"]);
  assert.deepStrictEqual(texts(chunksOf(CR)), [CR]);
  assert.deepStrictEqual(texts(chunksOf("a" + CR + NL)), ["a" + CR + NL]);
});

test("split by lines ignores the wider splitlines separators", () => {
  const text = "a" + WIDE_LINE_ENDS + "b";
  assert.deepStrictEqual(texts(chunksOf(text, { by: "lines" })), [text]);
});

const PARAGRAPHS: Array<[string, string[]]> = [
  ["a" + NL + NL + "b", ["a" + NL + NL, "b"]],
  ["a" + NL + NL + NL + "b", ["a" + NL + NL + NL, "b"]],
  ["a" + CR + NL + CR + NL + "b", ["a" + CR + NL + CR + NL, "b"]],
  ["a" + NL + CR + NL + "b", ["a" + NL + CR + NL, "b"]],
  ["a" + CR + CR + NL + NL + "b", ["a" + CR + CR + NL + NL, "b"]],
  ["a" + NL + "b", ["a" + NL + "b"]],
  ["a" + CR + NL + "b", ["a" + CR + NL + "b"]],
  ["a" + NL + " " + NL + "b", ["a" + NL + " " + NL + "b"]],
  [NL + NL + "abc", [NL + NL, "abc"]],
  ["abc" + NL + NL, ["abc" + NL + NL]],
  ["a" + NL + NL + "b" + NL + NL + "c", ["a" + NL + NL, "b" + NL + NL, "c"]],
  [NL + NL + NL + NL, [NL + NL + NL + NL]],
];

PARAGRAPHS.forEach(([text, expected], i) => {
  test(`split by paragraphs: boundary case ${i}`, () => {
    assert.deepStrictEqual(texts(chunksOf(text, { by: "paragraphs" })), expected);
  });
});

test("split by size counts code points", () => {
  const text = "ab" + ASTRAL.repeat(3) + "c"; // 6 code points, 9 UTF-16 units
  const c = chunksOf(text, { by: "size", size: 2 });
  assert.deepStrictEqual(texts(c), ["ab", ASTRAL.repeat(2), ASTRAL + "c"]);
  assert.deepStrictEqual(spans(c), [[0, 2], [2, 4], [4, 6]]);
  assert.deepStrictEqual(texts(chunksOf("abcdef", { by: "size", size: 3 })), ["abc", "def"]);
  assert.deepStrictEqual(texts(chunksOf("abc", { by: "size", size: 10 })), ["abc"]);
  assert.deepStrictEqual(texts(chunksOf("ab", { by: "size", size: 1 })), ["a", "b"]);
  assert.deepStrictEqual(texts(chunksOf(ASTRAL.repeat(3), { by: "size", size: 1 })), [ASTRAL, ASTRAL, ASTRAL]);
});

test("split counts a lone surrogate as one code point, as an iterating string does", () => {
  const lone = String.fromCharCode(0xd83d);
  const c = chunksOf(lone + ASTRAL + "a", { by: "size", size: 2 });
  assert.deepStrictEqual(texts(c), [lone + ASTRAL, "a"]);
  assert.deepStrictEqual(spans(c), [[0, 2], [2, 3]]);
  const lines = chunksOf("a" + lone + NL + "b");
  assert.deepStrictEqual(spans(lines), [[0, 3], [3, 4]]);
});

const MODES: Array<[string, SplitOptions]> = [
  ["lines", { by: "lines" }],
  ["paragraphs", { by: "paragraphs" }],
  ["size", { by: "size", size: 3 }],
];

for (const [label, options] of MODES) {
  test(`split by ${label}: empty text yields nothing and a separator-free text is one chunk`, () => {
    assert.deepStrictEqual(splitOf([{ text: "", id: 1 }], options), []);
    const out = splitOf([{ id: 0, text: "xyz" }, { id: 1, text: "" }, { id: 2, text: "q" }], options);
    assert.deepStrictEqual(
      out.map((c) => [c.id, c.text]),
      [[0, "xyz"], [2, "q"]]
    );
    const only = chunksOf("abc", options);
    assert.deepStrictEqual(texts(only), ["abc"]);
    assert.deepStrictEqual(spans(only), [[0, 3]]);
  });
}

test("split: offsets index back into the text by code points", () => {
  const text = "caf" + E_ACUTE + CR + NL + "na" + NL + "ve" + ASTRAL + NL + NL + "z";
  const cps = [...text];
  for (const [, options] of MODES) {
    for (const c of chunksOf(text, options)) {
      assert.strictEqual(cps.slice(chunkOf(c).start, chunkOf(c).end).join(""), c.text);
    }
  }
});

test("split: chunks carry the parent fields and the input is never mutated", () => {
  const parent = { id: 7, text: "a" + NL + "b", meta: { k: 1 }, tags: ["t"] };
  const before = structuredClone(parent);
  const out = split([parent]);
  assert.deepStrictEqual(out, [
    { id: 7, text: "a" + NL, meta: { k: 1 }, tags: ["t"], chunk: { index: 0, start: 0, end: 2 } },
    { id: 7, text: "b", meta: { k: 1 }, tags: ["t"], chunk: { index: 1, start: 2, end: 3 } },
  ]);
  assert.deepStrictEqual(parent, before);
});

test("split: the index restarts for each parent and parents keep their order", () => {
  const out = split([
    { id: "a", text: "1" + NL + "2" + NL },
    { id: "b", text: "x" + NL + "y" + NL + "z" },
  ]);
  assert.deepStrictEqual(
    out.map((c) => [c.id, chunkOf(c).index]),
    [["a", 0], ["a", 1], ["b", 0], ["b", 1], ["b", 2]]
  );
});

test("split passes a record without a string field through untouched", () => {
  const records = [
    { id: 1 },
    { id: 2, text: null },
    { id: 3, text: 5 },
    { id: 4, text: ["a" + NL + "b"] },
    { id: 5, text: "k" + NL + "l" },
  ];
  const out = split(records);
  assert.deepStrictEqual(out.slice(0, 4), records.slice(0, 4));
  for (let i = 0; i < 4; i++) assert.strictEqual(out[i], records[i]);
  assert.deepStrictEqual(texts(out.slice(4)), ["k" + NL, "l"]);
});

test("split: a pass-through record may already have the into key", () => {
  const record = { text: 5, chunk: "x" };
  const out = split([record]);
  assert.deepStrictEqual(out, [record]);
  assert.strictEqual(out[0], record);
});

test("split: an existing into key raises input.field_conflict", () => {
  assert.throws(
    () => split([{ text: "ok" + NL + "ok" }, { text: "a" + NL + "b", chunk: 1 }]),
    (e: unknown) => {
      assert.ok(e instanceof InputShapeError);
      assert.deepStrictEqual([e.code, e.stage, e.param], ["input.field_conflict", "split", "into"]);
      assert.match(e.message, /record 1/);
      return true;
    }
  );
  // a different into name is the way out
  const out = split([{ text: "a" + NL + "b", chunk: 1 }], { into: "part" });
  assert.deepStrictEqual(out.map((c) => c.chunk), [1, 1]);
  assert.strictEqual((out[0].part as { index: number }).index, 0);
  // an empty text yields no chunks, but the clash is still refused
  raises(() => split([{ text: "", chunk: 1 }]), InputShapeError, "input.field_conflict");
  // into equal to field clashes with the very text being split
  raises(() => split([{ text: "a" }], { into: "text" }), InputShapeError, "input.field_conflict");
});

test("split reads and tests OWN properties only, never inherited ones", () => {
  const inheritedText = Object.create({ text: "a" + NL + "b" }) as Rec;
  assert.strictEqual(split([inheritedText])[0], inheritedText); // no own text: passes through
  const inheritedInto = Object.assign(Object.create({ chunk: 1 }) as Rec, { text: "a" + NL + "b" });
  const out = split([inheritedInto]); // an inherited into is no conflict
  assert.deepStrictEqual(texts(out), ["a" + NL, "b"]);
  assert.ok(Object.hasOwn(out[0], "chunk"));
});

test("split: a field or into named __proto__ is an ordinary own data property", () => {
  const byField = split([recordWith({ ["__proto__"]: "a" + NL + "b" })], { field: "__proto__" });
  assert.strictEqual(byField.length, 2);
  for (const c of byField) {
    assert.strictEqual(Object.getPrototypeOf(c), Object.prototype);
    assert.ok(Object.hasOwn(c, "__proto__") && Object.hasOwn(c, "chunk"));
  }
  assert.deepStrictEqual(
    byField.map((c) => Object.getOwnPropertyDescriptor(c, "__proto__")?.value),
    ["a" + NL, "b"]
  );
  const byInto = split([{ text: "a" + NL + "b" }], { into: "__proto__" });
  for (const c of byInto) {
    assert.strictEqual(Object.getPrototypeOf(c), Object.prototype);
    assert.ok(Object.hasOwn(c, "__proto__"));
  }
  assert.deepStrictEqual(Object.getOwnPropertyDescriptor(byInto[1], "__proto__")?.value, {
    index: 1,
    start: 2,
    end: 3,
  });
  // an OWN __proto__ already there is a clash; the inherited accessor is not
  raises(
    () => split([recordWith({ text: "a", ["__proto__"]: 1 })], { into: "__proto__" }),
    InputShapeError,
    "input.field_conflict"
  );
  assert.strictEqual(split([{ text: "a" }], { into: "__proto__" }).length, 1);
});

for (const size of [undefined, null, 0, -1, true, 2.5, "3", NaN, Infinity]) {
  test(`split by size requires a positive integer size: ${String(size)}`, () => {
    raises(
      () => splitOf([{ text: "abc" }], { by: "size", size }),
      ConfigError,
      "config.invalid_value",
      { stage: "split", param: "size" }
    );
  });
}

test("split by size accepts any positive integer, however large", () => {
  assert.deepStrictEqual(texts(chunksOf("abc", { by: "size", size: Number.MAX_SAFE_INTEGER * 4 })), ["abc"]);
});

for (const [by, size] of [["lines", 3], ["paragraphs", 3], ["lines", 0]] as const) {
  test(`split: size ${size} with by=${by} is contradictory`, () => {
    raises(
      () => splitOf([{ text: "abc" }], { by, size }),
      ConfigError,
      "config.contradictory",
      { stage: "split", param: "size" }
    );
  });
}

test("split: a null size with another mode means no size", () => {
  assert.deepStrictEqual(texts(splitOf([{ text: "a" + NL + "b" }], { by: "lines", size: null })), ["a" + NL, "b"]);
  assert.deepStrictEqual(texts(splitOf([{ text: "ab" }], { by: "paragraphs", size: undefined })), ["ab"]);
});

for (const by of ["words", "", null, 3, ["lines"]]) {
  test(`split: unknown by ${JSON.stringify(by)} raises`, () => {
    raises(
      () => splitOf([{ text: "abc" }], { by: by as never }),
      ConfigError,
      "config.invalid_value",
      { stage: "split", param: "by" }
    );
  });
}

for (const options of [{ field: 5 }, { into: null }, { into: 3 }]) {
  test(`split: field and into must be strings: ${JSON.stringify(options)}`, () => {
    raises(
      () => splitOf([{ text: "abc" }], options as never),
      ConfigError,
      "config.invalid_value"
    );
  });
}

test("split validates field, by, into, size in that order", () => {
  const bad = { field: 5, by: "words", into: 3, size: 0 };
  assert.throws(() => splitOf([], bad as never), (e: unknown) => (e as ConfigError).param === "field");
  assert.throws(() => splitOf([], { ...bad, field: "text" } as never), (e: unknown) => (e as ConfigError).param === "by");
  assert.throws(
    () => splitOf([], { ...bad, field: "text", by: "size" } as never),
    (e: unknown) => (e as ConfigError).param === "into"
  );
  assert.throws(
    () => splitOf([], { ...bad, field: "text", by: "size", into: "chunk" } as never),
    (e: unknown) => (e as ConfigError).param === "size"
  );
});

test("split checks its input in every mode", () => {
  assert.ok(!isStrict());
  for (const bad of [null, undefined, "abc", 5, { text: "a" }]) {
    raises(() => splitOf(bad), InputShapeError, "input.not_list", { stage: "split" });
  }
  assert.throws(
    () => splitOf([{ text: "a" }, "x"]),
    (e: unknown) => {
      assert.ok(e instanceof InputShapeError);
      assert.deepStrictEqual([e.code, e.stage], ["input.not_mapping", "split"]);
      assert.match(e.message, /item 1/);
      return true;
    }
  );
  raises(() => splitOf([{ text: "a" }, null]), InputShapeError, "input.not_mapping");
  raises(() => splitOf([[1]]), InputShapeError, "input.not_mapping");
});

test("split checks the shape before the configuration", () => {
  raises(() => splitOf(null, { by: "bogus" }), InputShapeError, "input.not_list");
  raises(() => splitOf([1], { by: "bogus" }), InputShapeError, "input.not_mapping");
});

test("split under a trace reports a non-list with the typed error", () => {
  raises(() => trace(null, () => splitOf(null)), InputShapeError, "input.not_list");
});

test("split does not mutate its input for any mode", () => {
  const records = [{ text: "a" + NL + NL + "b" + NL + "c", meta: { k: [1] } }];
  const before = structuredClone(records);
  for (const [, options] of MODES) split(records, options as never);
  assert.deepStrictEqual(records, before);
});

test("split is traced, and an expansion is not a drop", () => {
  const records = [
    { id: "a", text: "1" + NL + "2" + NL + "3" },
    { id: "b", text: "" },
    { id: "c", text: "z" },
    { text: "no id" + NL + "here" },
  ];
  const [out, tr] = trace({ idField: "id" }, () => split(records));
  const entry = tr.entries[0];
  assert.deepStrictEqual([entry.stage, entry.inCount, entry.outCount], ["split", 4, out.length]);
  assert.strictEqual(out.length, 3 + 1 + 2); // a: 3 chunks, b: none, c: 1, no-id: 2
  // b vanished (documented) and is reported; a and c were expanded or kept
  assert.deepStrictEqual(entry.droppedIds, ["b"]);
});

test("traced keepsIds makes attribution exact, and the default is unchanged", () => {
  // a stage that expands an id-less record into two and drops the record "b"
  const expandAndDrop = (_records: Rec[]): Rec[] => [{ t: "x" }, { t: "y" }, { id: "a" }];
  const records: Rec[] = [{ id: "a" }, { id: "b" }, { t: "one" }];
  const exact = traced("expand_and_drop", expandAndDrop, { keepsIds: true });
  const dflt = traced("expand_and_drop", expandAndDrop);
  const explicit = traced("expand_and_drop", expandAndDrop, { keepsIds: false });
  const [, tr] = trace({ idField: "id" }, () => {
    exact(records);
    dflt(records);
    explicit(records);
  });
  // exact: "b" has no survivor, so it is reported; the default rule explains
  // it away as an id lost by one of the id-less records the stage added
  assert.deepStrictEqual(
    tr.entries.map((e) => e.droppedIds),
    [["b"], [], []]
  );
});

test("traced keepsIds changes nothing without a trace and returns the stage's own output", () => {
  const fn = (records: Rec[]): Rec[] => records.slice(1);
  const wrapped = traced("slice", fn, { keepsIds: true });
  assert.deepStrictEqual(wrapped([{ id: 1 }, { id: 2 }]), [{ id: 2 }]);
});

test("split's stage policies are part of the fingerprint", () => {
  const fp = (options: SplitOptions) => pipeline([stage(split, options as never)]).fingerprint;
  assert.strictEqual(fp({ by: "size", size: 3 }), fp({ by: "size", size: 3 }));
  assert.notStrictEqual(fp({ by: "size", size: 3 }), fp({ by: "size", size: 4 }));
  assert.notStrictEqual(fp({ by: "lines" }), fp({ by: "paragraphs" }));
});

test("split runs in a strict pipeline and strict changes nothing", () => {
  const text = "a" + NL + "b" + NL + NL + "c";
  const stages = [stage(split, { by: "paragraphs" }), stage(dedupe, { key: "text" })];
  assert.deepStrictEqual(
    pipeline(stages, { strict: true })(asRecords(text)),
    pipeline(stages)(asRecords(text))
  );
});

test("an off-ramp inside a strict pipeline is refused", () => {
  // join returns a string, so it belongs OUTSIDE the pipeline (docs)
  const offRamp = join as unknown as (records: Records, params: object) => Records;
  raises(
    () => pipeline([stage(split, {}), stage(offRamp, {})], { strict: true })(asRecords("a" + NL + "b")),
    InputShapeError,
    "input.not_list"
  );
});

test("checked(..., always) validates without strict mode", () => {
  const always = checked("always", true, (records: Rec[]) => records, true);
  const lenient = checked("lenient", true, (records: Rec[]) => records);
  const explicit = checked("explicit", true, (records: Rec[]) => records, false);
  assert.ok(!isStrict());
  raises(() => always(null as never), InputShapeError, "input.not_list", { stage: "always" });
  raises(() => always([1] as never), InputShapeError, "input.not_mapping", { stage: "always" });
  assert.strictEqual(lenient(null as never), null); // strict is off: no check
  assert.strictEqual(explicit(null as never), null);
  assert.deepStrictEqual(always([{ a: 1 }]), [{ a: 1 }]);
});

test("checked(..., always) honours needsMapping, including a function of the arguments", () => {
  const listOnly = checked("list_only", false, (records: Rec[]) => records, true);
  raises(() => listOnly(null as never), InputShapeError, "input.not_list");
  assert.deepStrictEqual(listOnly([1] as never), [1]); // items are not inspected
  const byArgs = checked("by_args", (n: number) => n > 0, (records: Rec[], _n: number) => records, true);
  raises(() => byArgs([1] as never, 1), InputShapeError, "input.not_mapping");
  assert.deepStrictEqual(byArgs([1] as never, 0), [1]);
  raises(() => byArgs(null as never, 0), InputShapeError, "input.not_list");
});

/* ------------------------------------------------------------------- join ---- */

test("join skips missing, keeps strings and serializes the rest", () => {
  const records = [
    { text: "a" },
    { other: 1 },
    { text: { k: 1 } },
    { text: [1, "x"] },
    { text: null },
    { text: true },
    { text: 2.5 },
  ];
  assert.strictEqual(join(records, { sep: "|" }), 'a|{"k": 1}|[1, "x"]|null|true|2.5');
  assert.strictEqual(join(records), 'a{"k": 1}[1, "x"]nulltrue2.5');
});

test("join: field, sep and empty input", () => {
  assert.strictEqual(
    join([{ body: "x" }, { text: "no" }, { body: "y" }], { field: "body", sep: NL }),
    "x" + NL + "y"
  );
  assert.strictEqual(join([]), "");
  assert.strictEqual(join([{ other: 1 }]), "");
  assert.strictEqual(join([{ text: "" }, { text: "" }], { sep: "-" }), "-");
});

test("join reads OWN properties only", () => {
  assert.strictEqual(join([Object.create({ text: "x" }) as Rec]), "");
  assert.strictEqual(join([recordWith({ ["__proto__"]: "p" })], { field: "__proto__" }), "p");
});

test("join renders non-strings with the active serializer", () => {
  const out = tokens.scoped(
    { serializer: (v) => "<" + (Array.isArray(v) ? "list" : typeof v) + ">" },
    () => join([{ text: { k: 1 } }, { text: "s" }, { text: [1] }], { sep: " " })
  );
  assert.strictEqual(out, "<object> s <list>");
});

test("join checks its input in every mode", () => {
  for (const bad of [null, undefined, "abc", 5, { text: "a" }]) {
    raises(() => joinOf(bad), InputShapeError, "input.not_list", { stage: "join" });
  }
  assert.throws(
    () => joinOf([{ text: "a" }, null]),
    (e: unknown) => {
      assert.ok(e instanceof InputShapeError);
      assert.deepStrictEqual([e.code, e.stage], ["input.not_mapping", "join"]);
      return true;
    }
  );
});

for (const options of [{ field: 5 }, { sep: null }, { sep: 1 }]) {
  test(`join: field and sep must be strings: ${JSON.stringify(options)}`, () => {
    raises(
      () => joinOf([{ text: "a" }], options),
      ConfigError,
      "config.invalid_value",
      { stage: "join" }
    );
  });
}

test("join checks the shape before the configuration", () => {
  raises(() => joinOf(null, { field: 5 }), InputShapeError, "input.not_list");
});

test("join round-trips split for every mode", () => {
  const text =
    "line one" + CR + NL + "line two" + NL + NL + NL + "para " + ASTRAL + CR + "lone cr" + NL + E_ACUTE;
  for (const [, options] of MODES) {
    assert.strictEqual(join(chunksOf(text, options)), text);
  }
  assert.strictEqual(join(chunksOf(text, { by: "size", size: 5 })), text);
});

/* ---------------------------------------------------------- properties ---- */

const DEFAULT_SEED = 20261119;
const DEFAULT_CASES = 200;

function envInt(name: string, fallback: number): number {
  const raw = process.env[name];
  return raw === undefined ? fallback : Number.parseInt(raw, 10);
}

/** The run's seeds: CONTEXEL_PROP_SEED upwards, CONTEXEL_PROP_CASES of them. */
function seeds(): number[] {
  const base = envInt("CONTEXEL_PROP_SEED", DEFAULT_SEED);
  return Array.from({ length: envInt("CONTEXEL_PROP_CASES", DEFAULT_CASES) }, (_, i) => base + i);
}

/** The run's seeds, then the default ones: whether a check CAN fail must not
 * depend on how small a reproduction run is. */
function canarySeeds(): number[] {
  return [...seeds(), ...Array.from({ length: DEFAULT_CASES }, (_, i) => DEFAULT_SEED + i)];
}

/** A tiny linear congruential generator, so the sequence never depends on the
 * runtime (Math.random cannot be seeded). */
class Lcg {
  private state: number;
  constructor(seed: number) {
    this.state = seed >>> 0;
  }
  /** An integer in [0, n). */
  below(n: number): number {
    this.state = (Math.imul(this.state, 1664525) + 1013904223) >>> 0;
    return Math.floor((this.state / 4294967296) * n);
  }
  /** An integer in [lo, hi]. */
  between(lo: number, hi: number): number {
    return lo + this.below(hi - lo + 1);
  }
}

const ALPHABET = ["a", "b", " ", NL, NL, CR, CR + NL, CR + NL, NL + NL, ASTRAL, E_ACUTE, "x"];

function randomText(rng: Lcg): string {
  const k = rng.between(0, 40);
  let out = "";
  for (let i = 0; i < k; i++) out += ALPHABET[rng.below(ALPHABET.length)];
  return out;
}

const cpLength = (s: string): number => [...s].length;

/** Every promise of `split` about one text; throws an AssertionError. */
function checkSplit(text: string, by: string, size: number | null, chunks: Records): void {
  const cps = [...text];
  assert.strictEqual(chunks.map((c) => c.text).join(""), text, "chunks do not rebuild the text");
  assert.deepStrictEqual(
    chunks.map((c) => chunkOf(c).index),
    chunks.map((_, i) => i),
    "bad index"
  );
  let position = 0;
  for (const c of chunks) {
    const { start, end } = chunkOf(c);
    assert.ok(start === position && end > start, "offsets are not contiguous");
    assert.strictEqual(cps.slice(start, end).join(""), c.text, "offsets do not index the text");
    position = end;
  }
  assert.strictEqual(position, cps.length, "offsets do not cover the text");
  const body = chunks.slice(0, -1);
  if (by === "lines") {
    for (const c of body) {
      const t = c.text as string;
      assert.ok(t.endsWith(NL) && t.split(NL).length - 1 === 1, "line boundary");
    }
    if (chunks.length) assert.ok(((chunks[chunks.length - 1].text as string).split(NL).length - 1) <= 1, "line boundary");
  } else if (by === "paragraphs") {
    const run = /(?:\r?\n){2,}/;
    for (const c of chunks) {
      const m = run.exec(c.text as string);
      assert.ok(m === null || m.index + m[0].length === (c.text as string).length, "paragraph boundary");
    }
    for (const c of body) assert.ok(run.test(c.text as string), "paragraph boundary");
  } else {
    for (const c of body) assert.strictEqual(cpLength(c.text as string), size, "size boundary");
    if (chunks.length) {
      const last = cpLength(chunks[chunks.length - 1].text as string);
      assert.ok(last >= 1 && last <= (size as number), "size boundary");
    }
  }
}

const withMode = (by: string, size: number | null): SplitOptions =>
  size === null ? { by } : { by, size };

test("split is lossless and its offsets index back for random texts", () => {
  for (const seed of seeds()) {
    const rng = new Lcg(seed);
    const text = randomText(rng);
    const size = rng.between(1, 6);
    for (const [by, sz] of [["lines", null], ["paragraphs", null], ["size", size]] as const) {
      try {
        checkSplit(text, by, sz, chunksOf(text, withMode(by, sz)));
      } catch (e) {
        // name the seed, whatever failed
        throw new assert.AssertionError({
          message: `seed ${seed} by=${by} text=${JSON.stringify(text)}: ${String(e)}`,
        });
      }
    }
  }
});

const dropLastChar = (chunks: Records): Records =>
  chunks.map((c, i) => (i === chunks.length - 1 ? { ...c, text: [...(c.text as string)].slice(0, -1).join("") } : c));
const shiftOffsets = (chunks: Records): Records =>
  chunks.map((c) => ({ ...c, chunk: { ...chunkOf(c), start: chunkOf(c).start + 1, end: chunkOf(c).end + 1 } }));
const reverse = (chunks: Records): Records => [...chunks].reverse();
const cutOneTooSoon = (chunks: Records): Records => {
  if (!chunks.length) return chunks;
  const [first, ...rest] = chunks;
  return [
    { ...first, text: [...(first.text as string)].slice(0, -1).join(""), chunk: { ...chunkOf(first), end: chunkOf(first).end - 1 } },
    ...rest,
  ];
};

const CORRUPTIONS: Array<[string, (chunks: Records) => Records]> = [
  ["dropLastChar", dropLastChar],
  ["shiftOffsets", shiftOffsets],
  ["reverse", reverse],
  ["cutOneTooSoon", cutOneTooSoon],
];

for (const [name, corrupt] of CORRUPTIONS) {
  test(`the split check rejects a broken split: ${name}`, () => {
    let caught = 0;
    for (const seed of canarySeeds()) {
      const text = randomText(new Lcg(seed));
      if (cpLength(text) < 4) continue;
      for (const [by, size] of [["lines", null], ["paragraphs", null], ["size", 2]] as const) {
        const chunks = chunksOf(text, withMode(by, size));
        checkSplit(text, by, size, chunks); // the real split passes
        const broken = corrupt(chunks);
        if (JSON.stringify(broken) === JSON.stringify(chunks)) continue; // nothing to corrupt here
        assert.throws(() => checkSplit(text, by, size, broken), assert.AssertionError);
        caught++;
      }
      if (caught) return;
    }
    assert.fail("no seed produced a text the corruption could change");
  });
}

test("the generator is deterministic: the same seed gives the same text, another seed another", () => {
  assert.strictEqual(randomText(new Lcg(1)), randomText(new Lcg(1)));
  const distinct = new Set(Array.from({ length: 20 }, (_, i) => randomText(new Lcg(i))));
  assert.ok(distinct.size > 10);
  // pinned: if this sequence changes, every recorded failing seed changes meaning
  const rng = new Lcg(1);
  assert.deepStrictEqual([0, 1, 2, 3, 4].map(() => rng.below(1000)), [236, 369, 504, 704, 50]);
});

/* ---------------------------------------------------------- performance ---- */

/** Run `fn` and assert it finished in well under two seconds (the requirement
 * is linear time; a quadratic cut of a million characters takes minutes). */
function underTwoSeconds<T>(label: string, fn: () => T): T {
  const started = performance.now();
  const result = fn();
  const elapsed = performance.now() - started;
  assert.ok(elapsed < 2000, `${label} took ${Math.round(elapsed)} ms`);
  return result;
}

test("split completes on a million characters and round-trips", () => {
  const lines = "abcdefghi" + NL;
  const text = lines.repeat(100_000); // exactly 1,000,000 characters
  assert.strictEqual(text.length, 1_000_000);
  const c = underTwoSeconds("lines", () => chunksOf(text, { by: "lines" }));
  assert.strictEqual(c.length, 100_000);
  assert.deepStrictEqual(spans(c)[c.length - 1], [999_990, 1_000_000]);
  assert.strictEqual(join(c), text);

  const paragraphs = ("para" + NL + NL).repeat(166_666) + "tail";
  const p = underTwoSeconds("paragraphs", () => chunksOf(paragraphs, { by: "paragraphs" }));
  assert.strictEqual(p.length, 166_667);
  assert.strictEqual(join(p), paragraphs);

  const sized = underTwoSeconds("size", () => chunksOf(text, { by: "size", size: 1000 }));
  assert.strictEqual(sized.length, 1000);
  assert.strictEqual(join(sized), text);
  assert.deepStrictEqual(spans(sized)[sized.length - 1], [999_000, 1_000_000]);
});

test("split by size counts a million astral code points without UTF-16 arithmetic", () => {
  const text = ASTRAL.repeat(1_000_000); // 2,000,000 UTF-16 units
  const sized = underTwoSeconds("astral size", () => chunksOf(text, { by: "size", size: 1000 }));
  assert.strictEqual(sized.length, 1000);
  assert.deepStrictEqual(spans(sized)[999], [999_000, 1_000_000]);
  assert.strictEqual(join(sized), text);
  const lines = (ASTRAL + NL).repeat(100_000);
  const c = underTwoSeconds("astral lines", () => chunksOf(lines, { by: "lines" }));
  assert.deepStrictEqual(spans(c)[c.length - 1], [199_998, 200_000]);
});

for (const unit of [CR, CR + NL, NL + CR, NL, "a"]) {
  test(`split stays linear on adversarial separators: ${JSON.stringify(unit)}`, () => {
    // a million characters of separators that almost match: must just complete
    const text = unit.repeat(Math.floor(1_000_000 / unit.length));
    for (const by of ["lines", "paragraphs"]) {
      const out = underTwoSeconds(by, () => chunksOf(text, { by }));
      assert.strictEqual(join(out), text);
    }
  });
}
```

In `ts/package.json`, replace this block:
<!-- OP replace-old path=ts/package.json -->
```json
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "test": "tsc -p tsconfig.test.json && node --test dist-test/test/parity.test.js dist-test/test/behavior.test.js dist-test/test/cases.test.js dist-test/test/errors.test.js dist-test/test/strict.test.js dist-test/test/controls.test.js dist-test/test/config.test.js dist-test/test/runner.test.js dist-test/test/docs.test.js dist-test/test/fingerprint.test.js dist-test/test/audit.test.js",
    "prepublishOnly": "npm run build && npm test"
  },
```
with:
<!-- OP replace-new -->
```json
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "test": "tsc -p tsconfig.test.json && node --test dist-test/test/parity.test.js dist-test/test/behavior.test.js dist-test/test/cases.test.js dist-test/test/errors.test.js dist-test/test/strict.test.js dist-test/test/controls.test.js dist-test/test/config.test.js dist-test/test/runner.test.js dist-test/test/docs.test.js dist-test/test/fingerprint.test.js dist-test/test/audit.test.js dist-test/test/text.test.js",
    "prepublishOnly": "npm run build && npm test"
  },
```

- [ ] **Step 2.2: Build and run: they fail**

```bash
cd ts && npm run build && npm test
```

Expected:

```text
test/text.test.ts(16,3): error TS2724: '"../src/index.js"' has no exported member named 'asRecords'. Did you mean 'Records'?
test/text.test.ts(19,3): error TS2305: Module '"../src/index.js"' has no exported member 'join'.
test/text.test.ts(21,3): error TS2305: Module '"../src/index.js"' has no exported member 'split'.
...   (and further errors for the option parameters the new tests pass)
```

The compiler reports that `asRecords`, `split` and `join` are not exported from `../src/index.js`.

- [ ] **Step 2.3: Add the `always` and `keepsIds` options**

In `ts/src/validate.ts`, replace this block:
<!-- OP replace-old path=ts/src/validate.ts -->
```typescript
 * stage always indexes items as mappings, or a function of the call's
 * arguments for stages that only sometimes need one (`dedupe` with a `key`,
 * `rank` with a field name).
 */
export function checked<A extends unknown[], R>(
  name: string,
  needsMapping: boolean | ((...args: A) => boolean),
  fn: (records: Rec[], ...args: A) => R
): (records: Rec[], ...args: A) => R {
  return (records: Rec[], ...args: A): R => {
    if (isStrict()) {
      const need = typeof needsMapping === "function" ? needsMapping(...args) : needsMapping;
      checkRecords(records, name, need);
```
with:
<!-- OP replace-new -->
```typescript
 * stage always indexes items as mappings, or a function of the call's
 * arguments for stages that only sometimes need one (`dedupe` with a `key`,
 * `rank` with a field name). `always: true` validates in every mode, not only
 * in strict mode: the payload stages (`split`, `join`) are new, so they have no
 * lenient behavior to stay compatible with.
 */
export function checked<A extends unknown[], R>(
  name: string,
  needsMapping: boolean | ((...args: A) => boolean),
  fn: (records: Rec[], ...args: A) => R,
  always = false
): (records: Rec[], ...args: A) => R {
  return (records: Rec[], ...args: A): R => {
    if (always || isStrict()) {
      const need = typeof needsMapping === "function" ? needsMapping(...args) : needsMapping;
      checkRecords(records, name, need);
```

In `ts/src/trace.ts`, replace this block:
<!-- OP replace-old path=ts/src/trace.ts -->
```typescript
}

/** Wrap a stage so an active trace records its effect (incl. dropped ids). */
export function traced<A extends unknown[]>(
  name: string,
  fn: (records: Rec[], ...args: A) => Rec[]
): (records: Rec[], ...args: A) => Rec[] {
  return (records: Rec[], ...args: A): Rec[] => {
    const tr = currentTrace();
```
with:
<!-- OP replace-new -->
```typescript
}

/**
 * Wrap a stage so an active trace records its effect (incl. dropped ids).
 *
 * `keepsIds: true` declares that the stage never removes the id field from a
 * record it keeps (it may still emit several records for one input, as `split`
 * does). Attribution is then exact: every input id with no surviving record is
 * reported dropped, and the id-less-record allowance described under `trace` is
 * not applied. The default is unchanged.
 */
export function traced<A extends unknown[]>(
  name: string,
  fn: (records: Rec[], ...args: A) => Rec[],
  options: { keepsIds?: boolean } = {}
): (records: Rec[], ...args: A) => Rec[] {
  const keepsIds = options.keepsIds === true;
  return (records: Rec[], ...args: A): Rec[] => {
    const tr = currentTrace();
```

In `ts/src/trace.ts`, replace this block:
<!-- OP replace-old path=ts/src/trace.ts -->
```typescript
      // explained away; every other one is reported dropped (the first `lost`
      // in input order are the ones absorbed).
      const lost = Math.max(0, unidentifiedOut - unidentifiedIn);
      dropped = unmatched.slice(lost);
    }
```
with:
<!-- OP replace-new -->
```typescript
      // explained away; every other one is reported dropped (the first `lost`
      // in input order are the ones absorbed).
      const lost = keepsIds ? 0 : Math.max(0, unidentifiedOut - unidentifiedIn);
      dropped = unmatched.slice(lost);
    }
```

- [ ] **Step 2.4: Add the three stages and export them**

Create `ts/src/text.ts` with exactly this content (it ends with one newline):
<!-- OP create path=ts/src/text.ts -->
```typescript
/**
 * Payload stages: carry text through the record stages and back (ADR-005) —
 * parity port of contexel's Python `text` module.
 *
 * Every other stage takes a list of mappings. A log, a web page or a plain
 * string is none of that, so three small stages convert at the edges:
 *
 *     const chunks = split(asRecords(logText), { by: "lines" });   // text -> records
 *     // ... dedupe, rescore, rank, trimToBudget
 *     const text = join(chunks);                                   // records -> text
 *
 * `asRecords` and `join` are the entry and exit points: call them outside
 * `pipeline` (like `merge`), because a pipeline hands every stage a list.
 * `split` is an ordinary traced stage and belongs in a pipeline.
 *
 * Unlike the original stages, these validate the *shape* of their input in
 * every mode, not only in strict mode: they are new, so there is no lenient
 * behavior to stay compatible with.
 *
 * Boundaries are explicit and identical in Python, TypeScript and C#: a line
 * ends after "\n" only (so "\r\n" is one boundary and a lone "\r" is none), a
 * paragraph ends after a run of two or more newlines (`(?:\r?\n){2,}`), and
 * sizes and offsets count code points, never UTF-16 units.
 */
import * as tokens from "./tokens.js";
import { traced } from "./trace.js";
import { ConfigError, InputShapeError, checkChoice, checkStr, invalidValue } from "./errors.js";
import { checked } from "./validate.js";
import { pyRepr, pyTypeName } from "./py.js";
import type { Rec, Records } from "./stages.js";

/** Own-property write that cannot hit setters or the "__proto__" trap —
 * a key named "__proto__" becomes an ordinary data property, as in Python. */
function defineField(out: Rec, key: string, value: unknown): void {
  Object.defineProperty(out, key, {
    value,
    writable: true,
    enumerable: true,
    configurable: true,
  });
}

/** A mapping, as the on-ramp sees one: a plain object (the prototype is
 * `Object.prototype` or `null`). An array, `Set`, `Map`, `Date`, typed array,
 * boxed primitive or class instance is not one. */
function isPlainObject(value: unknown): value is Rec {
  if (value === null || typeof value !== "object") return false;
  if (Object.prototype.toString.call(value) !== "[object Object]") return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/** The name of a value's type for an error message. */
function kindOf(value: unknown): string {
  if (value !== null && typeof value === "object" && !Array.isArray(value) && !(value instanceof Set)) {
    const ctor = (value as { constructor?: { name?: unknown } }).constructor;
    return typeof ctor?.name === "string" && ctor.name ? ctor.name : "object";
  }
  return pyTypeName(value);
}

/**
 * Turn a payload into a list of records, the shape every stage takes.
 *
 * A string becomes `[{ [field]: x }]`; a mapping (a plain object) becomes `[x]`
 * (the same object, not a copy); an array keeps each mapping item and wraps
 * every other item as `{ [field]: item }` (nested JSON values are allowed).
 * `null`, `undefined`, bytes and every other type throw `InputShapeError`
 * (`input.not_list`). `field` must be a non-empty string (`ConfigError`,
 * `config.invalid_value`); the type check runs first. Not traced: it is an
 * entry point.
 */
export function asRecords(x: unknown, options: { field?: string } = {}): Records {
  const isText = typeof x === "string";
  const isList = Array.isArray(x);
  const isMap = isPlainObject(x);
  if (!isText && !isList && !isMap) {
    throw new InputShapeError(
      "input.not_list",
      `as_records: expected a string, a mapping or a list, got ${kindOf(x)}`,
      { stage: "as_records" }
    );
  }
  const field = options.field === undefined ? "text" : options.field;
  checkStr(field, "as_records", "field");
  if (field === "") throw invalidValue("as_records", "field", "field must not be empty");
  const wrap = (item: unknown): Rec => {
    const record: Rec = {};
    defineField(record, field, item);
    return record;
  };
  if (isText) return [wrap(x)];
  if (isMap) return [x];
  return (x as unknown[]).map((item) => (isPlainObject(item) ? item : wrap(item)));
}

const SURROGATE = /[\uD800-\uDFFF]/;

/** Whether a high surrogate at `i` is followed by a low one (one code point). */
function isPair(text: string, i: number): boolean {
  const hi = text.charCodeAt(i);
  if (hi < 0xd800 || hi > 0xdbff) return false;
  const lo = text.charCodeAt(i + 1); // NaN past the end
  return lo >= 0xdc00 && lo <= 0xdfff;
}

/**
 * Cut `text` into chunks and hand each to `emit(chunk, start, end)`, the
 * offsets counted in code points. One pass over the text: every position is
 * looked at a bounded number of times, so a million characters of separators
 * that almost match cost no more than a million of anything else.
 */
function cut(
  text: string,
  by: string,
  size: number | null,
  emit: (chunk: string, start: number, end: number) => void
): void {
  const n = text.length;
  const astral = SURROGATE.test(text); // without a surrogate UTF-16 index === code-point offset
  let from = 0; // UTF-16 index where the next chunk starts
  let cp = 0; // the same place, in code points
  const put = (to: number, known?: number): void => {
    let length = known ?? to - from;
    if (known === undefined && astral) {
      length = 0;
      for (let i = from; i < to; i += isPair(text, i) ? 2 : 1) length++;
    }
    emit(text.slice(from, to), cp, cp + length);
    from = to;
    cp += length;
  };
  if (by === "size") {
    const step = size as number;
    if (!astral) {
      for (let i = step; i < n; i += step) put(i);
    } else {
      while (from < n) {
        let to = from;
        let taken = 0;
        while (to < n && taken < step) {
          to += isPair(text, to) ? 2 : 1;
          taken++;
        }
        put(to, taken);
      }
    }
  } else if (by === "lines") {
    for (let pos = text.indexOf("\n"); pos !== -1; pos = text.indexOf("\n", pos + 1)) put(pos + 1);
  } else {
    // the leftmost run of two or more newline units ("\n" or "\r\n"), taken as
    // long as possible: (?:\r?\n){2,}. A start that yields fewer than two units
    // cannot succeed anywhere up to the point where it stopped, so the scan
    // resumes after that point and never revisits a character.
    let i = 0;
    while (i < n) {
      let j = i;
      let units = 0;
      for (;;) {
        const c = text.charCodeAt(j);
        if (c === 10) j += 1;
        else if (c === 13 && text.charCodeAt(j + 1) === 10) j += 2;
        else break;
        units++;
      }
      if (units >= 2) {
        put(j);
        i = j;
      } else {
        i = j + 1;
      }
    }
  }
  if (from < n) put(n); // the remainder after the last boundary is a chunk
}

/**
 * Cut the text in `field` into chunk records.
 *
 * `by: "lines"` (the default) ends a chunk after each `"\n"`; `by:
 * "paragraphs"` after each run of two or more newlines; `by: "size"` every
 * `size` code points (`size` must then be a positive integer). Every chunk
 * keeps its trailing separator, so joining the chunks with `""` reproduces the
 * text exactly.
 *
 * Each chunk is `{ ...parent, [field]: chunkText, [into]: { index, start, end } }`:
 * `index` counts from 0 within its parent and `[start, end)` are code-point
 * offsets into the original text. A record whose own `field` is not a string
 * passes through untouched (the same object); a string that is empty yields no
 * chunks (that record disappears). A string-valued record that already has its
 * own `into` property throws `InputShapeError` (`input.field_conflict`).
 *
 * `by` must be `"lines"`, `"paragraphs"` or `"size"` and `size` must be omitted
 * for the first two (`ConfigError`: `config.invalid_value` and
 * `config.contradictory`). Items must be mappings: this stage checks its input
 * in every mode.
 *
 * `rank` reorders chunks by score. To restore reading order before `join`,
 * rank again with `by: (r) => r.chunk.start` and `desc: false`.
 */
export const split = checked(
  "split",
  true,
  traced(
    "split",
    (
      records: Records,
      params: {
        field?: string;
        by?: "lines" | "paragraphs" | "size";
        size?: number | null;
        into?: string;
      } = {}
    ): Records => {
      const field = params.field === undefined ? "text" : params.field;
      checkStr(field, "split", "field");
      const by = params.by === undefined ? "lines" : params.by;
      checkChoice(by, "split", "by", ["lines", "paragraphs", "size"]);
      const into = params.into === undefined ? "chunk" : params.into;
      checkStr(into, "split", "into");
      const size = params.size === undefined ? null : params.size;
      if (by === "size") {
        if (typeof size !== "number" || !Number.isInteger(size) || size < 1) {
          throw invalidValue(
            "split",
            "size",
            `size must be a positive integer when by='size', got ${pyRepr(size)}`
          );
        }
      } else if (size !== null) {
        throw new ConfigError(
          "config.contradictory",
          `split: size=${pyRepr(size)} only applies to by='size', got by=${pyRepr(by)}`,
          { stage: "split", param: "size" }
        );
      }
      const out: Records = [];
      for (let i = 0; i < records.length; i++) {
        const r = records[i];
        const text = Object.hasOwn(r, field) ? r[field] : undefined;
        if (typeof text !== "string") {
          out.push(r);
          continue;
        }
        if (Object.hasOwn(r, into)) {
          throw new InputShapeError(
            "input.field_conflict",
            `split: record ${i} already has a ${pyRepr(into)} field; pass a different into`,
            { stage: "split", param: "into" }
          );
        }
        let index = 0;
        cut(text, by, size, (chunk, start, end) => {
          const c: Rec = { ...r };
          defineField(c, field, chunk);
          defineField(c, into, { index: index++, start, end });
          out.push(c);
        });
      }
      return out;
    },
    { keepsIds: true }
  ),
  true
);

/**
 * Join the `field` of every record into one string.
 *
 * A record without its own `field` is skipped; a string value is used as it is;
 * any other value is rendered with `tokens.serialize`, the text the token
 * budget priced. The parts are joined with `sep`. Items must be mappings
 * (checked in every mode). Not traced: it is an exit point.
 */
export const join = checked(
  "join",
  true,
  (records: Records, params: { field?: string; sep?: string } = {}): string => {
    const field = params.field === undefined ? "text" : params.field;
    checkStr(field, "join", "field");
    const sep = params.sep === undefined ? "" : params.sep;
    checkStr(sep, "join", "sep");
    const parts: string[] = [];
    for (const r of records) {
      if (!Object.hasOwn(r, field)) continue;
      const value = r[field];
      parts.push(typeof value === "string" ? value : tokens.serialize(value));
    }
    return parts.join(sep);
  },
  true
);
```

In `ts/src/index.ts`, replace this block:
<!-- OP replace-old path=ts/src/index.ts -->
```typescript
  type Records,
} from "./stages.js";
export { pipeline, stage, type StageFn } from "./pipeline.js";
export { shaped } from "./shaped.js";
```
with:
<!-- OP replace-new -->
```typescript
  type Records,
} from "./stages.js";
export { asRecords, split, join } from "./text.js";
export { pipeline, stage, type StageFn } from "./pipeline.js";
export { shaped } from "./shaped.js";
```

- [ ] **Step 2.5: Build and run all TypeScript tests**

```bash
cd ts && npm run build && npm test
```

Expected:

```text
ℹ tests 464
ℹ pass 464
ℹ fail 0
```

`tsc` must stay clean and every earlier test passes unchanged (the Slice 3 fingerprint baselines among them).

- [ ] **Step 2.6: Commit**

```bash
git add ts/test/text.test.ts ts/package.json ts/src/text.ts ts/src/validate.ts ts/src/trace.ts ts/src/index.ts
git commit -m "feat(ts): add asRecords, split and join payload stages"
```


### Task 3: C# port: `Text.AsRecords`, `Text.Split`, `Text.Join`

**Acceptance criteria:** AC 10 to 14 (C#)

**Files:**
- Create: `csharp/Contexel.Tests/TextTests.cs`, `csharp/Contexel/Text.cs`
- Modify: `csharp/Contexel/Strict.cs` (`always`), `csharp/Contexel/Trace.cs` (`keepsIds`)

**Interfaces:**
- Consumes: the Python canon of Task 1.
- Produces: `public static class Text` with `AsRecords(object? x, string field = "text")`, `Split(Records records, string field = "text", string by = "lines", int? size = null, string into = "chunk")`, `Join(Records records, string field = "text", string sep = "")`; `Strict.CheckRecords(..., always: false)`; `Trace.Traced(..., keepsIds: false)`. No existing public signature changes.

- [ ] **Step 3.1: Write the failing tests**

Create `csharp/Contexel.Tests/TextTests.cs` with exactly this content (it ends with one newline):
<!-- OP create path=csharp/Contexel.Tests/TextTests.cs -->
```csharp
using System.Diagnostics;
using System.Text.RegularExpressions;
using Xunit;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>Payload stages (ADR-005): AsRecords / Split / Join carry text
/// through the record stages and back, losslessly, with the same boundaries in
/// every language. Mirrors tests/test_text_stages.py. The property checks are
/// seeded (CONTEXEL_PROP_SEED, CONTEXEL_PROP_CASES) from a small LCG of our own,
/// so the sequence never changes between runtimes, and each has a canary
/// proving the check can fail. Non-ASCII text is built with
/// char.ConvertFromUtf32 so no editor can rewrite it.</summary>
public class TextTests
{
    private static readonly string Astral = char.ConvertFromUtf32(0x1F600);
    private static readonly string EAcute = char.ConvertFromUtf32(0xE9);

    // every character str.splitlines() treats as a line end, other than \n and \r
    private static readonly string WideLineEnds = string.Concat(
        new[] { 0x0B, 0x0C, 0x1C, 0x1D, 0x1E, 0x85, 0x2028, 0x2029 }.Select(char.ConvertFromUtf32));

    private static Rec R(params object?[] keyValues)
    {
        var rec = new Rec();
        for (int i = 0; i < keyValues.Length; i += 2) rec[(string)keyValues[i]!] = keyValues[i + 1];
        return rec;
    }

    private static List<object?> L(params object?[] items) => [.. items];

    private static Records ChunksOf(string text, string by = "lines", int? size = null,
                                    string field = "text") =>
        Text.Split(Text.AsRecords(text, field), field: field, by: by, size: size);

    private static string[] Texts(Records chunks) =>
        chunks.Select(c => (string)c["text"]!).ToArray();

    private static (long Index, long Start, long End) Where(Rec chunk)
    {
        var c = (Rec)chunk["chunk"]!;
        return ((long)c["index"]!, (long)c["start"]!, (long)c["end"]!);
    }

    private static (long, long)[] Spans(Records chunks) =>
        chunks.Select(c => (Where(c).Start, Where(c).End)).ToArray();

    /// <summary>Deep structural equality (canonical JSON; key order is irrelevant).</summary>
    private static void Same(object? expected, object? actual) =>
        Assert.Equal(Tokens.PythonJson(expected), Tokens.PythonJson(actual));

    private static T Code<T>(Action act, string code, string? stage = null, string? param = null)
        where T : ContexelException
    {
        var e = Assert.Throws<T>(act);
        Assert.Equal(code, e.Code);
        if (stage is not null) Assert.Equal(stage, e.Stage);
        if (param is not null) Assert.Equal(param, e.Param);
        return e;
    }

    /// <summary>The code points of a string (a surrogate pair is one).</summary>
    private static int[] CodePoints(string s)
    {
        var cps = new List<int>(s.Length);
        for (int i = 0; i < s.Length; i++)
        {
            if (char.IsSurrogatePair(s, i)) { cps.Add(char.ConvertToUtf32(s, i)); i++; }
            else cps.Add(s[i]);
        }
        return [.. cps];
    }

    private static string FromCodePoints(int[] cps, int start, int end) =>
        string.Concat(cps[start..end].Select(char.ConvertFromUtf32));

    // ---------------------------------------------------------- AsRecords ----

    [Fact]
    public void AsRecordsWrapsAString()
    {
        Same(new Records { R("text", "hello") }, Text.AsRecords("hello"));
        Same(new Records { R("body", "x") }, Text.AsRecords("x", "body"));
        Same(new Records { R("text", "") }, Text.AsRecords(""));
    }

    [Fact]
    public void AsRecordsASingleMappingIsTheSameObject()
    {
        var m = R("a", 1L);
        var output = Text.AsRecords(m);
        Same(new Records { R("a", 1L) }, output);
        Assert.Same(m, output[0]); // the same object, not a copy
    }

    [Fact]
    public void AsRecordsListItemsKeepMappingsAndWrapEverythingElse()
    {
        var keep = R("a", 1L);
        var nested = R("k", R("z", L(1L, 2L)));
        var output = Text.AsRecords(L(keep, "s", 5L, null, L("n", 1L), nested, true));
        Same(new Records
        {
            R("a", 1L), R("text", "s"), R("text", 5L), R("text", null),
            R("text", L("n", 1L)), R("k", R("z", L(1L, 2L))), R("text", true),
        }, output);
        Assert.Same(keep, output[0]);
        Assert.Same(nested, output[5]);
        // an array and a lazy sequence are lists too
        Same(new Records { R("a", 1L), R("text", "t") }, Text.AsRecords(new object?[] { R("a", 1L), "t" }));
        Same(new Records { R("text", "x"), R("text", "y") }, Text.AsRecords(Lazy("x", "y")));
        Same(new Records(), Text.AsRecords(new List<object?>()));
    }

    private static IEnumerable<object?> Lazy(params object?[] items)
    {
        foreach (var item in items) yield return item;
    }

    [Fact]
    public void AsRecordsDoesNotMutateAList()
    {
        var items = L(R("a", 1L), "s");
        var before = Tokens.PythonJson(items);
        Text.AsRecords(items);
        Assert.Equal(before, Tokens.PythonJson(items));
    }

    private sealed class Opaque;

    public static IEnumerable<object[]> NotLists() =>
    [
        [null!], [new byte[] { 1, 2 }], [5L], [5], [2.5], [true],
        [new HashSet<long> { 1, 2 }], [new Dictionary<string, string> { ["a"] = "b" }],
        [new Dictionary<int, int> { [1] = 2 }], [new DateTime(2026, 1, 1)], [new Opaque()],
    ];

    [Theory]
    [MemberData(nameof(NotLists))]
    public void AsRecordsNullBytesAndOtherTypesRaiseNotList(object? bad)
    {
        var e = Code<InputShapeException>(() => Text.AsRecords(bad), "input.not_list", "as_records");
        Assert.IsAssignableFrom<ContexelException>(e);
        Assert.IsAssignableFrom<ArgumentException>(e);
    }

    [Theory]
    [InlineData("")]
    [InlineData(null)]
    public void AsRecordsFieldMustBeANonEmptyString(string? bad) =>
        Code<ConfigException>(() => Text.AsRecords("x", bad!), "config.invalid_value",
                              "as_records", "field");

    [Fact]
    public void AsRecordsChecksTheShapeBeforeTheFieldName() =>
        Assert.Throws<InputShapeException>(() => Text.AsRecords(null, ""));

    // -------------------------------------------------------------- Split ----

    [Fact]
    public void SplitLinesKeepsSeparators()
    {
        var c = ChunksOf("one\ntwo\nthree", "lines");
        Assert.Equal(["one\n", "two\n", "three"], Texts(c));
        Assert.Equal([(0L, 4L), (4L, 8L), (8L, 13L)], Spans(c));
        Assert.Equal([0L, 1L, 2L], c.Select(x => Where(x).Index).ToArray());
        Assert.Equal(["a\n"], Texts(ChunksOf("a\n"))); // no empty remainder
        Assert.Equal(["\n"], Texts(ChunksOf("\n")));
        Assert.Equal(["\n", "\n"], Texts(ChunksOf("\n\n")));
    }

    [Fact]
    public void SplitCrlfIsOneBoundaryAndALoneCrIsNot()
    {
        Assert.Equal(["a\r\n", "b\rc\n", "d"], Texts(ChunksOf("a\r\nb\rc\nd")));
        Assert.Equal(["a\rb"], Texts(ChunksOf("a\rb")));
        Assert.Equal(["\r"], Texts(ChunksOf("\r")));
        Assert.Equal(["a\r\n"], Texts(ChunksOf("a\r\n")));
    }

    [Fact]
    public void SplitLinesIgnoresTheWiderSplitlinesSeparators()
    {
        string text = "a" + WideLineEnds + "b";
        Assert.Equal([text], Texts(ChunksOf(text, "lines")));
    }

    public static IEnumerable<object[]> ParagraphCases() =>
    [
        ["a\n\nb", new[] { "a\n\n", "b" }],
        ["a\n\n\nb", new[] { "a\n\n\n", "b" }],
        ["a\r\n\r\nb", new[] { "a\r\n\r\n", "b" }],
        ["a\n\r\nb", new[] { "a\n\r\n", "b" }],
        ["a\r\r\n\nb", new[] { "a\r\r\n\n", "b" }],
        ["a\nb", new[] { "a\nb" }],
        ["a\r\nb", new[] { "a\r\nb" }],
        ["a\n \nb", new[] { "a\n \nb" }],
        ["\n\nabc", new[] { "\n\n", "abc" }],
        ["abc\n\n", new[] { "abc\n\n" }],
        ["a\n\nb\n\nc", new[] { "a\n\n", "b\n\n", "c" }],
        ["\n\n\n\n", new[] { "\n\n\n\n" }],
    ];

    [Theory]
    [MemberData(nameof(ParagraphCases))]
    public void SplitParagraphsBoundaries(string text, string[] expected) =>
        Assert.Equal(expected, Texts(ChunksOf(text, "paragraphs")));

    [Fact]
    public void SplitSizeCountsCodePoints()
    {
        string text = "ab" + Astral + Astral + Astral + "c"; // 6 code points, 9 UTF-16 units
        var c = ChunksOf(text, "size", 2);
        Assert.Equal(["ab", Astral + Astral, Astral + "c"], Texts(c));
        Assert.Equal([(0L, 2L), (2L, 4L), (4L, 6L)], Spans(c));
        Assert.Equal(["abc", "def"], Texts(ChunksOf("abcdef", "size", 3)));
        Assert.Equal(["abc"], Texts(ChunksOf("abc", "size", 10)));
        Assert.Equal(["a", "b"], Texts(ChunksOf("ab", "size", 1)));
    }

    [Fact]
    public void SplitSizeNeverCutsASurrogatePairInHalf()
    {
        string text = Astral + Astral + Astral;
        foreach (var chunk in ChunksOf(text, "size", 1))
            Assert.Equal(Astral, chunk["text"]);
        Assert.Equal([(0L, 1L), (1L, 2L), (2L, 3L)], Spans(ChunksOf(text, "size", 1)));
    }

    public static IEnumerable<object?[]> EveryMode() =>
    [
        ["lines", null], ["paragraphs", null], ["size", 3],
    ];

    [Theory]
    [MemberData(nameof(EveryMode))]
    public void SplitEmptyTextYieldsNothingAndASeparatorFreeTextIsOneChunk(string by, int? size)
    {
        Same(new Records(), Text.Split([R("text", "", "id", 1L)], by: by, size: size));
        var output = Text.Split(
            [R("id", 0L, "text", "xyz"), R("id", 1L, "text", ""), R("id", 2L, "text", "q")],
            by: by, size: size);
        Assert.Equal(new object?[] { 0L, 2L }, output.Select(c => c["id"]).ToArray());
        Assert.Equal(["xyz", "q"], Texts(output));
        var only = ChunksOf("abc", by, size);
        Assert.Equal(["abc"], Texts(only));
        Assert.Equal([(0L, 3L)], Spans(only));
    }

    [Fact]
    public void SplitOffsetsIndexBackIntoTheText()
    {
        string text = "caf" + EAcute + "\r\nna\nve" + Astral + "\n\nz";
        var cps = CodePoints(text);
        foreach (var (by, size) in new (string, int?)[] { ("lines", null), ("paragraphs", null), ("size", 3) })
            foreach (var c in ChunksOf(text, by, size))
            {
                var (_, start, end) = Where(c);
                Assert.Equal(FromCodePoints(cps, (int)start, (int)end), c["text"]);
            }
    }

    [Fact]
    public void SplitChunksCarryTheParentFields()
    {
        var parent = R("id", 7L, "text", "a\nb", "meta", R("k", 1L), "tags", L("t"));
        var before = Tokens.PythonJson(parent);
        var output = Text.Split([parent]);
        Same(new Records
        {
            R("id", 7L, "text", "a\n", "meta", R("k", 1L), "tags", L("t"),
              "chunk", R("index", 0L, "start", 0L, "end", 2L)),
            R("id", 7L, "text", "b", "meta", R("k", 1L), "tags", L("t"),
              "chunk", R("index", 1L, "start", 2L, "end", 3L)),
        }, output);
        Assert.Equal(before, Tokens.PythonJson(parent)); // the input is never mutated
        Assert.Equal("a\nb", parent["text"]);
    }

    [Fact]
    public void SplitIndexRestartsForEachParentAndParentsKeepTheirOrder()
    {
        var output = Text.Split([R("id", "a", "text", "1\n2\n"), R("id", "x", "text", "x\ny\nz")]);
        Assert.Equal(
            [("a", 0L), ("a", 1L), ("x", 0L), ("x", 1L), ("x", 2L)],
            output.Select(c => ((string)c["id"]!, Where(c).Index)).ToArray());
    }

    [Fact]
    public void SplitPassesThroughARecordWithoutAStringField()
    {
        Records records =
        [
            R("id", 1L), R("id", 2L, "text", null), R("id", 3L, "text", 5L),
            R("id", 4L, "text", L("a\nb")), R("id", 5L, "text", "k\nl"),
        ];
        var output = Text.Split(records);
        for (int i = 0; i < 4; i++) Assert.Same(records[i], output[i]);
        Assert.Equal(["k\n", "l"], Texts(output.Skip(4).ToList()));
    }

    [Fact]
    public void SplitAPassthroughRecordMayAlreadyHaveTheIntoKey()
    {
        var record = R("text", 5L, "chunk", "x");
        var output = Text.Split([record]);
        Assert.Single(output);
        Assert.Same(record, output[0]);
    }

    [Fact]
    public void SplitExistingIntoKeyRaisesFieldConflict()
    {
        var e = Code<InputShapeException>(
            () => Text.Split([R("text", "ok\nok"), R("text", "a\nb", "chunk", 1L)]),
            "input.field_conflict", "split", "into");
        Assert.Contains("record 1", e.Message);
        // a different into name is the way out
        var output = Text.Split([R("text", "a\nb", "chunk", 1L)], into: "part");
        Assert.Equal(new object?[] { 1L, 1L }, output.Select(c => c["chunk"]).ToArray());
        Assert.Equal(0L, ((Rec)output[0]["part"]!)["index"]);
        // an empty text yields no chunks, but the clash is still refused
        Assert.Throws<InputShapeException>(() => Text.Split([R("text", "", "chunk", 1L)]));
        // into equal to field clashes with the very text being split
        Assert.Throws<InputShapeException>(() => Text.Split([R("text", "a")], into: "text"));
    }

    [Theory]
    [InlineData(null)]
    [InlineData(0)]
    [InlineData(-1)]
    public void SplitBySizeRequiresAPositiveIntegerSize(int? size) =>
        Code<ConfigException>(() => Text.Split([R("text", "abc")], by: "size", size: size),
                              "config.invalid_value", "split", "size");

    [Fact]
    public void SplitSizeTypesCSharpCannotSpellAreRefusedByTheUntypedEntry()
    {
        // the typed Split takes int?, so a bool, a fraction or a string cannot be
        // passed to it; the vector runner reaches them through SplitCore
        foreach (object? bad in new object?[] { null, 0L, -1L, true, 2.5, "3", 2.0 })
            Code<ConfigException>(
                () => Text.SplitCore([R("text", "abc")], "text", "size", bad, "chunk"),
                "config.invalid_value", "split", "size");
        // a long size beyond int is a valid size: it just holds the whole text
        Assert.Equal(["abc"], Texts(Text.SplitCore([R("text", "abc")], "text", "size",
                                                   long.MaxValue, "chunk")));
        Assert.Equal(["ab", "c"], Texts(Text.SplitCore([R("text", "abc")], "text", "size",
                                                       2L, "chunk")));
    }

    [Theory]
    [InlineData("lines", 3)]
    [InlineData("paragraphs", 3)]
    [InlineData("lines", 0)]
    public void SplitSizeWithAnotherModeIsContradictory(string by, int size) =>
        Code<ConfigException>(() => Text.Split([R("text", "abc")], by: by, size: size),
                              "config.contradictory", "split", "size");

    [Fact]
    public void SplitSizeWithAnotherModeIsContradictoryForAnyUntypedValue() =>
        Code<ConfigException>(
            () => Text.SplitCore([R("text", "abc")], "text", "lines", 2.5, "chunk"),
            "config.contradictory", "split", "size");

    [Theory]
    [InlineData("words")]
    [InlineData("")]
    [InlineData(null)]
    public void SplitUnknownByRaises(string? by) =>
        Code<ConfigException>(() => Text.Split([R("text", "abc")], by: by!),
                              "config.invalid_value", "split", "by");

    [Fact]
    public void SplitFieldAndIntoMustBeStrings()
    {
        Code<ConfigException>(() => Text.Split([R("text", "abc")], field: null!),
                              "config.invalid_value", "split", "field");
        Code<ConfigException>(() => Text.Split([R("text", "abc")], into: null!),
                              "config.invalid_value", "split", "into");
    }

    [Fact]
    public void SplitValidatesFieldThenByThenIntoThenSize()
    {
        // each pair is broken in two ways; the earlier one in the order is reported
        Code<ConfigException>(() => Text.Split([R("text", "a")], field: null!, by: "bogus"),
                              "config.invalid_value", "split", "field");
        Code<ConfigException>(() => Text.Split([R("text", "a")], by: "bogus", into: null!),
                              "config.invalid_value", "split", "by");
        Code<ConfigException>(() => Text.Split([R("text", "a")], by: "size", into: null!, size: 0),
                              "config.invalid_value", "split", "into");
    }

    [Fact]
    public void SplitChecksItsInputInEveryMode()
    {
        Assert.False(Strict.IsActive);
        Code<InputShapeException>(() => Text.Split(null!), "input.not_list", "split");
        var e = Code<InputShapeException>(() => Text.Split([R("text", "a"), null!]),
                                          "input.not_mapping", "split");
        Assert.Contains("item 1", e.Message);
    }

    [Fact]
    public void SplitChecksTheShapeBeforeTheConfiguration() =>
        Assert.Throws<InputShapeException>(() => Text.Split(null!, by: "bogus"));

    [Fact]
    public void SplitUnderATraceReportsANonListWithTheTypedError()
    {
        using var t = Trace.Begin();
        Assert.Throws<InputShapeException>(() => Text.Split(null!));
        Assert.Empty(t.Entries); // nothing was run, so nothing is recorded
    }

    [Fact]
    public void SplitDoesNotMutateItsInputForAnyMode()
    {
        Records records = [R("text", "a\n\nb\nc", "meta", R("k", L(1L)))];
        var before = Tokens.PythonJson(records);
        Text.Split(records);
        Text.Split(records, by: "paragraphs");
        Text.Split(records, by: "size", size: 2);
        Assert.Equal(before, Tokens.PythonJson(records));
    }

    [Fact]
    public void SplitIsTracedAndAnExpansionIsNotADrop()
    {
        Records records =
        [
            R("id", "a", "text", "1\n2\n3"), R("id", "b", "text", ""),
            R("id", "c", "text", "z"), R("text", "no id\nhere"),
        ];
        using var t = Trace.Begin("id");
        var output = Text.Split(records);
        var entry = t.Entries[0];
        Assert.Equal(("split", 4, output.Count), (entry.Stage, entry.InCount, entry.OutCount));
        Assert.Equal(3 + 1 + 2, output.Count); // a: 3 chunks, b: none, c: 1, no-id: 2
        // b vanished (documented) and is reported; a and c were expanded or kept
        Assert.Equal(new List<object?> { "b" }, entry.DroppedIds);
    }

    [Fact]
    public void TracedKeepsIdsMakesAttributionExactAndTheDefaultIsUnchanged()
    {
        // a stage that expands an id-less record into two and drops the record "b"
        Records ExpandAndDrop() => [R("t", "x"), R("t", "y"), R("id", "a")];
        Records records = [R("id", "a"), R("id", "b"), R("t", "one")];
        using var t = Trace.Begin("id");
        Trace.Traced("exact", records, ExpandAndDrop, keepsIds: true);
        Trace.Traced("default", records, ExpandAndDrop);
        // exact: "b" has no survivor, so it is reported; the default rule explains
        // it away as an id lost by one of the id-less records the stage added
        Assert.Equal(new List<object?> { "b" }, t.Entries[0].DroppedIds);
        Assert.Empty(t.Entries[1].DroppedIds);
    }

    [Fact]
    public void SplitStagePoliciesArePartOfTheFingerprint()
    {
        static string Fp(string by, int? size) => new Pipeline(
            new Stage("split", r => Text.Split(r, by: by, size: size),
                      new Rec { ["by"] = by, ["size"] = size.HasValue ? (long)size.Value : null }))
            .Fingerprint;

        Assert.Equal(Fp("size", 3), Fp("size", 3));
        Assert.NotEqual(Fp("size", 3), Fp("size", 4));
        Assert.NotEqual(Fp("lines", null), Fp("paragraphs", null));
    }

    [Fact]
    public void SplitRunsInAStrictPipelineAndStrictChangesNothing()
    {
        const string text = "a\nb\n\nc";
        Stage[] stages =
        [
            new Stage("split", r => Text.Split(r, by: "paragraphs")),
            new Stage("dedupe", r => Stages.Dedupe(r, "text")),
        ];
        Same(new Pipeline(stages, strict: true).Run(Text.AsRecords(text)),
             new Pipeline(stages).Run(Text.AsRecords(text)));
    }

    [Fact]
    public void AnOffRampInsideAStrictPipelineNamesTheStage()
    {
        // Join returns a string, so it belongs OUTSIDE the pipeline (docs); a stage
        // that hands the next one anything but a list is named by strict mode
        var pipe = new Pipeline(
            [
                new Stage("split", r => Text.Split(r)),
                new Stage("join", r => { Text.Join(r); return null!; }),
            ], strict: true);
        Code<InputShapeException>(() => pipe.Run(Text.AsRecords("a\nb")), "input.not_list", "join");
    }

    [Fact]
    public void CheckedAlwaysValidatesWithoutStrictMode()
    {
        Assert.False(Strict.IsActive);
        Code<InputShapeException>(
            () => Strict.CheckRecords<Rec>(null, "always", mapping: true, always: true),
            "input.not_list", "always");
        var e = Code<InputShapeException>(
            () => Strict.CheckRecords([R("a", 1L), null!], "always", mapping: true, always: true),
            "input.not_mapping", "always");
        Assert.Contains("item 1", e.Message);
        // a stage that never indexes an item does not need one
        Strict.CheckRecords([R("a", 1L), null!], "always", mapping: false, always: true);
        // without always and without strict mode nothing is checked
        Strict.CheckRecords<Rec>(null, "lenient", mapping: true);
        Strict.CheckRecords(new Records { null! }, "lenient", mapping: true);
        Strict.CheckRecords([R("a", 1L)], "always", mapping: true, always: true);
    }

    // --------------------------------------------------------------- Join ----

    [Fact]
    public void JoinSkipsMissingKeepsStringsAndSerializesTheRest()
    {
        Records records =
        [
            R("text", "a"), R("other", 1L), R("text", R("k", 1L)), R("text", L(1L, "x")),
            R("text", null), R("text", true), R("text", 2.5),
        ];
        Assert.Equal("a|{\"k\": 1}|[1, \"x\"]|null|true|2.5", Text.Join(records, sep: "|"));
        Assert.Equal("a{\"k\": 1}[1, \"x\"]nulltrue2.5", Text.Join(records));
    }

    [Fact]
    public void JoinFieldSepAndEmpty()
    {
        Assert.Equal("x\ny", Text.Join([R("body", "x"), R("text", "no"), R("body", "y")], "body", "\n"));
        Assert.Equal("", Text.Join([]));
        Assert.Equal("", Text.Join([R("other", 1L)]));
        Assert.Equal("-", Text.Join([R("text", ""), R("text", "")], sep: "-"));
    }

    [Fact]
    public void JoinRendersNonStringsWithTheActiveSerializer()
    {
        var output = Tokens.Scoped(
            new Tokens.Scope(Serializer: v => v is Rec ? "<dict>" : "<other>"),
            () => Text.Join([R("text", R("k", 1L)), R("text", "s"), R("text", 7L)], sep: " "));
        Assert.Equal("<dict> s <other>", output);
    }

    [Fact]
    public void JoinChecksItsInputInEveryMode()
    {
        Assert.False(Strict.IsActive);
        Code<InputShapeException>(() => Text.Join(null!), "input.not_list", "join");
        Code<InputShapeException>(() => Text.Join([R("text", "a"), null!]), "input.not_mapping", "join");
        Assert.Equal("ab", Text.Join([R("text", "a"), R("text", "b")]));
    }

    [Fact]
    public void JoinChecksTheShapeBeforeTheConfiguration() =>
        Assert.Throws<InputShapeException>(() => Text.Join(null!, field: null!));

    [Fact]
    public void JoinFieldAndSepMustBeStrings()
    {
        Code<ConfigException>(() => Text.Join([R("text", "a")], field: null!),
                              "config.invalid_value", "join", "field");
        Code<ConfigException>(() => Text.Join([R("text", "a")], sep: null!),
                              "config.invalid_value", "join", "sep");
    }

    [Fact]
    public void JoinRoundTripsSplitForEveryMode()
    {
        string text = "line one\r\nline two\n\n\npara " + Astral + "\rlone cr\n" + EAcute;
        foreach (var (by, size) in new (string, int?)[] { ("lines", null), ("paragraphs", null), ("size", 5) })
            Assert.Equal(text, Text.Join(ChunksOf(text, by, size)));
    }

    // ------------------------------------------ properties (AC 11, 12) ----

    /// <summary>A tiny linear congruential generator (Knuth's MMIX constants).
    /// Deterministic on every runtime: System.Random's sequence is not part of
    /// its contract, ours never changes.</summary>
    private sealed class Lcg(ulong seed)
    {
        private ulong _state = seed;

        private uint Next()
        {
            _state = unchecked(_state * 6364136223846793005UL + 1442695040888963407UL);
            return (uint)(_state >> 33);
        }

        /// <summary>An integer in [lo, hi].</summary>
        public int Between(int lo, int hi) => lo + (int)(Next() % (uint)(hi - lo + 1));
    }

    private const long DefaultSeed = 20261119;
    private const int DefaultCases = 200;

    private static long BaseSeed() =>
        long.TryParse(Environment.GetEnvironmentVariable("CONTEXEL_PROP_SEED"), out var s) ? s : DefaultSeed;

    private static int CaseCount() =>
        int.TryParse(Environment.GetEnvironmentVariable("CONTEXEL_PROP_CASES"), out var n) ? n : DefaultCases;

    private static IEnumerable<long> Seeds()
    {
        long b = BaseSeed();
        for (int i = 0; i < CaseCount(); i++) yield return b + i;
    }

    /// <summary>The run's seeds, then the default ones: whether a check CAN fail
    /// must not depend on how small a reproduction run is.</summary>
    private static IEnumerable<long> CanarySeeds()
    {
        foreach (var s in Seeds()) yield return s;
        for (int i = 0; i < DefaultCases; i++) yield return DefaultSeed + i;
    }

    private static readonly string[] Alphabet =
        ["a", "b", " ", "\n", "\n", "\r", "\r\n", "\r\n", "\n\n", Astral, EAcute, "x"];

    private static string RandomText(Lcg rng)
    {
        int pieces = rng.Between(0, 40);
        return string.Concat(Enumerable.Range(0, pieces).Select(_ => Alphabet[rng.Between(0, Alphabet.Length - 1)]));
    }

    /// <summary>A promise of Split that did not hold (the check itself failing,
    /// as opposed to the test harness).</summary>
    private sealed class CheckFailed(string message) : Exception(message);

    private static void Need(bool ok, string message)
    {
        if (!ok) throw new CheckFailed(message);
    }

    private static int Count(string s, char ch) => s.Count(x => x == ch);

    private static readonly Regex ParagraphRun = new(@"(?:\r?\n){2,}", RegexOptions.CultureInvariant);

    /// <summary>Every promise of Split about one text; throws CheckFailed.</summary>
    private static void CheckSplit(string text, string by, int? size, Records chunks)
    {
        var all = CodePoints(text);
        Need(string.Concat(chunks.Select(c => (string)c["text"]!)) == text, "chunks do not rebuild the text");
        Need(chunks.Select(c => Where(c).Index).SequenceEqual(Enumerable.Range(0, chunks.Count).Select(i => (long)i)),
             "bad index");
        long position = 0;
        foreach (var c in chunks)
        {
            var (_, start, end) = Where(c);
            Need(start == position && end > start, "offsets are not contiguous");
            Need(end <= all.Length && FromCodePoints(all, (int)start, (int)end) == (string)c["text"]!,
                 "offsets do not index the text");
            position = end;
        }
        Need(position == all.Length, "offsets do not cover the text");
        var body = chunks.Take(Math.Max(0, chunks.Count - 1)).ToList();
        if (by == "lines")
        {
            foreach (var c in body)
            {
                var t = (string)c["text"]!;
                Need(t.EndsWith('\n') && Count(t, '\n') == 1, "line boundary");
            }
            if (chunks.Count > 0) Need(Count((string)chunks[^1]["text"]!, '\n') <= 1, "line boundary");
        }
        else if (by == "paragraphs")
        {
            foreach (var c in chunks)
            {
                var m = ParagraphRun.Match((string)c["text"]!);
                Need(!m.Success || m.Index + m.Length == ((string)c["text"]!).Length, "paragraph boundary");
            }
            foreach (var c in body) Need(ParagraphRun.IsMatch((string)c["text"]!), "paragraph boundary");
        }
        else
        {
            foreach (var c in body) Need(CodePoints((string)c["text"]!).Length == size, "size boundary");
            if (chunks.Count > 0)
            {
                int last = CodePoints((string)chunks[^1]["text"]!).Length;
                Need(last >= 1 && last <= size, "size boundary");
            }
        }
    }

    [Fact]
    public void SplitIsLosslessAndItsOffsetsIndexBackForRandomTexts()
    {
        foreach (long seed in Seeds())
        {
            var rng = new Lcg((ulong)seed);
            string text = RandomText(rng);
            int size = rng.Between(1, 6);
            foreach (var (by, sz) in new (string, int?)[] { ("lines", null), ("paragraphs", null), ("size", size) })
            {
                try { CheckSplit(text, by, sz, ChunksOf(text, by, sz)); }
                catch (CheckFailed e) // name the seed, whatever failed
                {
                    throw new Xunit.Sdk.XunitException(
                        $"seed {seed} by={by} text={PyCompat.PyRepr(text)}: {e.Message}");
                }
            }
        }
    }

    private static Rec WithChunk(Rec c, long start, long end)
    {
        var chunk = new Rec((Rec)c["chunk"]!) { ["start"] = start, ["end"] = end };
        return new Rec(c) { ["chunk"] = chunk };
    }

    private static string WithoutLastCodePoint(string s) =>
        s.Length >= 2 && char.IsSurrogatePair(s, s.Length - 2) ? s[..^2] : s[..^1];

    private static readonly Dictionary<string, Func<Records, Records>> Corruptions = new()
    {
        ["drop_last_char"] = chunks => chunks.Select((c, i) => i == chunks.Count - 1
            ? new Rec(c) { ["text"] = WithoutLastCodePoint((string)c["text"]!) } : c).ToList(),
        ["shift_offsets"] = chunks => chunks.Select(c =>
            WithChunk(c, Where(c).Start + 1, Where(c).End + 1)).ToList(),
        ["reverse"] = chunks => Enumerable.Reverse(chunks).ToList(),
        ["cut_one_too_soon"] = chunks => chunks.Count == 0 ? chunks
            : chunks.Select((c, i) => i == 0
                ? new Rec(WithChunk(c, Where(c).Start, Where(c).End - 1))
                    { ["text"] = WithoutLastCodePoint((string)c["text"]!) }
                : c).ToList(),
    };

    [Theory]
    [InlineData("drop_last_char")]
    [InlineData("shift_offsets")]
    [InlineData("reverse")]
    [InlineData("cut_one_too_soon")]
    public void TheSplitCheckRejectsABrokenSplit(string corruption)
    {
        int caught = 0;
        foreach (long seed in CanarySeeds())
        {
            string text = RandomText(new Lcg((ulong)seed));
            if (CodePoints(text).Length < 4) continue;
            foreach (var (by, size) in new (string, int?)[] { ("lines", null), ("paragraphs", null), ("size", 2) })
            {
                var chunks = ChunksOf(text, by, size);
                CheckSplit(text, by, size, chunks); // the real split passes
                var broken = Corruptions[corruption](chunks);
                if (Tokens.PythonJson(broken) == Tokens.PythonJson(chunks))
                    continue; // nothing to corrupt on this text
                Assert.Throws<CheckFailed>(() => CheckSplit(text, by, size, broken));
                caught++;
            }
            if (caught > 0) return;
        }
        throw new Xunit.Sdk.XunitException("no seed produced a text the corruption could change");
    }

    [Fact]
    public void TheGeneratorIsDeterministic()
    {
        // pinned: a change of the sequence would silently change every property case
        var rng = new Lcg(20261119);
        Assert.Equal(new[] { 2, 6, 4, 6, 9, 8, 4, 6 }, Enumerable.Range(0, 8).Select(_ => rng.Between(0, 9)).ToArray());
        Assert.Equal(RandomText(new Lcg(1)), RandomText(new Lcg(1)));
    }

    // ------------------------------------------------- scale and adversarial ----

    private static void Within(TimeSpan limit, Action work, string what)
    {
        var watch = Stopwatch.StartNew();
        work();
        Assert.True(watch.Elapsed < limit, $"{what} took {watch.Elapsed.TotalMilliseconds:F0} ms");
    }

    [Fact]
    public void SplitCompletesOnAMillionCharactersAndRoundTrips()
    {
        string lines = string.Concat(Enumerable.Repeat("abcdefghi\n", 100_000)); // exactly 1,000,000
        Assert.Equal(1_000_000, lines.Length);
        Records c = [];
        Within(TimeSpan.FromSeconds(2), () => c = ChunksOf(lines, "lines"), "lines");
        Assert.Equal(100_000, c.Count);
        Assert.Equal((999_990L, 1_000_000L), Spans(c)[^1]);
        Assert.Equal(lines, Text.Join(c));

        string paragraphs = string.Concat(Enumerable.Repeat("para\n\n", 166_666)) + "tail";
        Records p = [];
        Within(TimeSpan.FromSeconds(2), () => p = ChunksOf(paragraphs, "paragraphs"), "paragraphs");
        Assert.Equal(166_667, p.Count);
        Assert.Equal(paragraphs, Text.Join(p));

        Records sized = [];
        Within(TimeSpan.FromSeconds(2), () => sized = ChunksOf(lines, "size", 1000), "size");
        Assert.Equal(1000, sized.Count);
        Assert.Equal(lines, Text.Join(sized));
        Assert.Equal((999_000L, 1_000_000L), Spans(sized)[^1]);
    }

    [Fact]
    public void SplitCountsCodePointsOnAMillionAstralCharacters()
    {
        // 500,000 astral code points = 1,000,000 UTF-16 units: offsets must be
        // code points, and the cut must stay linear
        string text = string.Concat(Enumerable.Repeat(Astral, 500_000));
        Records c = [];
        Within(TimeSpan.FromSeconds(2), () => c = ChunksOf(text, "size", 1000), "astral size");
        Assert.Equal(500, c.Count);
        Assert.Equal((499_000L, 500_000L), Spans(c)[^1]);
        Assert.Equal(text, Text.Join(c));
    }

    [Theory]
    [InlineData("\r")]
    [InlineData("\r\n")]
    [InlineData("\n\r")]
    [InlineData("\n")]
    [InlineData("a")]
    public void SplitStaysLinearOnAdversarialSeparators(string unit)
    {
        // a million characters of separators that almost match: must just complete
        string text = string.Concat(Enumerable.Repeat(unit, 1_000_000 / unit.Length));
        foreach (var by in new[] { "lines", "paragraphs", "size" })
        {
            Records chunks = [];
            Within(TimeSpan.FromSeconds(2),
                   () => chunks = by == "size" ? ChunksOf(text, by, 7) : ChunksOf(text, by),
                   $"{PyCompat.PyRepr(unit)} by {by}");
            Assert.Equal(text, Text.Join(chunks));
        }
    }
}
```

- [ ] **Step 3.2: Run: the project does not compile**

```bash
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
```

Expected:

```text
TextTests.cs(104,22): error CS0103: The name 'Text' does not exist in the current context
...   (the same error at every use of `Text`: the test project does not compile)
```

`Text` does not exist yet, so the test project fails to compile (a compile error is this language's red).

- [ ] **Step 3.3: Add the `always` and `keepsIds` options**

In `csharp/Contexel/Strict.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel/Strict.cs -->
```csharp
    /// <summary>In strict mode only: records must be non-null and, when
    /// <paramref name="mapping"/>, every item non-null. Called BEFORE
    /// <c>Trace.Traced</c>, which reads <c>records.Count</c> first.</summary>
    internal static void CheckRecords<T>(List<T>? records, string stage, bool mapping)
    {
        if (!Flag.Value) return;
        if (records is null)
            throw new InputShapeException("input.not_list",
```
with:
<!-- OP replace-new -->
```csharp
    /// <summary>In strict mode only: records must be non-null and, when
    /// <paramref name="mapping"/>, every item non-null. Called BEFORE
    /// <c>Trace.Traced</c>, which reads <c>records.Count</c> first.
    /// <paramref name="always"/> validates in every mode, not only in strict
    /// mode: the payload stages (<see cref="Text"/>) are new, so they have no
    /// lenient behavior to stay compatible with.</summary>
    internal static void CheckRecords<T>(List<T>? records, string stage, bool mapping,
                                         bool always = false)
    {
        if (!always && !Flag.Value) return;
        if (records is null)
            throw new InputShapeException("input.not_list",
```

In `csharp/Contexel/Trace.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel/Trace.cs -->
```csharp
    /// <summary>Wrap a stage body so an active trace records its effect
    /// (including dropped ids, with the unidentified-survivor wildcard).</summary>
    internal static Records Traced(string name, Records records, Func<Records> fn)
    {
        var tr = Current;
```
with:
<!-- OP replace-new -->
```csharp
    /// <summary>Wrap a stage body so an active trace records its effect
    /// (including dropped ids, with the unidentified-survivor wildcard).
    /// <paramref name="keepsIds"/> declares that the stage never removes the id
    /// field from a record it keeps (it may still emit several records for one
    /// input, as <see cref="Text.Split(Records, string, string, int?, string)"/>
    /// does): attribution is then exact, every input id with no surviving record
    /// is reported dropped, and the id-less-record allowance is not applied.</summary>
    internal static Records Traced(string name, Records records, Func<Records> fn,
                                   bool keepsIds = false)
    {
        var tr = Current;
```

In `csharp/Contexel/Trace.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel/Trace.cs -->
```csharp
            // unmatched ids are explained away; every other one is reported
            // dropped (the first `lost` in input order are the ones absorbed).
            int lost = Math.Max(0, unidentifiedOut - unidentifiedIn);
            dropped.AddRange(unmatched.Skip(lost));
        }
```
with:
<!-- OP replace-new -->
```csharp
            // unmatched ids are explained away; every other one is reported
            // dropped (the first `lost` in input order are the ones absorbed).
            int lost = keepsIds ? 0 : Math.Max(0, unidentifiedOut - unidentifiedIn);
            dropped.AddRange(unmatched.Skip(lost));
        }
```

- [ ] **Step 3.4: Add the three stages**

Create `csharp/Contexel/Text.cs` with exactly this content (it ends with one newline):
<!-- OP create path=csharp/Contexel/Text.cs -->
```csharp
using System.Collections;
using System.Text;

namespace Contexel;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>
/// Payload stages: carry text through the record stages and back (ADR-005).
/// Every other stage takes a list of mappings. A log, a web page or a plain
/// string is none of that, so three small stages convert at the edges:
/// <code>
/// var chunks = Text.Split(Text.AsRecords(log), by: "lines");   // text -> records
/// // ... Dedupe, Rescore, Rank, TrimToBudget
/// string text = Text.Join(chunks);                              // records -> text
/// </code>
/// <see cref="AsRecords"/> and <see cref="Join"/> are the entry and exit
/// points: call them outside a <see cref="Pipeline"/> (like
/// <see cref="Stages.Merge"/>), because a pipeline hands every stage a list.
/// <see cref="Split"/> is an ordinary traced stage and belongs in a pipeline.
/// <para>Unlike the original stages, these validate the SHAPE of their input in
/// every mode, not only in strict mode: they are new, so there is no lenient
/// behavior to stay compatible with.</para>
/// <para>Boundaries are explicit and identical in Python, TypeScript and C#: a
/// line ends after <c>"\n"</c> only (so <c>"\r\n"</c> is one boundary and a lone
/// <c>"\r"</c> is none), a paragraph ends after a run of two or more newlines
/// (<c>(?:\r?\n){2,}</c>), and sizes and offsets count code points: a surrogate
/// pair is ONE, never two.</para>
/// </summary>
public static class Text
{
    private static string Kind(object? value) => PyCompat.PyTypeName(value) switch
    {
        "NoneType" => "null",
        var other => other,
    };

    private static bool Implements(object value, Type openGeneric) =>
        value.GetType().GetInterfaces().Any(i =>
            i.IsGenericType && i.GetGenericTypeDefinition() == openGeneric);

    /// <summary>Turn a payload into a list of records, the shape every stage
    /// takes. A string becomes <c>[{field: x}]</c>; a
    /// <c>Dictionary&lt;string, object?&gt;</c> becomes <c>[x]</c> (the same
    /// object, not a copy); any other list (a non-string, non-<c>byte[]</c>,
    /// non-dictionary, non-set <see cref="IEnumerable"/>) keeps each mapping item
    /// and wraps every other item, null and nested lists included, as
    /// <c>{field: item}</c>. null, bytes and every other type throw
    /// <see cref="InputShapeException"/> (<c>input.not_list</c>). <c>field</c>
    /// must be a non-empty string (<see cref="ConfigException"/>,
    /// <c>config.invalid_value</c>), checked after the shape. Not traced: it is
    /// an entry point.</summary>
    public static Records AsRecords(object? x, string field = "text")
    {
        bool isList = x is IEnumerable && x is not (string or byte[] or IDictionary)
            && !Implements(x, typeof(ISet<>)) && !Implements(x, typeof(IReadOnlySet<>))
            && !Implements(x, typeof(IReadOnlyDictionary<,>));
        if (x is not (string or Rec) && !isList)
            throw new InputShapeException("input.not_list",
                $"as_records: expected a string, a mapping or a list, got {Kind(x)}",
                "as_records");
        Check.Str(field, "as_records", "field");
        if (field.Length == 0)
            throw Check.InvalidValue("as_records", "field", "field must not be empty");
        if (x is string text) return [new Rec { [field] = text }];
        if (x is Rec mapping) return [mapping];
        var output = new Records();
        foreach (var item in (IEnumerable)x!)
            output.Add(item is Rec r ? r : new Rec { [field] = item });
        return output;
    }

    /// <summary>The UTF-16 end offset (exclusive) of every chunk of
    /// <paramref name="text"/>. One linear pass per mode: no substring search
    /// from every position and no backtracking.</summary>
    private static List<int> Ends(string text, string by, int size)
    {
        int n = text.Length;
        var ends = new List<int>();
        if (by == "size")
        {
            for (int i = 0; i < n;)
            {
                int j = i;
                for (int taken = 0; taken < size && j < n; taken++)
                    j += char.IsSurrogatePair(text, j) ? 2 : 1; // one code point
                ends.Add(j);
                i = j;
            }
            return ends;
        }
        int last = 0;
        if (by == "lines")
        {
            for (int pos = text.IndexOf('\n'); pos != -1; pos = text.IndexOf('\n', last))
            {
                last = pos + 1;
                ends.Add(last);
            }
        }
        else
        {
            // (?:\r?\n){2,}, leftmost and greedy. A newline unit is "\n" or "\r\n"
            // and cannot be read two ways, so one left-to-right scan is exact: a
            // run of two or more units ends a chunk, a run of one is skipped.
            for (int i = 0; i < n;)
            {
                int j = i, units = 0;
                while (j < n)
                {
                    if (text[j] == '\n') j++;
                    else if (text[j] == '\r' && j + 1 < n && text[j + 1] == '\n') j += 2;
                    else break;
                    units++;
                }
                if (units >= 2)
                {
                    last = j;
                    ends.Add(last);
                }
                i = units == 0 ? i + 1 : j;
            }
        }
        if (last < n) ends.Add(n); // the remainder after the last boundary is a chunk
        return ends;
    }

    /// <summary>Code points in <c>text[start..end]</c>: UTF-16 units minus the
    /// pairs that count once.</summary>
    private static int CodePoints(string text, int start, int end)
    {
        int count = end - start;
        for (int i = start; i < end - 1; i++)
            if (char.IsSurrogatePair(text, i)) { count--; i++; }
        return count;
    }

    /// <summary>Cut the text in <c>field</c> into chunk records.
    /// <c>by: "lines"</c> ends a chunk after each <c>"\n"</c>;
    /// <c>by: "paragraphs"</c> after each run of two or more newlines;
    /// <c>by: "size"</c> every <c>size</c> code points (<c>size</c> must then be
    /// a positive integer). Every chunk keeps its trailing separator, so joining
    /// the chunks with <c>""</c> reproduces the text exactly.
    /// <para>Each chunk is <c>{...parent, [field]: chunk, [into]: {index, start,
    /// end}}</c>: <c>index</c> counts from 0 within its parent and <c>[start,
    /// end)</c> are code-point offsets into the original text. A record whose
    /// <c>field</c> is not a string passes through untouched (the same object);
    /// a string that is empty yields no chunks (that record disappears). A
    /// string-valued record that already has the <c>into</c> key throws
    /// <see cref="InputShapeException"/> (<c>input.field_conflict</c>).</para>
    /// <para><c>by</c> must be lines, paragraphs or size and <c>size</c> must be
    /// omitted for the first two (<see cref="ConfigException"/>:
    /// <c>config.invalid_value</c> and <c>config.contradictory</c>). Items must be
    /// mappings: this stage checks its input in every mode.</para>
    /// <para>Rank reorders chunks by score; to restore reading order before
    /// <see cref="Join"/>, rank again by <c>chunk.start</c> ascending.</para></summary>
    public static Records Split(Records records, string field = "text", string by = "lines",
                                int? size = null, string into = "chunk") =>
        SplitCore(records, field, by, size, into);

    /// <summary>The body of <see cref="Split"/> with <c>size</c> as a boxed value,
    /// so a value C# cannot spell as <c>int?</c> (a bool, a fraction, a string:
    /// the shared vectors carry them) reaches the same validation as in the
    /// other languages. Any whole number that is not a bool is a size; a
    /// <c>long</c> beyond <c>int.MaxValue</c> simply holds the whole text.</summary>
    internal static Records SplitCore(Records records, string field, string by, object? size,
                                      string into)
    {
        // shape first (always, strict mode or not), then the configuration
        Strict.CheckRecords(records, "split", mapping: true, always: true);
        return Trace.Traced("split", records, () =>
        {
            Check.Str(field, "split", "field");
            Check.Choice(by, "split", "by", "lines", "paragraphs", "size");
            Check.Str(into, "split", "into");
            int cut = 0;
            if (by == "size")
            {
                if (size is bool || size is not (long or int) || Convert.ToInt64(size) < 1)
                    throw Check.InvalidValue("split", "size",
                        $"size must be a positive integer when by='size', got {PyCompat.PyRepr(size)}");
                cut = (int)Math.Min(Convert.ToInt64(size), int.MaxValue);
            }
            else if (size is not null)
                throw new ConfigException("config.contradictory",
                    $"split: size={PyCompat.PyRepr(size)} only applies to by='size', " +
                    $"got by={PyCompat.PyRepr(by)}", "split", "size");
            var output = new Records();
            for (int i = 0; i < records.Count; i++)
            {
                var r = records[i];
                // only the record's own field counts, and only a string is cut
                if (!r.TryGetValue(field, out var value) || value is not string text)
                {
                    output.Add(r);
                    continue;
                }
                if (r.ContainsKey(into))
                    throw new InputShapeException("input.field_conflict",
                        $"split: record {i} already has a {PyCompat.PyRepr(into)} field; " +
                        "pass a different into", "split", "into");
                int start = 0;
                long position = 0; // code-point offset of `start`
                int index = 0;
                foreach (int end in Ends(text, by, cut))
                {
                    long length = CodePoints(text, start, end);
                    output.Add(new Rec(r)
                    {
                        [field] = text[start..end],
                        [into] = new Rec
                        {
                            ["index"] = (long)index,
                            ["start"] = position,
                            ["end"] = position + length,
                        },
                    });
                    position += length;
                    start = end;
                    index++;
                }
            }
            return output;
        }, keepsIds: true);
    }

    /// <summary>Join the <c>field</c> of every record into one string. A record
    /// without <c>field</c> is skipped; a string value is used as it is; any
    /// other value (null included) is rendered with
    /// <see cref="Tokens.Serialize"/>, the text the token budget priced. The
    /// parts are joined with <c>sep</c>. Items must be mappings (checked in every
    /// mode). Not traced: it is an exit point.</summary>
    public static string Join(Records records, string field = "text", string sep = "")
    {
        Strict.CheckRecords(records, "join", mapping: true, always: true);
        Check.Str(field, "join", "field");
        Check.Str(sep, "join", "sep");
        var output = new StringBuilder();
        bool first = true;
        foreach (var r in records)
        {
            if (!r.TryGetValue(field, out var value)) continue;
            if (!first) output.Append(sep);
            first = false;
            output.Append(value is string s ? s : Tokens.Serialize(value));
        }
        return output.ToString();
    }
}
```

- [ ] **Step 3.5: Run all C# tests**

```bash
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
```

Expected:

```text
Passed!  - Failed:     0, Passed:   402, Skipped:     0, Total:   402   (0 warnings)
```

0 warnings, and every earlier test passes unchanged.

- [ ] **Step 3.6: Commit**

```bash
git add csharp/Contexel.Tests/TextTests.cs csharp/Contexel/Text.cs csharp/Contexel/Strict.cs csharp/Contexel/Trace.cs
git commit -m "feat(cs): add Text.AsRecords, Text.Split and Text.Join"
```


### Task 4: Shared vectors for the payload stages, replayed in all three languages

**Acceptance criteria:** AC 10 to 15 (the cross-language contract; AC 15 is the end-to-end case)

**Files:**
- Modify: `parity/parity_cases.py`, `tests/test_parity_cases.py`; regenerate `parity/vectors.json`
- Modify: `ts/test/runner.ts`, `ts/test/runner.test.ts`, `csharp/Contexel.Tests/CaseTests.cs`, `csharp/Contexel.Tests/RunnerTests.cs`

**Interfaces:**
- Consumes: the three ports of Tasks 1 to 3.
- Produces: 44 new shared cases (79 to 123): kinds `as_records` (input any JSON payload), `join` (expect the joined string) and `text_pipeline` (`as_records`, then `args.stages`, then `join`, with optional `args.field` and `args.sep`), and `split` as a stage usable inside `pipeline` and trace cases. The 79 existing cases and every other vector section stay byte-identical; only `_meta.case_count` changes.

- [ ] **Step 4.1: Add the cases and the budget test**

In `parity/parity_cases.py`, replace this block:
<!-- OP replace-old path=parity/parity_cases.py -->
```python
per-language test, not a shared case.

Kinds: the eight record stages, ``merge`` (input = list of sources),
``pipeline`` / ``shaped`` (args.stages = [{"stage", "args"}, ...]), and
``trace_report`` (args.stages + optional args.id_field; expect = report text) and
``trace_dropped_ids`` (args.stages + args.id_field; expect = the ``dropped_ids`` of
```
with:
<!-- OP replace-new -->
```python
per-language test, not a shared case.

Kinds: the eight record stages and ``split``, ``merge`` (input = list of sources),
``as_records`` (input = any JSON payload) and ``join`` (input = records; expect =
the joined string), ``text_pipeline`` (input = a payload; args.stages + optional
args.field / args.sep; ``as_records`` -> the stages -> ``join``, the shape of
brief AC 15), ``pipeline`` / ``shaped`` (args.stages = [{"stage", "args"}, ...]), and
``trace_report`` (args.stages + optional args.id_field; expect = report text) and
``trace_dropped_ids`` (args.stages + args.id_field; expect = the ``dropped_ids`` of
```

In `parity/parity_cases.py`, replace this block:
<!-- OP replace-old path=parity/parity_cases.py -->
```python
from typing import Any, Dict, List

from contexel import (ContexelError, allowlist, dedupe, merge, pipeline,
                      quarantine, rank, rescore, select, shaped, stage, strict,
                      trace, trim_to_budget, truncate_field)

RECORD_STAGES = {
```
with:
<!-- OP replace-new -->
```python
from typing import Any, Dict, List

from contexel import (ContexelError, allowlist, as_records, dedupe, join, merge,
                      pipeline, quarantine, rank, rescore, select, shaped, split,
                      stage, strict, trace, trim_to_budget, truncate_field)

RECORD_STAGES = {
```

In `parity/parity_cases.py`, replace this block:
<!-- OP replace-old path=parity/parity_cases.py -->
```python
    "quarantine": quarantine, "rescore": rescore, "rank": rank,
    "truncate_field": truncate_field, "trim_to_budget": trim_to_budget,
}
ALLOWED_KEYS = {"id", "stage", "args", "input", "expect", "expect_error", "strict"}
NL = chr(10)  # a real newline, written without a backslash escape

# Arguments that make each record stage valid on an empty list (AC 20/22: the
```
with:
<!-- OP replace-new -->
```python
    "quarantine": quarantine, "rescore": rescore, "rank": rank,
    "truncate_field": truncate_field, "trim_to_budget": trim_to_budget,
    "split": split,
}
ALLOWED_KEYS = {"id", "stage", "args", "input", "expect", "expect_error", "strict"}
NL = chr(10)  # a real newline, written without a backslash escape
CR = chr(13)
ASTRAL = chr(0x1F600)  # one code point, two UTF-16 units
E_ACUTE = chr(0xE9)
# characters str.splitlines() cuts at but split(by="lines") must not
WIDE_LINE_ENDS = "".join(chr(c) for c in (0x0B, 0x0C, 0x1C, 0x85, 0x2028, 0x2029))

# Arguments that make each record stage valid on an empty list (AC 20/22: the
```

In `parity/parity_cases.py`, replace this block:
<!-- OP replace-old path=parity/parity_cases.py -->
```python
            _pipe(args["stages"])(records)
        return [stage_entry["dropped_ids"] for stage_entry in t.audit()["stages"]]
    raise ValueError(f"unknown case kind {kind!r}")
```
with:
<!-- OP replace-new -->
```python
            _pipe(args["stages"])(records)
        return [stage_entry["dropped_ids"] for stage_entry in t.audit()["stages"]]
    if kind == "as_records":
        return as_records(records, **args)
    if kind == "join":
        return join(records, **args)
    if kind == "text_pipeline":
        field, sep = args.get("field", "text"), args.get("sep", "")
        chunks = _pipe(args["stages"])(as_records(records, field=field))
        return join(chunks, field=field, sep=sep)
    raise ValueError(f"unknown case kind {kind!r}")
```

In `parity/parity_cases.py`, replace this block:
<!-- OP replace-old path=parity/parity_cases.py -->
```python
        "trace_dropped_ids", keep_only,
        [{"id": "1", "k": "drop"}, {"id": 1, "k": "keep"}])
    return cases
```
with:
<!-- OP replace-new -->
```python
        "trace_dropped_ids", keep_only,
        [{"id": "1", "k": "drop"}, {"id": 1, "k": "keep"}])
    # --- Slice 4: payload stages (ADR-005, brief AC 10-15) ---
    # as_records: the on-ramp. Nested JSON values are legal list items.
    add("as_records/wraps_a_string", "as_records", {}, "hello")
    add("as_records/uses_the_named_field", "as_records", {"field": "body"}, "hello")
    add("as_records/an_empty_string_is_one_record", "as_records", {}, "")
    add("as_records/a_single_mapping_is_one_record", "as_records", {}, {"a": 1, "n": {"z": [1, 2]}})
    add("as_records/list_keeps_mappings_and_wraps_everything_else", "as_records", {},
        [{"a": 1}, "s", 5, None, ["n", 1], {"k": {"z": [1, 2]}}, True, 2.5])
    add("as_records/an_empty_list_is_no_records", "as_records", {}, [])
    add_error("as_records/null_is_not_a_list", "as_records", {}, None, "input.not_list")
    add_error("as_records/a_number_is_not_a_list", "as_records", {}, 5, "input.not_list")
    add_error("as_records/an_empty_field_name_raises", "as_records", {"field": ""}, "x",
              "config.invalid_value")

    # split: boundaries are identical in every language (lines end after a
    # newline only; paragraphs after a run of two or more; sizes in code points)
    add("split/empty_input", "split", {}, [])
    add("split/lines_keep_their_separators", "split", {},
        [{"id": 1, "text": "one" + NL + "two" + NL + "three"}, {"id": 2, "text": "tail" + NL}])
    add("split/lines_crlf_is_one_boundary_and_a_lone_cr_is_not", "split", {},
        [{"id": 1, "text": "a" + CR + NL + "b" + CR + "c" + NL + "d"},
         {"id": 2, "text": CR}, {"id": 3, "text": NL + NL}])
    add("split/lines_ignore_the_wider_splitlines_separators", "split", {},
        [{"id": 1, "text": "a" + WIDE_LINE_ENDS + "b" + NL + "c"}])
    add("split/paragraphs_mixed_newlines", "split", {"by": "paragraphs"},
        [{"id": 1, "text": "a" + NL + NL + "b" + CR + NL + CR + NL + "c" + NL + CR + NL + "d"
          + NL + "e"},
         {"id": 2, "text": "x" + CR + CR + NL + NL + "y"}])
    add("split/paragraph_runs_at_the_edges_and_single_newlines", "split", {"by": "paragraphs"},
        [{"id": 1, "text": NL + NL + "abc"}, {"id": 2, "text": "abc" + NL + NL},
         {"id": 3, "text": "a" + NL + "b" + CR + NL + "c"}, {"id": 4, "text": "a" + NL + " " + NL + "b"},
         {"id": 5, "text": NL + NL + NL + NL}])
    add("split/size_astral", "split", {"by": "size", "size": 2},
        [{"id": 1, "text": "ab" + ASTRAL * 3 + "c"}, {"id": 2, "text": E_ACUTE + ASTRAL}])
    add("split/size_exact_multiple_and_larger_than_the_text", "split", {"by": "size", "size": 3},
        [{"id": 1, "text": "abcdef"}, {"id": 2, "text": "ab"}, {"id": 3, "text": "abc"}])
    add("split/an_empty_text_yields_no_chunks_and_its_neighbours_stay", "split", {},
        [{"id": 1, "text": "a" + NL + "b"}, {"id": 2, "text": ""}, {"id": 3, "text": "c"}])
    add("split/non_string_values_pass_through_untouched", "split", {},
        [{"id": 1}, {"id": 2, "text": None}, {"id": 3, "text": 5},
         {"id": 4, "text": ["a" + NL + "b"], "chunk": "kept"}, {"id": 5, "text": "k" + NL + "l"}])
    add("split/parent_fields_are_carried_and_the_index_restarts", "split", {"field": "body", "into": "part"},
        [{"id": "a", "body": "1" + NL + "2" + NL, "meta": {"k": [1, None]}, "text": "other"},
         {"id": "b", "body": "x" + NL + "y" + NL + "z", "meta": {}}])
    add("split/a_custom_into_name_clears_an_existing_chunk_field", "split", {"into": "part"},
        [{"id": 1, "text": "a" + NL + "b", "chunk": "old"}])
    add_error("split/an_existing_into_key_raises", "split", {},
              [{"text": "ok" + NL + "ok"}, {"text": "a" + NL + "b", "chunk": 1}],
              "input.field_conflict")
    add_error("split/an_empty_text_with_an_existing_into_key_raises", "split", {},
              [{"text": "", "chunk": 1}], "input.field_conflict")
    add_error("split/null_input_is_not_a_list", "split", {}, None, "input.not_list")
    add_error("split/null_item_is_not_a_mapping", "split", {}, [{"text": "a"}, None],
              "input.not_mapping")
    add_error("split/unknown_by_raises", "split", {"by": "words"}, [{"text": "a"}],
              "config.invalid_value")
    add_error("split/size_with_lines_is_contradictory", "split", {"size": 3}, [{"text": "a"}],
              "config.contradictory")
    add_error("split/size_with_paragraphs_is_contradictory", "split",
              {"by": "paragraphs", "size": 0}, [{"text": "a"}], "config.contradictory")
    add_error("split/by_size_without_a_size_raises", "split", {"by": "size"}, [{"text": "a"}],
              "config.invalid_value")
    add_error("split/a_zero_size_raises", "split", {"by": "size", "size": 0}, [{"text": "a"}],
              "config.invalid_value")
    add_error("split/a_negative_size_raises", "split", {"by": "size", "size": -2}, [{"text": "a"}],
              "config.invalid_value")
    add_error("split/a_fractional_size_raises", "split", {"by": "size", "size": 2.5},
              [{"text": "a"}], "config.invalid_value")

    # join: the off-ramp. Non-strings are rendered the way the budget prices them.
    add("join/skips_missing_keeps_strings_and_serializes_the_rest", "join", {"sep": "|"},
        [{"text": "a"}, {"other": 1}, {"text": {"k": 1, "a": [1, "x"]}}, {"text": [1, "x"]},
         {"text": None}, {"text": True}, {"text": 2.5}, {"text": E_ACUTE + ASTRAL}])
    add("join/uses_the_named_field_and_separator", "join", {"field": "body", "sep": NL},
        [{"body": "x"}, {"text": "no"}, {"body": "y"}])
    add("join/an_empty_list_is_an_empty_string", "join", {}, [])
    add("join/empty_strings_still_take_a_separator", "join", {"sep": "-"},
        [{"text": ""}, {"text": ""}])
    add_error("join/null_input_is_not_a_list", "join", {}, None, "input.not_list")
    add_error("join/null_item_is_not_a_mapping", "join", {}, [{"text": "a"}, None],
              "input.not_mapping")

    # text_pipeline: raw text -> as_records -> split -> dedupe -> rescore -> rank
    # -> trim_to_budget -> join (brief AC 15). The budget is a hard ceiling on
    # the joined text (tests/test_parity_cases.py measures it).
    log = ("2026-11-19 10:00:01 INFO  service started" + NL
           + "2026-11-19 10:00:02 WARN  retry backoff jitter exceeded for upstream" + CR + NL
           + "2026-11-19 10:00:03 INFO  health check ok" + NL
           + "2026-11-19 10:00:03 INFO  health check ok" + NL
           + "2026-11-19 10:00:04 ERROR timeout after retry with exponential backoff" + CR + NL
           + "2026-11-19 10:00:05 INFO  cache warmed" + NL
           + "2026-11-19 10:00:06 WARN  retry limit reached, backoff doubled" + NL
           + "2026-11-19 10:00:07 INFO  health check ok" + NL
           + "2026-11-19 10:00:08 INFO  " + E_ACUTE + "v" + E_ACUTE + "nement queued " + ASTRAL + NL)
    add("text_pipeline/log_text_end_to_end", "text_pipeline",
        {"stages": [{"stage": "split", "args": {"by": "lines"}},
                    {"stage": "dedupe", "args": {"key": "text"}},
                    {"stage": "rescore", "args": {"query": "retry backoff timeout", "fields": ["text"]}},
                    {"stage": "rank", "args": {"by": "score", "desc": True}},
                    {"stage": "trim_to_budget", "args": {"max_tokens": 150}}]},
        log)
    add("text_pipeline/a_list_of_strings_is_split_and_deduplicated", "text_pipeline",
        {"stages": [{"stage": "split", "args": {"by": "lines"}},
                    {"stage": "dedupe", "args": {"key": "text"}}]},
        ["alpha" + NL + "beta" + NL, "alpha" + NL + "beta" + NL, "gamma"])
    add("text_pipeline/a_named_field_and_a_separator", "text_pipeline",
        {"field": "body", "sep": "|",
         "stages": [{"stage": "split", "args": {"field": "body", "by": "size", "size": 2}}]},
        "abcde")
    add("text_pipeline/an_empty_text_joins_to_nothing", "text_pipeline",
        {"stages": [{"stage": "split", "args": {}}]}, "")

    # An expanding split is exact under trace: the empty-text parent "b" is a
    # real drop and the id-less parent's two chunks must not hide it.
    add("trace_dropped_ids/an_expanding_split_never_hides_a_dropped_id", "trace_dropped_ids",
        {"id_field": "id", "stages": [{"stage": "split", "args": {}}]},
        [{"id": "a", "text": "1" + NL + "2" + NL + "3"}, {"id": "b", "text": ""},
         {"id": "c", "text": "z"}, {"text": "no id" + NL + "here"}])
    # chunks share their parent's id, so a dropped chunk is reported by it
    add("trace_dropped_ids/a_chunk_dropped_by_dedupe_is_reported_by_its_parents_id",
        "trace_dropped_ids",
        {"id_field": "id",
         "stages": [{"stage": "split", "args": {}},
                    {"stage": "dedupe", "args": {"key": "text"}}]},
        [{"id": "a", "text": "x" + NL + "x" + NL + "y"}, {"id": "b", "text": "x" + NL}])
    return cases
```

In `tests/test_parity_cases.py`, replace this block:
<!-- OP replace-old path=tests/test_parity_cases.py -->
```python
    assert json.dumps(actual, sort_keys=True, ensure_ascii=False) == json.dumps(
        committed, sort_keys=True, ensure_ascii=False)
```
with:
<!-- OP replace-new -->
```python
    assert json.dumps(actual, sort_keys=True, ensure_ascii=False) == json.dumps(
        committed, sort_keys=True, ensure_ascii=False)


def test_the_end_to_end_log_case_fits_its_budget_and_keeps_the_best_lines_first():
    from contexel import tokens

    case = next(c for c in VECTORS["cases"] if c["id"] == "text_pipeline/log_text_end_to_end")
    budget = next(s["args"]["max_tokens"] for s in case["args"]["stages"]
                  if s["stage"] == "trim_to_budget")
    out = case["expect"]
    # the stated budget is a ceiling on the text that is handed to the model
    assert tokens.count(out) <= budget
    # the duplicate "health check ok" lines were dropped by dedupe, the lines that
    # mention the query come first (the line with all three words leads), and
    # the budget cut the rest
    assert "health check ok" not in out
    assert out.startswith("2026-11-19 10:00:04 ERROR timeout after retry")
    assert out.count("retry") >= 3
    assert len(out) < len(case["input"])
```

- [ ] **Step 4.2: Regenerate the vectors, twice, and check what changed**

```bash
PYTHONPATH=. python parity/generate_vectors.py
sha1sum parity/vectors.json
PYTHONPATH=. python parity/generate_vectors.py
sha1sum parity/vectors.json
python - <<'EOF'
import json, subprocess
old = json.loads(subprocess.run(['git', 'show', 'HEAD:parity/vectors.json'], capture_output=True).stdout.decode('utf-8'))
new = json.load(open('parity/vectors.json', encoding='utf-8'))
print(len(old['cases']), len(new['cases']), old['cases'] == new['cases'][:len(old['cases'])])
print(all(old[k] == new[k] for k in old if k not in ('cases', '_meta')))
EOF
```

Expected:

```text
wrote .../parity/vectors.json (46916 bytes)
f685ad244ba25b4a68d08523513d924d32d6bf03  parity/vectors.json
wrote .../parity/vectors.json (46916 bytes)
f685ad244ba25b4a68d08523513d924d32d6bf03  parity/vectors.json
79 123 True
True
```

The two hashes must be equal (the file is a pure function of the case table). The last two lines prove the existing 79 cases and every other section are unchanged. (The `wrote` path is wherever your checkout is.)

- [ ] **Step 4.3: The Python suite passes (the canon computes the new expectations)**

```bash
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
```

Expected:

```text
670 passed
```

- [ ] **Step 4.4: Replay in TypeScript and C#: the new cases fail (red)**

```bash
cd ts && npm run build && npm test
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
```

Expected:

```text
ℹ tests 508 / ℹ pass 464 / ℹ fail 44        (TypeScript: the 44 new cases)
Failed!  - Failed:    44, Passed:   402, Skipped:     0, Total:   446   (C#: the same 44)
```

The 44 failures are the 44 new cases: each runner rejects a stage or case kind it does not know (`as_records`, `join`, `text_pipeline`, and `split` in the stage table), which is the point of the runners' strictness (ADR-007).

- [ ] **Step 4.5: Teach both runners the new kinds**

In `ts/test/runner.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.ts -->
```typescript
  ContexelError,
  allowlist,
  dedupe,
  merge,
  pipeline,
```
with:
<!-- OP replace-new -->
```typescript
  ContexelError,
  allowlist,
  asRecords,
  dedupe,
  join,
  merge,
  pipeline,
```

In `ts/test/runner.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.ts -->
```typescript
  select,
  shaped,
  stage,
  strict,
```
with:
<!-- OP replace-new -->
```typescript
  select,
  shaped,
  split,
  stage,
  strict,
```

In `ts/test/runner.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.ts -->
```typescript
  truncate_field: truncateField,
  trim_to_budget: trimToBudget,
};
```
with:
<!-- OP replace-new -->
```typescript
  truncate_field: truncateField,
  trim_to_budget: trimToBudget,
  split,
};
```

In `ts/test/runner.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.ts -->
```typescript
  truncate_field: ["field", "max_tokens", "suffix"],
  trim_to_budget: ["max_tokens", "min_records"],
  merge: ["schema", "dedupe_key"],
  pipeline: ["stages"],
```
with:
<!-- OP replace-new -->
```typescript
  truncate_field: ["field", "max_tokens", "suffix"],
  trim_to_budget: ["max_tokens", "min_records"],
  split: ["field", "by", "size", "into"],
  as_records: ["field"],
  join: ["field", "sep"],
  text_pipeline: ["stages", "field", "sep"],
  merge: ["schema", "dedupe_key"],
  pipeline: ["stages"],
```

In `ts/test/runner.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.ts -->
```typescript
/** Throw unless `spec` is a known stage kind whose arguments are all known —
 * and, for pipeline/shaped/trace_report/trace_dropped_ids, so is every nested
 * stage spec. */
export function validateSpec(spec: Spec, where: string): void {
  assert.ok(
```
with:
<!-- OP replace-new -->
```typescript
/** Throw unless `spec` is a known stage kind whose arguments are all known —
 * and, for pipeline/shaped/text_pipeline/trace_report/trace_dropped_ids, so is
 * every nested stage spec. */
export function validateSpec(spec: Spec, where: string): void {
  assert.ok(
```

In `ts/test/runner.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.ts -->
```typescript
    case "merge":
      return merge(input as Records[], toOptions(c.args));
    case "pipeline":
      return build(stages)(records);
```
with:
<!-- OP replace-new -->
```typescript
    case "merge":
      return merge(input as Records[], toOptions(c.args));
    case "as_records":
      return asRecords(input, toOptions(c.args));
    case "join":
      return join(records, toOptions(c.args));
    case "text_pipeline": {
      // raw payload -> asRecords -> the stages -> join, the shape of a README example
      const field = (c.args.field as string | undefined) ?? "text";
      const sep = (c.args.sep as string | undefined) ?? "";
      return join(build(stages)(asRecords(input, { field })), { field, sep });
    }
    case "pipeline":
      return build(stages)(records);
```

In `ts/test/runner.test.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.test.ts -->
```typescript
  assert.deepStrictEqual(
    Object.keys(ARG_NAMES).sort(),
    [
      ...Object.keys(RECORD_STAGES),
      "merge",
      "pipeline",
      "shaped",
      "trace_report",
```
with:
<!-- OP replace-new -->
```typescript
  assert.deepStrictEqual(
    Object.keys(ARG_NAMES).sort(),
    [
      ...Object.keys(RECORD_STAGES),
      "as_records",
      "join",
      "text_pipeline",
      "merge",
      "pipeline",
      "shaped",
      "trace_report",
```

In `ts/test/runner.test.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.test.ts -->
```typescript
    /unknown argument "maxTokens"/
  );
});

for (const kind of ["pipeline", "shaped", "trace_report", "trace_dropped_ids"]) {
  test(`an unknown argument inside a nested ${kind} stage spec is rejected`, () => {
    const c = base({
      stage: kind,
      args: { stages: [{ stage: "select", args: { fields: ["a"], extra: 1 } }] },
```
with:
<!-- OP replace-new -->
```typescript
    /unknown argument "maxTokens"/
  );
});

for (const kind of ["pipeline", "shaped", "text_pipeline", "trace_report", "trace_dropped_ids"]) {
  test(`an unknown argument inside a nested ${kind} stage spec is rejected`, () => {
    const c = base({
      stage: kind,
      args: { stages: [{ stage: "select", args: { fields: ["a"], extra: 1 } }] },
```

In `ts/test/runner.test.ts`, replace this block:
<!-- OP replace-old path=ts/test/runner.test.ts -->
```typescript
    /unknown stage "merge"/
  );
});
```
with:
<!-- OP replace-new -->
```typescript
    /unknown stage "merge"/
  );
});

/* ---- payload kinds (Slice 4): as_records, join, text_pipeline, split ---- */

const NL = String.fromCharCode(10);

test("split is a record stage: valid on its own and as a nested stage", () => {
  checkCase(
    base({
      stage: "split",
      args: { by: "size", size: 2, into: "part" },
      input: [{ text: "abcde" }],
      expect: [
        { text: "ab", part: { index: 0, start: 0, end: 2 } },
        { text: "cd", part: { index: 1, start: 2, end: 4 } },
        { text: "e", part: { index: 2, start: 4, end: 5 } },
      ],
    }),
    FIXTURE
  );
  checkCase(
    base({
      stage: "pipeline",
      args: { stages: [{ stage: "split", args: { by: "lines" } }] },
      input: [{ text: "a" + NL + "b" }],
      expect: [
        { text: "a" + NL, chunk: { index: 0, start: 0, end: 2 } },
        { text: "b", chunk: { index: 1, start: 2, end: 3 } },
      ],
    }),
    FIXTURE
  );
});

for (const kind of ["split", "as_records", "join", "text_pipeline"]) {
  test(`an unknown argument name for ${kind} is rejected, not ignored`, () => {
    // `fields` and `separator` are typos for `field` and `sep`: ignoring them would default
    const stages = [{ stage: "split", args: {} }];
    for (const bad of ["fields", "separator", "chunk_size", "Field"]) {
      const args: Record<string, unknown> = kind === "text_pipeline" ? { stages, [bad]: "x" } : { [bad]: "x" };
      assert.throws(
        () => runCase(base({ stage: kind, args, input: [{ text: "a" }], expect: [] }), FIXTURE),
        new RegExp(`unknown argument "${bad}" for stage ${kind}`)
      );
    }
  });
}

test("a text_pipeline with an unknown nested stage is rejected", () => {
  const c = base({
    stage: "text_pipeline",
    args: { stages: [{ stage: "no_such_stage", args: {} }] },
    input: "a",
    expect: "a",
  });
  assert.throws(() => runCase(c, FIXTURE), /stages\[0\]: unknown stage "no_such_stage"/);
});

test("a text_pipeline nested stage must be a record stage, and its arguments are checked", () => {
  for (const nested of ["as_records", "join", "text_pipeline", "merge"]) {
    const c = base({
      stage: "text_pipeline",
      args: { stages: [{ stage: nested, args: {} }] },
      input: "a",
      expect: "a",
    });
    assert.throws(() => runCase(c, FIXTURE), new RegExp(`unknown stage "${nested}"`));
  }
  const typo = base({
    stage: "text_pipeline",
    args: { stages: [{ stage: "split", args: { by: "lines", sizes: 3 } }] },
    input: "a",
    expect: "a",
  });
  assert.throws(() => runCase(typo, FIXTURE), /stages\[0\]: unknown argument "sizes" for stage split/);
});

test("a text_pipeline needs its stages to be a list", () => {
  const c = base({ stage: "text_pipeline", args: { stages: "split" }, input: "a", expect: "a" });
  assert.throws(() => runCase(c, FIXTURE), /args\.stages must be a list/);
});

test("a text_pipeline runs asRecords, the stages, then join, with field and sep defaulted", () => {
  const stages = [{ stage: "split", args: { by: "lines" } }];
  checkCase(
    base({ stage: "text_pipeline", args: { stages }, input: "a" + NL + "b" + NL, expect: "a" + NL + "b" + NL }),
    FIXTURE
  );
  // a named field is used for the wrap, the stage and the join; sep joins the chunks
  checkCase(
    base({
      stage: "text_pipeline",
      args: { field: "body", sep: "|", stages: [{ stage: "split", args: { field: "body", by: "size", size: 2 } }] },
      input: "abcde",
      expect: "ab|cd|e",
    }),
    FIXTURE
  );
  // the stages really run: dedupe drops the repeated chunk
  checkCase(
    base({
      stage: "text_pipeline",
      args: { stages: [{ stage: "split", args: {} }, { stage: "dedupe", args: { key: "text" } }] },
      input: ["x" + NL + "x" + NL + "y"],
      expect: "x" + NL + "y",
    }),
    FIXTURE
  );
});

test("a text_pipeline expect_error case checks the code the pipeline throws", () => {
  const stages = [{ stage: "split", args: {} }];
  checkCase(
    base({ stage: "text_pipeline", args: { stages }, input: null, expect_error: { code: "input.not_list" } }),
    FIXTURE
  );
  assert.throws(
    () =>
      checkCase(
        base({ stage: "text_pipeline", args: { stages }, input: null, expect_error: { code: "input.not_mapping" } }),
        FIXTURE
      ),
    /wrong error code/
  );
});

test("as_records and join cases pass on the right output and fail on a wrong one", () => {
  checkCase(base({ stage: "as_records", args: { field: "body" }, input: "x", expect: [{ body: "x" }] }), FIXTURE);
  checkCase(base({ stage: "join", args: { sep: "-" }, input: [{ text: "a" }, { text: "b" }], expect: "a-b" }), FIXTURE);
  assert.throws(
    () => checkCase(base({ stage: "as_records", args: {}, input: "x", expect: [{ body: "x" }] }), FIXTURE),
    assert.AssertionError
  );
  assert.throws(
    () => checkCase(base({ stage: "join", args: {}, input: [{ text: "a" }], expect: "b" }), FIXTURE),
    assert.AssertionError
  );
});

test("as_records and join pass a null input through as null", () => {
  checkCase(base({ stage: "as_records", args: {}, input: null, expect_error: { code: "input.not_list" } }), FIXTURE);
  checkCase(base({ stage: "join", args: {}, input: null, expect_error: { code: "input.not_list" } }), FIXTURE);
  checkCase(
    base({ stage: "join", args: {}, input: [{ text: "a" }, null], expect_error: { code: "input.not_mapping" } }),
    FIXTURE
  );
  checkCase(
    base({ stage: "as_records", args: { field: "" }, input: "x", expect_error: { code: "config.invalid_value" } }),
    FIXTURE
  );
});

test("the payload kinds are not strict-dependent: strict true changes nothing", () => {
  checkCase(base({ stage: "as_records", args: {}, input: "x", strict: true, expect: [{ text: "x" }] }), FIXTURE);
  checkCase(base({ stage: "join", args: {}, input: null, strict: true, expect_error: { code: "input.not_list" } }), FIXTURE);
  checkCase(
    base({ stage: "split", args: {}, input: [{ text: "a" + NL + "b" }, 1], strict: true, expect_error: { code: "input.not_mapping" } }),
    FIXTURE
  );
});
```

In `csharp/Contexel.Tests/CaseTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/CaseTests.cs -->
```csharp
        ["trace_report"] = ["stages", "id_field"],
        ["trace_dropped_ids"] = ["stages", "id_field"],
    };

    private static readonly HashSet<string> NestingKinds =
        ["pipeline", "shaped", "trace_report", "trace_dropped_ids"];
    private static readonly HashSet<string> SpecKeys = ["stage", "args"];

    /// <summary>Reject an unknown option name in a case's args and, for
    /// pipeline/shaped/trace_report/trace_dropped_ids, in every nested stage
    /// spec.</summary>
    internal static void ValidateArgs(string kind, Rec args, string where)
    {
```
with:
<!-- OP replace-new -->
```csharp
        ["trace_report"] = ["stages", "id_field"],
        ["trace_dropped_ids"] = ["stages", "id_field"],
        ["split"] = ["field", "by", "size", "into"],
        ["as_records"] = ["field"],
        ["join"] = ["field", "sep"],
        ["text_pipeline"] = ["stages", "field", "sep"],
    };

    private static readonly HashSet<string> NestingKinds =
        ["pipeline", "shaped", "trace_report", "trace_dropped_ids", "text_pipeline"];
    private static readonly HashSet<string> SpecKeys = ["stage", "args"];

    /// <summary>Reject an unknown option name in a case's args and, for
    /// pipeline/shaped/trace_report/trace_dropped_ids/text_pipeline, in every
    /// nested stage spec.</summary>
    internal static void ValidateArgs(string kind, Rec args, string where)
    {
```

In `csharp/Contexel.Tests/CaseTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/CaseTests.cs -->
```csharp
        "trim_to_budget" => Stages.TrimToBudget(r, (int)(long)a["max_tokens"]!,
            minRecords: a.TryGetValue("min_records", out var m) ? (int)(long)m! : 0),
        _ => throw new ArgumentException($"unknown stage {kind}"),
    };
```
with:
<!-- OP replace-new -->
```csharp
        "trim_to_budget" => Stages.TrimToBudget(r, (int)(long)a["max_tokens"]!,
            minRecords: a.TryGetValue("min_records", out var m) ? (int)(long)m! : 0),
        // size goes in as the raw JSON value (SplitCore): a bool, a fraction or a
        // string is not an int?, and must reach the library's own validation
        "split" => Text.SplitCore(r, Str(a, "field", "text"), Str(a, "by", "lines"),
            a.GetValueOrDefault("size"), Str(a, "into", "chunk")),
        _ => throw new ArgumentException($"unknown stage {kind}"),
    };
```

In `csharp/Contexel.Tests/CaseTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/CaseTests.cs -->
```csharp
    private static readonly HashSet<string> RecordStages =
        ["select", "dedupe", "allowlist", "quarantine", "rescore", "rank",
         "truncate_field", "trim_to_budget"];

    private static Stage Bind(Rec spec)
```
with:
<!-- OP replace-new -->
```csharp
    private static readonly HashSet<string> RecordStages =
        ["select", "dedupe", "allowlist", "quarantine", "rescore", "rank",
         "truncate_field", "trim_to_budget", "split"];

    private static Stage Bind(Rec spec)
```

In `csharp/Contexel.Tests/CaseTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/CaseTests.cs -->
```csharp
                        : null,
                    args.TryGetValue("dedupe_key", out var dk) ? (string?)dk : null);
            case "pipeline":
                return Build(args).Run(Input(c));
```
with:
<!-- OP replace-new -->
```csharp
                        : null,
                    args.TryGetValue("dedupe_key", out var dk) ? (string?)dk : null);
            // the entry and exit points take the raw JSON payload and sit outside
            // the pipeline, like merge: asRecords -> pipeline(stages) -> join
            case "as_records":
                return Text.AsRecords(c["input"], Str(args, "field", "text"));
            case "join":
                return Text.Join(Input(c), Str(args, "field", "text"), Str(args, "sep", ""));
            case "text_pipeline":
            {
                string field = Str(args, "field", "text");
                return Text.Join(Build(args).Run(Text.AsRecords(c["input"], field)),
                    field, Str(args, "sep", ""));
            }
            case "pipeline":
                return Build(args).Run(Input(c));
```

In `csharp/Contexel.Tests/RunnerTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/RunnerTests.cs -->
```csharp
    }

    [Fact]
    public void TheRealVectorFileCarriesBothNewCaseKeys()
```
with:
<!-- OP replace-new -->
```csharp
    }

    // ----------------------- payload stages (as_records, split, join) -----------------------

    [Theory]
    [InlineData("as_records", "fields")]
    [InlineData("split", "sizes")]
    [InlineData("split", "into_")]
    [InlineData("join", "separator")]
    [InlineData("text_pipeline", "stage")]
    public void AnUnknownArgKeyIsRejectedForTheNewPayloadKinds(string kind, string typo)
    {
        var args = new Rec { [typo] = 1L };
        if (kind == "text_pipeline") args["stages"] = Items();
        var c = Case(kind, args, Items(), ("expect", Items()));
        var e = Assert.Throws<ArgumentException>(() => CaseTests.AssertCase(c));
        Assert.Contains(typo, e.Message);
    }

    [Fact]
    public void AnUnknownArgKeyInANestedSplitSpecOfATextPipelineIsRejected()
    {
        var stages = Items(
            Spec("split", new Rec { ["by"] = "size", ["size"] = 2L }),
            Spec("split", new Rec { ["byy"] = "lines" })); // typo of "by"
        var c = Case("text_pipeline", new Rec { ["stages"] = stages }, "abc", ("expect", "abc"));
        var e = Assert.Throws<ArgumentException>(() => CaseTests.AssertCase(c));
        Assert.Contains("byy", e.Message);
        Assert.Contains("stages[1]", e.Message);
    }

    [Fact]
    public void ATextPipelineWithAnUnknownNestedStageIsRejected()
    {
        foreach (var inner in new[] { "selekt", "as_records", "join", "text_pipeline" })
        {
            var c = Case("text_pipeline",
                new Rec { ["stages"] = Items(Spec(inner, new Rec())) }, "abc", ("expect", "abc"));
            var e = Assert.Throws<ArgumentException>(() => CaseTests.AssertCase(c));
            Assert.Contains($"unknown stage {inner}", e.Message); // only record stages nest
        }
        var badKey = Items(new Rec { ["stage"] = "split", ["args"] = new Rec(), ["note"] = "x" });
        Assert.Throws<ArgumentException>(() => CaseTests.AssertCase(
            Case("text_pipeline", new Rec { ["stages"] = badKey }, "abc", ("expect", "abc"))));
    }

    [Fact]
    public void ValidArgsOfTheNewKindsAreAccepted()
    {
        CaseTests.ValidateArgs("as_records", new Rec { ["field"] = "body" }, "ok");
        CaseTests.ValidateArgs("join", new Rec { ["field"] = "body", ["sep"] = "|" }, "ok");
        CaseTests.ValidateArgs("split", new Rec
        {
            ["field"] = "body", ["by"] = "size", ["size"] = 3L, ["into"] = "part",
        }, "ok");
        CaseTests.ValidateArgs("text_pipeline", new Rec
        {
            ["field"] = "body", ["sep"] = "|",
            ["stages"] = Items(Spec("split", new Rec { ["field"] = "body", ["by"] = "size", ["size"] = 2L })),
        }, "ok");
    }

    [Fact]
    public void ATextPipelineRunsAsRecordsThenThePipelineThenJoin()
    {
        var stages = Items(Spec("split", new Rec { ["field"] = "body", ["by"] = "size", ["size"] = 2L }));
        CaseTests.AssertCase(Case("text_pipeline",
            new Rec { ["field"] = "body", ["sep"] = "|", ["stages"] = stages }, "abcde",
            ("expect", "ab|cd|e")));
        // a wrong expectation fails: the runner really compares the joined text
        Assert.ThrowsAny<Xunit.Sdk.XunitException>(() => CaseTests.AssertCase(Case("text_pipeline",
            new Rec { ["field"] = "body", ["sep"] = "|", ["stages"] = stages }, "abcde",
            ("expect", "abcde"))));
    }

    [Fact]
    public void AnAsRecordsCaseTakesTheRawPayloadAndItsErrorCodeIsChecked()
    {
        CaseTests.AssertCase(Case("as_records", new Rec(), "hello",
            ("expect", Items(new Rec { ["text"] = "hello" }))));
        CaseTests.AssertCase(Case("as_records", new Rec(), null, ("expect_error", Err("input.not_list"))));
        var wrong = Case("as_records", new Rec(), null, ("expect_error", Err("config.invalid_value")));
        var e = Assert.ThrowsAny<Xunit.Sdk.XunitException>(() => CaseTests.AssertCase(wrong));
        Assert.Contains("input.not_list", e.Message);
    }

    [Fact]
    public void ASplitCaseWhoseSizeIsNotAnIntReachesTheLibrarysOwnCheck()
    {
        foreach (object? bad in new object?[] { 2.5, true, "3", null })
            CaseTests.AssertCase(Case("split", new Rec { ["by"] = "size", ["size"] = bad },
                Items(new Rec { ["text"] = "abc" }), ("expect_error", Err("config.invalid_value"))));
        CaseTests.AssertCase(Case("split", new Rec { ["size"] = 2.5 },
            Items(new Rec { ["text"] = "abc" }), ("expect_error", Err("config.contradictory"))));
    }

    [Fact]
    public void ASplitCaseChecksItsInputWithoutStrictMode()
    {
        CaseTests.AssertCase(Case("split", new Rec(), null, ("expect_error", Err("input.not_list"))));
        CaseTests.AssertCase(Case("join", new Rec(), Items(new Rec { ["text"] = "a" }, null),
            ("expect_error", Err("input.not_mapping"))));
    }

    [Fact]
    public void TheRealVectorFileCarriesThePayloadStageCases()
    {
        var cases = AsList(Vectors["cases"]).Select(AsRec).ToList();
        foreach (var kind in new[] { "as_records", "split", "join", "text_pipeline" })
            Assert.Contains(cases, c => (string)c["stage"]! == kind);
        // trace_dropped_ids reaches split too
        Assert.Contains(cases, c => (string)c["stage"]! == "trace_dropped_ids"
            && AsList(AsRec(c["args"])["stages"]).Any(s => (string)AsRec(s)["stage"]! == "split"));
        Assert.Contains(cases, c => (string)c["stage"]! == "split" && c.ContainsKey("expect_error"));
    }

    [Fact]
    public void TheRealVectorFileCarriesBothNewCaseKeys()
```

- [ ] **Step 4.6: All three suites pass**

```bash
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
cd ts && npm run build && npm test
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
```

Expected:

```text
670 passed
ℹ tests 523 / ℹ pass 523 / ℹ fail 0   (tsc clean)
Passed!  - Failed:     0, Passed:   459, Skipped:     0, Total:   459   (0 warnings)
```

The shared vectors now hold the three ports to one answer for every boundary, offset, error code and the end-to-end case.

- [ ] **Step 4.7: Commit**

```bash
git add parity/parity_cases.py parity/vectors.json tests/test_parity_cases.py ts/test/runner.ts ts/test/runner.test.ts csharp/Contexel.Tests/CaseTests.cs csharp/Contexel.Tests/RunnerTests.cs
git commit -m "test: replay the payload stage cases in all three languages"
```


### Task 5: Documentation, executed examples and the decision records

**Acceptance criteria:** AC 34 (new public API is documented and demonstrated); ADR-005 accepted; ADR-008 amended

**Files:**
- Modify: `tests/test_doc_examples.py`, `ts/test/docs.test.ts`, `csharp/Contexel.Tests/DocExampleTests.cs`
- Modify: `README.md`, `site/stages.html`, `ts/README.md`, `csharp/Contexel/README.md`, `CHANGELOG.md`, `docs/adr/005-payload-stage-family.md`, `docs/adr/008-policy-fingerprint-and-trace-attribution.md`

**Interfaces:**
- Consumes: the three ports and the shared vectors.
- Produces: a README section whose two Python examples are executed from the README by `tests/test_doc_examples.py` (its section finder now ends a section at the next heading of the same or a higher level, so two `###` sections no longer swallow each other's examples), the same example asserted in TypeScript and C#, a site reference entry per stage, the changelog entries (Added, Known limitations), ADR-005 accepted with its plan-time amendments and the ADR-008 amendment for `keeps_ids`.

- [ ] **Step 5.1: Write the doc tests**

In `tests/test_doc_examples.py`, replace this block:
<!-- OP replace-old path=tests/test_doc_examples.py -->
````python
AC 34): every ```python block in the section is run and its printed output must
equal the ```text block that follows it, so documentation cannot drift from
behavior. Slices 4 and 5 add their sections to SECTIONS."""
import contextlib
import io
````
with:
<!-- OP replace-new -->
````python
AC 34): every ```python block in the section is run and its printed output must
equal the ```text block that follows it, so documentation cannot drift from
behavior. Slice 5 adds its section to SECTIONS."""
import contextlib
import io
````

In `tests/test_doc_examples.py`, replace this block:
<!-- OP replace-old path=tests/test_doc_examples.py -->
```python
#: (README heading, number of runnable examples the section must contain)
SECTIONS = [("### Errors and strict mode", 2)]

with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
```
with:
<!-- OP replace-new -->
```python
#: (README heading, number of runnable examples the section must contain)
SECTIONS = [("### Text, logs and web pages", 2),
            ("### Errors and strict mode", 2)]

with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
```

In `tests/test_doc_examples.py`, replace this block:
<!-- OP replace-old path=tests/test_doc_examples.py -->
```python
def _section(heading):
    start = README.index(heading)
    end = README.find(NL + "## ", start)
    return README[start:end if end != -1 else len(README)]
```
with:
<!-- OP replace-new -->
```python
def _section(heading):
    # a section runs to the next heading of its own level or a higher one
    start = README.index(heading)
    level = len(heading.split(" ")[0])
    stops = [NL + "#" * n + " " for n in range(2, level + 1)]
    found = [i for i in (README.find(s, start + len(heading)) for s in stops) if i != -1]
    return README[start:min(found) if found else len(README)]
```

In `ts/test/docs.test.ts`, replace this block:
<!-- OP replace-old path=ts/test/docs.test.ts -->
````typescript
const FENCE = new RegExp("```(ts|text)" + NL + "([^]*?)```", "g");

/** [README heading, number of runnable examples the section must contain] */
const SECTIONS: Array<[string, number]> = [["## Errors and strict mode", 2]];

const README = readFileSync(new URL("../../README.md", import.meta.url), "utf-8")
  .split(CR + NL)
````
with:
<!-- OP replace-new -->
````typescript
const FENCE = new RegExp("```(ts|text)" + NL + "([^]*?)```", "g");

/** [README heading, number of runnable examples the section must contain] */
const SECTIONS: Array<[string, number]> = [
  ["## Text, logs and web pages", 2],
  ["## Errors and strict mode", 2],
];

const README = readFileSync(new URL("../../README.md", import.meta.url), "utf-8")
  .split(CR + NL)
````

In `ts/test/docs.test.ts`, replace this block:
<!-- OP replace-old path=ts/test/docs.test.ts -->
```typescript
  });
}
```
with:
<!-- OP replace-new -->
```typescript
  });
}

/* ---- Slice 4: the payload-stages example (text in, best lines out, text back) ---- */

test("payload stages: the log example returns the best lines, in rank and in reading order", () => {
  const { asRecords, dedupe, join, pipeline, rank, rescore, split, stage, trimToBudget } = contexel;
  const log =
    "INFO started" + NL + "WARN retry limit reached" + NL + "INFO ok" + NL + "INFO ok" + NL +
    "ERROR timeout after retry" + NL;
  const pipe = pipeline([
    stage(split, { by: "lines" }),
    stage(dedupe, { key: "text" }),
    stage(rescore, { query: "retry timeout", fields: ["text"] }),
    stage(rank, { by: "score" }),
    stage(trimToBudget, { maxTokens: 60 }),
  ]);
  const best = pipe(asRecords(log));
  assert.strictEqual(join(best), "ERROR timeout after retry" + NL + "WARN retry limit reached" + NL);
  const startOf = (r: contexel.Rec) => (r.chunk as { start: number; end: number }).start;
  assert.deepStrictEqual(best.map(startOf), [54, 13]); // offsets into the log
  // rank again by offset to restore reading order
  const reading = rank(best, { by: startOf, desc: false });
  assert.strictEqual(join(reading), "WARN retry limit reached" + NL + "ERROR timeout after retry" + NL);
});

test("payload stages: the paragraphs example keeps each paragraph and its offsets", () => {
  const { asRecords, split } = contexel;
  const paras = split(asRecords("intro" + NL + NL + "body one" + NL + "body two" + NL + NL + "end"), {
    by: "paragraphs",
  });
  assert.deepStrictEqual(
    paras.map((c) => c.text),
    ["intro" + NL + NL, "body one" + NL + "body two" + NL + NL, "end"]
  );
  const chunk = (c: contexel.Rec) => c.chunk as { start: number; end: number };
  assert.deepStrictEqual(
    paras.map((c) => [chunk(c).start, chunk(c).end]),
    [[0, 7], [7, 26], [26, 29]]
  );
});
```

In `csharp/Contexel.Tests/DocExampleTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/DocExampleTests.cs -->
```csharp
        File.ReadAllText(path).Replace("\r\n", "\n");

    private static List<(string Lang, string Body)> ReadmeBlocks()
    {
        string readme = ReadText(FindUp(Path.Combine("csharp", "Contexel", "README.md")));
        int start = readme.IndexOf("## Errors and strict mode", StringComparison.Ordinal);
        Assert.True(start >= 0, "README has no 'Errors and strict mode' section");
        int end = readme.IndexOf("\n## ", start + 1, StringComparison.Ordinal);
        string section = readme[start..(end < 0 ? readme.Length : end)];
```
with:
<!-- OP replace-new -->
```csharp
        File.ReadAllText(path).Replace("\r\n", "\n");

    private const string ErrorsHeading = "## Errors and strict mode";
    private const string PayloadHeading = "## Text, logs and web pages";

    private static List<(string Lang, string Body)> ReadmeBlocks(string heading = ErrorsHeading)
    {
        string readme = ReadText(FindUp(Path.Combine("csharp", "Contexel", "README.md")));
        int start = readme.IndexOf(heading, StringComparison.Ordinal);
        Assert.True(start >= 0, $"README has no '{heading}' section");
        int end = readme.IndexOf("\n## ", start + 1, StringComparison.Ordinal);
        string section = readme[start..(end < 0 ? readme.Length : end)];
```

In `csharp/Contexel.Tests/DocExampleTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/DocExampleTests.cs -->
```csharp
    /// <summary>The README's n-th C# example (without its using line) and its expected output.</summary>
    private static (string Source, string Expected) ReadmeExample(int n)
    {
        var blocks = ReadmeBlocks();
        int seen = 0;
        for (int i = 0; i < blocks.Count; i++)
```
with:
<!-- OP replace-new -->
```csharp
    /// <summary>The README's n-th C# example (without its using line) and its expected output.</summary>
    private static (string Source, string Expected) ReadmeExample(int n, string heading = ErrorsHeading)
    {
        var blocks = ReadmeBlocks(heading);
        int seen = 0;
        for (int i = 0; i < blocks.Count; i++)
```

In `csharp/Contexel.Tests/DocExampleTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/DocExampleTests.cs -->
```csharp
    }

    private static void Check(int n, Action example, string thisFile)
    {
        var (source, expected) = ReadmeExample(n);
        Assert.Equal(source, CompiledSource(n, thisFile));
        var original = Console.Out;
        var captured = new StringWriter();
```
with:
<!-- OP replace-new -->
```csharp
    }

    private static void Check(int n, Action example, string thisFile,
                              string heading = ErrorsHeading, int? marker = null)
    {
        var (source, expected) = ReadmeExample(n, heading);
        Assert.Equal(source, CompiledSource(marker ?? n, thisFile));
        var original = Console.Out;
        var captured = new StringWriter();
```

In `csharp/Contexel.Tests/DocExampleTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/DocExampleTests.cs -->
```csharp
    public void ReadmeExample2PrintsWhatTheReadmeShows() =>
        Check(2, Example2, ThisFile());

    private static string ThisFile([CallerFilePath] string path = "") => path;
```
with:
<!-- OP replace-new -->
```csharp
    public void ReadmeExample2PrintsWhatTheReadmeShows() =>
        Check(2, Example2, ThisFile());

    // The payload-stage examples (Text, logs and web pages): the README section is tied
    // to Example3 and Example4 below like the others, and the two tests that follow pin
    // the exact printed text (blank lines included) on their own.

    [Fact]
    public void ThePayloadSectionHasItsTwoRunnableExamples() =>
        Assert.Equal(2, ReadmeBlocks(PayloadHeading).Count(b => b.Lang == "csharp"));

    [Fact]
    public void PayloadExample1PrintsWhatTheReadmeShows() =>
        Check(1, Example3, ThisFile(), PayloadHeading, marker: 3);

    [Fact]
    public void PayloadExample2PrintsWhatTheReadmeShows() =>
        Check(2, Example4, ThisFile(), PayloadHeading, marker: 4);

    private static string Printed(Action example)
    {
        var original = Console.Out;
        var captured = new StringWriter();
        Console.SetOut(captured);
        try { example(); }
        finally { Console.SetOut(original); }
        return captured.ToString().Replace("\r\n", "\n");
    }

    [Fact]
    public void TextExample3FindsTheBestLinesAndTheirOffsetsInTheLog() =>
        Assert.Equal(
            "ERROR timeout after retry\nWARN retry limit reached\n[54, 13]\n" +
            "WARN retry limit reached\nERROR timeout after retry\n",
            Printed(Example3));

    [Fact]
    public void TextExample4SplitsParagraphsWithOffsetsIntoTheText() =>
        Assert.Equal(
            "[\"intro\\n\\n\", \"body one\\nbody two\\n\\n\", \"end\"]\n[[0, 7], [7, 26], [26, 29]]\n",
            Printed(Example4));

    private static string ThisFile([CallerFilePath] string path = "") => path;
```

In `csharp/Contexel.Tests/DocExampleTests.cs`, replace this block:
<!-- OP replace-old path=csharp/Contexel.Tests/DocExampleTests.cs -->
```csharp
        // </doc-example-2>
    }
}
```
with:
<!-- OP replace-new -->
```csharp
        // </doc-example-2>
    }

    private static void Example3()
    {
        // <doc-example-3>
        var log = "INFO started\nWARN retry limit reached\nINFO ok\nINFO ok\nERROR timeout after retry\n";

        var pipe = new Pipeline(
            new Stage("split", r => Text.Split(r, by: "lines")),                      // one record per line
            new Stage("dedupe", r => Stages.Dedupe(r, "text")),                       // the repeated "INFO ok" goes
            new Stage("rescore", r => Stages.Rescore(r, "retry timeout", new[] { "text" })),
            new Stage("rank", r => Stages.Rank(r, "score")),
            new Stage("trim_to_budget", r => Stages.TrimToBudget(r, 60)));
        var best = pipe.Run(Text.AsRecords(log));
        Console.Write(Text.Join(best));
        Console.WriteLine(Tokens.PythonJson(best.Select(c => ((Dictionary<string, object?>)c["chunk"]!)["start"]).ToList()));

        // rank again on the offset to restore reading order before Join
        var reading = Stages.Rank(best, r => ((Dictionary<string, object?>)r["chunk"]!)["start"], desc: false);
        Console.Write(Text.Join(reading));
        // </doc-example-3>
    }

    private static void Example4()
    {
        // <doc-example-4>
        var paras = Text.Split(Text.AsRecords("intro\n\nbody one\nbody two\n\nend"), by: "paragraphs");
        Console.WriteLine(Tokens.PythonJson(paras.Select(c => c["text"]).ToList()));
        Console.WriteLine(Tokens.PythonJson(paras.Select(c =>
        {
            var at = (Dictionary<string, object?>)c["chunk"]!;
            return new List<object?> { at["start"], at["end"] };
        }).ToList()));
        // </doc-example-4>
    }
}
```

- [ ] **Step 5.2: Run them**

```bash
PYTHONPATH=. python -m pytest -q tests/test_doc_examples.py
cd ts && npm run build && npm test
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
```

Expected:

```text
3 failed, 670 passed                          (Python: the README has no payload section)
ℹ tests 521 / ℹ pass 520 / ℹ fail 1        (TypeScript)
Failed!  - Failed:     3, Passed:   461, Skipped:     0, Total:   464   (C#)
```

The tests that read the README are red in all three languages because it has no payload section yet: three Python tests (the section's count test and its two examples), one TypeScript failure (the doc test cannot find the section) and three C# tests (the section's count test and its two README-tied examples). The direct tests of the same examples in `ts/test/docs.test.ts` and `csharp/Contexel.Tests/DocExampleTests.cs` pass at once: the library already behaves as documented, so they are guards, not red tests.

- [ ] **Step 5.3: Write the documentation**

In `README.md`, replace this block:
<!-- OP replace-old path=README.md -->
```markdown
| `quarantine(records, fields=...)` | tripwire for literal injection markers | case-insensitive pattern screen ("ignore previous instructions", role resets, system tags); `drop` or `flag` — not a security boundary: paraphrase passes, provenance gating is the stronger control |
| `merge(*sources, schema=...)` | unify differently-shaped tool outputs | maps candidate field names onto one schema, first match wins; optional cross-source dedupe |

Compose them with `pipeline([...])` — plain function composition, any
```
with:
<!-- OP replace-new -->
```markdown
| `quarantine(records, fields=...)` | tripwire for literal injection markers | case-insensitive pattern screen ("ignore previous instructions", role resets, system tags); `drop` or `flag` — not a security boundary: paraphrase passes, provenance gating is the stronger control |
| `merge(*sources, schema=...)` | unify differently-shaped tool outputs | maps candidate field names onto one schema, first match wins; optional cross-source dedupe |
| `as_records(x, field="text")` | turn a string, a mapping or a list into records | entry point (outside `pipeline`): a string becomes `[{field: x}]`, a mapping `[x]`, a list keeps its mappings and wraps every other item; `None` and bytes raise `input.not_list` |
| `split(records, field="text", by="lines")` | cut text into chunk records | by lines (after each `\n`), paragraphs (after a run of two or more newlines) or `size` code points; every chunk keeps its separator and an `{index, start, end}` offset, so joining the chunks rebuilds the text exactly |
| `join(records, field="text", sep="")` | turn records back into one string | exit point (outside `pipeline`): strings as they are, anything else rendered the way the budget priced it; records without the field are skipped |

Compose them with `pipeline([...])` — plain function composition, any
```

In `README.md`, replace this block:
<!-- OP replace-old path=README.md -->
```markdown
many missing ids as the stage produced extra id-less records and reports the
rest as dropped, so keep the id field in every `select` for exact attribution.

All of it is stdlib-only Python. No embeddings, no model calls, no
```
with:
<!-- OP replace-new -->
```markdown
many missing ids as the stage produced extra id-less records and reports the
rest as dropped, so keep the id field in every `select` for exact attribution.
`split` keeps every id (each chunk carries its parent's fields), so it is attributed
exactly: an empty-text record that vanishes is reported, a chunk dropped later is
reported under its parent's id.

All of it is stdlib-only Python. No embeddings, no model calls, no
```

In `README.md`, replace this block:
<!-- OP replace-old path=README.md -->
```markdown
back to the process default).

### Errors and strict mode
```
with:
<!-- OP replace-new -->
````markdown
back to the process default).

### Text, logs and web pages

Stages take a list of mappings, and a log, a web page or a plain string is
none of that. Three small stages convert at the edges: `as_records` turns a
string (or one mapping, or a list) into records, `split` cuts the text of each
record into chunk records, and `join` turns records back into one string.
Everything in between is an ordinary stage. Call `as_records` and `join`
outside `pipeline`, as you call `merge`: a pipeline hands every stage a list,
and a strict pipeline rejects `join`'s string, naming the stage.

```python
from contexel import (as_records, dedupe, join, pipeline, rank, rescore,
                      split, stage, trim_to_budget)

log = "INFO started\nWARN retry limit reached\nINFO ok\nINFO ok\nERROR timeout after retry\n"

pipe = pipeline([
    stage(split, by="lines"),                              # one record per line
    stage(dedupe, key="text"),                             # the repeated "INFO ok" goes
    stage(rescore, query="retry timeout", fields=["text"]),
    stage(rank, by="score"),
    stage(trim_to_budget, max_tokens=60),
])
best = pipe(as_records(log))
print(join(best), end="")
print([c["chunk"]["start"] for c in best])                 # offsets into the log
```

```text
ERROR timeout after retry
WARN retry limit reached
[54, 13]
```

The cuts are the same in Python, TypeScript and C#:

| `by` | a chunk ends |
|---|---|
| `"lines"` (default) | after each `\n`: `\r\n` is one boundary and a lone `\r` is none (Python's wider `splitlines` set is not used) |
| `"paragraphs"` | after each run of two or more newlines, `(?:\r?\n){2,}` |
| `"size"` | every `size` code points (`size` is a required positive integer, and only valid with this mode) |

- Every chunk keeps its trailing separator, so `join(split(as_records(text)))`
  returns `text` exactly. Each chunk is a copy of its parent record with the
  text replaced and `{"index", "start", "end"}` stored under `into` (default
  `"chunk"`): `text[start:end]` is the chunk, and offsets and sizes count code
  points in every language.
- A record whose text field is not a string passes through untouched; an empty
  text produces no chunks, so that record disappears; a record that already has
  the `into` key raises `input.field_conflict`.
- These stages check their input in every mode, not only in strict mode: a
  non-list raises `input.not_list` and a non-mapping item `input.not_mapping`.
- `join` renders a value that is not a string the way the token budget priced it
  (`tokens.serialize`) and skips records that lack the field.
- `rank` reorders the chunks by score. To restore reading order before `join`,
  rank again on the offset with a named key function (a dotted path such as
  `"chunk.start"` is not supported):

```python
from contexel import as_records, join, rank, split

chunks = split(as_records("one\ntwo\nthree\n"), by="lines")
by_length = rank(chunks, by=lambda r: len(r["text"]))
in_order = rank(by_length, by=lambda r: r["chunk"]["start"], desc=False)
print(repr(join(by_length)))
print(repr(join(in_order)))
```

```text
'three\none\ntwo\n'
'one\ntwo\nthree\n'
```

Overlapping windows and token-sized chunks are not offered: they either break
losslessness or need a tokenizer every language shares.

### Errors and strict mode
````

In `README.md`, replace this block:
<!-- OP replace-old path=README.md -->
```markdown
`config.empty` for `quarantine` and `rescore` only; `select(records, [])` still
returns `[{}, ...]`.

A `strict()` object keeps its own token stack, so one object can be entered
```
with:
<!-- OP replace-new -->
```markdown
`config.empty` for `quarantine` and `rescore` only; `select(records, [])` still
returns `[{}, ...]`.

The payload stages (`as_records`, `split`, `join`) are new, so they check their input
in every mode instead of only in strict mode (see [Text, logs and web pages](#text-logs-and-web-pages)).

A `strict()` object keeps its own token stack, so one object can be entered
```

In `site/stages.html`, replace this block:
<!-- OP replace-old path=site/stages.html -->
```html
    <a href="#truncate_field">truncate_field</a>
    <a href="#trim_to_budget">trim_to_budget</a>
    <a href="#merge">merge</a><a href="#compose">pipeline · shaped · trace</a>
    <a href="#errors">errors · strict mode</a>
  </div>
```
with:
<!-- OP replace-new -->
```html
    <a href="#truncate_field">truncate_field</a>
    <a href="#trim_to_budget">trim_to_budget</a>
    <a href="#merge">merge</a><a href="#as_records">as_records</a>
    <a href="#split">split</a><a href="#join">join</a>
    <a href="#compose">pipeline · shaped · trace</a>
    <a href="#errors">errors · strict mode</a>
  </div>
```

In `site/stages.html`, replace this block:
<!-- OP replace-old path=site/stages.html -->
```html
                         "url":   ["url", "link", "href"]})</code></pre>

<h2 id="compose">pipeline · stage · shaped · trace · tokens</h2>
<ul>
```
with:
<!-- OP replace-new -->
```html
                         "url":   ["url", "link", "href"]})</code></pre>

<h2 id="as_records">as_records(x, field="text")</h2>
<p><strong>Turns</strong> a payload into records, the shape every other stage
takes, so a log, a web page or a plain string can go through
<code>dedupe</code>, <code>rescore</code>, <code>rank</code> and
<code>trim_to_budget</code>. A string becomes <code>[{field: x}]</code>; a
mapping becomes <code>[x]</code> (the same object); a list keeps each mapping
item and wraps every other item as <code>{field: item}</code> (nested JSON
values are fine). <code>None</code>, bytes and every other type raise
<code>input.not_list</code>, and <code>field</code> must be a non-empty string.
An entry point, like <code>merge</code>: call it outside
<code>pipeline</code>; it is not auto-traced and it checks its input in every
mode, not only in strict mode.</p>

<h2 id="split">split(records, field="text", by="lines", size=None, into="chunk")</h2>
<p><strong>Cuts</strong> the text in <code>field</code> into chunk records. A
chunk is a copy of its parent record with the text replaced and
<code>{"index", "start", "end"}</code> stored under <code>into</code>:
<code>index</code> counts from 0 within the parent and <code>[start, end)</code>
are code-point offsets, so <code>text[start:end]</code> is the chunk. Every
chunk keeps its trailing separator, so joining the chunks with
<code>""</code> returns the text exactly.</p>
<ul>
  <li><code>by="lines"</code>: a chunk ends after each <code>\n</code>
  (<code>\r\n</code> is one boundary, a lone <code>\r</code> is none, and
  Python's wider <code>splitlines</code> set is not used).</li>
  <li><code>by="paragraphs"</code>: after each run of two or more newlines,
  <code>(?:\r?\n){2,}</code>.</li>
  <li><code>by="size"</code>: every <code>size</code> code points;
  <code>size</code> is a required positive integer here and an error with any
  other mode (<code>config.contradictory</code>).</li>
</ul>
<p>The boundaries are the same in Python, TypeScript and C#. A record whose
field is not a string passes through; an empty text produces no chunks, so that
record disappears; a record that already has the <code>into</code> key raises
<code>input.field_conflict</code>. Unlike the original stages it checks its
input in every mode: a non-list raises <code>input.not_list</code>, a
non-mapping item <code>input.not_mapping</code>. It is auto-traced and keeps
every id, so under <code>trace(id_field=...)</code> an empty-text record that
vanishes is reported as dropped and a chunk dropped later is reported under its
parent's id. <code>rank</code> reorders chunks by score: to restore reading
order before <code>join</code>, rank again on the offset with a named key
function (<code>by=lambda r: r["chunk"]["start"], desc=False</code>).
Overlapping windows and token-sized chunks are not offered.</p>
<pre><code>chunks = split(as_records(log), by="lines")
text = join(chunks)                  # == log, byte for byte</code></pre>

<h2 id="join">join(records, field="text", sep="")</h2>
<p><strong>Turns</strong> records back into one string. A record without
<code>field</code> is skipped; a string value is used as it is; any other value
is rendered the way the token budget priced it
(<code>tokens.serialize</code>); the parts are joined with <code>sep</code>.
An exit point, like <code>merge</code>: call it outside <code>pipeline</code>
(a strict pipeline rejects a stage that returns a string, naming it); it is not
auto-traced and it checks its input in every mode.</p>

<h2 id="compose">pipeline · stage · shaped · trace · tokens</h2>
<ul>
```

In `site/stages.html`, replace this block:
<!-- OP replace-old path=site/stages.html -->
```html
  <tr><td><code>config.invalid_value</code></td><td>an unsupported option value or a wrong-typed parameter (<code>match</code>, <code>action</code>, <code>by</code>, a negative or non-integer <code>max_tokens</code>)</td></tr>
  <tr><td><code>config.empty</code></td><td>the call would silently do nothing or everything: an empty pattern fragment, an empty replacement list, <code>fields=[]</code> for <code>quarantine</code> and <code>rescore</code></td></tr>
  <tr><td><code>config.contradictory</code></td><td><code>replace_patterns=True</code> without <code>patterns</code></td></tr>
  <tr><td><code>config.invalid_pattern</code></td><td>a pattern fails to compile; the message names the pattern</td></tr>
  <tr><td><code>input.not_list</code></td><td>(strict) records are not a list</td></tr>
  <tr><td><code>input.not_mapping</code></td><td>(strict) an item is not a mapping; the message names the stage and index. <code>quarantine</code> always raises it, strict or not, because a screen that skips what it cannot read would keep the attack</td></tr>
  <tr><td><code>input.field_conflict</code></td><td>an output field already exists (<code>quarantine</code> flag <code>into</code>) — always raised, because continuing would destroy data</td></tr>
</table>
</div>
```
with:
<!-- OP replace-new -->
```html
  <tr><td><code>config.invalid_value</code></td><td>an unsupported option value or a wrong-typed parameter (<code>match</code>, <code>action</code>, <code>by</code>, a negative or non-integer <code>max_tokens</code>)</td></tr>
  <tr><td><code>config.empty</code></td><td>the call would silently do nothing or everything: an empty pattern fragment, an empty replacement list, <code>fields=[]</code> for <code>quarantine</code> and <code>rescore</code></td></tr>
  <tr><td><code>config.contradictory</code></td><td><code>replace_patterns=True</code> without <code>patterns</code>, or <code>size</code> given to <code>split</code> with a <code>by</code> other than <code>"size"</code></td></tr>
  <tr><td><code>config.invalid_pattern</code></td><td>a pattern fails to compile; the message names the pattern</td></tr>
  <tr><td><code>input.not_list</code></td><td>(strict) records are not a list; <code>split</code>, <code>join</code> and <code>as_records</code> raise it in every mode</td></tr>
  <tr><td><code>input.not_mapping</code></td><td>(strict) an item is not a mapping; the message names the stage and index. <code>quarantine</code> always raises it, strict or not, because a screen that skips what it cannot read would keep the attack</td></tr>
  <tr><td><code>input.field_conflict</code></td><td>an output field already exists (<code>quarantine</code> flag <code>into</code>, <code>split</code> <code>into</code>) — always raised, because continuing would destroy data</td></tr>
</table>
</div>
```

In `site/stages.html`, replace this block:
<!-- OP replace-old path=site/stages.html -->
```html
<code>input.not_mapping</code> are raised whether or not strict mode is on.
Strict mode covers the eight record stages and the pipeline or
<code>shaped</code> output check, not <code>merge</code>.</p>
<pre><code>with contexel.strict():                         # ambient, this context only
    select(records, ["a"])                      # InputShapeError names stage + item
```
with:
<!-- OP replace-new -->
```html
<code>input.not_mapping</code> are raised whether or not strict mode is on.
Strict mode covers the eight record stages and the pipeline or
<code>shaped</code> output check, not <code>merge</code>; the payload stages (<code>as_records</code>, <code>split</code>, <code>join</code>) are new and check their input in every mode.</p>
<pre><code>with contexel.strict():                         # ambient, this context only
    select(records, ["a"])                      # InputShapeError names stage + item
```

In `ts/README.md`, replace this block:
<!-- OP replace-old path=ts/README.md -->
```markdown
| `trimToBudget` | keep records until the total token budget is spent; `minRecords` guarantees the best records survive a too-small budget instead of returning `[]` |

Plus `merge` for combining multiple sources under one schema, `pipeline`/`stage`
for composition with a stable policy fingerprint, `trace`/`audit` for the
governance record, and `tokens.scoped` for concurrency-safe (AsyncLocalStorage)
tokenizer and serializer overrides per tenant.

## Errors and strict mode
```
with:
<!-- OP replace-new -->
````markdown
| `trimToBudget` | keep records until the total token budget is spent; `minRecords` guarantees the best records survive a too-small budget instead of returning `[]` |

Plus `asRecords`, `split` and `join` for text (below), `merge` for combining multiple sources under one schema, `pipeline`/`stage`
for composition with a stable policy fingerprint, `trace`/`audit` for the
governance record, and `tokens.scoped` for concurrency-safe (AsyncLocalStorage)
tokenizer and serializer overrides per tenant.

## Text, logs and web pages

Stages take an array of records, and a log, a web page or a plain string is none
of that. Three small stages convert at the edges: `asRecords` turns a string (or
one record, or an array) into records, `split` cuts the text of each record into
chunk records, and `join` turns records back into one string. Everything in
between is an ordinary stage. Call `asRecords` and `join` outside `pipeline`, as
you call `merge`: a pipeline hands every stage an array, and a strict pipeline
rejects `join`'s string.

```ts
import { asRecords, dedupe, join, pipeline, rank, rescore, split, stage, trimToBudget } from "contexel";

const log = "INFO started\nWARN retry limit reached\nINFO ok\nINFO ok\nERROR timeout after retry\n";

const pipe = pipeline([
  stage(split, { by: "lines" }),                            // one record per line
  stage(dedupe, { key: "text" }),                           // the repeated "INFO ok" goes
  stage(rescore, { query: "retry timeout", fields: ["text"] }),
  stage(rank, { by: "score" }),
  stage(trimToBudget, { maxTokens: 60 }),
]);
const best = pipe(asRecords(log));
console.log(JSON.stringify(join(best)));
console.log(JSON.stringify(best.map((c) => c.chunk)));      // offsets into the log
```

```text
"ERROR timeout after retry\nWARN retry limit reached\n"
[{"index":4,"start":54,"end":80},{"index":1,"start":13,"end":38}]
```

The cuts are the same as in Python and C#: `by: "lines"` (the default) ends a
chunk after each `\n` (`\r\n` is one boundary, a lone `\r` is none),
`by: "paragraphs"` after each run of two or more newlines, `by: "size"` every
`size` code points (a required positive integer, valid only with this mode).
Every chunk keeps its trailing separator, so `join(split(asRecords(text)))`
returns `text` exactly; each chunk is a copy of its parent with the text replaced
and `{ index, start, end }` stored under `into` (default `"chunk"`). Offsets and
sizes count code points, never UTF-16 units. A record whose own text field is not
a string passes through untouched; an empty text produces no chunks; a record
that already has its own `into` property throws `input.field_conflict`. These
stages check their input in every mode, not only inside `strict(...)`: a
non-array throws `input.not_list` and a non-record item `input.not_mapping`.
`asRecords` accepts only a string, a plain object or an array: `null`, a number,
a `Map`, a `Set`, a `Date`, a `Buffer` or a class instance throws
`input.not_list`.

`rank` reorders the chunks by score. To restore reading order before `join`, rank
again on the offset with a key function:

```ts
import { asRecords, join, rank, split } from "contexel";

const chunks = split(asRecords("one\ntwo\nthree\n"), { by: "lines" });
const byLength = rank(chunks, { by: (r) => String(r.text).length });
const inOrder = rank(byLength, { by: (r) => Object(r.chunk).start, desc: false });
console.log(JSON.stringify(join(byLength)));
console.log(JSON.stringify(join(inOrder)));
```

```text
"three\none\ntwo\n"
"one\ntwo\nthree\n"
```

## Errors and strict mode
````

In `csharp/Contexel/README.md`, replace this block:
<!-- OP replace-old path=csharp/Contexel/README.md -->
```markdown
| `TrimToBudget` | keep records until the budget is spent; `minRecords` guarantees the best records survive a too-small budget |

Plus `Merge` for combining sources, `Pipeline`/`Stage` with stable policy
fingerprints, `Trace`/`Audit` for the governance record, and
`Tokens.Scoped` (AsyncLocal) for concurrency-safe per-tenant token
```
with:
<!-- OP replace-new -->
```markdown
| `TrimToBudget` | keep records until the budget is spent; `minRecords` guarantees the best records survive a too-small budget |

Plus `Text.AsRecords`, `Text.Split` and `Text.Join` for text (below), `Merge` for combining sources, `Pipeline`/`Stage` with stable policy
fingerprints, `Trace`/`Audit` for the governance record, and
`Tokens.Scoped` (AsyncLocal) for concurrency-safe per-tenant token
```

In `csharp/Contexel/README.md`, replace this block:
<!-- OP replace-old path=csharp/Contexel/README.md -->
```markdown
stage. A lambda that calls `inner.Run` is opaque too. There is no tiktoken in
this package.

## Errors and strict mode
```
with:
<!-- OP replace-new -->
````markdown
stage. A lambda that calls `inner.Run` is opaque too. There is no tiktoken in
this package.

## Text, logs and web pages

Stages take a `List<Dictionary<string, object?>>`, and a log, a web page or a plain
string is none of that. Three small static methods convert at the edges:
`Text.AsRecords` turns a string (or one record, or a list) into records,
`Text.Split` cuts the text of each record into chunk records, and `Text.Join`
turns records back into one string. Everything in between is an ordinary stage.
Call `AsRecords` and `Join` outside a `Pipeline`, as you call `Merge`: a pipeline
hands every stage a list, and a strict pipeline rejects a stage that returns
something else.

```csharp
using Contexel;

var log = "INFO started\nWARN retry limit reached\nINFO ok\nINFO ok\nERROR timeout after retry\n";

var pipe = new Pipeline(
    new Stage("split", r => Text.Split(r, by: "lines")),                      // one record per line
    new Stage("dedupe", r => Stages.Dedupe(r, "text")),                       // the repeated "INFO ok" goes
    new Stage("rescore", r => Stages.Rescore(r, "retry timeout", new[] { "text" })),
    new Stage("rank", r => Stages.Rank(r, "score")),
    new Stage("trim_to_budget", r => Stages.TrimToBudget(r, 60)));
var best = pipe.Run(Text.AsRecords(log));
Console.Write(Text.Join(best));
Console.WriteLine(Tokens.PythonJson(best.Select(c => ((Dictionary<string, object?>)c["chunk"]!)["start"]).ToList()));

// rank again on the offset to restore reading order before Join
var reading = Stages.Rank(best, r => ((Dictionary<string, object?>)r["chunk"]!)["start"], desc: false);
Console.Write(Text.Join(reading));
```

```text
ERROR timeout after retry
WARN retry limit reached
[54, 13]
WARN retry limit reached
ERROR timeout after retry
```

The cuts are the same as in Python and TypeScript: `by: "lines"` (the default)
ends a chunk after each `\n` (`\r\n` is one boundary, a lone `\r` is none),
`by: "paragraphs"` after each run of two or more newlines, `by: "size"` every
`size` code points (a required positive integer, valid only with this mode).
Every chunk keeps its trailing separator, so `Text.Join(Text.Split(Text.AsRecords(text)))`
returns `text` exactly; each chunk is a copy of its parent with the text replaced
and `{ index, start, end }` (all `long`) stored under `into` (default `"chunk"`).
Offsets and sizes count code points: a surrogate pair is one, never two. A record
whose field is not a string passes through untouched; an empty text produces no
chunks; a record that already has the `into` key throws `input.field_conflict`.
These methods check their input in every mode, not only inside `Strict.Begin()`:
a null list throws `input.not_list` and a null item `input.not_mapping`.
`AsRecords` accepts a string, a `Dictionary<string, object?>` or a list (any
non-string, non-`byte[]`, non-set, non-dictionary `IEnumerable`); `null`, `byte[]`,
a set or any other dictionary type throws `input.not_list`. `size` is an `int?`,
so the `size` errors that need a non-integer (a fraction, a bool) are reachable
only through the shared vectors, not through this signature.

`Rank` reorders the chunks by score. To restore reading order before `Join`, rank
again on the offset with a key function, as the example does (`desc: false`).

```csharp
using Contexel;

var paras = Text.Split(Text.AsRecords("intro\n\nbody one\nbody two\n\nend"), by: "paragraphs");
Console.WriteLine(Tokens.PythonJson(paras.Select(c => c["text"]).ToList()));
Console.WriteLine(Tokens.PythonJson(paras.Select(c =>
{
    var at = (Dictionary<string, object?>)c["chunk"]!;
    return new List<object?> { at["start"], at["end"] };
}).ToList()));
```

```text
["intro\n\n", "body one\nbody two\n\n", "end"]
[[0, 7], [7, 26], [26, 29]]
```

## Errors and strict mode
````

In `CHANGELOG.md`, replace this block:
<!-- OP replace-old path=CHANGELOG.md -->
```markdown
  2.x cannot target Python 3.9, so it checks against 3.10 and the Python 3.9
  test legs prove the runtime.

### Behavior changes
```
with:
<!-- OP replace-new -->
```markdown
  2.x cannot target Python 3.9, so it checks against 3.10 and the Python 3.9
  test legs prove the runtime.

### Added — payload stages (ADR-005, all three languages)
- `as_records`, `split` and `join` (TypeScript `asRecords`, `split`, `join`; C#
  `Text.AsRecords`, `Text.Split`, `Text.Join`) carry a log, a web page or a plain
  string through every existing stage and back. `as_records` turns a string, a
  mapping or a list into records; `split` cuts the text of each record into chunk
  records by lines, paragraphs or code points, keeping the trailing separator,
  the parent's fields and an `{index, start, end}` offset, so joining the chunks
  rebuilds the text byte for byte; `join` turns records back into one string.
  The boundaries are the same in all three languages: a line ends after `\n`
  only, a paragraph after a run of two or more newlines, and offsets and sizes
  count code points.
- They are new, so they check their input in every mode, not only in strict
  mode: a non-list raises `input.not_list`, a non-mapping item
  `input.not_mapping`, and a record that already has the `into` key raises
  `input.field_conflict`. `as_records` and `join` are the entry and exit
  points: call them outside `pipeline` (a strict pipeline rejects a stage that
  returns a string, naming it); `split` is an ordinary traced stage.
- Under `trace(id_field=...)`, `split` is attributed exactly: it keeps every id,
  so an empty-text record that vanishes is reported as dropped even beside
  id-less records that `split` expanded. (Without this the id-less allowance of
  Behavior change 8 would have hidden that drop.) The shared vectors pin it in
  all three languages.
- The shared vectors gain `as_records`, `join` and `text_pipeline` cases and
  accept `split` as a stage: 44 new cases (123 in all), among them raw log text
  through `as_records`, `split`, `dedupe`, `rescore`, `rank`, `trim_to_budget`
  and `join`, identical in all three languages and inside its token budget.

### Behavior changes
```

In `CHANGELOG.md`, replace this block:
<!-- OP replace-old path=CHANGELOG.md -->
```markdown
  commented-out `<Version>` or a `<PackageVersion>`/`<VersionPrefix>` override
  is not detected (none exist today).

### Tests
```
with:
<!-- OP replace-new -->
```markdown
  commented-out `<Version>` or a `<PackageVersion>`/`<VersionPrefix>` override
  is not detected (none exist today).
- Payload stages: the chunks of one parent share its id, so under
  `trace(id_field=...)` a chunk dropped by a later stage is reported under its
  parent's id and one stage's `dropped_ids` can list the same id more than once.
  `rank` reorders chunks by score; restoring reading order needs a key function
  over `chunk.start` (a dotted `rank` path is not supported). There are no
  overlapping windows and no token-sized chunks: they break losslessness or need
  a tokenizer all three languages share.
- Payload stages, per language: a "mapping" is a `Mapping` in Python, a plain
  object in TypeScript (a `Map`, `Set`, `Date`, typed array or class instance
  is `input.not_list` for `as_records`) and a `Dictionary<string, object?>` in
  C#; TypeScript has one number type, so it accepts `size: 2.0` as 2 where
  Python rejects the float; a lone surrogate counts as one code point in every
  language but lies outside the parity vectors.

### Tests
```

In `docs/adr/005-payload-stage-family.md`, replace this block:
<!-- OP replace-old path=docs/adr/005-payload-stage-family.md -->
```markdown
# ADR-005 — Non-record payloads: `as_records`, `split`, `join`

**Date:** 2026-11-19 · **Status:** proposed · **Deciders:** Chief Architect + human (public API addition)

## Context
```
with:
<!-- OP replace-new -->
```markdown
# ADR-005 — Non-record payloads: `as_records`, `split`, `join`

**Date:** 2026-11-19 · **Status:** accepted (2026-11-21, Slice 4) · **Deciders:** Chief Architect + human (public API addition)

## Context
```

In `docs/adr/005-payload-stage-family.md`, replace this block:
<!-- OP replace-old path=docs/adr/005-payload-stage-family.md -->
```markdown
- Invalidation triggers: a user need for overlap or token-sized chunks; a portable tokenizer.
```
with:
<!-- OP replace-new -->
```markdown
- Invalidation triggers: a user need for overlap or token-sized chunks; a portable tokenizer.

## Amendments at G2 (Slice 4 plan, 2026-11-21)
Decisions the design left open, each recorded in the Slice 4 plan as S4-1 to S4-8:
- **Ramps stay outside `pipeline`** (S4-1). `as_records` takes a non-list and
  `join` returns a string; a pipeline hands every stage a list, TypeScript and C#
  type it `Records -> Records`, and a strict pipeline rejects a stage that returns
  a non-list. They are called around a pipeline, as `merge` is.
- **Shape is checked in every mode, and before the configuration** (S4-2), through
  an internal `always` option of the existing strict wrapper.
- **A string-valued parent that already has `into` raises `input.field_conflict`,
  even when its text is empty; a record passed through (its field is not a
  string) is never checked** (S4-3).
- **`split` is attributed exactly under `trace`** (S4-4). Found while planning: the
  Slice 3 rule (`lost = max(0, unidentified_out - unidentified_in)`) read the
  id-less chunks of an expanded id-less record as ids lost by survivors and hid a
  real drop (ADR-008). `split` never removes an id, so it declares `keeps_ids`
  and `lost` is 0 for it.
- **"Mapping" is per language** (S4-5): `Mapping` in Python, a plain object in
  TypeScript, `Dictionary<string, object?>` in C#.
```

In `docs/adr/008-policy-fingerprint-and-trace-attribution.md`, replace this block:
<!-- OP replace-old path=docs/adr/008-policy-fingerprint-and-trace-attribution.md -->
```markdown
  (the built-in stages never do either). That is deliberate, since a reported
  drop is the safe side of the audit; such a stage should keep its ids.

## Alternatives considered
```
with:
<!-- OP replace-new -->
```markdown
  (the built-in stages never do either). That is deliberate, since a reported
  drop is the safe side of the audit; such a stage should keep its ids.
- **Stages that keep ids (Slice 4).** A stage that never removes the id field from a
  record it keeps can declare it (Python `traced(keeps_ids=True)`, TypeScript
  `traced(name, fn, { keepsIds: true })`, C# `Trace.Traced(..., keepsIds: true)`), and
  `lost` is then 0: every input id with no surviving record is reported dropped.
  Only `split` declares it, because it turns one record into several: an id-less
  parent's extra chunks would otherwise be read as ids lost by survivors and hide a
  real drop. All other stages keep the rule above.

## Alternatives considered
```

- [ ] **Step 5.4: Run everything**

```bash
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
cd ts && npm run build && npm test
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
python tools/site_check.py
python tools/check_versions.py
python -m ruff check contexel --no-cache
python -m mypy contexel --python-version 3.10 --no-incremental
```

Expected:

```text
673 passed
ℹ tests 528 / ℹ pass 528 / ℹ fail 0   (tsc clean)
Passed!  - Failed:     0, Passed:   464, Skipped:     0, Total:   464   (0 warnings)
checked 6 pages under site/ -> OK
check_versions: all 7 version locations say 0.1.17
All checks passed!
Success: no issues found in 9 source files
```

The README examples are executed, not eyeballed: if one drifts from the code, `test_readme_example_prints_what_the_readme_shows` fails.

- [ ] **Step 5.5: Commit**

```bash
git add tests/test_doc_examples.py ts/test/docs.test.ts csharp/Contexel.Tests/DocExampleTests.cs README.md site/stages.html ts/README.md csharp/Contexel/README.md CHANGELOG.md docs/adr/005-payload-stage-family.md docs/adr/008-policy-fingerprint-and-trace-attribution.md
git commit -m "docs: document the payload stages in all three languages"
```


## Close-out checks (after Task 5, before the gates)

Run and paste real output; a slice is done only when every line holds.

```bash
PYTHONPATH=. python -m pytest -q --ignore-glob='tests/test_doctrine_*'
cd ts && npm run build && npm test
dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
PYTHONPATH=. python parity/generate_vectors.py
git diff --exit-code parity/vectors.json && echo vectors-stable
python -m ruff check contexel --no-cache
python -m mypy contexel --python-version 3.10 --no-incremental
python tools/check_versions.py
python tools/site_check.py
git status --short                      # prints nothing
git log --format=%s main..HEAD | awk '{print length}' | sort -n | tail -1   # at most 72
git log --format=%B main..HEAD | grep -ci 'co-authored'                     # 0
git diff main..HEAD | grep -nEi '<your Windows user name>|C:.Users|AppData|@[a-z0-9-]+[.]' || echo privacy-clean
```

Expected:

```text
the three totals of the table below
vectors-stable
All checks passed!
Success: no issues found in 9 source files
check_versions: all 7 version locations say 0.1.17
checked 6 pages under site/ -> OK
(nothing)
(a number <= 72)
0
privacy-clean
```

| After | Python | TypeScript | C# | Vector cases |
|---|---|---|---|---|
| Baseline | 537 | 354 | 315 | 79 |
| Task 1 | 625 | 354 | 315 | 79 |
| Task 2 | 625 | 464 | 315 | 79 |
| Task 3 | 625 | 464 | 402 | 79 |
| Task 4 | 670 passed | 523 | 459 | 123 |
| Task 5 | 673 | 528 | 464 | 123 |

(The Python rise in Task 4 is the 44 new committed cases that `test_committed_case_matches_canon` replays plus one budget test.)

## Gates (after the last task)

G4 and G5 are fresh-context gates by independent reviewers; the controller does not review its own work.

1. **G4 whole-branch code review**, severity-ranked, against this plan and the brief (ACs 10 to 15, 34). Review focus: the six classes above; that no existing behavior changed (the 79 cases, the Slice 3 golden fingerprints, the unchanged default of `checked` and `traced`); that the three ports agree where the vectors cannot reach (TypeScript `__proto__` and inherited keys, C# `byte[]`, non-generic enumerables).
2. **G5 QA with mutation testing**, on a fresh copy per mutant (`python -B`, purge `__pycache__`, verify each mutant applied). Suggested mutants, each of which a test or a vector must kill: lines `pos + 1` to `pos`; `"\r"` or the wider `splitlines` set counted as a boundary; paragraphs `{2,}` to `{1,}` or `{3,}`, or the `\r?` dropped; size cut at `size - 1`, or counted in UTF-16 units (TypeScript, C#); the remainder chunk missing or doubled; empty text yielding one empty chunk; `index` starting at 1; `start` and `end` swapped; the `into` check removed, moved after the empty-text exit, or applied to pass-through records; a non-string field raising or being dropped; `always` ignored (strict-only checks); `keeps_ids` removed; `join` appending the separator after the last part, skipping `None`, or serializing strings; `as_records` copying the mapping, wrapping instead of keeping mapping items, accepting bytes; TypeScript `Object.hasOwn` to `in`, chunk built by plain assignment (`__proto__`); C# `IndexOf("\n")` (culture-sensitive) in place of `IndexOf('\n')`. Also run the randomized differential check of the three ports against the canon (generator, runners and comparer are scratch tools, not part of the repository: seeded cases for `split`, `join` and `as_records`, compared as canonical JSON).
3. **G5 security (recommended, not required by the master plan):** the new code reads untrusted text, so ask for a read-only review of the linear-time claim (adversarial separators, the paragraph regular expression), the TypeScript prototype hazards and the resource bound of one million characters.
4. **One fix wave, then one scoped re-review.** File the evidence under `docs/reviews/foundation-hardening-s4-*.md` and `docs/qa/foundation-hardening-s4-qa.md` (sanitized), update the Slice 4 row and the deviation log of `docs/plans/foundation-hardening.md`, and stop: pushing and merging are the human's.

## Replay result (how this plan was checked)

**Replay.** A script applied every block of Tasks 1 to 5, in document order, onto a fresh `git archive` of `ece5687`: per task the test files first (the red measurement), then the implementation files (the green measurement), running the Python, TypeScript and C# suites after each phase (vectors regenerated whenever the case table changed). At the end it compared every file the scratch tree changed with the replayed tree: **32 files compared, all identical** (the 31 files of the task blocks plus the regenerated `parity/vectors.json`).

| Task | Phase | Python | TypeScript | C# |
|---|---|---|---|---|
| 1 | tests | 1 collection error (`ImportError`) | | |
| 1 | implementation | 625 passed | | |
| 2 | tests | 625 | does not compile (no test runs) | |
| 2 | implementation | 625 | 464 pass | |
| 3 | tests | 625 | 464 | does not compile |
| 3 | implementation | 625 | 464 | 402 passed |
| 4 | tests (case table, vectors) | 670 passed | 508 tests, 44 fail | 446 tests, 44 fail |
| 4 | implementation (runners) | 670 | 523 pass | 459 passed |
| 5 | tests (doc tests) | 3 failed, 670 passed | 521 tests, 1 fail | 3 failed, 461 passed |
| 5 | implementation (docs) | 673 | 528 | 464 |

C# reported 0 warnings and TypeScript `tsc` was clean at every green.

**Other checks run on the scratch tree (the final state of all five tasks):**
- Python 673 passed; TypeScript 528 pass; C# 464 passed; `ruff`, `mypy`, `tools/site_check.py` and `tools/check_versions.py` clean.
- `parity/vectors.json`: 123 cases; regenerated twice with the same SHA-1 (also by Python 3.9); the 79 existing cases and every other section are byte-identical to the Slice 3 file.
- Python 3.9: every changed Python file compiles, the stages and the README example behave identically, and the vectors regenerate to the same hash. `pytest` is not installed for 3.9 here, so the full suite on 3.9 is left to CI.
- **Randomized differential run** (scratch tools, not part of the repository): seeded generators produced 4,000 `split` cases (random texts over an alphabet of newlines, carriage returns, astral and accented characters, the `splitlines` separators, a zero-width joiner; lengths up to 4,000; all three modes), 1,500 `join` cases (random JSON values, fields and separators) and 600 `as_records` cases per seed; the Python canon's answers were compared with the TypeScript and C# ports as canonical JSON. Two seeds (20261121 and 7), 12,200 cases in all, **0 mismatches** in either port.
- Mutation checks the two port implementers ran on their own tests, each reverted afterwards: in C#, offsets counted in UTF-16 units (9 tests failed), size cut in UTF-16 units (9), a paragraph run of one newline (8), `keepsIds` ignored (2), `always` ignored (6); in TypeScript, the paragraph run length, the surrogate handling and the code-point count (8 to 9 of its 110 tests each).

**Not verified here:** the three-operating-system CI matrix (Linux and macOS are not available on this machine), Python 3.10, the full pytest suite on Python 3.9, Node 18 and 20, and the first CI run of any of it. The plan's own gates (G4, G5 QA with mutation testing, the recommended security read) have not run: they follow execution.
