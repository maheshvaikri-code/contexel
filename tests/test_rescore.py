from contexel import rescore


RECORDS = [
    {"id": 1, "snippet": "alpha beta"},          # covers both terms
    {"id": 2, "snippet": "alpha alpha alpha"},   # repeats one term
    {"id": 3, "snippet": "gamma"},               # matches nothing
]


def test_coverage_beats_repetition():
    scored = rescore(RECORDS, "alpha beta")
    by_id = {r["id"]: r["score"] for r in scored}
    assert by_id[1] > by_id[2] > by_id[3] == 0.0


def test_rare_terms_weigh_more():
    records = [
        {"id": 1, "snippet": "common rare"},
        {"id": 2, "snippet": "common"},
        {"id": 3, "snippet": "common"},
    ]
    scored = {r["id"]: r["score"] for r in rescore(records, "common rare")}
    # both match "common"; only id 1 adds the rarer, higher-idf term
    assert scored[1] > scored[2] == scored[3] > 0.0


def test_query_as_term_sequence_and_custom_fields():
    records = [{"name": "retry backoff", "snippet": ""}, {"name": "parser", "snippet": ""}]
    scored = rescore(records, ["retry", "backoff"], fields=("name",), into="rel")
    assert scored[0]["rel"] > scored[1]["rel"] == 0.0
    assert "rel" in scored[0] and "score" not in scored[0]


def test_deterministic_and_non_mutating():
    a = rescore(RECORDS, "alpha beta")
    b = rescore(RECORDS, "alpha beta")
    assert a == b
    assert "score" not in RECORDS[0]  # input untouched


def test_empty_query_scores_zero():
    assert all(r["score"] == 0.0 for r in rescore(RECORDS, ""))


def test_word_matching_ignores_morphological_decoys():
    records = [
        {"id": 1, "snippet": "return random value"},
        {"id": 2, "snippet": "returns randomly values"},
    ]
    word = {r["id"]: r["score"] for r in rescore(records, "random value")}
    assert word[1] > 0.0 and word[2] == 0.0  # exact tokens, like BM25/Lucene
    sub = {r["id"]: r["score"] for r in rescore(records, "random value",
                                                match="substring")}
    assert sub[2] > 0.0  # substring mode stays available


def test_word_matching_splits_snake_case():
    records = [{"symbol": "random_vector", "snippet": ""}]
    assert rescore(records, "random", fields=("symbol",))[0]["score"] > 0.0
