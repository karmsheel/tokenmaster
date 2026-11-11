// Minimal stand-in for @hermes/plugin-sdk, used only to render the plugin in
// Node for a smoke test. Mirrors the real exports the plugin imports, and hands
// useQuery the fixture payloads instead of a live backend.
//
// `load-plugin.mjs` rewrites the plugin's SDK import to point here. Point
// SMOKE_SUMMARY at summary-empty.json or summary-unavailable.json to render the
// empty and error paths instead.
import { readFileSync } from 'node:fs'

const fixtures = new URL('../fixtures/', import.meta.url)
const summary = JSON.parse(
  readFileSync(new URL(process.env.SMOKE_SUMMARY || 'summary.json', fixtures), 'utf8')
)
const accounts = JSON.parse(readFileSync(new URL('accounts.json', fixtures), 'utf8'))

export const ROUTES_AREA = 'routes'
export const SIDEBAR_NAV_AREA = 'sidebar.nav'
export const PALETTE_AREA = 'palette'
export const STATUSBAR_AREAS = { left: 'statusBar.left', right: 'statusBar.right' }

export const host = {
  navigate: (path) => console.log('[host.navigate]', path),
  notify: (payload) => console.log('[host.notify]', payload),
  notifyError: (message) => console.log('[host.notifyError]', message)
}

export function compactNumber(value) {
  const n = Number(value) || 0
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(Math.round(n))
}

export function useQuery(options) {
  const key = JSON.stringify(options.queryKey || [])
  const data = key.includes('accounts') ? accounts : summary
  return { data, isFetching: false, isError: false, error: null, refetch: () => {} }
}

export function useQueryClient() {
  return { invalidateQueries: async () => {} }
}
