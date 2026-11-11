"""Command-line entry point: python -m datascope input.csv -o report.html"""
from __future__ import annotations

import argparse
import os
import sys
import warnings


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="datascope",
        description="Profile a dataset and generate an interactive HTML report.",
    )
    parser.add_argument("input", nargs="?", default=None, help="Path to a csv/tsv/parquet/xlsx/json file")
    parser.add_argument("-o", "--output", default="data_profile_report.html", help="Output HTML path")
    parser.add_argument("--name", default=None, help="Source name shown in the report (default: input filename)")
    parser.add_argument("--sample-size", type=int, default=1000, help="Rows sampled per column for PII/PHI content checks")
    parser.add_argument("--open", action="store_true", help="Open the report in your browser when done")
    parser.add_argument(
        "--reference", action="append", default=[], metavar="CHILD=PARENT",
        help="Referential-integrity check (repeatable): every value of column CHILD must exist in PARENT. "
             "PARENT is a column of the same table, another file's column as PATH:COLUMN, or with BigQuery "
             "a column of another table as PROJECT.DATASET.TABLE.COLUMN",
    )

    bq = parser.add_argument_group(
        "BigQuery", "Profile inside BigQuery instead of loading a file (needs the 'bigquery' extra)."
    )
    bq.add_argument("--bq-table", default=None, metavar="PROJECT.DATASET.TABLE", help="Table to profile")
    bq.add_argument("--bq-query", default=None, metavar="SQL", help="SQL query whose result to profile")
    bq.add_argument("--bq-query-file", default=None, metavar="PATH", help="File containing the SQL query to profile")
    bq.add_argument("--columns", default=None, help="Comma-separated subset of columns to profile (default: all)")
    bq.add_argument("--bq-project", default=None, help="Project that runs (and is billed for) the query")
    bq.add_argument("--bq-location", default=None, help="BigQuery location, e.g. EU or US")
    bq.add_argument("--approx-distinct", action="store_true",
                    help="Use APPROX_COUNT_DISTINCT instead of exact COUNT(DISTINCT) — cheaper on very large tables")
    bq.add_argument("--max-bytes-billed", type=int, default=None, help="Fail the query rather than bill more than this many bytes")
    bq.add_argument("--estimate", action="store_true",
                    help="Show how much data the profile would scan (and the approximate on-demand cost) and exit without running it")
    bq.add_argument("--print-sql", action="store_true", help="Print the profiling SQL and exit without running it")
    args = parser.parse_args()

    bq_sources = [s for s in (args.bq_table, args.bq_query, args.bq_query_file) if s]
    if len(bq_sources) + (1 if args.input else 0) != 1:
        parser.error("give exactly one source: an input file, --bq-table, --bq-query or --bq-query-file")
    references = {}
    for spec in args.reference:
        child, sep, parent = spec.partition("=")
        if not sep or not child.strip() or not parent.strip():
            parser.error(f"--reference expects CHILD=PARENT, got {spec!r}")
        references[child.strip()] = parent.strip()

    if bq_sources:
        from .bigquery import BigQueryProfiler

        query = args.bq_query
        if args.bq_query_file:
            with open(args.bq_query_file, encoding="utf-8") as fh:
                query = fh.read()
        columns = [c.strip() for c in args.columns.split(",") if c.strip()] if args.columns else None
        profiler = BigQueryProfiler(
            project=args.bq_project, location=args.bq_location,
            exact_distinct=not args.approx_distinct, maximum_bytes_billed=args.max_bytes_billed,
        )
        # Surface skipped-column warnings as plain lines on stderr.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            if args.estimate:
                est = profiler.estimate(table=args.bq_table, query=query, columns=columns, references=references)
            elif args.print_sql:
                sqls = profiler.build_sql(table=args.bq_table, query=query, columns=columns, references=references)
            else:
                result = profiler.profile(table=args.bq_table, query=query, columns=columns, source_name=args.name,
                                          references=references)
        for w in caught:
            print(f"Warning: {w.message}", file=sys.stderr)
        if args.estimate:
            print(f"This profile will process {est['bytes_processed_human']} when run "
                  f"(about ${est['estimated_cost_usd']:.4f} at ${est['price_per_tib_usd']}/TiB on-demand). "
                  "Nothing was run.")
            return
        if args.print_sql:
            print(";\n\n".join(sqls))
            return
        profiler.to_html(result, args.output)
        if args.open:
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(args.output)}")
    else:
        from .core import DataProfiler, profile

        resolved = {}
        for child, parent in references.items():
            path, sep, column = parent.rpartition(":")
            if sep and os.path.isfile(path):
                other = DataProfiler()._load(path)
                if column not in other.columns:
                    parser.error(f"--reference {child}={parent}: {path} has no column {column!r}")
                resolved[child] = (f"{os.path.basename(path)}:{column}", other[column])
            else:
                resolved[child] = parent
        try:
            profile(
                args.input,
                output_html=args.output,
                source_name=args.name,
                open_browser=args.open,
                sample_size_for_content_checks=args.sample_size,
                references=resolved,
            )
        except ValueError as exc:
            if "references" not in str(exc):
                raise
            parser.error(str(exc))
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
