import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { load, harness, tick, deferred, nodes, text, button, mod, find } from './test-support.mjs'
import { env, id, animalId, organizationId, animal, male, genders, types, payload, record, histPath, animalPath, validation } from './flow-test-support.mjs'

test('runtime contracts validate every field, civil dates, unique IDs, expected Animal and catalogs', () => {
  assert.equal(validation.isBreeding(record, animalId), true)
  for (const field of Object.keys(record)) assert.equal(validation.isBreeding({ ...record, [field]: 42 }, animalId), false, field)
  assert.equal(validation.isBreeding({ ...record, date: '2025-02-30' }, animalId), false)
  assert.equal(validation.isBreeding({ ...record, date: '0000-01-01' }, animalId), false)
  assert.equal(validation.isBreeding({ ...record, technician: null, notes: null }, animalId), true)
  assert.equal(validation.isHistory([], animalId), true)
  assert.equal(validation.isHistory([record], id(99)), false)
  assert.equal(validation.isHistory([record, record], animalId), false)
  assert.equal(validation.isCatalog(types), true)
  assert.equal(validation.isCatalog([{ ...types[0], id: 'bad' }]), false)
  assert.equal(validation.isCatalog([types[0], types[0]]), false)
  assert.equal(validation.isAnimal(animal, animalId), true)
  assert.equal(validation.isAnimal(animal, id(99)), false)
  for (const field of Object.keys(animal)) assert.equal(validation.isAnimal({ ...animal, [field]: 42 }, animalId), false, field)
  assert.equal(validation.isAnimals([animal, animal]), false)
})

test('READ shape checks preserve historical data and ordering without new date/business rules', async () => {
  const e = env(), rows = [{ ...record, date: '2099-01-01', expected_birth: '2020-01-01', technician: '  histórico  ' }, { ...record, id: id(88) }]
  e.queue(histPath(animalId), { data: rows })
  const result = await e.service.getAnimalBreedingHistory(animalId, 'token')
  assert.deepEqual(Array.from(result, r => r.id), rows.map(r => r.id))
  assert.equal(result[0].technician, '  histórico  ')
})

for (const p of [payload, { ...payload, male_id: male.id, expected_birth: '2025-10-01', technician: 'Técnico', notes: 'Notas' },
  { animal_id: animalId, breeding_type_id: types[1].id, date: '2025-01-01' }]) {
  test(`valid CREATE ${JSON.stringify(p)}: fresh preparation, one POST and two GET refresh; no birth_date/type-specific rules`, async () => {
    const e = env(); await e.ready(); e.prepare(p)
    const expected = validation.normalizedPayload(p), saved = { ...expected, id: id(90) }
    e.queue('POST', { data: saved }); e.sync([saved])
    const old = e.form().props.onCreate, before = e.count('GET')
    assert.equal(await old(p), true); e.render()
    assert.equal(e.count('POST'), 1); assert.equal(e.count('GET') - before, p.male_id ? 7 : 6)
    assert.deepEqual(JSON.parse(e.calls.find(c => c.method === 'POST').body), { ...expected })
    assert.match(text(e.tree()), /guardado correctamente/); assert.equal(e.form().props.disabled, false)
    await old(p); assert.equal(e.count('POST'), 1, 'stale form callback cannot resend after confirmed sync')
  })
}

for (const field of Object.keys(payload)) {
  test(`POST response mismatch in ${field} => uncertain; never success`, async () => {
    const e = env(); await e.ready(); e.prepare()
    const value = { animal_id: id(99), breeding_type_id: types[1].id, date: '2025-01-02', male_id: male.id,
      expected_birth: '2025-10-01', technician: null, notes: 'changed' }[field]
    e.queue('POST', { data: { ...record, [field]: value } })
    await e.form().props.onCreate(payload); e.render()
    assert.match(text(e.tree()), /Resultado incierto/); assert.doesNotMatch(text(e.tree()), /guardado correctamente/)
    assert.equal(e.count('POST'), 1); assert.equal(e.form().props.disabled, true)
  })
}

