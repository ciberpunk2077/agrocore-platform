import assert from 'node:assert/strict'
import test from 'node:test'
import { deferred, tick, text, button } from '../breeding/test-support.mjs'
import { env, newProtocol, payload, record, pregnancy, animal, id, historyPath } from './flow-test-support.mjs'

for (const change of [
  { pregnancy_id: id(99) }, { mother_id: id(99) }, { calf_id: null }, { calf_id: 'bad' },
  { calf_gender_id: id(99) }, { birth_date: '2026-10-04' }, { birth_weight: '31' },
  { alive: false }, { dystocia: true }, { notes: 'changed' }, { notes: undefined },
  { birth_weight: 30 }, { birth_date: '2026-02-30' },
]) test(`incompatible POST response becomes uncertain ${JSON.stringify(change)}`, async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', { data: { ...record, ...change } })
  await e.form().props.onCreate(payload); e.render(); assert.match(text(e.tree()), /Resultado incierto/)
  const before = e.calls.length; assert.equal(await e.form().props.onCreate(payload), false); assert.equal(e.calls.length, before); assert.equal(e.count('POST'), 1)
})
for (const [label, response] of [
  ['null', { data: null }], ['malformed', { data: {} }], ['invalid JSON', { invalidJSON: true }],
  ['201', { status: 201, data: record }], ['500', { status: 500 }], ['503', { status: 503 }],
  ['network', new TypeError('network')], ['timeout', new Error('timeout')], ['aborted transport', Object.assign(new Error('aborted'), { name: 'AbortError' })],
]) test(`ambiguous ${label} blocks writes and never automatically retries`, async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', response)
  await e.form().props.onCreate(payload); e.render(); assert.match(text(e.tree()), /Resultado incierto/); assert.equal(e.count('POST'), 1)
})
for (const [p, result] of [
  [{ ...payload, calf_id: record.calf_id, calf_gender_id: null }, { ...record, calf_id: id(199), calf_gender_id: null }],
  [{ ...payload, alive: false }, { ...record, alive: false }],
]) test(`wrong existing/non-live calf semantics uncertain ${JSON.stringify(p)}`, async () => {
  const e = env(); await e.ready(); e.prepare({}, p); e.queue('POST', { data: result })
  await e.form().props.onCreate(p); e.render(); assert.match(text(e.tree()), /Resultado incierto/)
})
for (const status of [400, 403, 404, 422]) test(`deterministic ${status} rejects and syncs GET only`, async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', { status, data: { detail: 'rejected' } }); e.sync([], [pregnancy])
  await e.form().props.onCreate(payload); e.render(); assert.doesNotMatch(text(e.tree()), /Resultado incierto/)
  assert.match(text(e.tree()), /rejected/); assert.equal(e.count('POST'), 1); assert.equal(e.form().props.disabled, false)
})
test('401 invalidates session and cannot publish or retry', async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', { status: 401 })
  await e.form().props.onCreate(payload); const before = e.calls.length
  assert.equal(await e.form().props.onCreate(payload), false); assert.equal(e.calls.length, before)
})
for (const [rows, pregnancies, expected] of [
  [[record], [{ ...pregnancy, status: 'FINISHED' }], /compatible.*autoría/],
  [[{ ...record, birth_weight: '99' }], [{ ...pregnancy, status: 'FINISHED' }], /datos diferentes/],
  [[], [{ ...pregnancy, status: 'FINISHED' }], /FINISHED/],
  [[], [{ ...pregnancy, status: 'ABORTED' }], /ABORTED/],
  [[], [pregnancy], /ACTIVE/],
]) test(`uncertain GET recovery ${JSON.stringify(rows)} ${pregnancies[0].status} retains lock`, async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', new Error('network')); await e.form().props.onCreate(payload); e.render()
  e.sync(rows, pregnancies); button(e.tree(), 'Recuperar lecturas').props.onClick(); await tick(); e.render()
  assert.match(text(e.tree()), expected); assert.match(text(e.tree()), /Resultado incierto/); assert.equal(e.count('POST'), 1)
  assert.equal(await e.form()?.props.onCreate(payload), e.form() ? false : undefined)
})
for (const failure of ['history', 'pregnancy', 'animals']) test(`confirmed + ${failure} sync failure preserves success with GET recovery`, async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', { data: record })
  if (failure === 'history') e.queue(historyPath(animal.id), { status: 503 })
  else {
    e.queue(historyPath(animal.id), { data: [record] })
    e.queue(`/api/pregnancies/animal/${animal.id}/history`, failure === 'pregnancy' ? { status: 503 } : { data: [{ ...pregnancy, status: 'FINISHED' }] })
    e.queue('/api/animals/', failure === 'animals' ? { status: 503 } : { data: [animal] })
  }
  await e.form().props.onCreate(payload); e.render(); assert.match(text(e.tree()), /registrado correctamente/)
  assert.doesNotMatch(text(e.tree()), /Resultado incierto/); assert.ok(button(e.tree(), 'Recuperar lecturas')); assert.equal(e.count('POST'), 1)
  e.sync(); button(e.tree(), 'Recuperar lecturas').props.onClick(); await tick(); e.render()
  assert.equal(e.count('POST'), 1); assert.equal(e.history().props.history.length, 1)
})
for (const change of ['session', 'organization', 'A→B', 'A→B→A']) test(`pending POST ${change} ignores old response and retains unresolved attempt`, async () => {
  const e = env(), d = deferred(); await e.ready(); e.prepare(); e.queue('POST', () => d.promise)
  const work = e.form().props.onCreate(payload); await tick(); assert.equal(e.count('POST'), 1)
  if (change === 'session') e.changeSession()
  else if (change === 'organization') e.context({ currentOrganization: { id: id(99) } })
  else e.h.unmount()
  d.resolve({ data: record }); await work; e.render(); assert.doesNotMatch(text(e.tree()), /registrado correctamente/)
  if (change.startsWith('A')) {
    const next = env(e.protocol); await next.ready(change === 'A→B' ? { animal: { ...animal, id: id(99) } } : {})
    if (change === 'A→B→A') { assert.match(text(next.tree()), /Resultado incierto/); assert.equal(await next.form().props.onCreate(payload), false) }
    else assert.doesNotMatch(text(next.tree()), /Resultado incierto/)
    assert.equal(next.count('POST'), 0)
  }
})
test('A→B→A preparing can safely release an unsent attempt', async () => {
  const e = env(), d = deferred(); await e.ready(); e.prepare({ pregnancy: () => d.promise })
  const work = e.form().props.onCreate(payload); e.h.unmount(); d.resolve({ data: pregnancy }); await work
  const next = env(e.protocol); await next.ready(); assert.equal(next.form().props.disabled, false); assert.equal(e.count('POST'), 0)
})
test('F5 loses memory and reconstructs only by GET with no automatic POST', async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', new Error('network')); await e.form().props.onCreate(payload); e.h.unmount()
  const next = env(newProtocol()); await next.ready({}, [record]); assert.equal(next.count('POST'), 0); assert.equal(next.history().props.history.length, 1)
})
test('uncertain cannot start an incompatible Pregnancy attempt in same mother scope', async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', new Error('network')); await e.form().props.onCreate(payload)
  assert.equal(await e.form().props.onCreate({ ...payload, pregnancy_id: id(199) }), false); assert.equal(e.count('POST'), 1)
})
