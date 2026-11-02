import { detailImports } from '../reproduction/test-support.mjs'
import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { load, nodes, text, button, tick, deferred } from './test-support.mjs'
import { env, id, animalId, organizationId, animal, payload, record } from './flow-test-support.mjs'

const path = eventId => `/api/breeding/${eventId}`
function detailUI(e) {
  const History = load('./components/BreedingHistory.tsx', { ...detailImports, 'react/jsx-runtime': jsx, '../breeding.service': e.service })
  return History.default(e.history().props)
}
function click(e, eventId = record.id) {
  const row = nodes(detailUI(e)).find(n => n.type === 'tr' && n.key === eventId)
  nodes(row).find(n => n.type === 'button' && text(n).includes('Ver detalles')).props.onClick({ preventDefault() {} })
  e.render()
}
const detail = e => e.history().props.detail

test('click opens explicit loading and displays individual GET data, never cached list text', async () => {
  const e = env(), d = deferred(), cached = { ...record, notes: 'cached notes', technician: 'cached technician' }
  await e.ready(undefined, [cached]); e.queue(path(record.id), () => d.promise)
  click(e)
  assert.equal(detail(e).status, 'loading'); assert.match(text(detailUI(e)), /Cargando detalle/)
  assert.doesNotMatch(text(detailUI(e)), /cached notes|cached technician/)
  const fresh = { ...record, date: '2099-01-01', expected_birth: '2020-01-01', technician: '  fresh technician  ', notes: '\n fresh notes \n' }
  d.resolve({ data: fresh }); await tick(); e.render()
  assert.equal(detail(e).status, 'success')
  assert.deepEqual({ ...detail(e).record }, fresh)
  const dl = nodes(detailUI(e)).find(n => n.type === 'dl')
  assert.match(text(dl), /fresh technician/); assert.match(text(dl), /fresh notes/); assert.match(text(dl), /01\/01\/2099/)
  assert.doesNotMatch(text(dl), /cached/)
  const request = e.calls.find(c => c.path === path(record.id))
  assert.equal(request.method, undefined); assert.equal(request.cache, 'no-store'); assert.ok(request.signal instanceof AbortSignal)
  assert.equal(e.count('POST'), 0); e.h.unmount()
})

for (const [name, data] of [
  ['wrong event', { ...record, id: id(99) }], ['wrong animal', { ...record, animal_id: id(99) }],
  ['null', null], ['array', [record]], ['missing field', { ...record, notes: undefined }],
  ['invalid date', { ...record, date: '2026-02-30' }], ['invalid male', { ...record, male_id: '' }],
  ['invalid type', { ...record, breeding_type_id: 42 }], ['invalid technician', { ...record, technician: 42 }],
  ['invalid expected birth', { ...record, expected_birth: '' }],
]) {
  test(`individual GET rejects ${name} and permits GET-only recovery`, async () => {
    const e = env(); await e.ready(undefined, [record]); e.queue(path(record.id), { data })
    click(e); await tick(); e.render()
    assert.equal(detail(e).status, 'error'); assert.equal(nodes(detailUI(e)).some(n => n.type === 'dl'), false)
    e.queue(path(record.id), { data: { ...record, notes: 'recovered' } })
    button(detailUI(e), 'Reintentar detalle').props.onClick(); await tick(); e.render()
    assert.equal(detail(e).status, 'success'); assert.match(text(detailUI(e)), /recovered/)
    assert.equal(e.count('POST'), 0); e.h.unmount()
  })
}

for (const status of [404, 403, 503]) {
  test(`detail ${status} shows an explicit recoverable error without cached fallback`, async () => {
    const e = env(); await e.ready(undefined, [{ ...record, notes: 'cached secret' }]); e.queue(path(record.id), { status })
    click(e); await tick(); e.render()
    assert.equal(detail(e).status, 'error'); assert.doesNotMatch(text(detailUI(e)), /cached secret/)
    if (status === 404) assert.equal(detail(e).message, 'El evento reproductivo ya no está disponible.')
    e.queue(path(record.id), { data: record }); button(detailUI(e), 'Reintentar detalle').props.onClick()
    await tick(); e.render(); assert.equal(detail(e).status, 'success'); assert.equal(e.count('POST'), 0); e.h.unmount()
  })
}

