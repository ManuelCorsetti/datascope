import pandas as pd

from datascope.semantic import infer_semantic_type


def _type(series, name="col"):
    return infer_semantic_type(pd.Series(series), name)[0]


def test_empty_column():
    assert _type([None, None]) == "empty"


def test_constant_column():
    assert _type([1, 1, 1]) == "constant"


def test_boolean_dtype():
    assert _type(pd.array([True, False, True], dtype="boolean")) == "boolean"


def test_two_value_bool_like_strings():
    assert _type(["yes", "no", "yes", "no"]) == "boolean"


def test_two_value_non_bool_like_is_binary_categorical():
    assert _type(["north", "south", "north"]) == "binary_categorical"


def test_datetime_dtype():
    assert _type(pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"])) == "datetime"


def test_datetime_string_detected():
    t = _type(["2020-01-01", "2020-02-01", "2020-03-01", "2020-04-01", "2020-05-01"] * 5)
    assert t == "datetime_string"


def test_numeric_identifier_by_name():
    values = list(range(100))
    assert _type(values, name="customer_id") == "identifier"


def test_numeric_continuous_without_id_name():
    values = [x * 1.1 for x in range(100)]
    assert _type(values, name="amount") == "continuous_numeric"


def test_low_cardinality_numeric_is_discrete_categorical():
    assert _type([1, 2, 3, 1, 2, 3, 1, 2, 3] * 5, name="tier") == "discrete_numeric_categorical"


def test_string_identifier_high_uniqueness_short_values():
    values = [f"ID{i:05d}" for i in range(200)]
    assert _type(values, name="record_id") == "identifier"


def test_free_text_long_values():
    values = [f"This is a fairly long free-text note about record number {i} with detail." for i in range(50)]
    assert _type(values, name="notes") == "free_text"


def test_categorical_low_cardinality_strings():
    assert _type(["red", "green", "blue", "red", "green"] * 10, name="color") == "categorical"


def test_high_cardinality_text_fallback():
    # 100 distinct values spread over 300 rows: too many distinct values to
    # be "categorical", too repeated (33% unique) to be an identifier.
    values = [f"val-{i % 100}" for i in range(300)]
    assert _type(values, name="misc") == "high_cardinality_text"


def test_ordinal_hint_note_present_for_tier_like_names():
    _, _, notes = infer_semantic_type(pd.Series([1, 2, 3, 1, 2, 3] * 5), "priority_level")
    assert any("ordinal" in n.lower() for n in notes)
