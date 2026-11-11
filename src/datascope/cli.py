"""Command-line entry point: datascope input.csv -o report.html

Every threshold flag is generated from `datascope.settings.Settings`, so
`datascope --help` always lists the complete, current set of parameters
with their defaults.
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from typing import Any, Dict, List, Optional

from .settings import BIGQUERY, BOTH, GROUPS, PANDAS, Settings, flag_name, iter_fields

DESCRIPTION = """\
Profile a dataset and write a single, self-contained interactive HTML report.

Profiles a local file (csv, tsv, parquet, xlsx, json) with pandas, or a
BigQuery table / query inside BigQuery (only aggregates leave the
warehouse). After each run it prints which checks ran fully, which were
capped or skipped and the flags that would extend them, plus a command
that reproduces the run exactly. The report shows the same summary and
every setting used."""

EPILOG = """\
examples:
  datascope sales.csv -o sales.html --open
  datascope orders.csv --reference customer_id=customers.csv:id --reference parent_order_id=order_id
  datascope sales.csv --max-correlation-cols 60 --ri-parent-min-unique-pct 90
  datascope --bq-table my-project.sales.orders --estimate        # cost per section, runs nothing
  datascope --bq-table my-project.sales.orders --no-correlations --suggested-references check
  datascope --bq-table my-project.sales.orders --print-sql

