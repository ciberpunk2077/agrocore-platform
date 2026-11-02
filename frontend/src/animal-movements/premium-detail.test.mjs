import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { load, harness, tick, text, nodes, button } from './test-support.mjs'
import { detailImports } from '../reproduction/test-support.mjs'
import { env, record, animal, animalId, organizationId, types, farms, lots, id } from './flow-test-support.mjs'
async function ready(overrides = {}, catalogs = {}, globals = {}) {
  const e = env(), h = harness(), closed = []
  const component = load('./components/AnimalMovementDetail.tsx', { ...detailImports, react: h.react, 'react/jsx-runtime': jsx,
    '../../auth/session': e.session, '../../lib/api': e.api, '../../lib/api-errors': e.errors, '../animal-movements.service': e.service }, globals).default
  const props = { movementId: record.id, animalId, organizationId, revision: 1, types, farms, lots, animal, onClose: () => closed.push(true), ...catalogs }
  const render = () => h.render(component, props)
  e.queue(`/api/animal-movements/${record.id}`, { data: { ...record, ...overrides } })
  render(); await tick()
  return { tree: render(), e, closed, render, props }
}
for (const type of types) test(`premium detail preserves actual movement type ${type.code}`, async () => {
  const d = await ready({ movement_type_id: type.id })
  assert.match(text(d.tree), new RegExp(type.name))
  assert.match(text(d.tree), /Origen.*Farm 20.*Lot 20.*Destino.*Farm 21.*Lot 21/)
  assert.equal(nodes(d.tree).filter(n => n.props?.id === 'repro-panel-movement').length, 1)
  assert.equal(d.e.count('GET'), 1); assert.equal(d.e.count('POST'), 0)
})
test('missing locations, reason and notes remain explicit without invented data', async () => {
  const d = await ready({ origin_farm_id: null, origin_lot_id: null, destination_farm_id: null, destination_lot_id: null, reason: null, notes: null, origin_status_id: null })
  assert.match(text(d.tree), /Sin datos/); assert.match(text(d.tree), /Sin snapshot/)
  assert.doesNotMatch(text(d.tree), /Farm 20|Lot 20/)
})
test('unresolved relationships retain UUID only inside technical disclosure', async () => {
  const d = await ready({ origin_status_id: id(99) }, { types: [], farms: [], lots: [] })
  const disclosure = nodes(d.tree).find(n => n.type === 'details')
  assert.ok(text(disclosure).includes(id(99))); assert.ok(text(disclosure).includes(record.origin_farm_id))
  const main = nodes(d.tree).filter(n => n.props?.className === 'movement-detail__location')
  assert.ok(main.every(n => !text(n).includes(record.origin_farm_id)))
  assert.match(text(d.tree), /Información no disponible/)
})
test('known snapshot label, semantic dates, keyboard close and explicit back button', async () => {
  const d = await ready()
  assert.match(text(d.tree), /ACTIVE/)
  assert.ok(nodes(d.tree).some(n => n.type === 'time' && n.props.dateTime === record.date))
  d.tree.props.onKeyDown({ key: 'Escape', stopPropagation() {} }); assert.equal(d.closed.length, 1)
  button(d.tree, 'Volver al historial').props.onClick(); assert.equal(d.closed.length, 2)
})
test('selection changes load another record without adding writes', async () => {
  const d = await ready()
  d.props.movementId = id(98)
  d.e.queue(`/api/animal-movements/${id(98)}`, { data: { ...record, id: id(98), reason: 'Segundo movimiento' } })
  d.render(); await tick(); assert.match(text(d.render()), /Segundo movimiento/)
  assert.equal(d.e.count('GET'), 2); assert.equal(d.e.count('PUT'), 0)
})

test('selected detail precedes history, changes selection without duplication, and closes independently', async () => {
  const e = env()
  await e.ready(undefined, [record, { ...record, id: id(98) }])
  assert.equal(e.detail(), undefined)
  for (const selected of [record.id, id(98)]) {
    e.history().props.onDetail(selected)
    const tree = e.render(), children = tree.props.children.flat().filter(Boolean)
    assert.equal(children[0].type, 'h2')
    assert.equal(children[1].type, e.Detail)
    assert.equal(e.detail().props.movementId, selected)
    assert.ok(children.indexOf(e.detail()) < children.indexOf(e.history()))
    assert.equal(nodes(tree).filter(n => n.type === e.Detail).length, 1)
    assert.equal(e.detail().props.animalId, animalId)
    assert.equal(e.detail().props.organizationId, organizationId)
  }
  e.detail().props.onClose(); e.render()
  assert.equal(e.detail(), undefined); assert.ok(e.history())
  assert.equal(e.count('POST') + e.count('PUT') + e.count('DELETE'), 0)
})

for (const reduced of [true, false]) test(`heading receives focus and scroll respects reduced motion=${reduced}`, async () => {
  const calls = []
  const d = await ready({}, {}, { window: { matchMedia: query => {
    assert.equal(query, '(prefers-reduced-motion: reduce)'); return { matches: reduced }
  } } })
  const heading = nodes(d.tree).find(n => n.props?.id === 'repro-title-movement')
  const node = { focus: options => calls.push(['focus', options]), scrollIntoView: options => calls.push(['scroll', options]) }
  heading.props.ref(node)
  assert.equal(calls[0][0], 'focus'); assert.equal(calls[0][1].preventScroll, true)
  assert.equal(calls[1][0], 'scroll'); assert.equal(calls[1][1].behavior, reduced ? 'instant' : 'smooth')
  assert.equal(calls[1][1].block, 'start')
  assert.equal(nodes(d.render()).find(n => n.props?.id === 'repro-title-movement').props.ref, heading.props.ref)
  heading.props.ref(null); assert.equal(calls.length, 2)
})
