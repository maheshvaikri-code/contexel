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
