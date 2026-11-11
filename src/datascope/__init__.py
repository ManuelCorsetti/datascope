"""
datascope
=============
Extensive, dependency-light data profiling for pandas DataFrames (or a
CSV/Parquet/Excel/JSON path), producing a single self-contained
interactive HTML dashboard.

Quick start
-----------
    import pandas as pd
    from datascope import profile

    df = pd.read_csv("your_data.csv")
    profile(df, output_html="report.html", source_name="your_data")

or straight from a file, no DataFrame needed:

    from datascope import profile
    profile("your_data.csv", output_html="report.html")

or pushed down to BigQuery (only aggregates leave the warehouse):

    from datascope import profile_bigquery
    profile_bigquery("project.dataset.table", output_html="report.html")
"""

from .bigquery import BigQueryProfiler, estimate_bigquery_cost, profile_bigquery
from .core import DataProfiler, profile
from .settings import Settings

__all__ = ["DataProfiler", "profile", "BigQueryProfiler", "profile_bigquery", "estimate_bigquery_cost", "Settings"]
__version__ = "1.1.0"