for (const response of [{ status: 202, data: record }, { status: 204, data: null }, { data: {} }, { data: null },
  { data: { ...record, id: 'bad' } }, { status: 503 }, { status: 500 }, new TypeError('network'), Object.assign(new TypeError('timeout'), { name: 'AbortError' })]) {
  test(`ambiguous POST ${JSON.stringify(response)} blocks retries; equivalent history cannot attribute authorship`, async () => {
    const e = env(); await e.ready(); e.prepare(); e.queue('POST', response)
    const create = e.form().props.onCreate
    await create(payload); e.render(); await create(payload); await e.form().props.onCreate(payload)
    assert.equal(e.count('POST'), 1); assert.match(text(e.tree()), /Resultado incierto/)
    const before = e.count('GET'); e.sync([record])
    button(e.tree(), 'Recuperar lecturas').props.onClick(); button(e.tree(), 'Recuperar lecturas').props.onClick(); await tick(); e.render()
    assert.equal(e.count('GET') - before, 2); assert.equal(e.count('POST'), 1)
    assert.match(text(e.tree()), /compatible.*no demuestra autoría/); assert.doesNotMatch(text(e.tree()), /guardado correctamente/)
    assert.equal(e.form().props.disabled, true)
    await e.form().props.onCreate(payload); assert.equal(e.count('POST'), 1)
  })
}

for (const status of [400, 403, 404, 422]) {
  test(`known POST rejection ${status} releases attempt and preserves recoverable field errors`, async () => {
    const e = env(); await e.ready(); e.prepare()
    e.queue('POST', { status, data: { detail: status === 422 ? [{ loc: ['body', 'payload', 'technician'], msg: 'too long' }] : 'Rechazado' } })
    await assert.rejects(e.form().props.onCreate(payload)); e.render()
    assert.equal(e.form().props.disabled, false); assert.doesNotMatch(text(e.tree()), /Resultado incierto/)
    assert.equal(e.protocol.getAttempt(e.protocol.attemptKey(1, organizationId, animalId)), undefined)
    const normalized = e.errors.normalizeApiError(new e.api.ApiError(status, { detail: [{ loc: ['body', 'payload', 'technician'], msg: 'too long' }] }))
    if (status === 422) assert.equal(normalized.fieldErrors.technician[0], 'too long')
  })
}

test('401 invalidates session; late response cannot mutate scope or reissue POST', async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', { status: 401 })
  await e.form().props.onCreate(payload); e.render(); await e.form().props.onCreate(payload)
  assert.equal(e.count('POST'), 1); assert.equal(e.session.getSession(), null)
  assert.doesNotMatch(text(e.tree()), /guardado correctamente/)
  e.h.unmount()
  assert.equal(e.protocol.getAttempt(e.protocol.attemptKey(1, organizationId, animalId)).phase, 'uncertain')
})

test('confirmed + failed refresh keeps success; retry only two GET; next fresh form can submit deliberate duplicate', async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', { data: record })
  e.queue(histPath(animalId), { status: 503 }); e.queue(animalPath(animalId), { data: animal })
  await e.form().props.onCreate(payload); e.render()
  assert.match(text(e.tree()), /guardado correctamente/); assert.equal(e.form().props.disabled, true)
  const old = e.form().props.onCreate, before = e.count('GET'); e.sync()
  button(e.tree(), 'Recuperar lecturas').props.onClick(); await tick(); e.render()
  assert.equal(e.count('GET') - before, 2); assert.equal(e.count('POST'), 1); assert.equal(e.form().props.disabled, false)
  await old(payload); assert.equal(e.count('POST'), 1)
  e.prepare(); e.queue('POST', { data: { ...record, id: id(77) } }); e.sync([{ ...record, id: id(77) }, record])
  await e.form().props.onCreate(payload); assert.equal(e.count('POST'), 2, 'duplicates remain allowed after completed first attempt')
})

