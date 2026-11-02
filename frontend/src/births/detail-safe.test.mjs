import { detailImports } from '../reproduction/test-support.mjs'
import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { load, mod, harness, nodes, text, button, deferred } from '../breeding/test-support.mjs'
import { env, payload, record, animal, pregnancy, id } from './flow-test-support.mjs'
const path = b => `/api/births/${b}`
const fresh = { ...record, birth_date: '2020-01-02', birth_weight: '41.00', notes: 'fresh note', alive: false, calf_id: null, calf_gender_id: null, dystocia: true }
const ready = async (e, rows = [record]) => { await e.ready({ canWrite: false, businessTimeLease: null }, rows); return e.history().props.onOpenDetail }

test('VIEWER no business_time opens fresh individual GET with no-store signal and exact identity', async () => {
  const e = env(); const open = await ready(e); e.queue(path(record.id), { data: fresh })
  const work = open(record.id); e.render(); assert.equal(e.history().props.detail.status, 'loading')
  await work; e.render(); assert.equal(e.history().props.detail.status, 'success')
  assert.equal(e.history().props.detail.record.notes, 'fresh note'); assert.equal(e.history().props.history[0].notes, record.notes)
  const call = e.calls.find(c => c.path === path(record.id))
  assert.equal(call.cache, 'no-store'); assert.ok(call.signal instanceof AbortSignal); assert.equal(call.method, undefined)
  assert.equal(e.form(), undefined); assert.equal(e.count('POST'), 0); assert.equal(e.changed(), 0); assert.equal(e.calls.length, 2)
})
for (const role of ['OWNER', 'ADMIN', 'VETERINARIAN', 'OPERATOR', 'VIEWER']) test(`${role} can close and reopen with a new GET`, async () => {
  const e = env(); await ready(e); e.context({ currentRole: role }); e.queue(path(record.id), { data: fresh }, { data: { ...fresh, notes: 'newer' } })
  await e.history().props.onOpenDetail(record.id); e.render(); e.history().props.onCloseDetail(); e.render()
  assert.equal(e.history().props.detail.status, 'idle'); await e.history().props.onOpenDetail(record.id); e.render()
  assert.equal(e.history().props.detail.record.notes, 'newer'); assert.equal(e.calls.filter(c => c.path === path(record.id)).length, 2)
})
for (const change of [
  { id: 'bad' }, { id: id(199) }, { mother_id: id(199) }, { pregnancy_id: 'bad' },
  { birth_date: '2026-02-30' }, { birth_date: '0000-01-01' }, { birth_weight: 'NaN' }, { birth_weight: 30 },
  { alive: 'true' }, { dystocia: 1 }, { calf_id: undefined }, { calf_id: 'bad' }, { calf_gender_id: undefined },
  { calf_gender_id: 'bad' }, { notes: undefined }, { notes: 99 },
]) test(`invalid detail controlled error without history fallback ${JSON.stringify(change)}`, async () => {
  const e = env(); await ready(e); e.queue(path(record.id), { data: { ...record, ...change } })
  await e.history().props.onOpenDetail(record.id); e.render()
  assert.equal(e.history().props.detail.status, 'error'); assert.equal(e.history().props.detail.record, undefined)
  assert.equal(e.history().props.history[0].id, record.id); assert.equal(e.calls.length, 2); assert.equal(e.count('POST'), 0)
})
for (const value of [{ data: null }, { data: {} }, { data: [] }, { invalidJSON: true }, { status: 201, data: record }, new Error('network')]) test(`malformed detail never retries automatically ${JSON.stringify(value)}`, async () => {
  const e = env(); await ready(e); e.queue(path(record.id), value); await e.history().props.onOpenDetail(record.id); e.render()
  assert.equal(e.history().props.detail.status, 'error'); assert.equal(e.calls.length, 2)
})
test('404 keeps HISTORY and manual retry uses fresh GET only', async () => {
  const e = env(); await ready(e); e.queue(path(record.id), { status: 404 }, { data: fresh })
  await e.history().props.onOpenDetail(record.id); e.render()
  assert.equal(e.history().props.detail.message, 'Este parto ya no está disponible.')
  assert.equal(e.history().props.history.length, 1); assert.equal(e.history().props.detail.record, undefined)
  await e.history().props.onOpenDetail(record.id); e.render(); assert.equal(e.history().props.detail.status, 'success'); assert.equal(e.count('POST'), 0)
})
for (const response of [{ data: fresh }, { status: 404 }, new Error('late error')]) test(`close aborts and ignores late completion ${JSON.stringify(response)}`, async () => {
  const e = env(), d = deferred(); await ready(e); e.queue(path(record.id), () => d.promise)
  const work = e.history().props.onOpenDetail(record.id); e.render(); const call = e.calls.at(-1)
  e.history().props.onCloseDetail(); e.render(); assert.equal(call.signal.aborted, true)
  d.resolve(response); await work; e.render(); assert.equal(e.history().props.detail.status, 'idle')
})
for (const response of [{ data: fresh }, { status: 404 }, new Error('late X')]) test(`X to Y publishes only Y despite late X ${JSON.stringify(response)}`, async () => {
  const e = env(), d = deferred(), y = { ...record, id: id(199) }; await ready(e, [record, y])
  e.queue(path(record.id), () => d.promise); const xWork = e.history().props.onOpenDetail(record.id)
  e.queue(path(y.id), { data: { ...y, notes: 'Y fresh' } }); await e.history().props.onOpenDetail(y.id); e.render()
  assert.equal(e.calls.find(c => c.path === path(record.id)).signal.aborted, true)
  d.resolve(response); await xWork; e.render(); assert.equal(e.history().props.detail.birthId, y.id); assert.equal(e.history().props.detail.record.notes, 'Y fresh')
})
for (const change of ['A→B', 'A→B→A', 'session', 'organization', 'unmount']) test(`scope ${change} ignores old detail instance`, async () => {
  const e = env(), d = deferred(); await ready(e); e.queue(path(record.id), () => d.promise)
  const work = e.history().props.onOpenDetail(record.id); e.render()
  if (change === 'session') e.changeSession()
  else if (change === 'organization') e.context({ currentOrganization: { id: id(999) } })
  else e.h.unmount()
  d.resolve({ data: fresh }); await work; e.render(); assert.notEqual(e.history().props.detail.status, 'success')
  if (change.startsWith('A')) {
    const next = env(e.protocol); await next.ready({ canWrite: false, animal: change === 'A→B' ? { ...animal, id: id(999) } : animal }, change === 'A→B→A' ? [record] : [])
    assert.equal(next.history().props.detail.status, 'idle'); assert.equal(next.count('POST'), 0)
  }
})
for (const status of [401, 403, 500]) test(`detail ${status} respects global errors and preserves HISTORY`, async () => {
  const e = env(); await ready(e); e.queue(path(record.id), { status }); await e.history().props.onOpenDetail(record.id); e.render()
  assert.equal(e.history().props.history.length, 1); assert.equal(e.count('POST'), 0)
  assert.equal(e.history().props.detail.status, status === 401 ? 'loading' : 'error')
})
test('unknown history identity and invalid service request ids cannot issue GET', async () => {
  const e = env(); await ready(e); const before = e.calls.length
  await e.history().props.onOpenDetail(id(999)); await e.history().props.onOpenDetail('bad')
  await assert.rejects(e.service.getBirthDetail('bad', animal.id, 'token'))
  await assert.rejects(e.service.getBirthDetail(record.id, 'bad', 'token')); assert.equal(e.calls.length, before)
})
test('DETAIL cannot release uncertain ledger alter draft or change Pregnancy', async () => {
  const e = env(); await e.ready({}, [{ ...record, pregnancy_id: id(299) }]); e.prepare(); e.queue('POST', new Error('network'))
  await e.form().props.onCreate(payload); e.render(); const key = e.protocol.attemptKey(1, e.props.organizationId, animal.id), attempt = e.protocol.getAttempt(key)
  const form = e.form().props; e.queue(path(record.id), { data: fresh }); await e.history().props.onOpenDetail(record.id); e.render()
  e.history().props.onCloseDetail(); e.render(); assert.equal(e.protocol.getAttempt(key), attempt); assert.equal(attempt.phase, 'uncertain')
  assert.equal(e.form().props.animal.id, form.animal.id); assert.equal(e.form().props.disabled, true)
  assert.equal(await e.form().props.onCreate(payload), false); assert.equal(e.count('POST'), 1); assert.equal(e.changed(), 0)
})
for (const phase of ['preparing', 'pending', 'confirmed']) test(`DETAIL leaves ${phase} CREATE attempt untouched`, async () => {
  const e = env(); const key = e.protocol.attemptKey(1, e.props.organizationId, animal.id)
  e.protocol.beginPreparation(key, payload); e.protocol.preparePayload(key, payload); e.protocol.setAttemptPhase(key, phase)
  await e.ready({}, [record]); const attempt = e.protocol.getAttempt(key); e.queue(path(record.id), { data: fresh })
  await e.history().props.onOpenDetail(record.id); e.render(); e.history().props.onCloseDetail(); e.render()
  assert.equal(e.protocol.getAttempt(key), attempt); assert.equal(attempt.phase, phase); assert.equal(e.count('POST'), 0); assert.equal(e.changed(), 0)
})
test('real HISTORY action renders only fresh detail with UUID fallbacks and manual controls', async () => {
  const opens = [], closes = [], History = load('../births/components/BirthHistory.tsx', { ...detailImports, 'react/jsx-runtime': jsx }).default
  const props = { history: [{ ...record, notes: 'cached history note' }], animals: [], genders: [], disabled: true,
    detail: { status: 'idle' }, onOpenDetail: value => opens.push(value), onCloseDetail: () => closes.push(true) }
  let tree = History(props); const summary = nodes(tree).find(n => n.type === 'button' && text(n).includes('Ver detalles'))
  summary.props.onClick({ preventDefault() {} }); assert.deepEqual(opens, [record.id])
  tree = History({ ...props, detail: { status: 'loading', birthId: record.id } }); assert.match(text(tree), /Cargando detalle/)
  tree = History({ ...props, detail: { status: 'success', birthId: record.id, record: { ...fresh, calf_id: record.calf_id, calf_gender_id: record.calf_gender_id } } })
  const panel = nodes(tree).find(n => n.type === 'dl'); assert.match(text(panel), /fresh note/); assert.doesNotMatch(text(panel), /cached history note/)
  assert.match(text(panel), new RegExp(record.calf_id)); assert.match(text(panel), /41.00 kg/)
  button(tree, 'Volver al historial').props.onClick(); assert.equal(closes.length, 1)
  tree = History({ ...props, detail: { status: 'error', birthId: record.id, message: 'not available' } })
  assert.equal(nodes(tree).filter(n => n.type === 'dl').length, 0); button(tree, 'Reintentar detalle').props.onClick(); assert.equal(opens.length, 2)
  assert.doesNotMatch(text(tree), /Editar|Eliminar|Actualizar/)
})

