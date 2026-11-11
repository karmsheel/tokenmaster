// Loads the plugin under test straight from plugin/desktop/plugin.js, with its
// SDK import pointed at ./sdk/index.js. Both harnesses import from here, so
// there is no second copy of plugin.js to keep in sync.
import { readFileSync, writeFileSync } from 'node:fs'

const source = new URL('../plugin/desktop/plugin.js', import.meta.url)
const target = new URL('./plugin.under-test.mjs', import.meta.url)

const code = readFileSync(source, 'utf8')
if (!/@hermes\/plugin-sdk/.test(code)) {
  throw new Error(`no @hermes/plugin-sdk import found in ${source.pathname}`)
}

// The rewritten module lives in .smoke/, so a relative specifier resolves next
// to this file (and against the same react install the plugin already uses).
writeFileSync(target, code.replace(/from ['"]@hermes\/plugin-sdk['"]/, "from './sdk/index.js'"))

const plugin = await import(target.href)

export const buildBuckets = plugin.buildBuckets
export const resolveSeries = plugin.resolveSeries
export default plugin.default