for (const recovery of [[], [{ ...record, id: id(91), notes: 'other' }]]) {
  test(`uncertain recovery ${JSON.stringify(recovery)} still blocks; empty history proves neither existence nor outcome`, async () => {
    const e = env(); await e.ready(); e.prepare(); e.queue('POST', { status: 503 }); await e.form().props.onCreate(payload); e.render()
    e.sync(recovery); button(e.tree(), 'Recuperar lecturas').props.onClick(); await tick(); e.render()
    assert.match(text(e.tree()), /no demuestran el resultado/); assert.equal(e.form().props.disabled, true); assert.equal(e.count('POST'), 1)
  })
}

for (const broken of ['history', 'animal', 'identity']) {
  test(`uncertain recovery invalid ${broken} never unlocks`, async () => {
    const e = env(); await e.ready(); e.prepare(); e.queue('POST', { status: 503 }); await e.form().props.onCreate(payload); e.render()
    e.queue(histPath(animalId), broken === 'history' ? { status: 503 } : { data: [record] })
    e.queue(animalPath(animalId), broken === 'animal' ? { status: 503 } : { data: broken === 'identity' ? { ...animal, id: id(99) } : animal })
    button(e.tree(), 'Recuperar lecturas').props.onClick(); await tick(); e.render()
    assert.equal(e.form().props.disabled, true); assert.match(text(e.tree()), /Resultado incierto/); assert.equal(e.count('POST'), 1)
  })
}

test('two synchronous parent handlers while preparation/POST pending produce exactly one POST', async () => {
  const e = env(); await e.ready(); const d = deferred(); e.prepare(); e.queue('POST', () => d.promise); e.sync()
  const create = e.form().props.onCreate, first = create(payload)
  await create(payload); await tick(); e.render(); await e.form().props.onCreate(payload)
  assert.equal(e.count('POST'), 1)
  const attempt = e.protocol.getAttempt(e.protocol.attemptKey(1, organizationId, animalId))
  assert.equal(Object.isFrozen(attempt.payload), true); assert.equal(attempt.phase, 'pending')
  d.resolve({ data: record }); await first; assert.equal(e.count('POST'), 1)
})

for (const setup of ['inactive female', 'male female', 'invalid animal schema', 'wrong female identity', 'inactive male', 'female male', 'wrong male identity', 'catalog missing', 'catalog invalid', 'female 404', 'male 404']) {
  test(`fresh preparation rejects ${setup} before any POST`, async () => {
    const e = env(); await e.ready(); const p = { ...payload, male_id: male.id }
    e.queue(animalPath(animalId), setup === 'female 404' ? { status: 404 } : { data: { ...animal,
      ...(setup === 'inactive female' ? { is_active: false } : setup === 'male female' ? { gender_id: genders[1].id } : setup === 'invalid animal schema' ? { status_id: null } : setup === 'wrong female identity' ? { id: id(99) } : {}) } })
    e.queue('/api/catalogs/breeding-types', { data: setup === 'catalog missing' ? [] : setup === 'catalog invalid' ? {} : types })
    e.queue('/api/catalogs/genders', { data: genders })
    e.queue(animalPath(male.id), setup === 'male 404' ? { status: 404 } : { data: { ...male,
      ...(setup === 'inactive male' ? { is_active: false } : setup === 'female male' ? { gender_id: genders[0].id } : setup === 'wrong male identity' ? { id: id(99) } : {}) } })
    await assert.rejects(e.form().props.onCreate(p)); e.render()
    assert.equal(e.count('POST'), 0); assert.equal(e.protocol.getAttempt(e.protocol.attemptKey(1, organizationId, animalId)), undefined)
  })
}

