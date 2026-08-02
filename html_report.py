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
    html = _TEMPLATE.replace("__PROFILE_DATA_JSON__", json_str_safe)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


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
.kpi-card-score { display: flex; flex-direction: column; align-items: center; text-align: center; justify-content: center; }
.score-ring-wrap { position: relative; width: 92px; height: 92px; }
.score-ring { width: 92px; height: 92px; transform: rotate(-90deg); }
.score-ring-bg { fill: none; stroke: var(--surface-2); stroke-width: 9; }
.score-ring-fill { fill: none; stroke: var(--teal); stroke-width: 9; stroke-linecap: round;
  transition: stroke-dashoffset 0.9s cubic-bezier(.4,0,.2,1); }
.score-value { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  font-family: var(--font-mono); font-size: 24px; font-weight: 600; }
.kpi-card-label { font-family: var(--font-mono); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.07em; color: var(--text-muted); margin-top: 8px; }
.kpi-icon-badge { width: 36px; height: 36px; border-radius: 9px; display: flex; align-items: center; justify-content: center; margin-bottom: 12px; background: var(--badge-bg, var(--surface-2)); }
.kpi-icon-badge .icon { color: var(--badge-color, var(--text-muted)); }
.kpi-value { font-family: var(--font-mono); font-size: 22px; font-weight: 600; }
.kpi-label { font-size: 10.5px; color: var(--text-muted); margin-top: 3px; text-transform: uppercase; letter-spacing: 0.05em; }
.kpi-bar { margin-top: 10px; height: 4px; background: var(--surface-2); border-radius: 2px; overflow: hidden; }
.kpi-bar span { display: block; height: 100%; border-radius: 2px; transition: width 0.6s ease; }

.alert-list { display: flex; flex-direction: column; gap: 1px; background: var(--border); border-radius: var(--radius-sm); overflow: hidden; }
.alert-row { background: var(--surface); padding: 10px 12px; display: flex; gap: 10px; align-items: flex-start; border-left: 3px solid var(--sev-color, var(--border)); }
.alert-glyph { color: var(--sev-color, var(--text-muted)); font-size: 12px; margin-top: 2px; flex-shrink: 0; }
.alert-msg { font-size: 13.5px; color: var(--text); }
.alert-col { font-family: var(--font-mono); color: var(--text); font-weight: 600; }
.alert-empty, .empty-state { color: var(--text-faint); font-size: 13px; padding: 6px 0; }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
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
    <div class="kpi-card kpi-card-score">
      <div class="score-ring-wrap">
        <svg class="score-ring" viewBox="0 0 120 120">
          <circle class="score-ring-bg" cx="60" cy="60" r="52"></circle>
          <circle class="score-ring-fill" id="score-ring-fill" cx="60" cy="60" r="52"></circle>
        </svg>
        <div class="score-value" id="score-value">&mdash;</div>
      </div>
      <div class="kpi-card-label">Quality score</div>
    </div>
  </section>

  <section class="panel" id="alerts-panel"></section>

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

  <section class="columns-section">
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
</main>

<main id="view-detail" class="view" hidden>
  <button id="back-btn" class="back-btn"><span class="material-symbols-outlined icon">arrow_back</span>Dashboard</button>
  <div id="detail-content"></div>
</main>

<footer class="footer"><span class="material-symbols-outlined icon icon-sm" style="vertical-align:-2px">lock</span> Sensitive values are masked throughout. Type and quality-rule suggestions are heuristic &mdash; verify before enforcing.</footer>

<script>
const PROFILE = __PROFILE_DATA_JSON__;

function esc(s) { const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; }
function fmtInt(n) { if (n === null || n === undefined) return '\u2014'; return Number(n).toLocaleString('en-US'); }
function fmtPct(n, digits) { if (n === null || n === undefined) return '\u2014'; return Number(n).toFixed(digits === undefined ? 1 : digits) + '%'; }
function fmtNum(n) { if (n === null || n === undefined) return '\u2014'; if (Number.isInteger(n)) return fmtInt(n); return Number(n).toLocaleString('en-US', {maximumFractionDigits: 3}); }
function fmtBytes(n) { if (n === null || n === undefined) return '\u2014'; if (n < 1024) return n + ' B'; if (n < 1024*1024) return (n/1024).toFixed(1) + ' KB'; return (n/1024/1024).toFixed(2) + ' MB'; }
function titleCase(s) { return String(s).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()); }
function scoreColor(score) { if (score === null || score === undefined) return 'var(--text-muted)'; if (score >= 80) return 'var(--green)'; if (score >= 50) return 'var(--amber)'; return 'var(--coral)'; }

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

