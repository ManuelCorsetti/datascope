"""
Referential-integrity checks: does every value in one column (the
"child", e.g. orders.customer_id) exist in a key column (the "parent",
e.g. customers.id)? Child values that have no match are *orphans*.

Two ways a check comes about:

* **Declared** — the caller names the parent: another column of the same
  table, or a key column from another table (a pandas Series here; a
  `project.dataset.table.column` reference on the BigQuery engine).
* **Suggested** — within the profiled table only, a column whose name
  says it holds a key (`..._id`, `..._key`, `..._ref`, ...) is checked
  against an identifier column it names (`referred_by_customer_id` ->
  `customer_id`; any `..._id` -> a column literally called `id`). The
  name rule is deliberate: surrogate integer keys (1..N) are trivially
  "contained" in each other, so value overlap alone would flag
  `quantity -> customer_id`. A suggestion is only reported when at least
  `ri_suggest_min_match_pct` of its rows match; a lower rate means it
  probably isn't a reference at all, not that the data is broken.

Every threshold here comes from `Settings` (the `ri_*` fields).

NULL child values are not orphans (a missing reference is a
completeness question, reported elsewhere), matching SQL foreign keys.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import pandas as pd

from .pii import mask_value
from .settings import Settings

_KEY_SUFFIX_RE = re.compile(r"(?:^|_)(?:id|key|ref|code|no|num|number)$", re.IGNORECASE)
_CAMEL_KEY_SUFFIX_RE = re.compile(r"(?<=[a-z0-9])(?:Id|ID|Key|Ref|Code|No)$")

# A declared parent: same-table column name, another table's key column,
# or (label, key column) to control how it is named in the report.
Reference = Union[str, pd.Series, Tuple[str, pd.Series]]


def looks_like_key_name(name: str) -> bool:
    return bool(_KEY_SUFFIX_RE.search(name) or _CAMEL_KEY_SUFFIX_RE.search(name))


def key_stem(name: str) -> str:
    """'customer_id' -> 'customer', 'customerId' -> 'customer', 'id' -> ''."""
    stem = _CAMEL_KEY_SUFFIX_RE.sub("", name)
    stem = _KEY_SUFFIX_RE.sub("", stem)
    return stem.strip("_").lower()


def name_suggests_reference(child: str, parent: str) -> bool:
    """Whether `child`'s name says it points at `parent`."""
    if child == parent or not looks_like_key_name(child) or not looks_like_key_name(parent):
        return False
    stem = key_stem(parent)
    if not stem:  # parent is literally "id" / "key": any *_id may point at it
        return bool(key_stem(child))
    return stem in child.lower() and key_stem(child) != stem


def is_parent_candidate(col: Dict[str, Any], s: Settings) -> bool:
    """An identifier column unique enough to be a key. Duplicate rows can
    knock a real key slightly under 100%, hence ri_parent_min_unique_pct."""
    non_null = col.get("count", 0) - col.get("missing", 0)
    return (col.get("semantic_type") == "identifier" and col.get("missing", 1) == 0 and non_null > 0
            and col.get("unique", 0) / non_null * 100 >= s.ri_parent_min_unique_pct
            and not (col.get("numeric_stats") and not col["numeric_stats"].get("is_integer_like")))


def is_child_candidate(col: Dict[str, Any], s: Settings) -> bool:
    non_null = col.get("count", 0) - col.get("missing", 0)
    if non_null < s.ri_suggest_min_rows or col.get("unique", 0) < s.ri_suggest_min_distinct:
        return False
    if col.get("numeric_stats") and not col["numeric_stats"].get("is_integer_like"):
        return False
    # A column that is itself a key is a 1:1 twin, not a reference.
    return not (col.get("unique", 0) / non_null * 100 >= s.ri_parent_min_unique_pct)


def suggestion_pairs(column_profiles: Sequence[Dict[str, Any]], s: Settings,
                     exclude_children: Iterable[str] = ()) -> List[Tuple[str, str]]:
    """Every (child, parent) column-name pair worth checking, from names
    and the column profiles. Same table only; the caller applies
    max_reference_suggestions (so it can report what the cap left out)."""
    exclude = set(exclude_children)
    parents = [c for c in column_profiles if is_parent_candidate(c, s)]
    pairs = []
    for child in column_profiles:
        if child["name"] in exclude or not is_child_candidate(child, s):
            continue
        for parent in parents:
            if name_suggests_reference(child["name"], parent["name"]) and _kinds_match(child, parent):
                pairs.append((child["name"], parent["name"]))
    return pairs


