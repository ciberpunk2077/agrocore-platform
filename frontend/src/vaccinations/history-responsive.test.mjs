import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'
import { load, mod, harness, tick, nodes, text } from './test-support.mjs'

export async function historyFixture(count) {
  const hooks = harness()
  const rows = Array.from({ length: count }, (_, i) => ({
    id: `vaccination-${i}`, application_date: `2026-01-${String(i + 1).padStart(2, '0')}`,
    vaccine_name: i % 2 ? 'Vacuna con nombre extenso '.repeat(8) : 'Vacuna',
    dose: '2 ml', next_application_date: i % 2 ? '2026-12-01' : null,
    batch: i % 2 ? 'Lote'.repeat(60) : null,
    veterinarian: i % 2 ? 'Veterinario de prueba' : null,
    notes: i % 2 ? 'Notas de validación\n'.repeat(4) : null,
  }))
  const viewed = []
  const History = load('./components/VaccinationHistory.tsx', {
    react: hooks.react, 'react/jsx-runtime': jsx,
    '../../auth/WriteOnly': mod(() => null),
    '../../auth/session': { getSession: () => ({ access: 'test' }), getSessionRevision: () => 1 },
    '../vaccinations.service': { getAnimalVaccinationHistory: async () => rows },
  }).default
  const props = { animalId: 'test', saved: null, actionsDisabled: false, onLoaded() {}, onView: id => viewed.push(id) }
  hooks.render(History, props)
  await tick()
  const tree = hooks.render(History, props)
  return { tree, rows, viewed, html: renderToStaticMarkup(tree) }
}

for (const count of [1, 2, 3, 4, 5, 8]) {
  test(`vaccination history preserves ${count} records, one details action per card without duplicated detail`, async () => {
    const { tree, rows, viewed, html } = await historyFixture(count)
    const cards = nodes(tree).filter(n => n.type === 'tr' && n.props.role === 'row')
    assert.equal(cards.length, count)
    assert.deepEqual(cards.map(n => n.key), rows.map(r => r.id).reverse())
    const buttons = nodes(tree).filter(n => n.type === 'button' && text(n) === 'Ver detalles')
    assert.equal(buttons.length, count)
    assert.ok(buttons.every(n => text(n) === 'Ver detalles'))
    buttons[0].props.onClick()
    assert.equal(viewed[0], rows.at(-1).id)
    assert.doesNotMatch(html, /<summary|Editar|Eliminar/)
    if (count > 1) {
      assert.ok(html.includes(rows[1].vaccine_name))
      assert.ok(!html.includes(rows[1].batch))
      assert.ok(!html.includes(rows[1].notes))
      assert.match(html, /01\/12\/2026/)
    }
    assert.match(html, /—/)
    assert.equal(rows[0].id, 'vaccination-0')
  })
}
