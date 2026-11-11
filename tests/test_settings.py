import argparse

import numpy as np
import pandas as pd
import pytest

from datascope import DataProfiler, Settings
from datascope.cli import build_parser, main
from datascope.run_summary import format_text
from datascope.settings import iter_fields


def _check(result, id):
    return next(c for c in result["meta"]["checks"] if c["id"] == id)


class TestSettings:
    def test_defaults_and_validation(self):
        s = Settings()
        assert s.ri_parent_min_unique_pct == 99.0 and s.correlations is True
        assert Settings(ri_parent_min_unique_pct=90).ri_parent_min_unique_pct == 90.0  # int accepted for float
        with pytest.raises(ValueError, match="ri_parent_min_unique_pct"):
            Settings(ri_parent_min_unique_pct=120)
        with pytest.raises(ValueError, match="suggested_references"):
            Settings(suggested_references="sometimes")
        with pytest.raises(TypeError, match="correlations"):
            Settings(correlations="yes")
        with pytest.raises(ValueError, match="missing_warning_pct"):
            Settings(missing_warning_pct=60, missing_high_pct=50)
        with pytest.raises(TypeError, match="Unknown setting"):
            DataProfiler(not_a_setting=1)

    def test_auto_mode_resolves_per_engine(self):
        assert Settings().suggested_reference_mode("pandas") == "check"
        assert Settings().suggested_reference_mode("bigquery") == "list"
        assert Settings(max_reference_suggestions=0).suggested_reference_mode("pandas") == "off"

    def test_flags_round_trip_through_the_cli_parser(self):
        s = Settings(correlations=False, max_correlation_cols=45, ri_parent_min_unique_pct=90.5,
                     suggested_references="list", distinct_counts="approx")
        args = build_parser().parse_args(["x.csv"] + s.flags_for())
        given = {f.name: getattr(args, f.name) for f, _ in iter_fields() if hasattr(args, f.name)}
        assert Settings(**given) == s

    def test_every_setting_has_a_documented_flag(self):
        help_text = build_parser().format_help()
        for f, m in iter_fields():
            assert m["help"], f.name
            assert (m["flag"] or "--" + f.name.replace("_", "-")) in help_text


class TestThresholdsAreHonoured:
    def test_missing_alert_thresholds(self):
        df = pd.DataFrame({"a": [None] * 30 + [1] * 70})
        alerts = lambda **kw: [a["severity"] for a in DataProfiler(**kw).profile(df)["overview"]["alerts"]
                               if a["column"] == "a" and "missing" in a["message"]]
        assert alerts() == ["warning"]
        assert alerts(missing_high_pct=25) == ["high"]
        assert alerts(missing_warning_pct=40, missing_high_pct=50) == []

    def test_lower_parent_uniqueness_finds_a_messier_key(self):
        n = 200
        ids = np.arange(1, n + 1)
        ids[:6] = 1  # a key with a few duplicates: 97.5% unique
        referrers = np.r_[np.arange(2, 52), np.arange(2, 52)].astype(float)  # 50 customers, each referred twice
        df = pd.DataFrame({"customer_id": ids, "referred_by_customer_id": np.r_[referrers, [np.nan] * 100]})
        assert DataProfiler().profile(df)["referential_integrity"] == []
        found = DataProfiler(ri_parent_min_unique_pct=95).profile(df)["referential_integrity"]
        assert [(r["column"], r["references"]) for r in found] == [("referred_by_customer_id", "customer_id")]

    def test_switches(self):
        df = pd.DataFrame({"a": range(50), "b": np.arange(50) * 2.0, "c": [1, 2] * 25})
        r = DataProfiler(correlations=False, column_dependencies=False).profile(df)
        assert r["correlations"] is None and r["missing_correlation"] is None and r["column_dependencies"] == []
        assert _check(r, "correlations")["status"] == "skipped"
        assert _check(r, "dependencies")["flags"] == ["--column-dependencies"]
        assert _check(r, "dependencies")["name"] == "Column relationship dependencies"


