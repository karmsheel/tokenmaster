#!/usr/bin/env python3
"""Generate a self-contained dashboard.html from dashboard_data.json."""
import json, html

D = json.load(open(r"C:\Users\karms\Projects\tokenmaster\dashboard_data.json", encoding="utf-8"))
T = D["totals"]
daily, models, providers, sessions, cost_status, recent = (
    D["daily"], D["models"], D["provider_split"], D["sessions"],
    D["cost_by_status"], D["recent14"])

CI = lambda s: html.escape(str(s))

# ---- helpers ----
def fmt(n):  # thousands separator
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)

def fmt_usd(n):
    try:
        return f"${float(n):,.4f}"
    except Exception:
        return str(n)

# ---- line chart (daily input vs output) ----
def line_svg(days, width=760, height=260):
    pad = {"l": 34, "r": 16, "t": 12, "b": 26}
    w, h = width, height
    seq_in = [d["input_tokens"] for d in days]
    seq_out = [d["output_tokens"] for d in days]
    seq_ca = [d["cache_read"] for d in days]
    def rng(seq):
        mx = max(max(seq), 1)
        return mx
    R = {
        "input_tokens": rng(seq_in),
        "output_tokens": rng(seq_out),
        "cache_read": rng(seq_ca),
    }
    def pts(seq, key, color):
        mx = R[key]
        pts_ = []
        n = len(seq)
        for i, v in enumerate(seq):
            x = pad["l"] + (i / max(n - 1, 1)) * (w - pad["l"] - pad["r"])
            y = h - pad["b"] - (v / mx) * (h - pad["t"] - pad["b"])
            pts_.append((x, y))
        return pts_
    def poly(pts_, close=False):
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts_) + (" Z" if close else "")
    def area(pts_):
        if not pts_:
            return ""
        inner = pts_[:]
        inner.append((pts_[-1][0], h - pad["b"]))
        inner.append((pts_[0][0], h - pad["b"]))
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in inner) + " Z"
    # gridlines
    grid = []
    for i, v in enumerate([0.25, 0.5, 0.75]):
        y = h - pad["b"] - v * (h - pad["t"] - pad["b"])
        grid.append(f'<line x1="{pad["l"]}" y1="{y:.1f}" x2="{w - pad["r"]}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="1"/>')
    legend = ""
    # find min/max dates for labels
    d0, d1 = (days[0]["date"], days[-1]["date"]) if days else ("", "")
    title = f'Daily tokens (input vs output)  ·  {d0} → {d1}'
    return f'''<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" style="overflow:visible">
  {''.join(grid)}
  <path d="{area(pts(seq_ca, 'cache_read', '#3b82f6'))}" fill="#3b82f6" fill-opacity="0.08"/>
  <polyline points="{poly(pts(seq_ca, 'cache_read', '#3b82f6'))}" fill="none" stroke="#3b82f6" stroke-width="2" stroke-dasharray="4 3"/>
  <polyline points="{poly(pts(seq_in, 'input_tokens', '#10b981'))}" fill="none" stroke="#10b981" stroke-width="2.5"/>
  <polyline points="{poly(pts(seq_out, 'output_tokens', '#f59e0b'))}" fill="none" stroke="#f59e0b" stroke-width="2" stroke-dasharray="0"/>
  <circle cx="{pad["l"]}" cy="{h - pad["b"] - (0/R['input_tokens'])*(h-pad['t']-pad['b']):.1f}" r="0"/>
  <rect x="{w - pad["r"] - 26}" y="6" width="14" height="14" rx="3" fill="#10b981"/>
  <rect x="{w - pad["r"] - 26}" y="24" width="14" height="14" rx="3" fill="#f59e0b"/>
  <rect x="{w - pad["r"] - 26}" y="42" width="14" height="14" rx="3" fill="#3b82f6"/>
  <rect x="{w - pad["r"] - 26}" y="60" width="14" height="14" rx="3" fill="#9ca3af"/>
  <text x="{w - pad["r"] - 34}" y="19" fill="#10b981" font-size="11" font-weight="600" text-anchor="end">Input</text>
  <text x="{w - pad["r"] - 34}" y="37" fill="#f59e0b" font-size="11" font-weight="600" text-anchor="end">Output</text>
  <text x="{w - pad("r") - 34}" y="55" fill="#3b82f6" font-size="11" font-weight="600" text-anchor="end">Cache read</text>
  <text x="{w - pad("r") - 34}" y="74" fill="#9ca3af" font-size="10" font-weight="600" text-anchor="end">Cache write</text>
  <text x="14" y="18" fill="#374151" font-size="14" font-weight="700">{title}</text>
</svg>'''

