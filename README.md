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

### Referential integrity

Check that every value in a column exists in a key column — in the same
table, or in another one. NULLs are not counted as orphans, as with a
SQL foreign key:

```python
customers = pd.read_csv("customers.csv")
profile(orders, references={
    "customer_id": ("customers.id", customers["id"]),  # another table: (label, key column)
    "parent_order_id": "order_id",                     # same table: a column name
})
```

```
python -m datascope orders.csv --reference customer_id=customers.csv:id --reference parent_order_id=order_id
```

The report gets a Referential integrity panel (orphan row count and
percentage, distinct missing values, the most common examples), and any
orphans raise a column-level alert. datascope also **suggests**
same-table references on its own when a column's name points at an
identifier column (`referred_by_customer_id` -> `customer_id`, or any
`*_id` -> a column called `id`) and at least 90% of its values match.
Value overlap alone isn't enough, because surrogate keys 1..N overlap by
chance.

When suggestions are made: after the column statistics are computed,
because that is when datascope knows which columns really look like keys
(identifier, no NULLs, at least 99% unique). With pandas the suggested
checks then run in memory. On BigQuery each one would be an extra query,
so by default they are only **listed**, with the cost of checking each
(from a free dry run), and the run summary gives the flag that checks
them. `--suggested-references check|list|off` overrides either default,
and every threshold above is a setting (see below).

Try it first on synthetic data (customers table with realistic messiness
baked in — PII, a couple of quality bugs, correlated missingness,
duplicate rows, dangling references):

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
datascope --bq-table my-project.sales.orders --reference customer_id=my-project.sales.customers.id
```

Referential-integrity checks take a same-table column name or a
`project.dataset.table.column` reference:
`profile_bigquery("my-project.sales.orders", references={"customer_id": "my-project.sales.customers.id"})`.

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
  columns). That query already reads every numeric column of a table of
  up to `max_columns_per_query` columns, so they usually cost nothing;
  on wider tables it also reads the numeric columns of later batches.
  `--estimate` shows the exact extra bytes, and `--no-correlations`
  (`correlations=False`) turns them off. They agree with the pandas
  engine; the missing-value correlation matrix is not computed.
- Each referential-integrity check is one extra query: an anti-join that
  reads only the two key columns and returns at most `ri_sample_orphans`
  rows. Nothing is joined beyond that pair. Declared checks always run.
  Suggested ones are listed with their cost by default (see Referential
  integrity above); with `--suggested-references check` they run after
  profiling, but only where the profile shows the parent column is a key.
  `--estimate` then counts every name-matched pair, as an upper bound.
- `--estimate` (`estimate_bigquery_cost`) breaks the cost down by section:
  profiling, correlations, and each reference check:

  ```
  This profile will process 1.21 GB when run (about $0.0074 at $6.25/TiB on-demand). Nothing was run.

    profiling                                               1.16 GB  $0.0071
    correlations                                               0 B   $0.0000  Extra columns the first profiling query reads ...
    reference customer_id -> my-project.sales.customers.id  48.2 MB  $0.0003
    suggested references                                       0 B   $0.0000  Listed after profiling with their cost, not run ...
  ```
- Not computed yet (each needs extra passes over the data): histograms,
  outlier counts, skew/kurtosis, duplicate rows, composite
  keys, functional dependencies, and detecting dates stored as text.
- Personal & sensitive data is detected by **column name only**: checking
  values would mean pulling them out of the warehouse.
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

## Settings and repeatable runs

Every threshold and limit that decides which checks run, or what gets
flagged, is a setting with a default. From the command line each one is
a flag (`datascope --help` lists them all, grouped by check). From
Python, pass a `Settings` object or the same names as keywords:

```python
from datascope import DataProfiler, Settings, profile