class TestRunSummary:
    def test_caps_are_reported_with_the_flag_that_lifts_them(self):
        df = pd.DataFrame({f"n{i}": np.random.default_rng(i).normal(size=40) for i in range(5)})
        r = DataProfiler(max_correlation_cols=3, sample_size_for_content_checks=10).profile(df, source_name="demo")
        corr = _check(r, "correlations")
        assert corr["status"] == "partial" and corr["flags"] == ["--max-correlation-cols", "5"]
        assert _check(r, "pii")["flags"] == ["--sample-size", "40"]
        meta = r["meta"]
        assert meta["settings"]["max_correlation_cols"] == 3 and meta["datascope_version"]
        assert meta["command"]["argv"][:4] == ["datascope", "INPUT", "--name", "demo"]
        assert "--max-correlation-cols 3" in meta["command"]["text"] and not meta["command"]["complete"]
        ext = meta["extend_command"]["text"]
        assert "--max-correlation-cols 5" in ext and "--sample-size 40" in ext
        text = format_text(meta)
        assert "To extend this run" in text and "→ --max-correlation-cols 5" in text

    def test_listed_suggestions_explain_how_to_check_them(self):
        df = pd.DataFrame({"order_id": np.arange(1, 101), "parent_order_id": np.r_[np.arange(1, 26).repeat(2), [np.nan] * 50]})
        r = DataProfiler(suggested_references="list").profile(df)
        assert r["referential_integrity"] == []
        assert r["reference_suggestions"] == [{"column": "parent_order_id", "references": "order_id",
                                               "status": "listed", "estimated_bytes": None}]
        sug = _check(r, "ri_suggested")
        assert sug["status"] == "listed" and sug["flags"] == ["--suggested-references", "check"]

    def test_over_the_limit_is_reported(self):
        df = pd.DataFrame({"id": np.arange(1, 101), "a_id": np.r_[np.arange(1, 51)] .tolist() * 2,
                           "b_id": [1, 2, 3, 4] * 25})
        r = DataProfiler(max_reference_suggestions=1).profile(df)
        assert [s["status"] for s in r["reference_suggestions"]] == ["checked", "over_limit"]
        assert _check(r, "ri_suggested")["flags"] == ["--max-reference-suggestions", "2"]


def test_shared_limit_takes_the_larger_request():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({f"n{i}": rng.normal(size=60) for i in range(5)})
    for i in range(4):
        df.loc[rng.choice(60, 5, replace=False), f"n{i}"] = np.nan  # 4 partly-missing columns, 5 numeric
    meta = DataProfiler(max_correlation_cols=2).profile(df)["meta"]
    assert "--max-correlation-cols 5" in meta["extend_command"]["text"]


def test_pk_search_is_not_extended_when_duplicate_rows_make_keys_impossible():
    df = pd.DataFrame({"a": [1, 1, 2, 3] * 10, "b": [1, 1, 2, 2] * 10})
    pk = _check(DataProfiler(max_pk_combo_size=2).profile(df), "pk")
    assert pk["status"] == "ran" and "duplicate" in pk["detail"] and not pk["flags"]


def test_cli_run_prints_summary_and_reproducible_command(tmp_path, monkeypatch, capsys):
    path = tmp_path / "d.csv"
    pd.DataFrame({f"n{i}": np.random.default_rng(i).normal(size=40) for i in range(4)}).to_csv(path, index=False)
    main([str(path), "-o", str(tmp_path / "r.html"), "--max-correlation-cols", "2", "--no-column-dependencies"])
    out = capsys.readouterr().out
    assert "◐ Correlations" in out and "→ --max-correlation-cols 4" in out
    assert f"datascope {path} --max-correlation-cols 2 --no-column-dependencies" in out
    with pytest.raises(SystemExit):
        main([str(path), "--ri-parent-min-unique-pct", "150"])
    assert "ri_parent_min_unique_pct" in capsys.readouterr().err


def test_docs_settings_table_is_current():
    import pathlib
    from datascope.settings import settings_markdown
    readme = (pathlib.Path(__file__).parent.parent / "docs" / "settings.md").read_text(encoding="utf-8")
    start = readme.index("<!-- settings-table:start")
    body = readme[readme.index("-->", start) + 3: readme.index("<!-- settings-table:end -->")].strip()
    assert body == settings_markdown(), "docs/settings.md settings table is stale: regenerate it with settings_markdown()"
