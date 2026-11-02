import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'
import { load, harness, nodes, text, tick, mod } from '../animal-movements/test-support.mjs'
import { animal, id } from '../animal-movements/flow-test-support.mjs'

const logic = load('../animals/inventory.ts', {})
const ui = load('../ui/components.tsx', { 'react/jsx-runtime': jsx })
const link = props => jsx.jsx('a', { ...props, href: props.to })
const identity = load('../animals/components/InventoryAnimal.tsx', { 'react/jsx-runtime': jsx, '../../ui/components': ui, '../inventory': logic })
const imports = { 'react/jsx-runtime': jsx, 'react-router-dom': { Link: link }, '../../ui/components': ui, '../inventory': logic, './InventoryAnimal': identity }
const Table = load('../animals/components/AnimalTable.tsx', imports).default
const Cards = load('../animals/components/AnimalCards.tsx', imports).default
const records = Array.from({ length: 55 }, (_, i) => ({ ...animal, id: id(100+i), name: `Vaca ${i}`, internal_id: `AG-${i}`, official_tag: `OF-${i}`, electronic_tag: `EL-${i}` }))
const blank = () => ({ ...logic.emptyFilters })
const control = (tree, id) => nodes(tree).find(n => n.type === ui.Field && n.props.id === id).props.children({ id })
const action = (tree, label) => nodes(tree).find(n => n.type === ui.Button && text(n) === label)
function inventory(animals = records) {
  const h = harness()
  const Component = load('../animals/components/AnimalInventory.tsx', { ...imports, react: h.react, './AnimalTable': mod(Table), './AnimalCards': mod(Cards) }).default
  return { render: () => h.render(Component, { animals }) }
}
for (const [query, index] of [['vaca 35', 35], ['AG-35', 35], ['OF-35', 35], ['EL-35', 35]]) test(`global list search includes ${query} beyond first page`, () => {
  assert.equal(logic.filterAnimals(records, query, blank())[0].id, records[index].id)
})
test('search ignores accents, surrounding spaces and letter case', () => {
  assert.equal(logic.filterAnimals([{ ...animal, name: 'José' }], ' JOSE ', blank()).length, 1)
})
for (const key of logic.filterKeys) test(`filter ${key} uses exact relationship identity`, () => {
  assert.equal(logic.filterAnimals(records, '', { ...blank(), [key]: records[0][key] }).length, 55)
  assert.equal(logic.filterAnimals(records, '', { ...blank(), [key]: id(999) }).length, 0)
})
test('missing relationships can be filtered, and options are deduplicated by ID', () => {
  const list = [{ ...animal, farm_id: null, farm: null }, animal]
  assert.equal(logic.filterAnimals(list, '', { ...blank(), farm_id: '__missing' }).length, 1)
  assert.equal(logic.filterOptions(records, 'lot_id').length, 1)
  assert.equal(logic.filterOptions(list, 'farm_id').find(([id]) => id === '__missing')[1], 'Sin datos')
})
test('view toggle retains page, search, filters, exact ordered rows and does not fetch', () => {
  const e = inventory(); let tree = e.render()
  control(tree, 'inventory-search').props.onChange({ target: { value: 'Vaca' } }); tree = e.render()
  control(tree, 'inventory-species_id').props.onChange({ target: { value: animal.species_id } }); tree = e.render()
  action(tree, 'Siguiente').props.onClick(); tree = e.render()
  const expected = nodes(tree).find(n => n.type === Table).props.animals.map(a => a.id)
  assert.deepEqual(expected, records.slice(24,48).map(a => a.id))
  action(tree, 'Tarjetas').props.onClick(); tree = e.render()
  assert.deepEqual(nodes(tree).find(n => n.type === Cards).props.animals.map(a => a.id), expected)
  assert.equal(control(tree, 'inventory-search').props.value, 'Vaca')
  assert.equal(control(tree, 'inventory-species_id').props.value, animal.species_id)
  assert.match(text(tree), /Página 2 de 3/)
  assert.equal(action(tree, 'Tarjetas').props['aria-pressed'], true)
  action(tree, 'Tabla').props.onClick(); tree = e.render()
  assert.deepEqual(nodes(tree).find(n => n.type === Table).props.animals.map(a => a.id), expected)
})
test('filter resets page, clear resets all filters, pagination bounds and result counts', () => {
  const e = inventory(); let tree = e.render()
  assert.equal(action(tree, 'Anterior').props.disabled, true)
  action(tree, 'Siguiente').props.onClick(); tree = e.render()
  control(tree, 'inventory-search').props.onChange({ target: { value: 'OF-54' } }); tree = e.render()
  assert.match(text(tree), /Página 1 de 1/); assert.match(text(tree), /1 resultados de 55/)
  assert.equal(action(tree, 'Siguiente').props.disabled, true)
  action(tree, 'Limpiar filtros').props.onClick(); tree = e.render()
  assert.equal(control(tree, 'inventory-search').props.value, '')
  for (const key of logic.filterKeys) assert.equal(control(tree, `inventory-${key}`).props.value, '')
  assert.match(text(tree), /55 resultados/)
})
test('farm changes clear stale lot selection', () => {
  const e = inventory(); let tree = e.render()
  control(tree, 'inventory-lot_id').props.onChange({ target: { value: animal.lot_id } }); tree = e.render()
  control(tree, 'inventory-farm_id').props.onChange({ target: { value: animal.farm_id } }); tree = e.render()
  assert.equal(control(tree, 'inventory-lot_id').props.value, '')
})
test('separate empty inventory and filtered empty states', () => {
  assert.match(text(inventory([]).render()), /No hay animales registrados/)
  const e = inventory(); let tree = e.render()
  control(tree, 'inventory-search').props.onChange({ target: { value: 'missing-animal' } }); tree = e.render()
  assert.match(text(tree), /No hay resultados para los filtros/)
})
for (const Component of [Table, Cards]) test(`${Component.name}: real links, missing data, no write action, semantic readable fields`, () => {
  const markup = renderToStaticMarkup(jsx.jsx(Component, { animals: [{ ...animal, name: null, internal_id: null, official_tag: null, electronic_tag: null, farm: null, lot: null }] }))
  assert.ok(markup.includes(`/animals/${animal.id}`)); assert.match(markup, /Ver expediente/)
  assert.match(markup, /Sin datos/); assert.match(markup, /Sin identificación/)
  assert.doesNotMatch(markup, /Editar|Eliminar|Nuevo animal/)
})
test('invalid paginated envelopes, duplicate IDs and malformed list rows rejected', () => {
  assert.equal(logic.isInventory(records), true)
  for (const value of [{ results: records }, [animal,animal], [{ ...animal, id: 'invalid' }], [{ ...animal, status: {} }]]) assert.equal(logic.isInventory(value), false)
})

