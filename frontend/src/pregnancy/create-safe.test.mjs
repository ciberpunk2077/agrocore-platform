import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { load, harness, tick, deferred, text, button, find, mod } from '../breeding/test-support.mjs'
import { id } from '../breeding/flow-test-support.mjs'
import { env, newProtocol, validation, payload, record, animal, breeding, genders, snapshot, organizationId, historyPath, breedingPath, animalPath } from './flow-test-support.mjs'

test('runtime validates every required field, exact civil dates, statuses, UUIDs and animal identity', () => {
  assert.equal(validation.isPregnancy(record, animal.id), true)
  for (const field of Object.keys(record)) assert.equal(validation.isPregnancy({ ...record, [field]: 42 }, animal.id), false, field)
  for (const change of [{ id: 'bad' }, { breeding_id: 'bad' }, { diagnosis_date: '2026-02-30' }, { expected_birth: '0000-01-01' }, { animal_id: id(99) }, { status: 'UNKNOWN' }]) {
    assert.equal(validation.isPregnancy({ ...record, ...change }, animal.id), false)
  }
  for (const status of ['ACTIVE', 'FINISHED', 'ABORTED']) assert.equal(validation.isPregnancy({ ...record, status, confirmed: false, notes: 'historical' }, animal.id), true)
  assert.equal(validation.isHistory([record, record], animal.id), false)
})
for (const rows of [[], [record], [{ ...record, status: 'FINISHED', diagnosis_date: '2099-01-01', expected_birth: '2020-01-01' }]]) {
  test(`READ preserves valid history/order without inventing business rules ${JSON.stringify(rows)}`, async () => {
    const e = env(); await e.ready({ canWrite: false, businessTimeLease: null }, rows)
    assert.equal(e.history().props.history.length, rows.length); assert.equal(e.form(), undefined); assert.equal(e.calls.length, 1)
  })
}
for (const data of [null, {}, [{ ...record, animal_id: id(99) }], [{ ...record, notes: undefined }]]) {
  test(`invalid HISTORY recoverable and never incorporated ${JSON.stringify(data)}`, async () => {
    const e = env(); e.queue(historyPath(animal.id), { data }); e.render({ canWrite: false }); await tick(); e.render()
    assert.equal(e.history(), undefined); assert.match(text(e.tree()), /No fue posible cargar el historial/)
    e.queue(historyPath(animal.id), { data: [] }); button(e.tree(), 'Actualizar historial').props.onClick(); e.render(); await tick(); e.render()
    assert.ok(e.history())
  })
}
test('CREATE option failures do not hide valid HISTORY', async () => {
  const e = env(); e.queue(historyPath(animal.id), { data: [record] }); e.queue(breedingPath(animal.id), { data: [breeding] })
  e.queue('/api/catalogs/breeding-types', { status: 503 }); e.queue('/api/animals/', { data: [animal] })
  e.queue('/api/catalogs/genders', { data: genders }); e.queue(animalPath(animal.id), { data: animal })
  e.render(); await tick(); e.render(); assert.equal(e.history().props.history.length, 1); assert.match(text(e.tree()), /API request|opciones/)
})
test('VIEWER refresh is GET-only and independent of business_time', async () => {
  const e = env(); await e.ready({ canWrite: false, businessTimeLease: null })
  e.sync(); button(e.tree(), 'Actualizar eventos disponibles').props.onClick(); await tick(); e.render()
  assert.equal(e.history().props.history.length, 1); assert.equal(e.count('POST'), 0); assert.equal(e.count('GET'), 3)
})
test('VIEWER has READ and no CREATE handler even with fresh business_time', async () => {
  const viewer = env(); await viewer.ready({ canWrite: false }); assert.equal(viewer.form(), undefined)
  assert.equal(viewer.count('POST'), 0); assert.ok(viewer.history())
})
test('role change remount invalidates a captured writer handler before VIEWER can invoke it', async () => {
  const e = env(); await e.ready(); const old = e.form().props.onCreate
  e.h.unmount()
  const viewer = env(e.protocol); await viewer.ready({ canWrite: false })
  assert.equal(await old(payload), false); assert.equal(e.count('POST'), 0); assert.equal(viewer.count('POST'), 0)
})
for (const role of ['OWNER', 'ADMIN', 'VETERINARIAN', 'OPERATOR']) {
  test(`writer context ${role} exposes CREATE independently from HISTORY`, async () => {
    const e = env(); await e.ready(); e.context({ currentRole: role, canWrite: true })
    assert.ok(e.form()); assert.ok(e.history()); assert.equal(e.form().props.disabled, false)
  })
}
test('business_today is delivered to form max, even when browser UTC day differs', async () => {
  const e = env(); await e.ready(); assert.equal(e.form().props.businessToday, '2026-10-05')
})
for (const change of [{ diagnosis_date: '2026-10-06' }, { diagnosis_date: '2024-12-31' }, { diagnosis_date: '2026-02-30' },
  { expected_birth: '2026-10-05' }, { expected_birth: '2026-10-04' }, { breeding_id: 'bad' }, { animal_id: id(99) }, { confirmed: false }]) {
  test(`invalid input before preparation no POST ${JSON.stringify(change)}`, async () => {
    const e = env(); await e.ready(); const before = e.calls.length
    await assert.rejects(e.form().props.onCreate({ ...payload, ...change })); assert.equal(e.count('POST'), 0); assert.equal(e.calls.length, before)
  })
}
for (const problem of ['missing breeding', 'consumed breeding', 'active pregnancy', 'new breeding date', 'inactive animal', 'male animal']) {
  test(`fresh preparation rejects ${problem}`, async () => {
    const e = env(); await e.ready()
    e.prepare(problem === 'consumed breeding' ? [{ ...record, status: 'ABORTED' }] : problem === 'active pregnancy' ? [{ ...record, breeding_id: id(88) }] : [],
      problem === 'missing breeding' ? [] : [{ ...breeding, date: problem === 'new breeding date' ? '2026-10-06' : breeding.date }],
      { ...animal, ...(problem === 'inactive animal' ? { is_active: false } : problem === 'male animal' ? { gender_id: genders[1].id } : {}) })
    assert.equal(await e.form().props.onCreate(payload), false); e.render(); assert.equal(e.count('POST'), 0); assert.equal(e.protocol.getAttempt(e.protocol.attemptKey(1, organizationId, animal.id)), undefined)
  })
}
test('fresh preparation, normalized frozen payload and double click yield one confirmed POST', async () => {
  const e = env(); await e.ready(); e.prepare(); const d = deferred(), input = { ...payload, notes: '  hello  ' }
  const saved = { ...record, notes: 'hello', status: 'FINISHED' }
  // A later GET may show a completed pregnancy; CREATE itself must return ACTIVE.
  e.queue('POST', () => d.promise); e.sync([saved])
  const create = e.form().props.onCreate, work = create(input); input.notes = 'changed'; await create(input); await tick(); e.render()
  assert.equal(e.count('POST'), 1)
  const attempt = e.protocol.getAttempt(e.protocol.attemptKey(1, organizationId, animal.id))
  assert.equal(Object.isFrozen(attempt.payload), true); assert.equal(attempt.payload.notes, 'hello')
  assert.equal(JSON.parse(e.calls.find(c => c.method === 'POST').body).notes, 'hello')
  d.resolve({ data: { ...saved, status: 'ACTIVE' } }); assert.equal(await work, true); e.render()
  assert.match(text(e.tree()), /guardada correctamente/); await create(payload); assert.equal(e.count('POST'), 1)
})
for (const field of Object.keys(payload)) {
  test(`response semantic mismatch ${field} is uncertain`, async () => {
    const e = env(); await e.ready(); e.prepare()
    const different = { animal_id: id(99), breeding_id: id(98), diagnosis_date: '2026-10-04', expected_birth: '2027-02-01', confirmed: false, notes: 'other' }
    e.queue('POST', { data: { ...record, [field]: different[field] } })
    await e.form().props.onCreate(payload); e.render(); assert.match(text(e.tree()), /Resultado incierto/); assert.doesNotMatch(text(e.tree()), /guardada correctamente/)
  })
}
for (const response of [{ data: {} }, { data: null }, { data: { ...record, status: 'ABORTED' } }, { status: 202, data: record },
  { status: 204, data: null }, { status: 500 }, { status: 503 }, new TypeError('network'), Object.assign(new TypeError('timeout'), { name: 'AbortError' })]) {
  test(`ambiguous response ${JSON.stringify(response)} blocks retries; GET match cannot prove authorship`, async () => {
    const e = env(); await e.ready(); e.prepare(); e.queue('POST', response)
    const create = e.form().props.onCreate; await create(payload); e.render(); await create(payload)
    assert.equal(e.count('POST'), 1); assert.match(text(e.tree()), /Resultado incierto/)
    e.sync(); const before = e.count('GET'); button(e.tree(), 'Recuperar lecturas').props.onClick(); button(e.tree(), 'Recuperar lecturas').props.onClick()
    await tick(); e.render(); assert.equal(e.count('GET') - before, 2); assert.equal(e.count('POST'), 1)
    assert.match(text(e.tree()), /compatible.*no demuestra autoría/); assert.equal(e.history().props.disabled, true)
  })
}
test('confirmed write survives refresh failure; recovery only GET and stale callback cannot resend', async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', { data: record }); e.queue(historyPath(animal.id), { status: 503 })
  const old = e.form().props.onCreate; await old(payload); e.render(); assert.match(text(e.tree()), /guardada correctamente/)
  assert.equal(e.protocol.getAttempt(e.protocol.attemptKey(1, organizationId, animal.id)).phase, 'confirmed')
  e.sync(); button(e.tree(), 'Recuperar lecturas').props.onClick(); await tick(); e.render(); await old(payload); assert.equal(e.count('POST'), 1)
})
for (const status of [400, 403, 404, 422]) {
  test(`known rejection ${status} releases attempt and GET refresh never repeats POST`, async () => {
    const e = env(); await e.ready(); e.prepare(); e.queue('POST', { status, data: { detail: 'Evento ya reservado' } }); e.sync([], [])
    await e.form().props.onCreate(payload); e.render(); assert.match(text(e.tree()), /Evento ya reservado/)
    assert.equal(e.protocol.getAttempt(e.protocol.attemptKey(1, organizationId, animal.id)), undefined); assert.equal(e.count('POST'), 1)
  })
}
for (const change of ['logout', 'login', 'organization', 'unmount']) {
  test(`scope change ${change} during preparation prevents POST`, async () => {
    const e = env(); await e.ready(); const d = deferred(); e.prepare(); e.queue('/api/common/context', () => d.promise)
    const work = e.form().props.onCreate(payload); await tick()
    if (change === 'logout' || change === 'login') e.changeSession(change === 'logout')
    else if (change === 'organization') e.context({ currentOrganization: { id: id(999) } })
    else e.h.unmount()
    // Context response also changes tenant when appropriate.
    const data = { ...((await import('../breeding/flow-test-support.mjs')).contextData()), ...(change === 'organization' ? { organization: { id: id(999), name: 'Other', code: 'OTHER' } } : {}) }
    d.resolve({ data }); await work; assert.equal(e.count('POST'), 0)
  })
}
test('expired snapshot during preparation refreshes again and revalidates new business_today', async () => {
  const e = env(); await e.ready(); e.prepare()
  const { contextData } = await import('../breeding/flow-test-support.mjs')
  e.queue('/api/common/context', { data: contextData(organizationId, { ...snapshot, valid_until: snapshot.server_now }) },
    { data: contextData(organizationId, { ...snapshot, business_today: '2026-10-04', server_now: '2026-10-05T00:30:00Z', valid_until: '2026-10-05T00:31:00Z' }) })
  await e.form().props.onCreate(payload); assert.equal(e.count('POST'), 0); assert.equal(e.calls.filter(c => c.path === '/api/common/context').length, 2)
})
test('expired snapshot refresh succeeds and permits only revalidated POST', async () => {
  const e = env(); await e.ready(); e.prepare(); const { contextData } = await import('../breeding/flow-test-support.mjs')
  e.queue('/api/common/context', { data: contextData(organizationId, null) }, { data: contextData() }); e.queue('POST', { data: record }); e.sync()
  await e.form().props.onCreate(payload); assert.equal(e.count('POST'), 1); assert.equal(e.calls.filter(c => c.path === '/api/common/context').length, 2)
})
test('business_time refresh failure prevents POST but HISTORY remains visible', async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('/api/common/context', { status: 503 })
  await e.form().props.onCreate(payload); e.render(); assert.equal(e.count('POST'), 0); assert.ok(e.history())
})
test('missing/expired business_time blocks CREATE without blocking READ', async () => {
  const e = env(); await e.ready({ businessTimeLease: null }); assert.equal(e.form().props.disabled, true)
  await e.form().props.onCreate(payload); assert.equal(e.count('POST'), 0); assert.ok(e.history())
})
test('lease expiration while page stays open disables max/submit until refreshed tenant snapshot', async () => {
  const e = env(); await e.ready()
  const expired = { ...e.props.businessTimeLease, remainingMs: 0 }
  e.render({ businessTimeLease: expired }); assert.equal(e.form().props.businessToday, null)
  await e.form().props.onCreate(payload); assert.equal(e.count('POST'), 0); assert.ok(e.history())
  const next = { ...snapshot, business_today: '2026-10-06', server_now: '2026-10-06T06:00:00Z', valid_until: '2026-10-06T06:01:00Z' }
  const lease = e.time.createBusinessTimeLease(next, performance.now(), Date.now())
  e.render({ businessTimeLease: lease }); assert.equal(e.form().props.businessToday, '2026-10-06')
})
test('failed Breeding recovery still updates HISTORY and blocks stale CREATE callback', async () => {
  const e = env(); await e.ready(); const old = e.form().props.onCreate
  e.queue(historyPath(animal.id), { data: [] }); e.queue(breedingPath(animal.id), { status: 503 })
  button(e.tree(), 'Actualizar eventos disponibles').props.onClick(); await tick(); e.render()
  assert.ok(e.history()); assert.equal(await old(payload), false); assert.equal(e.count('POST'), 0)
})
for (const change of ['animal A to B', 'animal A to B to A', 'logout/login', 'organization']) {
  test(`late HISTORY ignored across ${change}, even if transport ignores abort`, async () => {
    const e = env(), d = deferred(); e.queue(historyPath(animal.id), () => d.promise); e.render({ canWrite: false })
    if (change === 'logout/login') e.changeSession()
    else if (change === 'organization') e.context({ currentOrganization: { id: id(999) } })
    else e.h.unmount()
    d.resolve({ data: [record] }); await tick(); e.render(); assert.equal(e.history(), undefined)
    const next = env(); await next.ready({ canWrite: false, animal: change === 'animal A to B' ? { ...animal, id: id(88) } : animal })
    assert.equal(next.history().props.history.length, 0)
  })
}
test('outer key captures session revision, Organization, animal and permissions', async () => {
  const e = env(); assert.match(e.outer().key, new RegExp(`1:${organizationId}:${animal.id}:true`))
  e.changeSession(); e.context({ currentOrganization: { id: id(999) }, canWrite: false })
  assert.match(e.outer().key, new RegExp(`2:${id(999)}:${animal.id}:false`))
})
test('A to B to A preserves pending/uncertain attempt; stale POST cannot mutate new A', async () => {
  const protocol = newProtocol(), e = env(protocol); await e.ready(); e.prepare(); const d = deferred(); e.queue('POST', () => d.promise)
  const work = e.form().props.onCreate(payload); await tick(); e.h.unmount()
  const b = env(protocol); await b.ready({ animal: { ...animal, id: id(88) } }); b.h.unmount()
  const again = env(protocol); await again.ready(); assert.equal(again.form().props.disabled, true)
  await again.form().props.onCreate(payload); assert.equal(again.count('POST'), 0)
  d.resolve({ data: record }); await work; again.render(); assert.match(text(again.tree()), /Resultado incierto/); assert.doesNotMatch(text(again.tree()), /guardada correctamente/)
})
test('F5/new registry loses local attempt but rebuilds HISTORY without automatic POST', async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', { status: 503 }); await e.form().props.onCreate(payload); e.h.unmount()
  const reload = env(newProtocol()); await reload.ready({}, [record]); assert.equal(reload.history().props.history.length, 1); assert.equal(reload.count('POST'), 0)
})
test('ABORT integration preserves endpoint and historical record after fresh preparation', async () => {
  const e = env(); await e.ready({}, [record]); e.queue(`/api/pregnancies/${record.id}`, { data: record }); e.queue('POST', { data: { ...record, status: 'ABORTED' } }); e.sync([{ ...record, status: 'ABORTED' }])
  await e.history().props.onAbort(record); e.render(); assert.equal(e.count('POST'), 1)
  assert.equal(e.calls.find(c => c.method === 'POST').path, `/api/pregnancies/${record.id}/abort`)
  assert.match(text(e.tree()), /aborto ya fue registrado/)
})
test('real form max and submit use tenant date; no browser Date authority', async () => {
  const h = harness(), errors = load('../lib/api-errors.ts', { './api': {} }), calls = []
  const component = load('../pregnancy/components/PregnancyForm.tsx', { react: h.react, 'react/jsx-runtime': jsx,
    '../../components/FieldError': mod(() => null), '../../lib/api-errors': errors, '../validation': validation },
    { Date: class { constructor() { throw new Error('Browser date must not decide business day') } } })
  const props = { animal, events: [breeding], eventLabels: new Map(), disabled: false, businessToday: '2026-10-05', fieldErrors: {}, onClearErrors() {}, onCreate: async p => { calls.push(p); return true } }
  let tree = h.render(component.default, props)
  const { nodes } = await import('../breeding/test-support.mjs')
  const control = name => nodes(tree).find(n => n.props?.id === name)
  assert.equal(control('pregnancy-diagnosis').props.max, '2026-10-05')
  control('pregnancy-breeding').props.onChange({ target: { value: breeding.id } }); tree = h.render(component.default, props)
  control('pregnancy-diagnosis').props.onChange({ target: { value: '2026-10-06' } }); control('pregnancy-expected-birth').props.onChange({ target: { value: '2027-01-01' } })
  tree = h.render(component.default, props); await find(tree, 'form').props.onSubmit({ preventDefault() {} }); assert.equal(calls.length, 0)
  control('pregnancy-diagnosis').props.onChange({ target: { value: '2026-10-05' } }); tree = h.render(component.default, props)
  await find(tree, 'form').props.onSubmit({ preventDefault() {} }); assert.equal(calls.length, 1)
})

test('Birth invalidation version refetches Pregnancy without remounting or issuing POST', async () => {
  const e = env(); await e.ready({}, [record]); e.options(); e.queue(historyPath(animal.id), { data: [{ ...record, status: 'FINISHED' }] })
  e.render({ refreshVersion: 1 }); await tick(); e.render()
  assert.equal(e.history().props.history[0].status, 'FINISHED'); assert.equal(e.count('POST'), 0)
  assert.equal(e.history().props.disabled, false)
})
