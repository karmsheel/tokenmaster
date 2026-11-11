#!/usr/bin/env python3
"""Generate a self-contained dashboard.html from dashboard_data.json (placeholder replacement)."""
import json, html

D = json.load(open(r"C:\Users\karms\Projects\tokenmaster\dashboard_data.json", encoding="utf-8"))
T = D["totals"]
daily, models, providers, sessions, cost_status, recent = (
    D["daily"], D["models"], D["provider_split"], D["sessions"],
    D["cost_by_status"], D["recent14"])

CI = lambda s: html.escape(str(s))

def fmt(n):
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)

def fmt_usd(n):
    try:
        return f"${float(n):,.4f}"
    except Exception:
        return str(n)

# ---------- small SVG chart builders (return plain strings) ----------
def line_svg(days):
    w, h = 760, 260
    pad_l, pad_r, pad_t, pad_b = 34, 16, 12, 26
    seq_in = [d["input_tokens"] for d in days]
    seq_out = [d["output_tokens"] for d in days]
    seq_ca = [d["cache_read"] for d in days]
    def ng(key):
        return max(max(d[key] for d in days), 1)
    R = {"input_tokens": ng("input_tokens"), "output_tokens": ng("output_tokens"),
         "cache_read": ng("cache_read")}
    def pts(seq, key):
        n = len(seq)
        out = []
        for i, v in enumerate(seq):
            x = pad_l + (i / max(n - 1, 1)) * (w - pad_l - pad_r)
            y = h - pad_b - (v / R[key]) * (h - pad_t - pad_b)
            out.append((x, y))
        return out
    def poly(p):
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in p)
    def area(p):
        if not p: return ""
        q = p[:]
        q.append((p[-1][0], h - pad_b))
        q.append((p[0][0], h - pad_b))
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in q) + " Z"
    grid = "".join(
        f'<line x1="{pad_l}" y1="{h - pad_b - v * (h - pad_t - pad_b):.1f}" x2="{w - pad_r}" y2="{h - pad_b - v * (h - pad_t - pad_b):.1f}" stroke="#e5e7eb" stroke-width="1"/>'
        for v in (0.25, 0.5, 0.75))
    d0, d1 = (days[0]["date"], days[-1]["date"]) if days else ("", "")
    title = f'Daily tokens (input vs output)  ·  {d0} → {d1}'
    p_ca, p_in, p_out = pts(seq_ca, "cache_read"), pts(seq_in, "input_tokens"), pts(seq_out, "output_tokens")
    return f'''<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" style="overflow:visible">
  {grid}
  <path d="{area(p_ca)}" fill="#3b82f6" fill-opacity="0.08"/>
  <polyline points="{poly(p_ca)}" fill="none" stroke="#3b82f6" stroke-width="2" stroke-dasharray="4 3"/>
  <polyline points="{poly(p_in)}" fill="none" stroke="#10b981" stroke-width="2.5"/>
  <polyline points="{poly(p_out)}" fill="none" stroke="#f59e0b" stroke-width="2"/>
  <rect x="{w - pad_r - 26}" y="6" width="14" height="14" rx="3" fill="#10b981"/>
  <rect x="{w - pad_r - 26}" y="24" width="14" height="14" rx="3" fill="#f59e0b"/>
  <rect x="{w - pad_r - 26}" y="42" width="14" height="14" rx="3" fill="#3b82f6"/>
  <rect x="{w - pad_r - 26}" y="60" width="14" height="14" rx="3" fill="#9ca3af"/>
  <text x="{w - pad_r - 34}" y="19" fill="#10b981" font-size="11" font-weight="600" text-anchor="end">Input</text>
  <text x="{w - pad_r - 34}" y="37" fill="#f59e0b" font-size="11" font-weight="600" text-anchor="end">Output</text>
  <text x="{w - pad_r - 34}" y="55" fill="#3b82f6" font-size="11" font-weight="600" text-anchor="end">Cache read</text>
  <text x="14" y="18" fill="#374151" font-size="14" font-weight="700">{CI(title)}</text>
</svg>'''

