import datetime as dt
import json
from collections import namedtuple
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from datascope import BigQueryProfiler, DataProfiler, estimate_bigquery_cost, profile_bigquery
from datascope.bigquery import UnsupportedColumnWarning, _query_from_clause, _table_from_clause, build_profile_sql, format_bytes, quote_identifier
from datascope.cli import main
from datascope.html_report import _sanitize
from datascope.semantic import infer_semantic_type_from_summary

Field = namedtuple("Field", "name field_type mode")


# --------------------------------------------------------------- SQL text
class TestSqlGeneration:
    def test_single_scan_with_one_block_per_column(self):
        sql = build_profile_sql("`p.d.t`", [("id", "INT64", "NULLABLE"), ("name", "STRING", "NULLABLE")])
        assert sql.startswith("SELECT\n  COUNT(*) AS n_rows,")
        assert sql.endswith("FROM `p.d.t` AS _datascope_src")
        assert sql.count("FROM ") == 1
        assert "COUNTIF(`id` IS NULL) AS c0__missing" in sql
        assert "COUNT(DISTINCT `id`) AS c0__distinct" in sql
        assert "APPROX_QUANTILES(CAST(`id` AS FLOAT64), 4) AS c0__quartiles" in sql
        assert "AVG(CHAR_LENGTH(`name`)) AS c1__mean_length" in sql
        # no dangling comma before FROM
        assert ",\nFROM" not in sql

    def test_numeric_stats_only_for_numeric_columns(self):
        sql = build_profile_sql("`p.d.t`", [("name", "STRING", "NULLABLE"), ("flag", "BOOL", "NULLABLE")])
        assert "AVG(CAST(" not in sql and "APPROX_QUANTILES" not in sql
        assert "COUNTIF(`flag`) AS c1__true" in sql

    def test_float_columns_guard_against_nan_and_inf(self):
        sql = build_profile_sql("`p.d.t`", [("x", "FLOAT64", "NULLABLE")])
        assert "COUNTIF(IS_INF(`x`)) AS c0__infinite" in sql
        assert "AVG(IF(IS_NAN(`x`) OR IS_INF(`x`), NULL, `x`)) AS c0__mean" in sql

    def test_approx_distinct_switch(self):
        sql = build_profile_sql("`p.d.t`", [("id", "INT64", "NULLABLE")], exact_distinct=False)
        assert "APPROX_COUNT_DISTINCT(`id`) AS c0__distinct" in sql
        assert "COUNT(DISTINCT" not in sql

    def test_complex_types_are_compared_as_json_and_skip_top_values(self):
        sql = build_profile_sql("`p.d.t`", [("tags", "STRING", "REPEATED"), ("payload", "JSON", "NULLABLE")])
        assert "COUNTIF(IFNULL(ARRAY_LENGTH(`tags`), 0) = 0) AS c0__missing" in sql
        assert "COUNT(DISTINCT TO_JSON_STRING(`tags`))" in sql
        assert "COUNT(DISTINCT TO_JSON_STRING(`payload`))" in sql
        assert "APPROX_TOP_COUNT" not in sql

    def test_unknown_type_raises_instead_of_guessing(self):
        with pytest.raises(ValueError, match=r"'VECTOR'.*'emb'"):
            build_profile_sql("`p.d.t`", [("id", "INT64", "NULLABLE"), ("emb", "VECTOR", "NULLABLE")])
        with pytest.raises(ValueError, match="Unsupported BigQuery type"):
            build_profile_sql("`p.d.t`", [("emb", "VECTOR", "REPEATED")])

    def test_every_documented_type_is_accepted(self):
        types = ["INT64", "INTEGER", "FLOAT64", "FLOAT", "NUMERIC", "BIGNUMERIC", "STRING", "BYTES", "BOOL",
                 "BOOLEAN", "DATE", "DATETIME", "TIMESTAMP", "TIME", "STRUCT", "RECORD", "JSON", "GEOGRAPHY",
                 "RANGE", "INTERVAL", "string"]
        build_profile_sql("`p.d.t`", [(f"c{i}", t, "NULLABLE") for i, t in enumerate(types)])

    def test_top_values_can_be_disabled(self):
        assert "APPROX_TOP_COUNT" not in build_profile_sql("`p.d.t`", [("a", "STRING", "NULLABLE")], top_n_values=0)

    def test_identifier_quoting(self):
        assert quote_identifier("order id") == "`order id`"
        assert quote_identifier("we`ird") == "`we\\`ird`"

    def test_table_reference_validation(self):
        assert _table_from_clause("proj.ds.tbl") == "`proj.ds.tbl`"
        assert _table_from_clause("`my-proj.ds.tbl`") == "`my-proj.ds.tbl`"
        assert _table_from_clause("proj:ds.tbl") == "`proj.ds.tbl`"
        assert _table_from_clause("ds.tbl") == "`ds.tbl`"
        for bad in ("tbl", "p.d.t; DROP TABLE x", "p.d.t` JOIN `x", ""):
            with pytest.raises(ValueError):
                _table_from_clause(bad)

    def test_query_is_wrapped_safely(self):
        assert _query_from_clause("SELECT 1;") == "(\nSELECT 1\n)"
        assert _query_from_clause("SELECT 1 ;\n -- done\n") == "(\nSELECT 1\n)"
        # a trailing line comment must not swallow the closing paren
        assert _query_from_clause("SELECT 1 -- note").endswith("-- note\n)")
        # a semicolon inside the query is left alone
        assert "';'" in _query_from_clause("SELECT ';' AS s")
        with pytest.raises(ValueError):
            _query_from_clause(" ; ")


