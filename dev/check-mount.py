import sys

sys.path.insert(0, r"C:\Users\karms\AppData\Local\hermes\hermes-agent")

from fastapi import FastAPI

from hermes_cli import web_server_dashboard as wsd

plugins = wsd._discover_dashboard_plugins()
rows = [p for p in plugins if p.get("name") == "token-master"]
print("discovered token-master:", bool(rows))
for row in rows:
    print({k: row.get(k) for k in ("name", "source", "api", "enabled", "disabled")})

app = FastAPI()
mounted = []
if rows:
    with wsd._plugin_api_mount_lock:
        mounted.append(wsd._mount_one_plugin_api(app, rows[0], *wsd._plugin_enable_sets_here()))

print("mount returned:", mounted)
paths = sorted({getattr(r, "path", "") for r in app.router.routes if "plugins" in getattr(r, "path", "")})
print("routes:", paths)

if rows and mounted and mounted[0]:
    from fastapi.testclient import TestClient

    client = TestClient(app)
    for path in ("/api/plugins/token-master/summary?days=30", "/api/plugins/token-master/accounts", "/api/plugins/token-master/settings"):
        resp = client.get(path)
        body = resp.text
        print(path, "->", resp.status_code, body[:220].replace("\n", " "))
