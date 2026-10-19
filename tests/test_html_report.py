import json

import numpy as np
import pandas as pd

from datascope.core import DataProfiler
from datascope.html_report import _sanitize, render_html


def test_render_html_produces_valid_document(tmp_path):
    df = pd.DataFrame({"a": range(50), "b": np.random.default_rng(0).normal(size=50)})
    result = DataProfiler().profile(df, source_name="smoke_test")
    out = tmp_path / "report.html"
    render_html(result, str(out))
    content = out.read_text(encoding="utf-8")
    assert content.startswith("<!DOCTYPE html>")
    assert content.strip().endswith("</html>")
    assert "smoke_test" in content


def test_render_html_handles_minimal_profile_without_crashing(tmp_path):
    # No numeric columns -> no correlations; single column -> no PK search
    # collisions; nothing sensitive; nothing missing. Exercises every
    # "if not present, hide the panel" branch in the JS.
    df = pd.DataFrame({"only_col": ["a", "b", "c"]})
    result = DataProfiler().profile(df)
    out = tmp_path / "minimal.html"
    render_html(result, str(out))
    assert out.exists()


def test_render_html_handles_empty_dataframe(tmp_path):
    result = DataProfiler().profile(pd.DataFrame())
    out = tmp_path / "empty.html"
    render_html(result, str(out))
    assert out.exists()


class TestSanitize:
    def test_nan_and_inf_become_none(self):
        assert _sanitize({"x": float("nan")}) == {"x": None}
        assert _sanitize({"x": float("inf")}) == {"x": None}

    def test_numpy_scalars_converted_to_python(self):
        assert _sanitize(np.int64(5)) == 5
        assert isinstance(_sanitize(np.int64(5)), int)

    def test_result_is_always_json_serializable(self):
        df = pd.DataFrame({"a": [1, 2, np.nan], "b": [np.inf, -np.inf, 3]})
        result = DataProfiler().profile(df)
        json.dumps(_sanitize(result))  # must not raise
