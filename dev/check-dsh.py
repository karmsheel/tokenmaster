import json
from datetime import datetime
from pathlib import Path

root = Path(r"C:\Users\karms\.dsh\storages\session_projcache\sessions")
files = sorted(root.glob("*.json"))
print("session files:", len(files))

sample = max(files, key=lambda p: p.stat().st_size)
data = json.loads(sample.read_text(encoding="utf-8"))
rec = data.get("record") or {}

print("\n== sample:", sample.name, "==")
print("record keys:", sorted(rec.keys())[:40])

tu = rec.get("tokenUsage") or {}
print("\ntokenUsage keys:", sorted(tu.keys()))
val = tu.get("val") or {}
print("tokenUsage.val keys:", sorted(val.keys()))
print("totals:", json.dumps(val.get("totals"), indent=1))
last = val.get("last") or {}
print("last keys:", sorted(last.keys()), "buckets:", json.dumps(last.get("buckets"))[:200])

for key in ("id", "title", "model", "createdAt", "updatedAt", "startedAt", "cwd", "profile"):
    if key in rec:
        print(f"  {key}: {rec[key]}")

print("\n== all sessions: totals + dates ==")
rows = []
for path in files:
    try:
        rec = (json.loads(path.read_text(encoding="utf-8")).get("record") or {})
    except Exception:
        continue
    tu = ((rec.get("tokenUsage") or {}).get("val") or {}).get("totals") or {}
    total = sum(int(tu.get(k) or 0) for k in ("uncachedInputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens"))
    if total <= 0:
        continue
    stamp = rec.get("updatedAt") or rec.get("createdAt") or rec.get("lastActiveAt")
    rows.append((rec.get("id", path.stem)[:12], stamp, rec.get("model"), total, tu))

rows.sort(key=lambda r: str(r[1]))
print("sessions with usage:", len(rows))
for row in rows[:6]:
    print("  ", row[0], row[1], row[2], f"{row[3]:,}")
print("  ...")
for row in rows[-4:]:
    print("  ", row[0], row[1], row[2], f"{row[3]:,}")
print("GRAND TOTAL (all DSH sessions on disk):", f"{sum(r[3] for r in rows):,}")