test('invalid input before preparation: dose-free business rules only, no new age/species/pregnancy constraints', async () => {
  const e = env(); await e.ready()
  for (const invalid of [{ date: '2099-01-01' }, { date: '2025-02-30' }, { expected_birth: '2025-01-01' },
    { male_id: animalId }, { male_id: 'bad' }, { breeding_type_id: 'bad' }, { animal_id: id(99) }, { technician: 'x'.repeat(151) }, { notes: null }]) {
    await assert.rejects(e.form().props.onCreate({ ...payload, ...invalid }))
  }
  assert.equal(e.count('POST'), 0); assert.equal(e.count('GET'), 5)
})

test('VIEWER history remains available with no form/callback; empty history is valid', async () => {
  const e = env(); await e.ready({ canWrite: false }); assert.equal(e.form(), undefined); assert.ok(e.history()); assert.equal(e.count('POST'), 0)
  e.context({ status: 'loaded', currentOrganization: { id: organizationId }, canWrite: false })
  assert.equal(e.outer().props.canWrite, false)
})

test('history is independently readable after option failure, wrong-animal history blocks CREATE', async () => {
  const e = env(); e.queue(histPath(animalId), { data: [record] }); e.queue('/api/catalogs/breeding-types', { status: 503 })
  e.queue('/api/catalogs/genders', { data: genders }); e.queue('/api/animals/', { data: [animal] }); e.queue(animalPath(animalId), { data: animal })
  e.render(); await tick(); e.render(); assert.equal(e.history().props.history.length, 1); assert.equal(e.form(), undefined)
  const f = env(); f.defaults([{ ...record, animal_id: id(99) }]); f.render(); await tick(); f.render()
  assert.equal(f.form().props.disabled, true)
  f.queue(histPath(animalId), { data: [] }); button(f.tree(), 'Actualizar historial').props.onClick(); f.render(); await tick(); f.render()
  assert.equal(f.form().props.disabled, false); assert.equal(f.history().props.history.length, 0)
})

for (const fresh of [{ ...animal, is_active: false }, { ...animal, gender_id: genders[1].id }]) {
  test(`fresh initial Animal gates form ${JSON.stringify(fresh)}`, async () => {
    const e = env(); e.defaults([], fresh); e.render(); await tick(); e.render()
    assert.equal(e.form(), undefined); assert.match(text(e.tree()), /hembras activas/)
  })
}

for (const stage of ['history', 'options', 'preparing', 'pending', 'refresh', 'recovery']) {
  test(`A-B-A at ${stage}: aborted late work cannot contaminate new scope; unresolved attempts survive`, async () => {
    const e = env(), d = deferred(); let work
    if (stage === 'history') {
      e.queue(histPath(animalId), () => d.promise); e.queue('/api/catalogs/breeding-types', { data: types }); e.queue('/api/catalogs/genders', { data: genders })
      e.queue('/api/animals/', { data: [animal, male] }); e.queue(animalPath(animalId), { data: animal }); e.render(); await tick()
    } else if (stage === 'options') {
      e.queue(histPath(animalId), { data: [] }); e.queue('/api/catalogs/breeding-types', () => d.promise); e.queue('/api/catalogs/genders', { data: genders })
      e.queue('/api/animals/', { data: [animal, male] }); e.queue(animalPath(animalId), { data: animal }); e.render(); await tick()
    } else {
      await e.ready()
      if (stage === 'preparing') {
        e.queue(animalPath(animalId), () => d.promise); e.queue('/api/catalogs/breeding-types', { data: types }); e.queue('/api/catalogs/genders', { data: genders })
        work = e.form().props.onCreate(payload)
      } else {
        e.prepare(); e.queue('POST', stage === 'pending' ? () => d.promise : stage === 'recovery' ? { status: 503 } : { data: record })
        if (stage === 'refresh') { e.queue(histPath(animalId), () => d.promise); e.queue(animalPath(animalId), { data: animal }) }
        work = e.form().props.onCreate(payload); await tick()
        if (stage === 'recovery') {
          await work; e.render(); e.queue(histPath(animalId), () => d.promise); e.queue(animalPath(animalId), { data: animal })
          button(e.tree(), 'Recuperar lecturas').props.onClick()
        }
      }
    }
    await tick(); const snapshot = text(e.tree()); e.h.unmount()
    assert.ok(e.calls.every(call => call.signal.aborted))
    const b = env(e.protocol); await b.ready({ animal: { ...animal, id: id(100) } }); assert.equal(b.form().props.disabled, false)
    d.resolve({ data: stage === 'options' ? types : stage === 'pending' ? record : stage === 'preparing' ? animal : [record] })
    if (work) await work; await tick(); assert.equal(text(e.tree()), snapshot)
    const back = env(e.protocol); await back.ready()
    const unresolved = ['pending', 'refresh', 'recovery'].includes(stage)
    assert.equal(back.form().props.disabled, unresolved)
    if (unresolved) { await back.form().props.onCreate(payload); assert.equal(back.count('POST'), 0) }
  })
}

