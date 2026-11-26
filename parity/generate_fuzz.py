"""Seeded differential fuzz corpus for the cross-language parity suites (ADR-007, AC 36).

    python parity/generate_fuzz.py --out parity/fuzz-corpus.json [--seed N] [--cases N]
    python parity/generate_fuzz.py --seed N --show INDEX      # one case, to reproduce a divergence

The Python canon computes every expectation. The output is a ``cases`` file in
the format of ``parity/vectors.json`` (see ``parity_cases.py``), so the
TypeScript and C# suites replay it with the runners that already replay the
shared vectors (``ts/test/fuzz.test.ts``, ``csharp/Contexel.Tests/FuzzTests.cs``).
The corpus is generated, never committed (it is ignored by git).

The generator draws only from ``random.Random.random()``, the one method Python
guarantees to keep stable, so a seed gives the same corpus on every Python
version and operating system. Case ``i`` depends on ``(seed, i)`` alone: a
divergence is reproduced from its index without regenerating the rest.

The domain is the documented parity envelope (ADR-001 4a, ADR-002 3, ADR-007):
JSON data only, no NaN or Inf, no integer-valued floats (a score of 0.0 that a
later stage serializes is one: the case is redrawn), integers within 2**53, no
case-special characters (U+0130 among them), and astral letters only in the
``note`` field, which ``rescore`` never reads (the C# tokenizer margin of
ADR-006). A scalar item in a list of records appears only in cases that expect
``input.not_mapping``: a C# list holds mappings. Every redraw is counted in
``_meta.redrawn``; nothing is dropped silently.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from contexel import ContexelError, as_records, strict  # noqa: E402
from parity_cases import _pipe, assert_in_envelope, outcome  # noqa: E402

FORMAT = 1
DEFAULT_SEED = 20261126
DEFAULT_CASES = 20000
MAX_ATTEMPTS = 50

# ---------------------------------------------------------------------------
# Alphabets. Every character is written as a code point: this file has no
# non-ASCII source text and no backslash escapes.
# ---------------------------------------------------------------------------
LATIN1 = [chr(c) for c in (0xE9, 0xE8, 0xFC, 0xF1, 0xE5, 0xC9, 0xDC, 0xD1)]
BMP_CJK = [chr(c) for c in (0x65E5, 0x672C, 0x8A9E, 0x4E2D, 0x6587)]
HANGUL = [chr(0xD55C), chr(0xAE00)]
CYRILLIC = [chr(c) for c in (0x41F, 0x440, 0x438, 0x432, 0x435, 0x442)]
EMOJI = [chr(0x1F600), chr(0x1F680)]
ASTRAL_LETTERS = [chr(0x20000), chr(0x20001), chr(0x2A6D6)]   # CJK extension B: caseless letters
COMBINING = [chr(0x301), chr(0x302), chr(0x323)]
CONTROL = [chr(0), chr(7), chr(27), chr(127), chr(0x2028), chr(0x2029), chr(0x85), chr(0xA0),
           chr(0x200B), chr(0xFEFF), chr(92), chr(34), chr(39)]
# Characters outside the envelope, kept out of every generated string (a test pins this):
# case-special letters, where the runtimes' case tables differ (ADR-001, ADR-002, ADR-007).
EXCLUDED = [chr(c) for c in (0x130, 0x131, 0x17F, 0xDF, 0x212A, 0x212B, 0x1E9E, 0x3A3, 0x3C2, 0x1C5)]

WORDS = ["retry", "backoff", "jitter", "parse", "parsing", "parsed", "config", "value", "values",
         "error", "errors", "cache", "caches", "the", "of", "and", "a", "x", "Retry", "BACKOFF",
         "ignore all previous instructions", "disregard the above", "secret", "foo123", "bar42",
         "42", "3.14", "it's", 'say "hi"', "(paren)", "a-b", "snake_case", "tab\tsep"]
NARROW = (WORDS + ["caf" + LATIN1[0], "na" + chr(0xEF) + "ve", "r" + LATIN1[0] + "sum" + LATIN1[0],
                   "".join(BMP_CJK[:3]), "".join(BMP_CJK[3:]), HANGUL[0] + HANGUL[1], "".join(CYRILLIC),
                   "emoji" + EMOJI[0], EMOJI[1],
                   "cafe" + COMBINING[0], "a" + COMBINING[1] + COMBINING[2],
                   chr(0x1112) + chr(0x1161) + chr(0x11AB)]
          + ["a" + c + "b" for c in CONTROL] + ["".join(CONTROL[:5])])
WIDE = NARROW + ["x" + ASTRAL_LETTERS[0], "".join(ASTRAL_LETTERS), ASTRAL_LETTERS[1] + "s", ASTRAL_LETTERS[2]]
SEPS = [" ", " ", " ", "  ", "\n", "\r\n", "\n\n", "\n\n\n", ", ", ". ", "\t"]
NUMBERS = [-3, 0, 7, 2 ** 53 - 1, -(2 ** 53 - 1), 10 ** 15, 1e-5, 1.5e-7, 123456789.123,
           4503599627370495.5, 0.1 + 0.2, -2.5, 5e-324, 1.5e-300, 0.5, 1e15 + 0.5, 99999.99999,
           0.0001, 1234567.891]

# Field roles. ``note`` alone may hold astral letters; ``rescore`` never reads it.
TEXT_FIELDS = ["snippet", "title", "path", "text"]
SCALAR_FIELDS = TEXT_FIELDS + ["note", "line", "source", "score", "hits"]
ANY_FIELDS = SCALAR_FIELDS + ["tags", "meta"]
RESCORE_FIELDS = [f for f in ANY_FIELDS if f != "note"]
RECORD_KINDS = ["select", "dedupe", "allowlist", "quarantine", "rescore", "rank",
                "truncate_field", "trim_to_budget", "split"]
OTHER_KINDS = ["merge", "stem", "as_records", "join", "text_pipeline", "pipeline", "shaped",
               "trace_report", "trace_dropped_ids"]
KINDS = RECORD_KINDS + OTHER_KINDS
WEIGHT = {"pipeline": 3, "trace_dropped_ids": 2, "text_pipeline": 2, "shaped": 1, "trace_report": 1}
NO_ITEM_CHECK = ("merge", "stem", "as_records", "text_pipeline")


class Gen:
    """Draws from ``random()`` alone (see the module docstring)."""

    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed).random

    def below(self, n: int) -> int:
        return int(self._random() * n)

    def between(self, lo: int, hi: int) -> int:
        return lo + self.below(hi - lo + 1)

    def chance(self, p: float) -> bool:
        return self._random() < p

    def choice(self, seq: Sequence[Any]) -> Any:
        return seq[self.below(len(seq))]

    def sample(self, seq: Sequence[Any], k: int) -> List[Any]:
        pool = list(seq)
        return [pool.pop(self.below(len(pool))) for _ in range(min(k, len(pool)))]

    def pick(self, seq: Sequence[Any], lo: int = 1, hi: int = 3) -> List[Any]:
        return self.sample(seq, self.between(lo, hi))

    def real(self) -> float:
        return self._random()


def text(g: Gen, lo: int = 0, hi: int = 12, wide: bool = False) -> str:
    pool = WIDE if wide else NARROW
    return "".join(g.choice(pool) + g.choice(SEPS) for _ in range(g.between(lo, hi)))


def fraction(g: Gen) -> float:
    value = round(g.real() * 10 + 0.001, 3)
    return value + 0.001 if value.is_integer() else value


def number(g: Gen) -> Any:
    return g.choice(NUMBERS) if g.chance(0.5) else g.choice([g.between(0, 9), fraction(g)])


def record(g: Gen) -> Dict[str, Any]:
    rec: Dict[str, Any] = {
        "path": g.choice(["src/a.py", "src/b.py", "docs/guide.md", "tests/t.py", "web/x.txt"]),
        "line": g.between(1, 6),
        "source": g.choice(["repo", "docs", "web", None]),
        "snippet": text(g, 0, 8),
        "title": text(g, 0, 3),
        "note": text(g, 0, 4, wide=True),
        "text": text(g, 0, 12),
        "score": number(g),
        "hits": number(g),
        "tags": g.choice([[], ["a"], ["a", "b"]]),
        "meta": g.choice([{}, {"k": 1}, {"k": {"z": None}}, {"k": [1, 2.5, "s"]}]),
    }
    for key in list(rec):
        if g.chance(0.12):
            del rec[key]
    return rec


def records(g: Gen) -> List[Dict[str, Any]]:
    limit = 24 if g.chance(0.06) else 8
    out: List[Dict[str, Any]] = []
    for _ in range(g.between(0, limit)):
        if out and g.chance(0.2):
            out.append(json.loads(json.dumps(g.choice(out))))      # an exact duplicate
        else:
            out.append(record(g))
    return out


# ---------------------------------------------------------------------------
# Stage arguments: valid ones, and a table of invalid ones for the error cases.
# ---------------------------------------------------------------------------
def args_for(kind: str, g: Gen) -> Dict[str, Any]:
    if kind == "select":
        return {"fields": g.pick(ANY_FIELDS + ["nope"], 1, 4)}
    if kind == "dedupe":
        return {"key": g.choice([None, g.choice(SCALAR_FIELDS), g.pick(SCALAR_FIELDS, 1, 2)])}
    if kind == "allowlist":
        pool = ["repo", "docs", "web", None, 1, 2, 3, 0, True, False, 2.5, "a", "src/a.py"]
        return {"field": g.choice(["source", "line", "score", "hits", "title", "path"]),
                "allowed": g.choice([g.sample(pool, g.between(1, 4)), g.choice(["repo", "docs"])])}
    if kind == "quarantine":
        a: Dict[str, Any] = {"fields": g.pick(ANY_FIELDS, 1, 3)}
        if g.chance(0.4):
            a["patterns"] = g.pick(["secret", r"foo\d+", r"b(a|o)r", r"[A-Z]{3,}", "42"], 1, 2)
            if g.chance(0.5):
                a["replace_patterns"] = True
        if g.chance(0.4):
            a["action"] = g.choice(["drop", "flag"])
        if g.chance(0.15):
            a["into"] = g.choice(["flagged", "q"])
        if g.chance(0.3):
            a["normalize"] = g.choice([None, "nfc"])
        return a
    if kind == "rescore":
        a = {"query": g.choice([text(g, 1, 3), [g.choice(NARROW), g.choice(NARROW)], g.choice(NARROW)]),
             "fields": g.pick(RESCORE_FIELDS, 1, 3)}
        if g.chance(0.2):
            a["into"] = g.choice(["rel", "s2"])
        if g.chance(0.3):
            a["proximity"] = g.choice([True, False])
        if g.chance(0.4):
            a["match"] = g.choice(["word", "stem"])
        if g.chance(0.3):
            a["normalize"] = g.choice([None, "nfc"])
        return a
    if kind == "rank":
        return {"by": g.choice(["score", "line", "hits", "title", "path", "note"]),
                "desc": g.choice([True, False])}
    if kind == "truncate_field":
        a = {"field": g.choice(TEXT_FIELDS + ["note"]), "max_tokens": g.between(0, 20)}
        if g.chance(0.3):
            a["suffix"] = g.choice(["...", "~", chr(0x2026), ""])
        return a
    if kind == "trim_to_budget":
        a = {"max_tokens": g.between(0, 1500 if g.chance(0.2) else 400)}
        if g.chance(0.4):
            a["min_records"] = g.between(0, 3)
        return a
    if kind == "split":
        by = g.choice(["lines", "paragraphs", "size"])
        a = {"field": g.choice(["text", "snippet", "note"]), "by": by}
        if by == "size":
            a["size"] = g.between(1, 30)
        if g.chance(0.2):
            a["into"] = g.choice(["c", "part"])
        return a
    raise AssertionError(kind)


BAD_ARGS: Dict[str, List[Dict[str, Any]]] = {
    "select": [{"fields": []}, {"fields": "a"}],
    "dedupe": [{"key": []}, {"key": ""}],
    "allowlist": [{"field": "", "allowed": ["x"]}, {"field": "source", "allowed": []}],
    "quarantine": [{"fields": ["snippet"], "action": "allow"}, {"fields": []},
                   {"patterns": ["("]}, {"normalize": "NFC"}],
    "rescore": [{"query": "x", "match": "fuzzy"}, {"query": "x", "normalize": "nfd"}],
    "rank": [{"by": ""}],
    "truncate_field": [{"field": "snippet", "max_tokens": -1}, {"field": "", "max_tokens": 3}],
    "trim_to_budget": [{"max_tokens": -5}, {"max_tokens": 5, "min_records": -1}],
    "split": [{"by": "words"}, {"by": "size"}, {"by": "lines", "size": 3}, {"by": "size", "size": 0}],
}


def stage_args(kind: str, g: Gen, error_rate: float) -> Dict[str, Any]:
    return g.choice(BAD_ARGS[kind]) if g.chance(error_rate) else args_for(kind, g)


def specs(g: Gen, lo: int = 1, hi: int = 5) -> List[Dict[str, Any]]:
    kinds = [g.choice(RECORD_KINDS) for _ in range(g.between(lo, hi))]
    return [{"stage": k, "args": stage_args(k, g, 0.06)} for k in kinds]


STEMS = ["pars", "test", "load", "stop", "plan", "class", "stat", "quer", "stud", "valu", "fil", "run",
         "hit", "log", "need", "string", "bu", "gla"]
ENDS = ["", "s", "es", "ies", "ied", "ing", "ed", "ings", "eds", "ss", "us", "is", "e", "y", "ly"]


def stem_words(g: Gen) -> List[str]:
    out = []
    for _ in range(g.between(1, 12)):
        word = g.choice(STEMS) + g.choice(ENDS)
        if g.chance(0.15):
            word = word + word[-1] + g.choice(["ing", "ed"])
        out.append(word.upper() if g.chance(0.1) else word)
    return out


def payload(g: Gen) -> Any:
    return g.choice([
        text(g, 0, 30),
        [text(g, 0, 6) for _ in range(g.between(0, 4))],
        [record(g) for _ in range(g.between(0, 3))],
        record(g),
        [text(g, 0, 4), record(g), g.between(0, 9), None, [1, "a"]],
    ])


def draw_case(seed: int, index: int, attempt: int) -> Dict[str, Any]:
    g = Gen((seed * 1_000_003 + index) * 101 + attempt)
    kind = g.choice([k for k in KINDS for _ in range(WEIGHT.get(k, 2))])
    cid = "fuzz/%d/%05d/%s" % (seed, index, kind)
    if kind in RECORD_KINDS:
        case = {"id": cid, "stage": kind, "args": stage_args(kind, g, 0.15), "input": records(g)}
        return with_strict(case, g)
    if kind == "merge":
        args: Dict[str, Any] = {}
        if g.chance(0.6):
            args["schema"] = {"title": ["title", "path"], "url": ["source", "path"]}
            if g.chance(0.5):
                args["dedupe_key"] = g.choice(["title", "url"])
        return {"id": cid, "stage": kind, "args": args,
                "input": [records(g) for _ in range(g.between(0, 3))]}
    if kind == "stem":
        return {"id": cid, "stage": kind, "args": {}, "input": stem_words(g)}
    if kind == "as_records":
        return {"id": cid, "stage": kind,
                "args": {} if g.chance(0.7) else {"field": g.choice(["t", "body"])}, "input": payload(g)}
    if kind == "join":
        return {"id": cid, "stage": kind,
                "args": {"field": g.choice(["text", "snippet"]), "sep": g.choice(["", "\n", " | "])},
                "input": records(g)}
    if kind == "text_pipeline":
        args = {"stages": specs(g, 1, 4)}
        if g.chance(0.5):
            args["field"] = g.choice(["text", "snippet"])
        if g.chance(0.5):
            args["sep"] = g.choice(["", "\n"])
        return {"id": cid, "stage": kind, "args": args, "input": payload(g)}
    if kind in ("pipeline", "shaped"):
        return with_strict({"id": cid, "stage": kind, "args": {"stages": specs(g)}, "input": records(g)}, g)
    args = {"stages": specs(g)}
    if kind == "trace_dropped_ids":
        args["id_field"] = g.choice(["path", "title", "line"])
    elif g.chance(0.6):
        args["id_field"] = g.choice(["path", "title"])
    return {"id": cid, "stage": kind, "args": args, "input": records(g)}


def with_strict(case: Dict[str, Any], g: Gen) -> Dict[str, Any]:
    """A quarter of the cases run in strict mode; some of those carry a scalar or null item."""
    if g.chance(0.25):
        case["strict"] = True
        if case["input"] and g.chance(0.4):
            case["input"].insert(g.below(len(case["input"]) + 1), g.choice([None, 5, "x"]))
    return case


# ---------------------------------------------------------------------------
# The envelope, and the canon's outcome.
# ---------------------------------------------------------------------------
def outside_envelope(case: Dict[str, Any], got: Dict[str, Any]) -> Optional[str]:
    """Why a case lies outside the parity envelope, or None. Besides the input, the arguments and
    the expectation, every intermediate output of a pipeline is checked: a score of 0.0 that a
    later stage serializes costs a different token count in TypeScript."""
    for part, where in ((case["input"], "input"), (case["args"], "args"), (got.get("expect"), "expect")):
        try:
            assert_in_envelope(part, where)
        except AssertionError as error:
            return "%s: %s" % (where, str(error).split(": ", 1)[1][:40])
    stages = case["args"].get("stages")
    if not stages or case["stage"] == "merge":
        return None
    records_in = case["input"]
    if case["stage"] == "text_pipeline":
        records_in = as_records(records_in, case["args"].get("field", "text"))
    for count in range(1, len(stages) + 1):
        try:
            if case.get("strict"):
                with strict():
                    out = _pipe(stages[:count])(json.loads(json.dumps(records_in)))
            else:
                out = _pipe(stages[:count])(json.loads(json.dumps(records_in)))
        except ContexelError:
            return None
        try:
            assert_in_envelope(out, "stage %d" % count)
        except AssertionError as error:
            return "intermediate: %s" % str(error).split(": ", 1)[1][:40]
    return None


def only_mappings_or_not_mapping_error(case: Dict[str, Any], got: Dict[str, Any]) -> bool:
    if case["stage"] in NO_ITEM_CHECK or all(isinstance(i, dict) for i in case["input"]):
        return True
    return got.get("expect_error", {}).get("code") == "input.not_mapping"


def make_case(seed: int, index: int, redrawn: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Case ``index`` of the corpus for ``seed``: the first draw that lies inside the envelope,
    with the canon's outcome. Each redraw is counted in ``redrawn`` by reason."""
    redrawn = redrawn if redrawn is not None else {}
    for attempt in range(MAX_ATTEMPTS):
        case = draw_case(seed, index, attempt)
        try:
            got = outcome(case, [])
        except ContexelError:
            raise
        except Exception as error:   # the canon raised something that is not a contexel error
            reason = "canon raised %s" % type(error).__name__
            redrawn[reason] = redrawn.get(reason, 0) + 1
            continue
        if not only_mappings_or_not_mapping_error(case, got):
            case["input"] = [i for i in case["input"] if isinstance(i, dict)]
            got = outcome(case, [])
        reason = outside_envelope(case, got)
        if reason is None:
            return {**case, **got}
        redrawn[reason] = redrawn.get(reason, 0) + 1
    raise AssertionError("no case inside the envelope for seed %d index %d" % (seed, index))