function renderHero() {
  const score = PROFILE.overview.quality_score;
  const r = 52, circ = 2 * Math.PI * r;
  const fillEl = document.getElementById('score-ring-fill');
  fillEl.style.strokeDasharray = circ.toFixed(2);
  fillEl.style.strokeDashoffset = circ.toFixed(2);
  fillEl.style.stroke = scoreColor(score);
  document.getElementById('score-value').textContent = (score === null || score === undefined) ? '\u2014' : score;
  document.getElementById('score-value').style.color = scoreColor(score);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    const pct = (score === null || score === undefined) ? 0 : score/100;
    fillEl.style.strokeDashoffset = (circ * (1 - pct)).toFixed(2);
  }));

  const m = PROFILE.meta, o = PROFILE.overview;
  const completeness = Math.max(0, 100 - o.total_missing_pct);
  const alertCount = (o.alerts || []).length;
  const completenessColor = completeness > 90 ? 'var(--green)' : completeness > 70 ? 'var(--amber)' : 'var(--coral)';
  const tiles = [
    {label: 'Rows', value: fmtInt(m.n_rows), iconName: 'table_rows', color: 'var(--teal)'},
    {label: 'Columns', value: fmtInt(m.n_cols), iconName: 'view_column', color: 'var(--teal)'},
    {label: 'Completeness', value: fmtPct(completeness), bar: completeness, barColor: completenessColor, iconName: 'task_alt', color: completenessColor},
    {label: 'Duplicate rows', value: fmtInt(m.duplicate_rows) + (m.duplicate_rows_pct ? ' (' + fmtPct(m.duplicate_rows_pct) + ')' : ''), iconName: 'content_copy', color: m.duplicate_rows > 0 ? 'var(--amber)' : 'var(--text-faint)'},
    {label: 'Sensitive columns', value: fmtInt(o.sensitive_columns_count), iconName: 'shield', color: o.sensitive_columns_count > 0 ? 'var(--violet)' : 'var(--text-faint)'},
    {label: 'Alerts', value: fmtInt(alertCount), iconName: 'warning', color: alertCount > 0 ? 'var(--amber)' : 'var(--text-faint)'},
    {label: 'Memory', value: m.memory_mb + ' MB', iconName: 'memory', color: 'var(--text-muted)'},
  ];
  const html = tiles.map((t,i) =>
    '<div class="kpi-card" style="--i:' + (i+1) + '">' +
      '<div class="kpi-icon-badge" style="--badge-color:' + t.color + ';--badge-bg:' + softBg(t.color) + '">' + icon(t.iconName, 'xl', null, true) + '</div>' +
      '<div class="kpi-value">' + esc(t.value) + '</div>' +
      '<div class="kpi-label">' + esc(t.label) + '</div>' +
      (t.bar !== undefined ? '<div class="kpi-bar"><span style="width:' + t.bar + '%; background:' + t.barColor + '"></span></div>' : '') +
    '</div>'
  ).join('');
  document.getElementById('kpi-grid').insertAdjacentHTML('beforeend', html);
}

function renderAlerts() {
  const panel = document.getElementById('alerts-panel');
  const alerts = PROFILE.overview.alerts || [];
  const titleIcon = icon('warning', null);
  if (!alerts.length) { panel.innerHTML = '<div class="panel-title">' + titleIcon + 'Alerts</div><div class="alert-empty">' + icon('check_circle','sm') + ' No alerts \u2014 nothing stood out.</div>'; return; }
  const order = {high:0, sensitive:1, warning:2, info:3};
  const sorted = alerts.slice().sort((a,b) => (order[a.severity] === undefined ? 9 : order[a.severity]) - (order[b.severity] === undefined ? 9 : order[b.severity]));
  const rows = sorted.map(a =>
    '<div class="alert-row" style="--sev-color:' + (SEVERITY_COLOR[a.severity] || 'var(--border)') + '">' +
      '<span class="alert-glyph">' + icon(SEVERITY_ICON[a.severity] || 'info', 'sm') + '</span>' +
      '<span class="alert-msg">' + (a.column ? '<span class="alert-col">' + esc(a.column) + '</span> \u2014 ' : '') + esc(a.message) + '</span>' +
    '</div>'
  ).join('');
  panel.innerHTML = '<div class="panel-title">' + titleIcon + 'Alerts <span class="panel-sub">' + alerts.length + '</span></div><div class="alert-list">' + rows + '</div>';
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
function renderCorrelation() { renderHeatmap('corr-heatmap', PROFILE.correlations, 'Fewer than two numeric columns \u2014 nothing to correlate.'); }
function renderMissingCorr() {
  const section = document.getElementById('missing-corr-section');
  if (!PROFILE.missing_correlation) { section.style.display = 'none'; return; }
  section.style.display = '';
  renderHeatmap('missing-corr-heatmap', PROFILE.missing_correlation, 'Not enough columns with partial missingness.');
}
function renderPkCandidates() {
  const panel = document.getElementById('pk-panel');
  const list = document.getElementById('pk-list');
  const candidates = PROFILE.pk_candidates || [];
  if (!candidates.length) { panel.style.display = 'none'; return; }
  panel.style.display = '';
  list.innerHTML = candidates.map(c => '<div class="pk-row"><span class="pk-type">' + (c.type === 'single' ? 'Single column' : 'Composite') + '</span><span class="pk-cols">' + c.columns.map(esc).join(' + ') + '</span></div>').join('');
}

const state = { search: '', sensitiveOnly: false, typeFilters: new Set(), sort: 'name' };

function renderFilterChips() {
  const dist = PROFILE.overview.type_distribution || {};
  const types = Object.keys(dist).sort((a,b) => dist[b]-dist[a]);
  const sensCount = PROFILE.overview.sensitive_columns_count;
  let html = '';
  if (sensCount > 0) html += '<button class="chip chip-sensitive" data-filter-sensitive="1">Sensitive <span class="chip-count">' + sensCount + '</span></button>';
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
        (c.sensitive.is_sensitive ? '<span class="material-symbols-outlined icon icon-sm sens-icon" title="Flagged ' + esc(c.sensitive.category) + '">lock</span>' : '') +
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
      const code = btn.closest('.dbt-block').querySelector('code');
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
      (col.sensitive.is_sensitive ? '<span class="badge" style="--badge-color:var(--violet);--badge-bg:var(--violet-soft)">' + esc(col.sensitive.category) + ' \u00b7 ' + esc(titleCase(col.sensitive.type)) + ' \u00b7 ' + Math.round(col.sensitive.confidence*100) + '%</span>' : '') +
    '</div>' +
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
renderAlerts();
renderTypeDistribution();
renderCorrelation();
renderMissingCorr();
renderPkCandidates();
renderFilterChips();
renderColumnGrid();
</script>
</body>
</html>
'''
