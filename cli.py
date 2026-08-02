"""Command-line entry point: python -m datascope input.csv -o report.html"""
from __future__ import annotations

import argparse

from .core import profile


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="datascope",
        description="Profile a dataset and generate an interactive HTML report.",
    )
    parser.add_argument("input", help="Path to a csv/tsv/parquet/xlsx/json file")
    parser.add_argument("-o", "--output", default="data_profile_report.html", help="Output HTML path")
    parser.add_argument("--name", default=None, help="Source name shown in the report (default: input filename)")
    parser.add_argument("--sample-size", type=int, default=1000, help="Rows sampled per column for PII/PHI content checks")
    parser.add_argument("--open", action="store_true", help="Open the report in your browser when done")
    args = parser.parse_args()

    profile(
        args.input,
        output_html=args.output,
        source_name=args.name,
        open_browser=args.open,
        sample_size_for_content_checks=args.sample_size,
    )
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
