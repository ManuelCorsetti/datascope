<div align="center">

# 📚 datascope documentation

**Everything about profiling data with datascope, from your first report to tuning every threshold.**

[⬅️ Back to the project README](../README.md)

</div>

---

## 🗺️ Where to start

| If you want to… | Read |
|---|---|
| 🚀 make your first report in five minutes | **[Getting started](getting-started.md)** |
| 🖼️ understand what a panel in the report is telling you | **[A tour of the report](report-tour.md)** |
| 🔎 know exactly how a check decides, or what an engine supports | **[The checks](checks.md)** |
| ☁️ profile a BigQuery table, and control what it costs | **[BigQuery](bigquery.md)** |
| ⚙️ change a threshold, or rerun with more coverage | **[Settings & repeatable runs](settings.md)** |
| 💻 look up a command-line flag | **[Command line reference](cli.md)** |
| 🐍 call datascope from Python, or read the profile dict | **[Python API](python-api.md)** |

---

## 📖 All guides

### 🚀 [Getting started](getting-started.md)
Install, the supported file formats, your first report three ways (CLI, Python file, DataFrame), the demo dataset, and a checklist of what to look at first.

### 🖼️ [A tour of the report](report-tour.md)
Every panel of the HTML report, with screenshots: the headline tiles, the data-quality section, personal & sensitive data, correlations, keys, column relationship dependencies, referential integrity, the column grid, the column detail view and the run summary.

### 🔎 [The checks](checks.md)
What each check does and the exact rules behind it: column statistics, semantic types, personal & sensitive data detection, data quality and alerts, correlations, primary keys, column relationship dependencies and referential integrity. Includes a side-by-side **pandas vs BigQuery** support matrix.

### ☁️ [BigQuery](bigquery.md)
Authentication, profiling a table, a query or some columns, the queries datascope runs, **what it costs** on on-demand and slot pricing, `--estimate`, `--sample`, distinct counts, progress output, and the limits of the engine.

### ⚙️ [Settings & repeatable runs](settings.md)
How settings work from the command line and Python, the **run summary** (what ran, what didn't, and how to extend it), the full **settings table** with defaults, and the fixed heuristics that aren't settings.

### 💻 [Command line reference](cli.md)
Every flag of the `datascope` command, grouped by purpose, exit codes, and a cookbook of ready-to-copy commands.

### 🐍 [Python API](python-api.md)
`profile()`, `DataProfiler`, `Settings`, `profile_bigquery()`, `BigQueryProfiler` and `estimate_bigquery_cost()`, with signatures and examples, plus a field-by-field guide to the **profile dict**.

---

## 🔤 Glossary

| Term | Meaning |
|---|---|
| **Profile dict** | The Python dictionary every run returns. The report is drawn from it. See [its structure](python-api.md#-the-profile-dict). |
| **Engine** | Where the profiling happens: **pandas** (in memory) or **BigQuery** (inside the warehouse). |
| **Check** | One family of analysis, such as correlations or referential integrity. Each appears in the [run summary](settings.md#-the-run-summary). |
| **Alert** | A finding worth a look, with a severity: high, warning, info, or sensitive (personal data). |
| **PII** | Personally identifiable information: names, emails, phone numbers, addresses, ID numbers, dates of birth. |
| **Orphan** | A value that should exist in a key column but doesn't, e.g. an order whose `customer_id` isn't in the customers table. |
| **A → B** | A [column relationship dependency](checks.md#-column-relationship-dependencies): each value of A always goes with the same value of B. |
| **Slot time** | BigQuery compute time. On capacity (slot) pricing it's what you pay for, rather than bytes read. |
