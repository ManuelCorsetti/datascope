# 🚀 Getting started

> From zero to your first datascope report in about five minutes.

[📚 Docs home](README.md) • [🖼️ Report tour](report-tour.md) • [🔎 Checks](checks.md) • [☁️ BigQuery](bigquery.md) • [⚙️ Settings](settings.md) • [💻 CLI](cli.md) • [🐍 Python API](python-api.md)

---

**On this page**

- [📦 Install](#-install)
- [📂 Supported inputs](#-supported-inputs)
- [🎬 Your first report](#-your-first-report)
- [🧪 Try the demo dataset](#-try-the-demo-dataset)
- [👀 What to look at first](#-what-to-look-at-first)
- [🧭 Where next](#-where-next)

---

## 📦 Install

datascope needs **Python 3.11 or newer**. From a checkout of the repository:

```bash
pip install -e .
```

Optional extras add support for more sources:

| Extra | Install | Adds |
|---|---|---|
| ☁️ BigQuery | `pip install -e ".[bigquery]"` | Profiling BigQuery tables and queries ([guide](bigquery.md)) |
| 📊 Excel | `pip install -e ".[excel]"` | Reading `.xlsx` files |
| 🧪 Development | `pip install -e ".[dev]"` | The test suite, including a local stand-in for BigQuery |

> [!NOTE]
> Reading **Parquet** files needs `pyarrow`, which isn't part of any extra yet: `pip install pyarrow`.

Check it worked:

```bash
datascope --help
```

---

## 📂 Supported inputs

| Source | How | Notes |
|---|---|---|
| `.csv` | `datascope data.csv` | Read with `pandas.read_csv` |
| `.tsv` | `datascope data.tsv` | Tab-separated |
| `.json` | `datascope data.json` | Read with `pandas.read_json` |
| `.parquet`, `.pq` | `datascope data.parquet` | Needs `pyarrow`. Keeps column types, such as real dates |
| `.xlsx` | `datascope data.xlsx` | Needs the `excel` extra |
| pandas DataFrame | `profile(df, ...)` | From Python, see [below](#-your-first-report) |
| BigQuery table | `datascope --bq-table project.dataset.table` | Runs inside BigQuery, see the [BigQuery guide](bigquery.md) |
| BigQuery query | `datascope --bq-query "SELECT ..."` | Profiles every column the query returns |

> [!TIP]
> CSV files store dates as text, so date columns are reported as *dates stored as text*. If you have the data in Parquet, or as a DataFrame with real date types, use that instead.

---

## 🎬 Your first report

Pick whichever way suits you. They all produce the same report.

### 💻 From the command line

```bash
datascope sales.csv -o sales.html --open
```

`-o` sets the output file (default: `data_profile_report.html`) and `--open` opens it in your browser. While it runs, datascope prints what it's doing to the terminal, then a **run summary**:

```text
Loading and profiling customers.parquet ...
Report written to report.html

Checks:
  ✓ Column statistics                    ran           All 19 columns: nulls, distinct counts, top values, ...
  ◐ Personal & sensitive data detection  partial       Column names checked; values checked on a sample of 1,000 rows per column (largest column has 4,012).  → --sample-size 4012
  ✓ Duplicate rows                       ran           Exact duplicates across all columns.
  ✓ Correlations                         ran           All 5 numeric columns (10 pairs).
  ✓ Primary-key search                   ran           No key can be unique: the table has 12 exact duplicate rows.
  ✓ Column relationship dependencies     ran           All 13 candidate columns tested in both directions.
  ✓ Referential integrity (declared)     ran           1 check.
  ...

To extend this run with every → change above:
  datascope customers.parquet --reference country_code=countries.csv:code --sample-size 4012

To reproduce this run:
  datascope customers.parquet --reference country_code=countries.csv:code
```

The `◐ partial` line means a limit kicked in, and the `→` shows the flag that would lift it. [More on the run summary](settings.md#-the-run-summary).

### 🐍 From Python, with a file

```python
from datascope import profile

result = profile("sales.csv", output_html="sales.html")
```

### 🐼 From Python, with a DataFrame

```python
import pandas as pd
from datascope import profile

df = pd.read_csv("sales.csv")
result = profile(df, output_html="sales.html", source_name="sales")
```

`source_name` is the name shown at the top of the report. Every call also **returns** the profile as a Python dict, so you can use the numbers directly, for example in a data-quality gate in CI:

```python
result = profile(df, output_html="sales.html")
assert result["meta"]["duplicate_rows"] == 0, "duplicate rows found"
assert not [a for a in result["overview"]["alerts"] if a["severity"] == "high"], "high-severity alerts"
```

See the [Python API](python-api.md) for everything the dict contains.

---

## 🧪 Try the demo dataset

The repository ships with a synthetic customer table that has realistic problems built in:

```bash
python example.py
```

It writes `example_report.html`. Things to find in it:

| 🔍 Look for | Where in the report |
|---|---|
| 6 columns of personal data (names, emails, phone numbers, SSNs, addresses, dates of birth), masked | [Personal & sensitive data](report-tour.md#-personal--sensitive-data) |
| 12 exact duplicate rows | [Data quality → Table level](report-tour.md#-data-quality) |
| Columns that are mostly empty (`churn_date`, `support_notes`, ...) | [Data quality → Column level](report-tour.md#-data-quality) |
| A constant column (`schema_version`) | [Data quality → Column level](report-tour.md#-data-quality) |
| Negative quantities, which shouldn't exist | `quantity` → [column detail](report-tour.md#-column-detail) |
| Dates stored as text (`date_of_birth`) | [Alerts](report-tour.md#-data-quality) |
| Customers referred by IDs that don't exist | [Referential integrity](report-tour.md#-referential-integrity) |
| Country codes missing from a lookup table (`SE`) | [Referential integrity](report-tour.md#-referential-integrity) |
| `churn_reason → is_active`: a churn reason always means inactive | [Column relationship dependencies](report-tour.md#-column-relationship-dependencies) |

---

## 👀 What to look at first

When you open a report for the first time, this order works well:

1. **🧾 The headline tiles**: rows, columns, how many columns hold personal data.
2. **🟧 The strip under them**, if there is one: it tells you which checks were limited in this run.
3. **🩺 Data quality**: completeness and duplicates for the whole table, then the column-level alerts, most severe first.
4. **🔐 Personal & sensitive data**: before sharing the data, or the report, with anyone.
5. **🔗 Referential integrity and column relationship dependencies**: broken links and broken rules.
6. **🧱 The column grid**: filter, sort by missing %, and click any column for its full detail.
7. **🧮 The run summary** at the bottom: what wasn't checked, and the command to check it.

---

## 🧭 Where next

<table>
<tr>
<td>🖼️ <b><a href="report-tour.md">A tour of the report</a></b><br>What every panel means.</td>
<td>☁️ <b><a href="bigquery.md">Profile BigQuery</a></b><br>Tables and queries, with cost control.</td>
</tr>
<tr>
<td>🔎 <b><a href="checks.md">The checks</a></b><br>How each one decides.</td>
<td>⚙️ <b><a href="settings.md">Settings</a></b><br>Change any threshold, repeat any run.</td>
</tr>
</table>
