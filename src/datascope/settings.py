"""
Every tunable threshold and limit, in one place.

`Settings` is the single source of truth for:

* the defaults both engines use,
* validation of user-supplied values,
* the command-line flags and `--help` text (cli.py generates them from
  the field metadata below, so the manual can't drift from the code),
* what gets recorded in `result["meta"]["settings"]`, so any report can
  be reproduced exactly.

Thresholds that are *not* here are fixed heuristics (semantic-type
cut-offs, PII scoring weights, quality-rule suggestions). They are
documented in the README ("Fixed heuristics") and pinned by the
datascope version recorded in every report.

    from datascope import DataProfiler, Settings
    DataProfiler(settings=Settings(ri_parent_min_unique_pct=90))
    DataProfiler(ri_parent_min_unique_pct=90)          # same thing
"""
from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, field, fields, replace
from typing import Any, Dict, Iterator, List, Optional, Tuple

BOTH, PANDAS, BIGQUERY = "both", "pandas", "bigquery"

# Display order and titles of the setting groups (CLI --help and README).
GROUPS: List[Tuple[str, str]] = [
    ("general", "Column statistics and sampling"),
    ("alerts", "Alert thresholds"),
    ("correlations", "Correlations"),
    ("keys", "Keys and duplicates"),
    ("fd", "Functional dependencies (column A determines column B)"),
    ("ri", "Referential integrity"),
    ("bigquery", "BigQuery query shape"),
]

SUGGESTED_REFERENCE_MODES = ("auto", "check", "list", "off")


def _s(default: Any, help: str, group: str, engines: str = BOTH, *, minimum: Optional[float] = None,
       maximum: Optional[float] = None, flag: Optional[str] = None, choices: Optional[Tuple[str, ...]] = None,
       metavar: Optional[str] = None) -> Any:
    return field(default=default, metadata={
        "help": help, "group": group, "engines": engines, "min": minimum, "max": maximum,
        "flag": flag, "choices": choices, "metavar": metavar,
    })


