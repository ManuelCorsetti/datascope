import numpy as np
import pandas as pd
import pytest

from datascope.stats import (
    compute_numeric_stats, compute_string_stats, compute_datetime_stats,
    compute_boolean_stats, compute_histogram, compute_length_histogram, compute_top_values,
)


class TestNumericStats:
    def test_basic_stats(self):
        s = pd.Series([1, 2, 3, 4, 5])
        stats = compute_numeric_stats(s)
        assert stats["mean"] == 3.0
        assert stats["min"] == 1.0
        assert stats["max"] == 5.0
        assert stats["median"] == 3.0
        assert stats["zeros"] == 0
        assert stats["negatives"] == 0
        assert stats["infinite_count"] == 0

    def test_empty_series_returns_empty_dict(self):
        assert compute_numeric_stats(pd.Series([], dtype=float)) == {}

    def test_all_null_returns_empty_dict(self):
        assert compute_numeric_stats(pd.Series([None, None], dtype=float)) == {}

    def test_outlier_detection_1_5_iqr(self):
        s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 1000])
        stats = compute_numeric_stats(s)
        assert stats["outlier_count"] >= 1
        assert stats["max"] == 1000.0

    def test_infinite_values_dropped_from_stats_but_counted(self):
        s = pd.Series([1.0, 2.0, np.inf, -np.inf, 3.0])
        stats = compute_numeric_stats(s)
        assert stats["infinite_count"] == 2
        assert stats["max"] == 3.0
        assert stats["min"] == 1.0

    def test_all_infinite_returns_placeholder_dict(self):
        s = pd.Series([np.inf, -np.inf])
        stats = compute_numeric_stats(s)
        assert stats["infinite_count"] == 2
        assert stats["mean"] is None

    def test_is_integer_like_true_for_whole_numbers(self):
        stats = compute_numeric_stats(pd.Series([1.0, 2.0, 3.0]))
        assert stats["is_integer_like"] is True

    def test_is_integer_like_false_for_fractions(self):
        stats = compute_numeric_stats(pd.Series([1.5, 2.5, 3.5]))
        assert stats["is_integer_like"] is False

    def test_negatives_and_zeros_counted(self):
        stats = compute_numeric_stats(pd.Series([-1, 0, 0, 1, 2]))
        assert stats["negatives"] == 1
        assert stats["zeros"] == 2

    def test_result_is_json_safe(self):
        import json
        stats = compute_numeric_stats(pd.Series([1.123456789, 2.0, np.nan]))
        json.dumps(stats)  # must not raise


class TestHistogram:
    def test_empty_returns_empty_edges_and_counts(self):
        h = compute_histogram(pd.Series([], dtype=float))
        assert h == {"edges": [], "counts": []}

    def test_single_unique_value_does_not_crash(self):
        h = compute_histogram(pd.Series([5.0, 5.0, 5.0]))
        assert sum(h["counts"]) == 3

    def test_bin_count_capped_by_requested_bins(self):
        s = pd.Series(range(1000))
        h = compute_histogram(s, bins=10)
        assert len(h["counts"]) <= 10
        assert sum(h["counts"]) == 1000


class TestStringStats:
    def test_basic(self):
        s = pd.Series(["ab", "abc", "a"])
        stats = compute_string_stats(s)
        assert stats["min_length"] == 1
        assert stats["max_length"] == 3

    def test_empty_series(self):
        assert compute_string_stats(pd.Series([], dtype=object)) == {}

    def test_whitespace_only_values_counted(self):
        s = pd.Series(["a", "   ", "", "b"])
        stats = compute_string_stats(s.replace("", None).dropna())
        # sanity: whitespace-only string counted separately from real empties
        s2 = pd.Series(["a", "   ", "b"])
        stats2 = compute_string_stats(s2)
        assert stats2["empty_or_whitespace"] == 1


class TestLengthHistogram:
    def test_empty(self):
        assert compute_length_histogram(pd.Series([], dtype=object)) == {"edges": [], "counts": []}

    def test_basic(self):
        s = pd.Series(["a", "bb", "ccc"])
        h = compute_length_histogram(s)
        assert sum(h["counts"]) == 3


class TestDatetimeStats:
    def test_basic_range(self):
        s = pd.Series(pd.to_datetime(["2020-01-01", "2020-06-15", "2021-01-01"]))
        stats = compute_datetime_stats(s)
        assert stats["range_days"] == 366
        assert stats["future_dates"] == 0

    def test_future_dates_detected(self):
        # A date far enough out to always be "future" relative to whenever
        # this test runs, but safely inside datetime64[ns]'s representable
        # range (~1677-2262) on every supported pandas version -- a
        # hardcoded far-future date like "2999-01-01" overflows that range
        # on pandas < 3.0 and raises OutOfBoundsDatetime instead.
        future = (pd.Timestamp.now() + pd.Timedelta(days=3650)).strftime("%Y-%m-%d")
        s = pd.Series(pd.to_datetime(["2020-01-01", future]))
        stats = compute_datetime_stats(s)
        assert stats["future_dates"] == 1

    def test_string_dates_parsed(self):
        s = pd.Series(["2020-01-01", "2020-03-15"])
        stats = compute_datetime_stats(s)
        assert stats["range_days"] == 74

    def test_empty_returns_empty_dict(self):
        assert compute_datetime_stats(pd.Series([], dtype=object)) == {}

    def test_unparseable_strings_dropped_not_raised(self):
        s = pd.Series(["not a date", "also not a date"])
        stats = compute_datetime_stats(s)
        assert stats == {}


class TestBooleanStats:
    def test_python_bools(self):
        stats = compute_boolean_stats(pd.Series([True, True, False]))
        assert stats["true_count"] == 2
        assert stats["false_count"] == 1

    def test_string_bool_like_values(self):
        stats = compute_boolean_stats(pd.Series(["yes", "no", "y", "n", "true", "false"]))
        assert stats["true_count"] == 3
        assert stats["false_count"] == 3

    def test_empty(self):
        assert compute_boolean_stats(pd.Series([], dtype=object)) == {}


class TestTopValues:
    def test_basic_ordering_and_pct(self):
        s = pd.Series(["a", "a", "a", "b", "b", "c"])
        top = compute_top_values(s, n=2)
        assert top[0]["value"] == "a"
        assert top[0]["count"] == 3
        assert top[0]["pct"] == pytest.approx(50.0)

    def test_empty_series_returns_empty_list(self):
        assert compute_top_values(pd.Series([], dtype=object)) == []

    def test_long_values_truncated(self):
        s = pd.Series(["x" * 500])
        top = compute_top_values(s)
        assert len(top[0]["value"]) == 200
