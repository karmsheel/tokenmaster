import sqlite3
from pathlib import Path

H = Path(r"C:\Users\karms\AppData\Local\hermes")
now = 1794438000
cutoff90 = now - 90 * 86400

dbs = [H / "state.db"] + sorted((H / "profiles").glob("*/state.db"))
print("databases found:", len(dbs))

grand = 0
for db in dbs:
    label = "root(default)" if db.parent == H else f"profile:{db.parent.name}"
    try:
        c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        tables = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
        if "session_model_usage" not in tables:
            print(f"{label:22} no usage table")
            continue
        row = c.execute(
            """SELECT COUNT(*) n,
                      COALESCE(SUM(input_tokens+output_tokens+cache_read_tokens+cache_write_tokens+reasoning_tokens),0) tok
               FROM session_model_usage WHERE last_seen >= ?""",
            (cutoff90,),
        ).fetchone()
        provs = c.execute(
            """SELECT COALESCE(NULLIF(billing_provider,''),'none') p,
                      SUM(input_tokens+output_tokens+cache_read_tokens+cache_write_tokens+reasoning_tokens) tok
               FROM session_model_usage WHERE last_seen >= ? GROUP BY p ORDER BY tok DESC""",
            (cutoff90,),
        ).fetchall()
        grand += int(row["tok"])
        print(f"{label:22} rows={row['n']:4} 90d_tokens={int(row['tok']):>12,}")
        for p in provs:
            print(f"{'':22}   {p['p']:14} {int(p['tok'] or 0):>12,}")
        c.close()
    except Exception as exc:
        print(f"{label:22} ERROR {type(exc).__name__}: {str(exc)[:90]}")

print(f"\nTOTAL across all profile DBs (90d): {grand:,}")

# root DB session profile distribution
c = sqlite3.connect(f"file:{(H / 'state.db').as_posix()}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("\nroot DB sessions by profile_name:")
for r in c.execute(
    "SELECT COALESCE(profile_name,'(null)') p, COUNT(*) n FROM sessions GROUP BY p ORDER BY n DESC"
):
    print("   ", dict(r))
print("\nroot DB profile-scoped dirs:")
for d in sorted((H / "profiles").iterdir()):
    if d.is_dir():
        db = d / "state.db"
        print(f"   {d.name:16} state.db={'yes' if db.exists() else 'no'}"
              + (f" ({db.stat().st_size:,} bytes)" if db.exists() else ""))