profile(df, ri_parent_min_unique_pct=90, max_correlation_cols=60)
DataProfiler(settings=Settings(correlations=False, suggested_references="list"))
```

```
datascope data.csv --ri-parent-min-unique-pct 90 --max-correlation-cols 60
```

**Every run reports what it did and didn't check.** After a run, the
command line prints, and the report's **Run summary** panel shows:

- each check family, with its status: ran, partial (a limit kicked in),
  skipped (turned off), listed (found but not run), not set up (needs
  input, e.g. `--reference`), or not available on this engine;
- the flag that would extend each partial, skipped or listed check;
- a command that **extends** the run with all of those flags at once,
  and one that **reproduces** it exactly;
- every setting used, with changed values highlighted, plus the
  datascope version.

```
Checks:
  ✓ Column statistics                  ran           All 19 columns: nulls, distinct counts, ...
  ◐ Personal & sensitive data detection  partial    Column names checked; values checked on a sample of 500 rows per column ...  → --sample-size 4012
  ◐ Correlations                       partial       First 3 of 5 numeric columns.  → --max-correlation-cols 5
  ✓ Primary-key search                 ran           No key can be unique: the table has 12 exact duplicate rows.
  · Referential integrity (declared)   not set up    None declared.  (set up with --reference CHILD=PARENT ...)
  ...

To extend this run with every → change above:
  datascope customers.csv --sample-size 4012 --max-correlation-cols 5

To reproduce this run:
  datascope customers.csv --sample-size 500 --max-correlation-cols 3