for (const stage of ['initial', 'preparing', 'pending', 'refresh', 'recovery']) {
  for (const logout of [false, true]) test(`session revision/logout ${logout} during ${stage} ignores stale response`, async () => {
    const e = env(), d = deferred(); let work
    if (stage === 'initial') {
      e.queue(histPath(animalId), () => d.promise); e.queue('/api/catalogs/breeding-types', { data: types }); e.queue('/api/catalogs/genders', { data: genders })
      e.queue('/api/animals/', { data: [animal, male] }); e.queue(animalPath(animalId), { data: animal }); e.render(); await tick()
    } else {
      await e.ready()
      if (stage === 'preparing') {
        e.queue(animalPath(animalId), () => d.promise); e.queue('/api/catalogs/breeding-types', { data: types }); e.queue('/api/catalogs/genders', { data: genders })
      } else {
        e.prepare(); e.queue('POST', stage === 'pending' ? () => d.promise : stage === 'recovery' ? { status: 503 } : { data: record })
        if (stage === 'refresh') { e.queue(histPath(animalId), () => d.promise); e.queue(animalPath(animalId), { data: animal }) }
      }
      work = e.form().props.onCreate(payload); await tick()
      if (stage === 'recovery') { await work; e.render(); e.queue(histPath(animalId), () => d.promise); e.queue(animalPath(animalId), { data: animal }); button(e.tree(), 'Recuperar lecturas').props.onClick() }
    }
    e.render(); const before = text(e.tree()), writes = e.count('POST'); e.changeSession(logout)
    d.resolve({ data: stage === 'preparing' ? animal : stage === 'pending' ? record : [record] })
    if (work) await work; await tick(); e.render()
    assert.equal(text(e.tree()), before); assert.equal(e.count('POST'), writes)
  })
}

test('outer scope key includes organization, revision, Animal and write capability', () => {
  const e = env(); const before = e.outer().key
  e.changeSession(); assert.notEqual(e.outer().key, before)
  const changed = e.outer().key
  e.context({ status: 'loaded', currentOrganization: { id: id(99) }, canWrite: true }); assert.notEqual(e.outer().key, changed)
})

function formEnv(onCreate, suppliedEnv) {
  const e = suppliedEnv ?? env(), h = harness()
  const Form = load('./components/BreedingForm.tsx', { react: h.react, 'react/jsx-runtime': jsx,
    '../../components/FieldError': mod(() => null), '../../lib/api-errors': e.errors, '../breeding.service': e.service, '../validation': validation })
  const props = { animal, types, males: [male], disabled: false, businessToday: '2026-10-05', onCreate }
  let tree
  function render() { tree = h.render(Form.default, props); return tree }
  function set(control, value) { nodes(tree).find(n => n.props?.id === control).props.onChange({ target: { value } }); render() }
  render(); set('breeding-type', types[0].id); set('breeding-date', payload.date)
  return { h, props, render, set, tree: () => tree, submit: () => nodes(tree).find(n => n.type === 'form').props.onSubmit({ preventDefault() {} }) }
}

