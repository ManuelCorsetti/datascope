"""
Renders a profile dict to a single, self-contained interactive HTML file.

Design: everything is hand-rolled HTML/CSS/vanilla JS — no chart library,
no build step, no server. The only external dependency is a Google Fonts
CSS link (progressive enhancement: falls back to system fonts if it can't
load, nothing breaks). This mirrors the "plain files, zero install"
approach used elsewhere in this codebase.
"""
from __future__ import annotations

import json
import math
from typing import Any


def _sanitize(obj: Any) -> Any:
    """Recursively coerce any numpy/pandas leftovers and non-finite floats
    into plain JSON-safe Python values. Belt-and-braces on top of the
    stats module already returning clean types."""
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if hasattr(obj, "item"):  # numpy scalar
        try:
            return _sanitize(obj.item())
        except Exception:
            return str(obj)
    return obj


def render_html(profile: dict, output_path: str) -> None:
    sanitized = _sanitize(profile)
    json_str = json.dumps(sanitized, default=str)
    json_str_safe = json_str.replace("</", "<\\/")  # don't let data content break out of <script>
    html = (_TEMPLATE.replace("__PROFILE_DATA_JSON__", json_str_safe)
            .replace("__SETTINGS_DOC_JSON__", json.dumps(_settings_doc()).replace("</", "<\\/")))
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def _settings_doc() -> list:
    """Every setting's flag, default, help and engines, so the report
    documents the parameters it was run with."""
    from .settings import GROUPS, flag_name, iter_fields
    titles = dict(GROUPS)
    return [{"name": f.name, "flag": flag_name(f.name), "default": f.default, "help": m["help"].replace("%%", "%"),
             "group": titles[m["group"]], "engines": m["engines"]} for f, m in iter_fields()]


_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Data Profile</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;500;600;700&family=Roboto:wght@400;500;600;700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..40,400..500,0..1,0" rel="stylesheet">
<style>
:root {
  --bg: #f8f9fa;
  --surface: #ffffff;
  --surface-2: #f1f3f4;
  --border: #dadce0;
  --text: #202124;
  --text-muted: #5f6368;
  --text-faint: #80868b;

  --teal: #1a73e8;        /* Google Blue — the one accent used for emphasis/identity */
  --teal-soft: rgba(26,115,232,0.09);
  --amber: #b06000;       /* darkened for AA text contrast; still reads as amber/warning */
  --amber-soft: rgba(249,171,0,0.16);
  --coral: #d93025;       /* Google Red */
  --coral-soft: rgba(217,48,37,0.08);
  --violet: #8430ce;      /* reserved exclusively for sensitive-data flags */
  --violet-soft: rgba(132,48,206,0.09);
  --green: #188038;       /* Google Green */
  --green-soft: rgba(24,128,56,0.10);
  --blue: #1a73e8;

  --font-mono: 'Roboto Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  --font-sans: 'Roboto', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;

  --radius: 8px;
  --radius-sm: 6px;
  --shadow: 0 1px 2px 0 rgba(60,64,67,0.30), 0 1px 3px 1px rgba(60,64,67,0.15);
}
* { box-sizing: border-box; }
html { color-scheme: light; scroll-behavior: smooth; }
body {
  margin: 0;
  background-color: var(--bg);
  color: var(--text);
  font-family: var(--font-sans);
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
button, input, select { font: inherit; color: inherit; }
h1, h2, h3 { margin: 0; font-weight: 600; }
p { margin: 0; }
:focus-visible { outline: 2px solid var(--teal); outline-offset: 2px; border-radius: 3px; }

.material-symbols-outlined {
  font-family: 'Material Symbols Outlined'; font-weight: normal; font-style: normal;
  display: inline-block; line-height: 1; letter-spacing: normal; text-transform: none;
  white-space: nowrap; word-wrap: normal; direction: ltr; -webkit-font-smoothing: antialiased;
  font-variation-settings: 'FILL' 0, 'GRAD' 0, 'opsz' 20, 'wght' 400;
  vertical-align: middle; user-select: none; flex-shrink: 0;
}
.icon { font-size: 20px; }
.icon-sm { font-size: 16px; }
.icon-lg { font-size: 34px; }
.icon-xl { font-size: 24px; }
.icon-fill { font-variation-settings: 'FILL' 1, 'GRAD' 0, 'opsz' 24, 'wght' 500; }
.row-icon { display: inline-flex; align-items: center; gap: 4px; }

.topbar { position: sticky; top: 0; z-index: 50; background: var(--surface);
  border-bottom: 1px solid var(--border); }
.topbar-inner { max-width: 1240px; margin: 0 auto; padding: 14px 24px;
  display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.brand { display: flex; align-items: center; gap: 9px; font-family: var(--font-mono); }
.brand-mark { color: var(--teal); font-size: 18px; }
.brand-text { font-weight: 600; letter-spacing: 0.08em; font-size: 13px; }
.topbar-meta { font-family: var(--font-mono); font-size: 12px; color: var(--text-muted); display: flex; align-items: center; gap: 8px; }
.topbar-meta .dot { color: var(--text-faint); }

main { max-width: 1240px; margin: 0 auto; padding: 28px 24px 80px; }
.view[hidden] { display: none; }
section { margin-bottom: 22px; }

@keyframes rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
.kpi-grid, .panel, .columns-section { animation: rise 0.5s ease both; }
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  * { animation-duration: 0.001s !important; transition-duration: 0.001s !important; }
}

.panel { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 18px 20px; box-shadow: var(--shadow); }
.panel-title { font-family: var(--font-mono); font-size: 12px; text-transform: uppercase; letter-spacing: 0.09em;
  color: var(--text-muted); font-weight: 600; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; }
.panel-sub { color: var(--text-faint); font-weight: 400; text-transform: none; letter-spacing: 0; font-size: 11px; }

.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; }
.kpi-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 16px 18px; box-shadow: var(--shadow); animation: rise 0.4s ease both; animation-delay: calc(var(--i, 0) * 50ms); }
.kpi-icon-badge { width: 36px; height: 36px; border-radius: 9px; display: flex; align-items: center; justify-content: center; margin-bottom: 12px; background: var(--badge-bg, var(--surface-2)); }
.kpi-icon-badge .icon { color: var(--badge-color, var(--text-muted)); }
.kpi-value { font-family: var(--font-mono); font-size: 22px; font-weight: 600; }
.kpi-label { font-size: 10.5px; color: var(--text-muted); margin-top: 3px; text-transform: uppercase; letter-spacing: 0.05em; }
.kpi-link { position: relative; display: flex; flex-direction: column; justify-content: flex-start; width: 100%; text-align: left; cursor: pointer;
  transition: transform .15s ease, border-color .15s ease; }
.kpi-link:hover { transform: translateY(-2px); border-color: var(--teal); }
.kpi-link-arrow { position: absolute; top: 14px; right: 14px; color: var(--text-faint); transition: color .15s ease, transform .15s ease; }
.kpi-link:hover .kpi-link-arrow, .kpi-link:focus-visible .kpi-link-arrow { color: var(--teal); transform: translateY(2px); }
#dq-section, #columns-section, #sensitive-panel { scroll-margin-top: 76px; }
@keyframes flash { from { box-shadow: 0 0 0 3px var(--teal); } to { box-shadow: 0 0 0 3px transparent; } }
.flash { animation: flash 1.4s ease-out; border-radius: var(--radius); }
.kpi-sub { font-size: 11.5px; color: var(--text-faint); margin-top: 2px; }
.kpi-bar { margin-top: 10px; height: 4px; background: var(--surface-2); border-radius: 2px; overflow: hidden; }
.kpi-bar span { display: block; height: 100%; border-radius: 2px; transition: width 0.6s ease; }

.alert-list { display: flex; flex-direction: column; gap: 1px; background: var(--border); border-radius: var(--radius-sm); overflow: hidden; }
.alert-row { background: var(--surface); padding: 10px 12px; display: flex; gap: 10px; align-items: flex-start; border-left: 3px solid var(--sev-color, var(--border)); }
.alert-glyph { color: var(--sev-color, var(--text-muted)); font-size: 12px; margin-top: 2px; flex-shrink: 0; }
.alert-msg { font-size: 13.5px; color: var(--text); }
.alert-col { font-family: var(--font-mono); color: var(--text); font-weight: 600; }
.alert-col-link { font-family: var(--font-mono); font-weight: 600; color: var(--teal); background: none; border: none; padding: 0; cursor: pointer; font-size: inherit; }
.alert-col-link:hover { text-decoration: underline; }
.dq-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0; }
.dq-scope { min-width: 0; padding: 4px 0; }
.dq-scope + .dq-scope { border-left: 1px solid var(--border); padding-left: 22px; margin-left: 22px; }
@media (max-width: 880px) {
  .dq-grid { grid-template-columns: 1fr; }
  .dq-scope + .dq-scope { border-left: none; margin-left: 0; padding-left: 0; border-top: 1px solid var(--border); margin-top: 18px; padding-top: 18px; }
}
.dq-scope-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.scope-tag { display: inline-flex; align-items: center; gap: 6px; font-family: var(--font-mono); font-size: 11.5px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.07em; color: var(--text); background: var(--surface-2); border: 1px solid var(--border);
  padding: 4px 10px 4px 8px; border-radius: 999px; }
.scope-tag .icon { color: var(--teal); }
.scope-desc { font-size: 12.5px; color: var(--text-muted); }
.dq-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 16px; }
.dq-tiles .kpi-card { box-shadow: none; }
.dq-alerts-head { font-family: var(--font-mono); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted);
  font-weight: 600; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
.dq-alerts-head .count { color: var(--text-faint); font-weight: 400; }
.alert-empty, .empty-state { color: var(--text-faint); font-size: 13px; padding: 6px 0; }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.two-col > * { min-width: 0; }  /* let wide heatmaps scroll inside their panel instead of widening the page */
@media (max-width: 880px) { .two-col { grid-template-columns: 1fr; } }

