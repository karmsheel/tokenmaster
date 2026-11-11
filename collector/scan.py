"""Read-only scan (runs on the remote machine via: ssh host python3 -).

Prints one JSON object with last-N-day token totals from every source this
machine has: Hermes profiles (state.db session_model_usage) and DeepSeek
Harness session ledgers. Never writes anything.
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
cutoff = time.time() - DAYS * 86400

out = {"host": os.uname().nodename, "days": DAYS, "hermes": {}, "dsh": {}, "totals": {}}


def open_ro(db):
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5.0)


def sum_rows(rows):
    keys = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens")
    tokens = {k: 0 for k in keys}
    providers = {}
    calls = 0
    for row in rows:
        for k in keys:
            tokens[k] += int(row.get(k) or 0)
        calls += int(row.get("api_call_count") or 0)
        provider = str(row.get("billing_provider") or "unattributed")
        providers[provider] = providers.get(provider, 0) + sum(int(row.get(k) or 0) for k in keys)
    tokens["total"] = sum(tokens[k] for k in keys)
    return {"tokens": tokens, "providers": providers, "calls": calls}


dbs = [("default", home / "state.db")]
prof = home / "profiles"
if prof.is_dir():
    for child in sorted(prof.iterdir()):
        if child.is_dir() and not child.name.startswith(".") and (child / "state.db").is_file():
            dbs.append((child.name, child / "state.db"))

hermes_total = 0
for name, db in dbs:
    try:
        conn = open_ro(db)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM session_model_usage WHERE last_seen >= ?", (cutoff,)
        )]
        conn.close()
    except Exception as exc:
        out["hermes"][name] = {"error": f"{type(exc).__name__}: {exc}"}
        continue
    summary = sum_rows(rows)
    out["hermes"][name] = summary
    hermes_total += summary["tokens"]["total"]

dsh_total = 0
dsh_home = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
for path in sorted(dsh_home.glob("storages/*/sessions/*.json")):
    try:
        if path.stat().st_mtime < cutoff:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        atoms = (payload.get("record") or {}).get("rows") or {}
        usage = ((atoms.get("tokenUsage") or {}).get("val") or {}).get("totals")
        if not isinstance(usage, dict):
            continue
        total = sum(int(usage.get(k) or 0) for k in (
            "uncachedInputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens"))
        if total <= 0:
            continue
        last = ((atoms.get("modelSelection") or {}).get("val") or {}).get("lastUsed") or {}
        provider = str(last.get("provider") or "unknown")
        bucket = out["dsh"].setdefault(provider, {"tokens": 0, "sessions": 0})
        bucket["tokens"] += total
        bucket["sessions"] += 1
        dsh_total += total
    except Exception:
        continue

out["totals"] = {"hermes": hermes_total, "dsh": dsh_total, "all": hermes_total + dsh_total}
print(json.dumps(out, indent=1))
