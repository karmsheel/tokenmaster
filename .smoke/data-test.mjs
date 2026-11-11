// Numeric checks on the chart's data layer: the stacked series must reconcile
// with the backend totals, and opencode-go must be its own series.
import { readFileSync } from 'node:fs'
import { buildBuckets, resolveSeries } from './load-plugin.mjs'

const DAY_MS = 86400000
const pad2 = (value) => String(value).padStart(2, '0')
const keyOf = (date) => `${date.getUTCFullYear()}-${pad2(date.getUTCMonth() + 1)}-${pad2(date.getUTCDate())}`
const toUtc = (key) =>
  Date.UTC(Number(key.slice(0, 4)), Number(key.slice(5, 7)) - 1, Number(key.slice(8, 10)))

// The fixtures are committed, so their day keys are frozen at the moment they
// were generated while buildBuckets anchors its window to today. Slide the whole
// payload forward so the 90-day assertions still see the data.
function anchor(fixture) {
  const days = (fixture.daily || []).map((row) => row.day).sort()
  if (days.length === 0) return fixture
  const now = new Date()
  const shift = Math.round((toUtc(keyOf(now)) - toUtc(days[days.length - 1])) / DAY_MS)
  if (shift === 0) return fixture
  const move = (key) => keyOf(new Date(toUtc(key) + shift * DAY_MS))
  const shifted = (rows) => (rows || []).map((row) => ({ ...row, day: move(row.day) }))
  return {
    ...fixture,
    daily: shifted(fixture.daily),
    by_day_provider: shifted(fixture.by_day_provider),
    by_day_profile: shifted(fixture.by_day_profile),
    by_day_source: shifted(fixture.by_day_source)
  }
}

const data = anchor(JSON.parse(readFileSync(new URL('./fixtures/summary.json', import.meta.url), 'utf8')))
let failures = 0

function check(label, actual, expected, tolerance = 0) {
  const ok = Math.abs(actual - expected) <= tolerance
  if (!ok) {
    failures += 1
    console.log(`FAIL ${label}: actual=${actual} expected=${expected}`)
  } else {
    console.log(`ok   ${label}: ${actual}`)
  }
}

const total = data.totals.tokens
console.log(`fixture: ${data.daily.length} days, ${total.toLocaleString()} tokens, profiles=${data.profiles.length}`)

// ── class stacking reconciles with totals ────────────────────────────────────
const classSeries = resolveSeries(data, 'class')
const classBuckets = buildBuckets(data, 90, false, 'class', classSeries)
check('class buckets cover 90 days', classBuckets.length, 90)
const classSum = classBuckets.reduce((sum, bucket) => sum + bucket.total, 0)
check('class stack sum == totals.tokens', classSum, total)
check(
  'input component == totals.input',
  classBuckets.reduce((sum, bucket) => sum + bucket.values.input, 0),
  data.totals.input
)
check(
  'cache component == totals.cache_read',
  classBuckets.reduce((sum, bucket) => sum + bucket.values.cache_read, 0),
  data.totals.cache_read
)

// ── provider stacking shows opencode-go as its own band ──────────────────────
const providerSeries = resolveSeries(data, 'provider')
const names = providerSeries.map((entry) => entry.key)
console.log('provider series:', names.join(', '))
if (!names.includes('opencode-go')) {
  failures += 1
  console.log('FAIL opencode-go missing from provider series')
}
const providerBuckets = buildBuckets(data, 90, false, 'provider', providerSeries)
const providerSum = providerBuckets.reduce((sum, bucket) => sum + bucket.total, 0)
check('provider stack sum == totals.tokens', providerSum, total)
const ocSum = providerBuckets.reduce((sum, bucket) => sum + bucket.values['opencode-go'], 0)
const ocExpected = data.by_provider.find((row) => row.provider === 'opencode-go').tokens
check('opencode-go series sum == payload', ocSum, ocExpected)
console.log(`     opencode-go share: ${((ocSum / total) * 100).toFixed(1)}%`)

// ── profile stacking reconciles with its own breakdown ───────────────────────
const profileSeries = resolveSeries(data, 'profile')
const profileBuckets = buildBuckets(data, 90, false, 'profile', profileSeries)
check(
  'profile stack sum == totals.tokens',
  profileBuckets.reduce((sum, bucket) => sum + bucket.total, 0),
  total
)

// ── source stacking: the harness must be its own band ────────────────────────
const sourceSeries = resolveSeries(data, 'source')
const sourceNames = sourceSeries.map((entry) => entry.key)
console.log('source series:', sourceNames.join(', '))
if (!sourceNames.includes('deepseek-harness')) {
  failures += 1
  console.log('FAIL deepseek-harness missing from source series')
}
const sourceBuckets = buildBuckets(data, 90, false, 'source', sourceSeries)
check(
  'source stack sum == totals.tokens',
  sourceBuckets.reduce((sum, bucket) => sum + bucket.total, 0),
  total
)
const dshSum = sourceBuckets.reduce((sum, bucket) => sum + bucket.values['deepseek-harness'], 0)
console.log(`     deepseek-harness share: ${((dshSum / total) * 100).toFixed(1)}%`)

// ── monthly roll-up ──────────────────────────────────────────────────────────
const monthly = buildBuckets(data, 365, true, 'class', classSeries)
const monthlySum = monthly.reduce((sum, bucket) => sum + bucket.total, 0)
check('monthly buckets sum == totals.tokens', monthlySum, total)
console.log(
  'monthly buckets:',
  monthly.map((bucket) => `${bucket.key}(${bucket.total.toLocaleString()})`).join(' ')
)

console.log(failures === 0 ? 'CHART DATA OK' : `CHART DATA FAILURES: ${failures}`)
process.exitCode = failures === 0 ? 0 : 1

