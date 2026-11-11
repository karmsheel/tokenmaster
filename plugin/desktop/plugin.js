/**
 * Token Master — a Hermes Desktop plugin.
 *
 * One chart of daily token consumption across every account, provider and
 * Hermes profile on this machine, plus the configuration screen that marks each
 * credential as a subscription (quota) account, an API-spend account, or free.
 *
 * Disk plugins are loaded uncompiled: no JSX, and the only importable
 * specifiers are `@hermes/plugin-sdk`, `react` and `react/jsx-runtime`.
 * Tailwind does not scan this file, so every layout rule lives in the CSS
 * block below and reads the app's own theme tokens.
 */

import {
  compactNumber,
  host,
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  useQuery,
  useQueryClient
} from '@hermes/plugin-sdk'
import { useEffect, useMemo, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'token-master'

const RANGES = [
  { days: 7, label: '7D' },
  { days: 30, label: '30D' },
  { days: 90, label: '90D' },
  { days: 365, label: '1Y' }
]

const STACKS = [
  { key: 'class', label: 'Token class' },
  { key: 'provider', label: 'Provider' },
  { key: 'profile', label: 'Profile' },
  { key: 'source', label: 'Source' }
]

const SOURCE_LABELS = {
  hermes: 'Hermes',
  'deepseek-harness': 'DeepSeek Harness'
}

function sourceLabel(name) {
  return SOURCE_LABELS[name] || `Remote · ${name}`
}

/** Stack order, bottom to top: the expensive bands sit on the baseline. */
const CLASSES = [
  { key: 'input', label: 'Input', cssVar: '--tm-fill-input' },
  { key: 'output', label: 'Output', cssVar: '--tm-fill-output' },
  { key: 'reasoning', label: 'Reasoning', cssVar: '--tm-fill-reasoning' },
  { key: 'cache_read', label: 'Cache read', cssVar: '--tm-fill-cacheRead' },
  { key: 'cache_write', label: 'Cache write', cssVar: '--tm-fill-cacheWrite' }
]

const CATEGORICAL = [
  '--tm-cat-1',
  '--tm-cat-2',
  '--tm-cat-3',
  '--tm-cat-4',
  '--tm-cat-5',
  '--tm-cat-6',
  '--tm-cat-7'
]

const MODE_OPTIONS = [
  { value: 'subscription', label: 'Subscription (quota)' },
  { value: 'api', label: 'API spend ($)' },
  { value: 'free', label: 'Free tier' }
]

/** How Hermes recorded the cost side of a request. */
const COST_LABELS = {
  included: 'Subscription (included)',
  estimated: 'API (estimated)',
  actual: 'API (billed)',
  none: 'Free tier',
  unknown: 'Price unknown',
  'not recorded': 'Not recorded (harness / remote)'
}

const CSS = `
.tm-page{height:100%;overflow:auto;background:var(--ui-bg-editor);color:var(--ui-text-primary);
  font-family:var(--font-sans,system-ui,sans-serif);padding:22px 26px 44px;box-sizing:border-box}
.tm-wrap{max-width:1180px;margin:0 auto;display:flex;flex-direction:column;gap:16px}
.tm-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;flex-wrap:wrap}
.tm-title{margin:0;font-size:20px;line-height:26px;font-weight:600;letter-spacing:-.01em}
.tm-sub{margin:3px 0 0;font-size:12px;line-height:17px;color:var(--ui-text-tertiary)}
.tm-actions{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.tm-chip{appearance:none;border:1px solid var(--tm-line);background:transparent;color:var(--ui-text-secondary);
  font:inherit;font-size:11px;line-height:15px;padding:4px 9px;border-radius:999px;cursor:pointer}
.tm-chip:hover{background:var(--chrome-action-hover);color:var(--ui-text-primary)}
.tm-chip[data-active=true]{border-color:var(--ui-accent);color:var(--ui-accent);
  background:color-mix(in srgb,var(--ui-accent) 12%,transparent)}
.tm-btn{appearance:none;border:1px solid var(--tm-line);background:transparent;color:var(--ui-text-secondary);
  font:inherit;font-size:11px;line-height:15px;padding:4px 10px;border-radius:6px;cursor:pointer}
.tm-btn:hover:not(:disabled){background:var(--chrome-action-hover);color:var(--ui-text-primary)}
.tm-btn:disabled{opacity:.5;cursor:default}
.tm-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.tm-kpi{border:1px solid var(--tm-line);border-radius:10px;padding:11px 13px;
  background:color-mix(in srgb,var(--ui-text-primary) 2.5%,transparent)}
.tm-kpi-label{font-size:10.5px;line-height:14px;letter-spacing:.05em;text-transform:uppercase;color:var(--ui-text-tertiary)}
.tm-kpi-value{margin-top:5px;font-size:21px;line-height:26px;font-weight:600;font-variant-numeric:tabular-nums}
.tm-kpi-note{margin-top:2px;font-size:10.5px;line-height:14px;color:var(--ui-text-quaternary)}
.tm-card{border:1px solid var(--tm-line);border-radius:10px;background:color-mix(in srgb,var(--ui-text-primary) 2%,transparent);
  padding:14px 16px 12px}
.tm-card-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}
.tm-card-title{margin:0;font-size:12.5px;line-height:17px;font-weight:600}
.tm-card-note{font-size:10.5px;line-height:14px;color:var(--ui-text-quaternary)}
.tm-legend{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:9px 0 2px}
.tm-legend-item{display:inline-flex;align-items:center;gap:5px;font-size:10.5px;line-height:14px;color:var(--ui-text-tertiary)}
.tm-swatch{width:9px;height:9px;border-radius:2px;display:inline-block}
.tm-chart{display:block;width:100%;height:auto;overflow:visible}
.tm-grid-line{stroke:color-mix(in srgb,var(--ui-text-primary) 9%,transparent);stroke-width:1}
.tm-axis{fill:var(--ui-text-quaternary);font-size:10px;font-family:var(--font-mono,monospace)}
.tm-bar{transition:opacity .12s ease}
.tm-bar[data-dim=true]{opacity:.35}
.tm-readout{min-height:16px;margin-top:2px;font-size:11px;line-height:16px;color:var(--ui-text-secondary);
  font-variant-numeric:tabular-nums}
.tm-readout strong{color:var(--ui-text-primary);font-weight:600}
.tm-two{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.tm-row{display:flex;align-items:center;gap:10px;padding:7px 0;border-top:1px solid var(--tm-line-faint)}
.tm-row:first-of-type{border-top:0}
.tm-row-name{font-size:11.5px;line-height:16px;color:var(--ui-text-primary);min-width:0;flex:0 0 132px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tm-row-bar{height:7px;border-radius:4px;flex:1 1 auto;min-width:40px;
  background:color-mix(in srgb,var(--ui-text-primary) 7%,transparent);overflow:hidden}
.tm-row-fill{height:100%;border-radius:4px;background:var(--ui-accent)}
.tm-row-val{font-size:11px;line-height:16px;color:var(--ui-text-secondary);font-variant-numeric:tabular-nums;
  min-width:74px;text-align:right;flex:0 0 auto}
.tm-row-share{font-size:10.5px;line-height:16px;color:var(--ui-text-quaternary);min-width:38px;text-align:right}
.tm-acct{display:flex;align-items:flex-start;gap:12px;padding:12px 0;border-top:1px solid var(--tm-line-faint);flex-wrap:wrap}
.tm-acct:first-of-type{border-top:0}
.tm-acct-main{flex:1 1 220px;min-width:0}
.tm-acct-name{font-size:12px;line-height:17px;color:var(--ui-text-primary);display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.tm-acct-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:260px}
.tm-tag{font-size:9.5px;line-height:13px;letter-spacing:.04em;text-transform:uppercase;padding:1px 6px;border-radius:999px;
  border:1px solid var(--tm-line);color:var(--ui-text-tertiary)}
.tm-tag[data-tone=subscription]{border-color:color-mix(in srgb,var(--ui-accent) 45%,transparent);color:var(--ui-accent)}
.tm-acct-meta{font-size:10.5px;line-height:15px;color:var(--ui-text-quaternary);margin-top:3px;font-variant-numeric:tabular-nums}
.tm-select{appearance:none;border:1px solid var(--tm-line);background:var(--ui-bg-editor);color:var(--ui-text-secondary);
  font:inherit;font-size:11px;line-height:15px;padding:4px 22px 4px 7px;border-radius:6px;cursor:pointer;
  background-image:linear-gradient(45deg,transparent 50%,var(--ui-text-tertiary) 50%),linear-gradient(135deg,var(--ui-text-tertiary) 50%,transparent 50%);
  background-position:calc(100% - 11px) 8px,calc(100% - 7px) 8px;background-size:4px 4px,4px 4px;background-repeat:no-repeat}
.tm-acct-limits{flex:1 1 260px;min-width:220px;display:flex;flex-direction:column;gap:5px}
.tm-window{display:flex;align-items:center;gap:8px}
.tm-window-label{font-size:10.5px;line-height:14px;color:var(--ui-text-tertiary);flex:0 0 96px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tm-window-track{height:6px;border-radius:3px;flex:1 1 auto;min-width:50px;
  background:color-mix(in srgb,var(--ui-text-primary) 8%,transparent);overflow:hidden}
.tm-window-fill{height:100%;border-radius:3px;background:var(--ui-accent)}
.tm-window-fill[data-warn=true]{background:color-mix(in srgb,var(--ui-accent) 70%,#d9534f)}
.tm-window-fill[data-full=true]{background:#d9534f}
.tm-window-pct{font-size:10.5px;line-height:14px;color:var(--ui-text-secondary);min-width:42px;text-align:right;
  font-variant-numeric:tabular-nums}
.tm-window-reset{font-size:10px;line-height:14px;color:var(--ui-text-quaternary);min-width:0;flex:0 0 92px;text-align:right}
.tm-window-wrap{display:flex;flex-direction:column;gap:1px}
.tm-window-trend{font-size:10px;line-height:14px;color:var(--ui-text-quaternary);padding-left:104px;font-variant-numeric:tabular-nums}
.tm-peer-row{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding-top:6px}
.tm-hint{font-size:10.5px;line-height:15px;color:var(--ui-text-quaternary)}
.tm-error{border:1px solid color-mix(in srgb,#d9534f 45%,transparent);border-radius:8px;padding:10px 12px;
  font-size:11.5px;line-height:17px;color:var(--ui-text-secondary)}
.tm-error strong{color:#e08a86;font-weight:600}
.tm-empty{padding:26px 4px;text-align:center;font-size:11.5px;line-height:17px;color:var(--ui-text-tertiary)}
.tm-foot{font-size:10px;line-height:15px;color:var(--ui-text-quaternary)}
.tm-chip-row{display:flex;align-items:center;gap:6px}
.tm-input{appearance:none;border:1px solid var(--tm-line);background:color-mix(in srgb,var(--ui-text-primary) 4%,transparent);
  color:var(--ui-text-primary);font:inherit;font-size:11px;line-height:15px;padding:4px 8px;border-radius:6px;min-width:180px}
.tm-input:focus{outline:1px solid var(--ui-accent);outline-offset:-1px}
.tm-remote-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding-top:8px}
.tm-remote-status{font-size:10.5px;line-height:15px;color:var(--ui-text-quaternary);padding-top:6px}
.tm-stack-row{display:flex;align-items:center;gap:6px;margin-left:2px}
.tm-stack-label{font-size:10px;line-height:15px;letter-spacing:.05em;text-transform:uppercase;color:var(--ui-text-quaternary);margin-right:2px}
`

// ── helpers ────────────────────────────────────────────────────────────────────

const pad2 = (n) => (n < 10 ? `0${n}` : String(n))

const dayKey = (date) => `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function shortDay(date) {
  return `${date.getDate()} ${MONTHS[date.getMonth()]}`
}

function longDay(key) {
  const [year, month, day] = key.split('-').map(Number)
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}`
}

