import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'
import { load, harness, nodes, text, tick, mod } from '../animal-movements/test-support.mjs'
import { id, farms, lots, organizationId } from '../animal-movements/flow-test-support.mjs'

const ui = load('../ui/components.tsx', { 'react/jsx-runtime': jsx })
const validation = load('./validation.ts', {})
const logic = load('../farms/farm-inventory.ts', { '../animal-movements/validation': validation })
const Icon = load('../components/navigation/ShellIcon.tsx', { 'react/jsx-runtime': jsx }).default
const Link = props => jsx.jsx('a', { ...props, href: props.to })
const imports = { 'react/jsx-runtime': jsx, 'react-router-dom': { Link }, '../../ui/components': ui,
  '../../components/navigation/ShellIcon': mod(Icon), '../farm-inventory': logic }
const action = (tree, label) => nodes(tree).find(n => n.type === ui.Button && text(n) === label)
function inventory(data = farms) {
  const h = harness(), Component = load('../farms/components/FarmInventory.tsx', { ...imports, react: h.react }).default
  return { render: () => h.render(Component, { farms: data }) }
}
test('cards default, identical order and farm links after repeated toggles', () => {
  const e = inventory(); let tree = e.render()
  assert.equal(action(tree, 'Tarjetas').props['aria-pressed'], true)
  const links = tree => nodes(tree).filter(n => n.type === Link).map(n => n.props.to)
  const cardLinks = links(tree)
  assert.deepEqual(cardLinks, farms.map(f => `/farms/${f.id}`))
  action(tree, 'Tabla').props.onClick(); tree = e.render()
  assert.equal(action(tree, 'Tabla').props['aria-pressed'], true)
  assert.deepEqual([...new Set(links(tree))], cardLinks)
  action(tree, 'Tarjetas').props.onClick(); tree = e.render()
  assert.deepEqual(links(tree), cardLinks)
})
test('cards and table expose available fields with explicit missing values', () => {
  const e = inventory([{ ...farms[0], city: '', state: ' ', code: '', farm_type: '' }])
  for (let i = 0; i < 2; i++) {
    const tree = e.render(), markup = renderToStaticMarkup(tree)
    assert.match(markup, /Sin datos/); assert.match(markup, /Farm 20/); assert.match(markup, /Ver finca/)
    assert.doesNotMatch(markup, /Eliminar|Editar/)
    if (!i) action(tree, 'Tabla').props.onClick()
  }
})
test('empty inventory remains accessible in either selected view', () => {
  const e = inventory([]); let tree = e.render(); assert.match(text(tree), /No hay fincas registradas/)
  action(tree, 'Tabla').props.onClick(); tree = e.render(); assert.match(text(tree), /No hay fincas registradas/)
})
test('invalid envelopes, duplicate farms and malformed display values rejected', () => {
  assert.equal(logic.isFarmInventory(farms), true)
  for (const value of [{ results: farms }, [farms[0], farms[0]], [{ ...farms[0], id: 'bad' }], [{ ...farms[0], name: {} }]]) assert.equal(logic.isFarmInventory(value), false)
})
function scope() {
  const h = harness(), calls = [], pending = { farms: [], lots: [], summary: [] }, context = { revision: 1, org: organizationId }
  const request = kind => (...args) => { calls.push({ kind, args }); return new Promise((resolve, reject) => pending[kind].push({ resolve, reject })) }
  const Page = load('../pages/FarmsPage.tsx', { react: h.react, 'react/jsx-runtime': jsx, 'react-router-dom': { Link },
    '../auth/WriteOnly': mod(() => null), '../auth/current-context': { useCurrentContext: () => ({ status: 'loaded', canRead: true, currentOrganization: { id: context.org }, isCurrentOrganization: org => org === context.org }) },
    '../auth/useSession': { useSession: () => ({ session: {}, revision: context.revision }) },
    '../auth/session': { getSession: () => ({ access: 'fixture' }), getSessionRevision: () => context.revision },
    '../farms/farms.service': { getFarms: request('farms') }, '../farms/farm-inventory': logic,
    '../farms/components/FarmInventory': mod(() => null), '../lots/lots.service': { getLots: request('lots') },
    '../animal-movements/validation': validation, '../dashboard/dashboard.service': { getDashboardSummary: request('summary') },
    '../lib/api-errors': { normalizeApiError: (_, message) => ({ message }) }, '../ui/components': ui,
  })
  const props = { revision: 1, organizationId, isCurrentOrganization: org => org === context.org }
  return { Page, calls, pending, context, unmount: h.unmount, render: () => h.render(Page.FarmScope, props), async resolve({ farmData = farms, lotData = lots, total = 325 } = {}) {
    pending.farms.shift().resolve(farmData); pending.lots.shift().resolve(lotData); pending.summary.shift().resolve({ total_animals: total }); await tick()
  } }
}
test('real independent indicators, list order untouched and no extra requests on rerender', async () => {
  const e = scope(); assert.match(text(e.render()), /Cargando fincas/)
  await e.resolve(); const tree = e.render()
  const cards = nodes(tree).filter(n => n.type === ui.Card)
  assert.match(text(cards), /Fincas disponibles2.*Lotes disponibles2.*Total de animales325/)
  assert.ok(nodes(tree).some(n => n.type === Link && n.props.to === '/lots'))
  e.render(); assert.equal(e.calls.length, 3); assert.ok(e.calls.every(c => c.args[1] instanceof AbortSignal))
})
test('zero counts are preserved and empty state list still rendered', async () => {
  const e = scope(); e.render(); await e.resolve({ farmData: [], lotData: [], total: 0 })
  const cards = nodes(e.render()).filter(n => n.type === ui.Card)
  assert.equal(cards.length, 3); assert.match(text(cards), /animales0/)
})
test('unavailable optional indicators omitted without blocking farms', async () => {
  const e = scope(); e.render(); e.pending.farms.shift().resolve(farms); e.pending.lots.shift().reject(Error()); e.pending.summary.shift().reject(Error()); await tick()
  const cards = nodes(e.render()).filter(n => n.type === ui.Card)
  assert.equal(cards.length, 1); assert.match(text(cards), /Fincas disponibles/)
})
test('lots from another tenant cannot supply an indicator', async () => {
  const e = scope(); e.render(); await e.resolve({ lotData: lots.map(l => ({ ...l, organization_id: id(999) })) })
  assert.doesNotMatch(text(e.render()), /Lotes disponibles/)
})
test('list error and invalid response offer retry; retry cancels previous reads', async () => {
  for (const invalid of [true, false]) {
    const e = scope(); e.render()
    if (invalid) e.pending.farms.shift().resolve({ results: farms }); else e.pending.farms.shift().reject(Error())
    await tick(); let tree = e.render(); assert.ok(nodes(tree).some(n => n.type === ui.ErrorState))
    action(tree, 'Reintentar').props.onClick(); tree = e.render()
    assert.match(text(tree), /Cargando fincas/); assert.equal(e.calls.length, 6)
    assert.ok(e.calls.slice(0, 3).every(c => c.args[1].aborted))
  }
})
for (const reason of ['session', 'tenant', 'unmount']) test(`late counts and list ignored on ${reason}`, async () => {
  const e = scope(); e.render()
  if (reason === 'session') e.context.revision++
  if (reason === 'tenant') e.context.org = id(999)
  if (reason === 'unmount') e.unmount()
  await e.resolve(); assert.doesNotMatch(text(e.render()), /325/)
})
test('tenant and session keys isolate A→B→A state', () => {
  const e = scope(); const first = e.Page.default().key
  e.context.org = id(999); const other = e.Page.default().key
  e.context.org = organizationId; e.context.revision++; assert.notEqual(e.Page.default().key, first); assert.notEqual(first, other)
})
test('farm and lot readers preserve endpoints and forward cancellation signals', async () => {
  const calls = [], apiRequest = (...args) => { calls.push(args); return Promise.resolve([]) }
  const f = load('../farms/farms.service.ts', { '../lib/api': { apiRequest } }), l = load('../lots/lots.service.ts', { '../lib/api': { apiRequest } })
  const signal = new AbortController().signal; await f.getFarms('test', signal); await l.getLots('test', signal)
  assert.equal(calls[0][0], '/farms/'); assert.equal(calls[1][0], '/lots/')
  assert.ok(calls.every(c => c[1].signal === signal && !c[1].method))
})