for (const action of ['rapid clicks', 'repeated Enter', 'simultaneous handler calls']) {
  test(`real form ${action}: one callback/POST per attempt, trimming preserved`, async () => {
    const e = env(); await e.ready(); e.prepare(); const d = deferred(); e.queue('POST', () => d.promise); e.sync()
    const f = formEnv(e.form().props.onCreate)
    f.set('breeding-technician', '  Técnico  '); f.set('breeding-notes', '  notas\n ')
    const first = f.submit(); await f.submit(); await tick(); await f.submit()
    assert.equal(e.count('POST'), 1)
    d.resolve({ data: { ...record, technician: 'Técnico', notes: 'notas' } }); await first
    assert.equal(JSON.parse(e.calls.find(c => c.method === 'POST').body).technician, 'Técnico')
    assert.equal(JSON.parse(e.calls.find(c => c.method === 'POST').body).notes, 'notas')
    f.h.unmount()
  })
}

test('real form technician maxLength/validation and FieldError are retained; errors do not clear fields', async () => {
  let calls = 0
  const f = formEnv(async () => { calls++; throw new Error('rechazo') })
  assert.equal(nodes(f.tree()).find(n => n.props?.id === 'breeding-technician').props.maxLength, 150)
  f.set('breeding-technician', 'x'.repeat(151)); await f.submit(); f.render(); assert.equal(calls, 0); assert.match(text(f.tree()), /150/)
  f.set('breeding-technician', 'x'.repeat(150)); await f.submit(); f.render(); assert.equal(calls, 1)
  assert.equal(nodes(f.tree()).find(n => n.props?.id === 'breeding-technician').props.value.length, 150)
  f.h.unmount()
})

test('out of order history retries ignore the aborted older result', async () => {
  // First force the existing READ retry UI; then invoke its captured handler twice.
  const failed = env(); failed.queue(histPath(animalId), { status: 503 })
  failed.queue('/api/catalogs/breeding-types', { data: types }); failed.queue('/api/catalogs/genders', { data: genders })
  failed.queue('/api/animals/', { data: [animal, male] }); failed.queue(animalPath(animalId), { data: animal })
  failed.render(); await tick(); failed.render()
  const retry = button(failed.tree(), 'Actualizar historial').props.onClick, d = deferred()
  failed.queue(histPath(animalId), () => d.promise, { data: [{ ...record, id: id(95) }] })
  retry(); failed.render(); retry(); failed.render(); await tick(); failed.render()
  assert.equal(failed.history().props.history[0].id, id(95))
  d.resolve({ data: [record] }); await tick(); failed.render()
  assert.equal(failed.history().props.history[0].id, id(95))
  const reads = failed.calls.filter(c => c.path === histPath(animalId))
  assert.equal(reads[1].signal.aborted, true)
})

test('late initial history cannot overwrite a newer uncertain recovery on A-B-A remount', async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', { status: 503 }); await e.form().props.onCreate(payload); e.h.unmount()
  const back = env(e.protocol), d = deferred()
  back.queue(histPath(animalId), () => d.promise)
  back.queue('/api/catalogs/breeding-types', { data: types }); back.queue('/api/catalogs/genders', { data: genders })
  back.queue('/api/animals/', { data: [animal, male] }); back.queue(animalPath(animalId), { data: animal })
  back.render(); await tick(); back.render()
  back.sync([{ ...record, id: id(95) }]); button(back.tree(), 'Recuperar lecturas').props.onClick(); await tick(); back.render()
  assert.equal(back.history().props.history[0].id, id(95))
  d.resolve({ data: [record] }); await tick(); back.render()
  assert.equal(back.history().props.history[0].id, id(95)); assert.equal(back.form().props.disabled, true)
})

