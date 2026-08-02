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
"""

from .core import DataProfiler, profile

__all__ = ["DataProfiler", "profile"]
__version__ = "1.0.0"