function monthLabel(key) {
  const [year, month] = key.split('-').map(Number)
  return `${MONTHS[Number(month) - 1]} ${String(year).slice(2)}`
}

function num(value) {
  return Number(value) || 0
}

function exact(value) {
  return num(value).toLocaleString()
}

function usd(value) {
  const amount = num(value)
  if (amount > 0 && amount < 1) return `$${amount.toFixed(3)}`
  return `$${amount.toFixed(2)}`
}

function compact(value) {
  return compactNumber(num(value))
}

function resetLabel(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const delta = date.getTime() - Date.now()
  if (delta <= 0) return 'reset due'
  const hours = delta / 3600000
  if (hours < 36) return `resets in ${Math.max(1, Math.round(hours))}h`
  return `resets ${date.getDate()} ${MONTHS[date.getMonth()]}`
}

function agoLabel(epochSeconds) {
  const stamp = num(epochSeconds)
  if (!stamp) return 'never synced'
  const minutes = Math.max(0, Math.round((Date.now() / 1000 - stamp) / 60))
  if (minutes < 1) return 'synced just now'
  if (minutes < 60) return `synced ${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `synced ${hours}h ago`
  return `synced ${Math.round(hours / 24)}d ago`
}

/** The series the chart stacks, for the active dimension. */
function resolveSeries(data, stackBy) {
  if (stackBy === 'class') {
    return CLASSES.map((tokenClass) => ({ ...tokenClass }))
  }
  const rows =
    stackBy === 'provider'
      ? data.by_provider || []
      : stackBy === 'source'
        ? data.by_source || []
        : data.by_profile || []
  const key = stackBy === 'provider' ? 'provider' : stackBy === 'source' ? 'source' : 'profile'
  const ranked = rows
    .map((row) => ({ name: String(row[key]), tokens: num(row.tokens) }))
    .filter((row) => row.tokens > 0)
    .sort((a, b) => b.tokens - a.tokens)
  const top = ranked.slice(0, 6)
  const series = top.map((row, index) => ({
    key: row.name,
    label: stackBy === 'source' ? sourceLabel(row.name) : row.name,
    cssVar: CATEGORICAL[index % CATEGORICAL.length]
  }))
  if (ranked.length > top.length) {
    series.push({ key: '__other', label: 'Other', cssVar: CATEGORICAL[6] })
  }
  return series
}

/**
 * Fill the window so the chart spans the selected range, gaps included, and
 * attach one value per series to every bucket.
 */
function buildBuckets(data, days, monthly, stackBy, series) {
  const daily = data.daily || []
  const known = new Set(series.map((entry) => entry.key))
  const source =
    stackBy === 'provider'
      ? data.by_day_provider || []
      : stackBy === 'profile'
        ? data.by_day_profile || []
        : stackBy === 'source'
          ? data.by_day_source || []
          : []
  const nameKey = stackBy === 'provider' ? 'provider' : stackBy === 'source' ? 'source' : 'profile'
  // Bucket key is the day, or the month once the range rolls up.
  const prefixLength = monthly ? 7 : 10

  const classesByBucket = new Map()
  for (const row of daily) {
    const prefix = String(row.day).slice(0, prefixLength)
    const bucket = classesByBucket.get(prefix) || {
      input: 0,
      output: 0,
      reasoning: 0,
      cache_read: 0,
      cache_write: 0,
      calls: 0,
      sessions: 0
    }
    bucket.input += num(row.input)
    bucket.output += num(row.output)
    bucket.reasoning += num(row.reasoning)
    bucket.cache_read += num(row.cache_read)
    bucket.cache_write += num(row.cache_write)
    bucket.calls += num(row.calls)
    bucket.sessions += num(row.sessions)
    classesByBucket.set(prefix, bucket)
  }

  // Per-dimension totals onto the same bucket key (provider / profile).
  const dimension = new Map()
  for (const row of source) {
    const prefix = String(row.day).slice(0, prefixLength)
    const name = String(row[nameKey])
    const key = known.has(name) ? name : '__other'
    dimension.set(`${prefix}|${key}`, (dimension.get(`${prefix}|${key}`) || 0) + num(row.tokens))
  }

  const makeBucket = (key, label, title) => {
    const values = {}
    for (const entry of series) values[entry.key] = 0
    const classes = classesByBucket.get(key)
    if (stackBy === 'class') {
      if (classes) {
        for (const tokenClass of CLASSES) values[tokenClass.key] = classes[tokenClass.key]
      }
    } else {
      for (const entry of series) values[entry.key] = dimension.get(`${key}|${entry.key}`) || 0
    }
    const total = Object.values(values).reduce((sum, value) => sum + num(value), 0)
    return {
      key,
      label,
      title,
      values,
      total,
      calls: classes ? classes.calls : 0,
      sessions: classes ? classes.sessions : 0,
      hasData: Boolean(classes) || total > 0
    }
  }

  if (monthly) {
    const keys = new Set([
      ...classesByBucket.keys(),
      ...[...dimension.keys()].map((entry) => entry.split('|')[0])
    ])
    return [...keys].sort().map((key) => makeBucket(key, monthLabel(key), monthLabel(key)))
  }

  const today = new Date()
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (days - 1))
  const buckets = []
  for (let index = 0; index < days; index += 1) {
    const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + index)
    const key = dayKey(date)
    buckets.push(makeBucket(key, shortDay(date), longDay(key)))
  }
  return buckets
}

// ── chart ──────────────────────────────────────────────────────────────────────

const W = 1000
const H = 260
const PAD = { top: 12, right: 8, bottom: 24, left: 52 }

function Axis({ max }) {
  const innerH = H - PAD.top - PAD.bottom
  const ticks = [0, 0.5, 1]
  return jsxs('g', {
    children: ticks.map((fraction) => {
      const y = PAD.top + innerH - fraction * innerH
      return jsxs(
        'g',
        {
          children: [
            jsx('line', {
              className: 'tm-grid-line',
              x1: PAD.left,
              x2: W - PAD.right,
              y1: y,
              y2: y
            }),
            jsx('text', {
              className: 'tm-axis',
              x: PAD.left - 8,
              y: y + 3,
              textAnchor: 'end',
              children: compact(max * fraction)
            })
          ]
        },
        `tick-${fraction}`
      )
    })
  })
}

function Chart({ buckets, series, hovered, onHover }) {
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const max = Math.max(1, ...buckets.map((bucket) => bucket.total))
  const step = innerW / Math.max(1, buckets.length)
  const gap = buckets.length > 180 ? 0.12 : buckets.length > 60 ? 0.2 : 0.32
  const barW = Math.max(1, step * (1 - gap))

  const labelEvery = Math.max(1, Math.ceil(buckets.length / 6))
  const labels = buckets.filter(
    (_, index) => index === buckets.length - 1 || index % labelEvery === 0
  )

  return jsxs('svg', {
    className: 'tm-chart',
    viewBox: `0 0 ${W} ${H}`,
    role: 'img',
    'aria-label': 'Token consumption over time, stacked',
    children: [
      jsx(Axis, { max }),
      jsxs(
        'g',
        {
          children: buckets.map((bucket, index) => {
            const x = PAD.left + index * step + (step - barW) / 2
            let cursor = PAD.top + innerH
            const dim = hovered !== null && hovered !== index
            const segments = series.map((entry) => {
              const value = num(bucket.values[entry.key])
              if (value <= 0) return null
              const height = (value / max) * innerH
              cursor -= height
              return jsx(
                'rect',
                {
                  className: 'tm-bar',
                  'data-dim': dim,
                  x,
                  y: cursor,
                  width: barW,
                  height,
                  fill: `var(${entry.cssVar})`,
                  shapeRendering: 'crispEdges'
                },
                `${bucket.key}-${entry.key}`
              )
            })
            return jsxs(
              'g',
              {
                children: [
                  ...segments,
                  jsx('rect', {
                    x: PAD.left + index * step,
                    y: PAD.top,
                    width: step,
                    height: innerH,
                    fill: 'transparent',
                    onMouseEnter: () => onHover(index),
                    onMouseLeave: () => onHover(null)
                  })
                ]
              },
              bucket.key
            )
          })
        }
      ),
      jsxs(
        'g',
        {
          children: labels.map((bucket) => {
            const index = buckets.indexOf(bucket)
            return jsx(
              'text',
              {
                className: 'tm-axis',
                x: PAD.left + index * step + step / 2,
                y: H - 7,
                textAnchor: 'middle',
                children: bucket.label
              },
              `label-${bucket.key}`
            )
          })
        }
      )
    ]
  })
}

// ── pieces ─────────────────────────────────────────────────────────────────────

function Kpi({ label, value, note }) {
  return jsxs('div', {
    className: 'tm-kpi',
    children: [
      jsx('div', { className: 'tm-kpi-label', children: label }),
      jsx('div', { className: 'tm-kpi-value', children: value }),
      note ? jsx('div', { className: 'tm-kpi-note', children: note }) : null
    ]
  })
}

function BarRows({ rows, nameKey, totals, empty, labelFor }) {
  const visible = rows.filter((row) => num(row.tokens) > 0).slice(0, 8)
  const peak = Math.max(1, ...visible.map((row) => num(row.tokens)))
  const label = (row) => {
    if (labelFor) return labelFor(row)
    const raw = String(row[nameKey])
    return nameKey === 'profile' ? sourceLabel(raw) : raw
  }
  if (visible.length === 0) {
    return jsx('div', { className: 'tm-empty', children: empty })
  }
  return jsxs('div', {
    children: visible.map((row) =>
      jsxs(
        'div',
        {
          className: 'tm-row',
          children: [
            jsx('div', {
              className: 'tm-row-name',
              title: label(row),
              children: label(row)
            }),
            jsx('div', {
              className: 'tm-row-bar',
              children: jsx('div', {
                className: 'tm-row-fill',
                style: { width: `${Math.max(2, (num(row.tokens) / peak) * 100)}%` }
              })
            }),
            jsx('div', { className: 'tm-row-val', children: compact(row.tokens) }),
            jsx('div', {
              className: 'tm-row-share',
              children: totals > 0 ? `${Math.round((num(row.tokens) / totals) * 100)}%` : '—'
            })
          ]
        },
        String(row[nameKey])
      )
    )
  })
}

function ModelRows({ models }) {
  const rows = models.slice(0, 6)
  if (rows.length === 0) {
    return jsx('div', { className: 'tm-empty', children: 'No model usage in this window.' })
  }
  return jsxs('div', {
    children: rows.map((row) =>
      jsxs(
        'div',
        {
          className: 'tm-row',
          children: [
            jsx('div', {
              className: 'tm-row-name',
              title: `${row.model} · ${row.provider}`,
              children: row.model
            }),
            jsx('div', {
              className: 'tm-row-val',
              style: { minWidth: '58px' },
              children: compact(row.tokens)
            }),
            jsx('div', { className: 'tm-row-share', children: `${exact(row.calls)} calls` })
          ]
        },
        `${row.model}-${row.provider}`
      )
    )
  })
}

function TaskRows({ tasks, totals }) {
  const rows = tasks.slice(0, 6)
  const peak = Math.max(1, ...rows.map((row) => num(row.tokens)))
  if (rows.length === 0) {
    return jsx('div', { className: 'tm-empty', children: 'No task breakdown in this window.' })
  }
  return jsxs('div', {
    children: rows.map((row) =>
      jsxs(
        'div',
        {
          className: 'tm-row',
          children: [
            jsx('div', {
              className: 'tm-row-name',
              title: row.task,
              children: row.task
            }),
            jsx('div', {
              className: 'tm-row-bar',
              children: jsx('div', {
                className: 'tm-row-fill',
                style: { width: `${Math.max(2, (num(row.tokens) / peak) * 100)}%` }
              })
            }),
            jsx('div', { className: 'tm-row-val', children: compact(row.tokens) }),
            jsx('div', {
              className: 'tm-row-share',
              children: totals > 0 ? `${Math.round((num(row.tokens) / totals) * 100)}%` : '—'
            })
          ]
        },
        row.task
      )
    )
  })
}

function WindowBar({ window }) {
  const used = num(window.used_percent)
  const clamped = Math.max(0, Math.min(100, used))
  return jsxs('div', {
    className: 'tm-window',
    children: [
      jsx('div', { className: 'tm-window-label', title: window.label, children: window.label }),
      jsx('div', {
        className: 'tm-window-track',
        children: jsx('div', {
          className: 'tm-window-fill',
          'data-warn': clamped >= 75 && clamped < 100,
          'data-full': clamped >= 100,
          style: { width: `${Math.max(1, clamped)}%` }
        })
      }),
      jsx('div', { className: 'tm-window-pct', children: `${Math.round(used)}%` }),
      jsx('div', { className: 'tm-window-reset', children: resetLabel(window.resets_at) })
    ]
  })
}

function AccountRow({ account, onMode }) {
  const [saving, setSaving] = useState(false)
  const limits = account.limits
  const windows = limits && Array.isArray(limits.windows) ? limits.windows : []
  const modeTone = account.mode === 'subscription' ? 'subscription' : 'plain'

  const change = async (event) => {
    const mode = event.target.value
    setSaving(true)
    try {
      await onMode(account.key, mode)
    } finally {
      setSaving(false)
    }
  }

  return jsxs('div', {
    className: 'tm-acct',
    children: [
      jsxs('div', {
        className: 'tm-acct-main',
        children: [
          jsxs('div', {
            className: 'tm-acct-name',
            children: [
              jsx('span', { className: 'tm-acct-label', children: account.label }),
              jsx('span', { className: 'tm-tag', 'data-tone': modeTone, children: account.provider }),
              account.auth_type
                ? jsx('span', { className: 'tm-tag', children: account.auth_type })
                : null
            ]
          }),
          jsxs('div', {
            className: 'tm-acct-meta',
            children: [
              `30d · ${compact(account.usage_30d.tokens)} tokens · ${exact(account.usage_30d.calls)} calls`,
              num(account.usage_30d.cost_est) > 0
                ? ` · ${usd(account.usage_30d.cost_est)} est.`
                : ' · no billable spend',
              num(account.requests) > 0 ? ` · ${exact(account.requests)} requests lifetime` : ''
            ]
          })
        ]
      }),
      jsx('select', {
        className: 'tm-select',
        value: account.mode,
        disabled: saving,
        'aria-label': `Spend mode for ${account.label}`,
        onChange: change,
        children: MODE_OPTIONS.map((option) =>
          jsx('option', { value: option.value, children: option.label }, option.value)
        )
      }),
      jsxs('div', {
        className: 'tm-acct-limits',
        children:
          windows.length > 0
            ? windows.map((window) => {
                const trend = (account.trends || []).find(
                  (entry) => String(entry.window).toLowerCase() === String(window.label).toLowerCase()
                )
                const parts = []
                if (trend && num(trend.percent_per_day) > 0) {
                  parts.push(`▲ ${num(trend.percent_per_day).toFixed(2)}%/day`)
                  if (trend.days_to_cap) parts.push(`cap in ${trend.days_to_cap}d`)
                  if (trend.tokens_per_percent) {
                    parts.push(`~${compact(trend.tokens_per_percent)} tokens per 1%`)
                  }
                }
                return jsxs(
                  'div',
                  {
                    className: 'tm-window-wrap',
                    children: [
                      jsx(WindowBar, { window }),
                      parts.length > 0
                        ? jsx('div', { className: 'tm-window-trend', children: parts.join(' · ') })
                        : null
                    ]
                  },
                  `${account.key}-${window.label}-${window.scope}`
                )
              })
            : [
                jsx('div', {
                  className: 'tm-hint',
                  children:
                    account.live_limits_supported === false
                      ? 'No live limit source for this provider. Set the mode by hand.'
                      : 'Checking provider limits…'
                })
              ]
      })
    ]
  })
}

// ── page ───────────────────────────────────────────────────────────────────────

function Page({ ctx }) {
  const [days, setDays] = useState(90)
  const [stackBy, setStackBy] = useState('class')
  const [hovered, setHovered] = useState(null)
  const queryClient = useQueryClient()

  const summary = useQuery({
    queryKey: ['token-master', 'summary', days],
    queryFn: () => ctx.rest(`/summary?days=${days}`),
    staleTime: 30000
  })
  const accounts = useQuery({
    queryKey: ['token-master', 'accounts'],
    queryFn: () => ctx.rest('/accounts'),
    staleTime: 60000
  })

  const data = summary.data
  const monthly = days >= 180
  const series = useMemo(() => {
    if (!data || !data.available) return []
    return resolveSeries(data, stackBy)
  }, [data, stackBy])
  const buckets = useMemo(() => {
    if (!data || !data.available) return []
    return buildBuckets(data, days, monthly, stackBy, series)
  }, [data, days, monthly, stackBy, series])

  const totals = data && data.totals ? data.totals : null
  const profileCount = data && Array.isArray(data.profiles) ? data.profiles.length : 0
  const sources = data && Array.isArray(data.sources) ? data.sources : []
  const hasHarness = sources.some((entry) => entry.id === 'deepseek-harness')
  const sourceSummary = hasHarness
    ? `${profileCount} Hermes profiles + DeepSeek Harness`
    : `${profileCount} Hermes profiles`
  const hoveredBucket = hovered !== null && buckets[hovered] ? buckets[hovered] : null

  const saveMode = async (key, mode) => {
    try {
      await ctx.rest('/settings', { method: 'PUT', body: { accounts: { [key]: { mode } } } })
      await queryClient.invalidateQueries({ queryKey: ['token-master', 'accounts'] })
      host.notify?.({ kind: 'info', message: 'Token Master: spend mode saved.' })
    } catch (error) {
      host.notifyError?.(String(error && error.message ? error.message : error))
      throw error
    }
  }

  const refreshLimits = async () => {
    try {
      await ctx.rest('/accounts?refresh=true')
      await queryClient.invalidateQueries({ queryKey: ['token-master', 'accounts'] })
    } catch (error) {
      host.notifyError?.(String(error && error.message ? error.message : error))
    }
  }

  // Quota windows cost a provider round-trip, so the card paints from the warm
  // cache first and then fills itself in once, without needing a click.
  const autoRefreshed = useRef(false)
  useEffect(() => {
    if (autoRefreshed.current) return
    const list = (accounts.data && accounts.data.accounts) || []
    if (list.length === 0) return
    const missing = list.some(
      (account) =>
        !(account.limits && Array.isArray(account.limits.windows) && account.limits.windows.length > 0)
    )
    if (!missing) return
    autoRefreshed.current = true
    void refreshLimits()
  }, [accounts.data])

  const [remoteDraft, setRemoteDraft] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [peers, setPeers] = useState(null)
  const remoteHosts =
    (accounts.data && accounts.data.settings && accounts.data.settings.remote_hosts) || []
  const remoteStatus = data && Array.isArray(data.remote) ? data.remote : []
  const draft = remoteDraft === null ? remoteHosts.join(', ') : remoteDraft

  const discoverMachines = async () => {
    try {
      const result = await ctx.rest('/machines')
      const online = (result.tailscale || []).filter((peer) => peer.online && !peer.self)
      setPeers(online)
    } catch (error) {
      host.notifyError?.(String(error && error.message ? error.message : error))
    }
  }

  const addPeer = (hostName) => {
    const current = draft
      .split(',')
      .map((entry) => entry.trim())
      .filter(Boolean)
    if (!current.includes(hostName)) {
      setRemoteDraft([...current, hostName].join(', '))
    }
  }

  const saveRemoteHosts = async () => {
    const hosts = draft
      .split(',')
      .map((entry) => entry.trim())
      .filter(Boolean)
    try {
      await ctx.rest('/settings', { method: 'PUT', body: { remote_hosts: hosts } })
      setRemoteDraft(null)
      await queryClient.invalidateQueries({ queryKey: ['token-master', 'accounts'] })
      host.notify?.({
        kind: 'info',
        message: hosts.length
          ? `Token Master: ${hosts.length} remote machine(s) saved.`
          : 'Token Master: remote machines cleared.'
      })
    } catch (error) {
      host.notifyError?.(String(error && error.message ? error.message : error))
    }
  }

  const syncRemote = async () => {    setSyncing(true)
    try {
      const result = await ctx.rest('/collect', { method: 'POST', body: { days } })
      const hosts = (result.hosts || []).filter(Boolean)
      const failed = hosts.filter((entry) => !entry.ok)
      await queryClient.invalidateQueries({ queryKey: ['token-master', 'summary', days] })
      await queryClient.invalidateQueries({ queryKey: ['token-master', 'accounts'] })
      if (failed.length > 0) {
        host.notifyError?.(`Token Master: ${failed[0].host} failed — ${failed[0].error || 'unknown error'}`)
      } else {
        host.notify?.({
          kind: 'info',
          message: `Token Master: collected ${hosts.map((entry) => `${entry.host} (${entry.rows} rows)`).join(', ')}.`
        })
      }
    } catch (error) {
      host.notifyError?.(String(error && error.message ? error.message : error))
    } finally {
      setSyncing(false)
    }
  }

  // A cached remote collection goes stale; refresh it once per page visit, in
  // the background, so the chart is never silently a day old.
  const autoSynced = useRef(false)
  useEffect(() => {
    if (autoSynced.current || remoteHosts.length === 0) return
    const stale = remoteStatus.some(
      (entry) => !entry.cached || Date.now() / 1000 - num(entry.collected_at) > 3600
    )
    if (!stale) return
    autoSynced.current = true
    void syncRemote()
  }, [remoteStatus.length, remoteHosts.length])

  const header = jsxs('header', {
    className: 'tm-head',
    children: [
      jsxs('div', {
        children: [
          jsx('h1', { className: 'tm-title', children: 'Token Master' }),
          jsx('p', {
            className: 'tm-sub',
            children:
              profileCount > 0
                ? `Every token, every account, every day — ${sourceSummary}.`
                : 'Every token, every account, every day — one graph and the limits behind it.'
          })
        ]
      }),
      jsxs('div', {
        className: 'tm-actions',
        children: [
          jsxs('div', {
            className: 'tm-chip-row',
            children: RANGES.map((range) =>
              jsx(
                'button',
                {
                  type: 'button',
                  className: 'tm-chip',
                  'data-active': range.days === days,
                  onClick: () => setDays(range.days),
                  children: range.label
                },
                range.label
              )
            )
          }),
          jsx('button', {
            type: 'button',
            className: 'tm-btn',
            disabled: summary.isFetching,
            onClick: () => summary.refetch(),
            children: summary.isFetching ? 'Refreshing…' : 'Refresh'
          })
        ]
      })
    ]
  })

  if (summary.isError) {
    return jsxs('div', {
      className: 'tm-page',
      children: [
        jsx('div', { className: 'tm-wrap', children: header }),
        jsx('div', {
          className: 'tm-wrap',
          children: jsxs('div', {
            className: 'tm-error',
            children: [
              jsx('strong', { children: 'Token Master could not read its backend. ' }),
              jsx('div', {
                children: String(
                  summary.error && summary.error.message ? summary.error.message : summary.error
                )
              }),
              jsx('div', {
                className: 'tm-hint',
                children:
                  'The backend mounts at /api/plugins/token-master. Run `hermes plugins enable token-master` if it is not enabled for this profile.'
              })
            ]
          })
        })
      ]
    })
  }

  const kpis = jsxs('div', {
    className: 'tm-kpis',
    children: [
      jsx(Kpi, {
        label: 'Total tokens',
        value: totals ? compact(totals.tokens) : '—',
        note: totals ? `${exact(totals.tokens)} incl. cache` : ''
      }),
      jsx(Kpi, {
        label: 'Billable (in + out)',
        value: totals ? compact(num(totals.input) + num(totals.output)) : '—',
        note: totals ? 'excludes cache reads — compare this to a provider dashboard' : ''
      }),
      jsx(Kpi, {
        label: 'API calls',
        value: totals ? compact(totals.calls) : '—',
        note: totals ? `${exact(totals.active_days)} active days` : ''
      }),
      jsx(Kpi, {
        label: 'Est. spend',
        value: totals ? usd(totals.cost_est) : '—',
        note: totals && num(totals.cost_est) === 0 ? 'free-tier / subscription routes' : 'provider list price'
      }),
      jsx(Kpi, {
        label: 'Cache share',
        value:
          totals && num(totals.tokens) > 0
            ? `${Math.round((num(totals.cache_read) / num(totals.tokens)) * 100)}%`
            : '—',
        note: totals ? `${compact(totals.cache_read)} cache reads` : ''
      })
    ]
  })

  const legend = jsxs('div', {
    className: 'tm-legend',
    children: series.map((entry) =>
      jsxs(
        'span',
        {
          className: 'tm-legend-item',
          children: [
            jsx('span', { className: 'tm-swatch', style: { background: `var(${entry.cssVar})` } }),
            jsx('span', { children: entry.label })
          ]
        },
        entry.key
      )
    )
  })

  const readout = hoveredBucket
    ? jsxs('div', {
        className: 'tm-readout',
        children: [
          jsx('strong', { children: hoveredBucket.title }),
          ` · ${compact(hoveredBucket.total)} tokens`,
          ...series
            .map((entry) => ({ entry, value: num(hoveredBucket.values[entry.key]) }))
            .filter((item) => item.value > 0)
            .sort((a, b) => b.value - a.value)
            .slice(0, 4)
            .map((item) => ` · ${item.entry.label} ${compact(item.value)}`),
          ` · ${exact(hoveredBucket.calls)} calls`
        ]
      })
    : jsx('div', {
        className: 'tm-readout',
        children: monthly
          ? 'Monthly totals — hover a column for the exact split.'
          : 'Hover a column for the exact split.'
      })

  const chartCard = jsxs('section', {
    className: 'tm-card',
    children: [
      jsxs('div', {
        className: 'tm-card-head',
        children: [
          jsxs('div', {
            children: [
              jsx('h2', {
                className: 'tm-card-title',
                children: monthly ? 'Tokens per month' : 'Tokens per day'
              }),
              jsx('span', {
                className: 'tm-card-note',
                children: monthly
                  ? `Stacked by ${stackBy === 'class' ? 'token class' : stackBy} · local months · all profiles`
                  : `Stacked by ${stackBy === 'class' ? 'token class' : stackBy} · local days · all profiles`
              })
            ]
          }),
          jsxs('div', {
            className: 'tm-stack-row',
            children: [
              jsx('span', { className: 'tm-stack-label', children: 'stack' }),
              ...STACKS.map((stack) =>
                jsx(
                  'button',
                  {
                    type: 'button',
                    className: 'tm-chip',
                    'data-active': stack.key === stackBy,
                    onClick: () => {
                      setStackBy(stack.key)
                      setHovered(null)
                    },
                    children: stack.label
                  },
                  stack.key
                )
              )
            ]
          })
        ]
      }),
      legend,
      data && data.available === false
        ? jsx('div', {
            className: 'tm-empty',
            children: `No token accounting available: ${data.reason || 'unknown reason'}.`
          })
        : buckets.length > 0
          ? jsx(Chart, { buckets, series, hovered, onHover: setHovered })
          : jsx('div', { className: 'tm-empty', children: 'No token usage recorded in this window yet.' }),
      readout
    ]
  })

  const breakdownTop = jsxs('div', {
    className: 'tm-two',
    children: [
      jsxs('section', {
        className: 'tm-card',
        children: [
          jsxs('div', {
            className: 'tm-card-head',
            children: [
              jsx('h2', { className: 'tm-card-title', children: 'By provider' }),
              jsx('span', { className: 'tm-card-note', children: 'billing route Hermes recorded' })
            ]
          }),
          jsx(BarRows, {
            rows: data && data.by_provider ? data.by_provider : [],
            nameKey: 'provider',
            totals: totals ? num(totals.tokens) : 0,
            empty: 'No provider usage in this window.'
          })
        ]
      }),
      jsxs('section', {
        className: 'tm-card',
        children: [
          jsxs('div', {
            className: 'tm-card-head',
            children: [
              jsx('h2', { className: 'tm-card-title', children: 'By profile' }),
              jsx('span', {
                className: 'tm-card-note',
                children: `${profileCount} profiles · one database each`
              })
            ]
          }),
          jsx(BarRows, {
            rows: data && data.by_profile ? data.by_profile : [],
            nameKey: 'profile',
            totals: totals ? num(totals.tokens) : 0,
            empty: 'No profile usage in this window.'
          })
        ]
      })
    ]
  })

  const breakdownBottom = jsxs('div', {
    className: 'tm-two',
    children: [
      jsxs('section', {
        className: 'tm-card',
        children: [
          jsxs('div', {
            className: 'tm-card-head',
            children: [
              jsx('h2', { className: 'tm-card-title', children: 'Top models' }),
              jsx('span', { className: 'tm-card-note', children: 'main agent + auxiliary calls' })
            ]
          }),
          jsx(ModelRows, { models: data && data.by_model ? data.by_model : [] })
        ]
      }),
      jsxs('section', {
        className: 'tm-card',
        children: [
          jsxs('div', {
            className: 'tm-card-head',
            children: [
              jsx('h2', { className: 'tm-card-title', children: 'Billing mix' }),
              jsx('span', { className: 'tm-card-note', children: 'subscription-included vs pay-per-token' })
            ]
          }),
          jsx(BarRows, {
            rows: data && data.by_cost_status ? data.by_cost_status : [],
            nameKey: 'status',
            totals: totals ? num(totals.tokens) : 0,
            empty: 'No billing status recorded in this window.',
            labelFor: (row) => COST_LABELS[row.status] || row.status
          })
        ]
      }),
      jsxs('section', {
        className: 'tm-card',
        children: [
          jsxs('div', {
            className: 'tm-card-head',
            children: [
              jsx('h2', { className: 'tm-card-title', children: 'By task' }),
              jsx('span', { className: 'tm-card-note', children: 'main agent vs background work' })
            ]
          }),
          jsx(TaskRows, {
            tasks: data && data.by_task ? data.by_task : [],
            totals: totals ? num(totals.tokens) : 0
          })
        ]
      })
    ]
  })

  const accountData = accounts.data
  const accountRows = accounts.isError
    ? jsx('div', {
        className: 'tm-hint',
        children: 'Accounts unavailable — the credential pool could not be read.'
      })
    : !accountData
      ? jsx('div', { className: 'tm-hint', children: 'Loading accounts…' })
      : (accountData.accounts || []).length === 0
        ? jsx('div', { className: 'tm-empty', children: 'No accounts configured yet.' })
        : jsxs('div', {
            children: (accountData.accounts || []).map((account) =>
              jsx(AccountRow, { account, onMode: saveMode }, account.key)
            )
          })

  const accountsCard = jsxs('section', {
    className: 'tm-card',
    children: [
      jsxs('div', {
        className: 'tm-card-head',
        children: [
          jsxs('div', {
            children: [
              jsx('h2', { className: 'tm-card-title', children: 'Accounts & limits' }),
              jsx('span', {
                className: 'tm-card-note',
                children: 'Mark each credential as quota-backed, pay-per-token, or free.'
              })
            ]
          }),
          jsx('button', {
            type: 'button',
            className: 'tm-btn',
            disabled: accounts.isFetching,
            onClick: refreshLimits,
            children: accounts.isFetching ? 'Refreshing…' : 'Refresh limits'
          })
        ]
      }),
      accountRows
    ]
  })

  const remoteCard = jsxs('section', {
    className: 'tm-card',
    children: [
      jsxs('div', {
        className: 'tm-card-head',
        children: [
          jsxs('div', {
            children: [
              jsx('h2', { className: 'tm-card-title', children: 'Remote machines' }),
              jsx('span', {
                className: 'tm-card-note',
                children:
                  'SSH host names. The collector runs read-only on the other machine and its rows join the chart as their own source.'
              })
            ]
          }),
          jsx('button', {
            type: 'button',
            className: 'tm-btn',
            disabled: syncing || remoteHosts.length === 0,
            onClick: syncRemote,
            children: syncing ? 'Syncing…' : 'Sync now'
          })
        ]
      }),
      jsxs('div', {
        className: 'tm-remote-row',
        children: [
          jsx('input', {
            className: 'tm-input',
            value: draft,
            placeholder: 'edge-01, edge-02',
            'aria-label': 'Remote machine SSH hosts',
            onChange: (event) => setRemoteDraft(event.target.value)
          }),
          jsx('button', {
            type: 'button',
            className: 'tm-btn',
            onClick: saveRemoteHosts,
            children: 'Save hosts'
          })
        ]
      }),
      jsxs('div', {
        className: 'tm-peer-row',
        children: [
          jsx('button', {
            type: 'button',
            className: 'tm-btn',
            onClick: discoverMachines,
            children: 'Discover Tailscale'
          }),
          ...(peers || []).map((peer) =>
            jsx(
              'button',
              {
                type: 'button',
                className: 'tm-chip',
                title: `${peer.os || 'unknown'} · ${peer.ip || ''}`,
                onClick: () => addPeer(peer.host),
                children: `+ ${peer.host}`
              },
              peer.host
            )
          ),
          peers !== null && peers.length === 0
            ? jsx('span', { className: 'tm-hint', children: 'No other online peers.' })
            : null
        ]
      }),
      jsx('div', {
        className: 'tm-remote-status',
        children:
          remoteStatus.length === 0
            ? 'No remote machines configured — this chart covers this machine only.'
            : remoteStatus
                .map(
                  (entry) =>
                    `${entry.host}: ${entry.cached ? `${entry.rows || 0} rows, ${agoLabel(entry.collected_at)}` : 'never synced'}`
                )
                .join(' · ')
      })
    ]
  })

  const foot = jsxs('div', {
    className: 'tm-foot',
    children: [
      `Sources: Hermes token accounting (state.db · session_model_usage, ${profileCount} profiles)`,
      hasHarness ? ' + the DeepSeek Harness session ledger' : '',
      ', bucketed by each row’s last activity day. “Provider” is the billing route the tool used, so ',
      'harness and Hermes traffic on the same subscription land in one band. Quota windows come from the ',
      'provider API and cover every machine on that account, which token counts from one machine cannot.'
    ]
  })

  return jsxs('div', {
    className: 'tm-page',
    'data-token-master': true,
    children: [
      jsxs('div', {
        className: 'tm-wrap',
        children: [
          header,
          kpis,
          chartCard,
          breakdownTop,
          breakdownBottom,
          accountsCard,
          remoteCard,
          summary.isFetching ? jsx('div', { className: 'tm-hint', children: 'Updating…' }) : null,
          foot
        ]
      })
    ]
  })
}

// ── status-bar chip ────────────────────────────────────────────────────────────

function Chip({ ctx }) {
  const query = useQuery({
    queryKey: ['token-master', 'summary', 2],
    queryFn: () => ctx.rest('/summary?days=2'),
    staleTime: 120000
  })
  const data = query.data
  if (!data || !data.available || !Array.isArray(data.daily) || data.daily.length === 0) {
    return null
  }
  const today = dayKey(new Date())
  const row = data.daily.find((entry) => entry.day === today)
  if (!row) return null
  const tokens = num(row.tokens)
  if (tokens <= 0) return null
  return jsx('button', {
    type: 'button',
    className: 'tm-chip',
    title: `Token Master — ${exact(tokens)} tokens today`,
    onClick: () => host.navigate('/token-master'),
    children: `◫ ${compact(tokens)}`
  })
}

// ── registration ───────────────────────────────────────────────────────────────

export default {
  id: ID,
  name: 'Token Master',
  description:
    'Token spend analytics across every Hermes profile, provider and account — one daily graph plus the limits behind it.',
  register(ctx) {
    const style = document.createElement('style')
    style.textContent = CSS
    document.head.append(style)
    ctx.onDispose(() => style.remove())

    // Theme-safe fills: the class ramp derives from the active accent, while the
    // categorical ramp (provider / profile) stays fixed so a provider keeps one
    // colour as ranges change.
    const fills = document.createElement('style')
    fills.textContent = `:root{
      --tm-line:color-mix(in srgb,var(--ui-text-primary) 13%,transparent);
      --tm-line-faint:color-mix(in srgb,var(--ui-text-primary) 7%,transparent);
      --tm-fill-input:var(--ui-accent);
      --tm-fill-output:color-mix(in srgb,var(--ui-accent) 58%,var(--ui-bg-editor));
      --tm-fill-reasoning:color-mix(in srgb,var(--ui-text-primary) 46%,transparent);
      --tm-fill-cacheRead:color-mix(in srgb,var(--ui-text-primary) 24%,transparent);
      --tm-fill-cacheWrite:color-mix(in srgb,var(--ui-text-primary) 13%,transparent);
      --tm-cat-1:#4f9fd6;
      --tm-cat-2:#d79a4e;
      --tm-cat-3:#9a86d9;
      --tm-cat-4:#57b98c;
      --tm-cat-5:#cf7290;
      --tm-cat-6:#8494ab;
      --tm-cat-7:#b8a64f;
    }`
    document.head.append(fills)
    ctx.onDispose(() => fills.remove())

    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: '/token-master' },
        render: () => jsx(Page, { ctx })
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        order: 60,
        data: { codicon: 'graph', label: 'Token Master', path: '/token-master' }
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: {
          id: 'token-master.open',
          label: 'Open Token Master',
          keywords: ['token', 'spend', 'usage', 'cost', 'analytics', 'subscription'],
          run: () => host.navigate('/token-master')
        }
      },
      {
        id: 'today',
        area: STATUSBAR_AREAS.right,
        order: 90,
        render: () => jsx(Chip, { ctx })
      }
    ])
  }
}

// Pure aggregation helpers, exported for the dev harness in the repo (radio does the same).
export { buildBuckets, resolveSeries }

