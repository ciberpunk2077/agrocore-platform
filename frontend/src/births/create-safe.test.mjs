import assert from 'node:assert/strict'
import test from 'node:test'
import { deferred, tick, text } from '../breeding/test-support.mjs'
import { contextData } from '../breeding/flow-test-support.mjs'
import { env, payload, record, pregnancy, animal, calf, genders, breeding, id, pregnancyPath } from './flow-test-support.mjs'

for (const role of ['OWNER', 'ADMIN', 'VETERINARIAN', 'OPERATOR']) test(`${role} sees CREATE`, async () => {
  const e = env(); await e.ready(); e.context({ currentRole: role }); assert.ok(e.form()); assert.equal(e.form().props.disabled, false)
})
test('VIEWER captured handler cannot prepare or POST after permission change', async () => {
  const e = env(); await e.ready(); const handler = e.form().props.onCreate, before = e.calls.length
  e.render({ canWrite: false }); assert.equal(await handler(payload), false); assert.equal(e.calls.length, before); assert.equal(e.confirmations(), 0)
})
test('cancelled confirmation performs no preparation or POST', async () => {
  const e = env(); await e.ready(); e.confirm(false); const before = e.calls.length
  assert.equal(await e.form().props.onCreate(payload), false); assert.equal(e.calls.length, before)
})
for (const [label, p, result] of [
  ['automatic calf', payload, record],
  ['existing calf preserves permissive contract', { ...payload, calf_id: calf.id, calf_gender_id: null }, { ...record, calf_gender_id: null }],
  ['non-live birth', { ...payload, alive: false }, { ...record, alive: false, calf_id: null }],
  ['Decimal semantic equality and exact notes', { ...payload, birth_weight: '30', notes: '  text  ' }, { ...record, birth_weight: '30.00', notes: '  text  ' }],
]) test(`confirmed ${label}: fresh GETs one POST and Pregnancy invalidation`, async () => {
  const e = env(); await e.ready(); e.prepare({}, p); e.queue('POST', { data: result }); e.sync([result])
  const saved = await e.form().props.onCreate(p); e.render()
  assert.equal(saved, true); assert.equal(e.count('POST'), 1); assert.match(text(e.tree()), /registrado correctamente/)
  assert.equal(e.history().props.history[0].id, result.id); assert.ok(e.changed() >= 1)
  const paths = e.calls.filter(c => !c.method).map(c => c.path)
  for (const path of [pregnancyPath(pregnancy.id), `/api/animals/${animal.id}`, `/api/births/animal/${animal.id}/history`, '/api/common/context', `/api/breeding/${breeding.id}`]) assert.ok(paths.includes(path), path)
  if (p.calf_id) assert.ok(paths.includes(`/api/animals/${p.calf_id}`))
})
for (const [label, changes] of [
  ['FINISHED', { pregnancy: { data: { ...pregnancy, status: 'FINISHED' } } }],
  ['ABORTED', { pregnancy: { data: { ...pregnancy, status: 'ABORTED' } } }],
  ['wrong mother', { pregnancy: { data: { ...pregnancy, animal_id: id(99) } } }],
  ['wrong pregnancy', { pregnancy: { data: { ...pregnancy, id: id(99) } } }],
  ['changed breeding identity', { pregnancy: { data: { ...pregnancy, breeding_id: id(99) } } }],
  ['consumed pregnancy', { history: { data: [record] } }],
  ['inactive mother', { mother: { data: { ...animal, is_active: false } } }],
  ['wrong mother GET', { mother: { data: { ...animal, id: id(99) } } }],
  ['malformed mother', { mother: { data: {} } }],
  ['gender disappeared', { genders: { data: [] } }],
  ['malformed genders', { genders: { data: {} } }],
  ['malformed history', { history: { data: {} } }],
  ['future diagnosis', { pregnancy: { data: { ...pregnancy, diagnosis_date: '2026-10-06' } } }],
  ['future breeding', { breeding: { data: { ...breeding, date: '2026-10-06' } } }],
  ['changed permission', { context: { data: { ...contextData(), can_write: false, role: 'VIEWER' } } }],
  ['changed organization', { context: { data: contextData(id(99)) } }],
  ['missing business time', { context: { data: contextData(undefined, null) } }],
  ['preparation GET error', { pregnancy: { status: 503 } }],
]) test(`fresh preparation ${label} sends no POST`, async () => {
  const e = env(); await e.ready(); e.prepare(changes); if (label === 'missing business time') e.queue('/api/common/context', changes.context); await e.form().props.onCreate(payload); e.render()
  assert.equal(e.count('POST'), 0); assert.doesNotMatch(text(e.tree()), /Resultado incierto/)
})
for (const changes of [{ calf: { data: { ...calf, is_active: false } } }, { calf: { data: { ...calf, mother_id: id(99) } } }, { calf: { data: {} } }]) test(`existing calf fresh validation ${JSON.stringify(changes)} no POST`, async () => {
  const e = env(), p = { ...payload, calf_id: calf.id, calf_gender_id: null }; await e.ready(); e.prepare(changes, p)
  await e.form().props.onCreate(p); assert.equal(e.count('POST'), 0)
})
for (const change of ['session', 'organization', 'animal', 'permission']) test(`${change} during preparation prevents POST`, async () => {
  const e = env(), d = deferred(); await e.ready(); e.prepare({ pregnancy: () => d.promise })
  const work = e.form().props.onCreate(payload)
  await tick()
  if (change === 'session') e.changeSession()
  else if (change === 'organization') e.context({ currentOrganization: { id: id(99) } })
  else if (change === 'permission') e.render({ canWrite: false })
  else e.h.unmount()
  d.resolve({ data: pregnancy }); await work; assert.equal(e.count('POST'), 0)
})
test('two synchronous submits produce one POST and freeze caller payload during preparation', async () => {
  const e = env(), d = deferred(); await e.ready(); e.prepare({ pregnancy: () => d.promise }); e.queue('POST', { data: record }); e.sync()
  const p = { ...payload }, handler = e.form().props.onCreate, first = handler(p), second = handler(p)
  p.pregnancy_id = id(99); p.notes = 'changed'; p.birth_weight = '99'; d.resolve({ data: pregnancy })
  await Promise.all([first, second]); assert.equal(e.count('POST'), 1)
  assert.deepEqual(JSON.parse(e.calls.find(c => c.method === 'POST').body), payload)
})
for (const change of [{ mother_id: id(99) }, { pregnancy_id: 'bad' }, { birth_weight: '0' }, { birth_weight: '-1' }, { birth_weight: '10000' }, { birth_weight: '1.001' }, { birth_date: '2026-02-30' }, { alive: false, calf_id: calf.id }, { calf_gender_id: null }]) test(`invalid request does not prepare ${JSON.stringify(change)}`, async () => {
  const e = env(); await e.ready(); const before = e.calls.length
  assert.equal(await e.form().props.onCreate({ ...payload, ...change }), false); assert.equal(e.calls.length, before)
})
test('READ persists when CREATE preparation fails', async () => {
  const e = env(); await e.ready({}, [{ ...record, pregnancy_id: id(199) }]); e.prepare({ pregnancy: { status: 404 } })
  await e.form().props.onCreate(payload); e.render(); assert.equal(e.history().props.history.length, 1)
})

