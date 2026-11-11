"""Token Master backend, mounted at ``/api/plugins/token-master/``.

Two jobs, both read-mostly:

* **History** — aggregate token accounting across *every* Hermes profile on this
  machine. Each profile keeps its own ``state.db``; a whole-machine spend view has
  to read the root home plus ``profiles/<name>/`` or it silently reports a
  fraction of the truth (a coding profile can hold more spend than the default
  one). Rows carry ``first_seen``/``last_seen``, every token class, and the
  billing route, so the series is derivable without touching a transcript.
* **Accounts** — the credential pool (``auth.json`` -> ``credential_pool``) plus
  whatever live allowance windows Hermes can fetch for a provider
  (``agent.account_usage``) and the user's own subscription/API-spend mode.

Every handler is ``async def`` and offloads blocking work (SQLite, network
allowance fetches) with ``asyncio.to_thread``: under the default
``plugins.isolation: in_process`` these handlers share the gateway event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Query

from hermes_constants import get_hermes_home, named_profile_home

logger = logging.getLogger(__name__)

router = APIRouter()

# Live allowance fetches hit a provider API; the page never pays for one on load
# (the app's own /usage fetches already warm the shared cache) and an explicit
# refresh dedupes across concurrent clicks.
_LIMIT_TTL_SECONDS = 300.0

_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)

_PROFILE_SKIP_PREFIXES = (".deleted", ".stale", ".")

_SETTINGS_VERSION = 1

# Sources this backend can read. Hermes is the only one with a billing route and
# a cost column; the others are "what tool made the call" so spend recorded
# outside Hermes is not silently missing from the total.
_SOURCE_HERMES = "hermes"
_SOURCE_DSH = "deepseek-harness"


# ── paths / storage ────────────────────────────────────────────────────────────


def _root_home() -> Path:
    """The app-level Hermes home, whichever profile this request is scoped to.

    A profile-scoped request has ``get_hermes_home()`` pointing at
    ``<root>/profiles/<name>``; spend still spans every profile, so unwrap it.
    """
    home = get_hermes_home()
    try:
        profile_home = named_profile_home(home)
    except Exception:  # noqa: BLE001 - path probing must never fail the page
        profile_home = None
    return profile_home.parent.parent if profile_home else home


def _profile_dbs() -> list[tuple[str, Path]]:
    """``[(profile, state.db)]`` — the default home first, then named profiles."""
    root = _root_home()
    dbs: list[tuple[str, Path]] = [("default", root / "state.db")]
    profiles_dir = root / "profiles"
    try:
        children = sorted(profiles_dir.iterdir(), key=lambda p: p.name)
    except OSError:
        return dbs
    for child in children:
        if not child.is_dir() or child.name.startswith(_PROFILE_SKIP_PREFIXES):
            continue
        db = child / "state.db"
        if db.is_file():
            dbs.append((child.name, db))
    return dbs


def _settings_dir() -> Path:
    """The sanctioned per-plugin data root (``plugin-data/<name>/``).

    Accounts are machine-wide, so the file deliberately lives on the root home
    even when the request is profile-scoped — otherwise switching profile in the
    app would silently show a different set of subscription modes for the same
    accounts. ``plugin_data_dir`` is the documented door; when the active home is
    a named profile it would resolve under that profile, so fall back to the
    root's data dir in that case.
    """
    root_data = _root_home() / "plugin-data"
    try:
        from plugins.plugin_storage import plugin_data_dir

        resolved = plugin_data_dir("token-master")
        if resolved.parent == root_data:
            return resolved
    except Exception:  # noqa: BLE001 - helper absence/drift must not fail the page
        logger.debug("token-master: plugin_data_dir unavailable", exc_info=True)
    return root_data / "token-master"


def _settings_path():
    return _settings_dir() / "settings.json"


def _read_settings() -> dict[str, Any]:
    path = _settings_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": _SETTINGS_VERSION, "accounts": {}, "remote_hosts": []}
    except (OSError, ValueError):
        logger.warning("token-master: unreadable settings at %s", path, exc_info=True)
        return {"version": _SETTINGS_VERSION, "accounts": {}, "remote_hosts": []}
    if not isinstance(raw, dict):
        return {"version": _SETTINGS_VERSION, "accounts": {}, "remote_hosts": []}
    accounts = raw.get("accounts")
    hosts = raw.get("remote_hosts")
    return {
        "version": _SETTINGS_VERSION,
        "accounts": accounts if isinstance(accounts, dict) else {},
        "remote_hosts": [h for h in hosts if isinstance(h, str) and h.strip()][:8]
        if isinstance(hosts, list)
        else [],
    }


def _write_settings(payload: dict[str, Any]) -> dict[str, Any]:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    hosts = payload.get("remote_hosts") if isinstance(payload.get("remote_hosts"), list) else []
    clean = {
        "version": _SETTINGS_VERSION,
        "accounts": payload.get("accounts") if isinstance(payload.get("accounts"), dict) else {},
        "remote_hosts": [str(h).strip() for h in hosts if isinstance(h, str) and h.strip()][:8],
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return clean


# ── history ────────────────────────────────────────────────────────────────────


def _connect(db: Path) -> sqlite3.Connection:
    # Read-only URI connection: never triggers a write or a schema migration, and
    # reads a WAL database safely alongside another profile's writer process.
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _has_usage_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'session_model_usage'"
    ).fetchone()
    return row is not None


def _token_sum(row: dict[str, Any]) -> int:
    return sum(int(row.get(field) or 0) for field in _TOKEN_FIELDS)


def _local_day(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).date().isoformat()
    except (OverflowError, OSError, ValueError, TypeError):
        return ""


def _window_start(days: int) -> float:
    """Midnight (local) of the first day in the window.

    The chart draws one column per calendar day, so the aggregate window must be
    whole days too — a rolling ``now - N*86400`` cutoff would count a partial day
    the chart cannot show, and the KPI would disagree with the bars.
    """
    today = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return (today - timedelta(days=max(0, days - 1))).timestamp()


def _usage_rows(days: int) -> tuple[list[dict[str, Any]], bool]:
    """Every usage row in the window across all profiles, deduped.

    Returns ``(rows, available)``. Rows are raw usage rows tagged with the
    ``profile`` they came from; a session mirrored into the root database is
    folded into its profile's copy (identical row keys, larger counters win).
    """
    cutoff = _window_start(days)
    rows: dict[tuple, dict[str, Any]] = {}
    available = False

    for profile, db in _profile_dbs():
        if not db.exists():
            continue
        try:
            conn = _connect(db)
        except sqlite3.Error:
            logger.debug("token-master: cannot open %s", db, exc_info=True)
            continue
        try:
            if not _has_usage_table(conn):
                continue
            available = True
            for record in conn.execute(
                "SELECT * FROM session_model_usage WHERE last_seen >= ?", (cutoff,)
            ):
                row = dict(record)
                row["source"] = _SOURCE_HERMES
                row["profile"] = profile
                row["provider"] = str(row.get("billing_provider") or "") or "unattributed"
                row["model"] = str(row.get("model") or "") or "unknown"
                row["task"] = str(row.get("task") or "") or "main agent"
                row["day"] = _local_day(row.get("last_seen") or 0)
                if not row["day"]:
                    continue
                key = (
                    row.get("session_id"),
                    row["model"],
                    row["provider"],
                    row["task"],
                    int(float(row.get("first_seen") or 0)),
                    int(float(row.get("last_seen") or 0)),
                )
                previous = rows.get(key)
                if previous is None or _token_sum(row) > _token_sum(previous):
                    rows[key] = row
        except sqlite3.Error:
            logger.debug("token-master: usage read failed for %s", db, exc_info=True)
        finally:
            conn.close()

    return list(rows.values()), available


# ── DeepSeek Harness ──────────────────────────────────────────────────────────
#
# Hermes only records its own calls, so work done in DeepSeek Harness (this very
# conversation included) is invisible to the Hermes databases. DSH does keep a
# per-session token ledger: ``record.rows.tokenUsage.val.totals`` with uncached
# input, output, cache-read and cache-write counts, plus session stats. Read it
# directly, attribute each session to its last-write day (the file is rewritten
# every turn), and merge it into the same rows the chart consumes.

def _dsh_home() -> Path:
    override = os.environ.get("DSH_HOME", "").strip()
    return Path(override) if override else Path.home() / ".dsh"


def _dsh_rows(days: int) -> list[dict[str, Any]]:
    root = _dsh_home() / "storages"
    if not root.is_dir():
        return []

    cutoff = _window_start(days)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for path in sorted(root.glob("*/sessions/*.json")):
        session = path.stem
        if session in seen:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime < cutoff:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue

        record = payload.get("record") if isinstance(payload, dict) else None
        if not isinstance(record, dict):
            continue
        atoms = record.get("rows")
        if not isinstance(atoms, dict):
            continue

        usage = ((atoms.get("tokenUsage") or {}).get("val") or {}).get("totals")
        if not isinstance(usage, dict):
            continue
        input_tokens = int(usage.get("uncachedInputTokens") or 0)
        output_tokens = int(usage.get("outputTokens") or 0)
        cache_read = int(usage.get("cacheReadTokens") or 0)
        cache_write = int(usage.get("cacheWriteTokens") or 0)
        if input_tokens + output_tokens + cache_read + cache_write <= 0:
            continue

        stats = ((atoms.get("sessionStats") or {}).get("val")) or {}
        selection = ((atoms.get("modelSelection") or {}).get("val")) or {}
        last_used = selection.get("lastUsed") if isinstance(selection, dict) else None
        # DSH records the provider it routed through (e.g. opencode-go), so its
        # spend lands on the same subscription as Hermes' own calls instead of
        # showing up as a separate vendor.
        provider = "unknown"
        model = ""
        if isinstance(last_used, dict):
            provider = str(last_used.get("provider") or "unknown")
            model = str(last_used.get("model") or "")

        rows.append(
            {
                "source": _SOURCE_DSH,
                "profile": _SOURCE_DSH,
                "provider": provider,
                "model": model or "unknown",
                "task": "main agent",
                "day": _local_day(stat.st_mtime),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read,
                "cache_write_tokens": cache_write,
                "reasoning_tokens": 0,
                # DSH records steps, not billable API calls; the closest honest
                # unit, and it only feeds the "calls" column of its own rows.
                "api_call_count": int(stats.get("steps") or 0),
                "estimated_cost_usd": 0.0,
                "actual_cost_usd": 0.0,
                "session_id": f"dsh:{session}",
            }
        )
        seen.add(session)

    return rows


# ── remote machines ───────────────────────────────────────────────────────────
#
# A second machine has its own Hermes profiles and DSH home, so its rows can only
# come from that machine. The collector (`collector/scan_rows.py`) is stdlib-only
# and is streamed into the remote Python over SSH, so nothing is installed there
# and nothing is written: it opens the remote state.db read-only, prints rows,
# and the result is cached here under plugin-data. Collection is explicit (the
# page's Sync button) — a page load never waits on SSH.

def _remote_dir() -> Path:
    return _settings_dir() / "remote"


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:64] or "host"


def _collector_path() -> Path:
    return Path(__file__).resolve().parents[1] / "collector" / "scan_rows.py"


def _remote_hosts() -> list[str]:
    return _read_settings().get("remote_hosts") or []


def _collect_host(host: str, days: int) -> dict[str, Any]:
    """SSH to one machine, stream the collector in, cache the rows it prints."""
    script = _collector_path()
    if not script.is_file():
        return {"host": host, "ok": False, "error": "collector/scan_rows.py is missing"}

    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, "python3 -", str(days)],
            input=script.read_text(encoding="utf-8"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"host": host, "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        return {"host": host, "ok": False, "error": (detail[-1] if detail else "ssh failed")[:300]}

    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"host": host, "ok": False, "error": "collector produced no JSON"}

    payload["host"] = host  # the configured label, not the remote hostname
    try:
        _remote_dir().mkdir(parents=True, exist_ok=True)
        (_remote_dir() / f"{_slug(host)}.json").write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        return {"host": host, "ok": False, "error": f"cannot cache rows: {exc}"}

    return {
        "host": host,
        "ok": True,
        "rows": len(payload.get("rows") or []),
        "collected_at": payload.get("collected_at"),
        "errors": payload.get("errors") or [],
    }


def _remote_rows(days: int) -> list[dict[str, Any]]:
    """Rows from the cached remote collections, filtered to the window."""
    start_day = datetime.fromtimestamp(_window_start(days)).date().isoformat()
    today = datetime.now().date().isoformat()
    rows: list[dict[str, Any]] = []

    for path in sorted(_remote_dir().glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        host = str(payload.get("host") or path.stem)
        for item in payload.get("rows") or []:
            if not isinstance(item, dict):
                continue
            day = str(item.get("day") or "")
            if not day or day < start_day or day > today:
                continue
            rows.append(
                {
                    "source": host,
                    "profile": host,
                    "provider": str(item.get("provider") or "unattributed"),
                    "model": str(item.get("model") or "unknown"),
                    "task": "main agent",
                    "day": day,
                    "input_tokens": int(item.get("input") or 0),
                    "output_tokens": int(item.get("output") or 0),
                    "cache_read_tokens": int(item.get("cache_read") or 0),
                    "cache_write_tokens": int(item.get("cache_write") or 0),
                    "reasoning_tokens": int(item.get("reasoning") or 0),
                    "api_call_count": int(item.get("calls") or 0),
                    "estimated_cost_usd": 0.0,
                    "actual_cost_usd": 0.0,
                    "session_id": f"remote:{host}:{day}:{item.get('provider')}:{item.get('model')}",
                }
            )
    return rows


def _remote_status() -> list[dict[str, Any]]:
    out = []
    for host in _remote_hosts():
        path = _remote_dir() / f"{_slug(host)}.json"
        entry: dict[str, Any] = {"host": host, "cached": path.is_file()}
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                entry["collected_at"] = payload.get("collected_at")
                entry["rows"] = len(payload.get("rows") or [])
            except (OSError, ValueError):
                entry["cached"] = False
        out.append(entry)
    return out


def _tailscale_peers() -> list[dict[str, Any]]:
    """Online Tailscale peers, so agent machines can be added without typing.

    Read-only: ``tailscale status --json`` lists this tailnet. Only online peers
    are offered — an offline host would just fail the SSH probe. Adding one is
    still a deliberate click: discovery never writes ``remote_hosts``.
    """
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return []

    peers: list[dict[str, Any]] = []
    self_node = payload.get("Self") or {}
    nodes = [self_node, *(payload.get("Peer") or {}).values()]
    for node in nodes:
        if not isinstance(node, dict):
            continue
        host = str(node.get("HostName") or "")
        if not host:
            continue
        addresses = node.get("TailscaleIPs") or []
        peers.append(
            {
                "host": host,
                "os": node.get("OS"),
                "online": bool(node.get("Online", True)),
                "self": node is self_node,
                "ip": addresses[0] if addresses else None,
                "dns": node.get("DNSName"),
            }
        )
    peers.sort(key=lambda peer: (not peer["online"], peer["host"]))
    return peers


def _bucket() -> dict[str, Any]:
    return {
        "input": 0,
        "output": 0,
        "cache_read": 0,
        "cache_write": 0,
        "reasoning": 0,
        "calls": 0,
        "cost_est": 0.0,
        "cost_actual": 0.0,
        "sessions": set(),
    }


def _add(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    bucket["input"] += int(row.get("input_tokens") or 0)
    bucket["output"] += int(row.get("output_tokens") or 0)
    bucket["cache_read"] += int(row.get("cache_read_tokens") or 0)
    bucket["cache_write"] += int(row.get("cache_write_tokens") or 0)
    bucket["reasoning"] += int(row.get("reasoning_tokens") or 0)
    bucket["calls"] += int(row.get("api_call_count") or 0)
    bucket["cost_est"] += float(row.get("estimated_cost_usd") or 0)
    bucket["cost_actual"] += float(row.get("actual_cost_usd") or 0)
    if row.get("session_id"):
        bucket["sessions"].add(row["session_id"])


def _finish(bucket: dict[str, Any]) -> dict[str, Any]:
    bucket = dict(bucket)
    bucket["sessions"] = len(bucket["sessions"])
    tokens = sum(bucket[field] for field in ("input", "output", "cache_read", "cache_write", "reasoning"))
    bucket["tokens"] = tokens
    for key in ("cost_est", "cost_actual"):
        bucket[key] = round(bucket[key], 6)
    return bucket


def _summary(days: int) -> dict[str, Any]:
    hermes_rows, hermes_available = _usage_rows(days)
    dsh_rows = _dsh_rows(days)
    remote_rows = _remote_rows(days)
    rows = hermes_rows + dsh_rows + remote_rows
    if not rows:
        return {
            "available": False,
            "reason": "no Hermes profile, DeepSeek Harness session or remote machine on this machine has token accounting yet",
            "profiles": [name for name, _ in _profile_dbs()],
            "sources": [],
            "remote": _remote_status(),
        }

    daily: dict[str, dict[str, Any]] = {}
    by_provider: dict[str, dict[str, Any]] = {}
    by_profile: dict[str, dict[str, Any]] = {}
    by_source: dict[str, dict[str, Any]] = {}
    by_model: dict[tuple[str, str], dict[str, Any]] = {}
    by_task: dict[str, dict[str, Any]] = {}
    by_cost_status: dict[str, dict[str, Any]] = {}
    by_day_provider: dict[tuple[str, str], int] = {}
    by_day_profile: dict[tuple[str, str], int] = {}
    by_day_source: dict[tuple[str, str], int] = {}

    for row in rows:
        day = row["day"]
        provider = row["provider"]
        profile = row["profile"]
        source = row["source"]
        _add(daily.setdefault(day, _bucket()), row)
        _add(by_provider.setdefault(provider, _bucket()), row)
        _add(by_profile.setdefault(profile, _bucket()), row)
        _add(by_source.setdefault(source, _bucket()), row)
        _add(by_model.setdefault((row["model"], provider), _bucket()), row)
        _add(by_task.setdefault(row["task"], _bucket()), row)
        # Subscription-included vs pay-per-token: Hermes records the route it
        # billed through, which is how a Claude/ChatGPT plan's usage is told
        # apart from an API key's.
        status = str(row.get("cost_status") or "").strip() or "not recorded"
        _add(by_cost_status.setdefault(status, _bucket()), row)
        tokens = _token_sum(row)
        by_day_provider[(day, provider)] = by_day_provider.get((day, provider), 0) + tokens
        by_day_profile[(day, profile)] = by_day_profile.get((day, profile), 0) + tokens
        by_day_source[(day, source)] = by_day_source.get((day, source), 0) + tokens

    daily_rows = [{"day": day, **_finish(bucket)} for day, bucket in sorted(daily.items())]
    provider_rows = sorted(
        [{"provider": name, **_finish(bucket)} for name, bucket in by_provider.items()],
        key=lambda row: row["tokens"],
        reverse=True,
    )
    profile_rows = sorted(
        [{"profile": name, **_finish(bucket)} for name, bucket in by_profile.items()],
        key=lambda row: row["tokens"],
        reverse=True,
    )
    source_rows = sorted(
        [{"source": name, **_finish(bucket)} for name, bucket in by_source.items()],
        key=lambda row: row["tokens"],
        reverse=True,
    )
    model_rows = sorted(
        [
            {"model": model, "provider": provider, **_finish(bucket)}
            for (model, provider), bucket in by_model.items()
        ],
        key=lambda row: row["tokens"],
        reverse=True,
    )[:25]
    task_rows = sorted(
        [
            {"task": task, **_finish(bucket)}
            for task, bucket in by_task.items()
        ],
        key=lambda row: row["tokens"],
        reverse=True,
    )[:12]

    totals = {
        "input": sum(row["input"] for row in daily_rows),
        "output": sum(row["output"] for row in daily_rows),
        "cache_read": sum(row["cache_read"] for row in daily_rows),
        "cache_write": sum(row["cache_write"] for row in daily_rows),
        "reasoning": sum(row["reasoning"] for row in daily_rows),
        "calls": sum(row["calls"] for row in daily_rows),
        "cost_est": round(sum(row["cost_est"] for row in daily_rows), 6),
        "cost_actual": round(sum(row["cost_actual"] for row in daily_rows), 6),
        "active_days": len(daily_rows),
        "sessions": sum(row["sessions"] for row in profile_rows),
    }
    totals["tokens"] = sum(
        totals[field] for field in ("input", "output", "cache_read", "cache_write", "reasoning")
    )

    return {
        "available": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": days,
        "bucket": "day",
        "bucket_timezone": "local",
        "profiles": [name for name, _ in _profile_dbs()],
        "remote": _remote_status(),
        "sources": [
            {
                "id": row["source"],
                "label": (
                    "Hermes"
                    if row["source"] == _SOURCE_HERMES
                    else "DeepSeek Harness"
                    if row["source"] == _SOURCE_DSH
                    else f"Remote · {row['source']}"
                ),
                "tokens": row["tokens"],
                "sessions": row["sessions"],
            }
            for row in source_rows
        ],
        "daily": daily_rows,
        "by_provider": provider_rows,
        "by_profile": profile_rows,
        "by_source": source_rows,
        "by_model": model_rows,
        "by_task": task_rows,
        "by_cost_status": sorted(
            [
                {"status": status, **_finish(bucket)}
                for status, bucket in by_cost_status.items()
            ],
            key=lambda row: row["tokens"],
            reverse=True,
        ),
        "by_day_provider": [
            {"day": day, "provider": provider, "tokens": tokens}
            for (day, provider), tokens in sorted(by_day_provider.items())
        ],
        "by_day_profile": [
            {"day": day, "profile": profile, "tokens": tokens}
            for (day, profile), tokens in sorted(by_day_profile.items())
        ],
        "by_day_source": [
            {"day": day, "source": source, "tokens": tokens}
            for (day, source), tokens in sorted(by_day_source.items())
        ],
        "totals": totals,
    }


# ── accounts ───────────────────────────────────────────────────────────────────


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return None


def _snapshot_dict(snapshot: Any) -> Optional[dict[str, Any]]:
    if snapshot is None:
        return None
    windows = []
    for window in _get(snapshot, "windows", ()) or ():
        windows.append(
            {
                "label": _get(window, "label", "limit"),
                "used_percent": _get(window, "used_percent"),
                "resets_at": _iso(_get(window, "reset_at")),
                "scope": _get(window, "scope", "account"),
            }
        )
    fetched = _get(snapshot, "fetched_at")
    return {
        "plan": _get(snapshot, "plan"),
        "title": _get(snapshot, "title", "Account limits"),
        "source": _get(snapshot, "source"),
        "windows": windows,
        "details": list(_get(snapshot, "details", ()) or ()),
        "unavailable_reason": _get(snapshot, "unavailable_reason"),
        "fetched_at": _iso(fetched),
    }


# One attempt per provider per TTL, including a negative result: the page must
# never pay a provider round-trip twice, and a provider with no fetcher answers
# instantly anyway.
_probe_cache: dict[str, tuple[float, Optional[dict[str, Any]]]] = {}


def _probe_snapshot(provider: str) -> Optional[dict[str, Any]]:
    """One allowance fetch, memoized for the TTL.

    ``read_only=True`` is the plugin guide's usage-panel rule: a panel must not
    refresh, rotate or rewrite a credential, so this can never disturb sign-in.
    """
    now = time.time()
    hit = _probe_cache.get(provider)
    if hit and now - hit[0] < _LIMIT_TTL_SECONDS:
        return hit[1]
    try:
        from agent.account_usage import fetch_account_usage

        snapshot = _snapshot_dict(fetch_account_usage(provider, read_only=True))
    except Exception:  # noqa: BLE001 - a provider API can fail any way it likes
        logger.info("token-master: allowance fetch failed for %s", provider, exc_info=True)
        snapshot = None
    _probe_cache[provider] = (now, snapshot)
    return snapshot


# ── quota sampling ───────────────────────────────────────────────────────────
#
# Provider windows are percentages, and a percentage only becomes a burn rate
# over time. Every explicit limits refresh appends a sample, so after a few
# visits the plugin can say "%/day", "days to cap", and — by dividing the tokens
# this machine measured over the same stretch by the percentage change — an
# implied "tokens per 1%". That number is the honest bridge between a token
# count and a provider dashboard that may count differently.

_QUOTA_SAMPLE_LIMIT = 4000


def _quota_path() -> Path:
    return _settings_dir() / "quota-samples.json"


def _read_samples() -> list[dict[str, Any]]:
    try:
        raw = json.loads(_quota_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return []
    samples = raw.get("samples") if isinstance(raw, dict) else None
    return [s for s in samples if isinstance(s, dict)] if isinstance(samples, list) else []


def _write_samples(samples: list[dict[str, Any]]) -> None:
    path = _quota_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        trimmed = samples[-_QUOTA_SAMPLE_LIMIT:]
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"samples": trimmed}), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        logger.debug("token-master: quota sample write failed", exc_info=True)


def _record_samples(provider: str, limits: Optional[dict[str, Any]]) -> None:
    """Append one sample per window, skipping a repeat inside five minutes."""
    windows = (limits or {}).get("windows") or []
    if not windows:
        return
    samples = _read_samples()
    now = time.time()
    changed = False
    for window in windows:
        percent = window.get("used_percent")
        if percent is None:
            continue
        label = str(window.get("label") or "limit")
        recent = next(
            (
                sample
                for sample in reversed(samples)
                if sample.get("provider") == provider
                and sample.get("window") == label
                and now - float(sample.get("ts") or 0) < 300
            ),
            None,
        )
        if recent is not None:
            if abs(float(recent.get("percent") or 0) - float(percent)) < 1e-9:
                continue
            recent["percent"] = float(percent)
            recent["ts"] = now
            changed = True
            continue
        samples.append({"ts": now, "provider": provider, "window": label, "percent": float(percent)})
        changed = True
    if changed:
        _write_samples(samples)


def _quota_trends(tokens_per_day: dict[str, float]) -> dict[str, list[dict[str, Any]]]:
    """Per-provider window trends from the sample history."""
    samples = _read_samples()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for sample in samples:
        key = (str(sample.get("provider")), str(sample.get("window")))
        grouped.setdefault(key, []).append(sample)

    trends: dict[str, list[dict[str, Any]]] = {}
    now = time.time()
    for (provider, window), series in grouped.items():
        series.sort(key=lambda item: float(item.get("ts") or 0))
        latest = series[-1]
        # Compare against the newest sample at least an hour old, else the first.
        earlier = next(
            (
                sample
                for sample in reversed(series[:-1])
                if now - float(sample.get("ts") or 0) >= 3600
            ),
            series[0] if len(series) > 1 else None,
        )
        if earlier is None:
            continue
        hours = (float(latest["ts"]) - float(earlier["ts"])) / 3600.0
        if hours <= 0:
            continue
        delta = float(latest["percent"]) - float(earlier["percent"])
        percent_per_day = delta / (hours / 24.0)
        entry: dict[str, Any] = {
            "window": window,
            "percent": float(latest["percent"]),
            "delta": round(delta, 3),
            "hours": round(hours, 1),
            "percent_per_day": round(percent_per_day, 3),
            "days_to_cap": None,
            "tokens_per_percent": None,
            "implied_allowance": None,
            "samples": len(series),
        }
        if percent_per_day > 0 and latest["percent"] < 100:
            entry["days_to_cap"] = round((100.0 - float(latest["percent"])) / percent_per_day, 1)
        measured = tokens_per_day.get(provider) or 0.0
        if measured > 0 and percent_per_day > 0:
            per_percent = measured / percent_per_day
            entry["tokens_per_percent"] = round(per_percent, 0)
            entry["implied_allowance"] = round(per_percent * 100.0, 0)
        trends.setdefault(provider, []).append(entry)
    return trends


def _read_pool() -> dict[str, Any]:
    """Credential-pool metadata from ``auth.json``: labels, ids and status only.

    The file is read as data — no token is imported, refreshed or written, so
    the single-use refresh chains Hermes owns are never touched. A retry covers
    the window where a rotation rewrites the file mid-read.
    """
    path = _root_home() / "auth.json"
    for attempt in range(2):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = None
        pool = raw.get("credential_pool") if isinstance(raw, dict) else None
        if isinstance(pool, dict) and pool:
            return pool
        if attempt == 0:
            time.sleep(0.05)
    return {}


def _pool_accounts() -> list[dict[str, Any]]:
    pool = _read_pool()
    accounts: list[dict[str, Any]] = []
    for provider, entries in pool.items():
        for entry in entries or ():
            auth_type = str(_get(entry, "auth_type", "") or "")
            accounts.append(
                {
                    "provider": provider,
                    "id": str(_get(entry, "id", "") or ""),
                    "label": str(_get(entry, "label", "") or _get(entry, "id", "") or provider),
                    "auth_type": auth_type,
                    "priority": _get(entry, "priority", 0),
                    "requests": _get(entry, "request_count", 0),
                    "last_status": _get(entry, "last_status"),
                    "source": _get(entry, "source"),
                    "base_url": _get(entry, "base_url"),
                }
            )
    accounts.sort(key=lambda a: (a["provider"], int(a["priority"] or 0)))
    return accounts


def _provider_usage(days: int = 30) -> dict[str, dict[str, Any]]:
    """Per-provider spend across all profiles *and* DSH, for the account rows.

    DSH is included because it bills through the same subscriptions (its sessions
    record a provider like ``opencode-go``), so an account row that showed only
    Hermes' own calls would understate the quota burn.
    """
    hermes_rows, available = _usage_rows(days)
    rows = hermes_rows + _dsh_rows(days) + _remote_rows(days)
    if not rows:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = out.setdefault(row["provider"], {"tokens": 0, "calls": 0, "cost_est": 0.0})
        bucket["tokens"] += _token_sum(row)
        bucket["calls"] += int(row.get("api_call_count") or 0)
        bucket["cost_est"] += float(row.get("estimated_cost_usd") or 0)
    for bucket in out.values():
        bucket["cost_est"] = round(bucket["cost_est"], 6)
    return out


def _default_mode(account: dict[str, Any]) -> str:
    auth = (account.get("auth_type") or "").lower()
    if auth == "oauth":
        return "subscription"
    return "api"


def _accounts_payload(refresh: bool) -> dict[str, Any]:
    settings = _read_settings()
    saved = settings.get("accounts") or {}
    usage = _provider_usage(30)
    accounts = _pool_accounts()

    providers = sorted({a["provider"] for a in accounts})
    limits: dict[str, Optional[dict[str, Any]]] = {}
    supported: dict[str, Optional[bool]] = {}
    for provider in providers:
        if refresh:
            snapshot = _probe_snapshot(provider)
            _record_samples(provider, snapshot)
        cached = _probe_cache.get(provider)
        limits[provider] = cached[1] if cached else None
        # Unknown until one fetch has been attempted: a provider with no fetcher
        # is discovered by the probe answering None, not by importing internals.
        supported[provider] = (cached[1] is not None) if cached else None

    tokens_per_day = {provider: spend["tokens"] / 30.0 for provider, spend in usage.items()}
    trends = _quota_trends(tokens_per_day)

    for account in accounts:
        key = f"{account['provider']}|{account['id']}"
        choice = saved.get(key) or {}
        mode = choice.get("mode")
        account["key"] = key
        account["mode"] = mode if mode in ("subscription", "api", "free") else _default_mode(account)
        account["mode_explicit"] = mode in ("subscription", "api", "free")
        account["monthly_cap_usd"] = choice.get("monthly_cap_usd")
        account["limits"] = limits.get(account["provider"])
        account["live_limits_supported"] = supported.get(account["provider"])
        account["trends"] = trends.get(account["provider"], [])
        account["usage_30d"] = usage.get(account["provider"], {"tokens": 0, "calls": 0, "cost_est": 0})

    # A provider with usage but no pool entry (an env-only key that never got
    # pooled) still deserves a row, or its spend would be invisible here.
    pooled = {a["provider"] for a in accounts}
    for provider, spend in usage.items():
        if provider in pooled or provider == "unattributed":
            continue
        if provider not in limits:
            if refresh:
                _probe_snapshot(provider)
                cached = _probe_cache.get(provider)
                limits[provider] = cached[1] if cached else None
                supported[provider] = (cached[1] is not None) if cached else None
        accounts.append(
            {
                "provider": provider,
                "id": "",
                "key": f"{provider}|",
                "label": provider,
                "auth_type": "",
                "priority": 0,
                "requests": 0,
                "last_status": None,
                "source": None,
                "base_url": None,
                "mode": _default_mode({}),
                "mode_explicit": False,
                "monthly_cap_usd": None,
                "limits": limits.get(provider),
                "live_limits_supported": supported.get(provider),
                "trends": trends.get(provider, []),
                "usage_30d": spend,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "accounts": accounts,
        "providers": providers,
        "pool_available": bool(providers),
        "profiles": [name for name, _ in _profile_dbs()],
        "settings": settings,
    }


# ── routes ─────────────────────────────────────────────────────────────────────


@router.get("/summary")
async def summary(days: int = Query(90, ge=1, le=365)):
    """Daily token series + provider/profile/model/task breakdowns across all profiles."""
    return await asyncio.to_thread(_summary, days)


@router.get("/accounts")
async def accounts(refresh: bool = Query(False)):
    """Credential-pool accounts, configured mode, and cached allowance windows.

    ``refresh=true`` asks providers for fresh windows (network, seconds); the
    page loads without it and offers the refresh as an explicit action.
    """
    return await asyncio.to_thread(_accounts_payload, refresh)


@router.get("/settings")
async def settings_get():
    return _read_settings()


@router.get("/remote")
async def remote_status():
    """Configured machines and whether their last collection is cached."""
    return {"hosts": _remote_status()}


@router.get("/machines")
async def machines():
    """Configured remote machines plus online Tailscale peers for discovery."""
    return {
        "configured": _remote_status(),
        "tailscale": await asyncio.to_thread(_tailscale_peers),
    }


@router.get("/quota")
async def quota():
    """Recorded allowance samples for every provider window."""
    return {"samples": _read_samples(), "path": str(_quota_path())}


@router.post("/collect")
async def collect(body: dict[str, Any] = Body(default_factory=dict)):
    """Pull rows from every configured remote machine (explicit user action).

    Streams ``collector/scan_rows.py`` into the remote ``python3`` over SSH, so
    the remote host needs no install and nothing is written there. Results are
    cached and joined to the chart as their own source.
    """
    days = body.get("days") if isinstance(body, dict) else None
    try:
        window = max(1, min(30, int(days))) if days is not None else 3
    except (TypeError, ValueError):
        window = 3

    hosts = _remote_hosts()
    if not hosts:
        return {"configured": False, "hosts": [], "settings": _read_settings()}

    results = []
    for host in hosts:
        results.append(await asyncio.to_thread(_collect_host, host, window))
    return {"configured": True, "hosts": results}


@router.put("/settings")
async def settings_put(body: dict[str, Any] = Body(default_factory=dict)):
    """Persist the per-account mode and the remote-machine list."""
    if not isinstance(body, dict):
        return _read_settings()

    incoming = body.get("accounts")
    current = _read_settings()
    merged = dict(current.get("accounts") or {})

    if isinstance(incoming, dict):
        for key, value in incoming.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            mode = value.get("mode")
            cap = value.get("monthly_cap_usd")
            entry: dict[str, Any] = dict(merged.get(key) or {})
            if mode in ("subscription", "api", "free"):
                entry["mode"] = mode
            elif mode is None:
                entry.pop("mode", None)
            if isinstance(cap, (int, float)) and cap >= 0:
                entry["monthly_cap_usd"] = float(cap)
            elif cap is None:
                entry.pop("monthly_cap_usd", None)
            if entry:
                merged[key] = entry
            else:
                merged.pop(key, None)

    hosts = current.get("remote_hosts") or []
    if isinstance(body.get("remote_hosts"), list):
        hosts = body["remote_hosts"]

    return _write_settings({"accounts": merged, "remote_hosts": hosts})