# ------------------------------------------------- canned-response client
class CannedJob:
    def __init__(self, rows, schema=None):
        self._rows, self.schema, self.total_bytes_processed = rows, schema, 2048

    def result(self):
        return self._rows


class CannedClient:
    """Returns pre-baked rows; records what it was asked."""

    def __init__(self, schema, row):
        self.schema, self.row = schema, row
        self.queries, self.tables, self.dry_runs = [], [], []

    def get_table(self, ref):
        self.tables.append(ref)
        return namedtuple("Table", "schema num_bytes")(self.schema, 3 * 1024 * 1024)

    def query(self, sql, job_config=None, **kwargs):
        if getattr(job_config, "dry_run", False):
            self.dry_runs.append(sql)
            job = CannedJob([], schema=self.schema)
            job.total_bytes_processed = 512 * 1024 ** 3  # 0.5 TiB per query
            return job
        self.queries.append(sql)
        if "LIMIT 0" in sql:
            return CannedJob([], schema=self.schema)
        return CannedJob([{k: v for k, v in self.row.items()
                           if k == "n_rows" or f" AS {k}" in sql}])


@pytest.fixture
def canned():
    schema = [Field("order_id", "INT64", "REQUIRED"), Field("customer_email", "STRING", "NULLABLE"),
              Field("amount", "NUMERIC", "NULLABLE")]
    row = {
        "n_rows": 1000,
        "c0__missing": 0, "c0__distinct": 1000, "c0__min": 1.0, "c0__max": 1000.0, "c0__mean": 500.5,
        "c0__std": 288.8, "c0__sum": 500500.0, "c0__quartiles": [1.0, 250.0, 500.0, 750.0, 1000.0],
        "c0__zeros": 0, "c0__negatives": 0, "c0__top": [{"value": "1", "count": 1}],
        "c1__missing": 100, "c1__distinct": 850, "c1__min_length": 9, "c1__max_length": 30,
        "c1__mean_length": 18.0, "c1__blank": 0,
        "c1__top": [{"value": None, "count": 100}, {"value": "jo@example.com", "count": 7}],
        "c2__missing": 500, "c2__distinct": 400, "c2__min": -3.5, "c2__max": 99.0, "c2__mean": 20.0,
        "c2__std": 5.0, "c2__sum": 10000.0, "c2__quartiles": [-3.5, 10.0, 19.0, 30.0, 99.0],
        "c2__zeros": 5, "c2__negatives": 2, "c2__top": [],
    }
    return CannedClient(schema, row)