def build(seed: int = DEFAULT_SEED, count: int = DEFAULT_CASES) -> Dict[str, Any]:
    redrawn: Dict[str, int] = {}
    cases = [make_case(seed, i, redrawn) for i in range(count)]
    kinds: Dict[str, int] = {}
    codes: Dict[str, int] = {}
    for c in cases:
        kinds[c["stage"]] = kinds.get(c["stage"], 0) + 1
        if "expect_error" in c:
            code = c["expect_error"]["code"]
            codes[code] = codes.get(code, 0) + 1
    meta = {"format": FORMAT, "generated_by": "parity/generate_fuzz.py (python contexel canon)",
            "adr": "docs/adr/007-vector-format-v2-and-differential-fuzz.md",
            "seed": seed, "case_count": len(cases), "kind_counts": dict(sorted(kinds.items())),
            "error_codes": dict(sorted(codes.items())), "strict_cases": sum(1 for c in cases if c.get("strict")),
            "redrawn": dict(sorted(redrawn.items()))}
    return {"_meta": meta, "cases": cases}


def dumps(corpus: Dict[str, Any]) -> str:
    return json.dumps(corpus, ensure_ascii=True, separators=(",", ":")) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--cases", type=int, default=DEFAULT_CASES)
    parser.add_argument("--out", help="write the corpus to this file")
    parser.add_argument("--show", type=int, metavar="INDEX", help="print case INDEX of the seed and exit")
    args = parser.parse_args(argv)
    if args.show is not None:
        print(json.dumps(make_case(args.seed, args.show), indent=1, ensure_ascii=True))
        return 0
    if not args.out:
        parser.error("--out is required (or --show INDEX)")
    corpus = build(args.seed, args.cases)
    with open(args.out, "wb") as handle:
        handle.write(dumps(corpus).encode("ascii"))
    meta = corpus["_meta"]
    print("wrote %d cases (seed %d) to %s; %d error cases, %d strict, %d redrawn"
          % (meta["case_count"], args.seed, args.out, sum(meta["error_codes"].values()),
             meta["strict_cases"], sum(meta["redrawn"].values())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
