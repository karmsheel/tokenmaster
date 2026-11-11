// Render the Token Master plugin in Node against the stubbed SDK + real React,
// using the live backend's own JSON as fixtures. Catches render-time crashes,
// undefined components and empty render paths without a browser.
import { renderToStaticMarkup } from 'react-dom/server'

const calls = []
globalThis.document = {
  head: { append: () => {} },
  createElement: () => ({ textContent: '', remove: () => {} })
}

const plugin = (await import('./load-plugin.mjs')).default
const registrations = []
const disposers = []
const ctx = {
  source: `plugin:${plugin.id}`,
  register: (contribution) => {
    registrations.push(contribution)
    return () => {}
  },
  registerMany: (contributions) => {
    registrations.push(...contributions)
    return () => {}
  },
  registerSettingsPage: () => () => {},
  onDispose: (fn) => disposers.push(fn),
  onEvent: () => () => {},
  setTimeout: () => () => {},
  setInterval: () => () => {},
  addEventListener: () => () => {},
  rest: async (path) => {
    calls.push(path)
    return { ok: true }
  },
  storage: { get: (_k, fallback) => fallback, set: () => {}, remove: () => {} },
  i18n: { t: (key) => key, onLocaleChange: () => () => {}, register: () => {} },
  os: { openExternal: () => {} },
  pet: { say: () => {} },
  runAction: () => ({ ok: true }),
  listActions: () => []
}

plugin.register(ctx)

console.log('id:', plugin.id, '| name:', plugin.name)
console.log('disposers registered:', disposers.length)
console.log(
  'contributions:',
  registrations.map((c) => `${c.area}:${c.id}`).join(', ')
)

let failures = 0
for (const contribution of registrations) {
  if (typeof contribution.render !== 'function') continue
  const label = `${contribution.area}:${contribution.id}`
  try {
    const html = renderToStaticMarkup(contribution.render())
    const checks = ['tm-page', 'Token Master', 'Tokens per day', 'Accounts &amp; limits']
    const found = checks.filter((needle) => html.includes(needle))
    console.log(
      `${label} -> ${html.length} bytes | rects=${(html.match(/<rect/g) || []).length} | found=[${found.join(', ')}]`
    )
    if (label === 'sidebar.nav:nav') continue
    const page = label.endsWith(':page')
    if (page && !html.includes('Token Master')) {
      failures += 1
      console.log('  MISSING title')
    }
    if (page) {
      for (const needle of ['Tokens per day', 'By provider', 'By profile', 'Top models', 'By task', 'stack', 'Accounts &amp; limits']) {
        if (!html.includes(needle)) {
          failures += 1
          console.log(`  MISSING section: ${needle}`)
        }
      }
      if (!/1\.\dM|k|M/.test(html)) {
        failures += 1
        console.log('  MISSING formatted numbers')
      }
    }
  } catch (error) {
    failures += 1
    console.log(`${label} -> THREW ${error && error.stack ? error.stack.split('\n').slice(0, 4).join(' | ') : error}`)
  }
}

console.log(failures === 0 ? 'SMOKE OK' : `SMOKE FAILURES: ${failures}`)