@dataclass(frozen=True)
class Settings:
    # ----------------------------------------------------------- general
    top_n_values: int = _s(10, "Most frequent values kept per column.", "general", minimum=0)
    histogram_bins: int = _s(30, "Bars in each numeric histogram.", "general", PANDAS, minimum=1)
    sample_size_for_content_checks: int = _s(
        1000, "Rows sampled per column when checking values for personal or sensitive data (emails, phone "
              "numbers, ID and card numbers...). Larger = slower, fewer misses.", "general", PANDAS, minimum=1,
        flag="--sample-size")
    random_state: int = _s(42, "Seed for that sample, so reruns flag the same columns.", "general", PANDAS)
    sensitive_min_match_pct: float = _s(
        1.0, "Flag a column as personal or sensitive data when at least this %% of its sampled values match a "
             "pattern (email address, phone, ID, card or bank account number), whole or, for emails and dashed "
             "ID numbers, inside text. Low by default: a column that is only partly personal data still holds "
             "personal data. Column names are checked regardless.", "general", PANDAS, minimum=0, maximum=100)

    # ------------------------------------------------------------ alerts
    missing_warning_pct: float = _s(20.0, "A column with more than this %% missing raises a warning.", "alerts",
                                    minimum=0, maximum=100)
    missing_high_pct: float = _s(50.0, "A column with more than this %% missing raises a high-severity alert.",
                                 "alerts", minimum=0, maximum=100)
    outlier_alert_pct: float = _s(5.0, "Alert when more than this %% of a numeric column is outside 1.5x IQR.",
                                  "alerts", PANDAS, minimum=0, maximum=100)
    sensitive_alert_min_confidence: float = _s(
        0.0, "Raise an alert for a column that looks like personal or sensitive data only at or above this "
             "detection confidence (0-1). The default 0 alerts on every flagged column; raise it to alert only "
             "on the clearest cases. Flagged columns are masked either way.",
        "alerts", minimum=0, maximum=1)

    # ------------------------------------------------------ correlations
    correlations: bool = _s(True, "Pearson correlation matrix of numeric columns (and, on pandas, the "
                                  "missing-value correlation matrix). On BigQuery this adds CORR() terms to the "
                                  "first profiling query: free for tables of up to --max-columns-per-query "
                                  "columns, see --estimate for the exact cost.", "correlations")
    max_correlation_cols: int = _s(30, "Correlate at most this many numeric columns (n*(n-1)/2 pairs).",
                                   "correlations", minimum=2)
    high_correlation_threshold: float = _s(0.8, "Alert on column pairs with |r| at or above this.", "correlations",
                                           minimum=0, maximum=1)

    # -------------------------------------------------------------- keys
    max_pk_candidate_pool: int = _s(10, "Composite primary-key search: consider this many of the most distinct "
                                        "no-null columns.", "keys", PANDAS, minimum=1)
    max_pk_combo_size: int = _s(3, "Composite primary-key search: try combinations of up to this many columns.",
                                "keys", PANDAS, minimum=2)
    max_duplicate_column_check: int = _s(100, "Skip identical-column detection on tables wider than this "
                                              "(every pair is compared).", "keys", PANDAS, minimum=0)

    # ---------------------------------------------------------------- fd
    functional_dependencies: bool = _s(True, "Search for column A -> column B dependencies (zip -> state).", "fd",
                                       PANDAS)
    fd_min_purity: float = _s(0.98, "Report A -> B when at least this share (0-1) of evidence rows agree with "
                                    "the majority B for their A.", "fd", PANDAS, minimum=0, maximum=1)
    fd_min_support_rows: int = _s(20, "Ignore a pair with fewer evidence rows than this.", "fd", PANDAS, minimum=1)
    max_fd_candidate_pool: int = _s(25, "Test at most this many columns as either side (pairs grow with the "
                                        "square).", "fd", PANDAS, minimum=2)

    # ---------------------------------------------------------------- ri
    suggested_references: str = _s(
        "auto", "What to do with references datascope suggests itself (same table, from column names): "
                "'check' runs them; 'list' only lists them, with their cost on BigQuery; 'off' skips them. "
                "'auto' = check on pandas, list on BigQuery (where each is an extra query).",
        "ri", choices=SUGGESTED_REFERENCE_MODES)
    max_reference_suggestions: int = _s(10, "Check or list at most this many suggested references.", "ri",
                                        minimum=0)
    ri_parent_min_unique_pct: float = _s(
        99.0, "A suggested reference's target must be an identifier column, with no NULLs and at least this "
              "%% unique. Below 100 so that duplicate rows don't hide a real key; lower it for messier data.",
        "ri", minimum=0, maximum=100)
    ri_suggest_min_match_pct: float = _s(
        90.0, "Keep a suggestion only if at least this %% of its rows match the target; fewer means it is "
              "probably not a reference at all.", "ri", minimum=0, maximum=100)
    ri_suggest_min_rows: int = _s(10, "Don't suggest a reference for a column with fewer non-null rows.", "ri",
                                  minimum=1)
    ri_suggest_min_distinct: int = _s(3, "Don't suggest a reference for a column with fewer distinct values.",
                                      "ri", minimum=1)
    ri_sample_orphans: int = _s(5, "Example orphan values kept per check (the most frequent).", "ri", minimum=0)
    ri_high_orphan_pct: float = _s(5.0, "A declared check with more than this %% orphan rows raises a "
                                        "high-severity alert; otherwise a warning.", "ri", minimum=0, maximum=100)

    # ---------------------------------------------------------- bigquery
    exact_distinct: bool = _s(True, "Exact COUNT(DISTINCT). --no-exact-distinct uses APPROX_COUNT_DISTINCT: "
                                    "cheaper on very large tables, but disables primary-key detection.",
                              "bigquery", BIGQUERY)
    max_columns_per_query: int = _s(100, "Split wide tables into profiling queries of at most this many columns.",
                                    "bigquery", BIGQUERY, minimum=1)

    def __post_init__(self) -> None:
        for f in fields(self):
            v, m = getattr(self, f.name), f.metadata
            want = type(f.default)
            if want is float and isinstance(v, int) and not isinstance(v, bool):
                object.__setattr__(self, f.name, float(v))
                v = float(v)
            if not isinstance(v, want) or (want is not bool and isinstance(v, bool)):
                raise TypeError(f"Setting {f.name} must be {want.__name__}, got {v!r}.")
            if m["choices"] and v not in m["choices"]:
                raise ValueError(f"Setting {f.name} must be one of {m['choices']}, got {v!r}.")
            if m["min"] is not None and v < m["min"]:
                raise ValueError(f"Setting {f.name} must be >= {m['min']}, got {v!r}.")
            if m["max"] is not None and v > m["max"]:
                raise ValueError(f"Setting {f.name} must be <= {m['max']}, got {v!r}.")
        if self.missing_warning_pct > self.missing_high_pct:
            raise ValueError("missing_warning_pct must not exceed missing_high_pct.")

    # ------------------------------------------------------------ helpers
    def updated(self, **changes: Any) -> "Settings":
        unknown = sorted(set(changes) - {f.name for f in fields(self)})
        if unknown:
            raise TypeError(f"Unknown setting(s): {', '.join(unknown)}. See datascope.Settings or `datascope --help`.")
        return replace(self, **changes)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def non_defaults(self) -> Dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) != f.default}

    def suggested_reference_mode(self, engine: str) -> str:
        """'auto' resolved for an engine: 'check', 'list' or 'off'."""
        if self.max_reference_suggestions == 0:
            return "off"
        if self.suggested_references == "auto":
            return "list" if engine == BIGQUERY else "check"
        return self.suggested_references

    def flags_for(self, names: Optional[List[str]] = None, engine: str = BOTH) -> List[str]:
        """CLI tokens reproducing these settings (non-defaults only, or
        `names`), skipping settings the engine ignores."""
        out: List[str] = []
        for f, m in iter_fields():
            if names is not None and f.name not in names:
                continue
            if names is None and getattr(self, f.name) == f.default:
                continue
            if engine != BOTH and m["engines"] not in (BOTH, engine):
                continue
            out += setting_tokens(f.name, getattr(self, f.name))
        return out


