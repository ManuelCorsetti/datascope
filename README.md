# datascope

Extensive Python data profiling &rarr; one self-contained interactive HTML
dashboard. No server, no JS framework, no build step — the report is a
single `.html` file you can email, host, or open locally forever. The
only external resource is a Google Fonts CSS link (progressive
enhancement — falls back to system fonts if it can't load).

## Install

```
pip install -e .
```

`.xlsx`/`.xls` input requires the optional `excel` extra:

```
pip install -e ".[excel]"
```

## Usage

```python
import pandas as pd
from datascope import profile

df = pd.read_csv("your_data.csv")
profile(df, output_html="report.html", source_name="your_data")
```

Straight from a file, no DataFrame needed:

```python
from datascope import profile
profile("your_data.csv", output_html="report.html")
```

Or from the command line:

```
python -m datascope your_data.csv -o report.html --open
```

Try it first on synthetic data (customers table with realistic messiness
baked in — PII, a couple of quality bugs, correlated missingness,
duplicate rows):

```
python example.py
```

## BigQuery

Profile a table or a query *inside* BigQuery: datascope writes the SQL,
BigQuery runs it, and only the aggregated results come back — no rows
are downloaded. The result is the same profile dict and HTML report as
the local engine.

```
pip install -e ".[bigquery]"
```

```python
from datascope import profile_bigquery

# a whole table
profile_bigquery("my-project.sales.orders", output_html="orders.html")

# a sub-selection of columns
profile_bigquery("my-project.sales.orders", columns=["order_id", "amount", "status"])

# a SQL query — every column the query returns is profiled
profile_bigquery(query="""
    SELECT o.*, c.country
    FROM `my-project.sales.orders` o JOIN `my-project.sales.customers` c USING (customer_id)
    WHERE o.created_at >= '2026-01-01'
""", output_html="recent_orders.html")
```

It returns the profile dict (`output_html=None` skips the report), and
the SQL that ran is in `result["meta"]["sql"]`. Authentication uses your
default Google credentials (`gcloud auth application-default login`);
pass `project=` / `location=`, or your own `client=`, to override.

From the command line:

```
datascope --bq-table my-project.sales.orders -o orders.html
datascope --bq-table my-project.sales.orders --columns order_id,amount -o orders.html
datascope --bq-query-file recent_orders.sql -o recent_orders.html
datascope --bq-table my-project.sales.orders --print-sql     # just show the SQL, run nothing
```

**Check the cost first.** A dry run tells you how much data the profile
will scan — the same figure the BigQuery console shows before you press
Run — without running or billing anything:

```python
from datascope import estimate_bigquery_cost

est = estimate_bigquery_cost("my-project.sales.orders")
est["bytes_processed_human"]   # e.g. '12.40 GB'
est["estimated_cost_usd"]      # bytes x on-demand price (default $6.25/TiB)
```

```
datascope --bq-table my-project.sales.orders --estimate
```

The byte count is an upper bound (clustered tables can scan less). The
dollar figure is only bytes x `price_per_tib_usd`: it ignores the
monthly free tier, regional price differences, and doesn't apply if you
pay for capacity (slots) rather than on-demand.

**What the BigQuery engine computes** — in one scan of the source:
total rows; per column nulls, distinct count and top values; numeric
min / max / mean / std / sum / quartiles (median), zeros, negatives;
string length stats and blank count; date range, future-dated values and
weekday split; boolean true/false split. Semantic types, quality rules,
dbt snippets, single-column primary-key candidates and alerts are
derived from those, as usual. Pearson correlations between numeric
columns come from `CORR()` in the same scan.

**Things to know**

- Quartiles/median use `APPROX_QUANTILES` and top values use
  `APPROX_TOP_COUNT`, so they are approximate on large tables. Distinct
  counts are exact by default; pass `exact_distinct=False`
  (`--approx-distinct`) to switch to `APPROX_COUNT_DISTINCT` on very
  large tables.
- Pearson correlations between numeric columns are computed with `CORR()`
  in the first profiling query (first `max_correlation_cols=30` numeric
  columns; `0` turns them off). They agree with the pandas engine; the
  missing-value correlation matrix is not computed.
- Not computed yet (each needs extra passes over the data): histograms,
  outlier counts, skew/kurtosis, duplicate rows, composite
  keys, functional dependencies, and detecting dates stored as text.
- PII/PHI detection is by **column name only** — content checks would
  mean pulling values out of the warehouse.
- Cost: a table is scanned once (wide tables are split into queries of
  `max_columns_per_query=100` columns; each column is still read once).
  A SQL query source is re-run for each of those batches. Use
  `maximum_bytes_billed=` (`--max-bytes-billed`) as a safety cap.
- A column whose type datascope doesn't recognise is **skipped, not
  guessed at**: the rest of the table is still profiled, and the skip is
  reported as a warning in the report's Alerts panel, on stderr from the
  command line, as a Python `UnsupportedColumnWarning`, and in
  `result["meta"]["skipped_columns"]`.
- `ARRAY` columns count empty arrays as missing; `ARRAY`/`STRUCT`/`JSON`/
  `GEOGRAPHY` columns only get null and distinct counts.

## What it computes, per column

- **Summary stats** — count, missing %, unique %, memory; numeric: mean,
  std, quartiles, skew, kurtosis, zero/negative counts, 1.5×IQR outliers,
  infinite-value detection; string: length distribution; datetime: range,
  weekday distribution, future-dated values; boolean: true/false split.
- **Semantic type** — identifier, categorical, continuous/discrete
  numeric, free text, boolean, datetime (including dates stored as
  text), driven mainly by how *unique* the column is relative to row
  count, with dtype and column-name hints layered on top.
- **PII / PHI / PCI detection** — combines column-name keyword matching
  with sampled content regex (email, phone, national ID, IP, credit card
  with a Luhn check, IBAN). Flagged values are masked everywhere in the
  report, including drill-down samples. Heuristic — review before making
  access-control decisions on it.
- **Data quality rule suggestions** — not-null, uniqueness, accepted
  values, range checks, outlier/negative/future-date flags — plus a
  ready-to-paste **dbt `schema.yml`** test block per column.

## Dataset-level

- A **data quality** section that keeps table-level checks (completeness,
  duplicate rows) apart from column-level checks (columns with missing
  values, constant columns), each with its own alerts — no blended score
- Numeric correlation matrix and a **missing-value correlation matrix**
  (which columns tend to be null together — useful for spotting a shared
  upstream cause)
- Exact duplicate-row detection
- Primary-key candidate detection (single column, and a bounded search
  over identifier-like columns for composite keys)
- Functional dependency detection (does column A determine column B, e.g.
  `zip -> state`? — a bounded, evidence-weighted search flags near- and
  exact dependencies, with counter-example rows for anything short of 100%)
- An alerts panel surfacing all of the above at a glance

## Notes / assumptions

- The request that generated this said "PII or PSI" — there's no
  standard governance term "PSI", so this treats it as PHI (Protected
  Health Information), the usual pairing with PII. Categories are plain
  data in `pii.py` — easy to rename or extend if something else was meant.
- Content-based PII/PHI checks sample up to 1,000 rows per column by
  default (`DataProfiler(sample_size_for_content_checks=...)` to change).
- Every suggestion (quality rules, dbt tests, accepted-value lists) is a
  heuristic starting point learned from one snapshot of the data — review
  before enforcing anything in production.
- Only aggregated stats/histograms are embedded in the HTML, never raw
  rows, so file size stays reasonable regardless of dataset size.

## Files

```
src/datascope/
  core.py          DataProfiler class, orchestration, correlations, PK search
  stats.py         numeric/string/datetime/boolean stat + histogram calculators
  semantic.py      semantic type inference
  pii.py           PII/PHI/PCI detection + value masking
  quality.py       quality-rule + dbt-snippet recommendations, quality score
  relationships.py functional dependency detection (column A -> column B)
  html_report.py   renders the profile dict to the HTML dashboard
  bigquery.py      BigQuery engine: generates profiling SQL, maps results to the profile dict
  cli.py / __main__.py   `python -m datascope`
tests/              pytest suite (duckdb_bigquery.py runs the generated BigQuery SQL on DuckDB)
example.py          synthetic messy dataset + runnable demo
```

## Development

```
pip install -e ".[dev]"
pytest
```
