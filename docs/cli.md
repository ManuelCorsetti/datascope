# 💻 Command line reference

> Every option of the `datascope` command, plus a cookbook of ready-to-copy runs.

[📚 Docs home](README.md) • [🚀 Getting started](getting-started.md) • [🖼️ Report tour](report-tour.md) • [🔎 Checks](checks.md) • [☁️ BigQuery](bigquery.md) • [⚙️ Settings](settings.md) • [🐍 Python API](python-api.md)

---

**On this page**

- [📐 Synopsis](#-synopsis)
- [📥 Choosing the source](#-choosing-the-source)
- [📤 Output](#-output)
- [📡 BigQuery options](#-bigquery-options)
- [🔗 References](#-references)
- [🔧 Settings flags](#-settings-flags)
- [📺 What gets printed, and exit codes](#-what-gets-printed-and-exit-codes)
- [🍳 Cookbook](#-cookbook)

---

## 📐 Synopsis

```text
datascope [INPUT | --bq-table T | --bq-query SQL | --bq-query-file PATH]
          [-o OUTPUT] [--name NAME] [--open] [--quiet]
          [BigQuery options] [--reference CHILD=PARENT ...] [settings flags]
```

`python -m datascope` works the same way. `datascope --help` prints the complete, current manual, with every setting's default.

---

## 📥 Choosing the source

Give **exactly one** of:

| Option | Profiles | Engine |
|---|---|---|
| `INPUT` | A `.csv`, `.tsv`, `.json`, `.parquet`/`.pq` or `.xlsx` file ([formats](getting-started.md#-supported-inputs)) | 🐼 pandas |
| `--bq-table PROJECT.DATASET.TABLE` | A BigQuery table | ☁️ BigQuery |
| `--bq-query SQL` | The result of a SQL query | ☁️ BigQuery |
| `--bq-query-file PATH` | The result of the SQL in a file | ☁️ BigQuery |

---

## 📤 Output

| Option | Default | Does |
|---|---|---|
| `-o`, `--output PATH` | `data_profile_report.html` | Where to write the report |
| `--name NAME` | the file or table name | The source name shown at the top of the report |
| `--open` | off | Open the report in your browser when done |
| `--quiet` | off | Don't print progress or the [run summary](settings.md#-the-run-summary) |

---

## 📡 BigQuery options

| Option | Default | Does |
|---|---|---|
| `--columns a,b,c` | all columns | Profile only these columns |
| `--bq-project PROJECT` | your default | The project that runs, and pays for, the queries |
| `--bq-location LOC` | — | BigQuery location, e.g. `US` or `EU` |
| `--max-bytes-billed N` | — | Fail any query that would bill more than N bytes |
| `--estimate` | — | Dry-run everything and print the cost [per section](bigquery.md#-estimate-before-you-run). Runs and bills nothing |
| `--print-sql` | — | Print the SQL that would run, and exit |
| `--sample` | off | Profile a random sample of `--bq-table` and [project the full run](bigquery.md#-profile-a-sample-first) |
| `--sample-percent X` | `1` | Share of the table's storage blocks to sample (implies `--sample`) |
| `--sample-max-rows N` | `1000000` | Cap on sampled rows (implies `--sample`) |

> [!NOTE]
> `--estimate` and `--print-sql` only apply to BigQuery sources, and `--sample` needs `--bq-table`. Used otherwise, they stop with an error that says so.

---

## 🔗 References

`--reference CHILD=PARENT` declares a [referential-integrity check](checks.md#-referential-integrity): every non-empty value of column `CHILD` must exist in `PARENT`. Repeat it for several checks.

| `PARENT` form | Meaning | Example |
|---|---|---|
| `COLUMN` | A column of the same table | `--reference manager_id=employee_id` |
| `PATH:COLUMN` | A column of another file (pandas) | `--reference customer_id=data/customers.csv:id` |
| `PROJECT.DATASET.TABLE.COLUMN` | A column of another BigQuery table | `--reference customer_id=proj.sales.customers.id` |

---

## 🔧 Settings flags

Every [setting](settings.md) is also a flag, grouped in `--help` by check:

| Group | Flags |
|---|---|
| 📐 Column statistics and sampling | `--top-n-values`, `--histogram-bins`, `--sample-size`, `--random-state`, `--sensitive-min-match-pct` |
| 🚨 Alert thresholds | `--missing-warning-pct`, `--missing-high-pct`, `--outlier-alert-pct`, `--sensitive-alert-min-confidence` |
| 📈 Correlations | `--correlations` / `--no-correlations`, `--max-correlation-cols`, `--high-correlation-threshold` |
| 🔑 Keys and duplicates | `--max-pk-candidate-pool`, `--max-pk-combo-size`, `--max-duplicate-column-check` |
| 🧩 Column relationship dependencies | `--column-dependencies` / `--no-column-dependencies`, `--dependency-min-purity`, `--dependency-min-support-rows`, `--max-dependency-candidates` |
| 🔗 Referential integrity | `--suggested-references {auto,check,list,off}`, `--max-reference-suggestions`, `--ri-parent-min-unique-pct`, `--ri-suggest-min-match-pct`, `--ri-suggest-min-rows`, `--ri-suggest-min-distinct`, `--ri-sample-orphans`, `--ri-high-orphan-pct` |
| ☁️ BigQuery query shape | `--distinct-counts {keys,exact,approx}`, `--max-columns-per-query` |

👉 Defaults and descriptions: **[the full settings table](settings.md#-all-settings)**.

---

## 📺 What gets printed, and exit codes

| Stream | What |
|---|---|
| **stderr** | Progress while running (BigQuery: each query with its job ID, time, bytes, slot time and shuffle), and warnings such as skipped columns |
| **stdout** | `Report written to …`, BigQuery usage, the [run summary](settings.md#-the-run-summary), and the reproduce / extend commands |

Because progress goes to stderr, `datascope ... > summary.txt` captures just the summary.

| Exit code | Meaning |
|---|---|
| `0` | Success |
| `2` | Usage error, e.g. no source, two sources, an invalid setting value, or a bad `--reference` |
| `130` | Interrupted with Ctrl+C (any running BigQuery job is cancelled first) |
| other | An unexpected error, such as a BigQuery permission error; the message says what went wrong |

---

## 🍳 Cookbook

<details open>
<summary><b>🐼 Profile a file and open the report</b></summary>

```bash
datascope sales.csv -o sales.html --open
```
</details>

<details>
<summary><b>🔍 Check every value for personal data, not just a sample</b></summary>

```bash
datascope customers.csv --sample-size 1000000
```
</details>

<details>
<summary><b>🔐 Only alert on the clearest personal-data cases</b></summary>

```bash
datascope customers.csv --sensitive-alert-min-confidence 0.7
```
Flagged columns are still masked; only the alerts change.
</details>

<details>
<summary><b>🔗 Check orders against a customers file</b></summary>

```bash
datascope orders.csv --reference customer_id=customers.csv:id --reference parent_order_id=order_id
```
</details>

<details>
<summary><b>🧹 Messy data: let slightly-duplicated keys still count as keys</b></summary>

```bash
datascope orders.csv --ri-parent-min-unique-pct 90 --ri-suggest-min-match-pct 80
```
</details>

<details>
<summary><b>🧪 Stricter missing-value alerts</b></summary>

```bash
datascope data.csv --missing-warning-pct 5 --missing-high-pct 20
```
</details>

<details>
<summary><b>⚡ Quick run on a wide table</b></summary>

```bash
datascope wide.csv --no-correlations --no-column-dependencies
```
</details>

<details>
<summary><b>☁️ Estimate, then profile a BigQuery table safely</b></summary>

```bash
datascope --bq-table proj.sales.orders --bq-project my-billing-project --estimate
datascope --bq-table proj.sales.orders --bq-project my-billing-project --max-bytes-billed 10000000000 -o orders.html
```
</details>

<details>
<summary><b>🧪 Try a 1% sample of a big BigQuery table first</b></summary>

```bash
datascope --bq-table proj.sales.orders --sample
```
</details>

<details>
<summary><b>🎰 Lowest slot usage on BigQuery</b></summary>

```bash
datascope --bq-table proj.sales.orders --distinct-counts approx --no-correlations
```
Primary-key detection is off with approximate distinct counts.
</details>

<details>
<summary><b>📜 See the SQL without running anything</b></summary>

```bash
datascope --bq-table proj.sales.orders --print-sql
```
</details>
