import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path(r"C:\Users\karms\AppData\Local\hermes")
sys.path.insert(0, str(HOME / "hermes-agent"))

API = HOME / "plugins" / "token-master" / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("tm_api", API)
mod = importlib.util.module_from_spec(spec)
sys.modules["tm_api"] = mod
spec.loader.exec_module(mod)

summary = mod._summary(3)
print("3-day window totals:", f"{summary['totals']['tokens']:,}", "tokens")
print("  by source:", {r["source"]: f"{r['tokens']:,}" for r in summary["by_source"]})
print("  by provider:", {r["provider"]: f"{r['tokens']:,}" for r in summary["by_provider"]})
print("  daily:", [(r["day"], f"{r['tokens']:,}") for r in summary["daily"]])
print("  input+output:", f"{summary['totals']['input'] + summary['totals']['output']:,}")

# Are there DSH session stores outside storages/*/sessions/?
dsh = mod._dsh_home()
print("\nDSH home:", dsh)
found = sorted(dsh.glob("**/sessions/*.json"))
print("session json files found anywhere under DSH_HOME:", len(found))
roots = sorted({str(p.parent) for p in found})
for root in roots:
    print("  store:", root, len(list(Path(root).glob('*.json'))))
