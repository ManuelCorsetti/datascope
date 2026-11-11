"""
What a profile run did, what it left out, and how to repeat or extend it.

Every engine records in `result["meta"]`:

* `settings`  — every Settings value used (see settings.py),
* `checks`    — one entry per check family: did it run fully, partly
  (a size cap kicked in), not at all (turned off, or not available on
  this engine), or does it need input (declared references)? Entries
  that can be extended carry the setting `changes` that would do it,
* `command`   — the command line that reproduces the run, and the one
  that extends it with every suggested change.

The HTML report and the CLI both render this, so a reader can see what
was *not* checked as clearly as what was.
"""
from __future__ import annotations

import shlex
from typing import Any, Dict, List, Optional, Sequence

from .settings import BIGQUERY, PANDAS, Settings, setting_tokens

RAN, PARTIAL, SKIPPED, LISTED, NOT_CONFIGURED, NOT_AVAILABLE, NOTHING = (
    "ran", "partial", "skipped", "listed", "not_configured", "not_available", "nothing_to_check")
EXTENDABLE = (PARTIAL, SKIPPED, LISTED)


def check(id: str, name: str, status: str, detail: str, changes: Optional[Dict[str, Any]] = None,
          hint: Optional[str] = None) -> Dict[str, Any]:
    changes = changes or {}
    flags: List[str] = []
    for k, v in changes.items():
        flags += setting_tokens(k, v)
    return {"id": id, "name": name, "status": status, "detail": detail, "changes": changes,
            "flags": flags, "hint": hint}


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


# ------------------------------------------------------------- pieces
def correlation_check(s: Settings, n_numeric: int) -> Dict[str, Any]:
    name = "Correlations"
    if not s.correlations:
        return check("correlations", name, SKIPPED, "Turned off.", {"correlations": True})
    if n_numeric < 2:
        return check("correlations", name, NOTHING, f"{_plural(n_numeric, 'numeric column')}: nothing to correlate.")
    if n_numeric > s.max_correlation_cols:
        return check("correlations", name, PARTIAL,
                     f"First {s.max_correlation_cols} of {n_numeric} numeric columns.",
                     {"max_correlation_cols": n_numeric})
    return check("correlations", name, RAN, f"All {n_numeric} numeric columns "
                                            f"({_plural(n_numeric * (n_numeric - 1) // 2, 'pair')}).")


