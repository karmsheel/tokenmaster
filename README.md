# Token Master

Token spend analytics for [Hermes](https://hermes.nousresearch.com) — one graph of daily
token consumption across **every Hermes profile**, provider and account on the machine,
plus the screen that marks each credential as **subscription (quota)**, **API spend ($)**
or **free tier**.

Profiles matter: each profile keeps its own `state.db`, and a working profile can hold more
spend than the default one (on this machine the `coder` profile held 548M tokens in 90 days
against the default profile's 170M). Token Master reads them all and shows the split.

Built as two halves that share one plugin id:

| Half | File | Surface |
|---|---|---|
| Desktop UI | `plugin/desktop/plugin.js` | Hermes Desktop page at `/token-master`, sidebar row, ⌘K command, status-bar chip |
| Backend | `plugin/dashboard/plugin_api.py` | FastAPI router at `/api/plugins/token-master/` |

Everything else (`plugin/plugin.yaml`, `plugin/__init__.py`) exists so Hermes treats the
package as a real plugin it can enable — the agent side is deliberately empty.

## Why this design

- **No new collection.** Hermes already writes token accounting to `state.db`
  (`session_model_usage`: per session × model × task, every token class, the billing route,
  estimated/actual cost, and `first_seen`/`last_seen`). Token Master only aggregates it.
- **No restart, no build.** Desktop disk plugins load uncompiled and hot-reload on save.
  The backend router is hot-mounted on its first request
  (`hot-mount plugin API routes on first request` in `~/.hermes/logs/agent.log`).
- **Read-only database access.** The backend opens `state.db` with a `mode=ro` URI, so a
  dashboard request can never touch the writer, a lock, or a schema migration.

## What you see

- **Stacked chart, four stacking modes** — token class (input, output, reasoning, cache
  read, cache write), **provider**, **profile**, or **source** (Hermes vs DeepSeek Harness).
  Range chips 7D / 30D / 90D / 1Y; at ≥180 days the buckets roll up to months. Hover a
  column for the exact split.
- **KPIs** — total tokens, API calls, estimated spend, cache share of volume, all summed
  across profiles.
- **Breakdowns** — by provider, by profile, top models (main agent + auxiliary calls), and
  by task (main agent vs background review, compression, vision, titling).
- **Accounts & limits** — one row per credential-pool account with its 30-day usage,
  a mode selector, and any allowance windows Hermes can fetch (percent used + reset).

## Install

```powershell
./install.ps1
```

Copies the two halves into `%LOCALAPPDATA%\hermes` and enables the plugin:

```
~/.hermes/desktop-plugins/token-master/plugin.js        # Desktop UI
~/.hermes/plugins/token-master/{plugin.yaml,__init__.py,dashboard/*}   # backend + manifest
```

Then open Hermes Desktop: **Token Master** appears as a sidebar row, and the page mounts at
`/token-master`. If the row is missing, run ⌘K → *Reload desktop plugins*.

## Guide compliance

Built against the [Build a Hermes Plugin](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins)
guide and kept clean by both of its gates:

```powershell
hermes plugins doctor   ~/.hermes/plugins/token-master --ci   # discovery, manifest, import, register
hermes plugins validate ~/.hermes/plugins/token-master        # catalog admission checks
```

`validate` passes with no warnings: no private core imports, no core overrides, declared
tools/hooks match registrations. Two guide rules shape the backend:

- **Usage panels never touch credentials**: quota reads go through
  `fetch_account_usage(provider, read_only=True)`, which cannot refresh, rotate or rewrite a
  sign-in.
- **Durable state lives in the plugin data root** (`plugin-data/token-master/`), never in the
  install tree, so `hermes plugins update` / `remove` cannot destroy the user's settings.

## Data model, and the honest caveats

1. **History is per provider, not per login.** Neither `session_model_usage` nor DSH's ledger
   records which credential served a request, so history splits by provider and profile —
   never by which account login did the work. Per-account quota *is* live (provider windows),
   but per-account token history would have to be recorded forward-only.
2. **Days are bucketed by last activity**, not by when each token was spent: a Hermes row
   carries `last_seen`, a DSH session is attributed to its session file's last write. A
   session spanning midnight lands on the day it finished.
3. **Only this machine is covered.** A second machine (a VPS gateway, a laptop) has its own
   Hermes profiles and DSH home; their tokens are not in this database. Its *quota* still is,
   because the provider window is account-wide. Adding another machine means running the
   same collectors there and feeding the results in — see [Remote machines](#remote-machines).
4. **Live allowance windows are best-effort.** Hermes ships usage fetchers for
   `opencode-go`, `openai-codex`, `anthropic` and `openrouter` (`agent/account_usage.py`);
   `nous` and `xai-oauth` expose none, so those rows say so and lean on the manual mode.
   The card reads the warm cache first, then fills in once automatically; `Refresh limits`
   asks the providers again.

## Quota sampling

A provider window is a percentage, and a percentage only becomes a burn rate over time. Every
limits refresh appends a sample (`plugin-data/token-master/quota-samples.json` — timestamps and
percentages only, no secrets), and the accounts card derives:

- **%/day** — the observed burn rate for that window, from the last sample at least an hour old.
- **cap in Nd** — when the window would hit 100% at that rate.
- **~N tokens per 1%** — the tokens this plugin measured for that provider over the same stretch,
  divided by the percentage movement. This is the honest bridge between a token count and a
  provider dashboard: it says how many of *your* tokens one percent of allowance represents.

Sampling is passive: it needs the page open (or a refresh), so a long-idle period produces no
samples and no trend. Treat the trend as "what happened while I was watching", and the
percentage itself as the account-wide truth.

## Subscriptions (Claude, ChatGPT, and any other connected provider)

Subscription-backed routes are first-class, not special-cased:

- **Tokens** on an OAuth/plan route are recorded by Hermes with `cost_status: included`, so they
  are counted in every total and shown separately in the **Billing mix** card ("Subscription
  (included)" vs "API (estimated)"). A Claude Pro/Max or ChatGPT/Codex login therefore appears in
  the graph with zero dollar cost and real token volume — the correct shape for a plan you
  already pay for.
- **Quota** comes from the provider's own windows where Hermes has a fetcher: Anthropic
  (Claude session/weekly), `openai-codex` (5h + 7d), OpenCode Go (rolling/weekly/monthly),
  OpenRouter credits. `nous` and `xai-oauth` expose no windows and say so.
- **Any other connected provider** is already covered without code changes: the summary groups by
  whatever `billing_provider` Hermes recorded, and the accounts card lists every entry in the
  credential pool.

## Remote machines

Implemented. A machine is added by SSH host name in the **Remote machines** card; **Sync now**
streams `collector/scan_rows.py` into that host's `python3` over SSH, so nothing is installed
remotely and nothing is written there (its `state.db` is opened read-only). The rows are cached
under `plugin-data/token-master/remote/<host>.json` and join the chart as their own source,
so a machine can be added or removed without touching the local numbers.

Requirements: non-interactive SSH (`BatchMode=yes`) from the gateway's user, and `python3` on
the far side. The collector scans that machine's Hermes home (`~/.hermes`, all profiles) and
DeepSeek Harness home (`~/.dsh`).

What this *cannot* close: usage that no local ledger records. Provider quotas are account-wide,
so the percentage windows still cover every machine and every tool using that account — that is
the number to trust when a token count looks short.

## Where the numbers come from

Token counts and quota come from different places, because no single one sees everything:

| Source | What it provides | How |
|---|---|---|
| Hermes profiles | per-day tokens, billing route, model, aux tasks | `state.db` → `session_model_usage` in the root home **and** every `profiles/<name>/` |
| DeepSeek Harness | per-session token totals + the provider it routed through | `~/.dsh/storages/*/sessions/*.json` → `record.rows.tokenUsage.val.totals` |
| Provider APIs | **quota**, not tokens: percent used + reset | `agent.account_usage` (OpenCode Go `/zen/go/v1/usage`, OpenRouter credits, Codex windows) |

Two consequences worth knowing:

- **OpenCode Go has no token-history API.** Its usage endpoint returns percentages only —
  rolling / weekly / monthly (verified: `/zen/go/v1/usage` answers `{percent, resetsAt}`;
  `usage/history`, `usage/daily`, `billing`, `subscription` all 404 under the API key). So
  DSH's tokens can't be read *from* OpenCode; they are read from DSH's own ledger and
  attributed to `opencode-go` because that is the provider DSH routed through. That is why
  the same subscription shows both Hermes and harness traffic in one band.
- **Compare "billable", not "total".** Cache reads dominate real traffic — on this machine
  97.5% of opencode-go's 30-day volume is cache reads (input+output is ~44M of 1.81B). A
  provider dashboard that reports billed tokens will look ~40× smaller than a total that
  includes cache. The **Billable (in + out)** KPI exists for exactly that comparison.
- **Quota is the only cross-machine number.** A provider window covers every machine on the
  account, which token counting on one machine cannot. That is the number to trust for
  "how much of my subscription is left".

## Accounts & limits

`plugin-data/token-master/settings.json` holds one entry per `provider|account-id`:

```json
{ "version": 1, "accounts": { "nous|25ee24": { "mode": "subscription" } } }
```

OAuth credentials default to `subscription`, API keys to `api`. Saves go through
`PUT /api/plugins/token-master/settings`; the graph does not change, the account rows do —
this is the label that tells you whether a provider's tokens are quota or invoice.

## Develop

Edit the installed copy (`~/.hermes/desktop-plugins/token-master/plugin.js`) — the Desktop
app hot-reloads on save. The **backend is different**: the router is imported once and
hot-mounted on its first request, so editing `plugin_api.py` needs a gateway restart
(`hermes gateway restart`) before the running app sees the change. To render the UI without a
browser, `dev/` plus `.smoke/` provide a Node harness that loads the plugin with the real SDK
surface stubbed and renders it with React's server renderer against real backend JSON:

```powershell
python dev/make-fixtures.py          # dump live /summary + /accounts into .smoke/fixtures
copy plugin/desktop/plugin.js .smoke/token-master.mjs
cd .smoke; node run.mjs              # SMOKE OK  (render)
node data-test.mjs                   # CHART DATA OK  (stacked bars reconcile with totals)
```

`dev/check-mount.py` proves the backend is discovered, mounts on a fresh FastAPI app, and
answers 200 for `/summary`, `/accounts` and `/settings`. `dev/check-summary.py` prints the
aggregated numbers per window and per profile; `dev/check-profiles.py` and
`dev/compare-sources.py` are the read-only probes that established which tables and profiles
hold the spend.

## Uninstall

```powershell
hermes plugins disable token-master
Remove-Item -Recurse "$env:LOCALAPPDATA\hermes\desktop-plugins\token-master"
Remove-Item -Recurse "$env:LOCALAPPDATA\hermes\plugins\token-master"
Remove-Item -Recurse "$env:LOCALAPPDATA\hermes\plugin-data\token-master"
```
