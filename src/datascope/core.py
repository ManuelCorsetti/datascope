"""
Orchestration: load data, profile every column, compute dataset-level
signals (correlations, missing-value correlation, primary-key
candidates, alerts), and render the HTML report.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from itertools import combinations
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from .stats import (
    compute_numeric_stats, compute_string_stats, compute_datetime_stats,
    compute_boolean_stats, compute_histogram, compute_length_histogram, compute_top_values,
)
from .semantic import infer_semantic_type
from .pii import detect_sensitive_data, mask_value
from .quality import recommend_rules, generate_dbt_snippet
from .referential import Reference, alerts_for, find_referential_integrity
from .relationships import _candidate_pool, find_functional_dependencies
from .run_summary import finish as finish_run_summary, pandas_checks
from .settings import PANDAS, Settings, resolve
from .html_report import render_html

DATETIME_TYPES = ("datetime", "datetime_string")


class DataProfiler:
    """Profile a DataFrame (or a csv/tsv/parquet/xlsx/json path).

    Every threshold and limit is a `Settings` field: pass `settings=`, or
    any field as a keyword (`DataProfiler(max_correlation_cols=50)`).
    `suggest_references=False` is still accepted (same as
    `suggested_references="off"`). The values used are recorded in
    `result["meta"]["settings"]`.
    """

    def __init__(self, settings: Optional[Settings] = None, **kwargs: Any):
        self.settings = resolve(settings, kwargs)

    def __getattr__(self, name: str) -> Any:
        # Old attribute names (profiler.max_correlation_cols) read through.
        settings = self.__dict__.get("settings")
        if settings is not None and name in Settings.__dataclass_fields__:
            return getattr(settings, name)
        raise AttributeError(name)

    # ---------------------------------------------------------------- load
    def _load(self, data: Union[pd.DataFrame, str]) -> pd.DataFrame:
        if isinstance(data, pd.DataFrame):
            return data.copy()
        if isinstance(data, str):
            ext = os.path.splitext(data)[1].lower()
            if ext == ".csv":
                return pd.read_csv(data)
            if ext == ".tsv":
                return pd.read_csv(data, sep="\t")
            if ext in (".parquet", ".pq"):
                return pd.read_parquet(data)
            if ext in (".xlsx", ".xls"):
                return pd.read_excel(data)
            if ext == ".json":
                return pd.read_json(data)
            raise ValueError(f"Unsupported file extension: {ext!r}")
        raise TypeError("data must be a pandas DataFrame or a path to a csv/tsv/parquet/xlsx/json file")

    # ------------------------------------------------------------- profile
    def profile(self, data: Union[pd.DataFrame, str], source_name: Optional[str] = None,
                references: Optional[Dict[str, Reference]] = None) -> Dict[str, Any]:
        """Profile `data`.

        `references` declares referential-integrity checks, as
        {child column: parent}. The parent is another column of this
        table (its name), another table's key column (a Series), or
        (label, Series) to name it in the report, e.g.
        {"customer_id": ("customers.id", customers["id"])}. Likely
        same-table references are also suggested (see the
        `suggested_references` setting).
        """
        st = self.settings
        df = self._load(data)
        n_rows = len(df)
        n_cols = len(df.columns)
        given_name = source_name
        source_name = source_name or (data if isinstance(data, str) else "dataset")

        duplicate_rows = int(df.duplicated().sum()) if n_rows else 0
        memory_bytes = int(df.memory_usage(deep=True).sum())

        column_profiles = [self._profile_column(df, str(col), n_rows) for col in df.columns]

        total_cells = n_rows * n_cols
        total_missing = sum(c["missing"] for c in column_profiles)

        type_distribution: Dict[str, int] = {}
        for c in column_profiles:
            type_distribution[c["semantic_type"]] = type_distribution.get(c["semantic_type"], 0) + 1

        sensitive_cols = [c for c in column_profiles if c["sensitive"]["is_sensitive"]]

        numeric_cols = [c["name"] for c in column_profiles if c.get("numeric_stats")]
        correlations = self._numeric_correlation(df, numeric_cols) if st.correlations else None
        missing_correlation = self._missing_correlation(df) if st.correlations else None
        pk_candidates = self._find_pk_candidates(df, column_profiles)
        high_correlation_pairs = self._high_correlation_pairs(correlations)
        duplicate_columns = self._find_duplicate_columns(df, max_cols=st.max_duplicate_column_check)
        functional_dependencies = find_functional_dependencies(
            df, column_profiles, min_purity=st.fd_min_purity, min_support_rows=st.fd_min_support_rows,
            max_candidate_pool=st.max_fd_candidate_pool,
        ) if st.functional_dependencies else []
        referential_integrity, reference_suggestions = find_referential_integrity(
            df, column_profiles, references, st, mode=st.suggested_reference_mode(PANDAS))

        meta = {
            "source_name": str(source_name),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_rows": n_rows,
            "n_cols": n_cols,
            "memory_mb": round(memory_bytes / (1024 * 1024), 3),
            "duplicate_rows": duplicate_rows,
            "duplicate_rows_pct": round(100 * duplicate_rows / n_rows, 3) if n_rows else 0.0,
            "engine": PANDAS,
        }

        overview = {
            "type_distribution": type_distribution,
            "total_missing_cells": int(total_missing),
            "total_missing_pct": round(100 * total_missing / total_cells, 3) if total_cells else 0.0,
            "sensitive_columns_count": len(sensitive_cols),
        }

        result: Dict[str, Any] = {
            "meta": meta,
            "overview": overview,
            "columns": column_profiles,
            "correlations": correlations,
            "missing_correlation": missing_correlation,
            "pk_candidates": pk_candidates,
            "high_correlation_pairs": high_correlation_pairs,
            "duplicate_columns": duplicate_columns,
            "functional_dependencies": functional_dependencies,
            "referential_integrity": referential_integrity,
            "reference_suggestions": reference_suggestions,
        }
        result["overview"]["alerts"] = self._build_alerts(column_profiles, duplicate_rows, n_rows,
                                                            high_correlation_pairs, duplicate_columns,
                                                            functional_dependencies) + alerts_for(referential_integrity, st)

        pk_eligible = [c for c in column_profiles if c["missing"] == 0 and c["unique"] > 1]
        checks = pandas_checks(st, {
            "n_cols": n_cols, "n_rows": n_rows, "duplicate_rows": duplicate_rows,
            "max_non_null": max((c["count"] - c["missing"] for c in column_profiles), default=0),
            "n_numeric": len(numeric_cols),
            "n_missing_corr_cols": sum(1 for c in column_profiles if 0 < c["missing"] < n_rows),
            "pk": {"single_found": any(p["type"] == "single" for p in pk_candidates),
                   "composite_found": any(p["type"] == "composite" for p in pk_candidates),
                   "eligible": len(pk_eligible)},
            "fd_pool_eligible": len(_candidate_pool(column_profiles, max_pool=10 ** 9)),
            "declared": len(references or {}),
            "suggestions": reference_suggestions,
        })
        finish_run_summary(meta, st, checks, {
            "source": data if isinstance(data, str) else None,
            "source_name": given_name,
            "references": [_reference_arg(child, ref) for child, ref in (references or {}).items()],
        }, PANDAS, _version())
        return result

    # -------------------------------------------------------- per column
    def _profile_column(self, df: pd.DataFrame, col: str, n_rows: int) -> Dict[str, Any]:
        series = df[col]
        non_null = series.dropna()
        missing = int(series.isna().sum())
        unique = int(non_null.nunique())
        unique_pct = round(100 * unique / len(non_null), 3) if len(non_null) else 0.0

        semantic_type, confidence, notes = infer_semantic_type(series, col)

        profile: Dict[str, Any] = {
            "name": col,
            "dtype": str(series.dtype),
            "semantic_type": semantic_type,
            "semantic_type_confidence": confidence,
            "semantic_notes": notes,
            "count": int(len(series)),
            "missing": missing,
            "missing_pct": round(100 * missing / n_rows, 3) if n_rows else 0.0,
            "unique": unique,
            "unique_pct": unique_pct,
            "memory_bytes": int(series.memory_usage(deep=True)),
        }

        numeric_stats = string_stats = datetime_stats = boolean_stats = histogram = length_histogram = None

        if semantic_type in DATETIME_TYPES or pd.api.types.is_datetime64_any_dtype(series):
            datetime_stats = compute_datetime_stats(series)
        elif semantic_type == "boolean":
            boolean_stats = compute_boolean_stats(series)
        elif pd.api.types.is_numeric_dtype(series):
            numeric_stats = compute_numeric_stats(series)
            histogram = compute_histogram(series, bins=self.histogram_bins)
        else:
            string_stats = compute_string_stats(series)
            length_histogram = compute_length_histogram(series)

        profile["numeric_stats"] = numeric_stats
        profile["string_stats"] = string_stats
        profile["datetime_stats"] = datetime_stats
        profile["boolean_stats"] = boolean_stats
        profile["histogram"] = histogram
        profile["length_histogram"] = length_histogram
        profile["top_values"] = compute_top_values(series, n=self.top_n_values)

        sensitive = detect_sensitive_data(
            series, col, sample_size=self.sample_size_for_content_checks, random_state=self.random_state,
            # continuous_numeric measures (price, temperature, ...) are
            # skipped too: their str() form is a decimal expansion that
            # incidentally satisfies digit-plus-separator content regexes
            # (e.g. the phone pattern) purely by coincidence, not because
            # the values mean anything like a phone/SSN/card number.
            # Identifier / discrete_numeric_categorical columns (where a
            # numeric SSN or card number would actually land) still run.
            skip_content=(semantic_type in DATETIME_TYPES or semantic_type == "boolean"
                          or semantic_type == "continuous_numeric"
                          or pd.api.types.is_datetime64_any_dtype(series)),
        )
        profile["sensitive"] = sensitive

        if sensitive["is_sensitive"]:
            profile["top_values"] = [{**tv, "value": mask_value(tv["value"])} for tv in profile["top_values"]]

        profile["quality_rules"] = recommend_rules(profile)
        profile["dbt_snippet"] = generate_dbt_snippet(profile)
        return profile

    # --------------------------------------------------------- dataset-level
    def _numeric_correlation(self, df: pd.DataFrame, numeric_cols: List[str]) -> Optional[Dict[str, Any]]:
        cols = numeric_cols[: self.max_correlation_cols]
        if len(cols) < 2:
            return None
        corr = df[cols].corr().fillna(0)
        return {
            "columns": [str(c) for c in corr.columns],
            "matrix": corr.round(3).values.tolist(),
            "truncated": len(numeric_cols) > self.max_correlation_cols,
        }

    def _missing_correlation(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        null_matrix = df.isna().astype(int)
        cols_with_variance = [c for c in null_matrix.columns if 0 < null_matrix[c].sum() < len(df)]
        cols_with_variance = cols_with_variance[: self.max_correlation_cols]
        if len(cols_with_variance) < 2:
            return None
        corr = null_matrix[cols_with_variance].corr().fillna(0)
        return {"columns": [str(c) for c in corr.columns], "matrix": corr.round(3).values.tolist()}

    def _find_pk_candidates(self, df: pd.DataFrame, column_profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        n = len(df)
        if n == 0:
            return []
        candidates = []
        singles = [c["name"] for c in column_profiles if c["missing"] == 0 and c["unique"] == n]
        for s in singles:
            candidates.append({"columns": [s], "type": "single"})
        if singles:
            return candidates

        unique_by_name = {c["name"]: c["unique"] for c in column_profiles}
        pool = [c["name"] for c in column_profiles if c["missing"] == 0 and c["unique"] > 1]
        pool = sorted(pool, key=lambda c: -unique_by_name[c])[: self.max_pk_candidate_pool]

        for size in range(2, self.max_pk_combo_size + 1):
            for combo in combinations(pool, size):
                if df.duplicated(subset=list(combo)).sum() == 0:
                    candidates.append({"columns": list(combo), "type": "composite"})
                    return candidates
        return candidates

    def _high_correlation_pairs(self, correlations: Optional[Dict[str, Any]],
                                threshold: Optional[float] = None) -> List[Dict[str, Any]]:
        """Numeric column pairs that move together strongly enough to be
        worth a second look — possible redundancy, a derived column, or
        two columns that should collapse into one."""
        if not correlations:
            return []
        threshold = self.settings.high_correlation_threshold if threshold is None else threshold
        cols = correlations["columns"]
        matrix = correlations["matrix"]
        pairs = []
        for i, c1 in enumerate(cols):
            for j in range(i + 1, len(cols)):
                v = matrix[i][j]
                if v is not None and abs(v) >= threshold:
                    pairs.append({"col1": c1, "col2": cols[j], "correlation": round(float(v), 3)})
        return sorted(pairs, key=lambda p: -abs(p["correlation"]))

    def _find_duplicate_columns(self, df: pd.DataFrame, max_cols: int = 100) -> List[List[str]]:
        """Columns that are byte-for-byte identical to another column —
        usually a copy-paste artifact from an upstream join. Skipped above
        max_cols since it's an O(n^2) full-column comparison."""
        cols = list(df.columns)
        if len(cols) > max_cols:
            return []
        duplicates = []
        for i, c1 in enumerate(cols):
            for c2 in cols[i + 1:]:
                try:
                    if df[c1].equals(df[c2]):
                        duplicates.append([str(c1), str(c2)])
                except Exception:
                    pass
        return duplicates

    def _build_alerts(self, column_profiles: List[Dict[str, Any]], duplicate_rows: int, n_rows: int,
                       high_correlation_pairs: Optional[List[Dict[str, Any]]] = None,
                       duplicate_columns: Optional[List[List[str]]] = None,
                       functional_dependencies: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        st = self.settings
        alerts: List[Dict[str, Any]] = []
        if duplicate_rows > 0:
            alerts.append({
                "severity": "warning", "column": None,
                "message": f"{duplicate_rows} exact duplicate row(s) found ({round(100 * duplicate_rows / n_rows, 2)}%).",
            })
        for pair in (duplicate_columns or []):
            alerts.append({"severity": "warning", "column": None,
                            "message": f"'{pair[0]}' and '{pair[1]}' are byte-for-byte identical columns."})
        for pair in (high_correlation_pairs or [])[:8]:
            alerts.append({"severity": "info", "column": None,
                            "message": f"'{pair['col1']}' and '{pair['col2']}' are highly correlated (r={pair['correlation']})."})
        for fd in (functional_dependencies or [])[:8]:
            if fd["purity"] >= 0.999999:
                alerts.append({"severity": "info", "column": None,
                                "message": f"'{fd['determinant']}' fully determines '{fd['dependent']}' "
                                           f"({fd['distinct_determinant_values']} values, no exceptions) "
                                           "— possibly a redundant/derivable column or an undocumented business rule."})
            else:
                alerts.append({"severity": "info", "column": None,
                                "message": f"'{fd['determinant']}' appears to determine '{fd['dependent']}' "
                                           f"in {round(fd['purity'] * 100, 1)}% of rows — {fd['violation_count']} exception(s) worth reviewing."})
        for c in column_profiles:
            if c["semantic_type"] == "constant":
                alerts.append({"severity": "warning", "column": c["name"],
                                "message": "Single distinct value — consider dropping."})
            if c["missing_pct"] > st.missing_high_pct:
                alerts.append({"severity": "high", "column": c["name"],
                                "message": f"{c['missing_pct']}% missing values."})
            elif c["missing_pct"] > st.missing_warning_pct:
                alerts.append({"severity": "warning", "column": c["name"],
                                "message": f"{c['missing_pct']}% missing values."})
            if c["semantic_type"] == "high_cardinality_text":
                alerts.append({"severity": "info", "column": c["name"],
                                "message": "High cardinality — verify categorical vs. identifier vs. free text."})
            if c["semantic_type"] == "datetime_string":
                alerts.append({"severity": "info", "column": c["name"],
                                "message": "Dates stored as text — consider casting to a real datetime type."})
            if c["sensitive"]["is_sensitive"] and c["sensitive"]["confidence"] >= st.sensitive_alert_min_confidence:
                alerts.append({"severity": "sensitive", "column": c["name"],
                                "message": f"Likely {c['sensitive']['category']} ({c['sensitive']['type']}) — review access controls."})
            ns = c.get("numeric_stats")
            if ns and ns.get("outlier_pct", 0) > st.outlier_alert_pct:
                alerts.append({"severity": "info", "column": c["name"],
                                "message": f"{ns['outlier_pct']}% statistical outliers (1.5x IQR)."})
            if ns and ns.get("infinite_count", 0) > 0:
                alerts.append({"severity": "warning", "column": c["name"],
                                "message": f"{ns['infinite_count']} infinite value(s) found (dropped from stats below)."})
        return alerts

    # ------------------------------------------------------------- render
    def to_html(self, profile_dict: Dict[str, Any], output_path: str) -> str:
        render_html(profile_dict, output_path)
        return output_path


def profile(
    data: Union[pd.DataFrame, str],
    output_html: str = "data_profile_report.html",
    source_name: Optional[str] = None,
    open_browser: bool = False,
    references: Optional[Dict[str, Reference]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """One-liner: profile `data` (a DataFrame or a csv/parquet/xlsx/json
    path) and write an interactive HTML report to `output_html`. Returns
    the underlying profile dict too, in case you want it directly
    (e.g. to feed a CI data-quality gate). `references` declares
    referential-integrity checks — see `DataProfiler.profile`."""
    profiler = DataProfiler(**kwargs)
    result = profiler.profile(data, source_name=source_name, references=references)
    profiler.to_html(result, output_html)
    if open_browser:
        import webbrowser
        webbrowser.open(f"file://{os.path.abspath(output_html)}")
    return result


def _version() -> str:
    from . import __version__
    return __version__


def _reference_arg(child: str, ref: Any) -> Optional[str]:
    """CHILD=PARENT for the reproduce command; None when a reference was a
    bare Series the CLI can't name (the command marks it as a placeholder)."""
    if isinstance(ref, str):
        return f"{child}={ref}"
    if isinstance(ref, tuple) and ":" in str(ref[0]):
        return f"{child}={ref[0]}"  # the CLI's own PATH:COLUMN label
    return f"{child}=PATH:COLUMN"
