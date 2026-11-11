import os
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\karms\AppData\Local\hermes\hermes-agent")

env = Path(r"C:\Users\karms\AppData\Local\hermes\.env")
for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, value = line.partition("=")
    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from agent.account_usage import fetch_account_usage
from agent.account_usage_cache import has_account_usage

for provider in ("opencode-go", "opencode", "opencode-zen", "openrouter", "xai-oauth", "nous"):
    try:
        supported = has_account_usage(provider)
        snap = fetch_account_usage(provider)
        windows = (
            [(w.label, w.used_percent, str(w.reset_at), w.scope) for w in snap.windows]
            if snap
            else None
        )
        print(f"{provider:14} supported={supported} snapshot={'yes' if snap else 'no'}")
        if windows:
            for window in windows:
                print("   ", window)
        elif snap is not None:
            print("    reason:", snap.unavailable_reason, "| plan:", snap.plan)
    except Exception as exc:
        print(f"{provider:14} ERR {type(exc).__name__}: {str(exc)[:110]}")