def _kinds_match(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return bool(a.get("numeric_stats")) == bool(b.get("numeric_stats"))


def build_result(column: str, references: str, source: str, same_table: bool, checked: int,
                 orphans: int, orphan_values: int, samples: Sequence[Tuple[Any, int]],
                 sensitive: bool = False, compared_as: str = "value",
                 sample_n: int = Settings().ri_sample_orphans) -> Dict[str, Any]:
    show = (lambda v: mask_value(_display(v))) if sensitive else _display
    return {
        "column": column,
        "references": references,
        "source": source,
        "same_table": same_table,
        "checked": int(checked),
        "orphans": int(orphans),
        "orphan_pct": round(100 * orphans / checked, 3) if checked else 0.0,
        "orphan_values": int(orphan_values),
        "sample_orphans": [{"value": show(v), "count": int(n)} for v, n in samples[:sample_n]],
        "compared_as": compared_as,
    }


def _display(v: Any) -> str:
    # A key column with NULLs is float in pandas: show 999.0 as 999.
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def keep_suggestion(result: Dict[str, Any], s: Settings) -> bool:
    return result["checked"] >= s.ri_suggest_min_rows and 100 - result["orphan_pct"] >= s.ri_suggest_min_match_pct


def suggestion_entry(child: str, parent: str, status: str, estimated_bytes: Optional[int] = None) -> Dict[str, Any]:
    """A suggested reference that was listed (not checked) or set aside."""
    return {"column": child, "references": parent, "status": status, "estimated_bytes": estimated_bytes}


def alerts_for(results: Sequence[Dict[str, Any]], s: Settings = Settings()) -> List[Dict[str, Any]]:
    """Column-level alerts for checks that found orphans."""
    alerts = []
    for r in results:
        if not r["orphans"]:
            continue
        examples = ", ".join(s["value"] for s in r["sample_orphans"][:3])
        detail = (f"{r['orphans']} row(s) ({round(r['orphan_pct'], 2)}%) point to {r['orphan_values']} value(s) "
                  f"not found in {r['references']}" + (f", e.g. {examples}" if examples else "") + ".")
        if r["source"] == "declared":
            alerts.append({"severity": "high" if r["orphan_pct"] > s.ri_high_orphan_pct else "warning", "column": r["column"],
                           "message": f"Referential integrity: {detail}"})
        else:
            alerts.append({"severity": "warning", "column": r["column"],
                           "message": f"Looks like a reference to {r['references']}, but {detail}"})
    return alerts


# ------------------------------------------------------------- pandas
def _is_numeric(s: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)


def _as_text(s: pd.Series) -> pd.Series:
    if _is_numeric(s):
        try:
            if (s % 1 == 0).all():
                return s.astype("int64").astype(str)
        except (TypeError, ValueError):
            pass
    return s.astype(str).str.strip()


def check_reference(child: pd.Series, parent: pd.Series, column: str, references: str, source: str,
                    same_table: bool, sensitive: bool = False,
                    sample_n: int = Settings().ri_sample_orphans) -> Dict[str, Any]:
    c, p = child.dropna(), parent.dropna()
    compared_as = "value"
    if _is_numeric(c) != _is_numeric(p):
        # e.g. ids read as text in one file and as numbers in the other
        c, p = _as_text(c), _as_text(p)
        compared_as = "text"
    orphan_rows = c[~c.isin(pd.unique(p))]
    counts = orphan_rows.value_counts()
    samples = sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))[:sample_n]
    return build_result(column, references, source, same_table, checked=len(c), orphans=len(orphan_rows),
                        orphan_values=len(counts), samples=samples, sensitive=sensitive,
                        compared_as=compared_as, sample_n=sample_n)


def resolve_declared(df: pd.DataFrame, references: Optional[Dict[str, Reference]]) -> List[Tuple[str, str, pd.Series, bool]]:
    """-> (child column, parent label, parent values, same_table) per declared check."""
    resolved = []
    for child, ref in (references or {}).items():
        if child not in df.columns:
            raise ValueError(f"references: column {child!r} not found. Available: {list(map(str, df.columns))}")
        if isinstance(ref, str):
            if ref not in df.columns:
                raise ValueError(f"references: {child!r} -> {ref!r}, but there is no column {ref!r} in this table.")
            resolved.append((child, ref, df[ref], True))
        elif isinstance(ref, pd.Series):
            resolved.append((child, str(ref.name) if ref.name is not None else "reference", ref, False))
        elif isinstance(ref, tuple) and len(ref) == 2 and isinstance(ref[1], pd.Series):
            resolved.append((child, str(ref[0]), ref[1], False))
        else:
            raise TypeError(f"references[{child!r}] must be a column name, a pandas Series, or (label, Series).")
    return resolved


def find_referential_integrity(df: pd.DataFrame, column_profiles: Sequence[Dict[str, Any]],
                               references: Optional[Dict[str, Reference]] = None,
                               s: Settings = Settings(), mode: str = "check",
                               ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """-> (results, suggestions).

    `results` holds every check that ran and is worth reporting: all
    declared ones, plus suggested ones that matched well enough.
    `suggestions` accounts for every suggested pair found, whatever
    happened to it: status "checked" (in results), "below_match" (checked;
    too few matches to be a reference), "listed" (mode "list": not
    checked) or "over_limit" (beyond max_reference_suggestions).
    """
    by_name = {c["name"]: c for c in column_profiles}
    sensitive = {n for n, c in by_name.items() if c["sensitive"]["is_sensitive"]}
    results = [
        check_reference(df[child], parent, child, label, "declared", same_table, child in sensitive,
                        sample_n=s.ri_sample_orphans)
        for child, label, parent, same_table in resolve_declared(df, references)
    ]
    suggestions: List[Dict[str, Any]] = []
    if mode == "off":
        return results, suggestions
    pairs = suggestion_pairs(column_profiles, s, exclude_children=(references or {}).keys())
    for i, (child, parent) in enumerate(pairs):
        if i >= s.max_reference_suggestions:
            suggestions.append(suggestion_entry(child, parent, "over_limit"))
        elif mode == "list":
            suggestions.append(suggestion_entry(child, parent, "listed"))
        else:
            r = check_reference(df[child], df[parent], child, parent, "suggested", True, child in sensitive,
                                sample_n=s.ri_sample_orphans)
            kept = keep_suggestion(r, s)
            if kept:
                results.append(r)
            suggestions.append(suggestion_entry(child, parent, "checked" if kept else "below_match"))
    return results, suggestions
