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