class TestProfileShape:
    def test_table_profile_maps_aggregates_into_profile_dict(self, canned):
        result = BigQueryProfiler(client=canned).profile(table="proj.sales.orders")
        assert canned.tables == ["proj.sales.orders"]
        assert len(canned.queries) == 1
        meta = result["meta"]
        assert (meta["n_rows"], meta["n_cols"], meta["engine"]) == (1000, 3, "bigquery")
        assert meta["source_name"] == "proj.sales.orders"
        assert meta["memory_mb"] == 3.0
        assert meta["sql"] == canned.queries
        assert meta["bytes_processed"] == 2048
        assert meta["duplicate_rows"] is None

        order_id, email, amount = result["columns"]
        assert order_id["semantic_type"] == "identifier"
        assert order_id["unique_pct"] == 100.0
        assert order_id["numeric_stats"]["median"] == 500.0
        assert order_id["numeric_stats"]["is_integer_like"] is True
        assert result["pk_candidates"] == [{"columns": ["order_id"], "type": "single"}]
        assert order_id["top_values"] == []  # all-unique column: no meaningful "top" values

        assert email["missing"] == 100 and email["missing_pct"] == 10.0
        assert email["unique_pct"] == round(100 * 850 / 900, 3)
        assert email["string_stats"] == {"min_length": 9, "max_length": 30, "mean_length": 18.0,
                                         "empty_or_whitespace": 0}
        # NULL is not a "top value"; and the column name flags it as PII so it is masked
        assert [tv["count"] for tv in email["top_values"]] == [7]
        assert email["sensitive"]["type"] == "email"
        assert email["top_values"][0]["value"] == "j***@***.com"

        ns = amount["numeric_stats"]
        assert (ns["min"], ns["q1"], ns["median"], ns["q3"], ns["max"]) == (-3.5, 10.0, 19.0, 30.0, 99.0)
        assert ns["range"] == 102.5
        assert ns["negatives"] == 2 and ns["negatives_pct"] == 0.4
        assert "outlier_pct" not in ns  # not measured, so not reported
        assert any(r["type"] == "non_negative_check" for r in amount["quality_rules"])
        assert any(a["column"] == "amount" for a in result["overview"]["alerts"])
        assert result["overview"]["total_missing_cells"] == 600
        assert 0 < result["overview"]["quality_score"] <= 100
        json.dumps(_sanitize(result))  # must not raise

    def test_column_subset_is_case_insensitive_and_validated(self, canned):
        profiler = BigQueryProfiler(client=canned)
        result = profiler.profile(table="proj.sales.orders", columns=["AMOUNT"])
        assert [c["name"] for c in result["columns"]] == ["amount"]
        assert "order_id" not in canned.queries[-1]
        with pytest.raises(ValueError, match="nope"):
            profiler.profile(table="proj.sales.orders", columns=["nope"])

    def test_wide_tables_are_split_into_batches(self, canned):
        result = BigQueryProfiler(client=canned, max_columns_per_query=2).profile(table="proj.sales.orders")
        assert len(result["meta"]["sql"]) == 2
        assert [c["name"] for c in result["columns"]] == ["order_id", "customer_email", "amount"]
        assert result["columns"][2]["numeric_stats"]["max"] == 99.0

    def test_query_source_reads_schema_then_profiles_subquery(self, canned):
        result = BigQueryProfiler(client=canned).profile(query="SELECT * FROM `proj.sales.orders` WHERE amount > 0;")
        assert canned.tables == []
        assert "LIMIT 0" in canned.queries[0]
        assert "FROM (\nSELECT * FROM `proj.sales.orders` WHERE amount > 0\n) AS _datascope_src" in canned.queries[-1]
        assert result["meta"]["source_name"] == "query"
        assert result["meta"]["memory_mb"] is None

    def test_unknown_type_is_skipped_with_a_warning(self, canned, tmp_path):
        canned.schema.insert(1, Field("emb", "VECTOR", "NULLABLE"))
        # shift the canned aliases: the skipped column takes no alias
        profiler = BigQueryProfiler(client=canned)
        with pytest.warns(UnsupportedColumnWarning, match="'emb' was skipped: unsupported BigQuery type VECTOR"):
            result = profiler.profile(table="proj.sales.orders")
        assert "emb" not in canned.queries[-1]
        assert [c["name"] for c in result["columns"]] == ["order_id", "customer_email", "amount"]
        assert result["columns"][2]["numeric_stats"]["max"] == 99.0
        assert result["meta"]["n_cols"] == 3
        assert result["meta"]["skipped_columns"] == [
            {"name": "emb", "dtype": "VECTOR", "reason": "unsupported BigQuery type VECTOR"}]
        messages = [a["message"] for a in result["overview"]["alerts"]]
        assert "Column 'emb' was skipped: unsupported BigQuery type VECTOR." in messages
        out = tmp_path / "r.html"
        profiler.to_html(result, str(out))
        assert "was skipped: unsupported BigQuery type VECTOR" in out.read_text(encoding="utf-8")

    def test_no_warning_or_skips_when_all_types_supported(self, canned, recwarn):
        result = BigQueryProfiler(client=canned).profile(table="proj.sales.orders")
        assert result["meta"]["skipped_columns"] == []
        assert not [w for w in recwarn if issubclass(w.category, UnsupportedColumnWarning)]

    def test_cli_prints_skip_warning_to_stderr(self, canned, tmp_path, monkeypatch, capsys):
        canned.schema.append(Field("emb", "VECTOR", "NULLABLE"))
        monkeypatch.setattr(BigQueryProfiler, "client", property(lambda self: canned))
        out = tmp_path / "cli.html"
        monkeypatch.setattr("sys.argv", ["datascope", "--bq-table", "proj.sales.orders", "-o", str(out)])
        main()
        captured = capsys.readouterr()
        assert "Warning: Column 'emb' was skipped: unsupported BigQuery type VECTOR." in captured.err
        assert "Report written" in captured.out and out.exists()

    def test_exactly_one_source_required(self, canned):
        profiler = BigQueryProfiler(client=canned)
        with pytest.raises(ValueError):
            profiler.profile()
        with pytest.raises(ValueError):
            profiler.profile(table="a.b.c", query="SELECT 1")

    def test_build_sql_does_not_run_the_profile(self, canned):
        sqls = BigQueryProfiler(client=canned).build_sql(table="proj.sales.orders")
        assert len(sqls) == 1 and canned.queries == []

    def test_approx_distinct_never_exceeds_row_count_and_skips_pk(self, canned):
        canned.row["c0__distinct"] = 1012  # HLL overshoot
        result = BigQueryProfiler(client=canned, exact_distinct=False).profile(table="proj.sales.orders")
        assert result["columns"][0]["unique"] == 1000
        assert result["pk_candidates"] == []