function scope({ list = records, summary = { total_animals: 100, active_animals: 55 }, listError = false, summaryError = false } = {}) {
  const h = harness(), calls = [], context = { organization: id(2), revision: 1 }
  const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
  const listResult = deferred(), summaryResult = deferred()
  const Page = load('../pages/AnimalsPage.tsx', {
    react: h.react, 'react/jsx-runtime': jsx, 'react-router-dom': { Link: link }, '../auth/WriteOnly': mod(() => null),
    '../auth/current-context': { useCurrentContext: () => ({ status: 'loaded', canRead: true, currentOrganization: { id: context.organization }, isCurrentOrganization: org => org === context.organization }) },
    '../auth/useSession': { useSession: () => ({ session: {}, revision: context.revision }) },
    '../auth/session': { getSession: () => ({ access: 'fake' }), getSessionRevision: () => context.revision },
    '../animals/animals.service': { getAnimals: (...args) => { calls.push(['list', ...args]); return listResult.promise } },
    '../animals/inventory': logic, '../animals/components/AnimalInventory': mod(() => null),
    '../dashboard/dashboard.service': { getDashboardSummary: (...args) => { calls.push(['summary', ...args]); return summaryResult.promise } }, '../ui/components': ui,
  })
  const props = { revision: 1, organizationId: id(2), isCurrentOrganization: org => org === context.organization }
  return { Page, calls, context, props, unmount: h.unmount, render: () => h.render(Page.InventoryScope, props), async resolve() {
    listError ? listResult.reject(Error()) : listResult.resolve(list)
    summaryError ? summaryResult.reject(Error()) : summaryResult.resolve(summary)
    await tick()
  } }
}
test('summary totals come from dashboard, not visible page or list length; independent GETs run once', async () => {
  const e = scope(); assert.match(text(e.render()), /Cargando animales/); await e.resolve()
  const tree = e.render(); assert.match(text(tree), /100/); assert.match(text(tree), /55/)
  e.render(); assert.equal(e.calls.length, 2); assert.ok(e.calls.every(call => call[2] instanceof AbortSignal))
})
test('failed summary preserves inventory with explicit unavailable indicators', async () => {
  const e = scope({ summaryError: true }); e.render(); await e.resolve()
  assert.match(text(e.render()), /No disponible/); assert.match(text(e.render()), /consultarse de forma independiente/)
})
test('list failure and invalid response show accessible retry', async () => {
  for (const config of [{ listError: true }, { list: { results: records } }]) {
    const e = scope(config); e.render(); await e.resolve()
    const tree = e.render(); assert.ok(nodes(tree).some(n => n.type === ui.ErrorState)); assert.ok(action(tree, 'Reintentar carga'))
  }
})
for (const reason of ['session', 'tenant', 'unmount']) test(`late inventory and summary ignored after ${reason}`, async () => {
  const e = scope(); e.render()
  if (reason === 'session') e.context.revision++
  if (reason === 'tenant') e.context.organization = id(999)
  if (reason === 'unmount') e.unmount()
  await e.resolve(); assert.doesNotMatch(text(e.render()), /100/)
  if (reason === 'unmount') assert.ok(e.calls.every(call => call[2].aborted))
})
test('scope identity includes tenant and session revision; A→B→A cannot reuse state', () => {
  const e = scope(); const first = e.Page.default().key
  e.context.organization = id(999); const other = e.Page.default().key
  e.context.organization = id(2); e.context.revision++; const returned = e.Page.default().key
  assert.notEqual(first, other); assert.notEqual(first, returned)
})
