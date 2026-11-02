import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'
import { animalId, vaccinationId, record, mod, tick, load, harness, nodes, button, deferred } from './test-support.mjs'

export function detailComponents(hooks = harness(), getVaccination = async () => record) {
  return load('./components/VaccinationPreparation.tsx', {
    react: hooks.react, 'react/jsx-runtime': jsx,
    '../../auth/WriteOnly': mod(() => null), '../../auth/session': { getSession: () => ({ access: 'test' }), getSessionRevision: () => 1 },
    '../vaccinations.service': { getVaccination }, '../../lib/api': { ApiError: class extends Error {} },
    '../../lib/api-errors': {}, './VaccinationEditForm': mod(() => null),
  })
}

test('detail presents actual dates, dose, status and optional fields without invented units', () => {
  const { VaccinationDetail } = detailComponents()
  const data = { ...record, vaccine_name: 'Vacuna de nombre largo '.repeat(12), dose: '0.50', batch: 'Lote A', veterinarian: 'Profesional', notes: 'Primera línea\nSegunda línea' }
  let closed = 0
  const tree = VaccinationDetail({ record: data, onClose: () => { closed++ } })
  const html = renderToStaticMarkup(tree)
  for (const value of [data.vaccine_name, data.dose, data.batch, data.veterinarian, data.notes, '01/01/2026', 'Sin datos', 'Estado del registro: Activa']) assert.ok(html.includes(value), value)
  assert.doesNotMatch(html, /0.50 ml|Guardar|Editar|Eliminar|<form/)
  button(tree, 'Volver al historial').props.onClick()
  assert.equal(closed, 1)
  let focused = false
  nodes(tree).find(n => n.type === 'h3').props.ref({ focus() { focused = true } })
  assert.equal(focused, true)
})

test('missing fields use Sin datos; inactive is the actual record status', () => {
  const { VaccinationDetail } = detailComponents()
  const html = renderToStaticMarkup(VaccinationDetail({ record: { ...record, is_active: false, batch: '  ', veterinarian: null, notes: '' }, onClose() {} }))
  assert.equal((html.match(/Sin datos/g) ?? []).length, 4)
  assert.match(html, /Estado del registro: Inactiva/)
  assert.doesNotMatch(html, /Estado del registro: Activa/)
})

test('detail is a named region with grouped facts and preserves zero and civil dates', () => {
  const { VaccinationDetail } = detailComponents()
  const tree = VaccinationDetail({ record: { ...record, dose: '0', next_application_date: '2026-12-31' }, onClose() {} })
  const heading = nodes(tree).find(n => n.type === 'h3')
  assert.equal(tree.props['aria-labelledby'], heading.props.id)
  assert.equal(nodes(tree).filter(n => n.type === 'h4').length, 2)
  const dates = nodes(tree).filter(n => n.type === 'time').map(n => n.props.dateTime)
  assert.ok(dates.includes('2026-12-31'))
  const html = renderToStaticMarkup(tree)
  assert.match(html, /31\/12\/2026/)
  assert.match(html, /<dd>0<\/dd>/)
  assert.doesNotMatch(html, /Vigente|Vencida|Pendiente|\bml\b|\bmg\b/)
})

test('rerendering the same detail keeps the focus callback stable instead of stealing keyboard focus', () => {
  const h = harness()
  const { VaccinationDetail } = detailComponents(h)
  const props = { record, onClose() {} }
  const first = h.render(VaccinationDetail, props)
  const second = h.render(VaccinationDetail, { ...props, onClose() {} })
  assert.equal(nodes(first).find(n => n.type === 'h3').props.ref, nodes(second).find(n => n.type === 'h3').props.ref)
})

test('selecting a different vaccine remounts the loader; stale data cannot replace the new selection', async () => {
  const first = deferred(), second = deferred(), calls = []
  const h = harness()
  const { default: Preparation } = detailComponents(h, (...args) => { calls.push(args); return calls.length === 1 ? first.promise : second.promise })
  const props = { vaccinationId, animalId, birthDate: null, readOnly: true, onCancel() {} }
  const firstElement = Preparation(props)
  h.render(firstElement.type, firstElement.props)
  h.unmount(); h.slots.length = 0
  const newProps = { ...firstElement.props, vaccinationId: 'second' }
  h.render(firstElement.type, newProps)
  second.resolve({ ...record, id: 'second', vaccine_name: 'Segunda vacuna', next_application_date: '2027-02-01' })
  await tick()
  first.resolve({ ...record, vaccine_name: 'Vacuna anterior' }); await tick()
  const html = renderToStaticMarkup(h.render(firstElement.type, newProps))
  assert.match(html, /Segunda vacuna/); assert.match(html, /01\/02\/2027/)
  assert.doesNotMatch(html, /Vacuna anterior/)
  assert.equal(calls[0][1], animalId); assert.equal(calls[1][1], animalId)
  assert.equal(calls[0][3].aborted, true)
})