def hbar(models_):
    w = 700
    top = sorted(models_, key=lambda m: m["input_tokens"], reverse=True)[:12]
    maxv = max((m["input_tokens"] for m in top), default=1)
    n = len(top)
    rows = "".join(
        f'<rect x="0" y="{i*24}" width="{(m["input_tokens"]/maxv)*660}" height="20" rx="4" fill="#10b981" opacity="{0.55 + 0.45*((i+1)/n)}"/>'
        for i, m in enumerate(top))
    ylabels = "".join(f'<text x="8" y="{i*24+14}" fill="#6b7280" font-size="11" text-anchor="end">{CI(m["model"])}</text>' for i, m in enumerate(top))
    val_labels = "".join(f'<text x="672" y="{i*24+14}" fill="#374151" font-size="10" text-anchor="end">{fmt(m["input_tokens"])}</text>' for i, m in enumerate(top))
    return f'''<svg viewBox="0 0 {w} {n*24+30}" width="{w}" height="{n*24+30}" style="overflow:visible">
  <line x1="60" y1="{n*24}" x2="672" y2="{n*24}" stroke="#e5e7eb" stroke-width="1"/>
  {ylabels}
  {val_labels}
  {rows}
  <text x="10" y="{n*24-14}" fill="#6b7280" font-size="11">tokens (input)</text>
  <text x="10" y="16" fill="#374151" font-size="14" font-weight="700">Top models by input tokens</text>
</svg>'''

def donut(providers_):
    total = max(sum(p["tokens"] for p in providers_), 1)
    cw = ["#ff6a00", "#10b981", "#f59e0b", "#3b82f6", "#8b5cf6", "#ec4899", "#6b7280", "#14b8a6"]
    arcs, labels, counts = "", "", ""
    start = 0
    for i, p in enumerate(providers_[:8]):
        ang = p["tokens"] / total * 2 * 3.14159265
        c = cw[i % len(cw)]
        mid = 3.14159265 + start + ang / 2
        lx = 120 + (math.cos(mid) * 96)
        ly = 110 + (math.sin(mid) * 96)
        anchor = "middle" if abs(math.cos(mid)) < 0.9 else "start"
        counts += f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" fill="#ffffff" font-size="10" font-weight="700">{p["tokens"]/total*100:.0f}%</text>'
        arcs += f'<path d="M 120 110 L {120+math.cos(start)*96} {110+math.sin(start)*96} A 96 96 0 {"1" if ang > 3.14159265 else "0"} 1 {120+math.cos(start+ang)*96} {110+math.sin(start+ang)*96} Z" fill="{c}" fill-opacity="0.85"/>'
        start += ang
    return f'''<svg viewBox="0 0 260 240" width="260" height="240" style="overflow:visible">
  {arcs}
  <text x="130" y="120" text-anchor="middle" fill="#111827" font-size="15" font-weight="800">Share</text>
  <text x="130" y="140" text-anchor="middle" fill="#6b7280" font-size="10">of input tokens</text>
  {counts}
</svg>'''

import math