test('existing calf accepts different sex weight date father species breed with only current relation rules', async () => {
  const e = env(), p = { ...payload, calf_id: calf.id, calf_gender_id: null }
  await e.ready(); e.prepare({ calf: { data: { ...calf, gender_id: genders[1].id, birth_weight: '99.00', birth_date: '2020-01-01', father_id: id(900), species_id: id(901), breed_id: id(902), mother_id: null } } }, p)
  e.queue('POST', { data: { ...record, calf_gender_id: null } }); e.sync([{ ...record, calf_gender_id: null }])
  assert.equal(await e.form().props.onCreate(p), true); assert.equal(e.count('POST'), 1)
})
test('self-as-calf rejected without writing', async () => {
  const e = env(), p = { ...payload, calf_id: animal.id, calf_gender_id: null }
  await e.ready(); e.prepare({ calf: { data: animal } }, p); await e.form().props.onCreate(p); assert.equal(e.count('POST'), 0)
})

test('expired fresh temporal lease is refreshed once more and never permits POST without a valid replacement', async () => {
  const e = env(); await e.ready(); e.prepare({ context: { data: contextData(undefined, null) } })
  e.queue('/api/common/context', { data: contextData(undefined, null) })
  await e.form().props.onCreate(payload); assert.equal(e.count('POST'), 0)
  assert.equal(e.calls.filter(c => c.path === '/api/common/context').length, 2)
})
