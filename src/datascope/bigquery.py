"""
BigQuery engine: profile a table or a SQL query *inside* BigQuery.

Nothing but aggregates ever leaves the warehouse. datascope reads the
schema (table metadata, or a free dry run for a query), writes one
single-pass aggregate query covering every requested column, runs it,
and reshapes the one-row answer into the same profile dict the pandas
engine produces — so the HTML report, quality rules, dbt snippets and
alerts all work unchanged.

    from datascope import profile_bigquery

    profile_bigquery("my-project.sales.orders", output_html="orders.html")
    profile_bigquery("my-project.sales.orders", columns=["order_id", "amount"])
    profile_bigquery(query="SELECT * FROM `my-project.sales.orders` WHERE status = 'paid'")

Just want the SQL, to read it or run it yourself?

    from datascope import BigQueryProfiler
    print(BigQueryProfiler().build_sql("my-project.sales.orders")[0])

What this basic engine covers: row count, nulls, distinct counts, top
values, min / max / mean / std / sum / quartiles (median) for numbers,
length stats for strings, range + weekday split for dates, true/false
split for booleans, and Pearson correlations between numeric columns
(CORR() in the same scan), and referential-integrity checks (one small
anti-join query per declared or suggested reference — see
`references=`). What it deliberately does not (each would need
extra passes over the data): histograms, outlier counts,
duplicate-row detection, composite keys, functional dependencies, and
content-based PII detection (PII is flagged from column names only).
"""
from __future__ import annotations

import os
import re
import warnings
from datetime import date, datetime, timezone
from itertools import combinations
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

import pandas as pd

from .core import DataProfiler
from .html_report import render_html
from .pii import detect_sensitive_data, mask_value
from .quality import generate_dbt_snippet, recommend_rules
from .referential import (alerts_for, build_result, is_child_candidate, is_parent_candidate, keep_suggestion,
                          name_suggests_reference)
from .semantic import infer_semantic_type_from_summary
from .stats import _safe_float

_NUMERIC_TYPES = {"INT64", "INTEGER", "FLOAT64", "FLOAT", "NUMERIC", "BIGNUMERIC", "DECIMAL", "BIGDECIMAL"}
_INTEGER_TYPES = {"INT64", "INTEGER"}
_FLOAT_TYPES = {"FLOAT64", "FLOAT"}
_BOOL_TYPES = {"BOOL", "BOOLEAN"}
# Types profiled by null + distinct count only (compared as JSON text).
_COMPLEX_TYPES = {"STRUCT", "RECORD", "JSON", "GEOGRAPHY", "RANGE", "INTERVAL"}
_DATETIME_NOW = {"DATE": "CURRENT_DATE()", "DATETIME": "CURRENT_DATETIME()", "TIMESTAMP": "CURRENT_TIMESTAMP()"}
# EXTRACT(DAYOFWEEK ...) numbering: 1 = Sunday.
_WEEKDAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")

_TRAILING_SEMICOLON_RE = re.compile(r"(;(\s|--[^\n]*|#[^\n]*|/\*.*?\*/)*)+\Z", re.DOTALL)
_TABLE_REF_RE = re.compile(r"^([\w\-]+[.:])?[\w\-]+\.[\w\-$*]+$")


def _column_kind(field_type: str, mode: str, name: Optional[str] = None) -> str:
    """Collapse a BigQuery type into the handful of shapes we profile.

    Raises ValueError for a type that isn't recognised, rather than
    guessing how to aggregate it (BigQueryProfiler skips such columns
    with a warning).
    """
    t = (field_type or "").upper()
    known = t in _COMPLEX_TYPES
    kind = "complex"
    if t in _NUMERIC_TYPES:
        kind, known = "numeric", True
    elif t == "STRING":
        kind, known = "string", True
    elif t == "BYTES":
        kind, known = "bytes", True
    elif t in _BOOL_TYPES:
        kind, known = "boolean", True
    elif t in _DATETIME_NOW:
        kind, known = "datetime", True
    elif t == "TIME":
        kind, known = "time", True
    if not known:
        where = f" for column {name!r}" if name else ""
        raise ValueError(
            f"Unsupported BigQuery type {field_type!r}{where}."
        )
    # An ARRAY of any known element type is profiled as a complex value.
    return "complex" if (mode or "").upper() == "REPEATED" else kind


def quote_identifier(name: str) -> str:
    return "`" + name.replace("\\", "\\\\").replace("`", "\\`") + "`"


def _table_from_clause(table: str) -> str:
    ref = table.strip().strip("`")
    if not _TABLE_REF_RE.match(ref):
        raise ValueError(
            f"Not a valid BigQuery table reference: {table!r} "
            "(expected 'project.dataset.table' or 'dataset.table')."
        )
    return "`" + ref.replace(":", ".") + "`"