@pytest.fixture
def dry_run_config(monkeypatch):
    """Stand in for bigquery.QueryJobConfig so dry runs work without the Google library."""
    monkeypatch.setattr(BigQueryProfiler, "_job_config",
                        lambda self, dry_run=False: SimpleNamespace(dry_run=dry_run))


class TestEstimate:
    def test_estimate_dry_runs_every_batch_and_runs_nothing(self, canned, dry_run_config):
        est = BigQueryProfiler(client=canned, max_columns_per_query=2).estimate(table="proj.sales.orders")
        assert canned.queries == []
        assert canned.dry_runs == est["sql"] and est["queries"] == 2
        assert est["bytes_processed"] == 1024 ** 4
        assert est["bytes_processed_human"] == "1.00 TB"
        assert est["estimated_cost_usd"] == 6.25
        assert estimate_bigquery_cost("proj.sales.orders", client=canned, price_per_tib_usd=5)["estimated_cost_usd"] == 2.5

    def test_estimate_refuses_to_run_for_real_when_dry_run_unavailable(self, canned, monkeypatch):
        monkeypatch.setattr(BigQueryProfiler, "_job_config", lambda self, dry_run=False: None)
        with pytest.raises(RuntimeError, match="dry run"):
            BigQueryProfiler(client=canned).estimate(table="proj.sales.orders")
        assert canned.queries == []

    def test_cli_estimate(self, canned, dry_run_config, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(BigQueryProfiler, "client", property(lambda self: canned))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["datascope", "--bq-table", "proj.sales.orders", "--estimate"])
        main()
        out = capsys.readouterr().out
        assert "will process 512.00 GB" in out and "$3.1250" in out and "Nothing was run" in out
        assert canned.queries == [] and not list(tmp_path.iterdir())

    def test_format_bytes(self):
        assert [format_bytes(n) for n in (0, 1023, 1536, 5 * 1024 ** 2, 3 * 1024 ** 5)] == [
            "0 B", "1023 B", "1.50 KB", "5.00 MB", "3072.00 TB"]


class TestSemanticFromSummary:
    def test_matches_series_based_rules(self):
        assert infer_semantic_type_from_summary("x", "string", 0, 0)[0] == "empty"
        assert infer_semantic_type_from_summary("x", "string", 10, 1)[0] == "constant"
        assert infer_semantic_type_from_summary("flag", "string", 10, 2, top_values=["Y", "N"])[0] == "boolean"
        assert infer_semantic_type_from_summary("grp", "string", 10, 2, top_values=["a", "b"])[0] == "binary_categorical"
        assert infer_semantic_type_from_summary("user_id", "numeric", 1000, 1000)[0] == "identifier"
        assert infer_semantic_type_from_summary("price", "numeric", 1000, 990)[0] == "continuous_numeric"
        assert infer_semantic_type_from_summary("tier", "numeric", 1000, 4)[0] == "discrete_numeric_categorical"
        assert infer_semantic_type_from_summary("body", "string", 1000, 400, avg_length=300)[0] == "free_text"
        assert infer_semantic_type_from_summary("city", "string", 1000, 30, avg_length=8)[0] == "categorical"
        assert infer_semantic_type_from_summary("created", "datetime", 1000, 900)[0] == "datetime"
        assert infer_semantic_type_from_summary("payload", "other", 1000, 900)[0] == "unknown"