.dist-row { display: grid; grid-template-columns: 150px 1fr 40px; align-items: center; gap: 10px; padding: 5px 0; font-size: 12.5px; }
.dist-label { color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dist-bar-track { height: 8px; background: var(--surface-2); border-radius: 4px; overflow: hidden; }
.dist-bar-fill { display: block; height: 100%; border-radius: 4px; transition: width 0.6s ease; }
.dist-count { font-family: var(--font-mono); text-align: right; color: var(--text-muted); }

.heatmap-scroll { overflow-x: auto; }
table.heatmap { border-collapse: separate; border-spacing: 3px; font-family: var(--font-mono); font-size: 10.5px; }
table.heatmap th, table.heatmap td { text-align: center; white-space: nowrap; }
table.heatmap th { padding: 4px 6px; }
.heat-row-head, .heat-col-head { color: var(--text-muted); font-weight: 500; }
.heat-cell { border-radius: 4px; cursor: default; width: 42px; height: 42px; min-width: 42px; max-width: 42px; padding: 0; }

.pk-row { display: flex; gap: 10px; align-items: center; padding: 6px 0; font-size: 13px; }
.pk-type { font-family: var(--font-mono); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--teal); background: var(--teal-soft); padding: 2px 7px; border-radius: 4px; }
.pk-cols { font-family: var(--font-mono); color: var(--text); }
.fd-row { display: flex; gap: 10px; align-items: center; padding: 7px 0; font-size: 13px; border-top: 1px solid var(--border); }
.fd-row:first-child { border-top: none; }
.fd-expr { font-family: var(--font-mono); color: var(--text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fd-expr b { color: var(--text); font-weight: 600; }
.fd-arrow { color: var(--text-muted); }
.fd-purity { font-family: var(--font-mono); font-size: 10.5px; padding: 2px 7px; border-radius: 4px; white-space: nowrap; }
.fd-purity-exact { color: var(--teal); background: var(--teal-soft); }
.fd-purity-partial { color: var(--amber); background: var(--amber-soft); }
.fd-support { color: var(--text-muted); font-size: 11.5px; white-space: nowrap; }

.ri-row { padding: 9px 0; border-top: 1px solid var(--border); font-size: 13px; }
.ri-row:first-child { border-top: none; }
.ri-head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.ri-expr { font-family: var(--font-mono); flex: 1 1 220px; min-width: 0; overflow-wrap: anywhere; }
.ri-expr .alert-col-link { font-size: 13px; }
.ri-tag { font-family: var(--font-mono); font-size: 10.5px; padding: 2px 7px; border-radius: 4px; white-space: nowrap;
  color: var(--text-muted); background: var(--surface-2); text-transform: uppercase; letter-spacing: 0.04em; }
.ri-status { font-family: var(--font-mono); font-size: 11px; padding: 2px 8px; border-radius: 4px; white-space: nowrap;
  color: var(--sev-color); background: var(--sev-bg); display: inline-flex; align-items: center; gap: 4px; }
.ri-detail { color: var(--text-muted); font-size: 12px; margin-top: 4px; }
.ri-detail code { font-family: var(--font-mono); color: var(--text); }
.sens-intro { font-size: 13px; color: var(--text-muted); margin-bottom: 12px; max-width: 900px; }
.sens-intro b { color: var(--text); font-weight: 500; }
.sens-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.sens-table th { text-align: left; font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--text-faint); padding: 6px 12px 6px 0; }
.sens-table td { padding: 8px 12px 8px 0; border-top: 1px solid var(--border); vertical-align: top; }
.sens-kind { font-family: var(--font-mono); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap;
  color: var(--violet); background: var(--violet-soft); padding: 2px 7px; border-radius: 4px; }
.sens-why { color: var(--text-muted); }
.sens-conf { font-family: var(--font-mono); white-space: nowrap; }
.sens-conf .panel-sub { display: block; font-family: var(--font-sans); }
.detail-why { font-size: 13px; color: var(--text-muted); margin-top: 6px; max-width: 640px; }
.detail-why b { color: var(--violet); font-weight: 500; }
.run-strip { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: -6px 0 22px; padding: 10px 14px;
  background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--amber); border-radius: var(--radius-sm); font-size: 13px; }
.run-strip a { color: var(--teal); font-weight: 500; text-decoration: none; }
.run-strip a:hover { text-decoration: underline; }
#run-section { scroll-margin-top: 76px; }
.run-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.run-table td { padding: 8px 10px 8px 0; border-top: 1px solid var(--border); vertical-align: top; }
.run-table tr:first-child td { border-top: none; }
.run-name { font-weight: 500; white-space: nowrap; }
.run-detail { color: var(--text-muted); }
.run-flags code, .set-flag { font-family: var(--font-mono); font-size: 11.5px; background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 4px; padding: 1px 6px; color: var(--text); white-space: nowrap; }
.run-hint { color: var(--text-faint); font-size: 12px; }
.run-hint, .set-help, .ri-detail { font-variant-ligatures: none; }
.run-status { font-family: var(--font-mono); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.04em; padding: 2px 7px;
  border-radius: 4px; white-space: nowrap; color: var(--sev-color); background: var(--sev-bg); display: inline-flex; align-items: center; gap: 4px; }
.run-cmd { margin-top: 18px; }
.run-cmd-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 6px;
  font-family: var(--font-mono); font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); }
.run-cmd .code-block { white-space: pre-wrap; overflow-wrap: anywhere; }
.run-cmd-note { font-size: 12px; color: var(--text-faint); margin-top: 4px; }
details.settings { margin-top: 18px; }
details.settings summary { cursor: pointer; font-family: var(--font-mono); font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); }
.set-group { font-family: var(--font-mono); font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-faint); padding-top: 14px !important; }
.set-row td { padding: 6px 10px 6px 0; border-top: 1px solid var(--border); vertical-align: top; font-size: 12.5px; }
.set-val { font-family: var(--font-mono); white-space: nowrap; }
.set-changed .set-val { color: var(--teal); font-weight: 600; }
.set-help { color: var(--text-muted); }
.set-engine { font-size: 11px; color: var(--text-faint); white-space: nowrap; }
@media (max-width: 640px) {
  .run-table, .run-table tbody, .run-table tr, .run-table td { display: block; }
  .run-table tr { border-top: 1px solid var(--border); padding: 8px 0; }
  .run-table tr:first-child { border-top: none; }
  .run-table td, .set-row td { border-top: none; padding: 2px 0; }
  .run-name { white-space: normal; }
  .run-flags code, .set-flag { white-space: normal; overflow-wrap: anywhere; }
  .set-engine, .set-default { display: none; }
  .topbar-meta { flex-wrap: wrap; min-width: 0; }
  #source-name { overflow-wrap: anywhere; }
}
.columns-header { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
.columns-title { font-family: var(--font-mono); font-size: 13px; text-transform: uppercase; letter-spacing: 0.09em; color: var(--text-muted); font-weight: 600; }
.column-count { font-size: 12px; color: var(--text-faint); font-family: var(--font-mono); }
.columns-toolbar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 16px; }
.search-input { flex: 1 1 220px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 9px 12px; font-size: 13.5px; }
.search-input::placeholder { color: var(--text-faint); }
.sort-select { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 9px 10px; font-size: 13px; }
.filter-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.chip { background: var(--surface); border: 1px solid var(--border); border-radius: 999px; padding: 6px 12px; font-size: 12px; color: var(--text-muted); cursor: pointer; display: flex; align-items: center; gap: 6px; transition: border-color .15s ease, color .15s ease, background .15s ease; }
.chip:hover { border-color: var(--text-faint); color: var(--text); }
.chip.active { border-color: var(--teal); color: var(--teal); background: var(--teal-soft); }
.chip-sensitive.active { border-color: var(--violet); color: var(--violet); background: var(--violet-soft); }
.chip-count { font-family: var(--font-mono); opacity: 0.75; }

.column-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(228px, 1fr)); gap: 14px; }
.col-card { display: block; width: 100%; text-align: left; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 14px 12px; cursor: pointer; transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease; animation: rise 0.4s ease both; animation-delay: calc(var(--i, 0) * 25ms); }
.col-card:hover { transform: translateY(-2px); border-color: var(--teal); box-shadow: var(--shadow); }
.col-card-head { display: flex; align-items: center; gap: 7px; margin-bottom: 3px; }
.col-glyph { font-size: 13px; flex-shrink: 0; }
.col-glyph.large { font-size: 26px; }
.col-name { font-family: var(--font-mono); font-weight: 600; font-size: 13.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.sens-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--violet); flex-shrink: 0; box-shadow: 0 0 0 3px var(--violet-soft); }
.col-type-label { font-size: 11px; color: var(--text-faint); margin-bottom: 10px; }
.col-card-caption { font-size: 11px; color: var(--text-muted); font-family: var(--font-mono); margin-top: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.col-card-foot { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-faint); margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }
.col-card-foot b { color: var(--text-muted); font-family: var(--font-mono); font-weight: 600; }

.bars { display: flex; align-items: flex-end; gap: 2px; }
.bars-sm { height: 46px; }
.bars-lg { height: 190px; gap: 3px; }
.bar-el { flex: 1; background: var(--teal); border-radius: 2px 2px 0 0; min-width: 2px; transition: opacity .15s ease; }
.bar-el:hover { opacity: 0.7; }
.bars-empty { height: 46px; display: flex; align-items: center; justify-content: center; color: var(--text-faint); font-size: 10.5px; font-family: var(--font-mono); }

.back-btn { background: none; border: 1px solid var(--border); color: var(--text-muted); border-radius: var(--radius-sm); padding: 8px 14px; font-size: 13px; cursor: pointer; margin-bottom: 20px; font-family: var(--font-mono); transition: border-color .15s ease, color .15s ease; }
.back-btn:hover { border-color: var(--teal); color: var(--teal); }

.detail-header { margin-bottom: 20px; }
.detail-title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.detail-name { font-family: var(--font-mono); font-size: 25px; font-weight: 600; overflow-wrap: anywhere; }
.detail-badges { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.badge { font-family: var(--font-mono); font-size: 11px; padding: 4px 10px; border-radius: 999px; border: none; background: var(--badge-bg, var(--surface-2)); color: var(--badge-color, var(--text-muted)); text-transform: uppercase; letter-spacing: 0.03em; }
.detail-note { font-size: 13px; color: var(--text-muted); max-width: 640px; }

.stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; margin-bottom: 22px; }
.stat-cell { background: var(--surface); padding: 12px 14px; }
.stat-label { font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-faint); margin-bottom: 4px; }
.stat-value { font-family: var(--font-mono); font-size: 15px; font-weight: 600; }

.detail-block { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 18px; margin-bottom: 20px; }
.ruler-heading { font-family: var(--font-mono); font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between; }