def iter_fields() -> Iterator[Tuple[Any, Any]]:
    for f in fields(Settings):
        yield f, f.metadata


def flag_name(name: str) -> str:
    meta = Settings.__dataclass_fields__[name].metadata
    return meta["flag"] or "--" + name.replace("_", "-")


def setting_tokens(name: str, value: Any) -> List[str]:
    """`--max-correlation-cols 45`, `--no-correlations`, ... for one setting."""
    flag = flag_name(name)
    if isinstance(value, bool):
        return [flag] if value else ["--no-" + flag[2:]]
    return [flag, _fmt(value)]


def _fmt(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def default_of(name: str) -> Any:
    f = Settings.__dataclass_fields__[name]
    return f.default if f.default is not MISSING else None


def resolve(settings: Optional[Settings], overrides: Dict[str, Any]) -> Settings:
    """Settings from an optional base plus keyword overrides. Accepts the
    pre-Settings keyword `suggest_references=True/False` too."""
    overrides = dict(overrides)
    if "suggest_references" in overrides:
        flag = overrides.pop("suggest_references")
        overrides.setdefault("suggested_references", "auto" if flag else "off")
    return (settings or Settings()).updated(**overrides)


def settings_markdown() -> str:
    """The README's settings table (tests check the README matches)."""
    lines = []
    titles = dict(GROUPS)
    group = None
    for f, m in iter_fields():
        if m["group"] != group:
            group = m["group"]
            lines += ["", f"**{titles[group]}**", "", "| Flag / keyword | Default | Engines | What it does |", "|---|---|---|---|"]
        default = ("on" if f.default else "off") if isinstance(f.default, bool) else _fmt(f.default)
        engines = {BOTH: "both", PANDAS: "pandas", BIGQUERY: "BigQuery"}[m["engines"]]
        help_text = m["help"].replace("%%", "%").replace("|", "\\|")
        lines.append(f"| `{flag_name(f.name)}` / `{f.name}` | `{default}` | {engines} | {help_text} |")
    return "\n".join(lines).strip()
