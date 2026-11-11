import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\karms\AppData\Local\hermes\hermes-agent")

API = Path(r"C:\Users\karms\AppData\Local\hermes\plugins\token-master\dashboard\plugin_api.py")
spec = importlib.util.spec_from_file_location("tm_api", API)
mod = importlib.util.module_from_spec(spec)
sys.modules["tm_api"] = mod
spec.loader.exec_module(mod)

print("root home:", mod._root_home())
print("profile dbs:", [(n, p.exists()) for n, p in mod._profile_dbs()])

for days in (7, 30, 90, 365):
    summary = mod._summary(days)
    if not summary.get("available"):
        print(days, "UNAVAILABLE", summary)
        continue
    totals = summary["totals"]
    print(
        f"\n== {days}d == tokens={totals['tokens']:,} calls={totals['calls']:,} "
        f"active_days={totals['active_days']} sessions={totals['sessions']}"
    )
    print("  providers:", [(r["provider"], f"{r['tokens']:,}") for r in summary["by_provider"][:6]])
    print("  profiles :", [(r["profile"], f"{r['tokens']:,}") for r in summary["by_profile"][:8]])
    print("  models   :", [(r["model"], f"{r['tokens']:,}") for r in summary["by_model"][:4]])
    print("  tasks    :", [(r["task"], f"{r['tokens']:,}") for r in summary["by_task"][:5]])
    print(
        "  series   : daily=%d day_provider=%d day_profile=%d"
        % (len(summary["daily"]), len(summary["by_day_provider"]), len(summary["by_day_profile"]))
    )
    oc = [r for r in summary["by_provider"] if r["provider"] == "opencode-go"]
    print("  opencode-go:", f"{oc[0]['tokens']:,}" if oc else "MISSING")

accounts = mod._accounts_payload(False)
print("\n== accounts ==")
for account in accounts["accounts"]:
    print(
        f"  {account['provider']:14} {account['label'][:32]:32} mode={account['mode']:12} "
        f"30d={account['usage_30d']['tokens']:,} limits={'yes' if (account['limits'] or {}).get('windows') else 'no'}"
    )
print("profiles in accounts payload:", accounts["profiles"])
