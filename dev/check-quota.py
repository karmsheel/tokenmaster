import importlib.util
import os
import sys
from pathlib import Path

HOME = Path(r"C:\Users\karms\AppData\Local\hermes")
sys.path.insert(0, str(HOME / "hermes-agent"))

for line in (HOME / ".env").read_text(encoding="utf-8", errors="ignore").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, value = line.partition("=")
    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

API = HOME / "plugins" / "token-master" / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("tm_api", API)
mod = importlib.util.module_from_spec(spec)
sys.modules["tm_api"] = mod
spec.loader.exec_module(mod)

payload = mod._accounts_payload(True)
print("profiles:", payload["profiles"])
for account in payload["accounts"]:
    limits = account["limits"] or {}
    windows = limits.get("windows") or []
    print(
        f"{account['provider']:16} supported={str(account['live_limits_supported']):5} "
        f"30d_tokens={account['usage_30d']['tokens']:>14,} "
        f"windows={[(w['label'], w['used_percent']) for w in windows]}"
    )