# -------------------------------------- generated SQL, actually executed
def _customers(n=500):
    rng = np.random.default_rng(7)
    df = pd.DataFrame({
        "customer_id": np.arange(1, n + 1),
        "email": [f"user{i}@example.com" for i in range(n)],
        "country": rng.choice(["GB", "US", "DE", "FR"], n, p=[.5, .3, .15, .05]),
        "amount": np.round(rng.normal(100, 30, n), 2),
        "items": rng.integers(0, 6, n),
        "is_active": rng.random(n) > 0.3,
        "signup_date": [dt.date(2023, 1, 1) + dt.timedelta(days=int(d)) for d in rng.integers(0, 700, n)],
        "updated_at": pd.to_datetime(
            [dt.datetime(2024, 1, 1) + dt.timedelta(hours=int(h)) for h in rng.integers(0, 5000, n)]
        ).tz_localize("UTC"),
        "notes": [None if i % 4 == 0 else ("" if i % 50 == 1 else f"note {i % 37}") for i in range(n)],
        "const_col": "x",
        "tags": [[] if i % 10 == 0 else ["a", "b"][: 1 + i % 2] for i in range(n)],
    })
    df.loc[rng.choice(n, 40, replace=False), "amount"] = np.nan
    df.loc[3, "amount"] = -5.0
    return df


@pytest.fixture(scope="module")
def warehouse():
    pytest.importorskip("duckdb")
    pytest.importorskip("sqlglot")
    from duckdb_bigquery import DuckDBBigQueryClient

    client = DuckDBBigQueryClient(project="demo", dataset="shop")
    df = _customers()
    client.load("customers", df)
    client.con.execute("CREATE TABLE demo.shop.empty AS SELECT * FROM demo.shop.customers LIMIT 0")
    # DuckDB's UUID has no BigQuery counterpart here -> an unsupported type
    client.con.execute("CREATE TABLE demo.shop.sessions AS "
                       "SELECT i AS id, uuid() AS session, i % 3 AS grp FROM range(200) r(i)")
    return client, df