for (const status of [400, 401, 403, 404, 422, 503]) {
  test(`preparation GET error ${status} sends no POST and never creates write uncertainty`, async () => {
    const e = env(); await e.ready()
    e.queue(animalPath(animalId), { status }); e.queue('/api/catalogs/breeding-types', { data: types }); e.queue('/api/catalogs/genders', { data: genders })
    if (status === 401) await e.form().props.onCreate(payload)
    else await assert.rejects(e.form().props.onCreate(payload))
    e.h.unmount()
    assert.equal(e.count('POST'), 0); assert.equal(e.protocol.getAttempt(e.protocol.attemptKey(1, organizationId, animalId)), undefined)
  })
}

test('late options from old organization are aborted and cannot populate the new organization', async () => {
  const e = env(), d = deferred()
  e.queue(histPath(animalId), { data: [] }); e.queue('/api/catalogs/breeding-types', () => d.promise)
  e.queue('/api/catalogs/genders', { data: genders }); e.queue('/api/animals/', { data: [animal, male] }); e.queue(animalPath(animalId), { data: animal })
  e.render(); await tick(); const before = text(e.tree()); e.h.unmount()
  const other = env(e.protocol); await other.ready({ organizationId: id(99) })
  d.resolve({ data: [{ id: id(999), code: 'OLD', name: 'Old tenant type' }] }); await tick()
  assert.equal(text(e.tree()), before); assert.equal(other.form().props.types[0].id, types[0].id)
})

test('confirmed refresh invalid Animal identity remains locked and only GET recovery is possible', async () => {
  const e = env(); await e.ready(); e.prepare(); e.queue('POST', { data: record }); e.sync([record], { ...animal, id: id(99) })
  await e.form().props.onCreate(payload); e.render()
  assert.equal(e.form().props.disabled, true); assert.match(text(e.tree()), /guardado correctamente/)
  await e.form().props.onCreate(payload); assert.equal(e.count('POST'), 1)
  const before = e.count('GET'); e.sync(); button(e.tree(), 'Recuperar lecturas').props.onClick(); await tick(); e.render()
  assert.equal(e.count('GET') - before, 2); assert.equal(e.count('POST'), 1); assert.equal(e.form().props.disabled, false)
})

test('known rejection permits a fresh safe retry; frozen payload cannot be changed by caller during preparation', async () => {
  const e = env(); await e.ready(); const p = { ...payload }; e.prepare(p); e.queue('POST', { status: 400 })
  const rejected = e.form().props.onCreate(p); p.notes = 'mutated after submit'
  await assert.rejects(rejected); assert.equal(JSON.parse(e.calls.find(c => c.method === 'POST').body).notes, '')
  e.render(); e.prepare(); e.queue('POST', { data: record }); e.sync()
  assert.equal(await e.form().props.onCreate(payload), true); assert.equal(e.count('POST'), 2)
})

test('real form exposes Ninja 422 FieldError and unmounted handlers do not clear or mutate data', async () => {
  const e = env(), d = deferred()
  const f = formEnv(async () => { throw new e.api.ApiError(422, { detail: [{ loc: ['body', 'payload', 'technician'], msg: 'too long' }] }) }, e)
  await f.submit(); f.render()
  assert.equal(nodes(f.tree()).find(n => n.props?.id === 'breeding-technician').props['aria-invalid'], true)
  assert.match(text(f.tree()), /too long/)
  f.h.unmount()
  const late = formEnv(() => d.promise); late.set('breeding-notes', 'persist form draft'); const work = late.submit(); late.h.unmount()
  const before = late.h.slots.slice(); d.resolve(true); await work
  assert.deepEqual(late.h.slots.slice(), before)
})

