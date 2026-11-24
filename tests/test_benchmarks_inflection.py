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