def _query_from_clause(query: str) -> str:
    # Drop the terminating semicolon(s), plus any comments after them.
    q = _TRAILING_SEMICOLON_RE.sub("", query.strip()).rstrip()
    if not q:
        raise ValueError("query is empty.")
    # The closing paren goes on its own line so a trailing `-- comment`
    # in the user's query can't swallow it.
    return "(\n" + q + "\n)"


def _numeric_value(name: str, field_type: str) -> str:
    """A numeric column as FLOAT64 with NaN / +-inf turned into NULL, so
    they can't poison an aggregate. FLOAT64 also keeps SUM from
    overflowing INT64 and keeps NUMERIC results out of Decimal."""
    c = quote_identifier(name)
    if field_type.upper() in _FLOAT_TYPES:
        return f"IF(IS_NAN({c}) OR IS_INF({c}), NULL, {c})"
    return f"CAST({c} AS FLOAT64)"


def correlation_expressions(numeric: Sequence[Tuple[int, str, str]]) -> List[Tuple[str, str]]:
    """(result_alias, CORR expression) for every pair of `numeric`
    columns, given as (field index, name, bigquery_type). CORR skips rows
    where either side is NULL — pairwise-complete, like pandas."""
    return [
        (f"corr__{i}__{j}", f"CORR({_numeric_value(a, ta)}, {_numeric_value(b, tb)})")
        for (i, a, ta), (j, b, tb) in combinations(numeric, 2)
    ]


def _column_expressions(alias: str, name: str, field_type: str, mode: str,
                        top_n: int, exact_distinct: bool) -> List[Tuple[str, str]]:
    """(result_column_alias, sql_expression) pairs for one column."""
    c = quote_identifier(name)
    kind = _column_kind(field_type, mode, name)
    t = field_type.upper()
    out: List[Tuple[str, str]] = []

    def add(metric: str, expr: str) -> None:
        out.append((f"{alias}__{metric}", expr))

    if (mode or "").upper() == "REPEATED":
        # A stored ARRAY is never NULL; "no value" shows up as empty.
        add("missing", f"COUNTIF(IFNULL(ARRAY_LENGTH({c}), 0) = 0)")
    else:
        add("missing", f"COUNTIF({c} IS NULL)")

    # COUNT(DISTINCT) isn't defined for ARRAY/STRUCT/JSON/GEOGRAPHY, so
    # those are compared by their JSON text instead.
    distinct_arg = f"TO_JSON_STRING({c})" if kind == "complex" else c
    if exact_distinct:
        add("distinct", f"COUNT(DISTINCT {distinct_arg})")
    else:
        add("distinct", f"APPROX_COUNT_DISTINCT({distinct_arg})")

    if kind == "numeric":
        x = _numeric_value(name, field_type)
        if t in _FLOAT_TYPES:
            add("infinite", f"COUNTIF(IS_INF({c}))")
            add("nan", f"COUNTIF(IS_NAN({c}))")
        add("min", f"MIN({x})")
        add("max", f"MAX({x})")
        add("mean", f"AVG({x})")
        add("std", f"STDDEV_SAMP({x})")
        add("sum", f"SUM({x})")
        add("quartiles", f"APPROX_QUANTILES({x}, 4)")
        add("zeros", f"COUNTIF({x} = 0)")
        add("negatives", f"COUNTIF({x} < 0)")
    elif kind in ("string", "bytes"):
        length = f"CHAR_LENGTH({c})" if kind == "string" else f"BYTE_LENGTH({c})"
        add("min_length", f"MIN({length})")
        add("max_length", f"MAX({length})")
        add("mean_length", f"AVG({length})")
        if kind == "string":
            add("blank", f"COUNTIF(TRIM({c}) = '')")
        else:
            add("blank", f"COUNTIF({length} = 0)")
    elif kind == "boolean":
        add("true", f"COUNTIF({c})")
    elif kind == "datetime":
        add("min", f"MIN({c})")
        add("max", f"MAX({c})")
        add("range_days", f"DATE_DIFF(CAST(MAX({c}) AS DATE), CAST(MIN({c}) AS DATE), DAY)")
        add("future", f"COUNTIF({c} > {_DATETIME_NOW[t]})")
        for i in range(1, 8):
            add(f"dow{i}", f"COUNTIF(EXTRACT(DAYOFWEEK FROM {c}) = {i})")
    elif kind == "time":
        add("min", f"MIN({c})")
        add("max", f"MAX({c})")

    if kind not in ("complex", "bytes") and top_n > 0:
        # +1 because NULL is counted as a value and dropped afterwards.
        add("top", f"APPROX_TOP_COUNT(CAST({c} AS STRING), {top_n + 1})")
    return out