def hbar(models_, width=760):
    pad_l, pad_r, pad_b = 46, 14, 22
    top = sorted(models_, key=lambda m: m["input_tokens"], reverse=True)[:12]
    maxv = max((m["input_tokens"] for m in top), default=1)
    rows = []
    for i, m in enumerate(top):
        v = m["input_tokens"] / maxv
        rows.append(f'''<rect x="0" y="{i*24}" width="{v*1}" height="20" rx="4" fill="#10b981" opacity="{(0.55 + 0.45*((i+1)/len(top)))}"/>''')
    # x axis
    # build a scale: 0..maxv -> pixels relative to right anchor
    right_anchor = "100%"  # placeholder
    ylabels = "".join(f'<text x="8" y="{i*24+14}" fill="#6b7280" font-size="11" text-anchor="end">{CI(m["model"])}</text>' for i, m in enumerate(top))
    # value labels anchored near right
    val_labels = "".join(f'<text x="{"680"}" y="{i*24+14}" fill="#374151" font-size="10" text-anchor="end">{fmt(m["input_tokens"])}</text>' for i, m in enumerate(top))
    # gridline
    grid = f'<line x1="60" y1="{len(top)*24}" x2="{"680"}" y2="{len(top)*24}" stroke="#e5e7eb" stroke-width="1"/>'
    # value axis tick text
    return f'''<svg viewBox="0 0 700 {len(top)*24+24}" width="700" height="{len(top)*24+30}" style="overflow:visible">
  {grid}
  {ylabels}
  {val_labels}
  {rows}
  <text x="10" y="{len(top)*24-14}" fill="#6b7280" font-size="11">tokens (input)</text>
  <text x="10" y="16" fill="#374151" font-size="14" font-weight="700">Top models by input tokens</text>
</svg>'''

def donut(providers_, width=360):
    total = max(sum(p["tokens"] for p in providers_), 1)
    labels = ""
    arcs = ""
    start = 0
    colors = ["#10b981", "#f59e0b", "#3b82f6", "#ef4444", "#8b5cf6", "#ec4899", "#6b7280", "#14b8a6"]
    for i, p in enumerate(providers_[:8]):
        ang = p["tokens"] / total * 3.14159265 * 2
        c = colors[i % len(colors)]
        mid = math.pi + start + ang / 2
        # label position
        lx = 120 + math.cos(mid) * 96
        ly = 110 + math.sin(mid) * 96
        labels += f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{"middle" if abs(math.cos(mid))<0.9 else "start"}" fill="#374151" font-size="11" font-weight="600">{CI(p["provider"])}</text>'
        arcs += f'<path d="M 120 {110} L {120 + math.cos(start)*96} {110 + math.sin(start)*96} A 96 96 0 {("1" if ang > 3.14159265 else "0")} 1 {120 + math.cos(start+ang)*96} {110 + math.sin(start+ang)*96} Z" fill="{c}" fill-opacity="0.85"/>'
        arcs += f'<text x="{120 + math.cos(mid)*96}" y="{110 + math.sin(mid)*96}" text-anchor="{"middle" if abs(math.cos(mid))<0.9 else "start"}" fill="#ffffff" font-size="10" font-weight="700">{p["tokens"]/total*100:.0f}%</text>'
        start += ang
    return f'''<svg viewBox="0 0 260 240" width="260" height="240" style="overflow:visible">
  {arcs}
  <text x="130" y="120" text-anchor="middle" fill="#111827" font-size="15" font-weight="800">Share</text>
  <text x="130" y="140" text-anchor="middle" fill="#6b7280" font-size="10">of input tokens</text>
  {labels}
</svg>'''

