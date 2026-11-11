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
totals = summary["totals"]
print(f"30d total: {totals['tokens']:,} tokens | calls {totals['calls']:,} | sessions {totals['sessions']}")
print("\nby source:")
for row in summary["by_source"]:
    print(f"  {row['source']:20} {row['tokens']:>16,}  ({row['sessions']} sessions)")
print("\nby provider:")
for row in summary["by_provider"]:
    print(f"  {row['provider']:20} {row['tokens']:>16,}")

# Hermes vs DSH on opencode-go
hermes_rows, _ = mod._usage_rows(30)
dsh_rows = mod._dsh_rows(30)
for label, rows in (("hermes", hermes_rows), ("deepseek-harness", dsh_rows)):
    total = sum(mod._token_sum(r) for r in rows if r["provider"] == "opencode-go")
    print(f"\nopencode-go via {label:18}: {total:>16,}")

print("\nsettings dir:", mod._settings_dir())
print("settings path:", mod._settings_path())