class TestExecutedAgainstRealData:
    def test_table_profile_agrees_with_pandas_engine(self, warehouse, tmp_path):
        client, df = warehouse
        out = tmp_path / "bq.html"
        result = profile_bigquery("demo.shop.customers", client=client, output_html=str(out))
        html = out.read_text(encoding="utf-8")
        assert html.startswith("<!DOCTYPE html>") and "demo.shop.customers" in html

        local = df.drop(columns=["tags"]).assign(signup_date=pd.to_datetime(df["signup_date"]))
        expected = {c["name"]: c for c in DataProfiler().profile(local)["columns"]}
        assert result["meta"]["n_rows"] == len(df)

        for col in result["columns"]:
            if col["name"] == "tags":
                continue
            exp = expected[col["name"]]
            assert col["missing"] == exp["missing"], col["name"]
            assert col["unique"] == exp["unique"], col["name"]
            assert col["semantic_type"] == exp["semantic_type"], col["name"]
            for key in ("boolean_stats", "string_stats"):
                assert col[key] == exp[key], (col["name"], key)
            if exp["numeric_stats"]:
                got, want = col["numeric_stats"], exp["numeric_stats"]
                for stat in ("mean", "std", "min", "max", "sum", "range"):
                    assert got[stat] == pytest.approx(want[stat], rel=1e-6), (col["name"], stat)
                for stat in ("zeros", "negatives", "is_integer_like"):
                    assert got[stat] == want[stat], (col["name"], stat)
                # quartiles are approximate by design: allow 5% of the range
                tol = 0.05 * want["range"]
                for stat in ("q1", "median", "q3"):
                    assert abs(got[stat] - want[stat]) <= tol, (col["name"], stat)
            if exp["datetime_stats"]:
                got, want = col["datetime_stats"], exp["datetime_stats"]
                assert got["min_date"][:10] == want["min_date"][:10]
                assert got["max_date"][:10] == want["max_date"][:10]
                assert got["range_days"] == want["range_days"]
                assert got["weekday_distribution"] == want["weekday_distribution"]

        by_name = {c["name"]: c for c in result["columns"]}
        country_top = {tv["value"]: tv["count"] for tv in by_name["country"]["top_values"]}
        assert country_top == df["country"].value_counts().to_dict()
        assert by_name["tags"]["dtype"] == "ARRAY<STRING>"
        assert by_name["tags"]["missing"] == 50  # empty arrays
        assert by_name["tags"]["unique"] == 3
        assert {"columns": ["customer_id"], "type": "single"} in result["pk_candidates"]
        assert by_name["email"]["sensitive"]["is_sensitive"]
        assert by_name["email"]["top_values"] == []

    def test_query_profile_covers_every_result_column(self, warehouse):
        client, df = warehouse
        query = """
            SELECT country, SUM(amount) AS total_amount, COUNT(*) AS n
            FROM `demo.shop.customers`
            WHERE is_active
            GROUP BY country;  -- per-country rollup
        """
        result = profile_bigquery(query=query, client=client, output_html=None, source_name="rollup")
        active = df[df["is_active"]]
        assert result["meta"]["n_rows"] == active["country"].nunique()
        assert [(c["name"], c["dtype"]) for c in result["columns"]] == [
            ("country", "STRING"), ("total_amount", "FLOAT64"), ("n", "INT64")]
        n = {c["name"]: c for c in result["columns"]}["n"]["numeric_stats"]
        assert n["sum"] == len(active)
        assert n["max"] == active["country"].value_counts().max()
        total = {c["name"]: c for c in result["columns"]}["total_amount"]["numeric_stats"]
        assert total["sum"] == pytest.approx(active["amount"].sum())

    def test_column_subset_and_batching(self, warehouse):
        client, df = warehouse
        result = profile_bigquery("shop.customers", columns=["amount", "country"], client=client,
                                  output_html=None, max_columns_per_query=1)
        assert [c["name"] for c in result["columns"]] == ["amount", "country"]
        assert len(result["meta"]["sql"]) == 2
        assert result["columns"][0]["missing"] == int(df["amount"].isna().sum())
        assert result["columns"][1]["unique"] == 4

    def test_approximate_distinct_is_close(self, warehouse):
        client, df = warehouse
        result = profile_bigquery("demo.shop.customers", columns=["customer_id"], client=client,
                                  output_html=None, exact_distinct=False)
        assert result["columns"][0]["unique"] == pytest.approx(len(df), rel=0.05)

    def test_empty_table(self, warehouse, tmp_path):
        client, _ = warehouse
        result = profile_bigquery("demo.shop.empty", client=client, output_html=str(tmp_path / "empty.html"))
        assert result["meta"]["n_rows"] == 0
        assert {c["semantic_type"] for c in result["columns"]} == {"empty"}
        assert result["overview"]["quality_score"] is None

    def test_unsupported_column_is_skipped_and_the_rest_profiled(self, warehouse):
        client, _ = warehouse
        with pytest.warns(UnsupportedColumnWarning, match="'session' was skipped"):
            result = profile_bigquery("demo.shop.sessions", client=client, output_html=None)
        assert [c["name"] for c in result["columns"]] == ["id", "grp"]
        assert result["columns"][0]["unique"] == 200
        assert result["columns"][1]["unique"] == 3
        assert [s["name"] for s in result["meta"]["skipped_columns"]] == ["session"]

    def test_cli_runs_and_prints_sql(self, warehouse, tmp_path, monkeypatch, capsys):
        client, _ = warehouse
        monkeypatch.setattr(BigQueryProfiler, "client", property(lambda self: client))
        out = tmp_path / "cli.html"
        monkeypatch.setattr("sys.argv", ["datascope", "--bq-table", "demo.shop.customers",
                                         "--columns", "country, amount", "-o", str(out)])
        main()
        assert out.exists()

        sql_file = tmp_path / "q.sql"
        sql_file.write_text("SELECT country FROM `demo.shop.customers`;")
        monkeypatch.setattr("sys.argv", ["datascope", "--bq-query-file", str(sql_file), "--print-sql"])
        capsys.readouterr()
        main()
        printed = capsys.readouterr().out
        assert "COUNT(DISTINCT `country`) AS c0__distinct" in printed
        assert "Report written" not in printed


def test_cli_requires_exactly_one_source(monkeypatch):
    monkeypatch.setattr("sys.argv", ["datascope", "data.csv", "--bq-table", "p.d.t"])
    with pytest.raises(SystemExit):
        main()
    monkeypatch.setattr("sys.argv", ["datascope"])
    with pytest.raises(SystemExit):
        main()
