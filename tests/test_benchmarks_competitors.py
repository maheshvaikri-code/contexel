"""AC 23, 24, 25: the inflected episodes, the hand-written baselines and the
computed operation counts of the competitor comparison. Nothing here needs the
network or the dataset."""
import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

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
    # the golden targets: a change to the seed or to the order of the random calls moves them
    assert [ep["target"] for ep in plain] == [
        ("p/f28.py", "fn28"), ("p/f35.py", "fn35"), ("p/f29.py", "fn29"),
        ("p/f39.py", "fn39"), ("p/f32.py", "fn32"),
    ]


# SHA-256 of json.dumps([[target, terms], ...]) over the 100 default episodes of the real,
# verified dataset: the episodes every published outcome figure is measured on.
REAL_EPISODES_SHA256 = "61b29d1f116a07e0d231be42596e96bd04a6b76286f4c14d72971d6c10b33b9e"


def test_the_real_default_episodes_are_the_published_ones():
    from benchmarks import fetch_dataset

    if not fetch_dataset.DATA_FILE.exists():
        pytest.skip("the dataset cache is not downloaded (CI never downloads it)")
    episodes = competitors.build_episodes(fetch_dataset.load())
    assert len(episodes) == competitors.N_EPISODES
    pairs = json.dumps([[ep["target"], ep["terms"]] for ep in episodes])
    assert hashlib.sha256(pairs.encode("utf-8")).hexdigest() == REAL_EPISODES_SHA256


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
    # the query is tokenized like the record: "value." is the word "value" (alone, not
    # masked by a duplicate term); an untokenized query would score 0 here
    assert competitors.g_score_overlap([records[0]], ["value."])[0]["score"] == 1


def _hit(path, snippet, score):
    return {"path": path, "symbol": path[:-3], "snippet": snippet, "score_strong": score,
            "score_weak": score, "repo": "r", "url": "u", "language": "python"}


def test_outcomes_of_no_episodes_are_a_clear_error():
    with pytest.raises(ValueError, match="at least one episode"):
        competitors.native_outcomes([])
    with pytest.raises(ValueError, match="at least one episode"):
        competitors.inflected_outcomes([])


def test_the_inflected_outcomes_measure_word_and_stem_matching():
    # 80 decoys the tool ranks first fill the budget; only the query can lift the target
    hits = [_hit(f"d{i}.py", "build the cache entry for the worker queue and flush it", 50)
            for i in range(80)] + [_hit("t.py", "parse the header block", 1)]
    episode = {"target": ("t.py", "t"), "terms": ["parse"], "inflected": ["parsing"], "hits": hits}
    result = competitors.inflected_outcomes([episode])
    rows = {r["shaper"]: r for r in result["rows"]}
    assert result["episodes"] == 1 and result["terms"] == 1 and result["examples"] == [["parse", "parsing"]]
    assert rows["contexel"]["recall_original_pct"] == 100.0
    assert rows["contexel"]["recall_inflected_pct"] == 0.0      # exact words miss "parsing"
    assert rows["contexel (match=stem)"]["recall_inflected_pct"] == 100.0  # the stemmer reaches it
    assert rows["hand-written (term overlap)"]["recall_inflected_pct"] == 0.0
    assert rows["hand-written"]["recall_original_pct"] == rows["hand-written"]["recall_inflected_pct"] == 0.0


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


def test_an_inflection_is_never_a_word_of_the_path_or_symbol_either():
    # the shapers score snippet, symbol AND path: the guard must see all three.
    # "results" -> "result" is a word of the path only, not of the code or docstring
    corpus = _corpus()
    for row in corpus:
        row["func_path_in_repository"] = f"p/f{row['func_name'][2:]}_result.py"
    episodes = competitors.build_inflected_episodes(corpus, n=5)
    assert episodes
    by_key = {(r["func_path_in_repository"], r["func_name"]): r for r in corpus}
    for ep in episodes:
        assert "results" not in ep["terms"]
        row = by_key[ep["target"]]
        seen = inflection.words(" ".join((
            row["func_documentation_string"], row["func_name"], row["func_path_in_repository"])))
        assert not set(ep["inflected"]) & seen
