import numpy as np
import pandas as pd
import pytest

from datascope.core import DataProfiler, profile


@pytest.fixture
def sample_df():
    rng = np.random.default_rng(42)
    n = 200
    return pd.DataFrame({
        "id": range(n),
        "email": [f"user{i}@example.com" for i in range(n)],
        "age": rng.integers(18, 90, n),
        "signup_date": pd.date_range("2022-01-01", periods=n, freq="D"),
        "tier": rng.choice(["Free", "Pro", "Enterprise"], n),
        "score": rng.normal(50, 10, n),
    })


class TestProfileStructure:
    def test_top_level_keys_present(self, sample_df):
        result = DataProfiler().profile(sample_df, source_name="test")
        for key in ("meta", "overview", "columns", "correlations", "missing_correlation",
                    "pk_candidates", "high_correlation_pairs", "duplicate_columns",
                    "functional_dependencies"):
            assert key in result

    def test_meta_counts_correct(self, sample_df):
        result = DataProfiler().profile(sample_df, source_name="test")
        assert result["meta"]["n_rows"] == 200
        assert result["meta"]["n_cols"] == 6
        assert result["meta"]["source_name"] == "test"

    def test_one_profile_entry_per_column(self, sample_df):
        result = DataProfiler().profile(sample_df)
        assert len(result["columns"]) == len(sample_df.columns)
        assert {c["name"] for c in result["columns"]} == set(sample_df.columns)

    def test_quality_score_in_range(self, sample_df):
        result = DataProfiler().profile(sample_df)
        score = result["overview"]["quality_score"]
        assert score is not None
        assert 0.0 <= score <= 100.0

    def test_id_column_detected_as_pk_candidate(self, sample_df):
        result = DataProfiler().profile(sample_df)
        pk_cols = [c["columns"] for c in result["pk_candidates"]]
        assert ["id"] in pk_cols

    def test_email_column_flagged_sensitive(self, sample_df):
        result = DataProfiler().profile(sample_df)
        email_col = next(c for c in result["columns"] if c["name"] == "email")
        assert email_col["sensitive"]["is_sensitive"] is True


class TestDuplicateDetection:
    def test_exact_duplicate_rows_counted(self):
        df = pd.DataFrame({"a": [1, 1, 2, 3], "b": ["x", "x", "y", "z"]})
        result = DataProfiler().profile(df)
        assert result["meta"]["duplicate_rows"] == 1

    def test_duplicate_columns_detected(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [1, 2, 3], "c": [9, 8, 7]})
        result = DataProfiler().profile(df)
        assert ["a", "b"] in result["duplicate_columns"]


class TestAlerts:
    def test_high_missingness_triggers_alert(self):
        df = pd.DataFrame({"a": [1, None, None, None, None], "b": range(5)})
        result = DataProfiler().profile(df)
        messages = [a["message"] for a in result["overview"]["alerts"]]
        assert any("missing" in m.lower() for m in messages)

    def test_constant_column_triggers_alert(self):
        df = pd.DataFrame({"a": [1, 1, 1, 1], "b": range(4)})
        result = DataProfiler().profile(df)
        assert any(a["column"] == "a" and "distinct value" in a["message"] for a in result["overview"]["alerts"])

    def test_functional_dependency_triggers_alert(self):
        rng = np.random.default_rng(5)
        n = 300
        country = rng.choice(["US", "CA", "FR"], n)
        currency = ["USD" if c == "US" else "CAD" if c == "CA" else "EUR" for c in country]
        df = pd.DataFrame({"id": range(n), "country": country, "currency": currency})
        result = DataProfiler().profile(df)
        messages = [a["message"] for a in result["overview"]["alerts"]]
        assert any("determine" in m for m in messages)


class TestContinuousNumericNotFlaggedAsPii:
    def test_float_column_not_flagged_as_phone(self):
        # Regression test: str() of a float measure can incidentally match
        # the phone-number content regex (digits + one '.' + digits). A
        # continuous numeric column must not be flagged as sensitive from
        # content alone.
        rng = np.random.default_rng(1)
        df = pd.DataFrame({"amount": rng.uniform(1, 1000, 300)})
        result = DataProfiler().profile(df)
        col = result["columns"][0]
        assert col["semantic_type"] == "continuous_numeric"
        assert col["sensitive"]["is_sensitive"] is False


class TestEmptyAndEdgeCases:
    def test_empty_dataframe_does_not_crash(self):
        result = DataProfiler().profile(pd.DataFrame())
        assert result["meta"]["n_rows"] == 0
        assert result["columns"] == []

    def test_single_column_does_not_crash(self):
        result = DataProfiler().profile(pd.DataFrame({"a": [1, 2, 3]}))
        assert len(result["columns"]) == 1

    def test_all_null_column_does_not_crash(self):
        result = DataProfiler().profile(pd.DataFrame({"a": [None, None, None]}))
        assert result["columns"][0]["semantic_type"] == "empty"


class TestToHtml:
    def test_writes_html_file(self, sample_df, tmp_path):
        result = DataProfiler().profile(sample_df)
        out = tmp_path / "report.html"
        DataProfiler().to_html(result, str(out))
        content = out.read_text(encoding="utf-8")
        assert content.startswith("<!DOCTYPE html>")
        assert "DATA PROFILE" in content


class TestPublicProfileFunction:
    def test_one_liner_writes_file_and_returns_dict(self, sample_df, tmp_path):
        out = tmp_path / "report.html"
        result = profile(sample_df, output_html=str(out), source_name="one_liner")
        assert out.exists()
        assert result["meta"]["source_name"] == "one_liner"

    def test_accepts_csv_path(self, tmp_path):
        csv_path = tmp_path / "data.csv"
        pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}).to_csv(csv_path, index=False)
        out = tmp_path / "report.html"
        result = profile(str(csv_path), output_html=str(out))
        assert result["meta"]["n_rows"] == 3
