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

rows = mod._usage_rows(30)[0] + mod._dsh_rows(30)
oc = [row for row in rows if row["provider"] == "opencode-go"]
print("opencode-go rows (30d):", len(oc))
for field in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens"):
    print(f"  {field:20} {sum(int(r.get(field) or 0) for r in oc):>16,}")
print(f"  {'TOTAL':20} {sum(mod._token_sum(r) for r in oc):>16,}")
io = sum(int(r.get("input_tokens") or 0) + int(r.get("output_tokens") or 0) for r in oc)
print(f"  {'input+output':20} {io:>16,}")
print(f"  {'cache share':20} {100 * sum(int(r.get('cache_read_tokens') or 0) for r in oc) / max(1, sum(mod._token_sum(r) for r in oc)):.1f}%")