def recent_bar(recent_, width=520, height=200):
    pad_l, pad_r, pad_t, pad_b = 30, 8, 22, 26
    if not recent_:
        return '<svg></svg>'
    n = len(recent_)
    vals = [r["cache_read"] or 0 for r in recent_]
    inp = [r["input"] or 0 for r in recent_]
    out = [r["output"] or 0 for r in recent_]
    maxv = max(max(vals), max(inp), max(out), 1)
    w_px = width - pad_l - pad_r
    bars = ""
    for i, r in enumerate(recent_):
        x = pad_l + (i / max(n - 1, 1)) * w_px
        bw = w_px / max(n - 1, 1) * 0.5
        bbase = height - pad_b
        # cache read (top, blue)
        ba = bbase - (r["cache_read"] or 0) / maxv * (height - pad_t - pad_b)
        bars += f'<rect x="{x:.1f}" y="{ba:.1f}" width="{bw:.1f}" height="{bbase-ba:.1f}" rx="2" fill="#3b82f6" opacity="0.9"/>'
        # input (green, on top)
        ba = bbase - (r["input"] or 0) / maxv * (height - pad_t - pad_b)
        bars += f'<rect x="{x:.1f}" y="{ba:.1f}" width="{bw:.1f}" height="{bbase-ba:.1f}" rx="2" fill="#10b981" opacity="0.9"/>'
        # output (orange)
        ba = bbase - (r["output"] or 0) / maxv * (height - pad_t - pad_b)
        bars += f'<rect x="{x:.1f}" y="{ba:.1f}" width="{bw:.1f}" height="{bbase-ba:.1f}" rx="2" fill="#f59e0b" opacity="0.9"/>'
    # x labels (short)
    labels = "".join(f'<text x="{pad_l+(i/(max(n-1,1)))*w_px}" y="{height-10}" fill="#6b7280" font-size="9" text-anchor="{"middle"}">{r["date"][5:]}</text>' for i, r in enumerate(recent_))
    return f'''<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" style="overflow:visible">
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

# ---------- assemble ----------
donut_html = donut(providers)
hbar_html = hbar(models)
line_html = line_svg(daily)
recent_html = recent_bar(recent)

rows = ""
for c in cost_status:
    rows += f'<tr><td>{CI(c["status"])}</td><td style="text-align:right">{c["count"]}</td><td style="text-align:right">{fmt_usd(c["estimated_cost_usd"])}</td><td style="text-align:right">{fmt_usd(c["actual_cost_usd"])}</td></tr>'

data_json = json.dumps(D)

PAGE = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Hermes · Token Usage Dashboard</title>
<style>
  :root {{
    --bg: #f8fafc; --panel: #ffffff; --line: #e2e8f0; --text: #0f172a; --muted: #6b7280;
    --accent: #ff6a00; --accent2: #10b981; --input: #10b981; --output: #f59e0b; --cache: #3b82f6;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.45;
  }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px 20px 64px; }}
  header {{ border-bottom: 1px solid var(--line); padding-bottom: 16px; margin-bottom: 20px; }}
  header h1 {{ margin: 0 0 4px; font-size: 22px; display: flex; align-items: center; gap: 10px; }}
  header .sub {{ color: var(--muted); font-size: 12.5px; }}
  .kpi {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; }}
  .kpi .card {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px;
  }}
  .kpi .card .lbl {{ font-size: 11.5px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }}
  .kpi .card .val {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
  .kpi .card .val .unit {{ font-size: 13px; color: var(--muted); font-weight: 500; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 18px; }}
  .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 16px; }}
  .card h2 {{ margin: 0 0 12px; font-size: 15px; }}
  .card .sub {{ color: var(--muted); font-size: 11.5px; margin-bottom: 10px; }}
  .legend {{ display: flex; flex-wrap: wrap; gap: 14px; font-size: 11.5px; color: var(--muted); }}
  .legend span {{ display: flex; align-items: center; gap: 6px; }}
  .legend .dot {{ width: 10px; height: 10px; border-radius: 3px; display: inline-block; }}
  main {{ display: grid; gap: 18px; }}
  footer {{ color: var(--muted); font-size: 11px; margin-top: 24px; border-top: 1px solid var(--line); padding-top: 12px; }}
  @media (max-width: 780px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🐉 Hermes · token usage <span style="font-size:14px;font-weight:500">dashboard</span></h1>
    <div class="sub">Source: {CI(D["meta"]["source_notes"])} · generated {CI(D["meta"]["generated_at"])} · {T["input_tokens"]+T["output_tokens"]+T["cache_read"]:,} total tokens</div>
  </header>

  <div class="kpi">
    <div class="card"><div class="lbl">Input tokens</div><div class="val">{fmt(T["input_tokens"])}<span class="unit">tokens</span></div></div>
    <div class="card"><div class="lbl">Output tokens</div><div class="val">{fmt(T["output_tokens"])}<span class="unit">tokens</span></div></div>
    <div class="card"><div class="lbl">Cache read</div><div class="val">{fmt(T["cache_read"])}<span class="unit">tokens</span></div></div>
    <div class="card"><div class="lbl">API calls</div><div class="val">{fmt(T["api_call_count"])}<span class="unit">calls</span></div></div>
    <div class="card"><div class="lbl">Est. cost</div><div class="val">{fmt_usd(T["estimated_cost_usd"])}<span class="unit">USD</span></div></div>
    <div class="card"><div class="lbl">Sessions</div><div class="val">{sessions["total"]}<span class="unit">rows</span></div></div>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>Daily tokens · {daily[0]["date"] if daily else "—"} → {daily[-1]["date"] if daily else "—"}</h2>
      <div class="sub">Input (green), output (orange), cache read (blue dashes)</div>
      {line_html}
    </div>
    <div class="card">
      <h2>Top {len(models)} models by input tokens</h2>
      <div class="sub">Provider split inset</div>
      {hbar_html}
    </div>
  </div>

  <main>
    <div class="grid2" style="grid-template-columns: 1fr 1fr;">
      <div class="card">
        <h2>Billing provider split</h2>
        <div class="sub">Tokens by provider</div>
        <div style="text-align:center">{donut_html}</div>
        <div class="legend">{''.join(f'<span><span class="dot" style="background:#ff6a00"></span>{none}</span>' for _ in []) or ''}</div>
      </div>
      <div class="card">
        <h2>Recent 14 days</h2>
        <div class="sub">Cache read / input / output per day</div>
        {recent_html}
      </div>
    </div>
    <div class="card" style="grid-column: 1 / -1;">
      <h2>Cost by status</h2>
      <div class="sub">Estimated vs actual cost (USD)</div>
      <table style="width:100%; border-collapse:collapse; font-size:12.5px">
        <thead><tr style="text-align:left"><th>status</th><th style="text-align:right">count</th><th style="text-align:right">estimated</th><th style="text-align:right">actual</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </main>

  <footer>
    Build: dashboard_data.json generated by build_dashboard.py from state.db · {sessions["total"]} sessions · {sessions["api_calls"]} api calls
  </footer>
</div>
<script>
const DATA = {data_json};
</script>
</body>
</html>'''

# fix the donut legend placeholders (remove broken None loop) -> inject provider legend
legend_rows = "".join(f'<span><span class="dot" style="background:{["#ff6a00","#10b981","#f59e0b","#3b82f6","#8b5cf6"][i%5]}"></span>{c["provider"]} ({fmt(c["tokens"])} tokens)</span>' for i, c in enumerate(providers))
PAGE = PAGE.replace('{''}'.join(f'<span><span class="dot" style="background:#ff6a00"></span>{none}</span>' for _ in []) or ''), legend_rows)

with open(r"C:\Users\karms\Projects\tokenmaster\index.html", "w", encoding="utf-8") as f:
    f.write(PAGE)
print("Wrote index.html")
print("providers legend rows:", len(legend_rows))
