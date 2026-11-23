"""The frozen English stemmer (ADR-006, docs/stemmer-rules.md; brief AC 17, 18).

``stem`` is not part of the public API (``from contexel.stem import stem``):
``rescore(match="stem")`` is how it is used. These tests pin the rules, the
documented limits and the promise that it never raises and never grows a word.
"""
import itertools
import random
import re
import types
from pathlib import Path

import pytest

from contexel.stem import stem

ASTRAL = chr(0x1D49C)  # one code point, two UTF-16 units
E_ACUTE = chr(0xE9)

FAMILIES = [
    ["parse", "parses", "parsed", "parsing"],
    ["value", "values", "valued"],
    ["query", "queries", "queried", "querying"],
    ["try", "tries", "tried", "trying"],
    ["file", "files", "filed", "filing"],
    ["code", "codes", "coded", "coding"],
    ["test", "tests", "tested", "testing"],
    ["run", "runs", "running"],
    ["stop", "stops", "stopped", "stopping"],
    ["return", "returns", "returned", "returning"],
    ["class", "classes"],
    ["match", "matches", "matched", "matching"],
    ["request", "requests", "requested", "requesting"],
    ["error", "errors"],
    ["index", "indexes", "indexed", "indexing"],
    ["cache", "caches", "cached", "caching"],
]


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f[0])
def test_stem_families_unify(family):
    assert len({stem(word) for word in family}) == 1


def test_the_parse_family_stems_to_pars():
    assert [stem(w) for w in FAMILIES[0]] == ["pars"] * 4


# every rule, in the order the rules apply, with the word that exercises it
RULES = [
    ("sses", "glasses", "glass"),
    ("ies", "queries", "query"),
    ("ied", "queried", "query"),
    ("s", "tests", "test"),
    ("ing", "testing", "test"),
    ("ed", "tested", "test"),
    ("undoubling", "stopped", "stop"),
    ("final e", "value", "valu"),
    # a rule that does not apply falls through to the next one
    ("ies, four letters: the plural s rule", "ties", "tie"),
    ("ied, four letters: no vowel-bearing base of three letters", "tied", "tied"),
    # protected endings and short words
    ("ss is not a plural", "class", "class"),
    ("us is not a plural", "status", "status"),
    ("is is not a plural", "analysis", "analysis"),
    ("three letters or fewer", "bus", "bus"),
    ("base must keep three letters", "need", "need"),
    ("base must keep a vowel", "string", "string"),
    ("l is not undoubled", "falling", "fall"),
    ("s is not undoubled", "passed", "pass"),
    ("only one of ing and ed is stripped", "feeding", "feed"),
    ("digits are letters to the rules", "2020s", "2020"),
]


@pytest.mark.parametrize("name,word,expected", RULES, ids=[r[0] for r in RULES])
def test_each_rule(name, word, expected):
    assert stem(word) == expected


LIMITS = [
    # documented in docs/stemmer-rules.md: the price of a small frozen rule set
    ("configure", "configur"),  # is not "config"
    ("config", "config"),
    ("speed", "spe"),
    ("news", "new"),
    ("using", "using"),
    ("series", "sery"),
    ("species", "specy"),
    ("bias", "bia"),
]


@pytest.mark.parametrize("word,expected", LIMITS)
def test_stem_documented_limits(word, expected):
    assert stem(word) == expected


def test_stem_expects_lower_case_input():
    # the suffix rules are case-sensitive: an upper-case suffix is not
    # recognized, a lower-case one is stripped from whatever base it follows
    assert stem("PARSING") == "PARSING"
    assert stem("Parsing") == "Pars"


def test_stem_short_words_unchanged():
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789" + E_ACUTE + ASTRAL
    for n in range(4):
        for letters in itertools.product(alphabet, repeat=n):
            word = "".join(letters)
            assert stem(word) == word


def test_stem_counts_code_points_not_utf16_units():
    # an astral letter is ONE code point: these words are three or four code
    # points long, so the length rules treat them as the short words they are
    assert stem(ASTRAL + "as") == ASTRAL + "as"       # 3 code points: unchanged
    assert stem(ASTRAL + "aing") == ASTRAL + "aing"   # base of 2 code points
    assert stem(ASTRAL + "ies") == ASTRAL + "ie"      # 4 code points: plural s rule
    assert stem(ASTRAL * 2 + "ies") == ASTRAL * 2 + "y"  # 5 code points: ies -> y
    assert stem(ASTRAL + "aaing") == ASTRAL + "aa"    # base of 3 code points, has a vowel


def test_stem_never_raises_and_never_grows():
    rng = random.Random(20261123)
    alphabet = ("abcdefghijklmnopqrstuvwxyz" * 2 + "0123456789 _-" + "ABCSEING"
                + E_ACUTE + chr(0x4E2D) + chr(0x1F600) + ASTRAL + chr(0xD800))
    for _ in range(50_000):
        word = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 12)))
        out = stem(word)
        assert isinstance(out, str)
        assert len(out) <= len(word)
        assert (out == "") == (word == "")


def test_stem_is_not_part_of_the_public_api():
    # ruling S5-1: the stemmer is reached through rescore(match="stem") and the
    # module, never through the package namespace
    import contexel

    assert "stem" not in contexel.__all__
    assert isinstance(contexel.stem, types.ModuleType)


def test_the_rule_table_examples_are_what_the_stemmer_returns():
    doc = (Path(__file__).resolve().parent.parent / "docs" / "stemmer-rules.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([^`]*)` \| `([^`]*)` \|$", doc, flags=re.MULTILINE)
    assert len(rows) >= 40, "the rule document lost its worked examples"
    for word, expected in rows:
        assert stem(word) == expected, (word, expected)
