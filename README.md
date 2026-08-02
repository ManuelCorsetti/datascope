# datascope

Extensive Python data profiling &rarr; one self-contained interactive HTML
dashboard. No server, no JS framework, no build step — the report is a
single `.html` file you can email, host, or open locally forever. The
only external resource is a Google Fonts CSS link (progressive
enhancement — falls back to system fonts if it can't load).

## Install

```
pip install -r requirements.txt
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

- Quality score (0–100, shown with its components, not just the number)
- Numeric correlation matrix and a **missing-value correlation matrix**
  (which columns tend to be null together — useful for spotting a shared
  upstream cause)
- Exact duplicate-row detection
- Primary-key candidate detection (single column, and a bounded search
  over identifier-like columns for composite keys)
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
datascope/
  core.py          DataProfiler class, orchestration, correlations, PK search
  stats.py         numeric/string/datetime/boolean stat + histogram calculators
  semantic.py      semantic type inference
  pii.py           PII/PHI/PCI detection + value masking
  quality.py       quality-rule + dbt-snippet recommendations, quality score
  html_report.py   renders the profile dict to the HTML dashboard
  cli.py / __main__.py   `python -m datascope`
example.py         synthetic messy dataset + runnable demo
```