test('opening and closing DETAIL preserves real CREATE draft including an unsubmitted invalid date', async () => {
  const e = env(); await e.ready({}, [{ ...record, pregnancy_id: id(299) }])
  const h = harness(), Form = load('../births/components/BirthForm.tsx', { react: h.react, 'react/jsx-runtime': jsx,
    '../../components/FieldError': mod(() => null), '../../lib/api-errors': { fieldErrorAttributes: () => ({}) } }).default
  let tree = h.render(Form, e.form().props)
  const control = name => nodes(tree).find(n => n.props?.id === name)
  control('birth-pregnancy').props.onChange({ target: { value: pregnancy.id } }); tree = h.render(Form, e.form().props); tree = h.render(Form, e.form().props)
  control('birth-date').props.onChange({ target: { value: '2026-10-06' } })
  control('birth-weight').props.onChange({ target: { value: '22.5' } })
  control('birth-notes').props.onChange({ target: { value: 'draft note' } }); tree = h.render(Form, e.form().props)
  const source = e.form().props.pregnancies, key = e.form().key
  e.queue(path(record.id), { data: fresh }); await e.history().props.onOpenDetail(record.id); e.render()
  assert.equal(e.form().props.pregnancies, source); assert.equal(e.form().key, key)
  tree = h.render(Form, e.form().props); assert.equal(control('birth-date').props.value, '2026-10-06')
  assert.equal(control('birth-weight').props.value, '22.5'); assert.equal(control('birth-notes').props.value, 'draft note')
  e.history().props.onCloseDetail(); e.render(); tree = h.render(Form, e.form().props)
  assert.equal(control('birth-date').props.value, '2026-10-06'); assert.equal(e.changed(), 0); assert.equal(e.count('POST'), 0)
})