def reference_checks(s: Settings, engine: str, declared: int, suggestions: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    if declared:
        out.append(check("ri_declared", "Referential integrity (declared)", RAN, f"{_plural(declared, 'check')}."))
    else:
        out.append(check("ri_declared", "Referential integrity (declared)", NOT_CONFIGURED,
                         "None declared.", hint="--reference CHILD=PARENT (repeatable); PARENT is a column of this "
                         "table or " + ("PROJECT.DATASET.TABLE.COLUMN" if engine == BIGQUERY else "PATH:COLUMN of another file")))

    name = "Referential integrity (suggested)"
    mode = s.suggested_reference_mode(engine)
    by_status: Dict[str, int] = {}
    for sg in suggestions:
        by_status[sg["status"]] = by_status.get(sg["status"], 0) + 1
    total = len(suggestions)
    over = by_status.get("over_limit", 0)
    if mode == "off":
        out.append(check("ri_suggested", name, SKIPPED, "Turned off.", {"suggested_references": "check"}))
    elif not total:
        out.append(check("ri_suggested", name, NOTHING,
                         "No column's name and data point at an identifier column in this table."))
    elif mode == "list":
        known = [sg["estimated_bytes"] for sg in suggestions if sg["status"] == "listed" and sg["estimated_bytes"] is not None]
        cost = (f" Checking {'it' if len(known) == 1 else 'them'} would scan about {_fmt_bytes(sum(known))}."
                if known else "")
        changes: Dict[str, Any] = {"suggested_references": "check"}
        if over:
            changes["max_reference_suggestions"] = total
        out.append(check("ri_suggested", name, LISTED,
                         f"{_plural(total - over, 'possible reference')} listed, not checked.{cost}"
                         + (f" {over} more over --max-reference-suggestions." if over else ""), changes))
    else:
        checked = by_status.get("checked", 0) + by_status.get("below_match", 0)
        detail = f"{_plural(checked, 'possible reference')} checked; {by_status.get('checked', 0)} kept"
        if by_status.get("below_match"):
            detail += f", {by_status['below_match']} matched under {s.ri_suggest_min_match_pct:g}% and were dropped"
        detail += "."
        if over:
            out.append(check("ri_suggested", name, PARTIAL, detail + f" {over} more over the limit.",
                             {"max_reference_suggestions": total}))
        else:
            out.append(check("ri_suggested", name, RAN, detail))
    return out


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TB"


# ------------------------------------------------------------ engines
def pandas_checks(s: Settings, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """ctx: n_cols, n_rows, duplicate_rows, max_non_null, n_numeric,
    n_missing_corr_cols, pk (dict), fd_pool_eligible, declared, suggestions."""
    out = [check("column_stats", "Column statistics", RAN, f"All {_plural(ctx['n_cols'], 'column')}: nulls, "
                 "distinct counts, top values, numeric/text/date stats, histograms, outliers.")]

    if ctx["max_non_null"] > s.sample_size_for_content_checks:
        out.append(check("pii", "Personal & sensitive data detection", PARTIAL,
                         f"Column names checked; values checked on a sample of {s.sample_size_for_content_checks:,} "
                         f"rows per column (largest column has {ctx['max_non_null']:,}).",
                         {"sample_size_for_content_checks": ctx["max_non_null"]}))
    else:
        out.append(check("pii", "Personal & sensitive data detection", RAN,
                         "Column names and every value checked."))

    out.append(check("duplicate_rows", "Duplicate rows", RAN, "Exact duplicates across all columns."))
    if ctx["n_cols"] > s.max_duplicate_column_check:
        out.append(check("duplicate_columns", "Identical columns", SKIPPED,
                         f"{ctx['n_cols']} columns is over the limit of {s.max_duplicate_column_check}.",
                         {"max_duplicate_column_check": ctx["n_cols"]}))
    else:
        out.append(check("duplicate_columns", "Identical columns", RAN, "Every pair of columns compared."))

    out.append(correlation_check(s, ctx["n_numeric"]))
    m = ctx["n_missing_corr_cols"]
    if not s.correlations:
        out.append(check("missing_correlation", "Missing-value correlation", SKIPPED,
                         "Turned off with correlations.", {"correlations": True}))
    elif m < 2:
        out.append(check("missing_correlation", "Missing-value correlation", NOTHING,
                         f"{_plural(m, 'column')} partly missing: nothing to correlate."))
    elif m > s.max_correlation_cols:
        out.append(check("missing_correlation", "Missing-value correlation", PARTIAL,
                         f"First {s.max_correlation_cols} of {m} partly-missing columns.", {"max_correlation_cols": m}))
    else:
        out.append(check("missing_correlation", "Missing-value correlation", RAN,
                         f"All {m} partly-missing columns."))

    pk = ctx["pk"]
    name = "Primary-key search"
    if pk["single_found"]:
        out.append(check("pk", name, RAN, "Found a single-column key, so no composite search was needed."))
    elif ctx.get("duplicate_rows"):
        out.append(check("pk", name, RAN, f"No key can be unique: the table has "
                                          f"{_plural(ctx['duplicate_rows'], 'exact duplicate row')}."))
    elif pk["eligible"] < 2:
        out.append(check("pk", name, NOTHING, "No single-column key, and too few no-null columns to combine."))
    else:
        changes: Dict[str, Any] = {}
        if pk["eligible"] > s.max_pk_candidate_pool:
            changes["max_pk_candidate_pool"] = pk["eligible"]
        if not pk["composite_found"] and s.max_pk_combo_size < min(pk["eligible"], s.max_pk_candidate_pool):
            changes["max_pk_combo_size"] = s.max_pk_combo_size + 1
        detail = (f"Combinations of up to {s.max_pk_combo_size} of the {min(pk['eligible'], s.max_pk_candidate_pool)} "
                  f"most distinct no-null columns ({pk['eligible']} eligible); "
                  + ("found one." if pk["composite_found"] else "none is unique."))
        out.append(check("pk", name, PARTIAL if changes else RAN, detail, changes))

    name = "Functional dependencies"
    if not s.functional_dependencies:
        out.append(check("fd", name, SKIPPED, "Turned off.", {"functional_dependencies": True}))
    elif ctx["n_rows"] < s.fd_min_support_rows or ctx["fd_pool_eligible"] < 2:
        out.append(check("fd", name, NOTHING, "Too few rows or candidate columns."))
    elif ctx["fd_pool_eligible"] > s.max_fd_candidate_pool:
        out.append(check("fd", name, PARTIAL, f"{s.max_fd_candidate_pool} of {ctx['fd_pool_eligible']} candidate "
                         f"columns tested (lowest cardinality first).",
                         {"max_fd_candidate_pool": ctx["fd_pool_eligible"]}))
    else:
        out.append(check("fd", name, RAN, f"All {ctx['fd_pool_eligible']} candidate columns tested in both directions."))

    return out + reference_checks(s, PANDAS, ctx["declared"], ctx["suggestions"])


def bigquery_checks(s: Settings, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """ctx: n_cols, n_skipped, n_numeric, declared, suggestions."""
    out = [check("column_stats", "Column statistics", PARTIAL if ctx["n_skipped"] else RAN,
                 f"{_plural(ctx['n_cols'], 'column')}: nulls, distinct counts, top values, numeric/text/date stats"
                 + (f"; {ctx['n_skipped']} skipped (unsupported type)." if ctx["n_skipped"] else "."))]
    na = "Not available on the BigQuery engine"
    out += [
        check("pii", "Personal & sensitive data detection", NOT_AVAILABLE,
              "Column names only: checking values would mean pulling them out of the warehouse."),
        check("histograms", "Histograms and outliers", NOT_AVAILABLE, na + " yet (needs an extra pass)."),
        check("duplicate_rows", "Duplicate rows", NOT_AVAILABLE, na + " yet (needs an extra pass)."),
        check("duplicate_columns", "Identical columns", NOT_AVAILABLE, na + "."),
        correlation_check(s, ctx["n_numeric"]),
        check("missing_correlation", "Missing-value correlation", NOT_AVAILABLE, na + "."),
    ]
    if s.exact_distinct:
        out.append(check("pk", "Primary-key search", RAN, "Single-column keys (exact distinct counts). "
                                                          "Composite keys are not available on this engine."))
    else:
        out.append(check("pk", "Primary-key search", SKIPPED, "Approximate distinct counts can't prove "
                                                              "uniqueness.", {"exact_distinct": True}))
    out.append(check("fd", "Functional dependencies", NOT_AVAILABLE, na + "."))
    return out + reference_checks(s, BIGQUERY, ctx["declared"], ctx["suggestions"])


# ------------------------------------------------------------ command
def build_command(engine: str, s: Settings, *, source: Optional[str] = None, query: Optional[str] = None,
                  table: Optional[str] = None, source_name: Optional[str] = None,
                  references: Optional[List[str]] = None, columns: Optional[Sequence[str]] = None,
                  connection: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """argv/text reproducing a run. `references` are CHILD=PARENT strings
    (None entries mark a reference the CLI can't express)."""
    argv = ["datascope"]
    placeholders = []
    if engine == BIGQUERY:
        argv += ["--bq-table", table] if table else ["--bq-query", query or ""]
        if columns:
            argv += ["--columns", ",".join(columns)]
        for key, flag in (("project", "--bq-project"), ("location", "--bq-location"),
                          ("maximum_bytes_billed", "--max-bytes-billed")):
            if (connection or {}).get(key) is not None:
                argv += [flag, str(connection[key])]
    else:
        if source is None:
            placeholders.append("INPUT")
        argv.append(source or "INPUT")
    if source_name:
        argv += ["--name", source_name]
    for ref in references or []:
        if ref is None or "PATH:COLUMN" in ref:
            placeholders.append("--reference")
        argv += ["--reference", ref or "CHILD=PATH:COLUMN"]
    argv += s.flags_for(engine=engine)
    return {"argv": argv, "text": shlex.join(argv), "complete": not placeholders}


def finish(meta: Dict[str, Any], s: Settings, checks: List[Dict[str, Any]], command_kwargs: Dict[str, Any],
           engine: str, version: str) -> None:
    """Fill meta with settings, checks and the reproduce/extend commands."""
    changes: Dict[str, Any] = {}
    for c in checks:
        if c["status"] not in EXTENDABLE:
            continue
        for k, v in c["changes"].items():
            # Two checks can ask for the same limit (correlations and
            # missing-value correlation share max_correlation_cols): take
            # the larger, so both are covered.
            if isinstance(v, (int, float)) and not isinstance(v, bool) and k in changes:
                v = max(v, changes[k])
            changes[k] = v
    meta["datascope_version"] = version
    meta["settings"] = s.to_dict()
    meta["checks"] = checks
    meta["command"] = build_command(engine, s, **command_kwargs)
    meta["extend_command"] = build_command(engine, s.updated(**changes), **command_kwargs) if changes else None


def format_text(meta: Dict[str, Any]) -> str:
    """Plain-text run summary for the CLI."""
    marks = {RAN: "✓", PARTIAL: "◐", SKIPPED: "○", LISTED: "…", NOT_CONFIGURED: "·",
             NOT_AVAILABLE: "–", NOTHING: "✓"}
    labels = {RAN: "ran", PARTIAL: "partial", SKIPPED: "skipped", LISTED: "listed", NOT_CONFIGURED: "not set up",
              NOT_AVAILABLE: "n/a", NOTHING: "nothing to do"}
    width = max(len(c["name"]) for c in meta["checks"])
    lines = ["Checks:"]
    for c in meta["checks"]:
        line = f"  {marks[c['status']]} {c['name']:<{width}}  {labels[c['status']]:<13} {c['detail']}"
        if c["flags"] and c["status"] in EXTENDABLE:
            line += f"  → {' '.join(c['flags'])}"
        elif c["hint"]:
            line += f"  (set up with {c['hint']})"
        lines.append(line)
    if meta.get("extend_command"):
        lines += ["", "To extend this run with every → change above:",
                  "  " + meta["extend_command"]["text"]]
    lines += ["", "To reproduce this run:", "  " + meta["command"]["text"]]
    if not meta["command"]["complete"]:
        lines.append("  (replace the placeholders: the data was passed in from Python)")
    return "\n".join(lines)
