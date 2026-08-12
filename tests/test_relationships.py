import numpy as np
import pandas as pd

from datascope.core import DataProfiler
from datascope.relationships import find_functional_dependencies


def _column_profiles(df):
    profiler = DataProfiler()
    return [profiler._profile_column(df, str(c), len(df)) for c in df.columns]


def test_near_fd_detected_with_violations():
    rng = np.random.default_rng(0)
    zips = ["10001", "10002", "90001", "90002", "60601"]
    zip_to_state = {"10001": "NY", "10002": "NY", "90001": "CA", "90002": "CA", "60601": "IL"}
    n = 500
    zip_col = rng.choice(zips, n)
    state_col = [zip_to_state[z] for z in zip_col]
    for i in range(5):
        state_col[i] = "ZZ"  # inject known violations
    df = pd.DataFrame({
        "customer_id": range(n),
        "zip": zip_col,
        "state": state_col,
        "age": rng.integers(18, 80, n),
    })
    fds = find_functional_dependencies(df, _column_profiles(df))
    matches = [fd for fd in fds if fd["determinant"] == "zip" and fd["dependent"] == "state"]
    assert len(matches) == 1
    fd = matches[0]
    assert fd["violation_count"] == 5
    assert 0.98 <= fd["purity"] < 1.0
    assert len(fd["violation_examples"]) > 0


def test_exact_fd_detected_with_no_violations():
    rng = np.random.default_rng(1)
    n = 300
    country = rng.choice(["US", "CA", "FR", "DE"], n)
    currency_map = {"US": "USD", "CA": "CAD", "FR": "EUR", "DE": "EUR"}
    currency = [currency_map[c] for c in country]
    df = pd.DataFrame({"order_id": range(n), "country_code": country, "currency": currency})
    fds = find_functional_dependencies(df, _column_profiles(df))
    matches = [fd for fd in fds if fd["determinant"] == "country_code" and fd["dependent"] == "currency"]
    assert len(matches) == 1
    assert matches[0]["purity"] == 1.0
    assert matches[0]["violation_count"] == 0


def test_independent_columns_produce_no_false_positive():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({
        "a": rng.choice(list("ABCDE"), 200),
        "b": rng.choice(list("WXYZ"), 200),
    })
    fds = find_functional_dependencies(df, _column_profiles(df))
    assert fds == []


def test_near_unique_determinant_does_not_produce_spurious_fd():
    # Regression test: a determinant column where almost every value is
    # unique must NOT be reported as "determining" other columns just
    # because most of its groups are singletons (trivially "consistent").
    # This was a real bug: it produced 14+ spurious findings on realistic
    # data before evidence-weighting (requiring a determinant value to
    # repeat at least once) was added.
    rng = np.random.default_rng(3)
    n = 500
    df = pd.DataFrame({
        "address": [f"{i} Main St" for i in range(n)],  # unique per row
        "country": rng.choice(["US", "CA", "FR"], n),  # unrelated to address
    })
    fds = find_functional_dependencies(df, _column_profiles(df))
    assert fds == []


def test_empty_dataframe_returns_no_dependencies():
    df = pd.DataFrame()
    assert find_functional_dependencies(df, []) == []


def test_dataframe_below_min_support_returns_no_dependencies():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    fds = find_functional_dependencies(df, _column_profiles(df), min_support_rows=20)
    assert fds == []


def test_bidirectional_equivalence_reported_once():
    # a and b mirror each other's grouping exactly (equivalent keys) and
    # both sit below the 99%-unique pool cutoff so both directions get
    # evaluated -- should surface as one relationship, not both a->b and
    # b->a.
    n = 500
    a_vals = [i % 480 for i in range(n)]
    df = pd.DataFrame({
        "a": a_vals,
        "b": [f"code-{v}" for v in a_vals],
        "filler": ["x"] * n,
    })
    fds = find_functional_dependencies(df, _column_profiles(df))
    pair_count = sum(1 for fd in fds if {fd["determinant"], fd["dependent"]} == {"a", "b"})
    assert pair_count == 1
