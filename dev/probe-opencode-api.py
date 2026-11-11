"""Probe OpenCode for token-level usage (the dashboard shows tokens, so maybe an API does)."""

import json
import os
from pathlib import Path

HOME = Path(r"C:\Users\karms\AppData\Local\hermes")
for line in (HOME / ".env").read_text(encoding="utf-8", errors="ignore").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, value = line.partition("=")
    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

import httpx

key = os.environ.get("OPENCODE_GO_API_KEY", "").strip()
print("api key present:", bool(key), "len:", len(key))

headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
candidates = [
    "https://opencode.ai/zen/go/v1/usage",
    "https://opencode.ai/zen/v1/usage",
    "https://opencode.ai/zen/go/v1/usage/history",
    "https://opencode.ai/zen/go/v1/usage/daily",
    "https://opencode.ai/zen/go/v1/billing",
    "https://opencode.ai/zen/go/v1/subscription",
    "https://opencode.ai/zen/go/v1/me",
    "https://opencode.ai/zen/go/v1/models",
]

with httpx.Client(timeout=20.0) as client:
    for url in candidates:
        try:
            response = client.get(url, headers=headers)
            body = response.text[:900]
            print(f"\n{response.status_code}  {url}")
            print("  ", body.replace("\n", " ")[:700])
        except Exception as exc:
            print(f"\nERR {url}: {type(exc).__name__} {str(exc)[:120]}")
