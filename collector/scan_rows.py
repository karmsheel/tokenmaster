"""Token Master remote collector - reads one machine's ledgers and prints rows.

Runs with nothing installed (stdlib only), because the plugin streams it into a
remote Python over SSH:

    ssh <host> "python3 -" < collector/scan_rows.py

It never writes anything on the remote machine: Hermes profiles are opened with
a read-only SQLite URI and DeepSeek Harness session files are only read.

Output (one JSON object on stdout):

    {"host": "...", "days": 3, "collected_at": 1794..., "rows": [...], "errors": [...]}

Each row is one (day, provider, model) aggregate in the shape the plugin's
backend already consumes, so remote usage joins the local chart as its own
source instead of being averaged into it.
"""

import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
DSH = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
CUTOFF = time.time() - DAYS * 86400

TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens")
errors = []
rows = []


def day_of(timestamp):
    try:
        return datetime.fromtimestamp(float(timestamp)).date().isoformat()
    except (OSError, OverflowError, ValueError, TypeError):
        return ""


def emit(day, provider, model, tokens, calls, profile):
    if not day or sum(tokens.get(k, 0) for k in TOKEN_FIELDS) <= 0:
        return
    rows.append(
        {
            "day": day,
            "provider": str(provider or "unattributed"),
            "model": str(model or "unknown"),
            "profile": profile,
            "input": int(tokens.get("input_tokens", 0)),
            "output": int(tokens.get("output_tokens", 0)),
            "cache_read": int(tokens.get("cache_read_tokens", 0)),
            "cache_write": int(tokens.get("cache_write_tokens", 0)),
            "reasoning": int(tokens.get("reasoning_tokens", 0)),
            "calls": int(calls or 0),
        }
    )


def scan_hermes():
    dbs = [("default", HOME / "state.db")]
    profiles = HOME / "profiles"
    if profiles.is_dir():
        for child in sorted(profiles.iterdir()):
            if child.is_dir() and not child.name.startswith(".") and (child / "state.db").is_file():
                dbs.append((child.name, child / "state.db"))

    for name, db in dbs:
        if not db.is_file():
            continue
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT date(last_seen, 'unixepoch', 'localtime') AS day,
                       COALESCE(NULLIF(billing_provider, ''), 'unattributed') AS provider,
                       COALESCE(NULLIF(model, ''), 'unknown') AS model,
                       SUM(input_tokens) AS input_tokens,
                       SUM(output_tokens) AS output_tokens,
                       SUM(cache_read_tokens) AS cache_read_tokens,
                       SUM(cache_write_tokens) AS cache_write_tokens,
                       SUM(reasoning_tokens) AS reasoning_tokens,
                       SUM(COALESCE(api_call_count, 0)) AS calls
                FROM session_model_usage
                WHERE last_seen >= ?
                GROUP BY day, provider, model
                """,
                (CUTOFF,),
            )
            for record in cursor:
                row = dict(record)
                emit(row["day"], row["provider"], row["model"], row, row["calls"], name)
            conn.close()
        except Exception as exc:  # noqa: BLE001 - one unreadable profile must not stop the scan
            errors.append(f"hermes:{name}: {type(exc).__name__}: {exc}")


def scan_dsh():
    stores = sorted(DSH.glob("storages/*/sessions/*.json"))
    for path in stores:
        try:
            stat = path.stat()
            if stat.st_mtime < CUTOFF:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            atoms = (payload.get("record") or {}).get("rows") or {}
            usage = ((atoms.get("tokenUsage") or {}).get("val") or {}).get("totals")
            if not isinstance(usage, dict):
                continue
            last_used = ((atoms.get("modelSelection") or {}).get("val") or {}).get("lastUsed") or {}
            stats = (atoms.get("sessionStats") or {}).get("val") or {}
            tokens = {
                "input_tokens": int(usage.get("uncachedInputTokens") or 0),
                "output_tokens": int(usage.get("outputTokens") or 0),
                "cache_read_tokens": int(usage.get("cacheReadTokens") or 0),
                "cache_write_tokens": int(usage.get("cacheWriteTokens") or 0),
                "reasoning_tokens": 0,
            }
            emit(
                day_of(stat.st_mtime),
                last_used.get("provider") if isinstance(last_used, dict) else "unknown",
                last_used.get("model") if isinstance(last_used, dict) else "unknown",
                tokens,
                int(stats.get("steps") or 0),
                "deepseek-harness",
            )
        except Exception:  # noqa: BLE001 - skip an unreadable session file
            continue


scan_hermes()
scan_dsh()

print(
    json.dumps(
        {
            "host": os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "unknown"),
            "days": DAYS,
            "collected_at": time.time(),
            "rows": rows,
            "errors": errors[:10],
        }
    )
)