def build_profile_sql(
    from_clause: str,
    fields: Sequence[Tuple[str, str, str]],
    top_n_values: int = 10,
    exact_distinct: bool = True,
    alias_offset: int = 0,
    extra: Sequence[Tuple[str, str]] = (),
) -> str:
    """The profiling query: one scan, one result row.

    `from_clause` is a quoted table or a parenthesised subquery; `fields`
    is (name, bigquery_type, mode) per column. Result columns are named
    `c<i>__<metric>` (plus `n_rows`), where i is the column's position
    in `fields` offset by `alias_offset`. `extra` is further
    (result_alias, expression) pairs, e.g. `correlation_expressions`.
    """
    lines = ["  COUNT(*) AS n_rows"]
    for i, (name, field_type, mode) in enumerate(fields):
        alias = f"c{alias_offset + i}"
        lines.append(f"  -- {name.replace(chr(10), ' ')} ({field_type}{' ' + mode if (mode or '').upper() == 'REPEATED' else ''})")
        for result_alias, expr in _column_expressions(alias, name, field_type, mode, top_n_values, exact_distinct):
            lines.append(f"  {expr} AS {result_alias}")
    if extra:
        lines.append("  -- correlations between numeric columns")
        lines.extend(f"  {expr} AS {result_alias}" for result_alias, expr in extra)
    body = []
    for i, line in enumerate(lines):
        is_comment = line.lstrip().startswith("--")
        last_expr = not any(not l.lstrip().startswith("--") for l in lines[i + 1:])
        body.append(line if (is_comment or last_expr) else line + ",")
    return "SELECT\n" + "\n".join(body) + f"\nFROM {from_clause} AS _datascope_src"


def build_reference_sql(child_from: str, child_col: str, parent_from: str, parent_col: str,
                        as_text: bool = False, sample: int = 5) -> str:
    """Referential-integrity check as one anti-join: child values (NULLs
    excluded) with no match among the parent's distinct values. Returns
    at most `sample` rows — the most frequent orphan values — each also
    carrying the totals (`orphans` rows, `orphan_values` distinct), so
    no rows back means no orphans."""
    c, p = quote_identifier(child_col), quote_identifier(parent_col)
    cv = f"CAST({c} AS STRING)" if as_text else c
    pv = f"CAST({p} AS STRING)" if as_text else p
    return (
        "SELECT\n"
        "  CAST(child.v AS STRING) AS value,\n"
        "  COUNT(*) AS n,\n"
        "  SUM(COUNT(*)) OVER () AS orphans,\n"
        "  COUNT(*) OVER () AS orphan_values\n"
        f"FROM (SELECT {cv} AS v FROM {child_from} AS _datascope_src WHERE {c} IS NOT NULL) AS child\n"
        f"LEFT JOIN (SELECT DISTINCT {pv} AS v FROM {parent_from} AS _datascope_ref WHERE {p} IS NOT NULL) AS parent\n"
        "  ON child.v = parent.v\n"
        "WHERE parent.v IS NULL\n"
        "GROUP BY child.v\n"
        "ORDER BY n DESC, value\n"
        f"LIMIT {int(sample)}"
    )


class _RefCheck(NamedTuple):
    child: str            # profiled column name
    parent: str           # parent column name
    label: str            # how the parent is named in the report
    source: str           # "declared" | "suggested"
    same_table: bool
    sql: str
    as_text: bool = False  # child and parent types differ: compared as STRING


class _Plan(NamedTuple):
    fields: List[Tuple[str, str, str]]
    sqls: List[str]
    num_bytes: Optional[int]
    default_name: str
    skipped: List[Dict[str, Any]]
    ref_checks: List[_RefCheck]


# BigQuery on-demand list price (US multi-region), USD per TiB scanned.
# It differs by region and doesn't apply to capacity (slot) pricing —
# override with `price_per_tib_usd`.
ON_DEMAND_USD_PER_TIB = 6.25


def format_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TB"  # pragma: no cover


class UnsupportedColumnWarning(UserWarning):
    """A column was left out of the profile because of its type."""


def _skip_message(name: str, field_type: str) -> str:
    return f"Column '{name}' was skipped: unsupported BigQuery type {field_type}."


