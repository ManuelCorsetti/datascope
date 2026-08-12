"""
Cross-column relationship mining.

Functional dependency (FD) detection: does column A determine column B —
does every value of A map to (essentially) one value of B, the way `zip`
determines `state` or `country_code` determines `currency`? This is one
of the highest-value signals a profiler can surface (it points at
redundant/derivable columns, undocumented business rules, and referential
inconsistencies) and it's largely absent from lightweight profiling
tools, which mostly report single-column stats.

Approach — bounded, single-determinant search:
  For a pool of candidate columns, group by A and measure what fraction
  of rows fall in an A-group where B has exactly one distinct value
  ("support-weighted purity"). A is reported to determine B when purity
  clears `min_purity` over at least `min_support_rows` non-null rows.

This deliberately mirrors the same complexity trade-off `core.py` already
makes for primary-key search (bounded candidate pool, no exhaustive
composite search) rather than implementing a full TANE-style FD
discovery algorithm, which is superlinear in column count.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

DEFAULT_MIN_PURITY = 0.98
DEFAULT_MIN_SUPPORT_ROWS = 20
DEFAULT_MAX_CANDIDATE_POOL = 25
MAX_VIOLATION_EXAMPLES = 5


def _to_plain(v: Any) -> Any:
    if pd.isna(v):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v


def _candidate_pool(column_profiles: List[Dict[str, Any]], max_pool: int) -> List[str]:
    """Columns worth testing as either side of a functional dependency.

    Excludes near-constant columns (nothing to determine or be
    determined) and near-unique columns (an identifier trivially
    "determines" every other column and is never an interesting
    dependent either — that's what primary-key detection is for).
    Sorted by ascending cardinality: cheaper groupbys first, and lower-
    cardinality columns are more likely to be meaningful determinants.
    """
    pool = [
        c["name"] for c in column_profiles
        if c["semantic_type"] not in ("empty", "constant") and c["unique"] >= 2 and c["unique_pct"] < 99
    ]
    unique_by_name = {c["name"]: c["unique"] for c in column_profiles}
    pool.sort(key=lambda name: unique_by_name[name])
    return pool[:max_pool]


def find_functional_dependencies(
    df: pd.DataFrame,
    column_profiles: List[Dict[str, Any]],
    min_purity: float = DEFAULT_MIN_PURITY,
    min_support_rows: int = DEFAULT_MIN_SUPPORT_ROWS,
    max_candidate_pool: int = DEFAULT_MAX_CANDIDATE_POOL,
) -> List[Dict[str, Any]]:
    """Bounded search for near-functional-dependencies A -> B.

    Returns a list of dicts (sorted by purity desc, then row coverage
    desc), each with counter-example rows so a sub-100%-purity finding
    can be reviewed rather than taken on faith.
    """
    n_rows = len(df)
    if n_rows < min_support_rows:
        return []

    unique_by_name = {c["name"]: c["unique"] for c in column_profiles}
    pool = _candidate_pool(column_profiles, max_candidate_pool)

    results: List[Dict[str, Any]] = []

    for a in pool:
        for b in pool:
            if a == b:
                continue
            # Necessary condition for an exact FD A -> B: each A-group
            # contributes at most one B value, so distinct(B) <= distinct(A).
            # Used here as a prune for near-FDs too -- skip the direction
            # where B is strictly more fine-grained than A.
            if unique_by_name[a] < unique_by_name[b]:
                continue

            sub = df[[a, b]].dropna()
            if len(sub) < min_support_rows:
                continue

            # Restrict to "evidence" rows: A-values that repeat at least
            # once. A determinant value seen only a single time is
            # trivially "100% consistent" with whatever B it happens to
            # sit next to -- that's not evidence of a dependency, just an
            # artifact of high cardinality. Without this, any near-unique
            # column (e.g. a free-text address field with a few repeats)
            # would spuriously "determine" nearly every other column,
            # since almost all of its groups are singletons.
            group_sizes = sub.groupby(a).size()
            repeated_values = group_sizes[group_sizes >= 2].index
            evidence = sub[sub[a].isin(repeated_values)]
            total_rows = len(evidence)
            if total_rows < min_support_rows:
                continue

            # Majority-vote purity ("g3" approximate-FD measure): for each
            # A-value, the *most common* B-value is the "correct" mapping,
            # and every row matching it counts as consistent. This matters
            # for noisy real data -- a single bad row must only cost one
            # violation, not silently disqualify every other row that
            # shares its A-value (which a naive nunique()==1 check would do).
            pair_counts = evidence.groupby([a, b]).size().rename("n").reset_index()
            majority_idx = pair_counts.groupby(a)["n"].idxmax()
            mode_map = pair_counts.loc[majority_idx].set_index(a)[b]

            consistent_mask = evidence[b] == evidence[a].map(mode_map)
            consistent_rows = int(consistent_mask.sum())
            purity = consistent_rows / total_rows

            if purity < min_purity:
                continue

            violation_examples: List[Dict[str, Any]] = []
            if purity < 1.0:
                bad = evidence[~consistent_mask].head(MAX_VIOLATION_EXAMPLES)
                violation_examples = [
                    {"determinant_value": _to_plain(v1), "dependent_value": _to_plain(v2)}
                    for v1, v2 in zip(bad[a], bad[b])
                ]

            results.append({
                "determinant": a,
                "dependent": b,
                "purity": round(purity, 4),
                "support_rows": total_rows,
                "violation_count": total_rows - consistent_rows,
                "violation_examples": violation_examples,
                "distinct_determinant_values": int(evidence[a].nunique()),
            })

    results.sort(key=lambda r: (-r["purity"], -r["support_rows"]))
    return _dedupe_equivalent_pairs(results)


def _dedupe_equivalent_pairs(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """When A -> B and B -> A both hold perfectly, the two columns are
    equivalent keys (e.g. a code and its legacy alias) -- keep just one
    direction so the report doesn't show the same relationship twice."""
    seen_equivalent: set = set()
    deduped = []
    for r in results:
        if r["purity"] >= 0.999999:
            key = frozenset((r["determinant"], r["dependent"]))
            if key in seen_equivalent:
                continue
            seen_equivalent.add(key)
        deduped.append(r)
    return deduped
