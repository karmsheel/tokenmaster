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

print("collector present:", mod._collector_path().is_file(), mod._collector_path())

# Configure the machine, exactly as the page's settings call would.
mod._write_settings({"accounts": mod._read_settings().get("accounts") or {}, "remote_hosts": ["buzz-vps"]})
print("settings:", mod._read_settings())

result = mod._collect_host("buzz-vps", 3)
print("collect:", json.dumps(result, indent=1)[:600])

summary = mod._summary(3)
print("\n3d totals:", f"{summary['totals']['tokens']:,}")
print("sources:", [(s["id"], f"{s['tokens']:,}") for s in summary["sources"]])
print("remote:", summary["remote"])
print("daily:", [(d["day"], f"{d['tokens']:,}") for d in summary["daily"]])
