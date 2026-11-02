import assert from 'node:assert/strict'
import test from 'node:test'
import { deferred, tick, text, button } from '../breeding/test-support.mjs'
import { env, record, animal, pregnancy, breeding, genders, id, historyPath, pregnancyHistory, breedingHistory, animalPath, validation } from './flow-test-support.mjs'

for (const rows of [[], [record], [{ ...record, birth_date: '2099-01-01', birth_weight: '-1', calf_id: null, notes: ' histórico ' }]]) {
  test(`VIEWER reads valid HISTORY without business_time or CREATE options ${JSON.stringify(rows)}`, async () => {
    const e = env(); await e.ready({ canWrite: false, businessTimeLease: null }, rows)
    assert.deepEqual(JSON.parse(JSON.stringify(e.history().props.history)), rows)
    assert.equal(e.form(), undefined); assert.equal(e.calls.length, 1); assert.equal(e.count('POST'), 0)
  })
}
test('runtime validates all Birth fields and rejects duplicate ids and invalid civil dates', () => {
  assert.equal(validation.isBirth(record, animal.id), true)
  for (const field of Object.keys(record)) assert.equal(validation.isBirth({ ...record, [field]: 42 }, animal.id), false, field)
  for (const change of [{ id: 'bad' }, { mother_id: id(90) }, { birth_date: '2026-02-30' }, { birth_date: '0000-01-01' }, { birth_weight: 'NaN' }, { birth_weight: '1e3' }]) assert.equal(validation.isBirth({ ...record, ...change }, animal.id), false)
  assert.equal(validation.isHistory([record, record], animal.id), false)
})
for (const rows of [null, {}, [record, record], [{ ...record, mother_id: id(90) }], [{ ...record, notes: undefined }]]) {
  test(`invalid HISTORY is not incorporated and can recover ${JSON.stringify(rows)}`, async () => {
    const e = env(); e.queue(historyPath(animal.id), { data: rows }); e.render({ canWrite: false }); await tick(); e.render()
    assert.equal(e.history().props.history.length, 0); assert.match(text(e.tree()), /historial|Respuesta inválida/)
    e.queue(historyPath(animal.id), { data: [record] }); button(e.tree(), 'Actualizar historial').props.onClick(); e.render(); await tick(); e.render()
    assert.equal(e.history().props.history.length, 1)
  })
}
for (const path of [pregnancyHistory(animal.id), breedingHistory(animal.id), '/api/animals/', '/api/catalogs/genders', animalPath(animal.id)]) {
  test(`option failure ${path} preserves HISTORY`, async () => {
    const e = env(); e.queue(historyPath(animal.id), { data: [record] })
    const data = { [pregnancyHistory(animal.id)]: [pregnancy], [breedingHistory(animal.id)]: [breeding], '/api/animals/': [animal], '/api/catalogs/genders': genders, [animalPath(animal.id)]: animal }
    for (const [key, value] of Object.entries(data)) e.queue(key, key === path ? { status: 503 } : { data: value })
    e.render(); await tick(); e.render(); assert.equal(e.history().props.history.length, 1); assert.equal(e.form(), undefined)
  })
}
for (const change of ['session', 'organization', 'unmount', 'A→B', 'A→B→A']) {
  test(`late HISTORY ignored after ${change} even if transport ignores abort`, async () => {
    const e = env(), d = deferred(); e.queue(historyPath(animal.id), () => d.promise); e.render({ canWrite: false })
    if (change === 'session') e.changeSession()
    else if (change === 'organization') e.context({ currentOrganization: { id: id(99) } })
    else e.h.unmount()
    d.resolve({ data: [record] }); await tick(); e.render(); assert.equal(e.history().props.history.length, 0)
    if (change.startsWith('A')) {
      const next = env(e.protocol); await next.ready({ canWrite: false, animal: change === 'A→B' ? { ...animal, id: id(99) } : animal })
      assert.equal(next.history().props.history.length, 0)
    }
  })
}
test('wrapper scopes include session revision organization mother and permission', async () => {
  const e = env(); const a = e.outer(); e.changeSession(); const b = e.outer()
  assert.notEqual(a.key, b.key); e.context({ currentOrganization: { id: id(99) } }); assert.notEqual(b.key, e.outer().key)
})
