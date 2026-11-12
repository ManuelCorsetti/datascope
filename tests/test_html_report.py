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


# ------------------------------------------------------------------ security
# Data values (column names, top values) are attacker-controlled text: a
# CSV from a vendor or a free-text field can hold markup. These pin the
# defences in html_report.py; the payloads are the ones a manual review
# used to run script in the report before they were fixed.
import base64
import hashlib
import importlib.util
import re
from pathlib import Path

from datascope import html_report

ROOT = Path(__file__).resolve().parent.parent
PAYLOADS = [
    '<img src=x onerror=alert(1)>',
    'x" onmouseover="alert(1)',
    "x' onmouseover='alert(1)",
    "</script><script>alert(1)</script>",
    "<!--<script>",
    "__SETTINGS_DOC_JSON__ __SCRIPT_HASH__ __FONT_FACES__",
]


def _hostile_report(tmp_path):
    rng = np.random.default_rng(0)
    n = 60
    data = {p: rng.normal(size=n) for p in PAYLOADS[:3]}  # hostile column names
    data["status"] = [PAYLOADS[i % len(PAYLOADS)] for i in range(n)]  # hostile top values
    out = tmp_path / "hostile.html"
    result = DataProfiler().profile(pd.DataFrame(data))
    render_html(result, str(out))
    return result, out.read_text(encoding="utf-8")


def _script(html):
    start = html.index("<script>") + len("<script>")
    return html[start:html.index("</script>", start)]


def test_hostile_values_cannot_end_or_comment_out_the_script(tmp_path):
    result, html = _hostile_report(tmp_path)
    assert html.count("<script>") == 1 and html.count("</script>") == 1
    script = _script(html)
    assert "<!--" not in script and "<script" not in script
    # ...and the values still round-trip exactly (placeholders included).
    blob = re.search(r"const PROFILE = (.*?);\n", script).group(1)
    embedded = json.loads(blob)
    assert {tv["value"] for c in embedded["columns"] if c["name"] == "status" for tv in c["top_values"]} == set(PAYLOADS)
    assert set(PAYLOADS[:3]) <= {c["name"] for c in embedded["columns"]}


def test_csp_allows_only_the_reports_own_script_and_no_network(tmp_path):
    _, html = _hostile_report(tmp_path)
    csp = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', html).group(1)
    digest = base64.b64encode(hashlib.sha256(_script(html).encode("utf-8")).digest()).decode()
    assert f"script-src 'sha256-{digest}'" in csp
    assert "default-src 'none'" in csp and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    assert "http://" not in html and "https://" not in html


def test_report_js_escapes_quotes_and_renders_tooltips_as_text():
    t = html_report._TEMPLATE
    assert "'\"': '&quot;'" in t and "\"'\": '&#39;'" in t
    assert "tooltipEl.textContent = text" in t and "tooltipEl.innerHTML" not in t
    # every tooltip attribute goes through esc(); none is concatenated raw
    assert re.findall(r"data-tip=\"' \+ (?!esc\()", t) == []
    assert "<br>" not in t


def test_fonts_are_bundled_and_inlined(tmp_path):
    _, html = _hostile_report(tmp_path)
    for family in ("Roboto", "Roboto Mono", "Material Symbols Outlined"):
        assert f"font-family: '{family}'" in html
    assert html.count("url(data:font/woff2;base64,") == 5
    assert "<noscript>" in html and "Open this report in a web browser" in html


def test_every_icon_the_template_uses_is_in_the_bundled_subset():
    spec = importlib.util.spec_from_file_location("update_fonts", ROOT / "scripts" / "update_fonts.py")
    update_fonts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(update_fonts)
    used = update_fonts.used_icon_names(html_report._TEMPLATE)
    bundled = set((ROOT / "src" / "datascope" / "fonts" / "icons.txt").read_text().split())
    assert used - bundled == set(), "new icon(s) in the template: run python scripts/update_fonts.py"
