import importlib.util
import json
import sys
from pathlib import Path

HOME = Path(r"C:\Users\karms\AppData\Local\hermes")
sys.path.insert(0, str(HOME / "hermes-agent"))

API = HOME / "plugins" / "token-master" / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("tm_api", API)
mod = importlib.util.module_from_spec(spec)
sys.modules["tm_api"] = mod
spec.loader.exec_module(mod)

print("== billing mode breakdown (summary 30d) ==")
summary = mod._summary(30)
for row in summary.get("by_billing_mode", []):
    print(f"  {row['mode']:24} {row['tokens']:>16,}")

print("\n== quota sample + trends ==")
payload = mod._accounts_payload(True)
for account in payload["accounts"]:
    trends = account.get("trends") or []
    if not account["limits"] and not trends:
        continue
    print(f"  {account['provider']}: windows={[ (w['label'], w['used_percent']) for w in (account['limits'] or {}).get('windows', []) ]}")
    for trend in trends:
        print(
            f"     {trend['window']:14} {trend['percent']:>5.1f}% "
            f"delta={trend['delta']:>6}pp over {trend['hours']:>5}h -> "
            f"{trend['percent_per_day']:>6}%/day, cap in {trend['days_to_cap']}d, "
            f"~{trend['tokens_per_percent']} tokens/1%, implied allowance {trend['implied_allowance']}"
        )

print("\n== quota samples on disk ==")
samples = mod._read_samples()
print("count:", len(samples), "path:", mod._quota_path())
if samples:
    print("last:", json.dumps(samples[-3:]))

print("\n== machines ==")
print("tailscale peers:", json.dumps(mod._tailscale_peers(), indent=1)[:500])