.ruler-track { position: relative; height: 74px; margin: 0 10px; }
.ruler-baseline { position: absolute; top: 50%; left: 0; right: 0; height: 1px; background: var(--border); }
.ruler-band { position: absolute; top: calc(50% - 4px); height: 8px; background: var(--teal-soft); border-radius: 4px; }
.ruler-mark { position: absolute; top: 0; bottom: 0; transform: translateX(-50%); }
.ruler-mark-line { position: absolute; top: 50%; width: 1px; height: 14px; background: var(--text-faint); transform: translateY(-50%) translateX(-50%); left: 50%; }
.ruler-mark-line.strong { width: 2px; height: 20px; background: var(--teal); }
.ruler-mark-line.end { height: 22px; background: var(--text-muted); }
.ruler-mark-label { position: absolute; left: 50%; transform: translateX(-50%); font-family: var(--font-mono); font-size: 10.5px; color: var(--text-muted); white-space: nowrap; }
.ruler-mark-label.above { bottom: calc(50% + 14px); }
.ruler-mark-label.above.strong { color: var(--teal); font-weight: 600; bottom: calc(50% + 20px); }
.ruler-mark-label.below { top: calc(50% + 16px); }

.detail-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
@media (max-width: 780px) { .detail-two-col { grid-template-columns: 1fr; } }
.tv-list, .rule-list { display: flex; flex-direction: column; gap: 8px; }
.tv-row { display: grid; grid-template-columns: 1fr 90px 52px; align-items: center; gap: 8px; font-size: 12.5px; }
.tv-label { font-family: var(--font-mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tv-bar-track { height: 7px; background: var(--surface-2); border-radius: 4px; overflow: hidden; }
.tv-bar-fill { display: block; height: 100%; background: var(--teal); border-radius: 4px; }
.tv-pct { font-family: var(--font-mono); text-align: right; color: var(--text-muted); }

.rule-row { display: flex; gap: 9px; align-items: flex-start; padding: 8px 10px; background: var(--surface-2); border-left: 3px solid var(--sev-color, var(--border)); border-radius: 4px; }
.rule-glyph { color: var(--sev-color, var(--text-muted)); font-size: 11px; margin-top: 2px; }
.rule-desc { font-size: 12.5px; color: var(--text); }

.copy-btn { background: var(--surface-2); border: 1px solid var(--border); color: var(--text-muted); border-radius: var(--radius-sm); padding: 4px 10px; font-size: 11px; cursor: pointer; text-transform: none; letter-spacing: 0; font-family: var(--font-sans); }
.copy-btn:hover { border-color: var(--teal); color: var(--teal); }
.code-block { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 14px 16px; overflow-x: auto; font-family: var(--font-mono); font-size: 12.5px; line-height: 1.6; margin: 0; }

.tooltip { position: fixed; display: none; z-index: 1000; background: #3c4043; border: none; color: #ffffff; font-family: var(--font-mono); font-size: 11.5px; padding: 6px 10px; border-radius: 5px; pointer-events: none; box-shadow: 0 2px 6px rgba(0,0,0,0.25); max-width: 240px; line-height: 1.45; }

.footer { max-width: 1240px; margin: 0 auto; padding: 0 24px 40px; text-align: center; color: var(--text-faint); font-size: 12px; }

@media (max-width: 640px) {
  main { padding: 18px 14px 60px; }
  .topbar-inner { padding: 12px 16px; }
  .detail-name { font-size: 20px; }
  .dist-row { grid-template-columns: 110px 1fr 34px; }
}
.search-wrap { position: relative; flex: 1 1 220px; display: flex; align-items: center; }
.search-wrap > .icon { position: absolute; left: 10px; color: var(--text-faint); pointer-events: none; }
.search-wrap .search-input { flex: 1 1 auto; padding-left: 34px; }
.toolbar-label { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text-faint); margin-right: -2px; }
.stat-cell-head { display: flex; align-items: center; gap: 5px; margin-bottom: 4px; }
.stat-cell-head .icon { color: var(--text-faint); }
.sens-icon { color: var(--violet); flex-shrink: 0; }
.col-card-foot span { display: inline-flex; align-items: center; gap: 3px; }
.col-card-foot .icon { color: var(--text-faint); }
.brand-mark.icon { font-size: 20px; }
.back-btn { display: inline-flex; align-items: center; gap: 6px; }
.copy-btn { display: inline-flex; align-items: center; gap: 4px; }
.panel-title .icon, .ruler-heading .icon { color: var(--text-faint); }
.dbt-heading-row { display: flex; align-items: center; justify-content: space-between; }
</style>
</head>
<body>
<div id="tooltip" class="tooltip" role="tooltip"></div>

<header class="topbar">
  <div class="topbar-inner">
    <div class="brand"><span class="material-symbols-outlined brand-mark icon">dataset</span><span class="brand-text">DATA PROFILE</span></div>
    <div class="topbar-meta"><span id="source-name"></span><span class="dot">&middot;</span><span class="material-symbols-outlined icon icon-sm">schedule</span><span id="generated-at"></span></div>
  </div>
</header>

<main id="view-dashboard" class="view">
  <section class="kpi-grid" id="kpi-grid">
  </section>
  <div class="run-strip" id="run-strip" hidden></div>

  <section class="panel" id="dq-section">
    <div class="panel-title"><span class="material-symbols-outlined icon">fact_check</span>Data quality</div>
    <div class="dq-grid">
      <div class="dq-scope" id="dq-table"></div>
      <div class="dq-scope" id="dq-column"></div>
    </div>
  </section>

  <section class="panel" id="sensitive-panel" hidden>
    <div class="panel-title"><span class="material-symbols-outlined icon">shield_person</span>Personal &amp; sensitive data <span class="panel-sub">columns that look like they identify people, or hold health or payment data</span></div>
    <div id="sensitive-body"></div>
  </section>

  <section class="two-col">
    <div class="panel">
      <div class="panel-title"><span class="material-symbols-outlined icon">category</span>Type distribution</div>
      <div id="type-dist-bars"></div>
    </div>
    <div class="panel">
      <div class="panel-title"><span class="material-symbols-outlined icon">scatter_plot</span>Correlation <span class="panel-sub">Pearson &middot; numeric columns</span></div>
      <div id="corr-heatmap" class="heatmap-scroll"></div>
    </div>
  </section>

  <section class="panel" id="missing-corr-section" style="display:none">
    <div class="panel-title"><span class="material-symbols-outlined icon">link</span>Missing-value correlation <span class="panel-sub">columns that tend to be null together</span></div>
    <div id="missing-corr-heatmap" class="heatmap-scroll"></div>
  </section>

  <section class="panel" id="pk-panel" style="display:none">
    <div class="panel-title"><span class="material-symbols-outlined icon">key</span>Primary-key candidates</div>
    <div id="pk-list"></div>
  </section>

  <section class="panel" id="fd-panel" style="display:none">
    <div class="panel-title"><span class="material-symbols-outlined icon">account_tree</span>Column relationship dependencies <span class="panel-sub">one column&rsquo;s value determines another&rsquo;s</span></div>
    <p class="sens-intro"><b>A &rarr; B</b> means every row with the same value of A has the same value of B, like zip code &rarr; state. That can point to a redundant column (B could be looked up from A), an undocumented business rule, or, when it holds for almost all rows, the few rows that break the rule and are worth checking.</p>
    <div id="fd-list"></div>
  </section>

  <section class="panel" id="ri-panel" style="display:none">
    <div class="panel-title"><span class="material-symbols-outlined icon">conversion_path</span>Referential integrity <span class="panel-sub">do referenced values exist in their key column?</span></div>
    <div id="ri-list"></div>
  </section>

  <section class="columns-section" id="columns-section">
    <div class="columns-header">
      <div class="columns-title"><span class="material-symbols-outlined icon">table_view</span>Columns</div>
      <div class="column-count" id="column-count"></div>
    </div>
    <div class="columns-toolbar">
      <div class="search-wrap">
        <span class="material-symbols-outlined icon">search</span>
        <input type="text" id="search-input" class="search-input" placeholder="Search columns&hellip;" aria-label="Search columns">
      </div>
      <span class="toolbar-label"><span class="material-symbols-outlined icon icon-sm">tune</span>Filter</span>
      <div class="filter-chips" id="filter-chips"></div>
      <span class="toolbar-label"><span class="material-symbols-outlined icon icon-sm">sort</span></span>
      <select id="sort-select" class="sort-select" aria-label="Sort columns">
        <option value="name">Sort: name</option>
        <option value="missing">Sort: missing %</option>
        <option value="unique">Sort: unique %</option>
      </select>
    </div>
    <div id="column-grid" class="column-grid"></div>
  </section>

  <section class="panel" id="run-section" hidden>
    <div class="panel-title"><span class="material-symbols-outlined icon">fact_check</span>Run summary <span class="panel-sub">what was checked, what wasn't, and how to repeat or extend this run</span></div>
    <div id="run-body"></div>
  </section>
</main>

<main id="view-detail" class="view" hidden>
  <button id="back-btn" class="back-btn"><span class="material-symbols-outlined icon">arrow_back</span>Dashboard</button>
  <div id="detail-content"></div>
</main>

<footer class="footer"><span class="material-symbols-outlined icon icon-sm" style="vertical-align:-2px">lock</span> Values in columns that look like personal or sensitive data are masked throughout. Type and quality-rule suggestions are heuristic &mdash; verify before enforcing.</footer>

<script>
const PROFILE = __PROFILE_DATA_JSON__;

function esc(s) { const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; }
function fmtInt(n) { if (n === null || n === undefined) return '\u2014'; return Number(n).toLocaleString('en-US'); }
function fmtPct(n, digits) { if (n === null || n === undefined) return '\u2014'; return Number(n).toFixed(digits === undefined ? 1 : digits) + '%'; }
function fmtNum(n) { if (n === null || n === undefined) return '\u2014'; if (Number.isInteger(n)) return fmtInt(n); return Number(n).toLocaleString('en-US', {maximumFractionDigits: 3}); }
function fmtBytes(n) {
  if (n === null || n === undefined) return '\u2014';
  if (n < 1024) return n + ' B';
  const units = ['KB', 'MB', 'GB', 'TB', 'PB'];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < units.length - 1);
  return n.toFixed(i === 0 ? 1 : 2) + ' ' + units[i];
}
function titleCase(s) { return String(s).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()); }

