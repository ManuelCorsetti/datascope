# 🐍 Python API

> Call datascope from Python, and use the profile dict it returns.

[📚 Docs home](README.md) • [🚀 Getting started](getting-started.md) • [🖼️ Report tour](report-tour.md) • [🔎 Checks](checks.md) • [☁️ BigQuery](bigquery.md) • [⚙️ Settings](settings.md) • [💻 CLI](cli.md)

```python
from datascope import profile, DataProfiler, Settings                     # 🐼 pandas
from datascope import profile_bigquery, BigQueryProfiler, estimate_bigquery_cost  # ☁️ BigQuery
```

---

**On this page**

| 🐼 pandas | ☁️ BigQuery | 🧾 Results |
|---|---|---|
| [`profile()`](#-profile) | [`profile_bigquery()`](#-profile_bigquery) | [The profile dict](#-the-profile-dict) |
| [`DataProfiler`](#-dataprofiler) | [`BigQueryProfiler`](#-bigqueryprofiler) | [Recipes](#-recipes) |
| [`Settings`](#-settings) | [`estimate_bigquery_cost()`](#-estimate_bigquery_cost) | |

---

## 🎯 `profile()`

The one-liner: profile a DataFrame or a file, write the report, return the profile dict.

```python
profile(
    data,                                   # a pandas DataFrame, or a path to a csv/tsv/parquet/xlsx/json file
    output_html="data_profile_report.html", # where to write the report
    source_name=None,                       # name shown in the report (default: the path, or "dataset")
    open_browser=False,                     # open the report when done
    references=None,                        # referential-integrity checks, see below
    **settings,                             # any Settings field, e.g. max_correlation_cols=60
) -> dict
```

```python
from datascope import profile

result = profile("orders.csv", output_html="orders.html", missing_warning_pct=5)
```

**`references`** maps a child column to its parent, for [referential-integrity checks](checks.md#-referential-integrity):

```python
customers = pd.read_csv("customers.csv")

profile(orders, references={
    "parent_order_id": "order_id",                       # a column of the same table
    "customer_id": ("customers.id", customers["id"]),    # another table: (label, column)
    "product_id": products["id"],                        # another table, labelled with the Series name
})
```

---

## 🧰 `DataProfiler`

The class behind `profile()`. Use it to profile several datasets with the same settings, or to get the dict without writing a report.

```python
from datascope import DataProfiler

profiler = DataProfiler(max_correlation_cols=60)        # settings as keywords...
profiler = DataProfiler(settings=my_settings)          # ...or a Settings object

result = profiler.profile(data, source_name=None, references=None)   # -> dict, writes nothing
profiler.to_html(result, "report.html")                              # -> writes the report
```

---

## 🔩 `Settings`

An immutable, validated bundle of every [setting](settings.md#-all-settings).

```python
from datascope import Settings

strict = Settings(missing_warning_pct=5, missing_high_pct=20, sensitive_min_match_pct=0.5)
stricter = strict.updated(outlier_alert_pct=2)     # a copy with changes
strict.non_defaults()                              # {'sensitive_min_match_pct': 0.5, 'missing_warning_pct': 5.0, ...}
strict.to_dict()                                   # every setting
strict.flags_for()                                 # ['--sensitive-min-match-pct', '0.5', ...] for the CLI
```

Invalid values fail immediately:

```python
Settings(ri_parent_min_unique_pct=120)
# ValueError: Setting ri_parent_min_unique_pct must be <= 100, got 120.0.
```

---

## 🌐 `profile_bigquery()`

The BigQuery one-liner. Give a `table` or a `query`.

```python
profile_bigquery(
    table=None,                     # "project.dataset.table"
    *,
    query=None,                     # or a SQL query: every column it returns is profiled
    columns=None,                   # only these columns
    output_html="data_profile_report.html",   # None: don't write a report
    source_name=None,
    open_browser=False,
    references=None,                # {"customer_id": "proj.sales.customers.id", "manager_id": "employee_id"}
    sample_percent=None,            # e.g. 1: profile a TABLESAMPLE of the table instead
    sample_max_rows=1_000_000,
    **kwargs,                       # BigQueryProfiler arguments and any Settings field
) -> dict
```

```python
from datascope import profile_bigquery

result = profile_bigquery("my-project.sales.orders", output_html="orders.html",
                          project="my-billing-project", maximum_bytes_billed=10 * 1024**3,
                          correlations=False)
result["meta"]["sql"]                 # the SQL that ran
result["meta"]["usage_by_section"]    # bytes, slot time and shuffle per section
```

---

## 🏭 `BigQueryProfiler`

```python
BigQueryProfiler(
    client=None,                 # a google.cloud.bigquery.Client; created from your credentials if omitted
    project=None,                # the project that runs and pays for the queries
    location=None,               # e.g. "US", "EU"
    maximum_bytes_billed=None,   # fail any query that would bill more
    settings=None,               # a Settings object...
    progress=None,               # a callable that receives progress lines, e.g. print
    **settings_keywords,         # ...or settings as keywords
)
```

| Method | Returns | Runs queries? |
|---|---|---|
| `.profile(table=None, query=None, columns=None, source_name=None, references=None, sample_percent=None, sample_max_rows=1_000_000)` | the profile dict | ✅ |
| `.estimate(table=None, query=None, columns=None, price_per_tib_usd=6.25, references=None)` | a cost estimate, per section | ❌ dry runs only (free) |
| `.build_sql(table=None, query=None, columns=None, references=None)` | the SQL strings that would run | ❌ reads the schema only |
| `.to_html(result, path)` | the path written | ❌ |

```python
import sys
from datascope import BigQueryProfiler

profiler = BigQueryProfiler(project="my-billing-project", progress=lambda line: print(line, file=sys.stderr))
result = profiler.profile(table="my-project.sales.orders", sample_percent=1)
print(result["meta"]["sample"])        # sample size, and what a full run would use
```

---

## 💰 `estimate_bigquery_cost()`

```python
from datascope import estimate_bigquery_cost

est = estimate_bigquery_cost("my-project.sales.orders")   # same arguments as profile_bigquery
est["bytes_processed_human"]     # '1.21 GB'
est["estimated_cost_usd"]        # on-demand price, default $6.25/TiB (price_per_tib_usd=...)
for s in est["sections"]:        # profiling, correlations, each reference check, ...
    print(s["section"], s["bytes_processed_human"], s["note"])
```

| Key | Meaning |
|---|---|
| `bytes_processed`, `bytes_processed_human` | Total bytes the run would process |
| `estimated_cost_usd`, `price_per_tib_usd` | On-demand cost at that price |
| `queries` | How many queries would run |
| `sections` | Per-section `section`, `queries`, `bytes_processed`, `bytes_processed_human`, `estimated_cost_usd`, `note` |
| `pricing_note` | Reminder that capacity (slot) pricing bills slot time instead |
| `sql`, `skipped_columns` | The SQL, and any columns left out because of their type |

---

## 🧾 The profile dict

Every run returns the same structure, whichever engine produced it. The report is drawn entirely from it.

```text
result
├── meta                     about the run: source, size, engine, settings, checks, commands
├── overview                 type distribution, completeness, alerts
├── columns[]                one entry per column
├── correlations             numeric correlation matrix (or None)
├── missing_correlation      which columns are empty together (or None)
├── high_correlation_pairs[] pairs above the threshold
├── duplicate_columns[]      identical column pairs
├── pk_candidates[]          primary-key candidates
├── column_dependencies[]    A → B relationships
├── referential_integrity[]  reference check results
└── reference_suggestions[]  every suggested reference, and what happened to it
```

<details open>
<summary><b>🧾 <code>meta</code></b></summary>

| Key | Meaning |
|---|---|
| `source_name`, `generated_at` | What was profiled, and when (UTC, ISO 8601) |
| `n_rows`, `n_cols`, `memory_mb` | Size (`memory_mb` is the stored table size on BigQuery) |
| `duplicate_rows`, `duplicate_rows_pct` | Exact duplicate rows (`None` on BigQuery) |
| `engine` | `"pandas"` or `"bigquery"` |
| `datascope_version` | The version that produced the profile |
| `settings` | Every setting used |
| `checks` | The [run summary](settings.md#-the-run-summary): a list of `{id, name, status, detail, changes, flags, hint}` |
| `command`, `extend_command` | `{argv, text, complete}` to reproduce or extend the run (`extend_command` is `None` if nothing to extend) |
| *BigQuery only*: `sql` | Every query that ran |
| *BigQuery only*: `bytes_processed`, `bytes_processed_by_section`, `usage_by_section` | What the run used: per section `{queries, bytes_processed, slot_ms, shuffle_bytes}` (`None` where BigQuery didn't report it) |
| *BigQuery only*: `distinct_counts`, `exact_distinct_columns` | The [distinct-count mode](bigquery.md#-distinct-counts-and-slot-time), and which columns were counted exactly |
| *BigQuery only*: `skipped_columns` | Columns left out because of their type |
| *BigQuery only*: `sample` | With sampling: `table`, `percent`, `max_rows`, `sample_rows`, `table_rows`, `scale`, `full_bytes_processed`, `full_slot_ms`, and a `warning` if the sample came back whole or empty |

</details>

<details>
<summary><b>📋 <code>overview</code></b></summary>

| Key | Meaning |
|---|---|
| `type_distribution` | `{semantic_type: column count}` |
| `total_missing_cells`, `total_missing_pct` | Empty cells across the whole table |
| `sensitive_columns_count` | Columns flagged as personal or sensitive data |
| `alerts` | `[{severity, column, message}]`; `column` is `None` for table-level alerts. Severities: `high`, `warning`, `info`, `sensitive` |

</details>

<details>
<summary><b>🧱 <code>columns[]</code></b></summary>

| Key | Meaning |
|---|---|
| `name`, `dtype` | Column name and storage type |
| `semantic_type`, `semantic_type_confidence`, `semantic_notes` | [What the column means](checks.md#-semantic-types), how sure, and why |
| `count`, `missing`, `missing_pct`, `unique`, `unique_pct` | `count` is all rows; `unique_pct` is of non-empty values |
| `memory_bytes` | Size in memory (pandas) |
| `numeric_stats` | `mean, std, min, q1, median, q3, max, range, sum, zeros, zeros_pct, negatives, negatives_pct, skewness, kurtosis, outlier_count, outlier_pct, lower_fence, upper_fence, is_integer_like, infinite_count` (some are pandas only). For a column flagged as personal data, `min`, `q1`, `median`, `q3`, `max` and the fences are `None` |
| `string_stats` | `min_length, max_length, mean_length, empty_or_whitespace` |
| `datetime_stats` | `min_date, max_date, range_days, weekday_distribution, future_dates` (`min_date` / `max_date` are `None` for a personal-data column) |
| `boolean_stats` | `true_count, false_count, true_pct` |
| `histogram`, `length_histogram` | `{edges, counts}` (pandas; `histogram` is `None` for a personal-data column) |
| `top_values` | `[{value, count, pct}]`, masked for personal data |
| `sensitive` | `is_sensitive, category (PII/PHI/PCI), category_label, type, type_label, confidence, detected_by, reasons` |
| `quality_rules` | `[{type, severity, description, ...}]`, see [quality rules](checks.md#-quality-rules--dbt-tests) |
| `dbt_snippet` | A dbt `schema.yml` block, as text |

</details>

<details>
<summary><b>🔗 Relationships</b></summary>

| Key | Shape |
|---|---|
| `correlations` | `{columns, matrix, truncated}`; `matrix[i][j]` is r between `columns[i]` and `columns[j]` |
| `missing_correlation` | `{columns, matrix}` (pandas) |
| `high_correlation_pairs` | `[{col1, col2, correlation}]` |
| `duplicate_columns` | `[[col_a, col_b]]` (pandas) |
| `pk_candidates` | `[{columns: [...], type: "single" or "composite"}]` |
| `column_dependencies` | `[{determinant, dependent, purity, support_rows, violation_count, violation_examples, distinct_determinant_values}]` |
| `referential_integrity` | `[{column, references, source ("declared"/"suggested"), same_table, checked, orphans, orphan_pct, orphan_values, sample_orphans, compared_as}]` |
| `reference_suggestions` | `[{column, references, status, estimated_bytes}]`; `status` is `checked`, `below_match`, `listed` or `over_limit` |

</details>

---

## 🧪 Recipes

<details open>
<summary><b>🚦 A data-quality gate in CI</b></summary>

```python
import pandas as pd
from datascope import profile

customers = pd.read_csv("exports/customers.csv")
result = profile("exports/orders.csv", output_html="orders.html",
                 references={"customer_id": ("customers.id", customers["id"])})

problems = [a["message"] for a in result["overview"]["alerts"] if a["severity"] == "high"]
problems += [f"{r['column']}: {r['orphans']} orphan rows" for r in result["referential_integrity"] if r["orphans"]]
if result["meta"]["duplicate_rows"]:
    problems.append(f"{result['meta']['duplicate_rows']} duplicate rows")

assert not problems, "\n".join(problems)
```
</details>

<details>
<summary><b>🔐 List the columns holding personal data, and why</b></summary>

```python
for col in result["columns"]:
    s = col["sensitive"]
    if s["is_sensitive"]:
        print(f"{col['name']}: {s['category_label']} ({s['type_label']}), {' '.join(s['reasons'])}")
```
</details>

<details>
<summary><b>🔁 Profile many files with the same settings</b></summary>

```python
from pathlib import Path
from datascope import DataProfiler, Settings

profiler = DataProfiler(settings=Settings(missing_warning_pct=5, column_dependencies=False))
for path in Path("exports").glob("*.csv"):
    result = profiler.profile(str(path))
    profiler.to_html(result, f"reports/{path.stem}.html")
```
</details>

<details>
<summary><b>🧮 What wasn't fully checked?</b></summary>

```python
for c in result["meta"]["checks"]:
    if c["status"] in ("partial", "skipped", "listed"):
        print(f"{c['name']}: {c['detail']}  → {' '.join(c['flags'])}")
print(result["meta"]["extend_command"]["text"] if result["meta"]["extend_command"] else "Everything ran in full.")
```
</details>