def recent_bar(recent_):
    w, h = 520, 200
    pad_l, pad_r, pad_t, pad_b = 30, 8, 22, 26
    if not recent_:
        return '<svg></svg>'
    n = len(recent_)
    vals = [r["cache_read"] or 0 for r in recent_]
    inp = [r["input"] or 0 for r in recent_]
    out = [r["output"] or 0 for r in recent_]
    maxv = max(max(vals), max(inp), max(out), 1)
    wpx = w - pad_l - pad_r
    bars = ""
    for i, r in enumerate(recent_):
        x = pad_l + (i / max(n - 1, 1)) * wpx
        bw = wpx / max(n - 1, 1) * 0.5
        bbase = h - pad_b
        ba = bbase - (r["cache_read"] or 0) / maxv * (h - pad_t - pad_b)
        bars += f'<rect x="{x:.1f}" y="{ba:.1f}" width="{bw:.1f}" height="{bbase-ba:.1f}" rx="2" fill="#3b82f6" opacity="0.9"/>'
        ba = bbase - (r["input"] or 0) / maxv * (h - pad_t - pad_b)
        bars += f'<rect x="{x:.1f}" y="{ba:.1f}" width="{bw:.1f}" height="{bbase-ba:.1f}" rx="2" fill="#10b981" opacity="0.9"/>'
        ba = bbase - (r["output"] or 0) / maxv * (h - pad_t - pad_b)
        bars += f'<rect x="{x:.1f}" y="{ba:.1f}" width="{bw:.1f}" height="{bbase-ba:.1f}" rx="2" fill="#f59e0b" opacity="0.9"/>'
    labels = "".join(
        f'<text x="{pad_l+(i/(max(n-1,1)))*wpx:.1f}" y="{h-10}" fill="#6b7280" font-size="9" text-anchor="middle">{r["date"][5:]}</text>'
        for i, r in enumerate(recent_))
    return f'''<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" style="overflow:visible">
  {bars}
  {labels}
  <text x="14" y="16" fill="#374151" font-size="13" font-weight="700">Recent 14 days: tokens/day</text>
  <rect x="0" y="0" width="12" height="12" rx="3" fill="#3b82f6"/>
  <text x="18" y="10" fill="#6b7280" font-size="10">Cache read</text>
  <rect x="0" y="16" width="12" height="12" rx="3" fill="#10b981"/>
  <text x="18" y="28" fill="#6b7280" font-size="10">Input</text>
  <rect x="0" y="32" width="12" height="12" rx="3" fill="#f59e0b"/>
  <text x="18" y="44" fill="#6b7280" font-size="10">Output</text>
</svg>'''

# ---------- builders ----------
line_html = line_svg(daily)
hbar_html = hbar(models)
donut_html = donut(providers)
recent_html = recent_bar(recent)

legend_rows = "".join(
    f'<span><span class="dot" style="background:{["#ff6a00","#10b981","#f59e0b","#3b82f6","#8b5cf6"][i%5]}"></span>'
    f'{CI(c["provider"])} ({fmt(c["tokens"])} tokens)</span>' for i, c in enumerate(providers))

rows = "".join(
    f'<tr><td>{CI(c["status"])}</td><td style="text-align:right">{c["count"]}</td>'
    f'<td style="text-align:right">{fmt_usd(c["estimated_cost_usd"])}</td>'
    f'<td style="text-align:right">{fmt_usd(c["actual_cost_usd"])}</td></tr>' for c in cost_status)

data_json = json.dumps(D)

