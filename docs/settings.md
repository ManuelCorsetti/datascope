# ⚙️ Settings & repeatable runs

> Every threshold is a setting with a default. Every run tells you what it checked, what it didn't, and how to repeat or extend it.

[📚 Docs home](README.md) • [🚀 Getting started](getting-started.md) • [🖼️ Report tour](report-tour.md) • [🔎 Checks](checks.md) • [☁️ BigQuery](bigquery.md) • [💻 CLI](cli.md) • [🐍 Python API](python-api.md)

---

**On this page**

- [🧰 How settings work](#-how-settings-work)
- [🧮 The run summary](#-the-run-summary)
- [🔁 Reproduce or extend a run](#-reproduce-or-extend-a-run)
- [📋 All settings](#-all-settings)
- [🧷 Fixed heuristics](#-fixed-heuristics)

---

## 🧰 How settings work

A setting is anything that decides **which checks run** or **what gets flagged**: alert thresholds, size limits, sample sizes, on/off switches. Each one has the same name everywhere:

<table>
<tr><th>💻 Command line</th><th>🐍 Python</th></tr>
<tr>
<td>

```bash
datascope data.csv \
  --ri-parent-min-unique-pct 90 \
  --max-correlation-cols 60 \
  --no-correlations
```

</td>
<td>

```python
from datascope import profile, DataProfiler, Settings

# as keywords
profile(df, ri_parent_min_unique_pct=90, max_correlation_cols=60)

# or as a Settings object you can reuse
strict = Settings(missing_warning_pct=5, missing_high_pct=20)
DataProfiler(settings=strict).profile(df)
```

</td>
</tr>
</table>

- 🔤 **Names match**: `--max-correlation-cols` on the command line is `max_correlation_cols` in Python.
- 🔘 **Switches** have an on and an off form: `--correlations` / `--no-correlations`.
- 🛑 **Values are validated**: a percentage over 100, an unknown setting or a wrong type fails straight away with a clear message, rather than being silently ignored.
- 🐼☁️ **Engine-specific** settings are marked *pandas only* or *BigQuery only*, and the other engine ignores them.
- 📖 `datascope --help` lists every setting, grouped by check, with its default. It's generated from the same definitions as the table below, so the two always match.

---

## 🧮 The run summary

After every run, the command line prints, and the report's [Run summary panel](report-tour.md#-run-summary) shows, a status for **every check family**:

```text
Checks:
  ✓ Column statistics                    ran           All 19 columns: nulls, distinct counts, top values, ...
  ◐ Personal & sensitive data detection  partial       Column names checked; values checked on a sample of 1,000 rows per column (largest column has 4,012).  → --sample-size 4012
  ✓ Duplicate rows                       ran           Exact duplicates across all columns.
  ✓ Identical columns                    ran           Every pair of columns compared.
  ✓ Correlations                         ran           All 5 numeric columns (10 pairs).
  ✓ Missing-value correlation            ran           All 4 partly-missing columns.
  ✓ Primary-key search                   ran           No key can be unique: the table has 12 exact duplicate rows.
  ✓ Column relationship dependencies     ran           All 13 candidate columns tested in both directions.
  ✓ Referential integrity (declared)     ran           1 check.
  ✓ Referential integrity (suggested)    ran           1 possible reference checked; 1 kept.
```

| Mark | Status | Meaning | What to do |
|:---:|---|---|---|
| ✓ | **ran** | Done in full | Nothing |
| ◐ | **partial** | A limit kicked in (a sample size, a column cap, …) | Use the `→` flag to lift it |
| ○ | **skipped** | Turned off for this run | Use the `→` flag to turn it back on |
| … | **listed** | Found but not run, e.g. suggested references on BigQuery | Use the `→` flag to run them |
| · | **not set up** | Needs input from you | e.g. `--reference CHILD=PARENT` |
| – | **n/a** | Not available on this engine | See the [engine comparison](checks.md#-what-each-engine-supports) |
| ✓ | **nothing to do** | Nothing to check, e.g. fewer than two numeric columns | Nothing |

On BigQuery the summary also reports what the run [actually used](bigquery.md#-see-what-a-run-actually-used): bytes, slot time and bytes shuffled.

---

## 🔁 Reproduce or extend a run

Below the checks, two ready-made commands:

```text
To extend this run with every → change above:
  datascope customers.parquet --reference country_code=countries.csv:code --sample-size 4012

To reproduce this run:
  datascope customers.parquet --reference country_code=countries.csv:code
```

- **Reproduce** contains every setting that differed from its default, the references, and the source, so you can run the same profile again later and compare.
- **Extend** applies every `→` flag at once. When two checks ask for the same limit, it takes the larger.
- In the report, both have a **Copy** button, and **All settings** lists every value used (changed ones highlighted) with the datascope version.

Everything is also in the [profile dict](python-api.md#-the-profile-dict): `result["meta"]["settings"]`, `["checks"]`, `["command"]` and `["extend_command"]`.

> [!NOTE]
> When the data was passed in from Python as a DataFrame, there's no file name to put in the command, so it uses an `INPUT` placeholder (and `PATH:COLUMN` for references to other DataFrames).

---

## 📋 All settings

Defaults are in the second column. *Engines* says which engine uses the setting.

> [!TIP]
> This table is generated from `src/datascope/settings.py`, and a test fails if it goes stale. After changing a setting, regenerate it with `python -c "from datascope.settings import settings_markdown; print(settings_markdown())"` and paste the output between the markers below.

<!-- settings-table:start (generated from datascope/settings.py; tests check it is current) -->
**Column statistics and sampling**

| Flag / keyword | Default | Engines | What it does |
|---|---|---|---|
| `--top-n-values` / `top_n_values` | `10` | both | Most frequent values kept per column. |
| `--histogram-bins` / `histogram_bins` | `30` | pandas | Bars in each numeric histogram. |
| `--sample-size` / `sample_size_for_content_checks` | `1000` | pandas | Rows sampled per column when checking values for personal or sensitive data (emails, phone numbers, ID and card numbers...). Larger = slower, fewer misses. |
| `--random-state` / `random_state` | `42` | pandas | Seed for that sample, so reruns flag the same columns. |
| `--sensitive-min-match-pct` / `sensitive_min_match_pct` | `1` | pandas | Flag a column as personal or sensitive data when at least this % of its sampled values match a pattern (email address, phone, ID, card or bank account number), whole or, for emails and dashed ID numbers, inside text. Low by default: a column that is only partly personal data still holds personal data. Column names are checked regardless. |

**Alert thresholds**

| Flag / keyword | Default | Engines | What it does |
|---|---|---|---|
| `--missing-warning-pct` / `missing_warning_pct` | `20` | both | A column with more than this % missing raises a warning. |
| `--missing-high-pct` / `missing_high_pct` | `50` | both | A column with more than this % missing raises a high-severity alert. |
| `--outlier-alert-pct` / `outlier_alert_pct` | `5` | pandas | Alert when more than this % of a numeric column is outside 1.5x IQR. |
| `--sensitive-alert-min-confidence` / `sensitive_alert_min_confidence` | `0` | both | Raise an alert for a column that looks like personal or sensitive data only at or above this detection confidence (0-1). The default 0 alerts on every flagged column; raise it to alert only on the clearest cases. Flagged columns are masked either way. |

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

**Column relationship dependencies (one column's value determines another's)**

| Flag / keyword | Default | Engines | What it does |
|---|---|---|---|
| `--column-dependencies` / `column_dependencies` | `on` | pandas | Look for columns whose value always (or nearly always) determines another column's value, e.g. zip_code -> state: redundant columns, hidden business rules, and the rows that break them. |
| `--dependency-min-purity` / `dependency_min_purity` | `0.98` | pandas | Report A -> B when at least this share (0-1) of the rows agree with the most common B for their A; the rest are shown as exceptions. |
| `--dependency-min-support-rows` / `dependency_min_support_rows` | `20` | pandas | Ignore a pair of columns with fewer rows of evidence than this. |
| `--max-dependency-candidates` / `max_dependency_candidates` | `25` | pandas | Test at most this many columns on either side of A -> B (pairs grow with the square). |

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
| `--distinct-counts` / `distinct_counts` | `keys` | BigQuery | How distinct values are counted. 'keys': approximate counts (HyperLogLog++, about 1% error) for every column, then exact counts only for columns that could be keys (no NULLs and nearly all values unique), in a second query that reads just those columns. Key and reference detection stay exact, without the heavy shuffle (slot time) of an exact COUNT(DISTINCT) on every column. 'exact': exact counts for every column, the heaviest on slots. 'approx': approximate only, the lightest; primary-key detection is then off. |
| `--max-columns-per-query` / `max_columns_per_query` | `100` | BigQuery | Split wide tables into profiling queries of at most this many columns. |
<!-- settings-table:end -->

**Not settings, but command-line options**: the source (`--bq-table`, …), output (`-o`, `--name`, `--open`, `--quiet`), BigQuery connection (`--bq-project`, `--bq-location`, `--max-bytes-billed`), sampling (`--sample`, …) and `--reference`. See the [command line reference](cli.md).

---

## 🧷 Fixed heuristics

These rules are **not** settings: they decide how a column is classified and when personal data is suspected, and changing them means changing the code. Every report records the **datascope version**, which pins them.

<details open>
<summary><b>🔖 Semantic types</b> (<code>semantic.py</code>)</summary>
<br>

| Rule | Result |
|---|---|
| Exactly two distinct values | binary categorical, or boolean if they look like true/false |
| Numeric, ≥ 95% unique and more than 20 values | identifier if the name reads as an id, otherwise continuous numeric |
| Numeric with ≤ 20 distinct values, or < 5% unique | discrete numeric categorical |
| Text with `-` or `/` in most values that parses as dates for > 90% of a 200-value sample | datetime string (dates stored as text) |
| Text ≥ 98% unique | identifier (short values or an id-like name), otherwise free text |
| Text averaging more than 80 characters | free text |
| Text with ≤ 50 distinct values, or < 10% unique | categorical |
| Anything else that's text | high-cardinality text |

</details>

<details open>
<summary><b>🔐 Personal & sensitive data</b> (<code>pii.py</code>)</summary>
<br>

- A column is flagged when its **name** matches a keyword list, or when at least `--sensitive-min-match-pct` of sampled **values** match a pattern (email, national ID, phone, IP address, credit card with a Luhn checksum, IBAN with a mod-97 checksum). Emails and dashed ID numbers also count inside free text.
- **Confidence** = 0.55 for a name match + 0.5 × the share of values that match + 0.05 for a passed checksum, capped at 0.99. `--sensitive-alert-min-confidence` applies to this number.
- When two kinds score equally, the more specific wins (an SSN-shaped value is a national ID, not a phone number; `ip_address` is an IP address, not a postal address).

</details>

<details open>
<summary><b>✅ Quality-rule suggestions</b> (<code>quality.py</code>)</summary>
<br>

- **Accepted values** when the top values cover ≥ 99% of rows.
- **Outlier review** when more than 1% of values are outside 1.5 × IQR.
- **Non-negative check** when the name contains count, amount, qty, quantity, price, total, age, duration, length, size, score or balance, and there are negative values.

</details>

<details open>
<summary><b>🧩 Column relationship dependencies</b> (<code>relationships.py</code>)</summary>
<br>

- Nearly-unique (≥ 99% unique), empty and constant columns are left out of the search.
- Only values of A that repeat count as evidence.
- Up to 5 exception rows are kept per dependency.

</details>

<details open>
<summary><b>🚨 Alerts</b></summary>
<br>

- **Outliers** are values outside 1.5 × the interquartile range.
- At most **8** correlated pairs and **8** dependencies become alerts; the panels list them all.
- Reference suggestions need a key-like name (ending `_id`, `_key`, `_ref`, `_code`, `_no`, `_num` or `_number`, or the camelCase forms) that names the parent column.

</details>