test('closing pending detail aborts and clears it; reopening fetches again and ignores late response', async () => {
  const e = env(), d = deferred(); await e.ready(undefined, [record]); e.queue(path(record.id), () => d.promise)
  click(e); click(e)
  assert.equal(detail(e).status, 'idle'); assert.equal(e.calls.find(c => c.path === path(record.id)).signal.aborted, true)
  e.queue(path(record.id), { data: { ...record, notes: 'reopened fresh' } }); click(e); await tick(); e.render()
  d.resolve({ data: { ...record, notes: 'late closed' } }); await tick(); e.render()
  assert.match(text(detailUI(e)), /reopened fresh/); assert.doesNotMatch(text(detailUI(e)), /late closed/)
  assert.equal(e.calls.filter(c => c.path === path(record.id)).length, 2)
  click(e); assert.equal(detail(e).status, 'idle'); assert.equal(e.history().props.history.length, 1); e.h.unmount()
})

test('closing an error clears it and reopening starts a fresh loading state', async () => {
  const e = env(); await e.ready(undefined, [record]); e.queue(path(record.id), { status: 404 })
  click(e); await tick(); e.render(); click(e)
  assert.equal(detail(e).status, 'idle'); assert.doesNotMatch(text(detailUI(e)), /no está disponible/)
  const d = deferred(); e.queue(path(record.id), () => d.promise); click(e)
  assert.equal(detail(e).status, 'loading'); d.resolve({ data: record }); await tick(); e.render(); e.h.unmount()
})

test('X then Y: only one panel opens and late X cannot replace Y', async () => {
  const e = env(), x = deferred(), y = { ...record, id: id(99) }
  await e.ready(undefined, [record, y]); e.queue(path(record.id), () => x.promise); e.queue(path(y.id), { data: { ...y, notes: 'Y fresh' } })
  click(e); click(e, y.id); await tick(); e.render()
  assert.equal(nodes(detailUI(e)).filter(n => n.type === 'section' && n.props.className === 'repro-detail').length, 1)
  assert.equal(detail(e).eventId, y.id); assert.match(text(detailUI(e)), /Y fresh/)
  x.resolve({ data: { ...record, notes: 'X late' } }); await tick(); e.render()
  assert.equal(detail(e).eventId, y.id); assert.doesNotMatch(text(detailUI(e)), /X late/); e.h.unmount()
})

test('VIEWER with expired/missing business time can open historical detail without write controls', async () => {
  const e = env(); await e.ready({ canWrite: false, businessTimeLease: null }, [record])
  e.queue(path(record.id), { data: { ...record, notes: null, technician: null, date: '2099-01-01' } })
  click(e); await tick(); e.render()
  assert.equal(detail(e).status, 'success'); assert.equal(e.form(), undefined)
  assert.doesNotMatch(text(detailUI(e)), /Editar|Eliminar|Guardar/)
  assert.equal(e.calls.filter(c => c.path === '/api/common/context').length, 0)
  assert.equal(e.count('POST'), 0); e.h.unmount()
})

test('writer with expired business time still reads detail while CREATE stays disabled', async () => {
  const e = env(); await e.ready({ businessTimeLease: { receivedMonotonic: 0, receivedWall: 0, remainingMs: 0 } }, [record])
  assert.equal(e.form().props.disabled, true)
  e.queue(path(record.id), { data: record }); click(e); await tick(); e.render()
  assert.equal(detail(e).status, 'success'); assert.equal(e.form().props.disabled, true); e.h.unmount()
})

