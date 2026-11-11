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

out = Path(r"C:\Users\karms\Projects\tokenmaster\.smoke\fixtures")
out.mkdir(parents=True, exist_ok=True)

summary = mod._summary(90)
accounts = mod._accounts_payload(False)
(out / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
(out / "accounts.json").write_text(json.dumps(accounts), encoding="utf-8")
print("summary days:", len(summary["daily"]), "tokens:", summary["totals"]["tokens"])
print("accounts:", [(a["provider"], a["mode"]) for a in accounts["accounts"]])
