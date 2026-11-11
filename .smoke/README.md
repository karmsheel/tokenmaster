# .smoke — the browserless render harness

Renders the real plugin through React's server renderer with a stubbed
`@hermes/plugin-sdk`, so a broken component or a missing section fails a command
instead of showing up in the Desktop app.

```powershell
cd .smoke
node run.mjs        # SMOKE OK       — registers, renders, checks the sections exist
node data-test.mjs  # CHART DATA OK  — stacked buckets reconcile with payload totals
```

## How it loads the plugin

`load-plugin.mjs` reads `../plugin/desktop/plugin.js`, rewrites its
`@hermes/plugin-sdk` import to `./sdk/index.js`, writes `plugin.under-test.mjs`
(gitignored) and imports that. Both harnesses go through it, so there is no
second copy of `plugin.js` to keep in sync — edit the plugin and the harness
picks it up.

`sdk/index.js` is the stub: it mirrors the exports the plugin imports and hands
`useQuery` the fixture payloads rather than calling a backend.

## Fixtures

`fixtures/` is written by `../dev/make-fixtures.py`:

| File | What it is |
|---|---|
| `summary.json` | 90 days of daily token rows plus every breakdown — **synthetic** |
| `accounts.json` | credential pool, spend modes, quota windows — **synthetic** |
| `summary-empty.json` | fresh install: `available` but no rows |
| `summary-unavailable.json` | no accounting table: `available: false` |

The committed fixtures are synthetic: same shape as the backend's real payload,
but invented accounts, profile names and token volumes, so they are safe to
publish. They are also deterministic — same `--seed`, same bytes.

Point the harness at the other fixtures to render the empty and error paths:

```powershell
$env:SMOKE_SUMMARY='summary-empty.json';        node run.mjs
$env:SMOKE_SUMMARY='summary-unavailable.json';  node run.mjs
```

To test against your own database instead:

```powershell
python ../dev/make-fixtures.py --live          # your Hermes home, real numbers
python ../dev/make-fixtures.py                 # back to synthetic (the committed state)
```

**Don't commit `--live` output.** It carries your accounts, profiles and spend.

`data-test.mjs` slides the fixture days onto today before asserting, so a
fixture generated months ago still tests the 90-day window.

## React

`react` and `react-dom` are not vendored. `node_modules/` holds junctions into
the Hermes Desktop install, which already ships both:

```powershell
New-Item -ItemType Junction -Path node_modules\react     -Target "$env:LOCALAPPDATA\hermes\hermes-agent\node_modules\react"
New-Item -ItemType Junction -Path node_modules\react-dom -Target "$env:LOCALAPPDATA\hermes\hermes-agent\node_modules\react-dom"
```

If the Desktop app is installed somewhere else, point the junctions there.
