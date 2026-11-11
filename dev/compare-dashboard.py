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

DASHBOARD = {7: 2_150_000_000, 30: 7_804_000_000}

for days in (7, 30):
    summary = mod._summary(days)
    totals = summary["totals"]
    oc = next((r for r in summary["by_provider"] if r["provider"] == "opencode-go"), None)
    oc_tokens = oc["tokens"] if oc else 0
    sources = {s["id"]: s["tokens"] for s in summary["sources"]}
    dashboard = DASHBOARD[days]
    print(f"\n=== {days} days ===")
    print(f"  measured total      {totals['tokens']:>16,}")
    print(f"  measured opencode-go{oc_tokens:>16,}")
    print(f"  dashboard           {dashboard:>16,}")
    print(f"  ratio (open. vs dash) {oc_tokens / dashboard if dashboard else 0:>14.2f}x")
    print(f"  billable in+out     {totals['input'] + totals['output']:>16,}")
    for source, tokens in sources.items():
        print(f"    source {source:22} {tokens:>16,}")
    print("  providers:", ", ".join(f"{r['provider']}={r['tokens']:,}" for r in summary["by_provider"][:5]))
