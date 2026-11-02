import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import * as jsx from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'
import { load, mod, harness, tick, nodes, deferred } from '../breeding/test-support.mjs'

const validation = load('../breeding/validation.ts', {})
const helpers = load('../animals/record-chart.ts', { '../breeding/validation': validation })
const Chart = load('../animals/components/RecordChart.tsx', { 'react/jsx-runtime': jsx, '../record-chart': helpers }).default
const ProductionCharts = load('../animals/components/ProductionCharts.tsx', { 'react/jsx-runtime': jsx, './RecordChart': mod(Chart) }).default
const WeightOverview = load('../animals/components/WeightOverview.tsx', { 'react/jsx-runtime': jsx, './RecordChart': mod(Chart) }).default
const id = '11111111-1111-1111-1111-111111111111', other = '22222222-2222-2222-2222-222222222222'
const render = renderToStaticMarkup

test('graph rejects missing, ambiguous, negative, nonfinite and invalid date points', () => {
  for (const points of [[], [{}], [null], [{ date: '2026-01-01', value: '10' }], [{ date: '2026-01-01', value: '10' }, { date: '2026-01-01', value: '20' }], [{ date: '2026-02-30', value: '10' }, { date: '2026-03-01', value: '20' }], [{ date: '2026-01-01', value: '-1' }, { date: '2026-02-01', value: '20' }], [{ date: 'bad', value: 'NaN' }]]) {
    const html = render(Chart({ title: 'Test', unit: 'kg', points }))
    assert.doesNotMatch(html, /<svg/); assert.match(html, /no disponible/)
  }
})

test('graph uses elapsed time, true quantities and units; zero values remain on a zero baseline', () => {
  const points = [{ date: '2026-01-11', value: '10.00' }, { date: '2026-01-01', value: '0.00' }, { date: '2026-01-02', value: '5.00' }]
  const html = render(Chart({ title: 'Peso', unit: 'kg', points }))
  assert.match(html, /role="img"/); assert.match(html, /<desc>/)
  assert.match(html, /2026-01-01: 0.00 kg/); assert.match(html, /2026-01-11: 10.00 kg/)
  assert.match(html, /cx="124"/) // one day is 1/10 of the elapsed date range
  assert.equal(points[0].date, '2026-01-11')
  const zero = render(Chart({ title: 'Peso', unit: 'kg', points: [{ date: '2026-01-01', value: '0' }, { date: '2026-01-02', value: '0' }] }))
  assert.doesNotMatch(zero, /NaN|Infinity/); assert.match(zero, /cy="185"/)
  const utc = render(Chart({ title: 'UTC', unit: 'L', points: [{ date: '2026-01-01T23:00:00-06:00', value: '1' }, { date: '2026-01-03T12:00:00Z', value: '2' }] }))
  assert.match(utc, /y="215">2026-01-02<\/text>/)
})

test('production charts separate each type and exact unit; no totals or unit conversion', () => {
  const records = []
  for (const [production_type_id, unit] of [[id, 'L'], [id, 'kg'], [other, 'L']]) {
    for (const date of ['2026-01-01T12:00:00Z', '2026-01-02T12:00:00Z']) records.push({ production_type_id, unit, recorded_at: date, quantity: '10.50' })
  }
  const html = render(ProductionCharts({ records, types: [{ id, name: 'Leche' }, { id: other, name: 'Otro tipo' }] }))
  assert.equal((html.match(/<figure/g) ?? []).length, 3)
  assert.match(html, /· L/); assert.match(html, /· kg/); assert.doesNotMatch(html, /21\.00/)
  assert.doesNotMatch(render(ProductionCharts({ records: [{ ...records[0], unit: '' }], types: [] })), /<svg/)
})

test('weight summary uses latest date without inventing a same-day order; chart remains optional', () => {
  const records = [{ id, date: '2026-01-01', weight: '100.00' }, { id: other, date: '2026-02-01', weight: '150.00' }]
  assert.match(render(WeightOverview({ records })), /150.00 kg/)
  assert.equal(render(WeightOverview({ records: [] })), '')
  const html = render(WeightOverview({ records: [...records, { id: 'third', date: '2026-02-01', weight: '160.00' }] }))
  assert.match(html, /Sin datos/); assert.doesNotMatch(html, /<svg/)
})

