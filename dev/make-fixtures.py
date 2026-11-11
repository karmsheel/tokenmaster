#!/usr/bin/env python3
"""Write the JSON fixtures the .smoke/ render harness reads.

    python dev/make-fixtures.py              # synthetic: same shape, invented numbers
    python dev/make-fixtures.py --live       # dump this machine's real backend output

Synthetic is the default, and the one to use for anything that leaves this
machine. It keeps the payload shape -- and therefore every assertion in
.smoke/run.mjs and .smoke/data-test.mjs -- while replacing account labels,
profile names, host names and token volumes with plausible invented ones.
Output is byte-identical for a given --seed.

    --out DIR          where to write (default: <repo>/.smoke/fixtures)
    --seed N           PRNG seed for the synthetic generator (default 20261111)
    --days N           window length in days (default 90)
    --hermes-home DIR  Hermes install used by --live (default: $HERMES_HOME,
                       else %LOCALAPPDATA%\\hermes, else ~/.hermes)

Consistency is structural, not checked after the fact: every fixture number is
computed from one integer allocation table, so class sums, per-provider sums and
totals.tokens agree by construction -- which is exactly what data-test.mjs
asserts. Token volume is cache-heavy (~97% cache reads) because that is the real
shape, and the accounts payload reuses the same 30-day window so the two
fixtures cannot drift apart.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / ".smoke" / "fixtures"

CLASS_KEYS = ("input", "output", "cache_read", "cache_write", "reasoning")

TARGET_TOKENS = 2_900_000_000

# Placeholder names: nothing here is meant to match a real machine.
PROFILES = ["default", "coder", "designer", "planner", "researcher", "ops", "media"]
REMOTE_HOST = "edge-01"
REMOTE_LABEL = f"Remote · {REMOTE_HOST}"

# Token-class mixes. Cache reads dominate real traffic; the free-tier models are
# denser (little cache reuse) and the vision calls are input-heavy.
MIX_CACHE = {"input": 0.0200, "output": 0.0040, "cache_read": 0.9755, "cache_write": 0.0, "reasoning": 0.0005}
MIX_DENSE = {"input": 0.1100, "output": 0.0200, "cache_read": 0.8656, "cache_write": 0.0, "reasoning": 0.0044}
MIX_VISION = {"input": 0.5500, "output": 0.0500, "cache_read": 0.4000, "cache_write": 0.0, "reasoning": 0.0}

# provider, model, profile, source, task, cost status, relative weight, class mix, $/token, presence
STREAMS = [
    ("opencode-go", "deepseek-v4.1-flash", "coder", "hermes", "main agent", "not recorded", 0.300, MIX_CACHE, 0.0, 0.85),
    ("opencode-go", "deepseek-v4.1-flash", REMOTE_HOST, REMOTE_HOST, "main agent", "not recorded", 0.340, MIX_CACHE, 0.0, 0.90),
    ("opencode-go", "deepseek-v4.1-flash", "coder", "deepseek-harness", "main agent", "not recorded", 0.130, MIX_CACHE, 0.0, 0.75),
    ("opencode-go", "minimax-m3", "designer", "hermes", "main agent", "not recorded", 0.050, MIX_CACHE, 0.0, 0.35),
    ("opencode-go", "glm-5.3-flash", "planner", "hermes", "main agent", "not recorded", 0.030, MIX_CACHE, 0.0, 0.30),
    ("opencode-go", "longcat-2.5-preview-free", "media", "hermes", "main agent", "not recorded", 0.010, MIX_DENSE, 0.0, 0.15),
    ("openai", "deepseek-v4.1-flash", "designer", "hermes", "main agent", "estimated", 0.010, MIX_CACHE, 0.0000012, 0.20),
    ("openai", "deepseek-v4.1-flash", "coder", "deepseek-harness", "main agent", "estimated", 0.050, MIX_CACHE, 0.0000012, 0.25),
    ("deepseek-account", "deepseek-flash", "default", "hermes", "main agent", "unknown", 0.020, MIX_DENSE, 0.0, 0.30),
    ("nous", "stepfun/step-5-preview:free", "default", "hermes", "main agent", "unknown", 0.012, MIX_DENSE, 0.0, 0.30),
    ("nous", "tencent/hy3:free", "researcher", "hermes", "main agent", "unknown", 0.008, MIX_DENSE, 0.0, 0.20),
    ("nous", "upstage/solar-pro4:free", "ops", "hermes", "title_generation", "estimated", 0.004, MIX_DENSE, 0.0000004, 0.25),
    ("nous", "poolside/laguna-s-2.1:free", "researcher", "hermes", "background_review", "unknown", 0.003, MIX_DENSE, 0.0, 0.18),
    ("nous", "stepfun/step-3.7-flash:free", "ops", "hermes", "vision", "unknown", 0.002, MIX_VISION, 0.0, 0.12),
    ("nous", "meituan/longcat-2.5-preview:free", "media", "hermes", "tts_audio_tags", "unknown", 0.001, MIX_DENSE, 0.0, 0.08),
    ("nous", "stealth/space-bunny-alpha", "media", "hermes", "vision", "unknown", 0.0015, MIX_VISION, 0.0, 0.10),
    ("nous", "ornith/ornith-1.5-122b:free", "planner", "hermes", "background_review", "unknown", 0.0015, MIX_DENSE, 0.0, 0.12),
    ("unattributed", "unknown", "default", "hermes", "compression", "unknown", 0.004, MIX_DENSE, 0.0, 0.25),
    ("unattributed", "stepfun/step-5-preview:free", "default", "hermes", "approval", "unknown", 0.001, MIX_DENSE, 0.0, 0.15),
    ("unattributed", "deepseek-v4.1-flash", "coder", "deepseek-harness", "main agent", "not recorded", 0.006, MIX_CACHE, 0.0, 0.20),
]

SOURCE_LABELS = {"hermes": "Hermes", "deepseek-harness": "DeepSeek Harness", REMOTE_HOST: REMOTE_LABEL}


def blank() -> dict:
    row = {key: 0 for key in CLASS_KEYS}
    row.update({"calls": 0, "cost_est": 0.0, "cost_actual": 0.0, "sessions": 0, "tokens": 0})
    return row


def add_row(target: dict, classes: dict, calls: int, sessions: int, cost_est: float, cost_actual: float) -> None:
    for key in CLASS_KEYS:
        target[key] += classes[key]
    target["calls"] += calls
    target["sessions"] += sessions
    target["cost_est"] = round(target["cost_est"] + cost_est, 6)
    target["cost_actual"] = round(target["cost_actual"] + cost_actual, 6)
    target["tokens"] += sum(classes[key] for key in CLASS_KEYS)


def split(total: int, mix: dict) -> dict:
    """Integer class split that sums to exactly `total`."""
    parts = {key: int(round(total * mix[key])) for key in CLASS_KEYS if key != "cache_read"}
    parts["cache_read"] = total - sum(parts.values())
    if parts["cache_read"] < 0:
        parts["cache_read"] = 0
    return parts


def ordered(row: dict, leading: str, value) -> dict:
    return {leading: value, **{key: row[key] for key in (*CLASS_KEYS, "calls", "cost_est", "cost_actual", "sessions", "tokens")}}


def generate(seed: int, days: int) -> tuple[dict, dict]:
    rng = random.Random(seed)
    today = date.today()
    window = [today - timedelta(days=days - 1 - index) for index in range(days)]

    # A quiet start ramping into heavy use, weekends thinner, plus idle days --
    # ~75 active days out of 90, like a real machine.
    factors: dict[date, float] = {}
    for index, day in enumerate(window):
        ramp = 0.30 + 0.70 * (index / max(1, days - 1)) ** 1.4
        if day.weekday() == 5:
            weekday = 0.55
        elif day.weekday() == 6:
            weekday = 0.45
        elif day.weekday() == 0:
            weekday = 0.88
        else:
            weekday = 1.0
        factors[day] = ramp * weekday * rng.uniform(0.82, 1.18)

    active = []
    for day in window:
        idle_chance = 0.50 if day.weekday() >= 5 else 0.09
        if rng.random() >= idle_chance:
            active.append(day)
    if not active:
        active = [today]
        factors[today] = 1.0

    total_factor = sum(factors[day] for day in active)

    daily: dict[date, dict] = {}
    by_provider: dict[str, dict] = {}
    by_profile: dict[str, dict] = {}
    by_source: dict[str, dict] = {}
    by_model: dict[tuple[str, str], dict] = {}
    by_task: dict[str, dict] = {}
    by_status: dict[str, dict] = {}
    by_day_provider: dict[tuple[date, str], int] = {}
    by_day_profile: dict[tuple[date, str], int] = {}
    by_day_source: dict[tuple[date, str], int] = {}
    provider_30d: dict[str, dict] = {}
    cutoff = today - timedelta(days=29)

    for day in sorted(active):
        day_total = TARGET_TOKENS * factors[day] / total_factor
        row = blank()
        row_day = day

        # Not every provider is used every day; renormalise the weights over
        # whichever streams show up so the day still spends its full volume.
        present = [stream for stream in STREAMS if rng.random() < stream[9]]
        if not present:
            present = [STREAMS[0]]
        weight_total = sum(stream[6] for stream in present)

        for provider, model, profile, source, task, status, weight, mix, rate, _presence in present:
            amount = int(round(day_total * (weight / weight_total) * rng.uniform(0.85, 1.15)))
            if amount <= 0:
                continue
            classes = split(amount, mix)
            calls = max(1, int(round(amount / 165_000 * rng.uniform(0.75, 1.25))))
            sessions = max(1, int(round(calls / 24 + rng.uniform(0.0, 1.0))))
            cost_est = round(amount * rate, 6) if rate else 0.0

            add_row(row, classes, calls, sessions, cost_est, 0.0)
            for bucket, name in (
                (by_provider, provider),
                (by_profile, profile),
                (by_source, source),
                (by_task, task),
                (by_status, status),
            ):
                add_row(bucket.setdefault(name, blank()), classes, calls, sessions, cost_est, 0.0)
            add_row(by_model.setdefault((provider, model), blank()), classes, calls, sessions, cost_est, 0.0)
            by_day_provider[(day, provider)] = by_day_provider.get((day, provider), 0) + amount
            by_day_profile[(day, profile)] = by_day_profile.get((day, profile), 0) + amount
            by_day_source[(day, source)] = by_day_source.get((day, source), 0) + amount

            if day >= cutoff:
                recent = provider_30d.setdefault(provider, {"tokens": 0, "calls": 0, "cost_est": 0.0})
                recent["tokens"] += amount
                recent["calls"] += calls
                recent["cost_est"] = round(recent["cost_est"] + cost_est, 6)

        daily[row_day] = row

    totals = blank()
    for row in daily.values():
        add_row(totals, {key: row[key] for key in CLASS_KEYS}, row["calls"], row["sessions"], row["cost_est"], 0.0)
    totals["active_days"] = len(daily)

    sources = []
    for name, row in by_source.items():
        sources.append({"id": name, "label": SOURCE_LABELS[name], "tokens": row["tokens"], "sessions": row["sessions"]})
    sources.sort(key=lambda entry: entry["tokens"], reverse=True)

    summary = {
        "available": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": days,
        "bucket": "day",
        "bucket_timezone": "local",
        "profiles": PROFILES + [REMOTE_HOST],
        "remote": [
            {
                "host": REMOTE_HOST,
                "cached": True,
                "collected_at": round(time.time() - 1800, 4),
                "rows": 325,
            }
        ],
        "sources": sources,
        "daily": [ordered(daily[day], "day", day.isoformat()) for day in sorted(daily)],
        "by_provider": [ordered(row, "provider", name) for name, row in sorted(by_provider.items(), key=lambda kv: -kv[1]["tokens"])],
        "by_profile": [ordered(row, "profile", name) for name, row in sorted(by_profile.items(), key=lambda kv: -kv[1]["tokens"])],
        "by_source": [ordered(row, "source", name) for name, row in sorted(by_source.items(), key=lambda kv: -kv[1]["tokens"])],
        "by_model": [
            {
                "model": model,
                "provider": provider,
                **{key: row[key] for key in (*CLASS_KEYS, "calls", "cost_est", "cost_actual", "sessions", "tokens")},
            }
            for (provider, model), row in sorted(by_model.items(), key=lambda kv: -kv[1]["tokens"])
        ],
        "by_task": [ordered(row, "task", name) for name, row in sorted(by_task.items(), key=lambda kv: -kv[1]["tokens"])],
        "by_cost_status": [ordered(row, "status", name) for name, row in sorted(by_status.items(), key=lambda kv: -kv[1]["tokens"])],
        "by_day_provider": [
            {"day": day.isoformat(), "provider": provider, "tokens": tokens}
            for (day, provider), tokens in sorted(by_day_provider.items())
        ],
        "by_day_profile": [
            {"day": day.isoformat(), "profile": profile, "tokens": tokens}
            for (day, profile), tokens in sorted(by_day_profile.items())
        ],
        "by_day_source": [
            {"day": day.isoformat(), "source": source, "tokens": tokens}
            for (day, source), tokens in sorted(by_day_source.items())
        ],
        "totals": {
            key: totals[key]
            for key in (*CLASS_KEYS, "calls", "cost_est", "cost_actual", "active_days", "sessions", "tokens")
        },
    }

    accounts = accounts_payload(provider_30d)
    return summary, accounts


def accounts_payload(provider_30d: dict) -> dict:
    def usage(provider: str) -> dict:
        recent = provider_30d.get(provider, {"tokens": 0, "calls": 0, "cost_est": 0.0})
        return {"tokens": recent["tokens"], "calls": recent["calls"], "cost_est": round(recent["cost_est"], 6)}

    now = time.time()
    windows = [
        {"label": "Rolling 7d", "scope": "rolling", "used_percent": 38.4, "resets_at": iso_in(now, 3.4)},
        {"label": "Weekly", "scope": "weekly", "used_percent": 61.9, "resets_at": iso_in(now, 52.0)},
        {"label": "Monthly", "scope": "monthly", "used_percent": 24.2, "resets_at": iso_in(now, 264.0)},
    ]
    trends = [
        {"window": "Rolling 7d", "percent_per_day": 1.35, "days_to_cap": 45, "tokens_per_percent": 42_800_000},
        {"window": "Weekly", "percent_per_day": 0.58, "days_to_cap": 66, "tokens_per_percent": 38_100_000},
    ]

    entries = [
        {
            "provider": "opencode-go",
            "id": "7b6012",
            "label": "OPENCODE_GO_API_KEY",
            "auth_type": "api_key",
            "priority": 0,
            "requests": 0,
            "last_status": None,
            "source": "env:OPENCODE_GO_API_KEY",
            "base_url": "https://opencode.ai/zen/go/v1",
            "key": "opencode-go|7b6012",
            "mode": "subscription",
            "mode_explicit": True,
            "monthly_cap_usd": None,
            "limits": {"windows": windows, "fetched_at": round(now - 900, 3), "live": True},
            "live_limits_supported": True,
            "trends": trends,
            "usage_30d": usage("opencode-go"),
        },
        {
            "provider": "openai",
            "id": "4c8d11",
            "label": "device_code",
            "auth_type": "oauth",
            "priority": 0,
            "requests": 212,
            "last_status": "ok",
            "source": "device_code",
            "base_url": "https://api.openai.com/v1",
            "key": "openai|4c8d11",
            "mode": "subscription",
            "mode_explicit": False,
            "monthly_cap_usd": None,
            "limits": {
                "windows": [
                    {"label": "5h window", "scope": "session", "used_percent": 12.5, "resets_at": iso_in(now, 1.7)},
                    {"label": "Weekly", "scope": "weekly", "used_percent": 47.0, "resets_at": iso_in(now, 40.0)},
                ],
                "fetched_at": round(now - 900, 3),
                "live": True,
            },
            "live_limits_supported": True,
            "trends": [
                {"window": "Weekly", "percent_per_day": 0.42, "days_to_cap": 111, "tokens_per_percent": 9_600_000}
            ],
            "usage_30d": usage("openai"),
        },
        {
            "provider": "nous",
            "id": "25ee24",
            "label": "analyst@example.com",
            "auth_type": "oauth",
            "priority": 0,
            "requests": 485,
            "last_status": "ok",
            "source": "device_code",
            "base_url": None,
            "key": "nous|25ee24",
            "mode": "free",
            "mode_explicit": True,
            "monthly_cap_usd": None,
            "limits": None,
            "live_limits_supported": False,
            "trends": [],
            "usage_30d": usage("nous"),
        },
        {
            "provider": "xai-oauth",
            "id": "292489",
            "label": "device_code",
            "auth_type": "oauth",
            "priority": 0,
            "requests": 0,
            "last_status": "ok",
            "source": "device_code",
            "base_url": "https://api.x.ai/v1",
            "key": "xai-oauth|292489",
            "mode": "subscription",
            "mode_explicit": False,
            "monthly_cap_usd": None,
            "limits": None,
            "live_limits_supported": False,
            "trends": [],
            "usage_30d": usage("xai-oauth"),
        },
        {
            "provider": "openrouter",
            "id": "28bb93",
            "label": "OPENROUTER_API_KEY",
            "auth_type": "api_key",
            "priority": 0,
            "requests": 0,
            "last_status": "ok",
            "source": "env:OPENROUTER_API_KEY",
            "base_url": "https://openrouter.ai/api/v1",
            "key": "openrouter|28bb93",
            "mode": "api",
            "mode_explicit": False,
            "monthly_cap_usd": None,
            "limits": None,
            "live_limits_supported": False,
            "trends": [],
            "usage_30d": usage("openrouter"),
        },
    ]

    settings = {
        "version": 1,
        "accounts": {
            "opencode-go|7b6012": {"mode": "subscription"},
            "nous|25ee24": {"mode": "free"},
            "openai|4c8d11": {"mode": "subscription"},
        },
        "remote_hosts": [REMOTE_HOST],
    }

    providers = []
    for entry in entries:
        if entry["provider"] not in providers:
            providers.append(entry["provider"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "accounts": entries,
        "providers": providers,
        "pool_available": True,
        "profiles": PROFILES + [REMOTE_HOST],
        "settings": settings,
    }


def iso_in(epoch: float, hours: float) -> str:
    return datetime.fromtimestamp(epoch + hours * 3600, tz=timezone.utc).isoformat()


def empty_payload() -> dict:
    totals = {key: 0 for key in (*CLASS_KEYS, "calls", "cost_est", "cost_actual", "active_days", "sessions", "tokens")}
    now = time.time()
    return {
        "available": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": 90,
        "bucket": "day",
        "bucket_timezone": "local",
        "daily": [],
        "by_provider": [],
        "by_model": [],
        "by_task": [],
        "by_day_provider": [],
        "totals": totals,
        "history": {"rows": 0, "first_seen": now, "last_seen": now},
    }


def unavailable_payload() -> dict:
    return {
        "available": False,
        "reason": "this Hermes home has no token accounting table yet",
        "path": "<hermes-home>/state.db",
    }


def default_hermes_home() -> Path:
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "hermes"
    return Path.home() / ".hermes"


def live_payloads(hermes_home: Path, days: int) -> tuple[dict, dict]:
    api = hermes_home / "plugins" / "token-master" / "dashboard" / "plugin_api.py"
    if not api.exists():
        raise SystemExit(f"--live needs the installed backend at {api}\n  run ./install.ps1 first, or pass --hermes-home")
    sys.path.insert(0, str(hermes_home / "hermes-agent"))
    spec = importlib.util.spec_from_file_location("tm_api", api)
    module = importlib.util.module_from_spec(spec)
    sys.modules["tm_api"] = module
    spec.loader.exec_module(module)
    return module._summary(days), module._accounts_payload(False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the .smoke/ JSON fixtures.")
    parser.add_argument("--live", action="store_true", help="dump this machine's real backend output")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    parser.add_argument("--seed", type=int, default=20261111, help="PRNG seed (synthetic mode)")
    parser.add_argument("--days", type=int, default=90, help="window length in days")
    parser.add_argument("--hermes-home", type=Path, default=None, help="Hermes install for --live")
    args = parser.parse_args()

    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    if args.live:
        summary, accounts = live_payloads(args.hermes_home or default_hermes_home(), args.days)
        origin = "live backend"
    else:
        summary, accounts = generate(args.seed, args.days)
        origin = f"synthetic (seed {args.seed})"

    (out / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (out / "accounts.json").write_text(json.dumps(accounts), encoding="utf-8")
    (out / "summary-empty.json").write_text(json.dumps(empty_payload()), encoding="utf-8")
    (out / "summary-unavailable.json").write_text(json.dumps(unavailable_payload()), encoding="utf-8")

    print(f"wrote {out} from {origin}")
    print(f"  summary: {len(summary.get('daily', []))} active days, {summary['totals']['tokens']:,} tokens")
    if summary.get("sources"):
        print(f"  sources: {', '.join(entry['id'] for entry in summary['sources'])}")
    print(f"  accounts: {len(accounts['accounts'])} entries")


if __name__ == "__main__":
    main()