for (const transition of ['animal A-B', 'animal A-B-A', 'organization A-B-A']) {
  test(`${transition} aborts old detail and preserves a new scope against its late response`, async () => {
    const e = env(), d = deferred(); await e.ready(undefined, [record]); e.queue(path(record.id), () => d.promise); click(e)
    const oldTree = text(detailUI(e)); e.h.unmount()
    assert.equal(e.calls.find(c => c.path === path(record.id)).signal.aborted, true)
    const next = env(), nextAnimal = transition.startsWith('animal') ? { ...animal, id: id(100) } : animal
    await next.ready({ animal: nextAnimal, organizationId: transition.startsWith('organization') ? id(200) : organizationId }, [])
    assert.equal(detail(next).status, 'idle'); next.h.unmount()
    const back = env(), fresh = { ...record, notes: 'new scope fresh' }
    await back.ready(undefined, [record]); back.queue(path(record.id), { data: fresh }); click(back); await tick(); back.render()
    d.resolve({ data: { ...record, notes: 'old scope late' } }); await tick(); back.render()
    assert.match(text(detailUI(back)), /new scope fresh/); assert.doesNotMatch(text(detailUI(back)), /old scope late/)
    assert.equal(text(detailUI(e)), oldTree); back.h.unmount()
  })
}

test('organization guard discards a late response even before React unmounts the old scope', async () => {
  const e = env(), d = deferred(); await e.ready(undefined, [record]); e.queue(path(record.id), () => d.promise); click(e)
  e.context({ status: 'loaded', currentOrganization: { id: id(99) }, canWrite: true })
  d.resolve({ data: { ...record, notes: 'wrong tenant late' } }); await tick(); e.render()
  assert.equal(detail(e).status, 'loading'); assert.doesNotMatch(text(detailUI(e)), /wrong tenant late/)
  e.h.unmount()
})

for (const status of [200, 401, 403]) {
  test(`logout/login rejects old-session detail ${status} without affecting new session`, async () => {
    const e = env(), d = deferred(); await e.ready(undefined, [record]); e.queue(path(record.id), () => d.promise); click(e)
    e.changeSession(true); e.changeSession(false)
    d.resolve({ status, data: { ...record, notes: 'old session' } }); await tick(); e.render()
    assert.equal(detail(e).status, 'loading'); assert.doesNotMatch(text(detailUI(e)), /old session/)
    assert.ok(e.session.getSession()); e.h.unmount()
  })
}

test('current-session 401 uses global session invalidation and never renders detail', async () => {
  const e = env(); await e.ready(undefined, [record]); e.queue(path(record.id), { status: 401 })
  click(e); await tick(); e.render()
  assert.equal(e.session.getSession(), null); assert.notEqual(detail(e).status, 'success'); e.h.unmount()
})

test('real global api/session revision guards ignore stale 401 after login', async () => {
  const storage = new Map(), d = deferred()
  const session = load('../auth/session.ts', {}, { localStorage: { getItem: k => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k) } })
  const user = { id: id(90), email: 'test@example.com', first_name: '', last_name: '' }
  session.saveSession({ access: 'old-token', refresh: 'refresh', user })
  const api = load('../lib/api.ts', { '../auth/session': session }, { fetch: () => d.promise })
  const work = api.apiRequest(path(record.id), { accessToken: 'old-token' })
  session.saveSession({ access: 'new-token', refresh: 'refresh', user })
  d.resolve({ status: 401, ok: false, json: async () => ({ detail: 'Unauthorized' }) })
  await assert.rejects(work)
  assert.equal(session.getSession().access, 'new-token')
})

test('service validates request UUIDs and never transforms nullable detail fields', async () => {
  const e = env()
  await assert.rejects(e.service.getBreedingEvent('bad', animalId, 'token'))
  await assert.rejects(e.service.getBreedingEvent(record.id, 'bad', 'token'))
  assert.equal(e.calls.length, 0)
  const nullable = { ...record, technician: null, notes: null }
  e.queue(path(record.id), { data: nullable })
  const result = await e.service.getBreedingEvent(record.id, animalId, 'token')
  assert.deepEqual({ ...result }, nullable)
})

test('detail reads do not disturb CREATE SAFE confirmed/uncertain phases', async () => {
  const e = env(); await e.ready(undefined, [record]); e.prepare(); e.queue('POST', { status: 503 })
  await e.form().props.onCreate(payload); e.render(); assert.equal(e.form().props.disabled, true)
  e.queue(path(record.id), { data: record }); click(e); await tick(); e.render()
  assert.equal(detail(e).status, 'success'); assert.equal(e.form().props.disabled, true)
  assert.match(text(e.tree()), /Resultado incierto/); assert.equal(e.count('POST'), 1); e.h.unmount()
})