# ---------- template with placeholders ----------
TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Hermes · Token Usage Dashboard</title>
<style>
  :root {
    --bg: #f8fafc; --panel: #ffffff; --line: #e2e8f0; --text: #0f172a; --muted: #6b7280;
    --accent: #ff6a00; --input: #10b981; --output: #f59e0b; --cache: #3b82f6;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.45;
  }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 24px 20px 64px; }
  header { border-bottom: 1px solid var(--line); padding-bottom: 16px; margin-bottom: 20px; }
  header h1 { margin: 0 0 4px; font-size: 22px; display: flex; align-items: center; gap: 10px; }
  header .sub { color: var(--muted); font-size: 12.5px; }
  .kpi { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; }
  .kpi .card {
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px;
  }
  .kpi .card .lbl { font-size: 11.5px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .kpi .card .val { font-size: 22px; font-weight: 700; margin-top: 4px; }
  .kpi .card .val .unit { font-size: 13px; color: var(--muted); font-weight: 500; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 18px; }
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 15px; }
  .card .sub { color: var(--muted); font-size: 11.5px; margin-bottom: 10px; }
  .legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 11.5px; color: var(--muted); }
  .legend span { display: flex; align-items: center; gap: 6px; }
  .legend .dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
  main { display: grid; gap: 18px; }
  footer { color: var(--muted); font-size: 11px; margin-top: 24px; border-top: 1px solid var(--line); padding-top: 12px; }
  @media (max-width: 780px) { .grid2 { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Hermes · token usage dashboard</h1>
    <div class="sub">Source: __SRC__ · generated __GEN__ · __TOT__</div>
  </header>

  <div class="kpi">
    <div class="card"><div class="lbl">Input tokens</div><div class="val">__IN__<span class="unit">tokens</span></div></div>
    <div class="card"><div class="lbl">Output tokens</div><div class="val">__OUT__<span class="unit">tokens</span></div></div>
    <div class="card"><div class="lbl">Cache read</div><div class="val">__CR__<span class="unit">tokens</span></div></div>
    <div class="card"><div class="lbl">API calls</div><div class="val">__AC__<span class="unit">calls</span></div></div>
    <div class="card"><div class="lbl">Est. cost</div><div class="val">__EC__<span class="unit">USD</span></div></div>
    <div class="card"><div class="lbl">Sessions</div><div class="val">__SN__<span class="unit">rows</span></div></div>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>Daily tokens · __D0__ → __D1__</h2>
      <div class="sub">Input (green), output (orange), cache read (blue dashes)</div>
      __LINE__
    </div>
    <div class="card">
      <h2>Top models by input tokens</h2>
      <div class="sub">Provider split inset</div>
      __HBAR__
    </div>
  </div>

  <main>
    <div class="grid2" style="grid-template-columns: 1fr 1fr;">
      <div class="card">
        <h2>Billing provider split</h2>
        <div class="sub">Tokens by provider</div>
        <div style="text-align:center">__DONUT__</div>
        <div class="legend">__LEGEND__</div>
      </div>
      <div class="card">
        <h2>Recent 14 days</h2>
        <div class="sub">Cache read / input / output per day</div>
        __RECENT__
      </div>
    </div>
    <div class="card" style="grid-column: 1 / -1;">
      <h2>Cost by status</h2>
      <div class="sub">Estimated vs actual cost (USD)</div>
      <table style="width:100%; border-collapse:collapse; font-size:12.5px">
        <thead><tr style="text-align:left"><th>status</th><th style="text-align:right">count</th><th style="text-align:right">estimated</th><th style="text-align:right">actual</th></tr></thead>
        <tbody>__ROWS__</tbody>
      </table>
    </div>
  </main>

  <footer>
    Build: dashboard_data.json from state.db · __SN__ sessions · __AC__ api calls
  </footer>
</div>
<script>
const DATA = __DATA__;
</script>
</body>
</html>
"""

PAGE = (TEMPLATE
    .replace("__SRC__", CI(D["meta"]["source_notes"]))
    .replace("__GEN__", CI(D["meta"]["generated_at"]))
    .replace("__TOT__", f"{T['input_tokens']+T['output_tokens']+T['cache_read']:,} total tokens")
    .replace("__IN__", fmt(T["input_tokens"]))
    .replace("__OUT__", fmt(T["output_tokens"]))
    .replace("__CR__", fmt(T["cache_read"]))
    .replace("__AC__", fmt(T["api_call_count"]))
    .replace("__EC__", fmt_usd(T["estimated_cost_usd"]))
    .replace("__SN__", str(sessions["total"]))
    .replace("__D0__", daily[0]["date"] if daily else "—")
    .replace("__D1__", daily[-1]["date"] if daily else "—")
    .replace("__LINE__", line_html)
    .replace("__HBAR__", hbar_html)
    .replace("__DONUT__", donut_html)
    .replace("__LEGEND__", legend_rows)
    .replace("__RECENT__", recent_html)
    .replace("__ROWS__", rows)
    .replace("__DATA__", data_json))

with open(r"C:\Users\karms\Projects\tokenmaster\index.html", "w", encoding="utf-8") as f:
    f.write(PAGE)
print("Wrote index.html")
print("daily:", len(daily), "models:", len(models), "providers:", len(providers),
      "cost rows:", len(cost_status), "recent:", len(recent))