Settings marked [pandas only] or [BigQuery only] are ignored by the other
engine. Thresholds not listed here (semantic-type cut-offs, PII scoring
weights, quality-rule suggestions) are fixed heuristics, documented in the
README under "Fixed heuristics"; the report records the datascope version
that applied them."""


def _setting_help(f: Any, m: Dict[str, Any]) -> str:
    engine = {PANDAS: " [pandas only]", BIGQUERY: " [BigQuery only]", BOTH: ""}[m["engines"]]
    default = f.default
    shown = ("on" if default else "off") if isinstance(default, bool) else default
    return f"{m['help']}{engine} (default: {shown})"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="datascope", description=DESCRIPTION, epilog=EPILOG,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="?", default=None,
                        help="Path to a csv/tsv/parquet/xlsx/json file (or use --bq-table / --bq-query)")

    out = parser.add_argument_group("Output")
    out.add_argument("-o", "--output", default="data_profile_report.html",
                     help="Output HTML path (default: data_profile_report.html)")
    out.add_argument("--name", default=None, help="Source name shown in the report (default: the file or table name)")
    out.add_argument("--open", action="store_true", help="Open the report in your browser when done")
    out.add_argument("--quiet", action="store_true", help="Don't print progress or the run summary")

    bq = parser.add_argument_group(
        "BigQuery source", "Profile inside BigQuery instead of loading a file (needs the 'bigquery' extra).")
    bq.add_argument("--bq-table", default=None, metavar="PROJECT.DATASET.TABLE", help="Table to profile")
    bq.add_argument("--bq-query", default=None, metavar="SQL", help="SQL query whose result to profile")
    bq.add_argument("--bq-query-file", default=None, metavar="PATH", help="File containing the SQL query to profile")
    bq.add_argument("--sample", action="store_true",
                    help="Profile a random sample of --bq-table instead of all of it: SELECT * ... TABLESAMPLE "
                         "SYSTEM (1 PERCENT) LIMIT 1000000. Cheap, and after the run it projects what profiling the "
                         "whole table would use: bytes from a free dry run, slot time scaled up from the sample. "
                         "Each query re-samples, so steps can see slightly different rows.")
    bq.add_argument("--sample-percent", type=float, default=None, metavar="X",
                    help="Share of the table's storage blocks to sample, 0-100 (default: 1; implies --sample)")
    bq.add_argument("--sample-max-rows", type=int, default=None, metavar="N",
                    help="Cap on sampled rows (default: 1000000; implies --sample)")
    bq.add_argument("--columns", default=None, help="Comma-separated subset of columns to profile (default: all)")
    bq.add_argument("--bq-project", default=None, help="Project that runs (and is billed for) the queries")
    bq.add_argument("--bq-location", default=None, help="BigQuery location, e.g. EU or US")
    bq.add_argument("--max-bytes-billed", type=int, default=None,
                    help="Fail a query rather than bill more than this many bytes")
    bq.add_argument("--estimate", action="store_true",
                    help="Dry-run everything and print the bytes and approximate cost per section "
                         "(profiling, correlations, each reference check). Runs and bills nothing.")
    bq.add_argument("--print-sql", action="store_true", help="Print the SQL that would run, and exit")
    bq.add_argument("--approx-distinct", action="store_const", const="approx", dest="distinct_counts",
                    default=argparse.SUPPRESS, help="Same as --distinct-counts approx")

    groups = {}
    for key, title in GROUPS:
        groups[key] = parser.add_argument_group(f"Settings: {title}")
    groups["ri"].add_argument(
        "--reference", action="append", default=[], metavar="CHILD=PARENT",
        help="Declare a referential-integrity check (repeatable): every non-null value of column CHILD must "
             "exist in PARENT. PARENT is a column of the same table, another file's column as PATH:COLUMN, "
             "or on BigQuery another table's column as PROJECT.DATASET.TABLE.COLUMN.")
    for f, m in iter_fields():
        kwargs: Dict[str, Any] = {"dest": f.name, "default": argparse.SUPPRESS, "help": _setting_help(f, m)}
        if isinstance(f.default, bool):
            kwargs["action"] = argparse.BooleanOptionalAction
        else:
            kwargs["type"] = type(f.default)
            kwargs["metavar"] = m["metavar"] or ("{" + ",".join(m["choices"]) + "}" if m["choices"] else
                                                 {int: "N", float: "X", str: "TEXT"}[type(f.default)])
            if m["choices"]:
                kwargs["choices"] = m["choices"]
        groups[m["group"]].add_argument(flag_name(f.name), **kwargs)
    return parser


def _progress(message: str) -> None:
    # stderr, flushed: shows up immediately even where stdout is buffered
    # (e.g. Git Bash on Windows), and doesn't mix into piped output.
    print(message, file=sys.stderr, flush=True)


def _settings_from(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Settings:
    given = {f.name: getattr(args, f.name) for f, _ in iter_fields() if hasattr(args, f.name)}
    try:
        return Settings(**given)
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
        raise  # pragma: no cover


def _sample_text(sm: Dict[str, Any]) -> str:
    from .bigquery import format_bytes
    lines = [f"Sample: {sm['sample_rows']:,} rows ({sm['percent']:g}% of {sm['table']}"
             + (f", which has {sm['table_rows']:,} rows" if sm["table_rows"] is not None else "") + ")."]
    if sm.get("warning"):
        lines.append(sm["warning"])
    full = []
    if sm["full_bytes_processed"] is not None:
        full.append(f"process about {format_bytes(sm['full_bytes_processed'])} (free dry run; what on-demand pricing bills)")
    if sm["full_slot_ms"] is not None:
        full.append(f"use roughly {sm['full_slot_ms'] / 1000:,.0f} slot-seconds (this run's slot time x "
                    f"{sm['scale']:,.1f}, the table/sample row ratio; a rough guide, large queries don't scale exactly)")
    if full:
        lines.append("Profiling the whole table with the same settings would " + " and ".join(full) + ".")
    return "\n".join(lines)


def _print_estimate(est: Dict[str, Any]) -> None:
    width = max(len(s["section"]) for s in est["sections"])
    print(f"This profile will process {est['bytes_processed_human']} when run "
          f"(about ${est['estimated_cost_usd']:.4f} at ${est['price_per_tib_usd']}/TiB on-demand). Nothing was run.")
    print()
    for s in est["sections"]:
        print(f"  {s['section']:<{width}}  {s['bytes_processed_human']:>10}  ${s['estimated_cost_usd']:.4f}"
              + (f"  {s['note']}" if s["note"] else ""))
    print()
    print(est["pricing_note"])


def main(argv: Optional[List[str]] = None) -> None:
    try:
        _main(argv)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr, flush=True)
        sys.exit(130)


def _main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = _settings_from(args, parser)

    bq_sources = [s for s in (args.bq_table, args.bq_query, args.bq_query_file) if s]
    if len(bq_sources) + (1 if args.input else 0) != 1:
        parser.error("give exactly one source: an input file, --bq-table, --bq-query or --bq-query-file")
    references: Dict[str, Any] = {}
    for spec in args.reference:
        child, sep, parent = spec.partition("=")
        if not sep or not child.strip() or not parent.strip():
            parser.error(f"--reference expects CHILD=PARENT, got {spec!r}")
        references[child.strip()] = parent.strip()

    sample = args.sample or args.sample_percent is not None or args.sample_max_rows is not None
    if sample and not args.bq_table:
        parser.error("--sample needs --bq-table (it samples a table)")
    sample_percent = args.sample_percent if args.sample_percent is not None else 1.0
    sample_max_rows = args.sample_max_rows if args.sample_max_rows is not None else 1_000_000

    if bq_sources:
        from .bigquery import BigQueryProfiler, sample_query

        query = args.bq_query
        if args.bq_query_file:
            with open(args.bq_query_file, encoding="utf-8") as fh:
                query = fh.read()
        columns = [c.strip() for c in args.columns.split(",") if c.strip()] if args.columns else None
        profiler = BigQueryProfiler(project=args.bq_project, location=args.bq_location,
                                    maximum_bytes_billed=args.max_bytes_billed, settings=settings,
                                    progress=None if args.quiet else _progress)
        # Surface skipped-column warnings as plain lines on stderr.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                # --estimate / --print-sql with --sample describe the sample query.
                source = ({"query": sample_query(args.bq_table, sample_percent, sample_max_rows)} if sample
                          else {"table": args.bq_table, "query": query})
                if args.estimate:
                    est = profiler.estimate(columns=columns, references=references, **source)
                elif args.print_sql:
                    sqls = profiler.build_sql(columns=columns, references=references, **source)
                else:
                    result = profiler.profile(table=args.bq_table, query=query, columns=columns,
                                              source_name=args.name, references=references,
                                              sample_percent=sample_percent if sample else None,
                                              sample_max_rows=sample_max_rows)
            except ValueError as exc:
                if "references" not in str(exc) and "sample" not in str(exc):
                    raise
                parser.error(str(exc))
        for w in caught:
            print(f"Warning: {w.message}", file=sys.stderr)
        if args.estimate:
            _print_estimate(est)
            return
        if args.print_sql:
            print(";\n\n".join(sqls))
            return
        profiler.to_html(result, args.output)
        if args.open:
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(args.output)}")
    else:
        if args.estimate or args.print_sql:
            parser.error("--estimate and --print-sql only apply to BigQuery sources")
        from .core import DataProfiler, profile

        resolved: Dict[str, Any] = {}
        for child, parent in references.items():
            path, sep, column = parent.rpartition(":")
            if sep and os.path.isfile(path):
                other = DataProfiler()._load(path)
                if column not in other.columns:
                    parser.error(f"--reference {child}={parent}: {path} has no column {column!r}")
                resolved[child] = (parent, other[column])  # label as typed, so the run can be repeated
            else:
                resolved[child] = parent
        if not args.quiet:
            _progress(f"Loading and profiling {args.input} ...")
        try:
            result = profile(args.input, output_html=args.output, source_name=args.name, open_browser=args.open,
                             references=resolved, settings=settings)
        except ValueError as exc:
            if "references" not in str(exc):
                raise
            parser.error(str(exc))
    print(f"Report written to {args.output}")
    if not args.quiet:
        from .run_summary import format_text

        meta = result["meta"]
        if meta.get("usage_by_section"):
            from .bigquery import _usage_text
            print("BigQuery usage:")
            for section, usage in meta["usage_by_section"].items():
                print(f"  {section:<11} {usage['queries']} quer{'y' if usage['queries'] == 1 else 'ies'}: "
                      + _usage_text(usage))
        if meta.get("sample"):
            print()
            print(_sample_text(meta["sample"]))
        print()
        print(format_text(meta))


if __name__ == "__main__":
    main()
