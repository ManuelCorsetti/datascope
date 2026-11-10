"""
A stand-in for google.cloud.bigquery.Client that actually *executes* the
SQL datascope generates, so the BigQuery engine can be tested end to end
without a GCP project.

Each query is parsed with sqlglot's BigQuery dialect (so SQL that isn't
valid BigQuery syntax fails here), transpiled to DuckDB and run against
in-memory tables. It is a close approximation, not BigQuery itself:

* APPROX_TOP_COUNT has no DuckDB equivalent with the same return type,
  so it is computed with an exact GROUP BY and spliced into the row.
* DuckDB's quantile and distinct estimators differ from BigQuery's.
* DAYOFWEEK is renumbered (BigQuery counts from 1, DuckDB from 0).
"""
from __future__ import annotations

import re
from collections import namedtuple
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd
import sqlglot
from sqlglot import exp

import logging
logging.getLogger("sqlglot").setLevel(logging.ERROR)  # APPROX_TOP_COUNT is handled by hand below

SchemaField = namedtuple("SchemaField", "name field_type mode")

_TOP_RE = re.compile(r"^\s*APPROX_TOP_COUNT\((?P<expr>.+), (?P<n>\d+)\) AS (?P<alias>c\d+__top),?\s*$", re.MULTILINE)
_FROM_RE = re.compile(r"\nFROM (?P<src>.+) AS _datascope_src\s*\Z", re.DOTALL)


def _bq_type(duck_type: str) -> SchemaField:
    t = str(duck_type).upper()
    mode = "NULLABLE"
    if t.endswith("[]"):
        t, mode = t[:-2], "REPEATED"
    if t.startswith("DECIMAL"):
        bq = "NUMERIC"
    elif t.startswith("STRUCT"):
        bq = "RECORD"
    else:
        bq = {
            "BIGINT": "INT64", "INTEGER": "INT64", "SMALLINT": "INT64", "TINYINT": "INT64", "HUGEINT": "INT64",
            "DOUBLE": "FLOAT64", "FLOAT": "FLOAT64", "VARCHAR": "STRING", "BOOLEAN": "BOOL",
            "DATE": "DATE", "TIME": "TIME", "TIMESTAMP": "DATETIME", "TIMESTAMP_NS": "DATETIME",
            "TIMESTAMP WITH TIME ZONE": "TIMESTAMP", "BLOB": "BYTES", "JSON": "JSON",
        }.get(t, t)  # unmapped types keep their own name -> "unsupported"
    return SchemaField("", bq, mode)


class _Row(dict):
    """dict that also behaves like bigquery.Row for .items()/[] access."""


class _Result(list):
    def __init__(self, rows: List[_Row], schema: List[SchemaField]):
        super().__init__(rows)
        self.schema = schema


class _Job:
    def __init__(self, rows: Optional[List[_Row]], schema: List[SchemaField]):
        self._rows = rows
        self.schema = schema
        self.total_bytes_processed = 5 * 1024 * 1024 if rows is None else 1234  # dry run: the estimate

    def result(self) -> _Result:
        return _Result(self._rows or [], self.schema)


class _Table:
    def __init__(self, schema: List[SchemaField], num_bytes: int):
        self.schema = schema
        self.num_bytes = num_bytes


class DuckDBBigQueryClient:
    def __init__(self, project: str = "demo", dataset: str = "shop"):
        self.project, self.dataset = project, dataset
        self.con = duckdb.connect(":memory:")
        self.con.execute("SET TimeZone = 'UTC'")
        self.con.execute(f"ATTACH ':memory:' AS {project}")
        self.con.execute(f"CREATE SCHEMA {project}.{dataset}")
        self.queries: List[str] = []       # every statement received, in BigQuery SQL
        self.dry_runs: List[str] = []

    def load(self, table: str, df: pd.DataFrame) -> None:
        self.con.register("_incoming", df)
        self.con.execute(f"CREATE OR REPLACE TABLE {self.project}.{self.dataset}.{table} AS SELECT * FROM _incoming")
        self.con.unregister("_incoming")

    # --------------------------------------------------- client surface
    def get_table(self, ref: str) -> _Table:
        desc = self.con.execute(f"DESCRIBE {self._qualify(ref)}").fetchall()
        schema = [_bq_type(r[1])._replace(name=r[0]) for r in desc]
        return _Table(schema, num_bytes=5 * 1024 * 1024)

    def query(self, sql: str, job_config: Any = None, **_: Any) -> _Job:
        if job_config is not None and getattr(job_config, "dry_run", False):
            self.dry_runs.append(sql)
            return _Job(None, self._schema_of(sql))
        self.queries.append(sql)
        tops = {m.group("alias"): (m.group("expr"), int(m.group("n"))) for m in _TOP_RE.finditer(sql)}
        runnable = _TOP_RE.sub("", sql)
        runnable = re.sub(r",(\s*(?:--[^\n]*\n\s*)*)\nFROM ", r"\1\nFROM ", runnable)
        rel = self.con.execute(self._to_duckdb(runnable))
        names = [d[0] for d in rel.description]
        rows = [_Row(zip(names, r)) for r in rel.fetchall()]
        if tops and rows:
            src = _FROM_RE.search(sql).group("src")
            for alias, (expr, n) in tops.items():
                top_sql = (f"SELECT {expr} AS value, COUNT(*) AS count FROM {src} AS _datascope_src "
                           f"GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {n}")
                rows[0][alias] = [{"value": v, "count": c}
                                  for v, c in self.con.execute(self._to_duckdb(top_sql)).fetchall()]
        return _Job(rows, self._schema_of(sql))

    # ----------------------------------------------------------- helpers
    def _qualify(self, ref: str) -> str:
        parts = ref.split(".")
        if len(parts) == 2:
            parts = [self.project] + parts
        return ".".join(parts)

    def _to_duckdb(self, sql: str) -> str:
        tree = sqlglot.parse_one(sql, read="bigquery")   # raises on invalid BigQuery syntax
        # BigQuery's DAYOFWEEK is 1 (Sunday) .. 7; DuckDB's is 0 .. 6.
        for node in list(tree.find_all(exp.Extract)):
            if node.name.upper() == "DAYOFWEEK":
                node.replace(exp.Paren(this=exp.Add(this=node.copy(), expression=exp.Literal.number(1))))
        for table in tree.find_all(exp.Table):
            if table.args.get("db") and not table.args.get("catalog"):
                table.set("catalog", exp.to_identifier(self.project))
        return tree.sql(dialect="duckdb")

    def _schema_of(self, sql: str) -> List[SchemaField]:
        desc = self.con.execute("DESCRIBE " + self._to_duckdb(sql)).fetchall()
        return [_bq_type(r[1])._replace(name=r[0]) for r in desc]
