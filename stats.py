"""
Per-column statistic calculators.

Every function here takes a raw pandas Series and returns a small dict of
plain Python types (no numpy scalars, no NaN/NaT) so the result is always
safe to json.dumps() directly.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np
import pandas as pd


def _safe_float(x) -> float | None:
    try:
        if x is None or pd.isna(x):
            return None
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 6)
    except (TypeError, ValueError):
        return None


def compute_numeric_stats(series: pd.Series) -> Dict[str, Any]:
    raw = pd.to_numeric(series.dropna(), errors="coerce").dropna()
    is_inf = np.isinf(raw.to_numpy()) if len(raw) else np.array([], dtype=bool)
    infinite_count = int(is_inf.sum())
    clean = raw[~is_inf] if infinite_count else raw
    if clean.empty:
        if infinite_count == 0:
            return {}
        return {
            "mean": None, "std": None, "min": None, "q1": None, "median": None, "q3": None,
            "max": None, "range": None, "sum": None, "zeros": 0, "zeros_pct": 0.0,
            "negatives": 0, "negatives_pct": 0.0, "skewness": None, "kurtosis": None,
            "outlier_count": 0, "outlier_pct": 0.0, "lower_fence": None, "upper_fence": None,
            "is_integer_like": False, "infinite_count": infinite_count,
        }

    q1, median, q3 = clean.quantile([0.25, 0.5, 0.75])
    iqr = q3 - q1
    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr
    outliers = clean[(clean < lower_fence) | (clean > upper_fence)]
    n = len(clean)
    is_integer_like = bool(np.allclose(clean, clean.round(), equal_nan=False)) if n else False

    return {
        "mean": _safe_float(clean.mean()),
        "std": _safe_float(clean.std()),
        "min": _safe_float(clean.min()),
        "q1": _safe_float(q1),
        "median": _safe_float(median),
        "q3": _safe_float(q3),
        "max": _safe_float(clean.max()),
        "range": _safe_float(clean.max() - clean.min()),
        "sum": _safe_float(clean.sum()),
        "zeros": int((clean == 0).sum()),
        "zeros_pct": round(100 * float((clean == 0).sum()) / n, 2),
        "negatives": int((clean < 0).sum()),
        "negatives_pct": round(100 * float((clean < 0).sum()) / n, 2),
        "skewness": _safe_float(clean.skew()),
        "kurtosis": _safe_float(clean.kurt()),
        "outlier_count": int(len(outliers)),
        "outlier_pct": round(100 * len(outliers) / n, 2),
        "lower_fence": _safe_float(lower_fence),
        "upper_fence": _safe_float(upper_fence),
        "is_integer_like": is_integer_like,
        "infinite_count": infinite_count,
    }


def compute_histogram(series: pd.Series, bins: int = 30) -> Dict[str, List[float]]:
    clean = pd.to_numeric(series.dropna(), errors="coerce").dropna()
    clean = clean[np.isfinite(clean.to_numpy())] if len(clean) else clean
    if clean.empty:
        return {"edges": [], "counts": []}
    n_unique = clean.nunique()
    n_bins = max(1, min(bins, n_unique))
    counts, edges = np.histogram(clean.to_numpy(), bins=n_bins)
    return {
        "edges": [round(float(e), 6) for e in edges],
        "counts": [int(c) for c in counts],
    }


def compute_string_stats(series: pd.Series) -> Dict[str, Any]:
    clean = series.dropna().astype(str)
    if clean.empty:
        return {}
    lengths = clean.str.len()
    empty_or_ws = int((clean.str.strip() == "").sum())
    return {
        "min_length": int(lengths.min()),
        "max_length": int(lengths.max()),
        "mean_length": round(float(lengths.mean()), 2),
        "empty_or_whitespace": empty_or_ws,
    }


def compute_length_histogram(series: pd.Series, bins: int = 20) -> Dict[str, List[float]]:
    """Distribution of value *lengths* — the one chartable shape available
    for identifier / free-text columns, where the values themselves are
    (near) unique and a value-histogram or top-values chart would be
    meaningless (every bar would be ~1 row)."""
    clean = series.dropna().astype(str)
    if clean.empty:
        return {"edges": [], "counts": []}
    lengths = clean.str.len()
    n_bins = max(1, min(bins, lengths.nunique()))
    counts, edges = np.histogram(lengths.to_numpy(), bins=n_bins)
    return {
        "edges": [round(float(e), 2) for e in edges],
        "counts": [int(c) for c in counts],
    }


def compute_datetime_stats(series: pd.Series) -> Dict[str, Any]:
    if pd.api.types.is_datetime64_any_dtype(series):
        clean = series.dropna()
    else:
        raw = series.dropna()
        try:
            clean = pd.to_datetime(raw, errors="coerce", format="mixed")
        except (TypeError, ValueError):
            clean = pd.to_datetime(raw, errors="coerce")
        clean = clean.dropna()
    if clean.empty:
        return {}
    now = pd.Timestamp.now(tz=clean.dt.tz) if getattr(clean.dt, "tz", None) is not None else pd.Timestamp.now()
    try:
        future = int((clean > now).sum())
    except TypeError:
        future = 0
    weekday_counts = clean.dt.day_name().value_counts().to_dict()
    return {
        "min_date": clean.min().isoformat(),
        "max_date": clean.max().isoformat(),
        "range_days": int((clean.max() - clean.min()).days),
        "weekday_distribution": {str(k): int(v) for k, v in weekday_counts.items()},
        "future_dates": future,
    }


def compute_boolean_stats(series: pd.Series) -> Dict[str, Any]:
    clean = series.dropna()
    if clean.empty:
        return {}

    def to_bool(v):
        if isinstance(v, (bool, np.bool_)):
            return bool(v)
        s = str(v).strip().lower()
        return s in ("true", "1", "yes", "y", "t")

    bools = clean.apply(to_bool)
    true_count = int(bools.sum())
    total = len(bools)
    return {
        "true_count": true_count,
        "false_count": total - true_count,
        "true_pct": round(100 * true_count / total, 2),
    }


def compute_top_values(series: pd.Series, n: int = 10) -> List[Dict[str, Any]]:
    clean = series.dropna()
    total = len(series)
    if clean.empty or total == 0:
        return []
    try:
        vc = clean.astype(str).value_counts().head(n)
    except Exception:
        return []
    return [
        {"value": str(v)[:200], "count": int(c), "pct": round(100 * c / total, 2)}
        for v, c in vc.items()
    ]