for (const domain of ['Pregnancy', 'Births']) {
  test(`existing ${domain} consumes validated Breeding service without signature or flow changes`, async () => {
    const e = env(), h = harness(), Form = () => null, History = () => null
    const pregnancy = { id: id(150), animal_id: animalId, breeding_id: record.id, diagnosis_date: '2025-01-02', expected_birth: '2025-10-01', confirmed: true, notes: null, status: 'ACTIVE' }
    const unexpected = () => { throw new Error('No writes are allowed in this compatibility check') }
    const imports = { react: h.react, 'react/jsx-runtime': jsx, '../../auth/WriteOnly': mod(() => null),
      '../../animals/animals.service': { getAnimals: async () => [animal, male] },
      '../../animals/animal-options.service': { getGenders: async () => genders }, '../../auth/session': e.session,
      '../../breeding/breeding.service': e.service, '../../lib/api-errors': e.errors, '../../lib/api': e.api }
    e.queue(histPath(animalId), { data: [{ ...record, technician: null, notes: null }] })
    if (domain === 'Pregnancy') {
      e.queue('/api/catalogs/breeding-types', { data: types })
      e.queue('/api/animals/', { data: [animal, male] }); e.queue('/api/catalogs/genders', { data: genders })
      e.queue(animalPath(animalId), { data: animal })
      imports['../../auth/current-context'] = { useCurrentContext: () => ({ status: 'loaded', currentOrganization: { id: organizationId }, canWrite: true }) }
      imports['../../auth/business-time'] = load('../auth/business-time.ts', {})
      imports['../../lib/api'] = e.api
      imports['../create-protocol'] = load('../pregnancy/create-protocol.ts', {})
      imports['../abort-protocol'] = load('../pregnancy/abort-protocol.ts', {})
      imports['../validation'] = load('../pregnancy/validation.ts', { '../breeding/validation': validation })
      imports['../pregnancy.service'] = { createPregnancy: unexpected, abortPregnancy: unexpected, getAnimalPregnancyHistory: async () => [], pregnancyErrorMessage: e.service.breedingErrorMessage }
      imports['./PregnancyForm'] = mod(Form); imports['./PregnancyHistory'] = mod(History)
    } else {
      e.queue('/api/animals/', { data: [animal, male] }); e.queue('/api/catalogs/genders', { data: genders })
      e.queue(animalPath(animalId), { data: animal })
      imports['../../auth/current-context'] = { useCurrentContext: () => ({ status: 'loaded', currentOrganization: { id: organizationId }, canWrite: true }) }
      imports['../../auth/business-time'] = load('../auth/business-time.ts', {})
      imports['../create-protocol'] = load('../births/create-protocol.ts', {})
      imports['../validation'] = load('../births/validation.ts', { '../breeding/validation': validation })
      imports['../../pregnancy/pregnancy.service'] = { getAnimalPregnancyHistory: async () => [pregnancy] }
      imports['../births.service'] = { createBirth: unexpected, getAnimalBirthHistory: async () => [], birthErrorMessage: e.service.breedingErrorMessage }
      imports['./BirthForm'] = mod(Form); imports['./BirthHistory'] = mod(History)
    }
    const component = load(`../${domain === 'Pregnancy' ? 'pregnancy' : 'births'}/components/${domain}.tsx`, imports)
    const inner = domain === 'Pregnancy' ? { type: component.PregnancyScope, props: { animal, revision: 1, organizationId, canWrite: true,
      businessTimeLease: null, refreshCurrentContext: async () => { throw new Error('No CREATE preparation expected') }, isCurrentOrganization: org => org === organizationId } }
      : { type: component.BirthScope, props: { animal, revision: 1, organizationId, canWrite: true, businessTimeLease: null, refreshCurrentContext: unexpected, isCurrentOrganization: org => org === organizationId } }
    h.render(inner.type, inner.props); await tick(); const tree = h.render(inner.type, inner.props)
    const form = find(tree, Form)
    assert.ok(form, text(tree)); assert.equal((form.props.events ?? form.props.breedings)[0].id, record.id)
    assert.equal(e.count('POST'), 0); h.unmount()
  })
}