test('vaccination cards keep actual next-date, details and readonly permissions; order is chronological', async () => {
  const hooks = harness(), rows = [
    { id, application_date: '2026-01-01', vaccine_name: 'Real A', dose: '2 ml', next_application_date: null, notes: 'Nota real', batch: null, veterinarian: null },
    { id: other, application_date: '2026-02-01', vaccine_name: 'Real B', dose: '1 ml', next_application_date: null },
  ]
  const History = load('../vaccinations/components/VaccinationHistory.tsx', {
    react: hooks.react, 'react/jsx-runtime': jsx, '../../auth/WriteOnly': mod(() => null),
    '../../auth/session': { getSession: () => ({ access: 'fake' }), getSessionRevision: () => 1 },
    '../vaccinations.service': { getAnimalVaccinationHistory: async () => rows },
  }).default
  const props = { animalId: id, saved: null, actionsDisabled: false, onLoaded() {} }
  hooks.render(History, props); await tick()
  const html = render(hooks.render(History, props))
  assert.ok(html.indexOf('Real B') < html.indexOf('Real A'))
  assert.match(html, /data-label="Vacuna"/); assert.doesNotMatch(html, /Nota real/)
  assert.doesNotMatch(html, /Editar|Eliminar|2026-03/)
  assert.equal(rows[0].vaccine_name, 'Real A')
})

test('production refuses another animal before showing cards or graph', async () => {
  const hooks = harness()
  const History = load('../production/components/ProductionHistory.tsx', {
    react: hooks.react, 'react/jsx-runtime': jsx, '../../auth/WriteOnly': mod(() => null),
    './ProductionForm': mod(() => null), './ProductionDeleteConfirmation': mod(() => null),
    '../../auth/session': { getSession: () => ({ access: 'fake' }) },
    '../../lib/api': { ApiError: class extends Error {} }, '../../lib/api-errors': {},
    '../production.service': { getAnimalProductionHistory: async () => [{ animal_id: other, notes: 'FOREIGN' }], getProductionTypes: async () => [] },
    '../../animals/components/ProductionCharts': mod(ProductionCharts),
  }).default
  const root = History({ animalId: id }), inner = hooks.render(root.type, root.props)
  const loaded = nodes(inner).find(n => typeof n.type === 'function' && n.props?.onRetry)
  hooks.unmount()
  // The loader's hooks belong to hooks; mount the data component directly after clearing its slots.
  hooks.slots.length = 0
  hooks.render(loaded.type, loaded.props); await tick()
  const html = render(hooks.render(loaded.type, loaded.props))
  assert.match(html, /role="alert"/); assert.doesNotMatch(html, /FOREIGN|<figure/)
})

test('timeline presents dated events newest first with distinct decorative icons and no unknown synthetic events', async () => {
  const hooks = harness(), pending = deferred()
  const Timeline = load('../animals/components/AnimalTimeline.tsx', { react: hooks.react, 'react/jsx-runtime': jsx, '../animal-detail.service': { getAnimalTimeline: () => pending.promise } }).default
  const props = { animalId: id, accessToken: 'fake', current: () => true }
  hooks.render(Timeline, props)
  pending.resolve([{ id, date: '2026-01-01', event_type: 'weight', title: 'Old real event', description: '100 kg' }, { id: other, date: '2026-02-01', event_type: 'vaccination', title: 'New real event', description: 'Aplicada' }])
  await tick()
  const html = render(hooks.render(Timeline, props))
  assert.ok(html.indexOf('New real event') < html.indexOf('Old real event'))
  assert.equal((html.match(/animal-timeline__marker/g) ?? []).length, 2)
  assert.equal((html.match(/aria-hidden="true"/g) ?? []).length, 2)
})

test('premium CSS is scoped away from approved general/login/dashboard and adapts records and timeline', () => {
  const css = readFileSync(new URL('./components/ExpedientSections.css', import.meta.url), 'utf8')
  for (const size of [1000, 600, 380]) assert.ok(css.includes(`max-width: ${size}px`))
  assert.match(css, /overflow-wrap: anywhere/); assert.match(css, /clip-path: inset\(50%\)/)
  assert.doesNotMatch(css, /\.animal-overview|\.login-|\.dashboard-/)
  assert.match(css, /summary:focus-visible/)
})
