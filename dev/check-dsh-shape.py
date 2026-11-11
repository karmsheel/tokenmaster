import json
from pathlib import Path

root = Path(r"C:\Users\karms\.dsh\storages\session_projcache\sessions")
sample = max(root.glob("*.json"), key=lambda p: p.stat().st_size)
data = json.loads(sample.read_text(encoding="utf-8"))


def walk(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            if key in ("tokenUsage", "totals", "identity", "rows"):
                summary = value
                if isinstance(value, dict):
                    summary = {k: (v if not isinstance(v, (dict, list)) else type(v).__name__) for k, v in value.items()}
                print(f"{here}: {json.dumps(summary)[:240]}")
            walk(value, here)
    elif isinstance(node, list):
        for index, value in enumerate(node[:3]):
            walk(value, f"{path}[{index}]")


walk(data)

print("\n=== identity block ===")
print(json.dumps(data["record"]["identity"], indent=1)[:900])

print("\n=== rows shape ===")
rows = data["record"]["rows"]
print("rows:", type(rows).__name__, len(rows))
if isinstance(rows, list) and rows:
    print("first row keys:", sorted(rows[0].keys()) if isinstance(rows[0], dict) else type(rows[0]))
    print(json.dumps(rows[0], indent=1)[:600])
