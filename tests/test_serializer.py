from contexel import tokens, trim_to_budget


def teardown_function():
    tokens.set_serializer(None)


def test_default_serializer_is_canonical_json():
    assert tokens.serialize({"b": 2, "a": 1}) == '{"a": 1, "b": 2}'


def test_strings_bypass_the_serializer():
    tokens.set_serializer(lambda value: "should never be used")
    assert tokens.serialize("as-is") == "as-is"
    assert tokens.count("abcd" * 3) == 3  # 12 chars -> 3 tokens (heuristic)


def test_set_serializer_changes_counting_and_reset_restores_json():
    record = {"text": "x" * 400}
    baseline = tokens.count(record)
    tokens.set_serializer(lambda value: "tiny")
    assert tokens.count(record) == tokens.count("tiny")
    tokens.set_serializer(None)
    assert tokens.count(record) == baseline


def test_trim_to_budget_prices_records_via_serializer():
    records = [{"text": "word " * 40} for _ in range(50)]
    kept_json = len(trim_to_budget(records, max_tokens=500))
    assert kept_json < 50  # JSON pricing cannot fit them all

    tokens.set_serializer(lambda value: "cheap")  # every record ~1 token
    kept_cheap = len(trim_to_budget(records, max_tokens=500))
    assert kept_cheap == 50  # cheaper encoding -> same budget holds them all