const TYPE_COLOR = {
  identifier: 'var(--teal)', continuous_numeric: 'var(--teal)',
  discrete_numeric_categorical: 'var(--amber)', categorical: 'var(--amber)', binary_categorical: 'var(--amber)',
  boolean: 'var(--green)',
  datetime: 'var(--text-muted)', datetime_string: 'var(--text-muted)', free_text: 'var(--text-muted)', high_cardinality_text: 'var(--text-muted)',
  constant: 'var(--text-faint)', empty: 'var(--text-faint)', unknown: 'var(--text-faint)',
};
const TYPE_ICON = {
  identifier: 'vpn_key', continuous_numeric: 'monitoring', discrete_numeric_categorical: 'numbers',
  categorical: 'sell', binary_categorical: 'toggle_on', boolean: 'toggle_on',
  datetime: 'calendar_month', datetime_string: 'calendar_month', free_text: 'description', high_cardinality_text: 'notes',
  constant: 'block', empty: 'inbox', unknown: 'help',
};
const SEVERITY_COLOR = { high: 'var(--coral)', warning: 'var(--amber)', info: 'var(--teal)', sensitive: 'var(--violet)', suggested: 'var(--green)' };
const SEVERITY_ICON = { high: 'error', warning: 'warning', info: 'info', sensitive: 'shield', suggested: 'check_circle' };
const SOFT_BG = { 'var(--teal)': 'var(--teal-soft)', 'var(--amber)': 'var(--amber-soft)', 'var(--coral)': 'var(--coral-soft)', 'var(--violet)': 'var(--violet-soft)', 'var(--green)': 'var(--green-soft)' };
function softBg(colorVar) { return SOFT_BG[colorVar] || 'var(--surface-2)'; }
function icon(name, size, extraStyle, filled) {
  const cls = 'material-symbols-outlined icon' + (size ? ' icon-' + size : '') + (filled ? ' icon-fill' : '');
  return '<span class="' + cls + '"' + (extraStyle ? ' style="' + extraStyle + '"' : '') + ' aria-hidden="true">' + name + '</span>';
}



const tooltipEl = document.getElementById('tooltip');
function showTooltip(evt, html) { tooltipEl.innerHTML = html; tooltipEl.style.display = 'block'; positionTooltip(evt); }
function positionTooltip(evt) {
  const pad = 14;
  let x = evt.clientX + pad, y = evt.clientY + pad;
  const rect = tooltipEl.getBoundingClientRect();
  if (x + rect.width > window.innerWidth) x = evt.clientX - rect.width - pad;
  if (y + rect.height > window.innerHeight) y = evt.clientY - rect.height - pad;
  tooltipEl.style.left = x + 'px'; tooltipEl.style.top = y + 'px';
}
function hideTooltip() { tooltipEl.style.display = 'none'; }
function wireTooltips(root) {
  root.querySelectorAll('[data-tip]').forEach(elx => {
    elx.addEventListener('mouseenter', e => showTooltip(e, elx.getAttribute('data-tip')));
    elx.addEventListener('mousemove', positionTooltip);
    elx.addEventListener('mouseleave', hideTooltip);
  });
}

function getChartSpec(col) {
  if (col.numeric_stats && col.histogram && col.histogram.counts && col.histogram.counts.length) return {type: 'histogram', hist: col.histogram};
  if (col.boolean_stats) return {type: 'boolean', stats: col.boolean_stats};
  if ((col.semantic_type === 'datetime' || col.semantic_type === 'datetime_string') && col.datetime_stats && col.datetime_stats.weekday_distribution) return {type: 'weekday', dist: col.datetime_stats.weekday_distribution};
  if (['categorical','binary_categorical','discrete_numeric_categorical'].indexOf(col.semantic_type) !== -1 && col.top_values && col.top_values.length) return {type: 'topvalues', values: col.top_values};
  if (col.string_stats && col.length_histogram && col.length_histogram.counts && col.length_histogram.counts.length) return {type: 'length', hist: col.length_histogram};
  if (col.top_values && col.top_values.length) return {type: 'topvalues', values: col.top_values};
  return {type: 'none'};
}

function chartCaption(col, spec) {
  if (spec.type === 'histogram' && col.numeric_stats) return fmtNum(col.numeric_stats.min) + ' \u2013 ' + fmtNum(col.numeric_stats.max);
  if (spec.type === 'length' && col.string_stats) return 'avg length ' + fmtNum(col.string_stats.mean_length) + ' chars';
  if (spec.type === 'topvalues' && col.top_values.length) return 'top: ' + col.top_values[0].value + ' (' + fmtPct(col.top_values[0].pct) + ')';
  if (spec.type === 'weekday' && col.datetime_stats) return (col.datetime_stats.min_date||'').slice(0,10) + ' \u2192 ' + (col.datetime_stats.max_date||'').slice(0,10);
  if (spec.type === 'boolean' && col.boolean_stats) return fmtPct(col.boolean_stats.true_pct) + ' true';
  return '';
}

function renderBars(spec, size) {
  const cls = size === 'lg' ? 'bars-lg' : 'bars-sm';
  if (spec.type === 'histogram' || spec.type === 'length') {
    const counts = spec.hist.counts, edges = spec.hist.edges;
    const max = Math.max(...counts, 1);
    const bars = counts.map((c,i) => {
      const tip = fmtNum(edges[i]) + '\u2013' + fmtNum(edges[i+1]) + '<br>' + fmtInt(c) + ' rows';
      return '<span class="bar-el" style="height:' + Math.max(4, c/max*100) + '%" data-tip="' + esc(tip) + '"></span>';
    }).join('');
    return '<div class="bars ' + cls + '">' + bars + '</div>';
  }
  if (spec.type === 'topvalues') {
    const vals = spec.values.slice(0, size === 'lg' ? 12 : 7);
    const max = Math.max(...vals.map(v => v.count), 1);
    const bars = vals.map(v => {
      const tip = esc(v.value) + '<br>' + fmtInt(v.count) + ' (' + fmtPct(v.pct) + ')';
      return '<span class="bar-el" style="height:' + Math.max(4, v.count/max*100) + '%" data-tip="' + tip + '"></span>';
    }).join('');
    return '<div class="bars ' + cls + '">' + bars + '</div>';
  }
  if (spec.type === 'weekday') {
    const order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
    const max = Math.max(...order.map(d => spec.dist[d]||0), 1);
    const bars = order.map(d => {
      const c = spec.dist[d]||0;
      const tip = d + '<br>' + fmtInt(c);
      return '<span class="bar-el" style="height:' + Math.max(4, c/max*100) + '%" data-tip="' + esc(tip) + '"></span>';
    }).join('');
    return '<div class="bars ' + cls + '">' + bars + '</div>';
  }
  if (spec.type === 'boolean') {
    const t = spec.stats.true_pct, f = 100 - t;
    return '<div class="bars ' + cls + '">' +
      '<span class="bar-el" style="height:' + Math.max(4,t) + '%; background:var(--green)" data-tip="True<br>' + fmtPct(t) + '"></span>' +
      '<span class="bar-el" style="height:' + Math.max(4,f) + '%; background:var(--coral)" data-tip="False<br>' + fmtPct(f) + '"></span>' +
      '</div>';
  }
  return '<div class="bars-empty">no distribution</div>';
}

function renderHeader() {
  document.getElementById('source-name').textContent = PROFILE.meta.source_name;
  const d = new Date(PROFILE.meta.generated_at);
  document.getElementById('generated-at').textContent = isNaN(d.getTime()) ? PROFILE.meta.generated_at : d.toLocaleString();
  document.title = 'Data Profile \u2014 ' + PROFILE.meta.source_name;
}

// One KPI tile. `t.link` names a KPI_LINKS entry; tiles with nothing to
// drill into stay static rather than linking somewhere that doesn't
// explain the number.
function kpiTile(t, i) {
  const link = t.link && KPI_LINKS[t.link];
  const inner =
    '<div class="kpi-icon-badge" style="--badge-color:' + t.color + ';--badge-bg:' + softBg(t.color) + '">' + icon(t.iconName, 'xl', null, true) + '</div>' +
    '<div class="kpi-value">' + esc(t.value) + '</div>' +
    '<div class="kpi-label">' + esc(t.label) + '</div>' +
    (t.sub ? '<div class="kpi-sub">' + esc(t.sub) + '</div>' : '') +
    (t.bar !== undefined ? '<div class="kpi-bar"><span style="width:' + t.bar + '%; background:' + t.barColor + '"></span></div>' : '');
  if (!link) return '<div class="kpi-card" style="--i:' + (i+1) + '">' + inner + '</div>';
  return '<button type="button" class="kpi-card kpi-link" style="--i:' + (i+1) + '" data-kpi-link="' + t.link + '" title="' + esc(link.hint) + '">' +
    '<span class="kpi-link-arrow">' + icon('arrow_downward', 'sm') + '</span>' + inner + '</button>';
}
function wireKpiLinks(root) {
  root.querySelectorAll('[data-kpi-link]').forEach(btn => btn.addEventListener('click', () => KPI_LINKS[btn.dataset.kpiLink].go()));
}

function renderHero() {
  const m = PROFILE.meta, o = PROFILE.overview;
  const nCols = (PROFILE.columns || []).length;
  const tiles = [
    {label: 'Rows', value: fmtInt(m.n_rows), iconName: 'table_rows', color: 'var(--teal)'},
    {label: 'Columns', value: fmtInt(m.n_cols), iconName: 'view_column', color: 'var(--teal)', link: nCols > 0 ? 'columns' : null},
    {label: 'Personal & sensitive columns', value: fmtInt(o.sensitive_columns_count), iconName: 'shield_person', color: o.sensitive_columns_count > 0 ? 'var(--violet)' : 'var(--text-faint)', link: 'sensitive'},
    {label: m.engine === 'bigquery' ? 'Storage' : 'Memory', value: (m.memory_mb === null || m.memory_mb === undefined) ? '—' : m.memory_mb + ' MB', iconName: 'memory', color: 'var(--text-muted)'},
  ];
  const grid = document.getElementById('kpi-grid');
  grid.innerHTML = tiles.map(kpiTile).join('');
  wireKpiLinks(grid);
}

