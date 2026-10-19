"""
Semantic type inference.

Classifies a column into a practical category (identifier, categorical,
continuous_numeric, free_text, ...) using dtype plus, centrally, how
*unique* the column's values are relative to the row count. Uniqueness is
the strongest single signal for "is this a key, a category, or a
measure" — a near-100%-unique column is a key/identifier candidate no
matter its dtype; a handful of repeating values is categorical no matter
whether it's stored as text or numbers.

Returns (semantic_type, confidence, notes) — notes are short, human-
readable reasons shown in the report, not just a bare label.
"""
from __future__ import annotations

import re
from typing import List, Tuple

import pandas as pd

_ID_NAME_RE = re.compile(
    r"(^id$|_id$|^id_|_key$|^key$|_uuid$|^uuid$|_guid$|^guid$|_code$|_no$|_num$|_number$)",
    re.IGNORECASE,
)

_BOOL_LIKE_SETS = [
    {"true", "false"}, {"0", "1"}, {"yes", "no"}, {"y", "n"}, {"t", "f"},
]

# Python's \b treats '_' as a word character, so a plain \b...\b pattern
# never fires around it -- "priority_level" would not match \bpriority\b.
# Same fix as pii.py's _w() helper, needed here for the same reason: real
# column names are almost always snake_case compounds.
_ORDINAL_HINT_RE = re.compile(
    r"(?:^|_)(?:level|tier|rank|grade|priority|rating|severity)(?:_|$)", re.IGNORECASE
)


def _looks_like_id_name(name: str) -> bool:
    return bool(_ID_NAME_RE.search(name))


def _looks_ordinal(name: str) -> bool:
    return bool(_ORDINAL_HINT_RE.search(name))


def infer_semantic_type(series: pd.Series, col_name: str) -> Tuple[str, float, List[str]]:
    non_null = series.dropna()
    n_non_null = len(non_null)

    if n_non_null == 0:
        return "empty", 1.0, ["Column is entirely null."]

    unique_count = int(non_null.nunique())

    if unique_count == 1:
        return "constant", 1.0, ["Only one distinct value across all non-null rows."]

    if pd.api.types.is_bool_dtype(series):
        return "boolean", 0.98, []

    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime", 0.95, []

    unique_pct = unique_count / n_non_null * 100

    if unique_count == 2:
        vals = set(str(v).strip().lower() for v in non_null.unique())
        if vals in _BOOL_LIKE_SETS:
            return "boolean", 0.9, ["Two distinct values resembling True/False."]
        return "binary_categorical", 0.85, ["Exactly two distinct values."]

    if pd.api.types.is_numeric_dtype(series):
        looks_id = _looks_like_id_name(col_name)
        if unique_pct >= 95 and unique_count > 20:
            if looks_id:
                return "identifier", 0.9, [
                    f"{round(unique_pct, 1)}% unique and the column name reads as an identifier."
                ]
            return "continuous_numeric", 0.75, [f"{round(unique_pct, 1)}% unique numeric values."]
        if unique_count <= 20 or unique_pct < 5:
            notes = ["Low cardinality numeric — may represent a code or category rather than a measure."]
            if _looks_ordinal(col_name):
                notes.append("Column name suggests an ordinal scale (tier/rank/level/...) — order likely matters, don't treat as a plain unordered category.")
            return "discrete_numeric_categorical", 0.7, notes
        return "continuous_numeric", 0.7, []

    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        as_str = non_null.astype(str)
        avg_len = float(as_str.str.len().mean())
        looks_id = _looks_like_id_name(col_name)

        # Cheap pre-check before attempting date parsing: dates almost always
        # contain a separator; skip the parse attempt entirely otherwise
        # (avoids misclassifying plain numeric codes like zip codes).
        sample = as_str if len(as_str) <= 200 else as_str.sample(200, random_state=42)
        has_separator = bool(sample.str.contains(r"[-/]", regex=True).mean() > 0.5)
        if has_separator and unique_pct > 1:
            try:
                parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
            except (TypeError, ValueError):
                parsed = pd.to_datetime(sample, errors="coerce")
            if parsed.notna().mean() > 0.9:
                return "datetime_string", 0.8, [
                    "Values parse as dates but are stored as text — consider casting to a real datetime type."
                ]

        if unique_pct >= 98:
            if looks_id or avg_len <= 40:
                return "identifier", 0.85, [
                    f"{round(unique_pct, 1)}% unique values — likely a key or identifier."
                ]
            return "free_text", 0.75, ["High uniqueness with long values — likely free-form text."]
        if avg_len > 80:
            return "free_text", 0.75, [f"Average length {round(avg_len)} chars — likely free-form text."]
        if unique_count <= 50 or unique_pct < 10:
            notes = [f"Only {unique_count} distinct values."]
            if _looks_ordinal(col_name):
                notes.append("Column name suggests an ordinal scale (tier/rank/level/...) — order likely matters, don't treat as a plain unordered category.")
            return "categorical", 0.85, notes
        return "high_cardinality_text", 0.6, [
            "High cardinality string — verify whether this should be categorical, an identifier, or free text."
        ]

    return "unknown", 0.3, ["Could not confidently classify this column's semantic type."]
