import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'
import { load, harness, nodes, text, tick, mod } from '../animal-movements/test-support.mjs'
import { id, farms, lots, organizationId } from '../animal-movements/flow-test-support.mjs'
const ui = load('../ui/components.tsx', { 'react/jsx-runtime': jsx })
const validation = load('./validation.ts', {})
const farmLogic = load('../farms/farm-inventory.ts', { '../animal-movements/validation': validation })
const logic = load('../lots/lot-inventory.ts', {})
const Icon = load('../components/navigation/ShellIcon.tsx', { 'react/jsx-runtime': jsx }).default
const Link = props => jsx.jsx('a', { ...props, href: props.to })
const Reference = load('../lots/components/FarmReference.tsx', { 'react/jsx-runtime': jsx, 'react-router-dom': { Link } }).default
const imports = { 'react/jsx-runtime': jsx, 'react-router-dom': { Link }, '../../ui/components': ui,
  '../../components/navigation/ShellIcon': mod(Icon), '../../farms/farm-inventory': farmLogic, '../lot-inventory': logic, './FarmReference': mod(Reference) }
const six = Array.from({ length: 6 }, (_, i) => ({ ...lots[i%2], id: id(100+i), name: `Potrero ${i}`, code: `L-0${i}`, capacity: i * 10 }))
const farmMap = new Map(farms.map(f => [f.id, f]))
const action = (tree, label) => nodes(tree).find(n => n.type === ui.Button && text(n) === label)
const control = (tree, id) => nodes(tree).find(n => n.type === ui.Field && n.props.id === id).props.children({ id })
function inventory(data = six, farm, map = farmMap) {
  const h = harness(), Component = load('../lots/components/LotInventory.tsx', { ...imports, react: h.react }).default
  return { render: () => h.render(Component, { lots: data, farms: map, farm }) }
}
for (const query of ['potrero 5', 'L-05', '  POTRERO 5  ']) test(`complete six-lot search by name/code: ${query}`, () => {
  assert.equal(logic.filterLots(six, query, '').length, 1)
})
test('search is accent insensitive, and farm identity uses exact ID', () => {
  assert.equal(logic.filterLots([{ ...six[0], name: 'José' }], 'jose', farms[0].id).length, 1)
  assert.equal(logic.filterLots(six, '', farms[0].id).length, 3)
  assert.equal(logic.filterLots(six, '', id(999)).length, 0)
})
test('capacity sums registered values, preserves zero and omits invalid or unsafe totals', () => {
  assert.equal(logic.totalCapacity(six), 150)
  assert.equal(logic.totalCapacity([{ ...six[0], capacity: 0 }]), 0)
  for (const capacity of [null, -1, 1.5, Number.MAX_SAFE_INTEGER + 1]) assert.equal(logic.totalCapacity([{ ...six[0], capacity }]), null)
  assert.equal(logic.totalCapacity([{ ...six[0], capacity: Number.MAX_SAFE_INTEGER }, { ...six[1], capacity: 1 }]), null)
})
test('cards default, six real fixture rows, correct independent indicators and unit explanation', () => {
  const tree = inventory().render()
  assert.equal(action(tree, 'Tarjetas').props['aria-pressed'], true)
  assert.equal(nodes(tree).filter(n => n.type === Link).length, 6)
  const stats = nodes(tree).find(n => n.props?.className === 'lot-premium-stats')
  assert.match(text(stats), /Total de lotes6.*Fincas vinculadas2.*Capacidad total registrada150/)
  assert.match(text(tree), /no especifica la unidad/); assert.match(text(tree), /no es ocupación/)
})
test('filter and search retained between views, exact same ordered lots and global indicators', () => {
  const e = inventory(); let tree = e.render()
  control(tree, 'lot-inventory-search').props.onChange({ target: { value: 'Potrero' } }); tree = e.render()
  control(tree, 'lot-inventory-farm').props.onChange({ target: { value: farms[0].id } }); tree = e.render()
  const links = tree => nodes(tree).filter(n => n.type === Link && n.props.to.startsWith('/lots/')).map(n => n.props.to)
  const expected = links(tree); assert.equal(expected.length, 3)
  action(tree, 'Tabla').props.onClick(); tree = e.render()
  assert.deepEqual([...new Set(links(tree))], expected)
  assert.equal(control(tree, 'lot-inventory-search').props.value, 'Potrero')
  assert.equal(control(tree, 'lot-inventory-farm').props.value, farms[0].id)
  assert.match(text(tree), /3 resultados de 6 lotes/)
  assert.match(text(nodes(tree).find(n => n.props?.className === 'lot-premium-stats')), /registrada150/)
  action(tree, 'Limpiar filtros').props.onClick(); tree = e.render(); assert.match(text(tree), /6 resultados de 6/)
})
test('farm-specific inventory never leaks another farm after clear or view change', () => {
  const e = inventory(six, farms[0]); let tree = e.render()
  assert.equal(nodes(tree).some(n => n.type === ui.Field && n.props.id === 'lot-inventory-farm'), false)
  assert.match(text(tree), /3 resultados de 3/)
  control(tree, 'lot-inventory-search').props.onChange({ target: { value: 'L-01' } }); tree = e.render()
  assert.match(text(tree), /No hay resultados/)
  action(tree, 'Limpiar filtros').props.onClick(); tree = e.render()
  action(tree, 'Tabla').props.onClick(); tree = e.render()
  const ids = nodes(tree).filter(n => n.type === Link && n.props.to.startsWith('/lots/')).map(n => n.props.to)
  assert.ok(ids.every(path => six.filter(l => l.farm_id === farms[0].id).some(l => path.endsWith(l.id))))
})
test('empty inventory, empty filtered result and missing farm relation remain explicit', () => {
  assert.match(text(inventory([]).render()), /No hay lotes registrados/)
  assert.match(text(inventory([], farms[0]).render()), /Esta finca todavía no tiene lotes/)
  const e = inventory([{ ...six[0], name: '', code: '' }], undefined, new Map()); let tree = e.render()
  const markup = renderToStaticMarkup(tree); assert.match(markup, /Sin datos/); assert.match(markup, /Finca no disponible/)
  assert.doesNotMatch(markup, /Editar|Eliminar|Nuevo lote/)
  control(tree, 'lot-inventory-search').props.onChange({ target: { value: 'missing' } }); tree = e.render(); assert.match(text(tree), /No hay resultados/)
})
test('farm reference and lot links remain readable and use existing detail routes', () => {
  const markup = renderToStaticMarkup(inventory().render())
  assert.ok(markup.includes(`/lots/${six[0].id}`)); assert.ok(markup.includes(`/farms/${farms[0].id}`)); assert.match(markup, /Farm 20/)
})
function scope(farm) {
  const h = harness(), calls = [], pending = { lots: [], farms: [] }, context = { org: organizationId, revision: 1 }
  const request = kind => (...args) => { calls.push({ kind, args }); return new Promise((resolve, reject) => pending[kind].push({ resolve, reject })) }
  const Component = load('../lots/components/LotList.tsx', { react: h.react, 'react/jsx-runtime': jsx,
    '../../auth/current-context': { useCurrentContext: () => ({ status: 'loaded', canRead: true, currentOrganization: { id: context.org }, isCurrentOrganization: org => org === context.org }) },
    '../../auth/useSession': { useSession: () => ({ session: {}, revision: context.revision }) },
    '../../auth/session': { getSession: () => ({ access: 'fixture' }), getSessionRevision: () => context.revision },
    '../../farms/farms.service': { getFarms: request('farms') }, '../../farms/farm-inventory': farmLogic,
    '../../lib/api-errors': { normalizeApiError: (_, message) => ({ message }) }, '../../animal-movements/validation': validation,
    '../../ui/components': ui, '../lots.service': { getLots: request('lots') }, './LotInventory': mod(() => null),
  })
  const props = { farm, revision: 1, organizationId, isCurrentOrganization: org => org === context.org }
  return { Component, calls, pending, context, unmount: h.unmount, render: () => h.render(Component.LotListScope, props), async resolve(data = six) {
    pending.lots.shift().resolve(data); if (!farm) pending.farms.shift().resolve(farms); await tick()
  } }
}
test('loads lots and farms once, publishes together and uses cancellation', async () => {
  const e = scope(); assert.match(text(e.render()), /Cargando lotes/); await e.resolve(); const tree = e.render()
  assert.equal(tree.props.lots.length, 6); assert.equal(tree.props.farms.size, 2)
  e.render(); assert.equal(e.calls.length, 2); assert.ok(e.calls.every(c => c.args[1] instanceof AbortSignal))
})
test('farm scope uses existing farm without another farm request and limits data', async () => {
  const e = scope(farms[0]); e.render(); await e.resolve(); const tree = e.render()
  assert.equal(e.calls.length, 1); assert.equal(tree.props.lots.length, 3); assert.equal(tree.props.farms.size, 1)
  assert.ok(tree.props.lots.every(l => l.farm_id === farms[0].id))
})
for (const data of [{ results: six }, six.map(l => ({ ...l, organization_id: id(999) })), [{ ...six[0], capacity: -1 }]]) test('invalid/foreign tenant responses rejected with retry', async () => {
  const e = scope(); e.render(); await e.resolve(data); const tree = e.render()
  assert.equal(tree.type, ui.ErrorState); assert.ok(action(tree, 'Reintentar'))
})
test('network failure retry cancels previous requests and recovers without writes', async () => {
  const e = scope(); e.render(); e.pending.lots.shift().reject(Error()); e.pending.farms.shift().resolve(farms); await tick()
  action(e.render(), 'Reintentar').props.onClick(); e.render(); assert.equal(e.calls.length, 4)
  assert.ok(e.calls.slice(0, 2).every(c => c.args[1].aborted)); await e.resolve(); assert.equal(e.render().props.lots.length, 6)
})
for (const reason of ['session', 'tenant', 'unmount']) test(`late lots ignored on ${reason}`, async () => {
  const e = scope(); e.render()
  if (reason === 'session') e.context.revision++
  if (reason === 'tenant') e.context.org = id(999)
  if (reason === 'unmount') e.unmount()
  await e.resolve(); assert.equal(e.render().type, ui.LoadingState)
})
test('tenant/session/farm keys isolate scopes including A→B→A', () => {
  const e = scope(); const first = e.Component.default({}).key
  assert.notEqual(e.Component.default({ farm: farms[0] }).key, first)
  e.context.org = id(999); assert.notEqual(e.Component.default({}).key, first)
  e.context.org = organizationId; e.context.revision++; assert.notEqual(e.Component.default({}).key, first)
})
test('main page keeps the existing back route', () => {
  const Page = load('../pages/LotsPage.tsx', { 'react/jsx-runtime': jsx, 'react-router-dom': { Link }, '../lots/components/LotList': mod(() => null) }).default
  assert.ok(nodes(Page()).some(n => n.type === Link && n.props.to === '/farms')); assert.match(text(Page()), /Gestión de lotes/)
})
