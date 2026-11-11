import importlib.util
import sys
from pathlib import Path

HOME = Path(r"C:\Users\karms\AppData\Local\hermes")
sys.path.insert(0, str(HOME / "hermes-agent"))

API = HOME / "plugins" / "token-master" / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("tm_api", API)
mod = importlib.util.module_from_spec(spec)
sys.modules["tm_api"] = mod
spec.loader.exec_module(mod)

summary = mod._summary(30)
per_day = {}
for row in summary["by_day_provider"]:
    if row["provider"] == "opencode-go":
        per_day[row["day"]] = per_day.get(row["day"], 0) + row["tokens"]

days = sorted(per_day)
print("opencode-go per day (last 12 days):")
for day in days[-12:]:
    print(f"  {day}  {per_day[day]:>16,}")

last7 = days[-7:]
last6 = days[-6:]
today = days[-1]
print("\nlast 7 recorded days :", f"{sum(per_day[d] for d in last7):,}", f"({last7[0]}..{last7[-1]})")
print("excluding the last day:", f"{sum(per_day[d] for d in last6):,}", f"({last6[0]}..{last6[-1]})")
print("only the last day    :", f"{per_day[today]:,}", f"({today})")
print("\ndashboard 7d          : 2,150,000,000")
print("dashboard 30d         : 7,804,000,000")
sum30 = sum(per_day.values())
print(f"measured 30d opencode-go: {sum30:,}  -> {sum30 / 7_804_000_000:.3f}x dashboard")
