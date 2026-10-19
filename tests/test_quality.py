from datascope.quality import compute_quality_score, generate_dbt_snippet, recommend_rules

NOT_SENSITIVE = {"is_sensitive": False, "category": None, "type": None, "confidence": 0.0, "detected_by": []}
SENSITIVE = {"is_sensitive": True, "category": "PII", "type": "email", "confidence": 0.9, "detected_by": ["column_name"]}


def _col(**overrides):
    base = {
        "name": "col",
        "semantic_type": "continuous_numeric",
        "missing": 0,
        "missing_pct": 0.0,
        "unique_pct": 80.0,
        "top_values": [],
        "numeric_stats": None,
        "datetime_stats": None,
        "sensitive": NOT_SENSITIVE,
    }
    base.update(overrides)
    return base


class TestRecommendRules:
    def test_no_missing_suggests_not_null(self):
        rules = recommend_rules(_col(missing=0))
        assert any(r["type"] == "not_null" for r in rules)

    def test_identifier_with_full_uniqueness_suggests_unique(self):
        rules = recommend_rules(_col(semantic_type="identifier", unique_pct=99.95, missing=0))
        assert any(r["type"] == "unique" for r in rules)

    def test_identifier_with_low_uniqueness_flags_review(self):
        rules = recommend_rules(_col(semantic_type="identifier", unique_pct=80.0))
        assert any(r["type"] == "uniqueness_review" for r in rules)

    def test_categorical_full_coverage_suggests_accepted_values(self):
        top_values = [{"value": "a", "count": 5, "pct": 60.0}, {"value": "b", "count": 4, "pct": 40.0}]
        rules = recommend_rules(_col(semantic_type="categorical", top_values=top_values))
        assert any(r["type"] == "accepted_values" for r in rules)

    def test_infinite_values_flagged(self):
        ns = {"infinite_count": 3, "min": 0, "max": 10, "outlier_pct": 0, "negatives": 0}
        rules = recommend_rules(_col(numeric_stats=ns))
        assert any(r["type"] == "infinite_value_check" for r in rules)

    def test_negative_values_flagged_when_name_implies_nonnegative(self):
        ns = {"infinite_count": 0, "min": -5, "max": 10, "outlier_pct": 0, "negatives": 2}
        rules = recommend_rules(_col(name="total_amount", numeric_stats=ns))
        assert any(r["type"] == "non_negative_check" for r in rules)

    def test_future_dates_flagged(self):
        ds = {"future_dates": 2}
        rules = recommend_rules(_col(datetime_stats=ds))
        assert any(r["type"] == "future_date_check" for r in rules)

    def test_constant_column_flagged(self):
        rules = recommend_rules(_col(semantic_type="constant"))
        assert any(r["type"] == "review_column" for r in rules)

    def test_sensitive_column_flagged(self):
        rules = recommend_rules(_col(sensitive=SENSITIVE))
        assert any(r["type"] == "access_control" for r in rules)


class TestDbtSnippet:
    def test_returns_none_when_nothing_to_suggest(self):
        col = _col(missing=5, missing_pct=50.0, semantic_type="free_text")
        assert generate_dbt_snippet(col) is None

    def test_not_null_and_unique_included_for_pk_like_column(self):
        col = _col(semantic_type="identifier", unique_pct=100.0, missing=0)
        snippet = generate_dbt_snippet(col)
        assert "not_null" in snippet
        assert "unique" in snippet
        assert col["name"] in snippet

    def test_range_check_skipped_for_sensitive_numeric(self):
        ns = {"min": 0, "max": 100}
        col = _col(numeric_stats=ns, sensitive=SENSITIVE)
        snippet = generate_dbt_snippet(col)
        assert snippet is None or "accepted_range" not in snippet


class TestQualityScore:
    def _profile(self, cols, n_rows=100, missing_pct=0.0, dup_pct=0.0):
        return {
            "columns": cols,
            "meta": {"n_rows": n_rows, "duplicate_rows_pct": dup_pct},
            "overview": {"total_missing_pct": missing_pct},
        }

    def test_perfect_data_scores_100(self):
        cols = [_col(semantic_type="continuous_numeric") for _ in range(5)]
        score = compute_quality_score(self._profile(cols))
        assert score == 100.0

    def test_missing_values_lower_score(self):
        cols = [_col() for _ in range(5)]
        score = compute_quality_score(self._profile(cols, missing_pct=50.0))
        assert score < 100.0

    def test_constant_columns_lower_structure_score(self):
        cols = [_col(semantic_type="constant") for _ in range(5)]
        score = compute_quality_score(self._profile(cols))
        assert score < 100.0

    def test_empty_dataset_returns_none(self):
        assert compute_quality_score(self._profile([], n_rows=0)) is None

    def test_score_bounded_0_to_100(self):
        cols = [_col(semantic_type="constant") for _ in range(5)]
        score = compute_quality_score(self._profile(cols, missing_pct=100.0, dup_pct=100.0))
        assert 0.0 <= score <= 100.0