const SEVERITY_ORDER = {high:0, sensitive:1, warning:2, info:3};
function sortAlerts(alerts) {
  const rank = a => SEVERITY_ORDER[a.severity] === undefined ? 9 : SEVERITY_ORDER[a.severity];
  return alerts.slice().sort((a,b) => rank(a) - rank(b));
}
function alertRows(alerts, emptyMsg) {
  if (!alerts.length) return '<div class="alert-empty">' + icon('check_circle','sm') + ' ' + esc(emptyMsg) + '</div>';
  return '<div class="alert-list">' + sortAlerts(alerts).map(a =>
    '<div class="alert-row" style="--sev-color:' + (SEVERITY_COLOR[a.severity] || 'var(--border)') + '">' +
      '<span class="alert-glyph">' + icon(SEVERITY_ICON[a.severity] || 'info', 'sm') + '</span>' +
      '<span class="alert-msg">' + (a.column ? '<button type="button" class="alert-col-link" data-open-col="' + esc(a.column) + '" title="Open column details">' + esc(a.column) + '</button> — ' : '') + esc(a.message) + '</span>' +
    '</div>').join('') + '</div>';
}
function scopeBlock(tagIcon, tagLabel, desc, tiles, alerts, emptyMsg) {
  return '<div class="dq-scope-head"><span class="scope-tag">' + icon(tagIcon, 'sm') + esc(tagLabel) + '</span><span class="scope-desc">' + esc(desc) + '</span></div>' +
    '<div class="dq-tiles">' + tiles.map(kpiTile).join('') + '</div>' +
    '<div class="dq-alerts-head">' + icon('warning', 'sm') + 'Alerts <span class="count">' + alerts.length + '</span></div>' +
    alertRows(alerts, emptyMsg);
}

// Table-level vs column-level is decided by the alert itself: alerts tied
// to one column carry its name, everything else (duplicate rows, identical
// column pairs, correlations, dependencies, skipped columns) has none.
function renderQuality() {
  const m = PROFILE.meta, o = PROFILE.overview, cols = PROFILE.columns || [];
  const alerts = o.alerts || [];
  const tableAlerts = alerts.filter(a => !a.column);
  const columnAlerts = alerts.filter(a => a.column);

  const completeness = Math.max(0, 100 - o.total_missing_pct);
  const completenessColor = completeness > 90 ? 'var(--green)' : completeness > 70 ? 'var(--amber)' : 'var(--coral)';
  const totalCells = (m.n_rows || 0) * cols.length;
  const dupMeasured = m.duplicate_rows !== null && m.duplicate_rows !== undefined;
  const tableTiles = [
    {label: 'Completeness', value: cols.length ? fmtPct(completeness) : '—', sub: totalCells ? fmtInt(totalCells - o.total_missing_cells) + ' of ' + fmtInt(totalCells) + ' cells filled' : 'no cells',
     bar: totalCells ? completeness : undefined, barColor: completenessColor, iconName: 'task_alt', color: completenessColor},
    {label: 'Duplicate rows', value: dupMeasured ? fmtInt(m.duplicate_rows) : 'Not measured',
     sub: dupMeasured ? (m.duplicate_rows ? fmtPct(m.duplicate_rows_pct) + ' of rows are exact copies' : 'no exact copies') : 'not computed by this engine',
     iconName: 'content_copy', color: !dupMeasured ? 'var(--text-faint)' : m.duplicate_rows > 0 ? 'var(--amber)' : 'var(--green)'},
  ];

  const withMissing = cols.filter(c => c.missing > 0).length;
  const constant = cols.filter(c => c.semantic_type === 'constant').length;
  const columnTiles = [
    {label: 'Columns with missing values', value: fmtInt(withMissing) + ' / ' + fmtInt(cols.length), sub: withMissing ? 'click to sort by missing %' : cols.length ? 'every column fully populated' : 'no columns',
     iconName: 'help', color: withMissing ? 'var(--amber)' : 'var(--green)', link: withMissing ? 'missing' : null},
    {label: 'Constant columns', value: fmtInt(constant), sub: constant ? 'single distinct value' : cols.length ? 'none' : 'no columns',
     iconName: 'block', color: constant ? 'var(--amber)' : 'var(--green)', link: constant ? 'constant' : null},
  ];

  const tableEl = document.getElementById('dq-table');
  const colEl = document.getElementById('dq-column');
  tableEl.innerHTML = scopeBlock('table', 'Table level', 'The dataset as a whole and relationships between columns', tableTiles, tableAlerts, 'No table-level alerts.');
  colEl.innerHTML = scopeBlock('view_column', 'Column level', 'Individual columns — click a name for details', columnTiles, columnAlerts, 'No column-level alerts.');
  [tableEl, colEl].forEach(el => {
    wireKpiLinks(el);
    el.querySelectorAll('[data-open-col]').forEach(btn => btn.addEventListener('click', () => openDetail(btn.dataset.openCol)));
  });
}

// Each KPI link puts the target section into the view that explains the
// number, then scrolls to it.
const KPI_LINKS = {
  columns:   {hint: 'Show all columns',                 go: () => { setColumnView({}); jumpTo('columns-section'); }},
  missing:   {hint: 'Show columns sorted by missing %', go: () => { setColumnView({sort: 'missing'}); jumpTo('columns-section'); }},
  constant:  {hint: 'Show only constant columns',       go: () => { setColumnView({types: ['constant']}); jumpTo('columns-section'); }},
  sensitive: {hint: 'What was flagged, and why',         go: () => jumpTo('sensitive-panel')},
};

function setColumnView(opts) {
  state.search = '';
  document.getElementById('search-input').value = '';
  state.typeFilters = new Set(opts.types || []);
  document.querySelectorAll('[data-filter-type]').forEach(b => b.classList.toggle('active', state.typeFilters.has(b.dataset.filterType)));
  state.sensitiveOnly = !!opts.sensitiveOnly;
  const sensBtn = document.querySelector('[data-filter-sensitive]');
  if (sensBtn) { sensBtn.classList.toggle('active', state.sensitiveOnly); sensBtn.setAttribute('aria-pressed', String(state.sensitiveOnly)); }
  if (opts.sort) { state.sort = opts.sort; document.getElementById('sort-select').value = opts.sort; }
  renderColumnGrid();
}

function jumpTo(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({block: 'start'});
  el.classList.remove('flash');
  void el.offsetWidth;  // restart the animation on repeat clicks
  el.classList.add('flash');
}


function renderTypeDistribution() {
  const dist = PROFILE.overview.type_distribution || {};
  const entries = Object.entries(dist).sort((a,b) => b[1]-a[1]);
  const max = Math.max(...entries.map(e => e[1]), 1);
  const html = entries.map(([type, count]) =>
    '<div class="dist-row">' +
      '<span class="dist-label row-icon">' + icon(TYPE_ICON[type]||'help', null, 'color:' + (TYPE_COLOR[type]||'var(--text-muted)'), true) + ' ' + esc(titleCase(type)) + '</span>' +
      '<span class="dist-bar-track"><span class="dist-bar-fill" style="width:' + (count/max*100) + '%; background:' + (TYPE_COLOR[type]||'var(--text-muted)') + '"></span></span>' +
      '<span class="dist-count">' + count + '</span>' +
    '</div>'
  ).join('');
  document.getElementById('type-dist-bars').innerHTML = html || '<div class="empty-state">No columns.</div>';
}

function heatColor(t) {
  t = Math.max(-1, Math.min(1, t));
  const base = [241,243,244];
  const target = t >= 0 ? [26,115,232] : [217,48,37];
  const f = Math.abs(t);
  const mix = base.map((c,i) => Math.round(c + (target[i]-c)*f));
  return {rgb: 'rgb(' + mix.join(',') + ')', strong: f > 0.4};
}
function truncateLabel(s) { return s.length > 11 ? s.slice(0,10) + '\u2026' : s; }

