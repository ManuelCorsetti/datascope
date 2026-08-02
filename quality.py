"""
Data-quality rule recommendations, dbt-style test snippets, and a
composite quality score. Every recommendation here is a heuristic
starting point derived from the observed sample — review before
enforcing anything in production, especially accepted-value lists
learned from a single snapshot of the data.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_NONNEG_KEYWORDS = ("count", "amount", "qty", "quantity", "price", "total",
                     "age", "duration", "length", "size", "score", "balance")


def _name_implies_nonnegative(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in _NONNEG_KEYWORDS)


def recommend_rules(col: Dict[str, Any]) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    name = col["name"]
    sem = col["semantic_type"]

    if col["missing"] == 0:
        rules.append({"type": "not_null", "severity": "suggested",
                       "description": "No missing values observed — consider enforcing NOT NULL."})
    elif col["missing_pct"] < 2:
        rules.append({"type": "not_null_soft", "severity": "info",
                       "description": f"Only {col['missing_pct']}% missing — investigate before deciding on NOT NULL."})

    if sem == "identifier" and col["unique_pct"] >= 99.9 and col["missing"] == 0:
        rules.append({"type": "unique", "severity": "high",
                       "description": "Values are unique with no nulls — strong primary-key candidate."})
    elif sem == "identifier" and col["unique_pct"] < 99.9:
        rules.append({"type": "uniqueness_review", "severity": "warning",
                       "description": f"Looks like an identifier but is only {col['unique_pct']}% unique — check for duplicate keys."})

    if sem in ("categorical", "binary_categorical", "boolean", "discrete_numeric_categorical") and col.get("top_values"):
        values = [tv["value"] for tv in col["top_values"]]
        coverage = sum(tv["pct"] for tv in col["top_values"])
        if coverage >= 99:
            rules.append({"type": "accepted_values", "severity": "suggested", "values": values,
                           "description": f"Restrict to the {len(values)} observed value(s), covering {round(coverage, 1)}% of rows."})

    ns = col.get("numeric_stats")
    if ns and ns.get("infinite_count"):
        rules.append({"type": "infinite_value_check", "severity": "warning",
                       "description": f"{ns['infinite_count']} infinite value(s) found — likely an upstream division-by-zero or overflow bug."})
    if ns and ns.get("min") is not None:
        rules.append({"type": "range_check", "severity": "suggested",
                       "description": f"Observed range is {ns['min']} to {ns['max']} — consider a bounds check."})
        if ns.get("outlier_pct", 0) > 1:
            rules.append({"type": "outlier_review", "severity": "info",
                           "description": f"{ns['outlier_pct']}% of values sit outside 1.5x IQR — review before treating as errors."})
        if ns.get("negatives", 0) > 0 and _name_implies_nonnegative(name):
            rules.append({"type": "non_negative_check", "severity": "warning",
                           "description": f"Column name suggests non-negative values, but {ns['negatives']} negative value(s) found."})

    ds = col.get("datetime_stats")
    if ds and ds.get("future_dates", 0) > 0:
        rules.append({"type": "future_date_check", "severity": "warning",
                       "description": f"{ds['future_dates']} value(s) are dated in the future — verify validity."})

    if sem == "constant":
        rules.append({"type": "review_column", "severity": "warning",
                       "description": "Single distinct value across the dataset — likely low analytical value."})

    if sem == "high_cardinality_text":
        rules.append({"type": "cardinality_review", "severity": "info",
                       "description": "High cardinality for a text-like field — confirm it isn't meant to be a controlled category or a key."})

    if col["sensitive"]["is_sensitive"]:
        rules.append({"type": "access_control", "severity": "sensitive",
                       "description": f"Flagged as likely {col['sensitive']['category']} ({col['sensitive']['type']}) — apply masking or row-level access controls."})

    return rules


def generate_dbt_snippet(col: Dict[str, Any]) -> Optional[str]:
    """A ready-to-paste dbt schema.yml column block. Returns None when
    there's nothing worth suggesting."""
    tests: List[Any] = []

    if col["missing"] == 0:
        tests.append("not_null")
    if col["semantic_type"] == "identifier" and col["unique_pct"] >= 99.9 and col["missing"] == 0:
        tests.append("unique")
    if col["semantic_type"] in ("categorical", "binary_categorical") and col.get("top_values"):
        coverage = sum(tv["pct"] for tv in col["top_values"])
        if coverage >= 99:
            tests.append({"accepted_values": {"values": [tv["value"] for tv in col["top_values"]]}})
    ns = col.get("numeric_stats")
    if ns and ns.get("min") is not None and not col["sensitive"]["is_sensitive"]:
        tests.append({"dbt_utils.accepted_range": {"min_value": ns["min"], "max_value": ns["max"]}})

    if not tests:
        return None

    lines = [f"- name: {col['name']}", "  tests:"]
    for t in tests:
        if isinstance(t, str):
            lines.append(f"    - {t}")
        else:
            key = next(iter(t))
            lines.append(f"    - {key}:")
            for k, v in t[key].items():
                lines.append(f"        {k}: {v!r}")
    return "\n".join(lines)


def compute_quality_score(profile: Dict[str, Any]) -> Optional[float]:
    """A simple, explainable 0-100 composite: completeness, duplicate-row
    penalty, and structural cleanliness (share of non-constant columns).
    Shown in the report with its components broken out, not just the
    number, since a single opaque score is more misleading than useful."""
    cols = profile["columns"]
    meta = profile["meta"]
    if not cols or meta["n_rows"] == 0:
        return None

    completeness = 1 - profile["overview"]["total_missing_pct"] / 100
    dup_score = 1 - min(meta["duplicate_rows_pct"] / 100, 1.0)
    constant_cols = sum(1 for c in cols if c["semantic_type"] == "constant")
    structure_score = 1 - (constant_cols / len(cols))

    score = (completeness * 0.45 + dup_score * 0.25 + structure_score * 0.30) * 100
    return round(max(0.0, min(100.0, score)), 1)
