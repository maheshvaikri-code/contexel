"""A small, frozen English suffix stemmer (ADR-006, ``docs/stemmer-rules.md``).

``rescore(match="stem")`` reduces every word to a stem before counting, so
``parse``, ``parses``, ``parsed`` and ``parsing`` count as one term. The rules
are a short, ordered list that the TypeScript and C# ports repeat exactly: the
result is pinned by shared vectors, never by "close enough".

The stemmer is FROZEN: a future improvement ships under a new ``match`` name,
never by editing these rules. It is English only, it is not a lemmatizer
(``configure`` and ``config`` stay apart, ``speed`` becomes ``spe``), and it
expects lower-case input (``rescore`` lower-cases first; a suffix rule is
case-sensitive, so an upper-case word is returned unchanged). Lengths are
counted in code points. It never raises and never makes a word longer.
"""
from __future__ import annotations

_VOWELS = "aeiouy"
#: a doubled letter from this set loses one copy after "ing"/"ed" is stripped
#: (running -> run, stopped -> stop); "l", "s" and "z" keep both (falling, passed)
_UNDOUBLE = "bcdfghjkmnpqrtvwx"


def stem(word: str) -> str:
    """Return the stem of an already lower-case ``word``."""
    if len(word) <= 3:
        return word
    w = word
    # 1. plurals: the first rule that applies wins
    if w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("ied") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("s") and not w.endswith(("ss", "us", "is")):
        w = w[:-1]
    # 2. "ing" or "ed", never both: the one the word ends with is the only
    #    one considered; it is stripped only if a vowel-bearing base of at
    #    least three code points remains
    if w.endswith("ing"):
        suffix = "ing"
    elif w.endswith("ed"):
        suffix = "ed"
    else:
        suffix = ""
    if suffix:
        base = w[: -len(suffix)]
        if len(base) >= 3 and any(c in _VOWELS for c in base):
            w = base
            if w[-1] == w[-2] and w[-1] in _UNDOUBLE:
                w = w[:-1]
    # 3. a final "e"
    if len(w) > 3 and w.endswith("e"):
        w = w[:-1]
    return w
