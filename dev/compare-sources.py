import sqlite3

DB = r"C:\Users\karms\AppData\Local\hermes\state.db"
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
c.row_factory = sqlite3.Row

now = 1794438000  # 2026-11-11 ~15:40 SAST
for days in (7, 30, 90, 365):
    cutoff = now - days * 86400
    print(f"\n===== window {days}d (cutoff {cutoff}) =====")

    s = c.execute(
        """SELECT COALESCE(SUM(input_tokens),0) i, COALESCE(SUM(output_tokens),0) o,
                  COALESCE(SUM(cache_read_tokens),0) cr, COALESCE(SUM(cache_write_tokens),0) cw,
                  COALESCE(SUM(reasoning_tokens),0) r, COALESCE(SUM(api_call_count),0) calls,
                  COUNT(*) n FROM sessions WHERE started_at >= ?""",
        (cutoff,),
    ).fetchone()
    print("sessions   :", dict(s), "total", s["i"] + s["o"] + s["cr"] + s["cw"] + s["r"])

    u = c.execute(
        """SELECT COALESCE(SUM(input_tokens),0) i, COALESCE(SUM(output_tokens),0) o,
                  COALESCE(SUM(cache_read_tokens),0) cr, COALESCE(SUM(cache_write_tokens),0) cw,
                  COALESCE(SUM(reasoning_tokens),0) r, COALESCE(SUM(api_call_count),0) calls,
                  COUNT(*) n FROM session_model_usage WHERE last_seen >= ?""",
        (cutoff,),
    ).fetchone()
    print("usage rows :", dict(u), "total", u["i"] + u["o"] + u["cr"] + u["cw"] + u["r"])

    print("-- sessions by provider --")
    for row in c.execute(
        """SELECT COALESCE(NULLIF(billing_provider,''),'none') p, COUNT(*) n,
                  SUM(input_tokens+output_tokens+cache_read_tokens+cache_write_tokens+reasoning_tokens) tok,
                  SUM(COALESCE(api_call_count,0)) calls
           FROM sessions WHERE started_at >= ? GROUP BY p ORDER BY tok DESC""",
        (cutoff,),
    ):
        print("   ", dict(row))

    print("-- usage rows by provider --")
    for row in c.execute(
        """SELECT COALESCE(NULLIF(billing_provider,''),'none') p, COUNT(*) n,
                  SUM(input_tokens+output_tokens+cache_read_tokens+cache_write_tokens+reasoning_tokens) tok
           FROM session_model_usage WHERE last_seen >= ? GROUP BY p ORDER BY tok DESC""",
        (cutoff,),
    ):
        print("   ", dict(row))

print("\n== usage rows with task values ==")
for row in c.execute(
    "SELECT COALESCE(NULLIF(task,''),'(none)') t, COUNT(*) n FROM session_model_usage GROUP BY t"
):
    print("   ", dict(row))

print("\n== opencode-go sessions sample ==")
for row in c.execute(
    """SELECT id, started_at, model, billing_provider, billing_mode, input_tokens, output_tokens,
              cache_read_tokens, api_call_count, estimated_cost_usd
       FROM sessions WHERE billing_provider = 'opencode-go' ORDER BY started_at DESC LIMIT 8"""
):
    print("   ", dict(row))

print("\n== opencode-go usage rows sample ==")
for row in c.execute(
    """SELECT session_id, model, task, input_tokens, output_tokens, cache_read_tokens,
              api_call_count, first_seen, last_seen
       FROM session_model_usage WHERE billing_provider = 'opencode-go' ORDER BY last_seen DESC LIMIT 8"""
):
    print("   ", dict(row))