function renderHeatmap(containerId, data, emptyMsg) {
  const container = document.getElementById(containerId);
  if (!data || !data.columns || data.columns.length < 2) { container.innerHTML = '<div class="empty-state">' + emptyMsg + '</div>'; return; }
  const cols = data.columns;
  let html = '<table class="heatmap"><thead><tr><th></th>' + cols.map(c => '<th class="heat-col-head" title="' + esc(c) + '">' + esc(truncateLabel(c)) + '</th>').join('') + '</tr></thead><tbody>';
  cols.forEach((rowName, i) => {
    html += '<tr><th class="heat-row-head" title="' + esc(rowName) + '">' + esc(truncateLabel(rowName)) + '</th>';
    cols.forEach((colName, j) => {
      const v = data.matrix[i][j];
      const c = heatColor(v);
      const tip = esc(rowName) + ' \u00d7 ' + esc(colName) + '<br>' + v.toFixed(2);
      html += '<td class="heat-cell" style="background:' + c.rgb + '; color:' + (c.strong ? 'var(--bg)' : 'var(--text-muted)') + '" data-tip="' + tip + '">' + v.toFixed(2) + '</td>';
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  container.innerHTML = html;
  wireTooltips(container);
}
// Why a heatmap is empty comes from the run summary's record of the check
// (turned off, nothing to correlate, ...), not a guess from missing data.
function runCheck(id) { return ((PROFILE.meta || {}).checks || []).find(c => c.id === id); }
function emptyReason(id, fallback) {
  const c = runCheck(id);
  if (!c) return fallback;
  if (c.status === 'skipped') return 'Turned off for this run. Rerun with <code>' + esc(c.flags.join(' ')) + '</code> to compute it.';
  return esc(c.detail);
}
function renderCorrelation() {
  renderHeatmap('corr-heatmap', PROFILE.correlations, emptyReason('correlations', 'Fewer than two numeric columns \u2014 nothing to correlate.'));
}
function renderMissingCorr() {
  const section = document.getElementById('missing-corr-section');
  const c = runCheck('missing_correlation');
  // Hidden when it has nothing to say (or isn't available on this engine);
  // shown with the reason when it was turned off, so its absence is explained.
  if (!PROFILE.missing_correlation && !(c && c.status === 'skipped')) { section.style.display = 'none'; return; }
  section.style.display = '';
  renderHeatmap('missing-corr-heatmap', PROFILE.missing_correlation, emptyReason('missing_correlation', 'Not enough columns with partial missingness.'));
}
function renderPkCandidates() {
  const panel = document.getElementById('pk-panel');
  const list = document.getElementById('pk-list');
  const candidates = PROFILE.pk_candidates || [];
  if (!candidates.length) { panel.style.display = 'none'; return; }
  panel.style.display = '';
  list.innerHTML = candidates.map(c => '<div class="pk-row"><span class="pk-type">' + (c.type === 'single' ? 'Single column' : 'Composite') + '</span><span class="pk-cols">' + c.columns.map(esc).join(' + ') + '</span></div>').join('');
}

function renderColumnDependencies() {
  const panel = document.getElementById('fd-panel');
  const list = document.getElementById('fd-list');
  const fds = PROFILE.column_dependencies || [];
  if (!fds.length) { panel.style.display = 'none'; return; }
  panel.style.display = '';
  list.innerHTML = fds.map(fd => {
    const exact = fd.purity >= 0.999999;
    const purityLabel = exact ? 'always' : (fd.purity * 100).toFixed(1) + '%';
    const tip = exact
      ? esc(fd.determinant) + ' determines ' + esc(fd.dependent) + ' with no exceptions across ' + fd.support_rows + ' row(s).'
      : esc(fd.determinant) + ' determines ' + esc(fd.dependent) + ' in ' + purityLabel + ' of ' + fd.support_rows + ' row(s) — ' + fd.violation_count + ' exception(s).';
    return '<div class="fd-row">' +
      '<span class="fd-expr" data-tip="' + tip + '"><b>' + esc(fd.determinant) + '</b> <span class="fd-arrow">→</span> <b>' + esc(fd.dependent) + '</b></span>' +
      '<span class="fd-support">' + fd.distinct_determinant_values + ' value(s)</span>' +
      '<span class="fd-purity ' + (exact ? 'fd-purity-exact' : 'fd-purity-partial') + '">' + purityLabel + '</span>' +
    '</div>';
  }).join('');
  wireTooltips(list);
}

function renderReferentialIntegrity() {
  const panel = document.getElementById('ri-panel');
  const list = document.getElementById('ri-list');
  const checks = (PROFILE.referential_integrity || []).slice()
    .sort((a,b) => (b.orphans > 0) - (a.orphans > 0) || (a.source === 'declared' ? -1 : 1) - (b.source === 'declared' ? -1 : 1));
  const suggestions = PROFILE.reference_suggestions || [];
  const listed = suggestions.filter(s => s.status === 'listed');
  const overLimit = suggestions.filter(s => s.status === 'over_limit').length;
  if (!checks.length && !listed.length && !overLimit) { panel.style.display = 'none'; return; }
  panel.style.display = '';
  const highPct = setting('ri_high_orphan_pct', 5);
  const listedHtml = listed.map(sg =>
    '<div class="ri-row">' +
      '<div class="ri-head">' +
        '<span class="ri-expr"><button type="button" class="alert-col-link" data-open-col="' + esc(sg.column) + '" title="Open column details">' + esc(sg.column) + '</button> <span class="fd-arrow">\u2192</span> <b>' + esc(sg.references) + '</b></span>' +
        '<span class="ri-tag">suggested</span><span class="ri-tag">same table</span>' +
        '<span class="ri-status" style="--sev-color:var(--text-muted);--sev-bg:var(--surface-2)">' + icon('schedule', 'sm') + 'not checked</span>' +
      '</div>' +
      '<div class="ri-detail">Looks like a reference from its name and data, but checking it is an extra query' +
        (sg.estimated_bytes !== null && sg.estimated_bytes !== undefined ? ' (about ' + fmtBytes(sg.estimated_bytes) + ' scanned)' : '') +
        '. Rerun with <code>--suggested-references check</code>.</div>' +
    '</div>').join('') +
    (overLimit ? '<div class="ri-row"><div class="ri-detail">' + overLimit + ' more possible reference' + (overLimit === 1 ? '' : 's') +
      ' over the limit \u2014 raise <code>--max-reference-suggestions</code> (see the run summary).</div></div>' : '');
  list.innerHTML = checks.map(r => {
    const bad = r.orphans > 0;
    const sev = !bad ? 'var(--green)' : (r.source === 'declared' && r.orphan_pct > highPct ? 'var(--coral)' : 'var(--amber)');
    const status = bad
      ? icon('link_off', 'sm') + fmtInt(r.orphans) + ' orphan row' + (r.orphans === 1 ? '' : 's') + ' \u00b7 ' + fmtPct(r.orphan_pct, r.orphan_pct < 0.1 ? 3 : 1)
      : icon('check', 'sm') + 'all matched';
    const samples = (r.sample_orphans || []).map(s => '<code>' + esc(s.value) + '</code>' + (s.count > 1 ? ' \u00d7' + fmtInt(s.count) : '')).join(', ');
    const detail = bad
      ? fmtInt(r.orphan_values) + ' value' + (r.orphan_values === 1 ? '' : 's') + ' not found in <code>' + esc(r.references) + '</code>' + (samples ? ', e.g. ' + samples : '') + (r.orphan_values > (r.sample_orphans || []).length ? ' \u2026' : '')
      : 'All ' + fmtInt(r.checked) + ' non-null values found in <code>' + esc(r.references) + '</code>.';
    const tip = r.source === 'suggested'
      ? 'Suggested from the column names and data \u2014 not declared. Verify it really is a reference.'
      : 'Declared check.';
    return '<div class="ri-row">' +
      '<div class="ri-head">' +
        '<span class="ri-expr"><button type="button" class="alert-col-link" data-open-col="' + esc(r.column) + '" title="Open column details">' + esc(r.column) + '</button> <span class="fd-arrow">\u2192</span> <b>' + esc(r.references) + '</b></span>' +
        '<span class="ri-tag" data-tip="' + esc(tip) + '">' + (r.source === 'suggested' ? 'suggested' : 'declared') + '</span>' +
        '<span class="ri-tag">' + (r.same_table ? 'same table' : 'other table') + '</span>' +
        '<span class="ri-status" style="--sev-color:' + sev + ';--sev-bg:' + softBg(sev) + '">' + status + '</span>' +
      '</div>' +
      '<div class="ri-detail">' + detail + (r.compared_as === 'text' ? ' <span class="panel-sub">(compared as text: the two columns have different types)</span>' : '') + '</div>' +
    '</div>';
  }).join('') + listedHtml;
  list.querySelectorAll('[data-open-col]').forEach(btn => btn.addEventListener('click', () => openDetail(btn.dataset.openCol)));
  wireTooltips(list);
}

// Plain-language labels; older profiles only have the PII/PHI/PCI codes.
const SENS_GROUP = {PII: 'Personal data', PHI: 'Health data', PCI: 'Payment data'};
function sensGroup(sv) { return sv.category_label || SENS_GROUP[sv.category] || sv.category || 'Sensitive data'; }
function sensType(sv) { return sv.type_label || String(sv.type || '').replace(/_/g, ' '); }
function sensLabel(sv) { return sensGroup(sv) + ': ' + sensType(sv); }

function renderSensitive() {
  const cols = (PROFILE.columns || []).filter(c => c.sensitive && c.sensitive.is_sensitive)
    .sort((a,b) => b.sensitive.confidence - a.sensitive.confidence);
  const minConf = setting('sensitive_alert_min_confidence', 0.7);
  const bq = PROFILE.meta.engine === 'bigquery';
  let html = '<p class="sens-intro">datascope checks every column\u2019s <b>name</b>' +
    (bq ? '' : ' and a <b>sample of its values</b>') + ' for <b>personal data</b> (PII: names, email addresses, phone numbers, ' +
    'postal addresses, ID numbers, dates of birth), <b>health data</b> (PHI: medical records, diagnoses, medication) and ' +
    '<b>payment data</b> (PCI: card and bank account numbers). Values in flagged columns are <b>masked everywhere in this report</b>. ' +
    'This is pattern matching to point you at columns worth a review, not a compliance decision.' +
    (bq ? ' On BigQuery only column names are checked: checking values would mean pulling them out of the warehouse.' : '') + '</p>';
  if (!cols.length) {
    html += '<div class="empty-state">' + icon('check_circle', 'sm') + ' No column looks like personal or sensitive data.</div>';
  } else {
    html += '<table class="sens-table"><thead><tr><th>Column</th><th>Kind</th><th>Looks like</th><th>Why</th><th>Confidence</th></tr></thead><tbody>' +
      cols.map(c => {
        const sv = c.sensitive;
        const alerted = sv.confidence >= minConf;
        return '<tr><td><button type="button" class="alert-col-link" data-open-col="' + esc(c.name) + '" title="Open column details">' + esc(c.name) + '</button></td>' +
          '<td><span class="sens-kind">' + esc(sensGroup(sv)) + '</span></td>' +
          '<td>' + esc(sensType(sv)) + '</td>' +
          '<td class="sens-why">' + esc((sv.reasons || []).join(' ') || ((sv.detected_by || []).join(', ').replace(/_/g, ' '))) + '</td>' +
          '<td class="sens-conf">' + Math.round(sv.confidence * 100) + '%<span class="panel-sub">' +
            (alerted ? 'alert raised' : 'below the alert threshold (' + Math.round(minConf * 100) + '%)') + '</span></td></tr>';
      }).join('') + '</tbody></table>';
  }
  const body = document.getElementById('sensitive-body');
  body.innerHTML = html;
  body.querySelectorAll('[data-open-col]').forEach(btn => btn.addEventListener('click', () => openDetail(btn.dataset.openCol)));
  document.getElementById('sensitive-panel').hidden = false;
}

const SETTINGS_DOC = __SETTINGS_DOC_JSON__;
function setting(name, fallback) {
  const s = PROFILE.meta && PROFILE.meta.settings;
  return s && s[name] !== undefined ? s[name] : fallback;
}

const RUN_STATUS = {
  ran:              {label: 'ran',            icon: 'check_circle', color: 'var(--green)'},
  nothing_to_check: {label: 'nothing to do',  icon: 'check_circle', color: 'var(--text-muted)'},
  partial:          {label: 'partial',        icon: 'contrast',     color: 'var(--amber)'},
  skipped:          {label: 'skipped',        icon: 'block',        color: 'var(--amber)'},
  listed:           {label: 'listed',         icon: 'schedule',     color: 'var(--amber)'},
  not_configured:   {label: 'not set up',     icon: 'add_circle',   color: 'var(--text-muted)'},
  not_available:    {label: 'not available',  icon: 'do_not_disturb_on', color: 'var(--text-faint)'},
};
const EXTENDABLE = ['partial', 'skipped', 'listed'];

function fmtSetting(v) { return typeof v === 'boolean' ? (v ? 'on' : 'off') : String(v); }

function cmdBlock(title, cmd, note) {
  return '<div class="run-cmd copy-scope"><div class="run-cmd-head"><span>' + esc(title) + '</span>' +
    '<button class="copy-btn" data-copy>' + icon('content_copy','sm') + 'Copy</button></div>' +
    '<pre class="code-block"><code>' + esc(cmd.text) + '</code></pre>' +
    (note ? '<div class="run-cmd-note">' + note + '</div>' : '') + '</div>';
}

function renderRunSummary() {
  const meta = PROFILE.meta || {};
  const checks = meta.checks;
  if (!checks || !checks.length) return;  // a profile from an older datascope
  const extendable = checks.filter(c => EXTENDABLE.indexOf(c.status) !== -1);
  const sm = meta.sample;
  const sampleShort = sm ? 'This report profiles a ' + fmtNum(sm.percent) + '% sample (' + fmtInt(sm.sample_rows) + ' rows) of ' +
    esc(sm.table) + (sm.table_rows !== null && sm.table_rows !== undefined ? ', which has ' + fmtInt(sm.table_rows) + ' rows' : '') + '.' : '';
  const strip = document.getElementById('run-strip');
  if (extendable.length || sm) {
    strip.hidden = false;
    strip.innerHTML = icon('info', 'sm', 'color:var(--amber)') + '<span>' + (sm ? sampleShort + ' ' : '') +
      (extendable.length ? extendable.length + ' check' + (extendable.length === 1 ? ' was' : 's were') +
        ' capped, skipped or only listed in this run: ' + extendable.map(c => esc(c.name)).join(', ') + '.' : '') + '</span>' +
      '<a href="#run-section" id="run-strip-link">' + (extendable.length ? 'See how to extend it' : 'See the full-table projection') + ' \u2193</a>';
    document.getElementById('run-strip-link').addEventListener('click', e => { e.preventDefault(); jumpTo('run-section'); });
  }

  const rows = checks.map(c => {
    const st = RUN_STATUS[c.status] || RUN_STATUS.ran;
    const action = (EXTENDABLE.indexOf(c.status) !== -1 && c.flags.length)
      ? '<span class="run-flags">' + '<code>' + esc(c.flags.join(' ')) + '</code></span>'
      : (c.hint ? '<span class="run-hint">' + esc(c.hint) + '</span>' : '');
    return '<tr><td><span class="run-status" style="--sev-color:' + st.color + ';--sev-bg:' + softBg(st.color) + '">' + icon(st.icon, 'sm') + st.label + '</span></td>' +
      '<td class="run-name">' + esc(c.name) + '</td>' +
      '<td class="run-detail-cell"><div class="run-detail">' + esc(c.detail) + '</div>' + (action ? '<div style="margin-top:4px">' + action + '</div>' : '') + '</td></tr>';
  }).join('');

  let html = '';
  if (sm) {
    const full = [];
    if (sm.full_bytes_processed !== null && sm.full_bytes_processed !== undefined)
      full.push('process about <b>' + fmtBytes(sm.full_bytes_processed) + '</b> (from a free dry run; what on-demand pricing bills)');
    if (sm.full_slot_ms !== null && sm.full_slot_ms !== undefined)
      full.push('use roughly <b>' + fmtInt(Math.round(sm.full_slot_ms / 1000)) + ' slot-seconds</b> (this run\u2019s slot time \u00d7 ' +
        fmtNum(Math.round(sm.scale * 10) / 10) + ', the table/sample row ratio; a rough guide)');
    if (sm.warning) html += '<p class="sens-intro"><b>' + esc(sm.warning) + '</b></p>';
    html += '<p class="sens-intro">' + sampleShort + ' Every figure in it describes the sample, not the whole table, and each query ' +
      're-sampled, so steps can differ slightly. Keys and references found in a sample may not hold for the whole table.' +
      (full.length ? ' Profiling the whole table with the same settings would ' + full.join(' and ') + '.' : '') + '</p>';
  }
  html += '<table class="run-table"><tbody>' + rows + '</tbody></table>';
  const placeholderNote = 'Replace <code>INPUT</code>/<code>PATH:COLUMN</code>: this run was started from Python, so the data had no file name.';
  if (meta.extend_command) html += cmdBlock('Extend this run', meta.extend_command, (meta.extend_command.complete ? '' : placeholderNote));
  if (meta.command) html += cmdBlock('Reproduce this run', meta.command, (meta.command.complete ? '' : placeholderNote));

  const used = meta.settings || {};
  const engine = meta.engine;
  const changed = SETTINGS_DOC.filter(d => used[d.name] !== undefined && used[d.name] !== d.default).length;
  let group = null, setRows = '';
  SETTINGS_DOC.forEach(d => {
    if (d.group !== group) { group = d.group; setRows += '<tr><td colspan="4" class="set-group">' + esc(group) + '</td></tr>'; }
    const v = used[d.name];
    const isChanged = v !== undefined && v !== d.default;
    const applies = d.engines === 'both' || d.engines === engine;
    setRows += '<tr class="set-row' + (isChanged ? ' set-changed' : '') + '"' + (applies ? '' : ' style="opacity:.55"') + '>' +
      '<td><span class="set-flag">' + esc(d.flag) + '</span></td>' +
      '<td class="set-val">' + esc(v === undefined ? '\u2014' : fmtSetting(v)) + (isChanged ? ' <span class="set-default panel-sub">(default ' + esc(fmtSetting(d.default)) + ')</span>' : '') + '</td>' +
      '<td class="set-help">' + esc(d.help) + '</td>' +
      '<td class="set-engine">' + (d.engines === 'both' ? '' : esc(d.engines) + ' only') + '</td></tr>';
  });
  html += '<details class="settings"><summary>All settings \u2014 ' + (changed ? changed + ' changed from default' : 'all defaults') +
    (meta.datascope_version ? ' \u00b7 datascope ' + esc(meta.datascope_version) : '') + '</summary>' +
    '<table class="run-table" style="margin-top:8px"><tbody>' + setRows + '</tbody></table></details>';

  const body = document.getElementById('run-body');
  body.innerHTML = html;
  document.getElementById('run-section').hidden = false;
  wireCopyButtons(body);
}

const state = { search: '', sensitiveOnly: false, typeFilters: new Set(), sort: 'name' };

function renderFilterChips() {
  const dist = PROFILE.overview.type_distribution || {};
  const types = Object.keys(dist).sort((a,b) => dist[b]-dist[a]);
  const sensCount = PROFILE.overview.sensitive_columns_count;
  let html = '';
  if (sensCount > 0) html += '<button class="chip chip-sensitive" data-filter-sensitive="1">Personal &amp; sensitive <span class="chip-count">' + sensCount + '</span></button>';
  html += types.map(t => '<button class="chip" data-filter-type="' + esc(t) + '">' + esc(titleCase(t)) + ' <span class="chip-count">' + dist[t] + '</span></button>').join('');
  document.getElementById('filter-chips').innerHTML = html;
  document.querySelectorAll('[data-filter-type]').forEach(btn => btn.addEventListener('click', () => {
    const t = btn.dataset.filterType;
    if (state.typeFilters.has(t)) { state.typeFilters.delete(t); btn.classList.remove('active'); }
    else { state.typeFilters.add(t); btn.classList.add('active'); }
    renderColumnGrid();
  }));
  const sensBtn = document.querySelector('[data-filter-sensitive]');
  if (sensBtn) sensBtn.addEventListener('click', () => {
    state.sensitiveOnly = !state.sensitiveOnly;
    sensBtn.classList.toggle('active', state.sensitiveOnly);
    sensBtn.setAttribute('aria-pressed', String(state.sensitiveOnly));
    renderColumnGrid();
  });
}

function sortColumns(cols, mode) {
  const arr = cols.slice();
  if (mode === 'missing') arr.sort((a,b) => b.missing_pct - a.missing_pct);
  else if (mode === 'unique') arr.sort((a,b) => b.unique_pct - a.unique_pct);
  else arr.sort((a,b) => a.name.localeCompare(b.name));
  return arr;
}

function renderColumnGrid() {
  const grid = document.getElementById('column-grid');
  const query = state.search.trim().toLowerCase();
  let cols = PROFILE.columns.filter(c => {
    if (state.sensitiveOnly && !c.sensitive.is_sensitive) return false;
    if (state.typeFilters.size && !state.typeFilters.has(c.semantic_type)) return false;
    if (query && c.name.toLowerCase().indexOf(query) === -1) return false;
    return true;
  });
  cols = sortColumns(cols, state.sort);
  document.getElementById('column-count').textContent = cols.length + ' of ' + PROFILE.columns.length + ' columns';
  if (!cols.length) { grid.innerHTML = '<div class="empty-state">No columns match.</div>'; return; }
  grid.innerHTML = cols.map((c, i) => {
    const spec = getChartSpec(c);
    return '<button class="col-card" style="--i:' + i + '" data-col="' + esc(c.name) + '">' +
      '<div class="col-card-head">' +
        '<span class="col-glyph">' + icon(TYPE_ICON[c.semantic_type]||'help', 'xl', 'color:' + (TYPE_COLOR[c.semantic_type]||'var(--text-muted)'), true) + '</span>' +
        '<span class="col-name" title="' + esc(c.name) + '">' + esc(c.name) + '</span>' +
        (c.sensitive.is_sensitive ? '<span class="material-symbols-outlined icon icon-sm sens-icon" title="' + esc(sensLabel(c.sensitive)) + '">lock</span>' : '') +
      '</div>' +
      '<div class="col-type-label">' + esc(titleCase(c.semantic_type)) + ' \u00b7 ' + esc(c.dtype) + '</div>' +
      renderBars(spec, 'sm') +
      '<div class="col-card-caption">' + esc(chartCaption(c, spec)) + '</div>' +
      '<div class="col-card-foot">' +
        '<span title="Missing">' + icon('help', 'sm') + '<b>' + fmtPct(c.missing_pct) + '</b> missing</span>' +
        '<span title="Unique">' + icon('fingerprint', 'sm') + '<b>' + fmtPct(c.unique_pct) + '</b> unique</span>' +
      '</div>' +
    '</button>';
  }).join('');
  grid.querySelectorAll('.col-card').forEach(btn => btn.addEventListener('click', () => openDetail(btn.dataset.col)));
  wireTooltips(grid);
}

function showDashboard() { document.getElementById('view-detail').hidden = true; document.getElementById('view-dashboard').hidden = false; window.scrollTo(0, 0); }
function openDetail(colName) {
  const col = PROFILE.columns.find(c => c.name === colName);
  if (!col) return;
  renderDetail(col);
  document.getElementById('view-dashboard').hidden = true;
  document.getElementById('view-detail').hidden = false;
  window.scrollTo(0, 0);
}

function renderQuantileRuler(ns) {
  if (ns.min === null || ns.max === null || ns.min === ns.max) return '';
  const range = ns.max - ns.min;
  const pos = v => ((v - ns.min) / range) * 100;
  return '<div class="detail-block"><div class="ruler-heading">' + icon('straighten') + 'Quantile ruler</div><div class="ruler-track">' +
    '<div class="ruler-baseline"></div>' +
    '<span class="ruler-band" style="left:' + pos(ns.q1) + '%; width:' + (pos(ns.q3)-pos(ns.q1)) + '%"></span>' +
    '<div class="ruler-mark" style="left:0%"><span class="ruler-mark-line end"></span><span class="ruler-mark-label below">min ' + fmtNum(ns.min) + '</span></div>' +
    '<div class="ruler-mark" style="left:' + pos(ns.q1) + '%"><span class="ruler-mark-line"></span><span class="ruler-mark-label above">q1 ' + fmtNum(ns.q1) + '</span></div>' +
    '<div class="ruler-mark" style="left:' + pos(ns.median) + '%"><span class="ruler-mark-line strong"></span><span class="ruler-mark-label above strong">median ' + fmtNum(ns.median) + '</span></div>' +
    '<div class="ruler-mark" style="left:' + pos(ns.q3) + '%"><span class="ruler-mark-line"></span><span class="ruler-mark-label above">q3 ' + fmtNum(ns.q3) + '</span></div>' +
    '<div class="ruler-mark" style="left:100%"><span class="ruler-mark-line end"></span><span class="ruler-mark-label below">max ' + fmtNum(ns.max) + '</span></div>' +
    '</div></div>';
}

function renderTopValuesBlock(col) {
  const tv = col.top_values || [];
  const heading = '<div class="ruler-heading">' + icon('leaderboard') + 'Top values</div>';
  if (!tv.length) return '<div class="detail-block">' + heading + '<div class="empty-state">No values.</div></div>';
  const max = Math.max(...tv.map(v => v.pct), 1);
  const rows = tv.map(v => '<div class="tv-row"><span class="tv-label" title="' + esc(v.value) + '">' + esc(v.value) + '</span><span class="tv-bar-track"><span class="tv-bar-fill" style="width:' + (v.pct/max*100) + '%"></span></span><span class="tv-pct">' + fmtPct(v.pct) + '</span></div>').join('');
  return '<div class="detail-block">' + heading + '<div class="tv-list">' + rows + '</div></div>';
}
function renderQualityRulesBlock(col) {
  const rules = col.quality_rules || [];
  const heading = '<div class="ruler-heading">' + icon('checklist') + 'Quality rules</div>';
  if (!rules.length) return '<div class="detail-block">' + heading + '<div class="empty-state">' + icon('check_circle','sm') + ' Nothing to suggest.</div></div>';
  const rows = rules.map(r => '<div class="rule-row" style="--sev-color:' + (SEVERITY_COLOR[r.severity]||'var(--border)') + '"><span class="rule-glyph">' + icon(SEVERITY_ICON[r.severity]||'info', 'sm') + '</span><span class="rule-desc">' + esc(r.description) + '</span></div>').join('');
  return '<div class="detail-block">' + heading + '<div class="rule-list">' + rows + '</div></div>';
}
function renderDbtBlock(snippet) {
  return '<div class="detail-block dbt-block"><div class="ruler-heading dbt-heading-row"><span class="row-icon">' + icon('code') + 'dbt schema.yml</span><button class="copy-btn" data-copy>' + icon('content_copy','sm') + 'Copy</button></div><pre class="code-block"><code>' + esc(snippet) + '</code></pre></div>';
}
function wireCopyButtons(root) {
  root.querySelectorAll('[data-copy]').forEach(btn => {
    btn.addEventListener('click', () => {
      const code = btn.closest('.dbt-block, .copy-scope').querySelector('code');
      const text = code.textContent;
      const done = () => { const orig = btn.textContent; btn.textContent = 'Copied'; setTimeout(() => btn.textContent = orig, 1200); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done).catch(() => {});
    });
  });
}

function renderDetail(col) {
  const el = document.getElementById('detail-content');
  const parts = [];
  parts.push('<div class="detail-header"><div class="detail-title-row">' +
    '<span class="col-glyph large">' + icon(TYPE_ICON[col.semantic_type]||'help', 'lg', 'color:' + (TYPE_COLOR[col.semantic_type]||'var(--text-muted)'), true) + '</span>' +
    '<h1 class="detail-name">' + esc(col.name) + '</h1></div>' +
    '<div class="detail-badges">' +
      '<span class="badge" style="--badge-color:' + (TYPE_COLOR[col.semantic_type]||'var(--text-muted)') + ';--badge-bg:' + softBg(TYPE_COLOR[col.semantic_type]||'var(--text-muted)') + '">' + esc(titleCase(col.semantic_type)) + ' \u00b7 ' + Math.round(col.semantic_type_confidence*100) + '%</span>' +
      '<span class="badge">' + esc(col.dtype) + '</span>' +
      (col.sensitive.is_sensitive ? '<span class="badge" style="--badge-color:var(--violet);--badge-bg:var(--violet-soft)">' + esc(sensLabel(col.sensitive)) + ' \u00b7 ' + Math.round(col.sensitive.confidence*100) + '% confidence</span>' : '') +
    '</div>' +
    (col.sensitive.is_sensitive ? '<p class="detail-why"><b>Why it looks like ' + esc(sensGroup(col.sensitive).toLowerCase()) + ':</b> ' +
      esc((col.sensitive.reasons || []).join(' ') || 'Flagged by ' + (col.sensitive.detected_by || []).join(' and ').replace(/_/g, ' ') + '.') +
      ' Its values are masked in this report.</p>' : '') +
    (col.semantic_notes && col.semantic_notes.length ? '<p class="detail-note">' + col.semantic_notes.map(esc).join(' ') + '</p>' : '') +
  '</div>');

  const stats = [
    ['Count', fmtInt(col.count), 'tag'], ['Missing', fmtInt(col.missing) + ' (' + fmtPct(col.missing_pct) + ')', 'help'],
    ['Unique', fmtInt(col.unique) + ' (' + fmtPct(col.unique_pct) + ')', 'fingerprint'], ['Memory', fmtBytes(col.memory_bytes), 'storage'],
  ];
  if (col.numeric_stats) {
    const ns = col.numeric_stats;
    stats.push(['Mean', fmtNum(ns.mean), 'functions'], ['Std dev', fmtNum(ns.std), 'query_stats'], ['Min', fmtNum(ns.min), 'south'], ['Max', fmtNum(ns.max), 'north'],
      ['Zeros', fmtInt(ns.zeros) + ' (' + fmtPct(ns.zeros_pct) + ')', 'exposure_zero'], ['Negatives', fmtInt(ns.negatives), 'exposure_neg_1'],
      ['Skewness', fmtNum(ns.skewness), 'insights'], ['Outliers (1.5\u00d7IQR)', fmtInt(ns.outlier_count) + ' (' + fmtPct(ns.outlier_pct) + ')', 'report_problem']);
    if (ns.infinite_count) stats.push(['Infinite values', fmtInt(ns.infinite_count), 'warning']);
  }
  if (col.string_stats) {
    const ss = col.string_stats;
    stats.push(['Min length', fmtInt(ss.min_length), 'south'], ['Max length', fmtInt(ss.max_length), 'north'], ['Mean length', fmtNum(ss.mean_length), 'straighten'], ['Empty/whitespace', fmtInt(ss.empty_or_whitespace), 'remove_circle']);
  }
  if (col.datetime_stats) {
    const ds = col.datetime_stats;
    stats.push(['Earliest', ds.min_date ? ds.min_date.slice(0,10) : '\u2014', 'event'], ['Latest', ds.max_date ? ds.max_date.slice(0,10) : '\u2014', 'event'], ['Range', fmtInt(ds.range_days) + ' days', 'date_range'], ['Future-dated', fmtInt(ds.future_dates), 'schedule']);
  }
  if (col.boolean_stats) {
    const bs = col.boolean_stats;
    stats.push(['True', fmtInt(bs.true_count) + ' (' + fmtPct(bs.true_pct) + ')', 'check_circle'], ['False', fmtInt(bs.false_count), 'cancel']);
  }
  parts.push('<div class="stat-grid">' + stats.map(([k,v,ic]) => '<div class="stat-cell"><div class="stat-cell-head">' + icon(ic||'chevron_right', 'sm') + '<div class="stat-label">' + esc(k) + '</div></div><div class="stat-value">' + esc(v) + '</div></div>').join('') + '</div>');

  if (col.numeric_stats) parts.push(renderQuantileRuler(col.numeric_stats));
  const spec = getChartSpec(col);
  parts.push('<div class="detail-block"><div class="ruler-heading">Distribution</div>' + renderBars(spec, 'lg') + '</div>');
  parts.push('<div class="detail-two-col">' + renderTopValuesBlock(col) + renderQualityRulesBlock(col) + '</div>');
  if (col.dbt_snippet) parts.push(renderDbtBlock(col.dbt_snippet));

  el.innerHTML = parts.join('');
  wireCopyButtons(el);
  wireTooltips(el);
}

document.getElementById('search-input').addEventListener('input', e => { state.search = e.target.value; renderColumnGrid(); });
document.getElementById('sort-select').addEventListener('change', e => { state.sort = e.target.value; renderColumnGrid(); });
document.getElementById('back-btn').addEventListener('click', showDashboard);

renderHeader();
renderHero();
renderQuality();
renderSensitive();
renderTypeDistribution();
renderCorrelation();
renderMissingCorr();
renderPkCandidates();
renderColumnDependencies();
renderReferentialIntegrity();
renderRunSummary();
renderFilterChips();
renderColumnGrid();
</script>
</body>
</html>
'''