```

All of it is also in the returned dict: `result["meta"]["settings"]`,
`["checks"]`, `["command"]` and `["extend_command"]`. When the data came
from Python rather than a file, the command uses an `INPUT` placeholder.

### All settings

<!-- settings-table:start (generated from datascope/settings.py; tests check it is current) -->
**Column statistics and sampling**

| Flag / keyword | Default | Engines | What it does |
|---|---|---|---|
| `--top-n-values` / `top_n_values` | `10` | both | Most frequent values kept per column. |
| `--histogram-bins` / `histogram_bins` | `30` | pandas | Bars in each numeric histogram. |
| `--sample-size` / `sample_size_for_content_checks` | `1000` | pandas | Rows sampled per column when checking values for personal or sensitive data (emails, phone numbers, ID and card numbers...). Larger = slower, fewer misses. |
| `--random-state` / `random_state` | `42` | pandas | Seed for that sample, so reruns flag the same columns. |

**Alert thresholds**

| Flag / keyword | Default | Engines | What it does |
|---|---|---|---|
| `--missing-warning-pct` / `missing_warning_pct` | `20` | both | A column with more than this % missing raises a warning. |
| `--missing-high-pct` / `missing_high_pct` | `50` | both | A column with more than this % missing raises a high-severity alert. |
| `--outlier-alert-pct` / `outlier_alert_pct` | `5` | pandas | Alert when more than this % of a numeric column is outside 1.5x IQR. |
| `--sensitive-alert-min-confidence` / `sensitive_alert_min_confidence` | `0.7` | both | Raise an alert for a column that looks like personal or sensitive data only at or above this detection confidence (0-1). Columns below it are still flagged and masked, just without an alert. |

**Correlations**

| Flag / keyword | Default | Engines | What it does |
|---|---|---|---|
| `--correlations` / `correlations` | `on` | both | Pearson correlation matrix of numeric columns (and, on pandas, the missing-value correlation matrix). On BigQuery this adds CORR() terms to the first profiling query: free for tables of up to --max-columns-per-query columns, see --estimate for the exact cost. |
| `--max-correlation-cols` / `max_correlation_cols` | `30` | both | Correlate at most this many numeric columns (n*(n-1)/2 pairs). |
| `--high-correlation-threshold` / `high_correlation_threshold` | `0.8` | both | Alert on column pairs with \|r\| at or above this. |

**Keys and duplicates**

| Flag / keyword | Default | Engines | What it does |
|---|---|---|---|
| `--max-pk-candidate-pool` / `max_pk_candidate_pool` | `10` | pandas | Composite primary-key search: consider this many of the most distinct no-null columns. |
| `--max-pk-combo-size` / `max_pk_combo_size` | `3` | pandas | Composite primary-key search: try combinations of up to this many columns. |
| `--max-duplicate-column-check` / `max_duplicate_column_check` | `100` | pandas | Skip identical-column detection on tables wider than this (every pair is compared). |

**Functional dependencies (column A determines column B)**

| Flag / keyword | Default | Engines | What it does |
|---|---|---|---|
| `--functional-dependencies` / `functional_dependencies` | `on` | pandas | Search for column A -> column B dependencies (zip -> state). |
| `--fd-min-purity` / `fd_min_purity` | `0.98` | pandas | Report A -> B when at least this share (0-1) of evidence rows agree with the majority B for their A. |
| `--fd-min-support-rows` / `fd_min_support_rows` | `20` | pandas | Ignore a pair with fewer evidence rows than this. |
| `--max-fd-candidate-pool` / `max_fd_candidate_pool` | `25` | pandas | Test at most this many columns as either side (pairs grow with the square). |

**Referential integrity**

| Flag / keyword | Default | Engines | What it does |
|---|---|---|---|
| `--suggested-references` / `suggested_references` | `auto` | both | What to do with references datascope suggests itself (same table, from column names): 'check' runs them; 'list' only lists them, with their cost on BigQuery; 'off' skips them. 'auto' = check on pandas, list on BigQuery (where each is an extra query). |
| `--max-reference-suggestions` / `max_reference_suggestions` | `10` | both | Check or list at most this many suggested references. |
| `--ri-parent-min-unique-pct` / `ri_parent_min_unique_pct` | `99` | both | A suggested reference's target must be an identifier column, with no NULLs and at least this % unique. Below 100 so that duplicate rows don't hide a real key; lower it for messier data. |
| `--ri-suggest-min-match-pct` / `ri_suggest_min_match_pct` | `90` | both | Keep a suggestion only if at least this % of its rows match the target; fewer means it is probably not a reference at all. |
| `--ri-suggest-min-rows` / `ri_suggest_min_rows` | `10` | both | Don't suggest a reference for a column with fewer non-null rows. |
| `--ri-suggest-min-distinct` / `ri_suggest_min_distinct` | `3` | both | Don't suggest a reference for a column with fewer distinct values. |
| `--ri-sample-orphans` / `ri_sample_orphans` | `5` | both | Example orphan values kept per check (the most frequent). |
| `--ri-high-orphan-pct` / `ri_high_orphan_pct` | `5` | both | A declared check with more than this % orphan rows raises a high-severity alert; otherwise a warning. |

**BigQuery query shape**

| Flag / keyword | Default | Engines | What it does |
|---|---|---|---|
| `--exact-distinct` / `exact_distinct` | `on` | BigQuery | Exact COUNT(DISTINCT). --no-exact-distinct uses APPROX_COUNT_DISTINCT: cheaper on very large tables, but disables primary-key detection. |
| `--max-columns-per-query` / `max_columns_per_query` | `100` | BigQuery | Split wide tables into profiling queries of at most this many columns. |
<!-- settings-table:end -->

### Fixed heuristics

These rules are not settings. They decide how a column is classified and
when PII is suspected, and changing them means changing the code. The
report records the datascope version, which pins them.

- **Semantic type** (`semantic.py`): two distinct values → binary
  categorical, or boolean if they look like true/false. Numeric columns
  ≥ 95% unique with more than 20 values → identifier if the name reads as
  an id, otherwise continuous; numeric with ≤ 20 distinct values or < 5%
  unique → discrete categorical. Text with a `-` or `/` in most values that
  parses as dates for > 90% of a 200-value sample → dates stored as text.
  Text ≥ 98% unique → identifier (short values or an id-like name),
  otherwise free text; average length > 80 characters → free text;
  ≤ 50 distinct values or < 10% unique → categorical; otherwise
  high-cardinality text.
- **Personal & sensitive data detection** (`pii.py`, see above): a column is flagged when its name
  matches a keyword list, or when ≥ 60% of the sampled values match a
  pattern (email, phone, national ID, IP address, credit card with a Luhn
  check, IBAN). Its confidence is 0.55 for a name match plus 0.5 × the
  value match rate (+0.05 for a passed checksum), capped at 0.99;
  `--sensitive-alert-min-confidence` applies to that number.
- **Quality-rule suggestions** (`quality.py`): accepted values when the
  top values cover ≥ 99% of rows; an outlier review when > 1% of values
  are outside 1.5× IQR; a non-negative check when the name contains
  count, amount, qty, quantity, price, total, age, duration, length,
  size, score or balance.
- **Outliers** are values outside 1.5× the interquartile range.
- **Functional dependencies** (`relationships.py`): near-unique (≥ 99%
  unique) and constant columns are left out of the search; only
  determinant values that repeat count as evidence; up to 5 counter-example
  rows are kept per dependency.
- **Alerts**: at most 8 correlated pairs and 8 dependencies become alerts
  (the panels list them all).

## What it computes, per column

- **Summary stats** — count, missing %, unique %, memory; numeric: mean,
  std, quartiles, skew, kurtosis, zero/negative counts, 1.5×IQR outliers,
  infinite-value detection; string: length distribution; datetime: range,
  weekday distribution, future-dated values; boolean: true/false split.
- **Semantic type** — identifier, categorical, continuous/discrete
  numeric, free text, boolean, datetime (including dates stored as
  text), driven mainly by how *unique* the column is relative to row
  count, with dtype and column-name hints layered on top.
- **Personal & sensitive data detection**: flags columns that look like
  they hold *personal data* (PII, personally identifiable information:
  names, email addresses, phone numbers, postal addresses, national ID
  numbers, dates of birth), *health data* (PHI: medical records,
  diagnoses, medication) or *payment data* (PCI: card and bank account
  numbers). It checks the column name, and a sample of values against
  patterns (email, phone, national ID, IP address, credit card with a
  Luhn checksum, IBAN). The report's "Personal & sensitive data" panel
  lists each flagged column with the reason, e.g. "98% of 1,000 sampled
  values have the format of an email address", and the values of flagged
  columns are masked everywhere in the report. It is pattern matching to
  point you at columns worth a review, not a compliance decision.
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
- **Referential-integrity checks**, declared (same table or another
  table) or suggested from column names — see above
- An alerts panel surfacing all of the above at a glance

## Notes / assumptions

- The request that generated this said "PII or PSI" — there's no
  standard governance term "PSI", so this treats it as PHI (Protected
  Health Information), the usual pairing with PII. Categories are plain
  data in `pii.py` — easy to rename or extend if something else was meant.
- Value checks for personal data sample up to 1,000 rows per column by
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
  pii.py           personal & sensitive data detection (PII/PHI/PCI) + value masking
  quality.py       quality-rule + dbt-snippet recommendations
  relationships.py functional dependency detection (column A -> column B)
  referential.py   referential-integrity checks (declared and suggested references)
  settings.py      every tunable threshold: defaults, validation, CLI flags and help
  run_summary.py   what each run checked or left out, and the reproduce/extend commands
  html_report.py   renders the profile dict to the HTML dashboard
  bigquery.py      BigQuery engine: generates profiling SQL, maps results to the profile dict
  cli.py / __main__.py   `datascope` / `python -m datascope` (flags generated from settings.py)
tests/              pytest suite (duckdb_bigquery.py runs the generated BigQuery SQL on DuckDB)
example.py          synthetic messy dataset + runnable demo
```

## Development

```
pip install -e ".[dev]"
pytest
```