class BigQueryProfiler:
    """Profile a BigQuery table or query by pushing the work down as SQL.

    Parameters
    ----------
    client : google.cloud.bigquery.Client, optional
        Reused if given; otherwise one is created from `project` /
        `location` and your default Google credentials.
    top_n_values : most-frequent values kept per column (0 disables).
    exact_distinct : COUNT(DISTINCT) when True (exact, heavier on very
        large tables); APPROX_COUNT_DISTINCT (HyperLogLog++) when False.
    max_columns_per_query : wide tables are split into several queries
        of at most this many columns each.
    max_correlation_cols : Pearson correlations are computed between the
        first this-many numeric columns (n*(n-1)/2 CORR() aggregates in
        the first query); 0 turns them off.
    max_reference_suggestions : likely same-table references (e.g.
        `parent_customer_id` -> `customer_id`) checked automatically, one
        small query each; 0 turns suggestions off. Declared `references`
        are always checked.
    maximum_bytes_billed : safety cap passed to every query job.
    """

    def __init__(
        self,
        client: Any = None,
        project: Optional[str] = None,
        location: Optional[str] = None,
        top_n_values: int = 10,
        exact_distinct: bool = True,
        max_columns_per_query: int = 100,
        maximum_bytes_billed: Optional[int] = None,
        max_correlation_cols: int = 30,
        max_reference_suggestions: int = 5,
    ):
        if max_columns_per_query < 1:
            raise ValueError("max_columns_per_query must be >= 1")
        self._client = client
        self.project = project
        self.location = location
        self.top_n_values = top_n_values
        self.exact_distinct = exact_distinct
        self.max_columns_per_query = max_columns_per_query
        self.maximum_bytes_billed = maximum_bytes_billed
        self.max_correlation_cols = max_correlation_cols
        self.max_reference_suggestions = max_reference_suggestions

    # ------------------------------------------------------------ client
    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import bigquery
            except ImportError as exc:  # pragma: no cover - depends on env
                raise ImportError(
                    "BigQuery profiling needs the google-cloud-bigquery package: "
                    'pip install "datascope[bigquery]"'
                ) from exc
            self._client = bigquery.Client(project=self.project, location=self.location)
        return self._client

    def _job_config(self, dry_run: bool = False) -> Any:
        try:
            from google.cloud import bigquery
        except ImportError:  # a caller-supplied client that isn't the Google one
            return None
        config = bigquery.QueryJobConfig(dry_run=dry_run, use_query_cache=not dry_run)
        if not dry_run:
            config.labels = {"tool": "datascope"}
            if self.maximum_bytes_billed is not None:
                config.maximum_bytes_billed = self.maximum_bytes_billed
        return config

    def _run(self, sql: str, dry_run: bool = False) -> Any:
        config = self._job_config(dry_run=dry_run)
        kwargs = {"job_config": config} if config is not None else {}
        if self.location:
            kwargs["location"] = self.location
        return self.client.query(sql, **kwargs)

    # ------------------------------------------------------------ schema
    def _resolve_source(self, table: Optional[str], query: Optional[str]) -> Tuple[str, List[Any], Optional[int], str]:
        """-> (from_clause, schema fields, stored bytes if known, default source name)"""
        if (table is None) == (query is None):
            raise ValueError("Pass exactly one of `table` or `query`.")
        if table is not None:
            from_clause = _table_from_clause(table)
            ref = from_clause.strip("`")
            tbl = self.client.get_table(ref)
            return from_clause, list(tbl.schema), getattr(tbl, "num_bytes", None), ref

        from_clause = _query_from_clause(query)
        probe = f"SELECT * FROM {from_clause} AS _datascope_src LIMIT 0"
        job = self._run(probe, dry_run=True)  # dry run: free, returns the schema
        schema = getattr(job, "schema", None)
        if not schema:
            schema = self._run(probe).result().schema
        return from_clause, list(schema), None, "query"

    @staticmethod
    def _select_fields(schema: List[Any], columns: Optional[Sequence[str]]) -> List[Tuple[str, str, str]]:
        fields = [(f.name, f.field_type, getattr(f, "mode", None) or "NULLABLE") for f in schema]
        if columns is None:
            return fields
        if isinstance(columns, str):
            columns = [columns]
        by_lower = {f[0].lower(): f for f in fields}  # BigQuery column names are case-insensitive
        missing = [c for c in columns if c.lower() not in by_lower]
        if missing:
            raise ValueError(
                f"Column(s) not found: {missing}. Available: {[f[0] for f in fields]}"
            )
        seen, picked = set(), []
        for c in columns:
            if c.lower() not in seen:
                seen.add(c.lower())
                picked.append(by_lower[c.lower()])
        return picked

    def _plan(self, table: Optional[str], query: Optional[str], columns: Optional[Sequence[str]],
              references: Optional[Dict[str, str]] = None) -> _Plan:
        from_clause, schema, num_bytes, default_name = self._resolve_source(table, query)
        fields, skipped = [], []
        for name, field_type, mode in self._select_fields(schema, columns):
            try:
                _column_kind(field_type, mode, name)
            except ValueError:
                # Don't guess how to aggregate an unknown type, and don't
                # let one odd column block the rest: leave it out, loudly.
                skipped.append({"name": name, "dtype": field_type,
                                "reason": f"unsupported BigQuery type {field_type}"})
                warnings.warn(_skip_message(name, field_type), UnsupportedColumnWarning, stacklevel=4)
            else:
                fields.append((name, field_type, mode))
        # Correlations ride along in the first query rather than a query
        # of their own: for a table under max_columns_per_query columns
        # that query already reads every numeric column, so they cost
        # no extra bytes.
        corr = correlation_expressions(self._correlation_fields(fields))
        sqls = [
            build_profile_sql(from_clause, fields[start:start + self.max_columns_per_query],
                              top_n_values=self.top_n_values, exact_distinct=self.exact_distinct,
                              alias_offset=start, extra=corr if start == 0 else ())
            for start in range(0, len(fields), self.max_columns_per_query)
        ] or [build_profile_sql(from_clause, [])]
        ref_checks = self._plan_references(from_clause, schema, fields, references)
        return _Plan(fields, sqls, num_bytes, default_name, skipped, ref_checks)

    def _plan_references(self, from_clause: str, schema: List[Any], fields: List[Tuple[str, str, str]],
                         references: Optional[Dict[str, str]]) -> List[_RefCheck]:
        """Declared checks, then same-table suggestions picked from column
        names and types. Suggestions are planned before the profile runs
        (so estimate() can price them) and only actually run if the
        profile confirms the parent looks like a key — see profile()."""
        profiled = {name.lower(): (name, t, mode) for name, t, mode in fields}
        whole = {f.name.lower(): (f.name, f.field_type, getattr(f, "mode", None) or "NULLABLE") for f in schema}
        checks: List[_RefCheck] = []
        for child, ref in (references or {}).items():
            if child.lower() not in profiled:
                raise ValueError(f"references: column {child!r} is not among the profiled columns.")
            c_name, c_type, c_mode = profiled[child.lower()]
            if "." in ref:
                tbl_ref, _, p_col = ref.rpartition(".")
                parent_from = _table_from_clause(tbl_ref)
                parent_schema = {f.name.lower(): (f.name, f.field_type, getattr(f, "mode", None) or "NULLABLE")
                                 for f in self.client.get_table(parent_from.strip("`")).schema}
                where, label, same = parent_schema, None, False
            else:
                parent_from, p_col, where, label, same = from_clause, ref, whole, None, True
            if p_col.lower() not in where:
                raise ValueError(f"references: {child!r} -> {ref!r}, but column {p_col!r} was not found there.")
            p_name, p_type, p_mode = where[p_col.lower()]
            c_kind, p_kind = _column_kind(c_type, c_mode, c_name), _column_kind(p_type, p_mode, p_name)
            if "complex" in (c_kind, p_kind):
                raise ValueError(f"references: {c_name!r} -> {ref!r}: ARRAY/STRUCT/JSON columns can't be keys.")
            label = p_name if same else f"{parent_from.strip('`')}.{p_name}"
            as_text = c_kind != p_kind
            sql = build_reference_sql(from_clause, c_name, parent_from, p_name, as_text=as_text)
            checks.append(_RefCheck(c_name, p_name, label, "declared", same, sql, as_text))

        if self.max_reference_suggestions > 0:
            declared = {c.child for c in checks}
            keyish = [(n, t, m) for n, t, m in fields
                      if _column_kind(t, m, n) == "string" or t.upper() in _INTEGER_TYPES]
            suggested = []
            for c_name, c_type, _ in keyish:
                if c_name in declared:
                    continue
                for p_name, p_type, _ in keyish:
                    same_kind = (c_type.upper() in _INTEGER_TYPES) == (p_type.upper() in _INTEGER_TYPES)
                    if same_kind and name_suggests_reference(c_name, p_name):
                        suggested.append(_RefCheck(c_name, p_name, p_name, "suggested", True,
                                                   build_reference_sql(from_clause, c_name, from_clause, p_name)))
            checks += suggested[: self.max_reference_suggestions]
        return checks

    def _numeric_fields(self, fields: Sequence[Tuple[str, str, str]]) -> List[Tuple[int, str, str]]:
        return [(i, name, t) for i, (name, t, mode) in enumerate(fields)
                if _column_kind(t, mode, name) == "numeric"]

    def _correlation_fields(self, fields: Sequence[Tuple[str, str, str]]) -> List[Tuple[int, str, str]]:
        numeric = self._numeric_fields(fields)[: max(self.max_correlation_cols, 0)]
        return numeric if len(numeric) >= 2 else []

    def _correlations(self, fields, row: Dict[str, Any], column_profiles) -> Optional[Dict[str, Any]]:
        """Shape the CORR() results like the pandas engine's matrix: NaN
        (constant or too few rows) becomes 0, the diagonal is 1 unless the
        column has no variance, values rounded to 3 places."""
        numeric = self._correlation_fields(fields)
        if not numeric:
            return None
        n = len(numeric)
        matrix = [[0.0] * n for _ in range(n)]
        for a in range(n):
            std = (column_profiles[numeric[a][0]].get("numeric_stats") or {}).get("std")
            matrix[a][a] = 1.0 if std else 0.0
            for b in range(a + 1, n):
                v = _safe_float(row.get(f"corr__{numeric[a][0]}__{numeric[b][0]}"))
                matrix[a][b] = matrix[b][a] = round(max(-1.0, min(1.0, v)), 3) if v is not None else 0.0
        return {
            "columns": [name for _, name, _ in numeric],
            "matrix": matrix,
            "truncated": len(self._numeric_fields(fields)) > n,
        }

    # ------------------------------------------------------------ public
    def build_sql(self, table: Optional[str] = None, query: Optional[str] = None,
                  columns: Optional[Sequence[str]] = None,
                  references: Optional[Dict[str, str]] = None) -> List[str]:
        """The profiling SQL that `profile()` would run, without running
        it: the profiling queries, then one referential-integrity query
        per declared or suggested reference (a suggestion is skipped at
        run time if the profile shows its parent isn't a key). Only reads
        the schema (table metadata / a dry run)."""
        plan = self._plan(table, query, columns, references)
        return plan.sqls + [c.sql for c in plan.ref_checks]

    def estimate(self, table: Optional[str] = None, query: Optional[str] = None,
                 columns: Optional[Sequence[str]] = None,
                 price_per_tib_usd: float = ON_DEMAND_USD_PER_TIB,
                 references: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """How much data `profile()` would scan, without running it.

        Uses BigQuery dry runs (free; the same number the console shows
        as "This query will process ..."). The figure is an upper bound:
        clustered tables and cached results can come in lower.
        `estimated_cost_usd` is bytes x the on-demand price and ignores
        the monthly free tier; it doesn't apply if you pay for capacity.
        """
        # Checked first: without a dry-run config nothing below is safe to send.
        if self._job_config(dry_run=True) is None:
            raise RuntimeError(
                "Estimating needs a dry run, which requires the google-cloud-bigquery "
                'package: pip install "datascope[bigquery]"'
            )
        plan = self._plan(table, query, columns, references)
        sqls, skipped = plan.sqls + [c.sql for c in plan.ref_checks], plan.skipped
        total = 0
        for sql in sqls:
            job = self._run(sql, dry_run=True)
            total += int(getattr(job, "total_bytes_processed", None) or 0)
        return {
            "bytes_processed": total,
            "bytes_processed_human": format_bytes(total),
            "estimated_cost_usd": round(total / 1024 ** 4 * price_per_tib_usd, 4),
            "price_per_tib_usd": price_per_tib_usd,
            "queries": len(sqls),
            "sql": sqls,
            "skipped_columns": skipped,
        }

    def profile(self, table: Optional[str] = None, query: Optional[str] = None,
                columns: Optional[Sequence[str]] = None, source_name: Optional[str] = None,
                references: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """`references` declares referential-integrity checks as {child
        column: parent}, where the parent is a column of the same source
        ("customer_id") or of another table
        ("project.dataset.customers.id")."""
        fields, sqls, num_bytes, default_name, skipped, ref_checks = self._plan(table, query, columns, references)

        row: Dict[str, Any] = {}
        bytes_processed = 0
        for sql in sqls:
            job = self._run(sql)
            rows = list(job.result())
            row.update(dict(rows[0].items()) if rows else {})
            bytes_processed += int(getattr(job, "total_bytes_processed", None) or 0)

        n_rows = int(row.get("n_rows") or 0)
        column_profiles = [
            self._column_profile(f"c{i}", name, field_type, mode, row, n_rows)
            for i, (name, field_type, mode) in enumerate(fields)
        ]
        n_cols = len(column_profiles)
        total_missing = sum(c["missing"] for c in column_profiles)
        total_cells = n_rows * n_cols

        type_distribution: Dict[str, int] = {}
        for c in column_profiles:
            type_distribution[c["semantic_type"]] = type_distribution.get(c["semantic_type"], 0) + 1

        ref_sqls_run: List[str] = []
        referential_integrity, bytes_processed = self._check_references(
            ref_checks, column_profiles, ref_sqls_run, bytes_processed)
        correlations = self._correlations(fields, row, column_profiles)
        high_correlation_pairs = DataProfiler()._high_correlation_pairs(correlations)

        pk_candidates = []
        if n_rows and self.exact_distinct:
            pk_candidates = [{"columns": [c["name"]], "type": "single"}
                             for c in column_profiles if c["missing"] == 0 and c["unique"] == n_rows]

        result: Dict[str, Any] = {
            "meta": {
                "source_name": str(source_name or default_name),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "n_rows": n_rows,
                "n_cols": n_cols,
                "memory_mb": round(num_bytes / (1024 * 1024), 3) if num_bytes is not None else None,
                # Not measured by this engine (see module docstring).
                "duplicate_rows": None,
                "duplicate_rows_pct": None,
                "engine": "bigquery",
                "sql": sqls + ref_sqls_run,
                "bytes_processed": bytes_processed,
                "exact_distinct": self.exact_distinct,
                # Columns left out because their type isn't supported.
                "skipped_columns": skipped,
            },
            "overview": {
                "type_distribution": type_distribution,
                "total_missing_cells": int(total_missing),
                "total_missing_pct": round(100 * total_missing / total_cells, 3) if total_cells else 0.0,
                "sensitive_columns_count": sum(1 for c in column_profiles if c["sensitive"]["is_sensitive"]),
            },
            "columns": column_profiles,
            "correlations": correlations,
            "missing_correlation": None,
            "pk_candidates": pk_candidates,
            "high_correlation_pairs": high_correlation_pairs,
            "duplicate_columns": [],
            "functional_dependencies": [],
            "referential_integrity": referential_integrity,
        }
        alerts = [{"severity": "warning", "column": None, "message": _skip_message(sk["name"], sk["dtype"])}
                  for sk in skipped]
        result["overview"]["alerts"] = (alerts + DataProfiler()._build_alerts(column_profiles, 0, n_rows,
                                                                             high_correlation_pairs)
                                        + alerts_for(referential_integrity))
        return result

    def to_html(self, profile_dict: Dict[str, Any], output_path: str) -> str:
        render_html(profile_dict, output_path)
        return output_path

    def _check_references(self, checks: Sequence[_RefCheck], column_profiles: Sequence[Dict[str, Any]],
                          sqls_run: List[str], bytes_processed: int) -> Tuple[List[Dict[str, Any]], int]:
        by_name = {c["name"]: c for c in column_profiles}
        results = []
        for chk in checks:
            child = by_name[chk.child]
            if chk.source == "suggested":
                parent = by_name.get(chk.parent)
                if parent is None or not is_parent_candidate(parent) or not is_child_candidate(child):
                    continue
            job = self._run(chk.sql)
            sqls_run.append(chk.sql)
            bytes_processed += int(getattr(job, "total_bytes_processed", None) or 0)
            rows = [dict(r.items()) for r in job.result()]
            rows = [r for r in rows if r.get("value") is not None]
            r = build_result(
                chk.child, chk.label, chk.source, chk.same_table,
                checked=child["count"] - child["missing"],
                orphans=int(rows[0]["orphans"]) if rows else 0,
                orphan_values=int(rows[0]["orphan_values"]) if rows else 0,
                samples=[(x["value"], x["n"]) for x in rows],
                sensitive=child["sensitive"]["is_sensitive"],
                compared_as="text" if chk.as_text else "value",
            )
            if chk.source == "declared" or keep_suggestion(r):
                results.append(r)
        return results, bytes_processed

    # -------------------------------------------------------- per column
    def _column_profile(self, alias: str, name: str, field_type: str, mode: str,
                        row: Dict[str, Any], n_rows: int) -> Dict[str, Any]:
        def get(metric: str) -> Any:
            return row.get(f"{alias}__{metric}")

        kind = _column_kind(field_type, mode, name)
        repeated = (mode or "").upper() == "REPEATED"
        missing = int(get("missing") or 0)
        non_null = max(n_rows - missing, 0)
        # An approximate distinct count can overshoot the row count.
        unique = min(int(get("distinct") or 0), non_null)

        top_values = []
        for item in (get("top") or []):
            value, count = _top_entry(item)
            if value is None:
                continue
            top_values.append({"value": str(value)[:200], "count": int(count),
                               "pct": round(100 * count / n_rows, 2) if n_rows else 0.0})
        top_values = top_values[: self.top_n_values]
        if top_values and top_values[0]["count"] <= 1 and n_rows > 1:
            # Every value occurs once: a "top 10" would just be ten
            # arbitrary raw values, so show none.
            top_values = []

        mean_length = _safe_float(get("mean_length"))
        semantic_kind = {"bytes": "other", "time": "other", "complex": "other"}.get(kind, kind)
        semantic_type, confidence, notes = infer_semantic_type_from_summary(
            name, semantic_kind, non_null, unique, avg_length=mean_length,
            top_values=[tv["value"] for tv in top_values],
        )
        notes = list(notes)
        if repeated:
            notes.append("Repeated (ARRAY) column — empty arrays are counted as missing.")
        if not self.exact_distinct:
            notes.append("Distinct count is approximate (APPROX_COUNT_DISTINCT).")

        profile: Dict[str, Any] = {
            "name": name,
            "dtype": f"ARRAY<{field_type}>" if repeated else field_type,
            "semantic_type": semantic_type,
            "semantic_type_confidence": confidence,
            "semantic_notes": notes,
            "count": n_rows,
            "missing": missing,
            "missing_pct": round(100 * missing / n_rows, 3) if n_rows else 0.0,
            "unique": unique,
            "unique_pct": round(100 * unique / non_null, 3) if non_null else 0.0,
            "memory_bytes": None,
            "numeric_stats": None, "string_stats": None, "datetime_stats": None,
            "boolean_stats": None, "histogram": None, "length_histogram": None,
            "top_values": top_values,
        }

        if kind == "numeric":
            profile["numeric_stats"] = self._numeric_stats(get, field_type, non_null)
        elif kind in ("string", "bytes") and non_null:
            profile["string_stats"] = {
                "min_length": int(get("min_length") or 0),
                "max_length": int(get("max_length") or 0),
                "mean_length": round(mean_length or 0.0, 2),
                "empty_or_whitespace": int(get("blank") or 0),
            }
        elif kind == "boolean" and non_null:
            true_count = int(get("true") or 0)
            profile["boolean_stats"] = {
                "true_count": true_count,
                "false_count": non_null - true_count,
                "true_pct": round(100 * true_count / non_null, 2),
            }
        elif kind == "datetime" and non_null:
            weekdays = {day: int(get(f"dow{i}") or 0) for i, day in enumerate(_WEEKDAYS, start=1)}
            profile["datetime_stats"] = {
                "min_date": _iso(get("min")),
                "max_date": _iso(get("max")),
                "range_days": int(get("range_days") or 0),
                "weekday_distribution": {d: n for d, n in weekdays.items() if n},
                "future_dates": int(get("future") or 0),
            }
        elif kind == "time" and non_null:
            profile["datetime_stats"] = {"min_date": _iso(get("min")), "max_date": _iso(get("max"))}

        # Name-based only: content checks would mean pulling rows out.
        sensitive = detect_sensitive_data(pd.Series([], dtype=object), name, skip_content=True)
        profile["sensitive"] = sensitive
        if sensitive["is_sensitive"]:
            profile["top_values"] = [{**tv, "value": mask_value(tv["value"])} for tv in top_values]

        profile["quality_rules"] = recommend_rules(profile)
        profile["dbt_snippet"] = generate_dbt_snippet(profile)
        return profile

    @staticmethod
    def _numeric_stats(get, field_type: str, non_null: int) -> Dict[str, Any]:
        infinite = int(get("infinite") or 0)
        nan = int(get("nan") or 0)
        n = non_null - infinite - nan  # values the aggregates actually saw
        if n <= 0 and not infinite:
            return {}
        quartiles = [_safe_float(q) for q in (get("quartiles") or [])]
        q1, median, q3 = (quartiles[1], quartiles[2], quartiles[3]) if len(quartiles) == 5 else (None, None, None)
        lo, hi = _safe_float(get("min")), _safe_float(get("max"))
        zeros, negatives = int(get("zeros") or 0), int(get("negatives") or 0)
        # Outlier counts, skewness and kurtosis need a second pass over
        # the data and are left out rather than reported as zero.
        return {
            "mean": _safe_float(get("mean")),
            "std": _safe_float(get("std")),
            "min": lo,
            "q1": q1,
            "median": median,
            "q3": q3,
            "max": hi,
            "range": _safe_float(hi - lo) if lo is not None and hi is not None else None,
            "sum": _safe_float(get("sum")),
            "zeros": zeros,
            "zeros_pct": round(100 * zeros / n, 2) if n > 0 else 0.0,
            "negatives": negatives,
            "negatives_pct": round(100 * negatives / n, 2) if n > 0 else 0.0,
            "skewness": None,
            "kurtosis": None,
            "is_integer_like": field_type.upper() in _INTEGER_TYPES,
            "infinite_count": infinite,
            "nan_count": nan,
            "quantiles_approximate": True,
        }


def _top_entry(item: Any) -> Tuple[Any, int]:
    """APPROX_TOP_COUNT yields STRUCT<value, count>; clients hand that
    back as a dict or a Row."""
    if isinstance(item, dict):
        return item.get("value"), int(item.get("count") or 0)
    try:
        return item["value"], int(item["count"] or 0)
    except (KeyError, TypeError, IndexError):
        return item[0], int(item[1] or 0)


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    s = str(value)
    # "2024-01-02 03:04:05+00" -> "2024-01-02T03:04:05+00"
    return s.replace(" ", "T", 1) if re.match(r"^\d{4}-\d{2}-\d{2} ", s) else s


def profile_bigquery(
    table: Optional[str] = None,
    *,
    query: Optional[str] = None,
    columns: Optional[Sequence[str]] = None,
    output_html: Optional[str] = "data_profile_report.html",
    source_name: Optional[str] = None,
    open_browser: bool = False,
    references: Optional[Dict[str, str]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """One-liner: profile a BigQuery `table` ("project.dataset.table") or
    the result of a SQL `query`, computing everything inside BigQuery.

    `columns` restricts profiling to a subset (default: every column).
    `references` declares referential-integrity checks, e.g.
    {"customer_id": "my-project.sales.customers.id"} or, within the same
    table, {"manager_id": "employee_id"}.
    Writes the HTML report to `output_html` (pass None to skip it) and
    returns the profile dict — same shape as `datascope.profile()`. The
    SQL that ran is in `result["meta"]["sql"]`.

    Extra keyword arguments go to `BigQueryProfiler` (client, project,
    location, exact_distinct, top_n_values, maximum_bytes_billed, ...).
    """
    profiler = BigQueryProfiler(**kwargs)
    result = profiler.profile(table=table, query=query, columns=columns, source_name=source_name,
                              references=references)
    if output_html:
        profiler.to_html(result, output_html)
        if open_browser:
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(output_html)}")
    return result


def estimate_bigquery_cost(
    table: Optional[str] = None,
    *,
    query: Optional[str] = None,
    columns: Optional[Sequence[str]] = None,
    price_per_tib_usd: float = ON_DEMAND_USD_PER_TIB,
    references: Optional[Dict[str, str]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Dry-run the profiling SQL for `table` / `query` and return how many
    bytes it would scan and the approximate on-demand cost. Runs nothing
    and costs nothing. Same arguments as `profile_bigquery`."""
    return BigQueryProfiler(**kwargs).estimate(table=table, query=query, columns=columns,
                                               price_per_tib_usd=price_per_tib_usd, references=references)
