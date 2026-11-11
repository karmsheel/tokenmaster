#!/usr/bin/env python3
"""Build token-usage dashboard data from Hermes state.db."""
import sqlite3, json, os, sys
from collections import defaultdict

DB = os.environ.get("HERMES_DB", r"C:\Users\karms\AppData\Local\hermes\state.db")
OUT = os.environ.get("DASH_OUT", r"C:\Users\karms\Projects\tokenmaster\dashboard_data.json")

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

def q(sql, params=()):
    return c.execute(sql, params).fetchall()

# ---- header totals ----
tot = q("""SELECT
  SUM(input_tokens) input_tokens,
  SUM(output_tokens) output_tokens,
  SUM(cache_read_tokens) cache_read,
  SUM(cache_write_tokens) cache_write,
  SUM(reasoning_tokens) reasoning_tokens,
  SUM(api_call_count) api_call_count,
  SUM(estimated_cost_usd) estimated_cost_usd,
  SUM(actual_cost_usd) actual_cost_usd
FROM session_model_usage""")[0]

# ---- daily series ----
daily = []
for r in q("""SELECT date(first_seen,'unixepoch') d,
  SUM(input_tokens) input_tokens,
  SUM(output_tokens) output_tokens,
  SUM(cache_read_tokens) cache_read,
  SUM(reasoning_tokens) reasoning_tokens,
  SUM(api_call_count) api_call_count,
  SUM(estimated_cost_usd) estimated_cost_usd
  FROM session_model_usage
  GROUP BY d ORDER BY d"""):
    daily.append({'date': r['d'],
                  'input_tokens': int(r['input_tokens'] or 0),
                  'output_tokens': int(r['output_tokens'] or 0),
                  'cache_read': int(r['cache_read'] or 0),
                  'reasoning_tokens': int(r['reasoning_tokens'] or 0),
                  'api_call_count': int(r['api_call_count'] or 0),
                  'estimated_cost_usd': (r['estimated_cost_usd'] or 0)})

# ---- top models by total tokens ----
models = []
for r in q("""SELECT model, SUM(input_tokens) input_tokens,
  SUM(output_tokens) output_tokens, SUM(cache_read_tokens) cache_read,
  SUM(api_call_count) calls, SUM(estimated_cost_usd) est,
  COUNT(*) sessions, COUNT(DISTINCT billing_provider) provs
  FROM session_model_usage GROUP BY model ORDER BY input_tokens DESC LIMIT 30"""):
    models.append({'model': r['model'],
                   'input_tokens': int(r['input_tokens'] or 0),
                   'output_tokens': int(r['output_tokens'] or 0),
                   'cache_read': int(r['cache_read'] or 0),
                   'calls': int(r['calls'] or 0),
                   'est_cost_usd': (r['est'] or 0),
                   'sessions': int(r['sessions'] or 0),
                   'providers': int(r['provs'] or 0)})

# ---- provider split (tokens = input+output) ----
provs = defaultdict(lambda: {'tokens': 0, 'calls': 0})
for r in q("""SELECT billing_provider, input_tokens, output_tokens, api_call_count
  FROM session_model_usage WHERE billing_provider != ''"""):
    p = r['billing_provider'] or 'unknown'
    provs[p]['tokens'] += (r['input_tokens'] or 0) + (r['output_tokens'] or 0)
    provs[p]['calls'] += r['api_call_count'] or 0
provider_rows = [{'provider': p, 'tokens': v['tokens'], 'calls': v['calls'],
                  'sessions': 0, 'models': 0}
                 for p, v in sorted(provs.items(), key=lambda kv: -kv[1]['tokens'])]

# ---- sessions summary ----
sess = q("""SELECT COUNT(*) total,
  MIN(started_at) min_ts, MAX(started_at) max_ts,
  SUM(input_tokens) input_tokens, SUM(output_tokens) output_tokens,
  SUM(api_call_count) api_calls
  FROM sessions WHERE started_at IS NOT NULL""")[0]
sessions_summary = {
    'total': sess['total'],
    'min_ts': sess['min_ts'],
    'max_ts': sess['max_ts'],
    'input_tokens': sess['input_tokens'],
    'output_tokens': sess['output_tokens'],
    'api_calls': sess['api_calls'],
}

# ---- cost by status ----
cost_status = defaultdict(lambda: {'count': 0, 'est': 0.0, 'act': 0.0})
for r in q("""SELECT cost_status, estimated_cost_usd, actual_cost_usd
  FROM session_model_usage"""):
    s = r['cost_status'] or 'unknown'
    cost_status[s]['count'] += 1
    cost_status[s]['est'] += r['estimated_cost_usd'] or 0
    cost_status[s]['act'] += r['actual_cost_usd'] or 0
cost_rows = [{'status': s, 'count': v['count'], 'estimated_cost_usd': v['est'],
              'actual_cost_usd': v['act']} for s, v in cost_status.items()]

# ---- recent 14 days (for a compact recent view) ----
recent = []  # [date, input, output, cache_read]
for r in q("""SELECT date(first_seen,'unixepoch') d,
  SUM(input_tokens) input, SUM(output_tokens) output, SUM(cache_read_tokens) cache_read
  FROM session_model_usage GROUP BY d ORDER BY d DESC LIMIT 14"""):
    recent.append({'date': r['d'], 'input': r['input'], 'output': r['output'],
                   'cache_read': r['cache_read']})

data = {
    'meta': {
        'db': DB,
        'generated_at': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
        'source_notes': 'session_model_usage aggregate from Hermes state.db',
    },
    'totals': {
        'input_tokens': tot['input_tokens'] or 0,
        'output_tokens': tot['output_tokens'] or 0,
        'cache_read': tot['cache_read'] or 0,
        'cache_write': tot['cache_write'] or 0,
        'reasoning_tokens': tot['reasoning_tokens'] or 0,
        'api_call_count': tot['api_call_count'] or 0,
        'estimated_cost_usd': round((tot['estimated_cost_usd'] or 0), 4),
        'actual_cost_usd': round((tot['actual_cost_usd'] or 0), 4),
    },
    'daily': daily,
    'models': models,
    'provider_split': provider_rows,
    'sessions': sessions_summary,
    'cost_by_status': cost_rows,
    'recent14': recent,
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=1)

t = data['totals']
print("Wrote", OUT)
print("totals:", {k: t[k] for k in ('input_tokens','output_tokens','cache_read','api_call_count','estimated_cost_usd','actual_cost_usd')})
print("daily points:", len(data['daily']), "models:", len(data['models']),
      "providers:", len(data['provider_split']), "sessions:", sessions_summary['total'],
      "cost statuses:", [(r['status'], r['count']) for r in data['cost_by_status']])
